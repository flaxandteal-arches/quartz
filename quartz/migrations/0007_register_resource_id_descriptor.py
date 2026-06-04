import uuid
from django.db import migrations

FUNCTION_ID = "e7d7fd2a-973a-4b2c-8c6e-bd2238d7be70"
CONDITION_REPORT_GRAPH_ID = "9fccd932-8e8f-4595-89bd-3cb04ddfecae"
CONDITION_REPORT_FXG_ID = "3447c3ef-8a5e-4a2b-a3a4-bb31a2613817"
ASSOCIATED_HI_NODEGROUP_ID = "77cef118-454b-46e8-98a1-ab72095b3e3c"
DESCRIPTOR_TEMPLATE = "<associated_monument_heritage_item|resourceid>, <condition>, <report_date>"

FUNCTION_DETAILS = {
    "name": "Resource ID Descriptor",
    "functiontype": "primarydescriptors",
    "description": (
        "Like Multi-card Resource Descriptor but supports <alias|id> and <alias|nodealias> "
        "placeholders. <alias|id> expands to the UUID of the first linked resource. "
        "<alias|nodealias> expands to the value of that node on the linked resource."
    ),
    "defaultconfig": {
        "descriptor_types": {
            "name": {"nodegroup_id": "", "string_template": ""},
            "map_popup": {"nodegroup_id": "", "string_template": ""},
            "description": {"nodegroup_id": "", "string_template": ""},
        }
    },
    "classname": "ResourceIdDescriptor",
    "modulename": "resource_id_descriptor.py",
    "component": "views/components/functions/multicard-resource-descriptor",
}


def register_function(apps, schema_editor):
    Function = apps.get_model("models", "Function")
    GraphModel = apps.get_model("models", "GraphModel")
    FunctionXGraph = apps.get_model("models", "FunctionXGraph")

    Function.objects.update_or_create(
        functionid=uuid.UUID(FUNCTION_ID),
        defaults=FUNCTION_DETAILS,
    )

    descriptor_config = {
        "descriptor_types": {
            "name": {"nodegroup_id": ASSOCIATED_HI_NODEGROUP_ID, "string_template": DESCRIPTOR_TEMPLATE},
            "map_popup": {"nodegroup_id": ASSOCIATED_HI_NODEGROUP_ID, "string_template": DESCRIPTOR_TEMPLATE},
            "description": {"nodegroup_id": ASSOCIATED_HI_NODEGROUP_ID, "string_template": DESCRIPTOR_TEMPLATE},
        }
    }

    graph = GraphModel.objects.filter(graphid=uuid.UUID(CONDITION_REPORT_GRAPH_ID)).first()
    if graph:
        FunctionXGraph.objects.update_or_create(
            id=uuid.UUID(CONDITION_REPORT_FXG_ID),
            defaults={
                "function_id": uuid.UUID(FUNCTION_ID),
                "graph_id": uuid.UUID(CONDITION_REPORT_GRAPH_ID),
                "config": descriptor_config,
            },
        )


def unregister_function(apps, schema_editor):
    Function = apps.get_model("models", "Function")
    FunctionXGraph = apps.get_model("models", "FunctionXGraph")
    FunctionXGraph.objects.filter(id=uuid.UUID(CONDITION_REPORT_FXG_ID)).delete()
    Function.objects.filter(functionid=uuid.UUID(FUNCTION_ID)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0006_enable_iiif_plugin"),
    ]

    operations = [
        migrations.RunPython(register_function, unregister_function),
    ]
