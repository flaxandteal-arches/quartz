import collections
import functools
import io
import os
import re
import struct
import zlib

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_control
from django.views.generic import View
from PIL import Image

from arches.app.models import models
from arches.app.utils.response import JSONResponse

BLOCK_SIZE = 16 * 1024
CACHED_BLOCKS = 8
MAX_FETCH_BYTES = 2 * 1024 * 1024
MAX_CHUNK_BYTES = 1024 * 1024
MAX_VALUE_LENGTH = 500

EXIF_IFD = 0x8769
IMAGE_DESCRIPTION, DATE_TAKEN, USER_COMMENT = 0x010E, 0x9003, 0x9286
XP_TITLE, XP_COMMENT, XP_SUBJECT = 0x9C9B, 0x9C9C, 0x9C9F
XP_TAGS = {XP_TITLE, XP_COMMENT, XP_SUBJECT}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_TEXT_CHUNKS = {b"tEXt", b"zTXt", b"iTXt", b"eXIf"}

# The only fields the endpoint returns, in display order. To add one, add a line:
# (key, label, [(source, name), ...]); the first non-empty source wins. Sources:
# "exif" base-IFD tag, "exif_ifd" Exif-IFD tag, "xmp" XMP property, "text" PNG text chunk.
METADATA_FIELDS = [
    (
        "title",
        _("Title"),
        [
            ("exif", XP_TITLE),
            ("xmp", "title"),
            ("exif", IMAGE_DESCRIPTION),
            ("text", "Title"),
        ],
    ),
    ("subject", _("Subject"), [("exif", XP_SUBJECT), ("text", "Subject")]),
    (
        "date_taken",
        _("Date taken"),
        [
            ("exif_ifd", DATE_TAKEN),
            ("xmp", "DateTimeOriginal"),
            ("xmp", "DateCreated"),
            ("text", "Creation Time"),
        ],
    ),
    (
        "comment",
        _("Comment"),
        [
            ("exif", XP_COMMENT),
            ("exif_ifd", USER_COMMENT),
            ("xmp", "description"),
            ("text", "Comment"),
            ("text", "Description"),
        ],
    ),
]


class RangedBlobReader(io.RawIOBase):
    """Seekable read-only view of an Azure blob that fetches only the blocks Pillow touches."""

    def __init__(self, blob, size):
        self.blob = blob
        self.size = size
        self.pos = 0
        self.fetched = 0
        self.blocks = collections.OrderedDict()

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = max(base + offset, 0)
        return self.pos

    def _block(self, index):
        if index in self.blocks:
            self.blocks.move_to_end(index)
            return self.blocks[index]
        start = index * BLOCK_SIZE
        length = min(BLOCK_SIZE, self.size - start)
        if self.fetched + length > MAX_FETCH_BYTES:
            raise OSError("metadata fetch limit reached")
        self.fetched += length
        data = self.blob.download_blob(offset=start, length=length).readall()
        self.blocks[index] = data
        if len(self.blocks) > CACHED_BLOCKS:
            self.blocks.popitem(last=False)
        return data

    def readinto(self, buffer):
        want = min(len(buffer), self.size - self.pos)
        if want <= 0:
            return 0
        index, skip = divmod(self.pos, BLOCK_SIZE)
        chunk = self._block(index)[skip : skip + want]
        buffer[: len(chunk)] = chunk
        self.pos += len(chunk)
        return len(chunk)


def ranged_reader(blob, size):
    return io.BufferedReader(RangedBlobReader(blob, size))


def open_file(file):
    storage, name = file.path.storage, file.path.name
    if not hasattr(storage, "client"):
        return storage.open(name, "rb")
    blob = storage.client.get_blob_client(storage._get_valid_path(name))
    return ranged_reader(blob, blob.get_blob_properties().size)


class Sources:
    def __init__(self, exif, xmp=None, text=None):
        self.exif = exif
        self.xmp = xmp or {}
        self.text = text or {}


def _first_string(value):
    """XMP alt-lang values nest dicts and lists; returns the first string inside."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _first_string(item)
            if found:
                return found
    return ""


def _xmp_property(xmp, name):
    node = xmp
    for key in ("xmpmeta", "RDF", "Description", name):
        if isinstance(node, list):
            node = node[0] if node else {}
        if not isinstance(node, dict):
            return ""
        node = node.get(key, {})
    return _first_string(node)


def _decode(tag, value):
    if isinstance(value, (tuple, list)):
        value = bytes(value)
    if tag in XP_TAGS and isinstance(value, bytes):
        return value.decode("utf-16-le", errors="replace")
    if tag == USER_COMMENT and isinstance(value, bytes):
        charset = "utf-16-le" if value.startswith(b"UNICODE") else "utf-8"
        return value[8:].decode(charset, errors="replace")
    return value if isinstance(value, str) else ""


def _lookup(sources, source, name):
    if source == "exif":
        return _decode(name, sources.exif.get(name))
    if source == "exif_ifd":
        return _decode(name, sources.exif.get_ifd(EXIF_IFD).get(name))
    if source == "xmp":
        return _xmp_property(sources.xmp, name)
    return sources.text.get(name, "")


def _fields(sources):
    fields = []
    for key, label, candidates in METADATA_FIELDS:
        value = ""
        for source, name in candidates:
            value = _lookup(sources, source, name).strip().strip("\x00").strip()
            if value:
                break
        if key == "date_taken":
            value = re.sub(r"^(\d{4}):(\d\d):(\d\d)", r"\1-\2-\3", value)
        if value:
            fields.append(
                {"key": key, "label": str(label), "value": value[:MAX_VALUE_LENGTH]}
            )
    return fields


def _inflate(data):
    return zlib.decompressobj().decompress(data, MAX_CHUNK_BYTES)


def _png_text(ctype, body, text, exif):
    if ctype == b"eXIf":
        exif.load(body)
        return
    key, _sep, rest = body.partition(b"\0")
    if ctype == b"tEXt":
        text[key.decode("latin-1")] = rest.decode("latin-1")
    elif ctype == b"zTXt":
        text[key.decode("latin-1")] = _inflate(rest[1:]).decode("latin-1")
    else:
        compressed = rest[0]
        _lang, _sep, rest = rest[2:].partition(b"\0")
        _translated, _sep, value = rest.partition(b"\0")
        text[key.decode("utf-8", "replace")] = (
            _inflate(value) if compressed else value
        ).decode("utf-8", "replace")


def _png_sources(fp):
    """Walks PNG chunks, reading only text/EXIF ones and seeking past the pixel data."""
    text, exif = {}, Image.Exif()
    fp.seek(len(PNG_SIGNATURE))
    try:
        while True:
            header = fp.read(8)
            if len(header) < 8:
                break
            length, ctype = struct.unpack(">I4s", header)
            if ctype == b"IEND":
                break
            if ctype in PNG_TEXT_CHUNKS and length <= MAX_CHUNK_BYTES:
                _png_text(ctype, fp.read(length), text, exif)
                fp.seek(4, io.SEEK_CUR)
            else:
                fp.seek(length + 4, io.SEEK_CUR)
    except Exception:
        pass
    return Sources(exif, text=text)


def read_fields(fp):
    """Returns the allowlisted fields found in an image file object; never loads pixels."""
    try:
        if fp.read(len(PNG_SIGNATURE)) == PNG_SIGNATURE:
            return _fields(_png_sources(fp))
        fp.seek(0)
        with Image.open(fp) as im:
            try:
                xmp = im.getxmp()
            except Exception:
                xmp = {}
            return _fields(Sources(im.getexif(), xmp))
    except Exception:
        return []


@functools.lru_cache(maxsize=1024)
def read_metadata(file_id):
    file = models.File.objects.get(pk=file_id)
    with open_file(file) as fp:
        fields = read_fields(fp)
    return {
        "file_id": file_id,
        "name": os.path.basename(file.path.name),
        "fields": fields,
    }


class ImageMetadataView(View):
    @method_decorator(cache_control(private=True, max_age=86400))
    def get(self, request, fileid):
        if request.user.username in ("", "anonymous"):
            raise PermissionDenied

        try:
            file = models.File.objects.get(pk=fileid)
        except models.File.DoesNotExist:
            raise Http404

        if settings.RESTRICT_MEDIA_ACCESS:
            try:
                nodegroup = file.tile.nodegroup
            except models.NodeGroup.DoesNotExist:
                raise PermissionDenied
            if request.user.has_perm("read_nodegroup", nodegroup) is False:
                raise PermissionDenied

        return JSONResponse(read_metadata(str(fileid)))
