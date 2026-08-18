from django.db import migrations

COMPONENT_NAME = "search-results"
QUARTZ_MODULE = ("single_pin_search_results.py", "SinglePinSearchResultsFilter")
CORE_MODULE = ("search_results.py", "SearchResultsFilter")


def point_at(module):
    def apply(apps, schema_editor):
        SearchComponent = apps.get_model("models", "SearchComponent")
        modulename, classname = module
        SearchComponent.objects.filter(componentname=COMPONENT_NAME).update(
            modulename=modulename, classname=classname
        )

    return apply


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0012_update_condition_report_select_lists"),
    ]

    operations = [
        migrations.RunPython(point_at(QUARTZ_MODULE), point_at(CORE_MODULE)),
    ]
