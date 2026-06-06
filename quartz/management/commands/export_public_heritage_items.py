from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Export Final versions of Heritage Items with Public/Staging visibility"

    def add_arguments(self, parser):
        parser.add_argument(
            "-o",
            "--output",
            default="public_export",
            help="Output directory path (default: public_export)",
        )
        parser.add_argument(
            "--visibility",
            nargs="+",
            default=["Public", "Staging"],
            help='Visibility labels to include (default: Public Staging)',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be exported without writing",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="JSON indentation (default: 2, use 0 for compact)",
        )

    def _print_visibility_diagnostics(self, visibility_nodes, label):
        """Print which graphs have visibility nodes."""
        self.stdout.write(f"  {label}:")
        for vn in visibility_nodes:
            self.stdout.write(
                f"    {vn['graph_name']}: node {vn['node_id']} "
                f"(alias: {vn['alias']})"
            )

    def _print_relation_diagnostics(self, diagnostics):
        """Print relation filtering details."""
        self.stdout.write("  Relation filtering:")
        self.stdout.write(
            f"    Candidate relations (from in-scope tiles, "
            f"to graphs with visibility): {diagnostics['candidate_relations']}"
        )
        self.stdout.write(
            f"    Target resources total: "
            f"{diagnostics['target_resources_total']}"
        )
        self.stdout.write(
            f"    Target resources passing visibility filter: "
            f"{diagnostics['target_resources_visible']}"
        )
        if diagnostics["target_resources_filtered_out"]:
            self.stdout.write(
                self.style.WARNING(
                    f"    Target resources filtered out "
                    f"(visibility mismatch): "
                    f"{diagnostics['target_resources_filtered_out']}"
                )
            )

    def _print_pkg_diagnostics(self, diagnostics):
        """Print package export details."""
        if graphs := diagnostics.get("exported_graphs"):
            self.stdout.write(f"  Graphs exported: {len(graphs)}")
            for name in graphs:
                self.stdout.write(f"    {name}")
        if lists := diagnostics.get("exported_controlled_lists"):
            self.stdout.write(f"  Controlled lists exported: {len(lists)}")
            for name in lists:
                self.stdout.write(f"    {name}")

    def handle(self, *args, **options):
        from quartz.utils.public_export import (
            export_resources,
            get_draft_visibility_labels,
            get_final_resource_ids,
            get_outbound_relations,
            get_visibility_node_for_graph,
            get_visibility_nodes,
            get_visibility_uris,
            get_visible_draft_resource_ids,
            HERITAGE_ITEM_GRAPH_ID,
        )

        target_labels = options["visibility"]
        output_dir = options["output"]
        dry_run = options["dry_run"]
        indent = options["indent"] or None

        # 1. Discover all visibility nodes across graphs
        self.stdout.write("Discovering visibility nodes (controlled list lookup)...")
        visibility_nodes = get_visibility_nodes()
        if not visibility_nodes:
            self.stderr.write(
                self.style.ERROR("No visibility nodes found in any graph.")
            )
            return

        self._print_visibility_diagnostics(
            visibility_nodes, "Graphs with visibility node"
        )

        hi_visibility = get_visibility_node_for_graph(
            visibility_nodes, HERITAGE_ITEM_GRAPH_ID
        )
        if not hi_visibility:
            self.stderr.write(
                self.style.ERROR(
                    "Heritage Item graph has no visibility node."
                )
            )
            return

        # 2. Look up URIs for target visibility labels
        self.stdout.write(
            f"Looking up visibility URIs for: {', '.join(target_labels)}"
        )
        uris = get_visibility_uris(target_labels)
        if not uris:
            self.stderr.write(
                self.style.ERROR(
                    f"No controlled list items found for labels: {target_labels}"
                )
            )
            return

        for uri in uris:
            self.stdout.write(f"  {uri}")

        # 3. Find Draft Heritage Items with matching visibility
        self.stdout.write("Finding Draft Heritage Items with matching visibility...")
        draft_ids = get_visible_draft_resource_ids(hi_visibility, uris)
        self.stdout.write(f"  Found {len(draft_ids)} matching Draft resources")

        if not draft_ids:
            self.stdout.write(
                self.style.WARNING("No matching Heritage Items found.")
            )
            return

        # 3b. Build Draft → visibility label mapping
        draft_labels = get_draft_visibility_labels(hi_visibility, uris)

        # 4. Resolve to Final (Active) versions
        self.stdout.write("Resolving Final (Active) versions...")
        final_ids, missing_groups, final_labels = get_final_resource_ids(
            draft_ids, draft_labels=draft_labels,
        )
        self.stdout.write(f"  Found {len(final_ids)} Final versions")

        for group_id in missing_groups:
            self.stderr.write(
                self.style.WARNING(
                    f"  WARNING: resource group {group_id} has no Final version"
                )
            )

        if not final_ids:
            self.stdout.write(
                self.style.WARNING("No Final versions to export.")
            )
            return

        # 5. Dry run or export
        if dry_run:
            self.stdout.write("Checking outbound relations...")
            relations, diagnostics = get_outbound_relations(
                final_ids,
                visibility_nodes=visibility_nodes,
                visibility_uris=uris,
            )
            self._print_relation_diagnostics(diagnostics)
            self.stdout.write(
                self.style.SUCCESS(
                    f"DRY RUN: Would export {len(final_ids)} resources "
                    f"with {len(relations)} outbound relations "
                    f"to {output_dir}/"
                )
            )
            for rid in final_ids:
                self.stdout.write(f"  {rid}")
            return

        # 6. Export as pkg-style directory
        self.stdout.write(f"Exporting {len(final_ids)} resources to {output_dir}/...")
        result, diagnostics = export_resources(
            final_ids,
            output_dir=output_dir,
            visibility_nodes=visibility_nodes,
            visibility_uris=uris,
            resource_labels=final_labels,
            indent=indent,
        )

        if result:
            self._print_relation_diagnostics(diagnostics)
            self._print_pkg_diagnostics(diagnostics)
            self.stdout.write(self.style.SUCCESS(f"Exported to {result}/"))
        else:
            self.stderr.write(self.style.ERROR("Export produced no output"))
