import os
from django.db import migrations


def import_condition_report_graph(apps, schema_editor):
    from arches.app.utils.betterJSONSerializer import JSONDeserializer
    from arches.app.utils.data_management.resource_graphs.importer import import_graph

    graph_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "pkg",
        "graphs",
        "resource_models",
        "Condition Report.json",
    )

    with open(graph_path, "r") as f:
        archesfile = JSONDeserializer().deserialize(f)

    errors, _ = import_graph(archesfile["graph"], overwrite_graphs=True)

    if errors:
        raise Exception(f"Graph import errors: {errors}")


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0007_register_resource_id_descriptor"),
    ]

    operations = [
        migrations.RunPython(import_condition_report_graph, migrations.RunPython.noop),
    ]
