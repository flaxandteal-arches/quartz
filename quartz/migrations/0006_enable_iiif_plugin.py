from django.db import migrations

IIIF_PLUGIN_ID = "6f707d86-d49c-4ece-9883-8cbb2ecda1b5"


def enable_iiif_plugin(apps, schema_editor):
    Plugin = apps.get_model("models", "Plugin")
    plugin = Plugin.objects.get(pluginid=IIIF_PLUGIN_ID)
    plugin.config = {"show": True}
    plugin.save(update_fields=["config"])


def disable_iiif_plugin(apps, schema_editor):
    Plugin = apps.get_model("models", "Plugin")
    plugin = Plugin.objects.get(pluginid=IIIF_PLUGIN_ID)
    plugin.config = {"show": False}
    plugin.save(update_fields=["config"])


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0005_remove_heritageitemstate"),
        ("models", "6979_manifest_manager"),
    ]

    operations = [
        migrations.RunPython(enable_iiif_plugin, disable_iiif_plugin),
    ]
