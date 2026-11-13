"""Tests for the read-only embedded image metadata endpoint.

Run:
    python manage.py test tests.test_image_metadata_view --settings="tests.test_settings"
"""

import io
import os
import struct
import tempfile
import zlib
from http import HTTPStatus
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, override_settings
from django.urls import reverse
from PIL import Image

from arches.app.models import models
from quartz.views.image_metadata import (
    ImageMetadataView,
    RangedBlobReader,
    ranged_reader,
    read_fields,
    read_metadata,
)

from tests.base_test import ArchesTestCase


def make_image(fmt="JPEG", size=(8, 8), noise=False):
    exif = Image.Exif()
    exif[0x9C9B] = "Hall".encode("utf-16le") + b"\0\0"
    exif[0x9C9C] = "Front door".encode("utf-16le") + b"\0\0"
    exif[0x8298] = "Jane Doe"
    exif[0x013B] = "Some Artist"
    exif.get_ifd(0x8769)[0x9003] = "2020:05:17 10:30:00"
    exif.get_ifd(0x8825)[1] = "N"
    pixels = (
        os.urandom(size[0] * size[1] * 3) if noise else b"\0" * (size[0] * size[1] * 3)
    )
    out = io.BytesIO()
    Image.frombytes("RGB", size, pixels).save(out, fmt, exif=exif)
    return out.getvalue()


def png_with_late_title(title, side):
    """Noise PNG without EXIF, with a tEXt Title chunk placed after the pixel data."""
    out = io.BytesIO()
    Image.frombytes("RGB", (side, side), os.urandom(side * side * 3)).save(out, "PNG")
    data = out.getvalue()
    iend = data.rindex(b"IEND") - 4
    return data[:iend] + png_chunk(b"tEXt", b"Title\0" + title) + data[iend:]


def png_chunk(ctype, body):
    return (
        struct.pack(">I", len(body))
        + ctype
        + body
        + struct.pack(">I", zlib.crc32(ctype + body))
    )


class FakeBlob:
    def __init__(self, data):
        self.data = data
        self.fetched = 0

    def download_blob(self, offset, length):
        self.fetched += length
        return mock.Mock(readall=lambda: self.data[offset : offset + length])


def tiff_with_ifd_at_end(title=b"Hall\0", side=1200):
    """Greyscale TIFF whose only IFD (carrying ImageDescription) follows the pixel data."""
    pixels = side * side
    ifd_offset = 8 + pixels
    entries = [
        (256, 4, 1, side),
        (257, 4, 1, side),
        (258, 3, 1, 8),
        (259, 3, 1, 1),
        (262, 3, 1, 1),
        (270, 2, len(title), ifd_offset + 2 + 10 * 12 + 4),
        (273, 4, 1, 8),
        (277, 3, 1, 1),
        (278, 4, 1, side),
        (279, 4, 1, pixels),
    ]
    ifd = struct.pack("<H", len(entries))
    ifd += b"".join(struct.pack("<HHII", *entry) for entry in entries)
    return (
        b"II*\0"
        + struct.pack("<I", ifd_offset)
        + bytes(pixels)
        + ifd
        + b"\0\0\0\0"
        + title
    )


def read_ranged(data):
    blob = FakeBlob(data)
    return read_fields(ranged_reader(blob, len(data))), blob


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ImageMetadataTests(ArchesTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = User.objects.create_user("im_plain", password="x")
        cls.superuser = User.objects.create_superuser(
            "im_super", email="", password="x"
        )

    def setUp(self):
        read_metadata.cache_clear()

    def make_file(self, data, name="photo.jpg"):
        return models.File.objects.create(path=ContentFile(data, name=name))

    def get(self, file, user=None):
        if user:
            self.client.force_login(user)
        return self.client.get(reverse("image_metadata", args=[file.pk]))

    def test_jpeg_returns_only_allowlisted_fields_in_order(self):
        response = self.get(self.make_file(make_image()), self.superuser)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(
            [(f["label"], f["value"]) for f in response.json()["fields"]],
            [
                ("Title", "Hall"),
                ("Date taken", "2020-05-17 10:30:00"),
                ("Comment", "Front door"),
            ],
        )

    def test_non_image_returns_empty_fields(self):
        response = self.get(
            self.make_file(b"%PDF-1.4 not an image", "doc.pdf"), self.superuser
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json()["fields"], [])

    def test_unknown_file_is_404(self):
        self.client.force_login(self.superuser)
        url = reverse("image_metadata", args=["11111111-1111-1111-1111-111111111111"])
        self.assertEqual(self.client.get(url).status_code, HTTPStatus.NOT_FOUND)

    def test_anonymous_is_403(self):
        self.client.logout()
        response = self.get(self.make_file(make_image()))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

    def test_logged_in_non_superuser_is_allowed(self):
        response = self.get(self.make_file(make_image()), self.user)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    @override_settings(RESTRICT_MEDIA_ACCESS=True)
    def test_denied_without_read_nodegroup(self):
        file = self.make_file(make_image())
        with (
            mock.patch.object(models.File, "tile", mock.Mock(), create=True),
            mock.patch.object(User, "has_perm", return_value=False),
        ):
            request = RequestFactory().get("/")
            request.user = self.user
            with self.assertRaises(PermissionDenied):
                ImageMetadataView.as_view()(request, fileid=file.pk)

    def test_large_jpeg_fetches_only_the_header(self):
        data = make_image(size=(1500, 1500), noise=True)
        self.assertGreater(len(data), 1024 * 1024)
        fields, blob = read_ranged(data)
        self.assertEqual(fields[0]["value"], "Hall")
        self.assertLess(blob.fetched, len(data) / 10)

    def test_tiff_with_ifd_at_end_fetches_few_bytes(self):
        data = tiff_with_ifd_at_end()
        self.assertGreater(struct.unpack("<I", data[4:8])[0], len(data) / 2)
        fields, blob = read_ranged(data)
        self.assertEqual(fields[0]["value"], "Hall")
        self.assertLess(blob.fetched, len(data) / 10)

    def test_png_text_after_pixel_data_is_read_without_decoding(self):
        data = png_with_late_title(b"Boiler room", 700)
        with mock.patch.object(
            Image.Image, "load", side_effect=AssertionError("decoded")
        ):
            fields, blob = read_ranged(data)
        self.assertEqual(
            fields[0], {"key": "title", "label": "Title", "value": "Boiler room"}
        )
        self.assertLess(blob.fetched, len(data) / 2)

    def test_fetch_limit_stops_reading(self):
        data = png_with_late_title(b"Late", 1500)
        with mock.patch("quartz.views.image_metadata.MAX_FETCH_BYTES", 64 * 1024):
            self.assertEqual(read_ranged(data)[0], [])

    def test_decompression_bomb_returns_empty_fields(self):
        data = make_image()
        with mock.patch.object(
            Image, "open", side_effect=Image.DecompressionBombError("big")
        ):
            self.assertEqual(read_ranged(data)[0], [])

    def test_reader_matches_plain_file_reads(self):
        data = os.urandom(50000)
        reader = RangedBlobReader(FakeBlob(data), len(data))
        reader.seek(-100, io.SEEK_END)
        self.assertEqual(reader.read(), data[-100:])
        reader.seek(20000)
        self.assertEqual(reader.read(100), data[20000:20100])
