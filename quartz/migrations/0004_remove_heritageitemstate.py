from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0003_alter_heritageitemstate_state"),
        ("arches_resource_version_manager", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(
            name="HeritageItemState",
        ),
    ]
