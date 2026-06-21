import json
import logging
import os
from uuid import UUID

from django.db.models import Q

from arches.app.models.models import Node, ResourceXResource, TileModel
from arches.app.utils.betterJSONSerializer import JSONSerializer
from arches.app.utils.data_management.resource_graphs.exporter import (
    get_graphs_for_export,
)
from arches.app.utils.data_management.resources.formats.archesfile import (
    ArchesFileWriter,
)
from arches_controlled_lists.models import List, ListItem
from arches_controlled_lists.utils.skos import SKOSWriter
from arches_resource_version_manager.models import VersionedResource

logger = logging.getLogger(__name__)

HERITAGE_ITEM_GRAPH_ID = "076f9381-7b00-11e9-8d6b-80000b44d1d9"
REGISTRY_GRAPH_NAME = "Registry"
VERSIONING_NODEGROUP_ID = "03d5eb66-d748-57cc-8390-5788078696d7"
VISIBILITY_LIST_ID = "63244526-1690-5cfb-af89-49bfe6667b23"


def get_visibility_nodes():
    """Discover all nodes that use the visibility controlled list.

    Returns a list of dicts keyed by graph_id, each with node_id,
    nodegroup_id, graph_name, and alias. Node IDs and aliases vary
    per graph — the controlled list UUID is the only stable identifier.
    """
    nodes = Node.objects.filter(
        config__controlledList=VISIBILITY_LIST_ID,
    ).select_related("graph", "nodegroup")

    results = []
    for node in nodes:
        results.append({
            "node_id": str(node.nodeid),
            "nodegroup_id": str(node.nodegroup_id),
            "graph_id": str(node.graph_id),
            "graph_name": str(node.graph.name),
            "alias": node.alias,
        })
    return results


def get_visibility_node_for_graph(visibility_nodes, graph_id):
    """Get the visibility node info for a specific graph, or None."""
    for node in visibility_nodes:
        if node["graph_id"] == str(graph_id):
            return node
    return None


def get_visibility_uris(target_labels):
    """Look up controlled list item URIs for the given visibility labels."""
    items = ListItem.objects.filter(
        list_id=VISIBILITY_LIST_ID,
        list_item_values__value__in=target_labels,
    ).distinct()

    uris = [item.uri for item in items]
    if not uris:
        logger.warning(
            "No ListItems found for labels %s in list %s",
            target_labels,
            VISIBILITY_LIST_ID,
        )
    return uris


def get_visibility_uri_to_label_map():
    """Build a map of URI → lowercase label for all visibility list items."""
    uri_map = {}
    for item in ListItem.objects.filter(
        list_id=VISIBILITY_LIST_ID,
    ).prefetch_related("list_item_values"):
        for val in item.list_item_values.all():
            if val.value:
                uri_map[item.uri] = val.value.lower()
                break
    return uri_map


def build_visibility_uri_query(node_id, visibility_uris):
    """Build a Q filter matching any of the visibility URIs for a given node."""
    q = Q()
    for uri in visibility_uris:
        q |= Q(data__contains={node_id: [{"uri": uri}]})
    return q


def get_visible_draft_resource_ids(visibility_node, visibility_uris):
    """Find Draft Heritage Item resource IDs with matching visibility URIs.

    Args:
        visibility_node: dict from get_visibility_nodes() for Heritage Item graph
        visibility_uris: list of URIs to match against
    """
    uri_q = build_visibility_uri_query(visibility_node["node_id"], visibility_uris)

    return list(
        TileModel.objects.filter(
            uri_q,
            nodegroup_id=visibility_node["nodegroup_id"],
            resourceinstance__graph_id=HERITAGE_ITEM_GRAPH_ID,
            resourceinstance__resource_instance_lifecycle_state__name="Draft",
        ).values_list("resourceinstance_id", flat=True)
    )


def get_draft_visibility_labels(visibility_node, visibility_uris):
    """Build a map of Draft resource ID → visibility label (e.g. 'public', 'staging').

    Queries Draft Heritage Items that match the given visibility URIs and
    returns a dict mapping each resource ID to its visibility label.
    """
    uri_to_label = get_visibility_uri_to_label_map()
    node_id = visibility_node["node_id"]

    tiles = TileModel.objects.filter(
        nodegroup_id=visibility_node["nodegroup_id"],
        resourceinstance__graph_id=HERITAGE_ITEM_GRAPH_ID,
        resourceinstance__resource_instance_lifecycle_state__name="Draft",
    )

    result = {}
    for tile in tiles:
        node_data = tile.data.get(node_id, [])
        if isinstance(node_data, list):
            for entry in node_data:
                uri = entry.get("uri") if isinstance(entry, dict) else None
                if uri and uri in uri_to_label:
                    result[tile.resourceinstance_id] = uri_to_label[uri]
                    break
    return result


def get_final_resource_ids(draft_resource_ids, draft_labels=None):
    """Map Draft resource IDs to their Active (Final) version resource IDs.

    Args:
        draft_resource_ids: list of Draft resource instance IDs
        draft_labels: optional dict of Draft resource ID → visibility label

    Returns:
        tuple: (list of Final resource IDs, list of missing resource_group_ids,
                dict of Final resource ID → visibility label if draft_labels provided)
    """
    # Draft resource IDs → (resource_instance_id, resource_group_id)
    draft_vrs = VersionedResource.objects.filter(
        resourceinstance_id__in=draft_resource_ids,
    )
    # Build draft_id → group_id mapping
    draft_to_group = {vr.resourceinstance_id: vr.resource_group_id for vr in draft_vrs}
    group_ids = list(set(draft_to_group.values()))

    # resource_group_ids → Active (Final) resource IDs
    finals = VersionedResource.objects.filter(
        resource_group_id__in=group_ids,
        resourceinstance__resource_instance_lifecycle_state__name="Active",
    )
    found_ids = [vr.pk for vr in finals]
    found_groups = set(finals.values_list("resource_group_id", flat=True))
    missing_groups = [g for g in group_ids if g not in found_groups]

    # Map Final IDs → visibility labels via group_id
    final_labels = {}
    if draft_labels:
        group_to_label = {}
        for draft_id, label in draft_labels.items():
            if draft_id in draft_to_group:
                group_to_label[draft_to_group[draft_id]] = label
        for vr in finals:
            if vr.resource_group_id in group_to_label:
                final_labels[str(vr.pk)] = group_to_label[vr.resource_group_id]

    return found_ids, missing_groups, final_labels


def get_visible_resource_ids(visibility_nodes, visibility_uris):
    """Find resource IDs across all graphs that have matching visibility.

    Queries every graph that has a visibility node (using the shared controlled
    list) and returns the set of resource IDs whose visibility matches.
    """
    visible_ids = set()
    for vnode in visibility_nodes:
        uri_q = build_visibility_uri_query(vnode["node_id"], visibility_uris)
        ids = TileModel.objects.filter(
            uri_q,
            nodegroup_id=vnode["nodegroup_id"],
            resourceinstance__graph_id=vnode["graph_id"],
        ).values_list("resourceinstance_id", flat=True)
        visible_ids.update(ids)
    return visible_ids


def get_user_filtered_nodegroups(resource_ids, user):
    """Nodegroups present in the given resources' tiles that ``user`` cannot
    read — i.e. those the export writer dropped due to nodegroup permissions.

    The writer (Writer.get_tiles) keeps only tiles whose nodegroup is in
    ``get_nodegroups_by_perm(user, "models.read_nodegroup")``. This reports the
    complement for the resources being exported, so the effect of an --as-user
    whitelist is visible at a glance.

    Returns a list of {"nodegroup_id", "alias", "graph_name"} dicts, sorted by
    graph then alias. Empty when nothing was filtered (or user is None).
    """
    if user is None:
        return []

    from arches.app.utils.permission_backend import get_nodegroups_by_perm

    permitted = {
        str(ng) for ng in get_nodegroups_by_perm(user, "models.read_nodegroup")
    }
    present = {
        str(ng)
        for ng in TileModel.objects.filter(resourceinstance_id__in=resource_ids)
        .values_list("nodegroup_id", flat=True)
        .distinct()
        if ng is not None
    }
    filtered_ids = present - permitted
    if not filtered_ids:
        return []

    # Label via the grouping node (nodeid == nodegroup_id).
    labels = {
        str(nodegroup_id): {"alias": alias, "graph_name": str(graph_name)}
        for nodegroup_id, alias, graph_name in Node.objects.filter(
            nodeid__in=filtered_ids,
            source_identifier__isnull=True,
        ).values_list("nodegroup_id", "alias", "graph__name")
    }
    return sorted(
        (
            {
                "nodegroup_id": ng_id,
                "alias": labels.get(ng_id, {}).get("alias"),
                "graph_name": labels.get(ng_id, {}).get("graph_name"),
            }
            for ng_id in filtered_ids
        ),
        key=lambda d: (d["graph_name"] or "", d["alias"] or "", d["nodegroup_id"]),
    )


def get_visibility_labels_for_resources(visibility_nodes, resource_ids):
    """Map resource IDs (in any graph with a visibility node) → visibility label.

    Used to scope related resources (e.g. Digital Objects) correctly: a target
    that is only Staging-visible must not be exported with a public scope. Works
    across every graph that has a visibility node, so it is not Heritage-Item or
    lifecycle specific (unlike get_draft_visibility_labels).
    """
    uri_to_label = get_visibility_uri_to_label_map()
    result = {}
    for vnode in visibility_nodes:
        node_id = vnode["node_id"]
        tiles = TileModel.objects.filter(
            nodegroup_id=vnode["nodegroup_id"],
            resourceinstance__graph_id=vnode["graph_id"],
            resourceinstance_id__in=resource_ids,
        )
        for tile in tiles:
            node_data = tile.data.get(node_id, [])
            if isinstance(node_data, list):
                for entry in node_data:
                    uri = entry.get("uri") if isinstance(entry, dict) else None
                    if uri and uri in uri_to_label:
                        result[str(tile.resourceinstance_id)] = uri_to_label[uri]
                        break
    return result


def get_outbound_relations(
    resource_ids,
    visibility_nodes,
    visibility_uris,
    permitted_nodegroups=None,
):
    """Get outbound relations filtered to targets with matching visibility.

    Only includes tile-backed relations where the target resource belongs to a
    graph that has a visibility node AND that target's visibility matches the
    same filter used for Heritage Items.

    Relations to graphs without a visibility node are excluded entirely.

    Args:
        resource_ids: list of source resource instance IDs
        visibility_nodes: list of visibility node dicts (from get_visibility_nodes)
        visibility_uris: list of URIs representing the chosen visibility filter
        permitted_nodegroups: optional set of nodegroup UUIDs to filter source tiles

    Returns:
        tuple: (relations list, diagnostics dict, set of visible target
                resource IDs — the related resources that passed the visibility
                filter, e.g. Public Digital Objects, suitable for exporting as
                full resources)
    """
    # Graphs that have a visibility node
    graphs_with_visibility = {n["graph_id"] for n in visibility_nodes}

    filters = {
        "from_resource_id__in": resource_ids,
        "tile__isnull": False,
        "to_resource_graph_id__in": graphs_with_visibility,
    }
    if permitted_nodegroups is not None:
        filters["tile__nodegroup_id__in"] = permitted_nodegroups

    candidate_relations = ResourceXResource.objects.filter(
        **filters
    ).select_related("tile", "node")

    # Find which target resources pass the visibility filter
    target_ids = set(rel.to_resource_id for rel in candidate_relations)
    visible_target_ids = get_visible_resource_ids(visibility_nodes, visibility_uris)
    allowed_target_ids = target_ids & visible_target_ids

    # Build diagnostics
    skipped_not_visible = target_ids - allowed_target_ids
    diagnostics = {
        "candidate_relations": candidate_relations.count(),
        "target_resources_total": len(target_ids),
        "target_resources_visible": len(allowed_target_ids),
        "target_resources_filtered_out": len(skipped_not_visible),
        "graphs_with_visibility_node": {
            n["graph_name"]: n["node_id"] for n in visibility_nodes
        },
    }

    relations = [
        {
            "resourcexid": str(rel.resourcexid),
            "from_resource": str(rel.from_resource_id),
            "from_resource_graph": str(rel.from_resource_graph_id),
            "to_resource": str(rel.to_resource_id),
            "to_resource_graph": str(rel.to_resource_graph_id),
            "relationshiptype": rel.relationshiptype,
            "inverserelationshiptype": rel.inverserelationshiptype,
            "nodeid": str(rel.node_id) if rel.node_id else None,
            "tileid": str(rel.tile_id) if rel.tile_id else None,
            "notes": rel.notes or "",
        }
        for rel in candidate_relations
        if rel.to_resource_id in allowed_target_ids
    ]

    return relations, diagnostics, allowed_target_ids


def get_controlled_list_ids_for_graphs(graph_ids):
    """Find all controlled list IDs referenced by reference-type nodes in the given graphs."""
    nodes = Node.objects.filter(
        graph_id__in=graph_ids,
        datatype="reference",
        config__controlledList__isnull=False,
    )
    list_ids = set()
    for node in nodes:
        cl_id = node.config.get("controlledList")
        if cl_id:
            list_ids.add(cl_id)
    return list_ids


def get_file_node_ids(graph_ids=None):
    """Node IDs of file-list datatype nodes (image / document uploads).

    These are the nodes that carry actual file attachments — Heritage Item
    ``images``, Digital Object ``file_content``, etc. Restrict to ``graph_ids``
    when given, otherwise return them across all graphs.
    """
    qs = Node.objects.filter(datatype="file-list", source_identifier__isnull=True)
    if graph_ids is not None:
        qs = qs.filter(graph_id__in=[str(g) for g in graph_ids])
    return {str(nid) for nid in qs.values_list("nodeid", flat=True)}


def extract_file_references(resources, file_node_ids=None):
    """Collect file references from exported resource tiles.

    Scans the already-exported business_data resources for file-list datatype
    nodes and returns the de-duplicated set of files they reference, so a
    downstream job can copy/publish exactly the media that ships with the
    package. Because it reads the exported tiles (not the DB directly), it
    honours the same permission- and visibility-filtering the export applied —
    only files on tiles that actually made it into the package are listed.

    Args:
        resources: list of resource dicts (export["business_data"]["resources"])
        file_node_ids: optional set of file-list nodeids; queried if omitted

    Returns:
        list of {"file_id", "name", "url", "resourceinstanceid", "nodeid"} dicts,
        de-duplicated by file_id (falling back to name), sorted by name.
    """
    if file_node_ids is None:
        file_node_ids = get_file_node_ids()

    seen = set()
    files = []
    for resource_data in resources:
        rid = resource_data.get("resourceinstance", {}).get(
            "resourceinstanceid", ""
        )
        for tile in resource_data.get("tiles", []):
            data = tile.get("data") or {}
            for node_id, value in data.items():
                if node_id not in file_node_ids or not isinstance(value, list):
                    continue
                for entry in value:
                    if not isinstance(entry, dict):
                        continue
                    file_id = entry.get("file_id")
                    name = entry.get("name")
                    key = file_id or name
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    files.append({
                        "file_id": file_id,
                        "name": name,
                        "url": entry.get("url"),
                        "resourceinstanceid": rid,
                        "nodeid": node_id,
                    })
    return sorted(files, key=lambda f: (f["name"] or "", f["file_id"] or ""))


def _resolve_i18n_name(name):
    """Extract a plain string from an i18n name (dict or string)."""
    if isinstance(name, dict):
        return name.get("en", next(iter(name.values()), "Unknown"))
    return str(name)


def export_graphs_to_dir(graph_ids, dest_dir, indent=2):
    """Export graph JSON files to dest_dir/graphs/resource_models/ and write graphs.json manifest.

    Returns list of exported graph names.
    """
    graphs_dir = os.path.join(dest_dir, "graphs", "resource_models")
    os.makedirs(graphs_dir, exist_ok=True)

    graphs_data = get_graphs_for_export(graphids=[str(gid) for gid in graph_ids])
    exported = []
    manifest = {}
    for graph in graphs_data.get("graph", []):
        graph_id = str(graph.get("graphid", ""))
        graph_name = _resolve_i18n_name(graph.get("name", "Unknown"))
        safe_name = graph_name.replace("/", "-")
        filepath = os.path.join(graphs_dir, f"{safe_name}.json")
        with open(filepath, "wb") as f:
            f.write(
                JSONSerializer()
                .serialize({"graph": [graph]}, indent=indent)
                .encode("utf-8")
            )
        exported.append(graph_name)
        manifest[graph_id] = {"name": graph_name}

    # Write graphs.json manifest at the prebuild root
    manifest_path = os.path.join(dest_dir, "graphs.json")
    with open(manifest_path, "w") as f:
        json.dump({"models": manifest}, f, indent=indent)

    return exported


def export_controlled_lists_to_dir(list_ids, dest_dir):
    """Export controlled lists as SKOS-RDF XML to dest_dir/reference_data/controlled_lists/.

    Returns list of exported list names.
    """
    cl_dir = os.path.join(dest_dir, "reference_data", "controlled_lists")
    os.makedirs(cl_dir, exist_ok=True)

    exported = []
    for list_id in list_ids:
        try:
            controlled_list = List.objects.get(pk=list_id)
        except List.DoesNotExist:
            logger.warning("Controlled list %s not found, skipping", list_id)
            continue

        list_items = ListItem.objects.filter(
            list=controlled_list,
        ).prefetch_related("list_item_values", "parent", "children")

        skos = SKOSWriter()
        skos_data = skos.write_controlled_lists(
            [controlled_list], list_items, format="pretty-xml"
        )

        slug = controlled_list.name.lower().replace(" ", "_").replace("/", "_")
        filepath = os.path.join(cl_dir, f"{slug}.xml")
        with open(filepath, "wb") as f:
            f.write(skos_data)
        exported.append(controlled_list.name)

    return exported


def export_resources(
    resource_ids,
    output_dir,
    visibility_nodes,
    visibility_uris,
    resource_labels=None,
    user=None,
    indent=2,
):
    """Export resources as a pkg-style directory with business_data, graphs, and reference_data.

    Creates:
        output_dir/
            business_data/
                Heritage_Item.json  (resources + relations)
            graphs/
                resource_models/
                    <GraphName>.json  (for each graph referenced by exported resources)
            reference_data/
                controlled_lists/
                    <list_name>.xml  (SKOS-RDF for each controlled list used)

    Args:
        resource_ids: list of resource instance IDs to export
        output_dir: directory path to write the package to
        visibility_nodes: list of visibility node dicts (from get_visibility_nodes)
        visibility_uris: list of URIs representing the chosen visibility filter
        user: optional User for permission-based nodegroup filtering
        indent: JSON indentation level (None for compact)

    Returns:
        tuple: (output_dir, diagnostics dict) or (None, None)
    """
    writer = ArchesFileWriter()
    results = writer.write_resources(
        resourceinstanceids=[str(rid) for rid in resource_ids],
        user=user,
        indent=indent,
    )

    if not results:
        logger.warning("Export produced no output")
        return None, None

    # Parse the JSON so we can add relations
    raw_json = results[0]["outputfile"].getvalue()
    export = json.loads(raw_json)

    # Assign scopes based on each resource's visibility label and collect
    # in-scope nodegroups from the tiles that were actually exported.
    exported_nodegroups = set()

    def _scope_resource(resource_data, label_map):
        rid = resource_data.get("resourceinstance", {}).get(
            "resourceinstanceid", ""
        )
        label = (label_map or {}).get(rid, "public")
        scopes = ["public"]
        if label == "staging":
            scopes.append("staging")
        resource_data["__scopes"] = scopes
        for tile in resource_data.get("tiles", []):
            if ng := tile.get("nodegroup_id"):
                exported_nodegroups.add(ng)

    resources = export.get("business_data", {}).get("resources", [])
    for resource_data in resources:
        _scope_resource(resource_data, resource_labels)

    # Get outbound relations filtered by target visibility, plus the set of
    # visible related resources (e.g. Public Digital Objects) those relations
    # point at.
    relations, diagnostics, target_ids = get_outbound_relations(
        resource_ids,
        visibility_nodes=visibility_nodes,
        visibility_uris=visibility_uris,
        permitted_nodegroups=exported_nodegroups or None,
    )
    export["business_data"]["relations"] = relations

    # Second pass: export the visible related resources as full resources so the
    # package carries the Digital Objects (etc.) the relations reference, not
    # just dangling links. Still permission-filtered via the same user; scoped
    # by each target's own visibility label so a Staging-only target is not
    # leaked into the public scope. One level deep — targets-of-targets are not
    # followed.
    target_ids = {str(t) for t in target_ids} - {str(r) for r in resource_ids}
    diagnostics["included_target_resources"] = 0
    if target_ids:
        target_results = ArchesFileWriter().write_resources(
            resourceinstanceids=sorted(target_ids),
            user=user,
            indent=indent,
        )
        target_resources = (
            json.loads(target_results[0]["outputfile"].getvalue())
            .get("business_data", {})
            .get("resources", [])
            if target_results
            else []
        )
        target_labels = get_visibility_labels_for_resources(
            visibility_nodes, target_ids
        )
        for resource_data in target_resources:
            _scope_resource(resource_data, target_labels)
        resources.extend(target_resources)
        diagnostics["included_target_resources"] = len(target_resources)

    # Include all resource model graphs with visibility nodes (these are
    # the ones the public export ecosystem needs to understand), plus any
    # from the exported data itself. Exclude branches.
    from arches.app.models.models import GraphModel
    resource_model_ids = set(
        GraphModel.objects.filter(
            graphid__in=[n["graph_id"] for n in visibility_nodes],
            isresource=True,
        ).values_list("graphid", flat=True)
    )
    graph_ids = {str(gid) for gid in resource_model_ids}
    for resource_data in export.get("business_data", {}).get("resources", []):
        ri = resource_data.get("resourceinstance", {})
        if gid := ri.get("graph_id"):
            graph_ids.add(gid)
    for rel in relations:
        if gid := rel.get("to_resource_graph"):
            graph_ids.add(gid)

    # Always include Registry graph if it exists
    registry = GraphModel.objects.filter(
        name__contains=REGISTRY_GRAPH_NAME, isresource=True,
    ).first()
    if registry:
        graph_ids.add(str(registry.graphid))

    # Collect the files (images + Digital Object file_content, etc.) referenced
    # by the exported tiles, so a downstream job can publish exactly the media
    # that ships with this package. Reads the exported tiles, so it inherits the
    # same permission/visibility filtering already applied.
    file_refs = extract_file_references(resources)
    diagnostics["referenced_files"] = file_refs

    # 1. Write business_data
    bd_dir = os.path.join(output_dir, "business_data")
    os.makedirs(bd_dir, exist_ok=True)
    bd_path = os.path.join(bd_dir, "Heritage_Item.json")
    with open(bd_path, "w") as f:
        json.dump(export, f, indent=indent)

    # 1b. Write the referenced-file manifest at the package root.
    files_path = os.path.join(output_dir, "files.json")
    with open(files_path, "w") as f:
        json.dump({"files": file_refs}, f, indent=indent)

    # 2. Export graphs
    exported_graphs = export_graphs_to_dir(graph_ids, output_dir, indent=indent)
    diagnostics["exported_graphs"] = exported_graphs

    # 3. Export controlled lists referenced by those graphs
    list_ids = get_controlled_list_ids_for_graphs(graph_ids)
    exported_lists = export_controlled_lists_to_dir(list_ids, output_dir)
    diagnostics["exported_controlled_lists"] = exported_lists

    return output_dir, diagnostics


def package_export(output_dir, archive_name="prebuild.tgz"):
    """Tar+gzip an exported package directory into a single artefact.

    The directory contents are placed at the archive root (arcname=".") so
    that unpacking yields business_data/, graphs/, reference_data/ directly.

    Returns the path to the created archive (in a temp directory).
    """
    import tarfile
    import tempfile

    # basename only: archive_name may be a slash-prefixed blob name and the
    # local temp file must not point at a non-existent subdirectory.
    archive_path = os.path.join(
        tempfile.gettempdir(), os.path.basename(archive_name)
    )
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(output_dir, arcname=".")
    logger.info("Packaged export %s -> %s", output_dir, archive_path)
    return archive_path


def upload_artifact(archive_path, container=None, blob_name="prebuild.tgz"):
    """Upload an artefact to an Azure blob container.

    Uses the same storage account as the configured AZURE_ACCOUNT_NAME /
    AZURE_ACCOUNT_KEY but targets a separate container (default:
    STARCHES_VALIDATION_CONTAINER). Returns the blob URL on success.

    Raises RuntimeError if Azure credentials are not configured.
    """
    from django.conf import settings
    from azure.storage.blob import BlobServiceClient

    account_name = getattr(settings, "AZURE_ACCOUNT_NAME", None) or os.environ.get(
        "AZURE_ACCOUNT_NAME"
    )
    account_key = getattr(settings, "AZURE_ACCOUNT_KEY", None) or os.environ.get(
        "AZURE_ACCOUNT_KEY"
    )
    if not (account_name and account_key):
        raise RuntimeError(
            "Azure credentials not configured "
            "(AZURE_ACCOUNT_NAME / AZURE_ACCOUNT_KEY)."
        )

    container = (
        container
        or getattr(settings, "STARCHES_VALIDATION_CONTAINER", None)
        or os.environ.get("STARCHES_VALIDATION_CONTAINER")
        or "starches-validation"
    )

    service = BlobServiceClient(
        f"https://{account_name}.blob.core.windows.net",
        credential=account_key,
    )
    blob = service.get_blob_client(container=container, blob=blob_name)
    with open(archive_path, "rb") as fh:
        blob.upload_blob(fh, overwrite=True)
    logger.info("Uploaded %s to container '%s' as '%s'",
                archive_path, container, blob_name)
    return blob.url


def trigger_validation_build(event_type="prebuild", payload=None):
    """Trigger a GitHub Action via the repository_dispatch event.

    POSTs to /repos/{owner}/{repo}/dispatches using GITHUB_DISPATCH_REPO and
    GITHUB_DISPATCH_TOKEN. Returns the HTTP status code on success.

    Raises RuntimeError if the repo or token are not configured.
    """
    from django.conf import settings
    import requests

    repo = getattr(settings, "GITHUB_DISPATCH_REPO", None) or os.environ.get(
        "GITHUB_DISPATCH_REPO"
    )
    token = getattr(settings, "GITHUB_DISPATCH_TOKEN", None) or os.environ.get(
        "GITHUB_DISPATCH_TOKEN"
    )
    if not (repo and token):
        raise RuntimeError(
            "GitHub dispatch not configured "
            "(GITHUB_DISPATCH_REPO / GITHUB_DISPATCH_TOKEN)."
        )

    response = requests.post(
        f"https://api.github.com/repos/{repo}/dispatches",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"event_type": event_type, "client_payload": payload or {}},
        timeout=30,
    )
    response.raise_for_status()
    logger.info("Triggered repository_dispatch '%s' on %s (HTTP %s)",
                event_type, repo, response.status_code)
    return response.status_code


def resolve_export_user(username=None, expected_group="Public Export"):
    """Resolve the user whose nodegroup read-permissions the export applies.

    Mirrors the management command's --as-user handling so the Celery task and
    the command behave identically:
      * falsy username -> the 'anonymous' user (public-visitor view); if there
        is no 'anonymous' user, returns None (no nodegroup filtering).
      * a superuser raises ValueError (superusers bypass nodegroup permissions,
        which would silently export everything).

    Returns (user_or_None, messages) where messages is a list of
    (level, text) tuples for the caller to log.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    messages = []

    if not username:
        try:
            user = User.objects.get(username="anonymous")
        except User.DoesNotExist:
            messages.append((
                "warning",
                "No export user and no 'anonymous' user found: NO nodegroup "
                "filtering applied (every nodegroup will be exported).",
            ))
            return None, messages
        messages.append((
            "info",
            "Applying the 'anonymous' user's nodegroup permissions "
            "(public-visitor view).",
        ))
        return user, messages

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        raise ValueError(f"export user '{username}' does not exist")
    if user.is_superuser:
        raise ValueError(
            f"export user '{username}' is a superuser; superusers bypass "
            f"nodegroup permissions so the whitelist would not apply."
        )

    group_names = set(user.groups.values_list("name", flat=True))
    if expected_group not in group_names:
        messages.append((
            "warning",
            f"'{username}' is not in the '{expected_group}' group, so the "
            f"public-export whitelist will not be applied.",
        ))
    extra = group_names - {expected_group}
    if extra:
        messages.append((
            "warning",
            f"'{username}' also belongs to {sorted(extra)}; read_nodegroup "
            f"grants from those groups can re-expose denied nodegroups.",
        ))
    return user, messages


def run_export_pipeline(
    target_labels,
    output_dir="public_export",
    use_drafts=False,
    indent=2,
    user=None,
):
    """Run the full public-export selection+write pipeline (no console IO).

    Discovers visibility nodes, selects the matching Heritage Items (Final
    versions, or the Drafts themselves when ``use_drafts``), and writes the
    pkg-style export to ``output_dir`` via export_resources (honouring ``user``
    nodegroup permissions and pulling in visible related Digital Objects).

    Returns a dict:
        {
          "result": <output_dir> or None,
          "diagnostics": {...} or None,
          "export_ids": [str, ...],
          "missing_final_groups": [str, ...],
          "messages": [(level, text), ...],
        }
    """
    out = {
        "result": None,
        "diagnostics": None,
        "export_ids": [],
        "missing_final_groups": [],
        "messages": [],
    }
    msg = out["messages"]

    visibility_nodes = get_visibility_nodes()
    if not visibility_nodes:
        msg.append(("error", "No visibility nodes found in any graph."))
        return out

    hi_visibility = get_visibility_node_for_graph(
        visibility_nodes, HERITAGE_ITEM_GRAPH_ID
    )
    if not hi_visibility:
        msg.append(("error", "Heritage Item graph has no visibility node."))
        return out

    uris = get_visibility_uris(target_labels)
    if not uris:
        msg.append((
            "error", f"No controlled list items found for labels: {target_labels}"
        ))
        return out

    draft_ids = get_visible_draft_resource_ids(hi_visibility, uris)
    if not draft_ids:
        msg.append(("warning", "No matching Heritage Items found."))
        return out
    draft_labels = get_draft_visibility_labels(hi_visibility, uris)

    if use_drafts:
        export_ids = list(draft_ids)
        export_labels = {str(k): v for k, v in draft_labels.items()}
        msg.append((
            "warning",
            f"Exporting {len(export_ids)} Draft versions directly (use_drafts).",
        ))
    else:
        export_ids, missing_groups, export_labels = get_final_resource_ids(
            draft_ids, draft_labels=draft_labels,
        )
        out["missing_final_groups"] = [str(g) for g in missing_groups]
        for g in missing_groups:
            msg.append(("warning", f"resource group {g} has no Final version"))

    if not export_ids:
        msg.append(("warning", "No versions to export."))
        return out
    out["export_ids"] = [str(r) for r in export_ids]

    result, diagnostics = export_resources(
        export_ids,
        output_dir=output_dir,
        visibility_nodes=visibility_nodes,
        visibility_uris=uris,
        resource_labels=export_labels,
        user=user,
        indent=indent,
    )
    if not result:
        msg.append(("error", "Export produced no output."))
        return out

    out["result"] = result
    out["diagnostics"] = diagnostics
    return out
