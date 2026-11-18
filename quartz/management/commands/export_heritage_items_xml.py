from django.core.management.base import CommandError

from quartz.management.commands.export_public_heritage_items import (
    Command as PublicExportCommand,
    PUBLIC_EXPORT_GROUP,
)


class Command(PublicExportCommand):
    """Research XML export. Reuses the public export's --as-user resolution, but
    writes one XML file in the published register format instead of a pkg."""

    help = (
        "Export the register as a single XML file for researchers, in the same "
        "structure as the published heritage register file: the Final versions "
        "of Heritage Items with Heritage Item Visibility Public whose "
        "designation and protection status is Entered."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "-o",
            "--output",
            default="heritage-register.xml",
            help="Output XML file path (default: heritage-register.xml)",
        )
        parser.add_argument(
            "--as-user",
            dest="as_user",
            default=None,
            help="Apply nodegroup read permissions of this user (fields in "
            "nodegroups the user cannot read are omitted). Defaults to the "
            "'anonymous' user (public-visitor view).",
        )
        parser.add_argument(
            "--group",
            default=PUBLIC_EXPORT_GROUP,
            help=f"Group the --as-user account is expected to belong to "
            f"(default: {PUBLIC_EXPORT_GROUP}); used only for the guard checks",
        )
        parser.add_argument(
            "--language",
            default="en",
            help="Preferred language for text and labels (default: en)",
        )

    def handle(self, *args, **options):
        from arches.app.utils.permission_backend import get_nodegroups_by_perm

        from quartz.utils.public_xml_export import (
            export_register_xml,
            select_public_resource_ids,
        )

        export_user = self._resolve_export_user(options["as_user"], options["group"])
        permitted = None
        if export_user is not None:
            permitted = get_nodegroups_by_perm(export_user, "models.read_nodegroup")
        else:
            self.stderr.write(
                self.style.WARNING(
                    "No nodegroup filtering applied: every field of every "
                    "exported place will be written. Create the 'anonymous' "
                    "user or pass --as-user."
                )
            )

        ids, missing_groups = select_public_resource_ids()
        for group_id in missing_groups:
            self.stderr.write(
                self.style.WARNING(
                    f"WARNING: resource group {group_id} has no Final version, skipped"
                )
            )
        if not ids:
            raise CommandError("No Public Heritage Items found.")
        self.stdout.write(f"Found {len(ids)} Public Heritage Items (Final versions)")

        result = export_register_xml(
            ids,
            options["output"],
            permitted_nodegroups=permitted,
            language=options["language"],
        )
        for key, reason in (
            ("skipped_not_public", "not Public"),
            ("skipped_not_entered", "not Entered (designation and protection status)"),
        ):
            if result[key]:
                self.stdout.write(f"  Skipped {result[key]}: {reason}")
        if result["dropped_fields"]:
            self.stderr.write(
                self.style.WARNING(
                    "Omitted (user cannot read the nodegroup): "
                    + ", ".join(result["dropped_fields"])
                )
            )
        if result["count"] == 0:
            self.stderr.write(
                self.style.WARNING(
                    "No places matched, so the file is an empty register."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {result['count']} places to {options['output']}")
        )
