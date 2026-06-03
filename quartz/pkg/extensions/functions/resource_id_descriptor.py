import re
import uuid as uuid_module

from arches.app.datatypes.datatypes import DataTypeFactory
from arches.app.functions.primary_descriptors import AbstractPrimaryDescriptorsFunction
from arches.app.models.system_settings import settings
from arches.app.models import models

from django.utils.translation import get_language, gettext as _

details = {
    "functionid": "e7d7fd2a-973a-4b2c-8c6e-bd2238d7be70",
    "name": "Resource ID Descriptor",
    "type": "primarydescriptors",
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
    "component": "views/components/functions/multicard-resource-descriptor",
}

# Matches <alias>, <alias|id>, and <alias|nodealias>
_PLACEHOLDER_RE = re.compile(r"<([^>|]+)(\|[^>]+)?>")


class ResourceIdDescriptor(AbstractPrimaryDescriptorsFunction):
    """
    Descriptor function that supports three placeholder forms in string_template:

      <alias>             - replaced with the node's display value
      <alias|id>          - replaced with the UUID of the first linked resource instance
      <alias|nodealias>   - replaced with the value of <nodealias> on the linked resource
    """

    def get_primary_descriptor_from_nodes(
        self, resource, config, context=None, descriptor=None
    ):
        requested_language = context.get("language", None) if context else None
        lookup_language = requested_language or get_language() or settings.LANGUAGE_CODE

        template = config["string_template"]
        aliases = {m.group(1) for m in _PLACEHOLDER_RE.finditer(template)}

        nodes = {
            node.alias: node
            for node in models.Node.objects.filter(
                alias__in=aliases, graph_id=resource.graph_id
            )
        }

        datatype_factory = DataTypeFactory()
        result = template

        for match in _PLACEHOLDER_RE.finditer(template):
            alias, flag = match.group(1), match.group(2)
            node = nodes.get(alias)
            if node is None:
                continue

            tile = (
                models.TileModel.objects.filter(
                    resourceinstance_id=resource.resourceinstanceid,
                    nodegroup_id=node.nodegroup_id,
                )
                .order_by("sortorder")
                .first()
            )

            if flag == "|id" and tile:
                value = _extract_resource_id(tile, node)
            elif flag and flag != "|id" and tile:
                target_alias = flag[1:]  # strip leading |
                value = _extract_linked_node_value(
                    tile, node, target_alias, datatype_factory, lookup_language
                )
            elif tile:
                datatype = datatype_factory.get_instance(node.datatype)
                value = datatype.get_display_value(tile, node, language=lookup_language) or ""
            else:
                value = ""

            result = result.replace(match.group(0), str(value), 1)

        return result or _("Undefined")


def _extract_resource_id(tile, node):
    """Return the first resourceId from a resource-instance or resource-instance-list tile value."""
    raw = (tile.data or {}).get(str(node.nodeid))
    if not raw:
        return ""
    # resource-instance-list → list of dicts; resource-instance → single dict
    entry = raw[0] if isinstance(raw, list) else raw
    try:
        return str(uuid_module.UUID(entry["resourceId"]))
    except (KeyError, ValueError, TypeError):
        return ""


def _extract_linked_node_value(tile, node, target_alias, datatype_factory, language):
    """Follow a resource-instance link and return the display value of target_alias on that resource."""
    resource_id = _extract_resource_id(tile, node)
    if not resource_id:
        return ""
    try:
        linked_resource = models.ResourceInstance.objects.get(pk=resource_id)
    except models.ResourceInstance.DoesNotExist:
        return ""
    try:
        target_node = models.Node.objects.get(
            alias=target_alias, graph_id=linked_resource.graph_id
        )
    except models.Node.DoesNotExist:
        return ""
    linked_tile = (
        models.TileModel.objects.filter(
            resourceinstance_id=resource_id,
            nodegroup_id=target_node.nodegroup_id,
        )
        .order_by("sortorder")
        .first()
    )
    if not linked_tile:
        return ""
    datatype = datatype_factory.get_instance(target_node.datatype)
    return datatype.get_display_value(linked_tile, target_node, language=language) or ""
