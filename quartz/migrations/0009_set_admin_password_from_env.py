import os

from django.db import migrations


def set_admin_password(apps, schema_editor):
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        return

    User = apps.get_model("auth", "User")
    try:
        admin = User.objects.using(schema_editor.connection.alias).get(username="admin")
    except User.DoesNotExist:
        return

    # apps.get_model returns a historical model without set_password(),
    # so use make_password directly.
    from django.contrib.auth.hashers import make_password

    admin.password = make_password(password)
    admin.save(update_fields=["password"])


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0007_register_resource_id_descriptor"),
    ]

    operations = [
        migrations.RunPython(set_admin_password, migrations.RunPython.noop),
    ]
