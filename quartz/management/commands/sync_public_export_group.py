"""Create/sync a Django Group whose Arches nodegroup permissions mirror the
starches ``permissions.json`` whitelist used for the public export.

Nodegroup permissions are allow-by-default in Arches: a nodegroup with no
object-level permission is treated as accessible (see
``get_nodegroups_by_perm_for_user_or_group`` in arches_permission_base — "if no
explicit permissions, object is considered accessible by all with group
permissions"). This is independent of the PERMISSION_FRAMEWORK setting, which
only governs resource-*instance* defaults. To make this group a whitelist we
must therefore EXPLICITLY deny (``no_access_to_nodegroup``) every nodegroup that
is not whitelisted; granting only ``read_nodegroup`` on the allowed ones would
leave everything else readable.

For every graph referenced in ``permissions.json`` this command, per nodegroup:
  * assigns ``read_nodegroup``        when the alias is whitelisted (``true`` or
                                       a value-filtered ``{path, allowed}`` rule)
  * assigns ``no_access_to_nodegroup`` otherwise (explicit ``false``, or any
                                       nodegroup in the graph not mentioned)

Value-level filters (``{path, allowed}`` for ``images``/``descriptions``) cannot
be expressed as a nodegroup permission; the nodegroup is granted read and the
value filtering stays in the export code.
"""

import json
import re
from pathlib import Path

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F

GROUP_NAME = "Public Export"
READ = "read_nodegroup"
NO_ACCESS = "no_access_to_nodegroup"
NODEGROUP_PERMS = {READ, "write_nodegroup", "delete_nodegroup", NO_ACCESS}

# permissions.json key -> Arches graph name overrides (where CamelCase-splitting
# does not produce the real display name). Extend as needed.
GRAPH_NAME_OVERRIDES = {
    "Licence": ["Licence", "License"],
}


def graph_name_candidates(key):
    """Return possible Arches graph names for a starches graph key."""
    if key in GRAPH_NAME_OVERRIDES:
        return GRAPH_NAME_OVERRIDES[key]
    # "HeritageItem" -> "Heritage Item", "BibliographicSource" -> "Bibliographic Source"
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", key)
    return [spaced, key]


class Command(BaseCommand):
    help = (
        "Create/sync the 'Public Export' Django group with nodegroup "
        "permissions matching the starches permissions.json whitelist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--permissions",
            default=str(
                Path(__file__).resolve().parents[4]
                / "quartz-starches"
                / "prebuild"
                / "permissions.json"
            ),
            help="Path to permissions.json (default: ../quartz-starches/prebuild/permissions.json)",
        )
        parser.add_argument(
            "--group", default=GROUP_NAME, help=f"Group name (default: {GROUP_NAME})"
        )
        parser.add_argument(
            "--ensure-user",
            dest="ensure_user",
            default=None,
            help="Username of a non-login service account to create (if missing) "
            "and place in the group, for use as the export's --as-user. The "
            "account gets an unusable password and is removed from all other "
            "groups so it only carries the export whitelist.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the plan without writing any permissions",
        )

    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        from arches.app.models.models import Node, NodeGroup
        from arches.app.utils.permission_backend import (
            assign_perm,
            get_perms,
            remove_perm,
        )

        path = Path(options["permissions"])
        if not path.exists():
            raise CommandError(f"permissions.json not found at {path}")
        config = json.loads(path.read_text())

        dry_run = options["dry_run"]
        group_name = options["group"]
        ensure_user = options["ensure_user"]

        # Build the desired plan: {nodegroup_id: READ | NO_ACCESS}
        plan = {}            # nodegroup_id(str) -> codename
        labels = {}          # nodegroup_id(str) -> "GraphName / alias" for output
        skipped_graphs = []
        skipped_aliases = []

        for graph_key, entry in config.items():
            graph_id = self._resolve_graph(Node, graph_key)
            if graph_id is None:
                skipped_graphs.append(graph_key)
                continue

            # All nodegroups in this graph (we manage every one of them because
            # nodegroups are allow-by-default — an un-whitelisted nodegroup with
            # no explicit perm would otherwise stay readable).
            graph_ngs = {
                str(ng_id): alias
                for ng_id, alias in Node.objects.filter(
                    graph_id=graph_id,
                    nodeid=F("nodegroup_id"),
                    source_identifier__isnull=True,
                ).values_list("nodegroup_id", "alias")
            }

            if entry is True:
                # Whole graph readable.
                for ng_id, alias in graph_ngs.items():
                    plan[ng_id] = READ
                    labels[ng_id] = f"{graph_key} / {alias or '(root)'}"
                continue

            if not isinstance(entry, dict) or not entry:
                # {} or falsy -> deny every nodegroup in the graph.
                for ng_id, alias in graph_ngs.items():
                    plan[ng_id] = NO_ACCESS
                    labels[ng_id] = f"{graph_key} / {alias or '(root)'}"
                continue

            # Per-alias dict. Resolve each whitelisted alias to its nodegroup,
            # then deny anything in the graph that wasn't named.
            allowed_ng_ids = set()
            for alias, rule in entry.items():
                ng_id = self._resolve_nodegroup(Node, graph_id, alias)
                if ng_id is None:
                    skipped_aliases.append(f"{graph_key} / {alias or '(root)'}")
                    continue
                allowed = bool(rule)  # true OR a {path, allowed} filter dict
                plan[ng_id] = READ if allowed else NO_ACCESS
                labels[ng_id] = f"{graph_key} / {alias or '(root)'}"
                allowed_ng_ids.add(ng_id)

            for ng_id, alias in graph_ngs.items():
                if ng_id not in allowed_ng_ids:
                    plan.setdefault(ng_id, NO_ACCESS)
                    labels.setdefault(ng_id, f"{graph_key} / {alias or '(root)'}")

        # ----------------------------------------------------------------
        n_read = sum(1 for c in plan.values() if c == READ)
        n_deny = sum(1 for c in plan.values() if c == NO_ACCESS)
        self.stdout.write(
            f"Plan: {n_read} read, {n_deny} no_access across "
            f"{len(plan)} nodegroups for group '{group_name}'"
        )
        for ng_id, codename in sorted(plan.items(), key=lambda kv: labels[kv[0]]):
            mark = "+" if codename == READ else "-"
            self.stdout.write(f"  {mark} {labels[ng_id]}")

        for g in skipped_graphs:
            self.stderr.write(
                self.style.WARNING(f"  graph not found in this DB, skipped: {g}")
            )
        for a in skipped_aliases:
            self.stderr.write(
                self.style.WARNING(f"  alias not found, skipped: {a}")
            )

        if dry_run:
            self.stdout.write(self.style.SUCCESS("DRY RUN: no changes written"))
            return

        with transaction.atomic():
            group, created = Group.objects.get_or_create(name=group_name)
            self.stdout.write(
                f"Group '{group_name}' {'created' if created else 'exists'}"
            )
            ngs = {
                str(ng.pk): ng
                for ng in NodeGroup.objects.filter(pk__in=list(plan.keys()))
            }
            for ng_id, codename in plan.items():
                nodegroup = ngs.get(ng_id)
                if nodegroup is None:
                    continue
                # Clear-then-assign (idempotent) — mirrors PermissionDataView.
                for existing in get_perms(group, nodegroup):
                    if existing in NODEGROUP_PERMS:
                        remove_perm(existing, group, nodegroup)
                assign_perm(codename, group, nodegroup)

            if ensure_user:
                self._ensure_service_user(ensure_user, group)

        self.stdout.write(
            self.style.SUCCESS(
                f"Applied {n_read} read / {n_deny} no_access to '{group_name}'"
            )
        )

    def _ensure_service_user(self, username, group):
        """Create (if missing) a login-disabled service account whose ONLY group
        is ``group``, so it can be used as the export's --as-user."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"is_active": True, "is_staff": False, "is_superuser": False},
        )
        if created:
            user.set_unusable_password()
        if user.is_superuser:
            # Refuse to leave a superuser as the export account — it would
            # bypass nodegroup permissions entirely.
            raise CommandError(
                f"--ensure-user '{username}' is an existing superuser; refusing. "
                f"Superusers bypass nodegroup permissions."
            )
        user.save()
        # Single-group membership: the export guard treats extra groups as a
        # whitelist leak, so make this account carry only the export group.
        removed = set(user.groups.values_list("name", flat=True)) - {group.name}
        if removed:
            self.stderr.write(
                self.style.WARNING(
                    f"  '{username}' was also in {sorted(removed)}; removing those "
                    f"so it carries only '{group.name}'. (Use a dedicated service "
                    f"account if this was not intended.)"
                )
            )
        user.groups.set([group])
        self.stdout.write(
            self.style.SUCCESS(
                f"Service user '{username}' {'created' if created else 'updated'} "
                f"(sole group: '{group.name}')"
            )
        )

    # ------------------------------------------------------------------ #

    def _resolve_graph(self, Node, graph_key):
        """Return the published graph_id for a starches graph key, or None."""
        from arches.app.models.models import GraphModel

        for name in graph_name_candidates(graph_key):
            graph = GraphModel.objects.filter(
                name__icontains=name,
                source_identifier__isnull=True,
                isresource=True,
            ).first()
            if graph and str(graph.name).lower() == name.lower():
                return graph.graphid
        return None

    def _resolve_nodegroup(self, Node, graph_id, alias):
        """Resolve a nodegroup alias ('' = root top node) to its nodegroup_id."""
        qs = Node.objects.filter(
            graph_id=graph_id, source_identifier__isnull=True
        )
        node = (
            qs.filter(istopnode=True).first()
            if alias == ""
            else qs.filter(alias=alias).first()
        )
        if node is None or node.nodegroup_id is None:
            return None
        return str(node.nodegroup_id)
