from django.core.management.base import BaseCommand
from django.db import connection

from arches.app.models.models import GraphModel, Node, TileModel
from arches.app.models.system_settings import settings as arches_settings
from arches_search.models.models import NodeFilterConfig

SLUG = "filtering"


def _controlled_list_size(list_id):
    if not list_id:
        return 0
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM arches_controlled_lists_listitem WHERE list_id = %s",
            [list_id],
        )
        return cursor.fetchone()[0]


def _node_is_populated(graph, node):
    """True if any tile in this graph has non-null data for the node."""
    return (
        TileModel.objects.filter(
            resourceinstance__graph_id=graph.pk,
            nodegroup_id=node.nodegroup_id,
            data__has_key=str(node.nodeid),
        )
        .exclude(data__contains={str(node.nodeid): None})
        .exists()
    )


def build_filter_config(graph, max_nodes, max_options, populated_only):
    """Seed reference/controlled-list nodes as attribute filters for a graph.

    The SimpleSearch attribute-filter UI only renders options for reference
    datatype nodes with a `controlledList` config (it builds checkboxes from
    the list and emits a REFERENCES_ANY query). Other datatypes would render
    empty, dead filter sections, so we deliberately skip them.

    The UI renders every option of every section into the DOM up front (the
    accordion content is not lazy), so the panel slows down with the *total*
    number of checkbox options across sections, not the network. Levers:
      - `max_options`: skip nodes whose controlled list is large (a long
        checkbox list is slow and poor UX — it wants a typeahead the UI lacks),
      - `max_nodes`: hard cap on node count (0 = no cap),
      - `populated_only`: drop reference nodes that no resource actually fills
        in (e.g. Heritage Item defines 62 reference nodes but only ~25 hold
        data), which trims dead filters and the rendered DOM.

    Returns (config, dropped_count).
    """
    nodes = (
        Node.objects.filter(graph=graph, datatype="reference")
        .exclude(cardxnodexwidget__visible=False)
        .order_by("sortorder", "name")
    )

    config_nodes = []
    dropped = 0
    seen_labels = set()
    for node in nodes:
        list_id = (node.config or {}).get("controlledList")
        if not list_id:
            continue
        label = str(node.name)
        # The data model reuses the same node name across multiple nodegroups
        # (e.g. "Association Type" exists as association_type / _n1 / _n2), which
        # would render as several identical-looking filters. Keep one per label.
        if label in seen_labels:
            dropped += 1
            continue
        if max_options and _controlled_list_size(list_id) > max_options:
            dropped += 1
            continue
        if populated_only and not _node_is_populated(graph, node):
            dropped += 1
            continue
        seen_labels.add(label)
        config_nodes.append(
            {
                "node_alias": node.alias,
                "label": label,
                "sortorder": len(config_nodes),
            }
        )

    if max_nodes and len(config_nodes) > max_nodes:
        dropped += len(config_nodes) - max_nodes
        config_nodes = config_nodes[:max_nodes]

    return {"nodes": config_nodes}, dropped


class Command(BaseCommand):
    help = (
        "Create NodeFilterConfig (slug='filtering') for resource graphs, "
        "seeded with reference/controlled-list nodes. Run after load_package. "
        "Not a migration: graphs/resources don't exist at migrate time."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace existing configs instead of skipping them.",
        )
        parser.add_argument(
            "--graph",
            default=None,
            help="Limit to one graph (matched by slug, else name contains). "
            "Default: all resource graphs.",
        )
        parser.add_argument(
            "--populated-only",
            action="store_true",
            help="Only include reference nodes that resources actually fill in "
            "(skip nodes with no data anywhere in the graph).",
        )
        parser.add_argument(
            "--max-options",
            type=int,
            default=25,
            help="Skip reference nodes whose controlled list has more than "
            "this many items (long checkbox lists are slow). 0 = no limit. "
            "Default 25.",
        )
        parser.add_argument(
            "--max-nodes",
            type=int,
            default=0,
            help="Hard cap on filter nodes per graph. 0 = no cap (default).",
        )

    def handle(self, *args, **options):
        overwrite = options["overwrite"]
        populated_only = options["populated_only"]
        max_options = options["max_options"]
        max_nodes = options["max_nodes"]
        graph_filter = options["graph"]

        graphs = GraphModel.objects.filter(
            isresource=True,
            slug__isnull=False,
        ).exclude(pk=arches_settings.SYSTEM_SETTINGS_RESOURCE_MODEL_ID)

        if graph_filter:
            matched = graphs.filter(slug=graph_filter)
            if not matched.exists():
                matched = graphs.filter(name__icontains=graph_filter)
            graphs = matched

        if not graphs.exists():
            self.stderr.write(
                "No matching resource graphs found. Have you run load_package?"
            )
            return

        for graph in graphs:
            config, dropped = build_filter_config(
                graph, max_nodes, max_options, populated_only
            )
            count = len(config["nodes"])
            dropped_note = f", {dropped} dropped" if dropped else ""

            if overwrite:
                _, created = NodeFilterConfig.objects.update_or_create(
                    graph=graph,
                    slug=SLUG,
                    defaults={"config": config},
                )
                verb = "Created" if created else "Updated"
            else:
                _, created = NodeFilterConfig.objects.get_or_create(
                    graph=graph,
                    slug=SLUG,
                    defaults={"config": config},
                )
                verb = "Created" if created else "Skipped (already exists)"

            self.stdout.write(
                f"  [{SLUG}] {graph.name}: {verb} "
                f"({count} filter node(s){dropped_note})"
            )
