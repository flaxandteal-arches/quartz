import os

from django.core.management.base import BaseCommand, CommandError

PUBLIC_EXPORT_GROUP = "Public Export"
DEFAULT_BLOB_NAME = "prebuild.tgz"


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
            "--use-drafts",
            action="store_true",
            help="Export the Draft versions of matching Heritage Items "
            "instead of resolving to their Final (Active) versions",
        )
        parser.add_argument(
            "--as-user",
            dest="as_user",
            default=None,
            help="Apply nodegroup read permissions of this user when exporting "
            "(the writer drops tiles whose nodegroup the user cannot read). "
            f"Use the '{PUBLIC_EXPORT_GROUP}' service account to honour the "
            "public-export whitelist. Defaults to the 'anonymous' user "
            "(public-visitor view) when omitted.",
        )
        parser.add_argument(
            "--group",
            default=PUBLIC_EXPORT_GROUP,
            help=f"Group the --as-user account is expected to belong to "
            f"(default: {PUBLIC_EXPORT_GROUP}); used only for the guard checks",
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
        parser.add_argument(
            "--blob-name",
            dest="blob_name",
            default=os.environ.get("STARCHES_PREBUILD_BLOB_NAME", DEFAULT_BLOB_NAME),
            help="Name of the packaged artefact / Azure blob to upload "
            "(default: $STARCHES_PREBUILD_BLOB_NAME, else "
            f"'{DEFAULT_BLOB_NAME}'). Lets a k8s Job target a "
            "per-environment blob via an env var.",
        )
        parser.add_argument(
            "--push",
            action="store_true",
            help="Upload the packaged archive (see --blob-name) to the "
            "starches-validation Azure container",
        )
        parser.add_argument(
            "--trigger",
            action="store_true",
            help="Fire a GitHub repository_dispatch to launch the "
            "validation build",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            dest="run_async",
            help="Dispatch packaging/push/trigger via Celery instead of "
            "running it synchronously (requires a configured broker)",
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

    def _print_filtered_nodegroups(self, filtered):
        """Report nodegroups dropped from the export by the user's permissions."""
        if not filtered:
            self.stdout.write(
                "  Nodegroup filter: no nodegroups dropped for this user "
                "(everything present is readable)."
            )
            return
        self.stdout.write(
            self.style.WARNING(
                f"  Nodegroup filter: {len(filtered)} nodegroup(s) present in the "
                f"data will be DROPPED (user lacks read_nodegroup):"
            )
        )
        for ng in filtered:
            self.stdout.write(
                f"    {ng['graph_name']} / {ng['alias'] or '(root)'}  [{ng['nodegroup_id']}]"
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
        included = diagnostics.get("included_target_resources", 0)
        self.stdout.write(
            f"  Related visible resources included (e.g. Public Digital "
            f"Objects): {included}"
        )
        files = diagnostics.get("referenced_files", [])
        self.stdout.write(
            f"  Referenced files (images + Digital Object content), "
            f"written to files.json: {len(files)}"
        )

    def _resolve_export_user(self, username, expected_group):
        """Resolve --as-user to a User and guard against permission footguns.

        Returns the User whose read_nodegroup perms the writer will apply. When
        --as-user is not supplied, defaults to the 'anonymous' user so the
        export reflects exactly what an unauthenticated public visitor can read
        — rather than exporting every nodegroup. (The permission framework gives
        'anonymous' its own handling, honouring any no_access_to_nodegroup
        grants on the Public/Guest group.)
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()

        if not username:
            try:
                user = User.objects.get(username="anonymous")
            except User.DoesNotExist:
                self.stderr.write(
                    self.style.WARNING(
                        "No --as-user given and no 'anonymous' user found: "
                        "falling back to NO nodegroup filtering (every "
                        "nodegroup will be exported)."
                    )
                )
                return None
            self.stdout.write(
                "No --as-user given: applying the 'anonymous' user's nodegroup "
                "permissions (public-visitor view)."
            )
            return user

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(
                f"--as-user '{username}' does not exist. Seed it with: "
                f"manage.py sync_public_export_group --ensure-user {username}"
            )

        # Superusers short-circuit the permission framework to full access, so
        # the export would silently include every nodegroup. Refuse.
        if user.is_superuser:
            raise CommandError(
                f"--as-user '{username}' is a superuser; superusers bypass "
                f"nodegroup permissions so the whitelist would not apply. Use a "
                f"non-superuser service account in the '{expected_group}' group."
            )

        group_names = set(user.groups.values_list("name", flat=True))
        if expected_group not in group_names:
            self.stderr.write(
                self.style.WARNING(
                    f"  WARNING: '{username}' is not in the '{expected_group}' "
                    f"group, so the public-export whitelist will not be applied "
                    f"(nodegroups with no explicit perm export by default)."
                )
            )
        extra = group_names - {expected_group}
        if extra:
            self.stderr.write(
                self.style.WARNING(
                    f"  WARNING: '{username}' also belongs to {sorted(extra)}; "
                    f"read_nodegroup grants from those groups can re-expose "
                    f"nodegroups the whitelist denies. Use a single-group account."
                )
            )

        self.stdout.write(f"Applying nodegroup permissions of user '{username}'")
        return user

    def handle(self, *args, **options):
        from quartz.utils.public_export import (
            export_resources,
            get_draft_visibility_labels,
            get_final_resource_ids,
            get_outbound_relations,
            get_user_filtered_nodegroups,
            get_visibility_node_for_graph,
            get_visibility_nodes,
            get_visibility_uris,
            get_visible_draft_resource_ids,
            HERITAGE_ITEM_GRAPH_ID,
        )

        target_labels = options["visibility"]
        output_dir = options["output"]
        use_drafts = options["use_drafts"]
        dry_run = options["dry_run"]
        indent = options["indent"] or None
        push = options["push"]
        trigger = options["trigger"]
        run_async = options["run_async"]
        blob_name = options["blob_name"]

        # Async: hand the WHOLE pipeline to a worker, which generates output_dir
        # itself (nothing pre-staged). Dry-run still previews locally below.
        if run_async and not dry_run:
            from django.conf import settings as dj_settings

            if getattr(dj_settings, "CELERY_BROKER_URL", ""):
                from quartz.tasks import run_public_export

                async_result = run_public_export.delay(
                    visibility=target_labels,
                    output_dir=output_dir,
                    use_drafts=use_drafts,
                    indent=indent,
                    as_user=options["as_user"],
                    push=push,
                    trigger=trigger,
                    blob_name=blob_name,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Dispatched full public-export pipeline to worker: "
                        f"{async_result.id}"
                    )
                )
                return

            self.stderr.write(
                self.style.WARNING(
                    "--async requested but CELERY_BROKER_URL is not "
                    "configured; running the full export synchronously."
                )
            )
            run_async = False

        # 0. Resolve the optional export user (applies nodegroup read perms).
        export_user = self._resolve_export_user(
            options["as_user"], options["group"]
        )

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

        # 4. Select export targets: either the Drafts themselves, or their
        #    resolved Final (Active) versions.
        if use_drafts:
            export_ids = list(draft_ids)
            export_labels = {str(k): v for k, v in draft_labels.items()}
            self.stdout.write(
                self.style.WARNING(
                    f"Exporting {len(export_ids)} Draft versions "
                    f"directly (--use-drafts)"
                )
            )
        else:
            self.stdout.write("Resolving Final (Active) versions...")
            export_ids, missing_groups, export_labels = get_final_resource_ids(
                draft_ids, draft_labels=draft_labels,
            )
            self.stdout.write(f"  Found {len(export_ids)} Final versions")

            for group_id in missing_groups:
                self.stderr.write(
                    self.style.WARNING(
                        f"  WARNING: resource group {group_id} has no Final version"
                    )
                )

        if not export_ids:
            self.stdout.write(
                self.style.WARNING("No versions to export.")
            )
            return

        # 4b. Report nodegroups the export user is not permitted to read (and
        #     which the writer will therefore drop from the output).
        if export_user is not None:
            self._print_filtered_nodegroups(
                get_user_filtered_nodegroups(export_ids, export_user)
            )

        # 5. Dry run or export
        if dry_run:
            self.stdout.write("Checking outbound relations...")
            relations, diagnostics, target_ids = get_outbound_relations(
                export_ids,
                visibility_nodes=visibility_nodes,
                visibility_uris=uris,
            )
            related = {str(t) for t in target_ids} - {str(r) for r in export_ids}
            self._print_relation_diagnostics(diagnostics)
            self.stdout.write(
                self.style.SUCCESS(
                    f"DRY RUN: Would export {len(export_ids)} resources "
                    f"(plus {len(related)} related visible resources, "
                    f"e.g. Public Digital Objects) "
                    f"with {len(relations)} outbound relations "
                    f"to {output_dir}/"
                )
            )
            for rid in export_ids:
                self.stdout.write(f"  {rid}")
            return

        # 6. Export as pkg-style directory
        self.stdout.write(f"Exporting {len(export_ids)} resources to {output_dir}/...")
        result, diagnostics = export_resources(
            export_ids,
            output_dir=output_dir,
            visibility_nodes=visibility_nodes,
            visibility_uris=uris,
            resource_labels=export_labels,
            user=export_user,
            indent=indent,
        )

        if not result:
            self.stderr.write(self.style.ERROR("Export produced no output"))
            return

        self._print_relation_diagnostics(diagnostics)
        self._print_pkg_diagnostics(diagnostics)
        self.stdout.write(self.style.SUCCESS(f"Exported to {result}/"))

        # 7. Package the export and (optionally) push it to the
        #    starches-validation container / trigger the validation build.
        self._package_and_push(result, push, trigger, run_async, blob_name)

    def _package_and_push(self, output_dir, push, trigger, run_async, blob_name):
        """Package the export to prebuild.tgz and optionally push/trigger."""
        from quartz.tasks import export_and_push_public_heritage

        if run_async:
            from django.conf import settings

            if not getattr(settings, "CELERY_BROKER_URL", ""):
                self.stderr.write(
                    self.style.WARNING(
                        "--async requested but CELERY_BROKER_URL is not "
                        "configured; running synchronously instead."
                    )
                )
                run_async = False

        self.stdout.write(f"Packaging export as {blob_name}...")
        if run_async:
            async_result = export_and_push_public_heritage.delay(
                output_dir, push=push, trigger=trigger, blob_name=blob_name,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dispatched packaging task: {async_result.id}"
                )
            )
            return

        result = export_and_push_public_heritage(
            output_dir, push=push, trigger=trigger, blob_name=blob_name,
        )

        self.stdout.write(f"  Archive: {result['archive_path']}")
        if push:
            if result["uploaded_url"]:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Uploaded: {result['uploaded_url']}"
                    )
                )
        if trigger:
            if result["triggered_status"]:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Triggered build (HTTP {result['triggered_status']})"
                    )
                )
        for skipped in result["skipped"]:
            self.stdout.write(self.style.WARNING(f"  Skipped {skipped}"))
        for error in result["errors"]:
            self.stderr.write(self.style.ERROR(f"  Error {error}"))
