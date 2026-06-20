"""Ensure the blanket-role permission groups exist.

Idempotent on every ``migrate``. Membership only — these groups carry no
per-resource permission rows; the ``quartz.permissions.blanket_roles`` framework
grants resource-instance access by group membership when QUARTZ_BLANKET_ROLES is
enabled (default-deny). Creating the groups is a no-op while the framework is
off (the default), so this is safe to ship ahead of enabling deny.

Names are hard-coded (not imported from the framework module) so the migration
stays frozen-in-time; keep them in sync with FULL_ACCESS_GROUPS /
READ_ACCESS_GROUPS in quartz/permissions/blanket_roles.py.

Reverse is a no-op: un-applying must not delete groups (that would strip their
members' access and memberships).
"""

from django.db import migrations

GROUP_NAMES = ["Delegate", "Heritage Officer"]


def forwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    db_alias = schema_editor.connection.alias
    for name in GROUP_NAMES:
        Group.objects.using(db_alias).get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0009_set_admin_password_from_env"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
