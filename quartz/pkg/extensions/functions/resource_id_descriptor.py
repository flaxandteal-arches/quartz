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
        "Like Multi-card Resource Descriptor but supports <alias|id> placeholders "
        "that expand to the UUID of the first linked resource rather than its display name."
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

# Matches <alias> and <alias|id>
_PLACEHOLDER_RE = re.compile(r"<([^>|]+)(\|id)?>")


class ResourceIdDescriptor(AbstractPrimaryDescriptorsFunction):
    """
    Descriptor function that supports two placeholder forms in string_template:

      <alias>       — replaced with the node's display value (same as MulticardResourceDescriptor)
      <alias|id>    — replaced with the UUID of the first linked resource-instance(list) value;
                      falls back to display value for other datatypes
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
            alias, id_flag = match.group(1), match.group(2)
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

            if id_flag and tile:
                value = _extract_resource_id(tile, node)
            elif tile:
                datatype = datatype_factory.get_instance(node.datatype)
                value = datatype.get_display_value(tile, node, language=lookup_language) or ""
            else:
                value = ""

            result = result.replace(match.group(0), str(value), 1)

        return result or _("Undefined")


def _extract_resource_id(tile, node):
    """Return the first resourceId UUID from a resource-instance or resource-instance-list tile value."""
    raw = (tile.data or {}).get(str(node.nodeid))
    if not raw:
        return ""
    # resource-instance-list → list of dicts; resource-instance → single dict
    entry = raw[0] if isinstance(raw, list) else raw
    try:
        return str(uuid_module.UUID(entry["resourceId"]))
    except (KeyError, ValueError, TypeError):
        return ""
