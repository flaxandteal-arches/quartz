from django.core.management.base import BaseCommand

from arches.app.models.models import CardModel, GraphModel, Node
from arches.app.models.system_settings import settings as arches_settings
from arches_modular_reports.models import ReportConfig

SEARCH_CONFIG = {
    "name": "Search Result",
    "theme": "",
    "components": [
        {
            "component": "arches_search/SearchResults/components/DescriptorSection",
            "config": {},
        }
    ],
}

EXCLUDED_DATATYPES = {"semantic", "annotation", "geojson-feature-collection"}


def build_expanded_config(graph):
    top_cards = (
        CardModel.objects.filter(
            graph=graph,
            nodegroup__parentnodegroup__isnull=True,
        )
        .order_by("sortorder")
    )

    sections = []
    for card in top_cards:
        grouping_node = Node.objects.filter(
            pk=card.nodegroup_id,
            graph=graph,
        ).first()
        if not grouping_node:
            continue
        node_aliases = list(
            Node.objects.filter(graph=graph, nodegroup=card.nodegroup)
            .exclude(datatype__in=EXCLUDED_DATATYPES)
            .exclude(cardxnodexwidget__visible=False)
            .values_list("alias", flat=True)
        )
        sections.append({
            "name": str(card.name),
            "components": [
                {
                    "component": "arches_modular_reports/ModularReport/components/DataSection",
                    "config": {
                        "nodegroup_alias": grouping_node.alias,
                        "node_aliases": node_aliases,
                        "custom_labels": {},
                        "custom_card_name": None,
                    },
                }
            ],
        })

    return {
        "name": "Search Result Expanded",
        "theme": "",
        "components": [
            {
                "component": "arches_modular_reports/ModularReport/components/LinkedSections",
                "config": {"sections": sections},
            }
        ] if sections else [],
    }


class Command(BaseCommand):
    help = "Create search and search_result_expanded ReportConfigs for all resource graphs. Run after load_package."

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace existing configs instead of skipping them.",
        )

    def handle(self, *args, **options):
        overwrite = options["overwrite"]

        graphs = GraphModel.objects.filter(
            isresource=True,
            slug__isnull=False,
        ).exclude(pk=arches_settings.SYSTEM_SETTINGS_RESOURCE_MODEL_ID)

        if not graphs.exists():
            self.stderr.write("No resource graphs found. Have you run load_package?")
            return

        for graph in graphs:
            self._upsert(graph, "search", SEARCH_CONFIG, overwrite)
            self._upsert(graph, "search_result_expanded", build_expanded_config(graph), overwrite)

    def _upsert(self, graph, slug, config, overwrite):
        if overwrite:
            obj, created = ReportConfig.objects.update_or_create(
                graph=graph,
                slug=slug,
                defaults={"config": config},
            )
            verb = "Created" if created else "Updated"
        else:
            obj, created = ReportConfig.objects.get_or_create(
                graph=graph,
                slug=slug,
                defaults={"config": config},
            )
            verb = "Created" if created else "Skipped (already exists)"

        self.stdout.write(f"  [{slug}] {graph.name}: {verb}")
