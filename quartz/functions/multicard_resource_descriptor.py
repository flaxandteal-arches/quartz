from arches.app.datatypes.datatypes import DataTypeFactory
from arches.app.functions.primary_descriptors import AbstractPrimaryDescriptorsFunction
from arches.app.models.system_settings import settings
from arches.app.models import models
import re

from django.utils.translation import get_language, gettext as _

# This duplicates the configuration declared in migration 0004,
# but on first package load, the function will be re-registered, because
# the .py file has not yet been placed in the destination folder.
# Re-registration will overwrite whatever the migration inserted.
details = {
    "functionid": "00b2d15a-fda0-4578-b79a-784e4138664b",
    "name": "Multi-card Resource Descriptor",
    "type": "primarydescriptors",
    "description": "Configure the name, description, and map popup of a resource",
    "defaultconfig": {
        "descriptor_types": {
            "name": {
                "nodegroup_id": "",
                "string_template": "",
            },
            "map_popup": {
                "nodegroup_id": "",
                "string_template": "",
            },
            "description": {
                "nodegroup_id": "",
                "string_template": "",
            },
        }
    },
    "classname": "MulticardResourceDescriptor",
    "component": "views/components/functions/multicard-resource-descriptor",
}


class MulticardResourceDescriptor(AbstractPrimaryDescriptorsFunction):
    """Updates multicard
    This implementation just fetches the calculated result from the db."""

    def get_primary_descriptor_from_nodes(
        self, resource, config, context=None, descriptor=None
    ):
        resource.get_descriptor_language(context)

        result = ""
        requested_language = context.get("language", None) if context else None

        lookup_language = requested_language or get_language() or settings.LANGUAGE_CODE
        datatype_factory = None
        result = config["string_template"]

        if (
            str(resource.graph_id) == "076f9381-7b00-11e9-8d6b-80000b44d1d9"
        ):  # heritage item graph
            node_aliases, result = extract_heritage_item_substrings(result, resource)
        else:
            node_aliases = extract_substrings(result)
        nodes = models.Node.objects.filter(
            alias__in=node_aliases, graph_id=resource.graph_id
        )
        for node in nodes:
            datatype_factory = DataTypeFactory()
            datatype = datatype_factory.get_instance(node.datatype)
            tile = (
                models.TileModel.objects.filter(
                    resourceinstance_id=resource.resourceinstanceid,
                    nodegroup_id=node.nodegroup_id,
                )
                .order_by("sortorder")
                .first()
            )
            if tile:
                value = datatype.get_display_value(tile, node, language=lookup_language)
            else:
                value = ""
            result = result.replace("<%s>" % node.alias, str(value))
        return result


def extract_substrings(template_string):
    pattern = r"<(.*?)>"
    substrings = re.findall(pattern, template_string)

    return substrings


def extract_heritage_item_substrings(template_string, resource):
    pattern = r"<(.*?)>"
    substrings = re.findall(pattern, template_string)

    if (
        "version" in substrings
        and resource.resource_instance_lifecycle_state.name == "Draft"
    ):
        substrings.remove("version")
        template_string = template_string.replace("<version>", "")

    return substrings, template_string
