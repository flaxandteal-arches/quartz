"""Idempotent setup of nodegroup permissions on versioning nodegroups.

Ensures Heritage Officers can read but NOT write the versioning nodegroup
(which contains version number, working copy reference, and visibility).
This prevents officers from changing visibility through the editor UI.
Delegates retain full write access.

Safe to run repeatedly — clears then reassigns each time.
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

READ = "read_nodegroup"
WRITE = "write_nodegroup"
NO_ACCESS = "no_access_to_nodegroup"
NODEGROUP_PERMS = {READ, WRITE, "delete_nodegroup", NO_ACCESS}

VERSIONING_NODEGROUPS = {
    "03d5eb66-d748-57cc-8390-5788078696d7",  # Heritage Item
    "07028e38-c27c-572f-8be5-e37ec837ad4f",  # Artefact
}

PERMISSIONS_PLAN = {
    "Heritage Officer": READ,
    "Delegate": WRITE,
}


class Command(BaseCommand):
    help = "Set versioning nodegroup permissions (Heritage Officer=read, Delegate=write)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the plan without writing any permissions",
        )

    def handle(self, *args, **options):
        from arches.app.models.models import NodeGroup
        from arches.app.utils.permission_backend import (
            assign_perm,
            get_perms,
            remove_perm,
        )

        dry_run = options["dry_run"]

        nodegroups = {
            str(ng.pk): ng
            for ng in NodeGroup.objects.filter(pk__in=VERSIONING_NODEGROUPS)
        }

        missing = VERSIONING_NODEGROUPS - set(nodegroups.keys())
        if missing:
            self.stderr.write(
                self.style.WARNING(
                    f"Nodegroups not found (graph not loaded?): {missing}"
                )
            )

        if dry_run:
            for group_name, codename in PERMISSIONS_PLAN.items():
                for ng_id in nodegroups:
                    self.stdout.write(
                        f"  [DRY RUN] {group_name} -> {ng_id}: {codename}"
                    )
            self.stdout.write(self.style.SUCCESS("DRY RUN: no changes written"))
            return

        with transaction.atomic():
            for group_name, codename in PERMISSIONS_PLAN.items():
                group, _ = Group.objects.get_or_create(name=group_name)

                for ng_id, nodegroup in nodegroups.items():
                    for existing in get_perms(group, nodegroup):
                        if existing in NODEGROUP_PERMS:
                            remove_perm(existing, group, nodegroup)
                    assign_perm(codename, group, nodegroup)
                    self.stdout.write(f"  {group_name} -> {ng_id}: {codename}")

        self.stdout.write(self.style.SUCCESS("Versioning permissions applied"))
