#!/usr/bin/env bash
# Give Artefact its own lists; it was sharing Heritage Item's, which lack its labels.
set -euo pipefail

for list in description_roles point_sources feature_types; do
    python manage.py packages -o import_controlled_lists \
        -s "scripts/data_fixes/0003_artefact_${list}.xml" -ow overwrite
done

python manage.py shell <<'PY'
from arches.app.models.graph import Graph
from arches.app.models.models import Node

ARTEFACT_GRAPHID = "343cc20c-2c5a-11e8-90fa-0242ac120005"
NODE_LISTS = {
    "c30977b1-991e-11ea-b259-f875a44e0e11": "c6d288e2-9275-5f09-89a2-96d740759ea2",  # description type
    "f7ccef5f-f447-11eb-8b98-a87eeabdefba": "e8eab2c4-ecf0-5ce4-a26d-fc06c9d1ae71",  # capture scale
    "f7cc8c75-f447-11eb-953a-a87eeabdefba": "dd13d08d-c321-55a5-92d3-3bc6bcc8bf67",  # feature shape
}

graph = Graph.objects.get(pk=ARTEFACT_GRAPHID, source_identifier__isnull=True)
for nodeid, list_id in NODE_LISTS.items():
    for node in Node.objects.filter(pk=nodeid) | Node.objects.filter(source_identifier_id=nodeid):
        node.config["controlledList"] = list_id
        node.save()
graph.publish()
print("Repointed Artefact nodes and republished the graph.")
PY
