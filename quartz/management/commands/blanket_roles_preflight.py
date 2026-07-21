"""Pre-flight for enabling the hard-gate blanket-role framework.

Switching to the blanket-role gate (QUARTZ_BLANKET_ROLES=True) confines
resource-instance access to an allowlist: superuser, Delegate (full) and
Heritage Officer (view + change on Draft). It is a HARD GATE — it also overrides
the base owner (principaluser) short-circuit and explicit per-instance rows, so
being in a blanket group is the ONLY way an ordinary user keeps access. This
command reports who would lose access — i.e. active, non-superuser users who are
NOT in a blanket-access group — so the switch can be made safely. It also
re-ensures the groups exist (the same set the migration seeds), so it is a
no-op-safe convenience.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from quartz.permissions.blanket_roles import (
    FULL_ACCESS_GROUPS,
    READ_ACCESS_GROUPS,
)

BLANKET_GROUPS = FULL_ACCESS_GROUPS + READ_ACCESS_GROUPS


class Command(BaseCommand):
    help = (
        "Report users who would lose default resource-instance access when the "
        "blanket-role default-deny framework is enabled, and ensure the groups "
        "exist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Max at-risk usernames to list (default: 50)",
        )

    def handle(self, *args, **options):
        for name in BLANKET_GROUPS:
            _, created = Group.objects.get_or_create(name=name)
            self.stdout.write(
                f"  group '{name}': {'created' if created else 'exists'}"
            )

        User = get_user_model()
        at_risk = (
            User.objects.filter(is_active=True, is_superuser=False)
            .exclude(groups__name__in=BLANKET_GROUPS)
            .distinct()
        )
        count = at_risk.count()

        self.stdout.write("")
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "Pre-flight OK: every active non-superuser is already in a "
                    f"blanket group {BLANKET_GROUPS} (or there are none)."
                )
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"{count} active non-superuser user(s) are NOT in {BLANKET_GROUPS} "
                f"and will LOSE ALL resource-instance access when "
                f"QUARTZ_BLANKET_ROLES is enabled. The hard gate overrides owner "
                f"and explicit per-instance grants, so add them to a blanket group "
                f"before enabling it in production:"
            )
        )
        for username in at_risk.values_list("username", flat=True)[: options["limit"]]:
            self.stdout.write(f"    {username}")
        if count > options["limit"]:
            self.stdout.write(f"    ... and {count - options['limit']} more")
