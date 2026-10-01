#!/usr/bin/env bash
# Reload the Heritage Item Type list with comma categories built as parents.
set -euo pipefail
LIST_FILE=scripts/data_fixes/0002_heritage_item_type.xml

# Refuse if tiles point at items the new list drops; 0003 can't remap them.
python manage.py shell <<PY
import sys
import xml.etree.ElementTree as ET
from django.db import connection

root = ET.parse("$LIST_FILE").getroot()
list_id = root.find("{http://www.w3.org/2004/02/skos/core#}ConceptScheme").get(
    "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about"
).rsplit("/", 1)[-1]
kept_uris = [e.text for e in root.iter("{http://purl.org/dc/terms/}identifier")]
with connection.cursor() as cursor:
    cursor.execute(
        """
        SELECT count(*)
        FROM nodes n
        JOIN tiles t ON t.nodegroupid = n.nodegroupid
        CROSS JOIN LATERAL jsonb_array_elements(t.tiledata -> n.nodeid::text) AS e(value)
        JOIN arches_controlled_lists_listitem i
          ON i.list_id = %(list_id)s::uuid AND i.uri = e.value->>'uri'
        WHERE n.datatype = 'reference'
          AND n.config->>'controlledList' = %(list_id)s
          AND jsonb_typeof(t.tiledata -> n.nodeid::text) = 'array'
          AND NOT i.uri = ANY(%(kept_uris)s)
        """,
        {"list_id": list_id, "kept_uris": kept_uris},
    )
    stranded = cursor.fetchone()[0]
if stranded:
    sys.exit(f"{stranded} tile values point at items this list removes; not reloading it.")
print(f"No tile values point at removed items of list {list_id}.")
PY

python manage.py packages -o import_controlled_lists -s "$LIST_FILE" -ow overwrite
