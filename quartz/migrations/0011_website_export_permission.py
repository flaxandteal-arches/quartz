"""Create the 'export_to_website' permission and grant it to Delegate.

A Django auth Permission (codename ``export_to_website`` under app_label
``quartz``) that gates the "Export to Website" UI button and its endpoint. It is
group-assignable like any Django permission; this migration grants it to the
Delegate group. Superusers pass ``has_perm`` automatically, so they always see
and can use the button.

Created via a data migration (with a placeholder content type) rather than a
model, so there is no model for ``makemigrations --check`` to flag. The endpoint
enforces the permission server-side; the template only hides the button.

Reverse is a no-op (keep the permission/assignment).
"""

from django.db import migrations

PERM_CODENAME = "export_to_website"
PERM_NAME = "Can export public heritage to the website"


def forwards(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    db = schema_editor.connection.alias

    content_type, _ = ContentType.objects.using(db).get_or_create(
        app_label="quartz", model="websiteexport"
    )
    permission, _ = Permission.objects.using(db).get_or_create(
        codename=PERM_CODENAME,
        content_type=content_type,
        defaults={"name": PERM_NAME},
    )
    delegate, _ = Group.objects.using(db).get_or_create(name="Delegate")
    delegate.permissions.add(permission)


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0010_create_blanket_role_groups"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
