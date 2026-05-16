import logging
import uuid
from datetime import datetime

from arches.app.models.tile import Tile

logger = logging.getLogger(__name__)


def i18n_string(value: str) -> dict:
    """Wrap a plain string in Arches 8 i18n format."""
    return {"en": {"value": value, "direction": "ltr"}}


def parse_date(value: str):
    """
    Convert a date string to YYYY-MM-DD (the format Arches date nodes expect).
    Accepts DD/MM/YYYY, YYYY-MM-DD, and ISO 8601 timestamps.
    Returns None if the value is blank or unparseable.
    """
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning("Could not parse date value: %r", value)
    return None


def make_tile(
    nodegroup_id: str, data: dict, parent_tile_id: str = None, sortorder: int = 0
) -> Tile:
    return Tile(
        {
            "tileid": uuid.uuid4(),
            "nodegroup_id": nodegroup_id,
            "parenttile_id": parent_tile_id,
            "data": data,
            "sortorder": sortorder,
        }
    )
