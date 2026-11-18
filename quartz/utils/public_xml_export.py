"""XML export of the Queensland Heritage Register.

Produces the same structure as the register's published ``heritage-register``
XML file (``heritage_places`` > ``place`` with ``place_ref``, ``name``,
``description``, ``history``, ``street_address``, ``suburb``, ``lga``,
``register_entry_date``, ``alternate_name`` and ``criterion``), plus
``place_type`` and ``thematic_framework`` elements for researchers.

Only Heritage Items that have Heritage Item Visibility set to Public and a
designation and protection status of "Entered" are exported (the records on the
public website). ``export_register_xml`` applies both rules itself, so no
caller can bypass them.

Values are read straight from the database. This deliberately bypasses the
Arches search/CSV export, which reads from Elasticsearch, skips nodes flagged
``exportable=False`` (for example LGA) and flattens repeating nodegroups into a
single cell.
"""

import os
import re
import xml.etree.ElementTree as ET
from uuid import UUID

from arches.app.models.models import Node, ResourceInstance, TileModel
from arches_controlled_lists.models import ListItem
from arches_resource_version_manager.models import VersionedResource

from quartz.utils.public_export import (
    HERITAGE_ITEM_GRAPH_ID,
    get_final_resource_ids,
    get_visibility_labels_for_resources,
    get_visibility_node_for_graph,
    get_visibility_nodes,
    get_visibility_uris,
    get_visible_draft_resource_ids,
    get_visible_resource_ids,
)

NAMESPACE = "https://data.qld.gov.au/dataset/the-queensland-heritage-register"

# Write the register namespace as the default (unprefixed) one, as the published
# file does. ElementTree's ``default_namespace`` argument cannot be used because
# it rejects unqualified attribute names such as ``type``.
ET.register_namespace("", NAMESPACE)

# Node aliases the export reads. Aliases are stable across environments, node
# ids are not guaranteed to be.
FIELD_ALIASES = (
    "primary_reference_number",
    "monument_name",
    "monument_name_use_type",
    "monument_name_currency",
    "description",
    "description_type",
    "street_value",
    "building_number_value",
    "full_address",
    "suburbs",
    "locality_value",
    "lga",
    "monument_type",
    "functional_type",
    "designation_or_protection_type",
    "designation_start_date",
    "local_heritage_list_criteria_type",
    # The statement of significance for a criterion: the "Description" under
    # Designation Name, a child nodegroup of Designation and Protection
    # Assignment, so its tile is a child of the tile holding the criterion.
    "designation_description",
)

# Nodes that share the Addresses nodegroup.
ADDRESS_ALIASES = (
    "street_value",
    "building_number_value",
    "full_address",
    "suburbs",
    "locality_value",
    "lga",
)

ENTERED_LABEL = "Entered"
PUBLIC_LABEL = "Public"

# The register file lists State Heritage places, which is what Entered means.
PLACE_TYPE_ATTRIBUTE = "State Heritage"

# Name Use Types in order of preference for the register name. Every other name
# becomes an alternate_name.
NAME_USE_PREFERENCE = ("Registered", "Primary", "Latest")

# Description types that map to the register's description and history.
DESCRIPTION_TYPE = "Description"
HISTORY_TYPE = "History"

# Wording of each criterion, as published in the register file.
CRITERION_DETAILS = {
    "Criterion A": "The place is important in demonstrating the evolution or pattern of Queensland's history",
    "Criterion B": "The place demonstrates rare, uncommon or endangered aspects of Queensland's cultural heritage",
    "Criterion C": "The place has potential to yield information that will contribute to an understanding of Queensland's history",
    "Criterion D": "The place is important in demonstrating the principal characteristics of a particular class of cultural places",
    "Criterion E": "The place is important because of its aesthetic significance",
    "Criterion F": "The place is important in demonstrating a high degree of creative or technical achievement at a particular period",
    "Criterion G": "The place has a strong or special association with a particular community or cultural group for social, cultural or spiritual reasons",
    "Criterion H": "The place has a special association with the life or work of a particular person, group or organisation of importance in Queensland's history",
}

# Characters that are illegal in XML 1.0 and are not escaped by ElementTree.
_INVALID_XML_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def clean_text(value):
    """Return ``value`` as stripped text with XML-illegal characters removed."""
    return _INVALID_XML_CHARS.sub("", str(value)).strip()


def pick_text(value, language="en"):
    """Plain text from a string-node value, a number, or None.

    String nodes hold ``{"en": {"value": "...", "direction": "ltr"}}``. The
    requested language is preferred, otherwise the first one present.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        entry = value.get(language)
        if entry is None:
            entry = next(iter(value.values()), None)
        if isinstance(entry, dict):
            entry = entry.get("value")
        value = entry
        if value is None:
            return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return clean_text(value) or None


def reference_labels(value, language="en"):
    """Preferred labels from a reference-node value, one per reference."""
    if not isinstance(value, list):
        return []
    result = []
    for ref in value:
        if not isinstance(ref, dict):
            continue
        pref = [
            label
            for label in ref.get("labels") or []
            if label.get("valuetype_id") == "prefLabel"
        ]
        chosen = next(
            (label for label in pref if label.get("language_id") == language),
            pref[0] if pref else None,
        )
        if chosen and chosen.get("value"):
            text = clean_text(chosen["value"])
            if text:
                result.append(text)
    return result


def register_date(value):
    """``YYYY-MM-DD 00:00:00`` from a date-node value, or None.

    This is the format the register file uses for ``register_entry_date``.
    """
    match = _ISO_DATE.search(str(value or ""))
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)} 00:00:00"


def _dedupe(items):
    return list(dict.fromkeys(items))


def load_field_nodes():
    """Map alias to Node for every field the export reads."""
    nodes = {
        node.alias: node
        for node in Node.objects.filter(
            graph_id=HERITAGE_ITEM_GRAPH_ID,
            alias__in=FIELD_ALIASES,
            source_identifier__isnull=True,
        )
    }
    missing = sorted(set(FIELD_ALIASES) - set(nodes))
    if missing:
        raise RuntimeError(
            f"Heritage Item graph is missing expected nodes: {', '.join(missing)}"
        )
    return nodes


def choose_names(names):
    """Split ``[(text, use type, currency)]`` into (register name, alternates).

    The register name is the one with the most preferred Name Use Type, then a
    Current one, then the first alphabetically. Every other distinct name is an
    alternate. Alternates are sorted so the output is stable.
    """

    def rank(item):
        text, use, currency = item
        use_rank = (
            NAME_USE_PREFERENCE.index(use)
            if use in NAME_USE_PREFERENCE
            else len(NAME_USE_PREFERENCE)
        )
        return (use_rank, 0 if currency == "Current" else 1, text)

    if not names:
        return None, []
    ordered = sorted(names, key=rank)
    primary = ordered[0][0]
    return primary, sorted({text for text, _, _ in ordered[1:] if text != primary})


def collect_place(tiles, nodes, language="en"):
    """Reduce one resource's tiles to a plain dict of exportable values.

    ``nodes`` is the alias to Node map from ``load_field_nodes`` (possibly with
    unreadable aliases removed). Fields whose node is absent stay empty.
    """
    nid = {alias: str(node.nodeid) for alias, node in nodes.items()}
    ng = {alias: str(node.nodegroup_id) for alias, node in nodes.items()}
    address_groups = {ng[a] for a in ADDRESS_ALIASES if a in ng}

    def get(alias, data):
        return data.get(nid[alias]) if alias in nid else None

    def labels(alias, data):
        return reference_labels(get(alias, data), language)

    def text(alias, data):
        return pick_text(get(alias, data), language)

    register_id = None
    names, street_addresses, suburbs, lgas = [], [], [], []
    place_types, themes = [], []
    description_parts = {DESCRIPTION_TYPE: [], HISTORY_TYPE: []}
    designations, statements = [], {}

    for tile in tiles:
        ngid = str(tile.nodegroup_id)
        data = tile.data or {}

        if ng.get("primary_reference_number") == ngid:
            reg = text("primary_reference_number", data)
            if reg and register_id is None:
                register_id = reg

        if ng.get("monument_name") == ngid:
            name = text("monument_name", data)
            if name:
                use = labels("monument_name_use_type", data)
                currency = labels("monument_name_currency", data)
                names.append(
                    (name, use[0] if use else None, currency[0] if currency else None)
                )

        if ng.get("description") == ngid:
            body = text("description", data)
            kind = labels("description_type", data)
            if body and kind and kind[0] in description_parts:
                description_parts[kind[0]].append(body)

        if ngid in address_groups:
            parts = [
                p
                for p in (
                    text("building_number_value", data),
                    text("street_value", data),
                )
                if p
            ]
            address = " ".join(parts) if parts else text("full_address", data)
            if address:
                street_addresses.append(address)
            suburb = labels("suburbs", data) or [
                s for s in (text("locality_value", data),) if s
            ]
            suburbs += suburb
            lgas += labels("lga", data)

        if ng.get("monument_type") == ngid:
            place_types += labels("monument_type", data)

        if ng.get("functional_type") == ngid:
            themes += labels("functional_type", data)

        if ng.get("designation_or_protection_type") == ngid:
            designations.append(
                {
                    "tileid": str(tile.tileid),
                    "status": labels("designation_or_protection_type", data),
                    "start": register_date(get("designation_start_date", data)),
                    "criteria": labels("local_heritage_list_criteria_type", data),
                }
            )

        if ng.get("designation_description") == ngid:
            statement = text("designation_description", data)
            if statement and tile.parenttile_id is not None:
                statements.setdefault(str(tile.parenttile_id), []).append(statement)

    name, alternates = choose_names(names)

    entry_dates = [
        d["start"] for d in designations if ENTERED_LABEL in d["status"] and d["start"]
    ]
    criteria = []
    for designation in designations:
        for label in designation["criteria"]:
            criteria.append((label, "".join(statements.get(designation["tileid"], []))))

    return {
        "register_id": register_id,
        "name": name,
        "alternate_names": alternates,
        "description": "".join(description_parts[DESCRIPTION_TYPE]) or None,
        "history": "".join(description_parts[HISTORY_TYPE]) or None,
        "street_address": street_addresses[0] if street_addresses else None,
        "suburbs": _dedupe(suburbs),
        "lgas": _dedupe(lgas),
        "register_entry_date": min(entry_dates) if entry_dates else None,
        "place_types": _dedupe(place_types),
        "themes": _dedupe(themes),
        "criteria": sorted(criteria),
    }


def criterion_type(label):
    """``Criterion A`` for the single letter labels A to H, else the label."""
    return f"Criterion {label}" if len(label) == 1 else label


def _q(tag):
    return f"{{{NAMESPACE}}}{tag}"


def _add(parent, tag, text=None, **attrs):
    element = ET.SubElement(parent, _q(tag), attrs)
    if text is not None:
        element.text = text
    return element


def place_to_element(place):
    """Build the ``<place>`` element, in the register file's element order."""
    el = ET.Element(_q("place"), {"type": PLACE_TYPE_ATTRIBUTE})
    for tag, key in (
        ("place_ref", "register_id"),
        ("name", "name"),
        ("description", "description"),
        ("history", "history"),
        ("street_address", "street_address"),
    ):
        if place[key]:
            _add(el, tag, place[key])
    for suburb in place["suburbs"]:
        _add(el, "suburb", suburb)
    for lga in place["lgas"]:
        _add(el, "lga", lga)
    if place["register_entry_date"]:
        _add(el, "register_entry_date", place["register_entry_date"])
    for alternate in place["alternate_names"]:
        _add(el, "alternate_name", alternate)
    # Not in the published register file, but requested by researchers.
    for place_type in place["place_types"]:
        _add(el, "place_type", place_type)
    for theme in place["themes"]:
        _add(el, "thematic_framework", theme)
    for label, statement in place["criteria"]:
        kind = criterion_type(label)
        attrs = {"type": kind}
        if kind in CRITERION_DETAILS:
            attrs["detail"] = CRITERION_DETAILS[kind]
        _add(el, "criterion", statement, **attrs)
    return el


def _sort_key(item):
    _, register_id, resource_id = item
    try:
        number = int(register_id)
    except (TypeError, ValueError):
        number = None
    return (0 if number is not None else 1, number or 0, resource_id)


def build_xml_tree(places):
    """Assemble the document from ``(element, register_id, resource_id)``."""
    root = ET.Element(_q("heritage_places"))
    for element, _, _ in sorted(places, key=_sort_key):
        root.append(element)
    return ET.ElementTree(root)


def write_xml_tree(tree, output):
    """Write ``tree`` to a path or binary file object, indented."""
    ET.indent(tree, space="  ")
    if not hasattr(output, "write"):
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    tree.write(output, encoding="utf-8", xml_declaration=True)


def _list_item_uri(node, label):
    item = (
        ListItem.objects.filter(
            list_id=node.config["controlledList"], list_item_values__value=label
        )
        .distinct()
        .first()
    )
    if item is None:
        raise RuntimeError(f'No "{label}" item in the list for {node.alias}')
    return item.uri


def entered_resource_ids(resource_ids, nodes):
    """Subset of ``resource_ids`` with a designation tile whose status is Entered.

    Same rule as filtering Heritage Items on Designation or Protection Type
    "Entered" in the advanced search: any matching tile qualifies. "Not
    Entered", "Removed" and the other statuses do not.
    """
    node = nodes["designation_or_protection_type"]
    uri = _list_item_uri(node, ENTERED_LABEL)
    return set(
        TileModel.objects.filter(
            resourceinstance_id__in=list(resource_ids),
            nodegroup_id=node.nodegroup_id,
            data__contains={str(node.nodeid): [{"uri": uri}]},
        ).values_list("resourceinstance_id", flat=True)
    )


def public_resource_ids(resource_ids):
    """Subset of ``resource_ids`` whose own Heritage Item Visibility is Public.

    Each version (Draft or Final) is judged on its own visibility tile.
    """
    heritage_graph = str(HERITAGE_ITEM_GRAPH_ID)
    visibility_nodes = [
        n for n in get_visibility_nodes() if n["graph_id"] == heritage_graph
    ]
    labels = get_visibility_labels_for_resources(visibility_nodes, resource_ids)
    return {rid for rid in resource_ids if labels.get(str(rid)) == PUBLIC_LABEL.lower()}


def select_public_resource_ids():
    """Heritage Items to export: Final versions of those with a Public Draft.

    The Draft's Heritage Item Visibility decides which places are candidates
    and the Final (Active) version is what is exported, as in the public
    export. Heritage Items with no version history are included when they are
    Active and Public. ``export_register_xml`` then re-checks Public and Entered
    on what it is given.

    Returns:
        tuple: (resource ids, resource group ids with no Final version)
    """
    uris = get_visibility_uris([PUBLIC_LABEL])
    if not uris:
        return [], []

    heritage_graph = str(HERITAGE_ITEM_GRAPH_ID)
    visibility_nodes = [
        n for n in get_visibility_nodes() if n["graph_id"] == heritage_graph
    ]
    heritage_visibility = get_visibility_node_for_graph(
        visibility_nodes, HERITAGE_ITEM_GRAPH_ID
    )
    if heritage_visibility is None:
        return [], []

    draft_ids = get_visible_draft_resource_ids(heritage_visibility, uris)
    final_ids, missing, _ = get_final_resource_ids(draft_ids)

    # Active and Public Heritage Items that are not part of any version group.
    active_public = get_visible_resource_ids(visibility_nodes, uris)
    versioned = set(
        VersionedResource.objects.filter(
            resourceinstance_id__in=active_public
        ).values_list("pk", flat=True)
    )
    unversioned = [pk for pk in active_public if pk not in versioned]

    return list(dict.fromkeys(list(final_ids) + unversioned)), missing


def export_register_xml(
    resource_ids, output_path, permitted_nodegroups=None, language="en"
):
    """Write the register XML for ``resource_ids`` to ``output_path``.

    Only Heritage Items with Heritage Item Visibility Public and designation
    status Entered are written. Anything else in ``resource_ids`` is skipped
    and counted in the result.

    Args:
        resource_ids: candidate resource ids (UUIDs or their string form).
        output_path: file path to write, or a writable binary file object.
        permitted_nodegroups: optional set of nodegroup id strings the export
            user may read. Fields in other nodegroups are omitted. None means
            no filtering at all. This never affects which places are selected.
        language: preferred language for text and labels.

    Returns:
        dict with ``count`` (places written), ``skipped_other_graph``,
        ``skipped_not_public``, ``skipped_not_entered`` and ``dropped_fields``
        (aliases omitted because of ``permitted_nodegroups``).
    """
    resource_ids = list(dict.fromkeys(UUID(str(rid)) for rid in resource_ids))
    nodes = load_field_nodes()

    # Scope, decided from the database before any permission filtering so a
    # user's permissions never change which places are in the register.
    heritage_graph = str(HERITAGE_ITEM_GRAPH_ID)
    heritage_ids = [
        pk
        for pk, graph_id in ResourceInstance.objects.filter(
            pk__in=resource_ids
        ).values_list("pk", "graph_id")
        if str(graph_id) == heritage_graph
    ]
    public = public_resource_ids(heritage_ids)
    entered = entered_resource_ids(
        [rid for rid in heritage_ids if rid in public], nodes
    )
    kept = [rid for rid in resource_ids if rid in public and rid in entered]
    skipped_other_graph = len(resource_ids) - len(heritage_ids)
    skipped_not_public = len(heritage_ids) - len(public)
    skipped_not_entered = len(public) - len(kept)

    dropped_fields = []
    if permitted_nodegroups is not None:
        permitted = {str(ng) for ng in permitted_nodegroups}
        dropped_fields = sorted(
            a for a, n in nodes.items() if str(n.nodegroup_id) not in permitted
        )
        nodes = {a: n for a, n in nodes.items() if a not in dropped_fields}

    tiles_by_resource = {}
    nodegroup_ids = {node.nodegroup_id for node in nodes.values()}
    for tile in TileModel.objects.filter(
        resourceinstance_id__in=kept, nodegroup_id__in=nodegroup_ids
    ).order_by("sortorder", "tileid"):
        tiles_by_resource.setdefault(tile.resourceinstance_id, []).append(tile)

    places = []
    for rid in kept:
        place = collect_place(tiles_by_resource.get(rid, []), nodes, language)
        places.append((place_to_element(place), place["register_id"], str(rid)))

    write_xml_tree(build_xml_tree(places), output_path)
    return {
        "count": len(places),
        "skipped_other_graph": skipped_other_graph,
        "skipped_not_public": skipped_not_public,
        "skipped_not_entered": skipped_not_entered,
        "dropped_fields": dropped_fields,
    }
