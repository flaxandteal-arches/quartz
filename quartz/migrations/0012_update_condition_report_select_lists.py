from django.db import migrations

CONDITION_REPORT_GRAPHID = "9fccd932-8e8f-4595-89bd-3cb04ddfecae"

# nodeid -> (old controlledList id, new controlledList id)
NODE_CONTROLLED_LIST_UPDATES = {
    "9cbe0f0d-e6e5-4999-b3cd-5d85cdaceb43": (  # maintenance
        "11e94aef-1f27-4f5a-9f0c-4a573cb1fa09",
        "0e499a33-4bda-528d-a2e4-d3c2b34b7f64",
    ),
    "9f196994-68b6-4971-a528-6e6e923cdb0b": (  # occupancy
        "46d6c3b3-fa78-48c0-8668-28362a608c70",
        "dc4f53d9-3634-536c-9f5f-ecd0701b7418",
    ),
    "fa209d71-a371-4ef8-8589-a9fa2d93e6de": (  # condition
        "2953436b-3673-40e8-a521-ab34801800db",
        "3ea13a92-a333-5f9e-a91e-fe5a7311953f",
    ),
}


def update_node_controlled_lists(apps, schema_editor, updates):
    from arches.app.models.graph import Graph
    from arches.app.models.models import Node

    for nodeid, controlled_list_id in updates.items():
        for node in Node.objects.filter(pk=nodeid) | Node.objects.filter(
            source_identifier_id=nodeid
        ):
            node.config["controlledList"] = controlled_list_id
            node.save()

    Graph.objects.get(
        pk=CONDITION_REPORT_GRAPHID, source_identifier__isnull=True
    ).publish()


def update_select_lists_for_cr(apps, schema_editor):
    update_node_controlled_lists(
        apps,
        schema_editor,
        {
            nodeid: new_controlled_list_id
            for nodeid, (
                _,
                new_controlled_list_id,
            ) in NODE_CONTROLLED_LIST_UPDATES.items()
        },
    )


def revert_select_lists_for_cr(apps, schema_editor):
    update_node_controlled_lists(
        apps,
        schema_editor,
        {
            nodeid: old_controlled_list_id
            for nodeid, (
                old_controlled_list_id,
                _,
            ) in NODE_CONTROLLED_LIST_UPDATES.items()
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0011_website_export_permission"),
    ]

    operations = [
        migrations.RunPython(update_select_lists_for_cr, revert_select_lists_for_cr),
    ]
