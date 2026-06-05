import uuid

from django.db import migrations

# Arches System Settings resource + the "Project Extent" nodegroup/node.
# These IDs are stable across Arches installs (defined in the core
# Arches_System_Settings graph).
SYSTEM_SETTINGS_RESOURCE_ID = "a106c400-260c-11e7-a604-14109fd34195"
PROJECT_EXTENT_NODEGROUP_ID = "0e8fdef0-4148-11e7-8330-c4b301baab9f"
PROJECT_EXTENT_NODE_ID = "0e8ffbcf-4148-11e7-a95a-c4b301baab9f"

# Desired project extent. Edit these polygons to change the extent; this
# migration is what re-applies them on every `manage.py migrate` (i.e. on every
# DB reset via the docker entrypoint), so they survive a reset.
PROJECT_EXTENT_GEOMETRIES = [
    {
        "type": "Polygon",
        "coordinates": [
            [
                [137.23261329079463, -8.79508674957843],
                [137.41888846138266, -27.11343112264619],
                [141.51694221425907, -30.93991157206991],
                [157.443469299308, -29.247768543060047],
                [158.09543239635633, -11.346334286257019],
                [137.23261329079463, -8.79508674957843],
            ]
        ],
    },
]


def _feature_collection():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": uuid.uuid4().hex,
                "properties": {},
                "geometry": geometry,
            }
            for geometry in PROJECT_EXTENT_GEOMETRIES
        ],
    }


def set_project_extent(apps, schema_editor):
    from arches.app.models.models import TileModel

    tile, _created = TileModel.objects.get_or_create(
        nodegroup_id=PROJECT_EXTENT_NODEGROUP_ID,
        resourceinstance_id=SYSTEM_SETTINGS_RESOURCE_ID,
        defaults={"data": {}, "sortorder": 0},
    )
    data = tile.data or {}
    # semantic collector node carries no value
    data.setdefault(PROJECT_EXTENT_NODEGROUP_ID, None)
    data[PROJECT_EXTENT_NODE_ID] = _feature_collection()
    tile.data = data
    tile.save()


def noop(apps, schema_editor):
    # Forward-only: leave whatever extent is in place on reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("quartz", "0008_import_condition_report_graph"),
    ]

    operations = [
        migrations.RunPython(set_project_extent, noop),
    ]
