import datetime

from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.generic import View

from arches.app.models import models
from arches.app.models.resource import Resource
from arches.app.utils.betterJSONSerializer import JSONDeserializer
from arches.app.utils.decorators import can_edit_resource_instance, group_required
from arches.app.utils.response import JSONResponse


@method_decorator(can_edit_resource_instance, name="dispatch")
class ReorderTilesView(View):
    """Replaces core reorder_tiles, which runs a full Tile.save() per tile and so
    reindexes the whole resource once for every tile in the card."""

    @method_decorator(group_required("Resource Editor", raise_exception=True))
    def post(self, request):
        data = JSONDeserializer().deserialize(request.body)
        tileids = [tile["tileid"] for tile in data.get("tiles", []) if tile.get("tileid")]
        tiles = models.TileModel.objects.filter(pk__in=tileids).select_related("nodegroup")
        tile_lookup = {str(tile.pk): tile for tile in tiles}

        can_write = {}
        reordered = []
        for tileid in tileids:
            tile = tile_lookup.get(str(tileid))
            if tile is None:
                continue
            if tile.nodegroup_id not in can_write:
                can_write[tile.nodegroup_id] = request.user.has_perm(
                    "write_nodegroup", tile.nodegroup
                )
            if can_write[tile.nodegroup_id]:
                tile.sortorder = len(reordered)
                reordered.append(tile)

        if not reordered:
            return JSONResponse({"reordered": 0})

        touched = {(tile.resourceinstance_id, tile.nodegroup_id) for tile in reordered}
        resources = Resource.objects.in_bulk({resourceid for resourceid, _ in touched})

        with transaction.atomic():
            models.TileModel.objects.bulk_update(reordered, ["sortorder"])
            for resourceid, nodegroupid in touched:
                resource = resources[resourceid]
                resource.save_descriptors()
                self.log_reorder(request.user, resource, nodegroupid, len(reordered))

        for resource in resources.values():
            resource.index()

        return JSONResponse({"reordered": len(reordered)})

    @staticmethod
    def log_reorder(user, resource, nodegroupid, count):
        # 'tile edit' with empty values: the history page throws on unknown edit types or value keys
        models.EditLog.objects.create(
            resourceclassid=str(resource.graph_id),
            resourceinstanceid=str(resource.resourceinstanceid),
            nodegroupid=str(nodegroupid),
            edittype="tile edit",
            oldvalue={},
            newvalue={},
            note=f"Reordered {count} tiles",
            resourcedisplayname=resource.displayname(),
            timestamp=datetime.datetime.now(),
            userid=str(user.id),
            user_email=user.email,
            user_firstname=user.first_name,
            user_lastname=user.last_name,
            user_username=user.username,
        )
