from django.db import migrations

PLUGIN_DATA = {
    "pluginid": "7517ca99-689d-4840-acdf-bc65a449c30a",
    "name": "Certificate Generator",
    "icon": "fa fa-file",
    "component": "views/components/plugins/certificate-generator-plugin",
    "componentname": "certificate-generator-plugin",
    "config": {"show": True},
    "slug": "certificate-generator-plugin",
    "sortorder": 0,
}


def register_plugin(apps, schema_editor):
    Plugin = apps.get_model("models", "Plugin")
    Plugin.objects.update_or_create(
        pluginid=PLUGIN_DATA["pluginid"],
        defaults=PLUGIN_DATA,
    )


def unregister_plugin(apps, schema_editor):
    Plugin = apps.get_model("models", "Plugin")
    Plugin.objects.filter(pluginid=PLUGIN_DATA["pluginid"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0007_register_resource_id_descriptor"),
    ]

    operations = [
        migrations.RunPython(register_plugin, unregister_plugin),
    ]
