"""Integration tests for the public Heritage Item export.

Exercises the genuinely new behaviour of quartz.utils.public_export.export_resources:
  * nodegroup read-permission filtering (tiles whose nodegroup the export user
    cannot read are dropped from the output),
  * the related-resource inclusion pass (visible Digital Objects are exported as
    full resources; non-visible ones are not),
  * relation filtering by target visibility,
  * per-resource __scopes assignment.

Run (same invocation CI uses):
    python manage.py test tests.test_public_export --settings="tests.test_settings"

Self-contained: loads the real Heritage Item + Digital Object graphs from
tests/fixtures/resource_graphs, seeds the visibility controlled list, and builds
a small resource graph by hand — it does NOT rely on a loaded package.
"""

import json
import os
import tempfile

from django.contrib.auth.models import User
from django.core import management

from arches.app.models import models
from arches.app.models.graph import Graph
from arches.app.models.resource import Resource
from arches.app.models.tile import Tile
from arches.app.utils.betterJSONSerializer import JSONDeserializer
from arches.app.utils.data_management.resource_graphs.importer import (
    import_graph as ResourceGraphImporter,
)
from arches.app.utils.permission_backend import assign_perm
from django.test.utils import captured_stdout

from arches_controlled_lists.models import List, ListItem, ListItemValue

from tests.base_test import ArchesTestCase

from quartz.utils.public_export import (
    VISIBILITY_LIST_ID,
    export_resources,
    get_visibility_nodes,
    get_visibility_uris,
)

HI_GRAPH_ID = "076f9381-7b00-11e9-8d6b-80000b44d1d9"
DO_GRAPH_ID = "a535a235-8481-11ea-a6b9-f875a44e0e11"
PUBLIC_URI = "https://example.org/vis/public"
STAGING_URI = "https://example.org/vis/staging"


class PublicExportIntegrationTests(ArchesTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        # 0. Heritage Item references quartz's Multi-card Resource Descriptor
        # function, normally registered by package load; a fresh test DB only
        # has the migration-registered functions, so register it here.
        with captured_stdout():
            management.call_command(
                "fn",
                "register",
                source="quartz/functions/multicard_resource_descriptor.py",
            )

        # 1. Load the real Heritage Item + Digital Object graphs (they carry the
        #    'versioning' / heritage_item_visibility nodes the export relies on).
        for stem in ("Heritage_Item", "Digital_Object"):
            path = os.path.join("tests/fixtures/resource_graphs", f"{stem}.json")
            with captured_stdout():
                with open(path) as f:
                    archesfile = JSONDeserializer().deserialize(f)
                errors, _ = ResourceGraphImporter(
                    archesfile["graph"], overwrite_graphs=True
                )
            if errors:
                raise RuntimeError(f"Graph import failed for {stem}: {errors}")

        cls.user = User.objects.create(username="pe_test_user")
        for graph_id in (HI_GRAPH_ID, DO_GRAPH_ID):
            Graph.objects.get(pk=graph_id).publish(user=cls.user)

        # 2. Seed the visibility controlled list (Public / Staging) the graph
        #    visibility nodes point at by UUID.
        vis_list, _ = List.objects.get_or_create(
            pk=VISIBILITY_LIST_ID, defaults={"name": "Heritage Item Visibility"}
        )
        cls.vis_labels = {}
        for i, (uri, label) in enumerate(
            [(PUBLIC_URI, "Public"), (STAGING_URI, "Staging")]
        ):
            item = ListItem.objects.create(uri=uri, list=vis_list, sortorder=i)
            cls.vis_labels[uri] = ListItemValue.objects.create(
                list_item=item,
                value=label,
                valuetype_id="prefLabel",
                language_id="en",
            )

        # 3. Resolve the nodegroups we will populate / permission.
        cls.hi_desc_ng = cls._ng(HI_GRAPH_ID, "descriptions")
        cls.hi_denied_ng = cls._ng(HI_GRAPH_ID, "spatial_metadata_descriptions")
        cls.hi_versioning_ng = cls._ng(HI_GRAPH_ID, "versioning")
        cls.do_names_ng = cls._ng(DO_GRAPH_ID, "names")
        cls.do_versioning_ng = cls._ng(DO_GRAPH_ID, "versioning")
        cls.do_vis_node_id = str(
            models.Node.objects.get(
                graph_id=DO_GRAPH_ID,
                alias="heritage_item_visibility",
                source_identifier__isnull=True,
            ).nodeid
        )

        # 4. Build resources:
        #    - HI source: a granted tile (descriptions), a denied tile
        #      (spatial_metadata_descriptions), and a denied visibility tile.
        cls.hi = Resource(graph_id=HI_GRAPH_ID)
        cls.hi.tiles.append(Tile(data={}, nodegroup_id=str(cls.hi_desc_ng)))
        cls.hi.tiles.append(Tile(data={}, nodegroup_id=str(cls.hi_denied_ng)))
        cls.hi.save(index=False)

        #    - DO public target: a visibility tile = Public (so it is selected)
        #      plus a content tile.
        cls.do_public = Resource(graph_id=DO_GRAPH_ID)
        cls.do_public.tiles.append(Tile(data={}, nodegroup_id=str(cls.do_names_ng)))
        cls.do_public.tiles.append(
            Tile(
                data={
                    cls.do_vis_node_id: [
                        {
                            "uri": PUBLIC_URI,
                            "list_id": str(VISIBILITY_LIST_ID),
                            "labels": [
                                {
                                    "id": str(cls.vis_labels[PUBLIC_URI].pk),
                                    "value": "Public",
                                    "language": "en",
                                    "valuetype": "prefLabel",
                                }
                            ],
                        }
                    ]
                },
                nodegroup_id=str(cls.do_versioning_ng),
            )
        )
        cls.do_public.save(index=False)

        #    - DO hidden target: no visibility tile -> not selected.
        cls.do_hidden = Resource(graph_id=DO_GRAPH_ID)
        cls.do_hidden.tiles.append(Tile(data={}, nodegroup_id=str(cls.do_names_ng)))
        cls.do_hidden.save(index=False)

        # 5. Relations HI -> each DO, backed by the granted HI tile.
        rel_tile = cls.hi.tiles[0]
        rel_node = models.Node.objects.filter(nodegroup_id=cls.hi_desc_ng).first()
        for target in (cls.do_public, cls.do_hidden):
            models.ResourceXResource.objects.create(
                from_resource_id=cls.hi.pk,
                to_resource_id=target.pk,
                from_resource_graph_id=HI_GRAPH_ID,
                to_resource_graph_id=DO_GRAPH_ID,
                relationshiptype="",
                tile_id=rel_tile.tileid,
                node_id=rel_node.nodeid,
            )

        # 6. Permission the export user: deny the sensitive nodegroups; the rest
        #    stay readable (default-allow). Visibility detection is independent
        #    of these grants, so denying 'versioning' does not hide the DO.
        for ng in (cls.hi_denied_ng, cls.hi_versioning_ng, cls.do_versioning_ng):
            assign_perm(
                "no_access_to_nodegroup",
                cls.user,
                models.NodeGroup.objects.get(pk=ng),
            )

    @staticmethod
    def _ng(graph_id, alias):
        return models.Node.objects.get(
            graph_id=graph_id, alias=alias, source_identifier__isnull=True
        ).nodegroup_id

    # ------------------------------------------------------------------ #

    def _run_export(self):
        out_dir = tempfile.mkdtemp()
        result, diagnostics = export_resources(
            [self.hi.pk],
            output_dir=out_dir,
            visibility_nodes=get_visibility_nodes(),
            visibility_uris=get_visibility_uris(["Public", "Staging"]),
            resource_labels={str(self.hi.pk): "public"},
            user=self.user,
            indent=2,
        )
        with open(os.path.join(result, "business_data", "Heritage_Item.json")) as f:
            export = json.load(f)
        return export, diagnostics

    def _resource(self, export, resource_id):
        for rd in export["business_data"]["resources"]:
            if rd["resourceinstance"]["resourceinstanceid"] == str(resource_id):
                return rd
        return None

    # ------------------------------------------------------------------ #

    def test_denied_nodegroups_are_dropped(self):
        export, _ = self._run_export()
        hi = self._resource(export, self.hi.pk)
        self.assertIsNotNone(hi, "Heritage Item should be exported")
        ng_ids = {t["nodegroup_id"] for t in hi["tiles"]}
        self.assertIn(str(self.hi_desc_ng), ng_ids, "granted nodegroup kept")
        self.assertNotIn(str(self.hi_denied_ng), ng_ids, "no_access nodegroup dropped")
        self.assertNotIn(
            str(self.hi_versioning_ng), ng_ids, "versioning (denied) dropped"
        )

    def test_visible_digital_object_included_and_hidden_excluded(self):
        export, diagnostics = self._run_export()
        self.assertIsNotNone(
            self._resource(export, self.do_public.pk),
            "Public Digital Object should be included as a full resource",
        )
        self.assertIsNone(
            self._resource(export, self.do_hidden.pk),
            "Non-visible Digital Object must NOT be included",
        )
        self.assertEqual(diagnostics["included_target_resources"], 1)

    def test_relations_filtered_by_visibility(self):
        export, _ = self._run_export()
        targets = {r["to_resource"] for r in export["business_data"]["relations"]}
        self.assertIn(str(self.do_public.pk), targets)
        self.assertNotIn(str(self.do_hidden.pk), targets)

    def test_scopes_assigned(self):
        export, _ = self._run_export()
        hi = self._resource(export, self.hi.pk)
        self.assertEqual(hi.get("__scopes"), ["public"])
