# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Tests for the atrope cache manager and image files."""

import hashlib
import os
import pathlib

import fixtures
from oslo_config import cfg

from atrope import cache, image
from atrope.tests import base

CONF = cfg.CONF


class FakeImage(image.BaseImage):
    """An image that 'downloads' locally generated contents."""

    contents = b"image contents"

    def __init__(self, identifier):
        super().__init__(None)
        self.identifier = identifier
        self.hash = f"sha512:{hashlib.sha512(self.contents).hexdigest()}"
        self.format = "qcow2"

    def download_and_verify(self, location):
        with open(location, "wb") as f:
            f.write(self.contents)
        self.verify_checksum(location=location)


class FakeList:
    """An image list with the attributes used by the cache manager."""

    def __init__(
        self,
        name,
        images,
        enabled=True,
        trusted=True,
        verified=True,
        expired=False,
    ):
        self.name = name
        self.enabled = enabled
        self.trusted = trusted
        self.verified = verified
        self.expired = expired
        self.images = images

    def get_subscribed_images(self):
        return self.images


class CacheManagerTestCase(base.TestCase):
    def setUp(self):
        super().setUp()
        self.cache_dir = self.useFixture(fixtures.TempDir()).path
        CONF.set_override("path", self.cache_dir, group="cache")
        self.addCleanup(CONF.clear_override, "path", group="cache")

    def _sync(self, images, name="list", **kwargs):
        lst = FakeList(name, images, **kwargs)
        manager = cache.CacheManager()
        manager.sync_one(lst)
        return manager

    def _images_dir(self, name="list"):
        return pathlib.Path(self.cache_dir) / name / "images"

    def test_image_is_downloaded_and_kept(self):
        self._sync([FakeImage("image")])

        imgdir = self._images_dir()
        self.assertTrue((imgdir / "image").exists())

        # a new sync keeps the image in the cache
        self._sync([FakeImage("image")])
        self.assertTrue((imgdir / "image").exists())

    def test_converted_images_are_kept(self):
        self._sync([FakeImage("image")])

        imgdir = self._images_dir()
        original = imgdir / "image"
        # simulate a conversion made by a dispatcher (e.g. qcow2 -> raw)
        converted = imgdir / "image.raw"
        converted.write_bytes(b"converted contents")
        self.assertTrue(original.exists())

        # a new sync must not remove the converted image
        self._sync([FakeImage("image")])
        self.assertTrue(original.exists())
        self.assertTrue(converted.exists())

    def test_converted_images_removed_when_not_subscribed(self):
        self._sync([FakeImage("image")])

        imgdir = self._images_dir()
        converted = imgdir / "image.raw"
        converted.write_bytes(b"converted contents")

        # the image is not subscribed anymore, everything is removed
        self._sync([])
        self.assertFalse((imgdir / "image").exists())
        self.assertFalse(converted.exists())

    def test_disabled_list_removes_images(self):
        self._sync([FakeImage("image")])

        imgdir = self._images_dir()
        converted = imgdir / "image.raw"
        converted.write_bytes(b"converted contents")

        self._sync([FakeImage("image")], enabled=False)
        self.assertFalse(imgdir.exists())

    def test_untrusted_list_removes_images(self):
        self._sync([FakeImage("image")])

        imgdir = self._images_dir()
        converted = imgdir / "image.raw"
        converted.write_bytes(b"converted contents")

        self._sync([FakeImage("image")], trusted=False)
        self.assertFalse(imgdir.exists())


class ImageFilesTestCase(base.TestCase):
    def setUp(self):
        super().setUp()
        self.dest = self.useFixture(fixtures.TempDir()).path

    def test_download_tracks_converted_images(self):
        location = os.path.join(self.dest, "image")
        converted = os.path.join(self.dest, "image.raw")
        with open(location, "wb") as f:
            f.write(FakeImage.contents)
        with open(converted, "wb") as f:
            f.write(b"converted contents")

        img = FakeImage("image")
        img.download(self.dest)

        self.assertEqual(location, img.location)
        self.assertEqual([location, converted], img.locations)

    def test_stale_converted_images_are_removed_on_redownload(self):
        location = os.path.join(self.dest, "image")
        converted = os.path.join(self.dest, "image.raw")
        # image in the cache with different contents
        with open(location, "wb") as f:
            f.write(b"stale contents")
        with open(converted, "wb") as f:
            f.write(b"converted from stale contents")

        img = FakeImage("image")
        img.download(self.dest)

        # the image has been downloaded again, the converted image does
        # not match the new contents and is removed
        self.assertFalse(os.path.exists(converted))
        self.assertEqual([location], img.locations)

    def test_convert_appends_location_once(self):
        location = os.path.join(self.dest, "image")
        converted = f"{location}.raw"
        with open(location, "wb") as f:
            f.write(FakeImage.contents)
        with open(converted, "wb") as f:
            f.write(b"converted contents")

        img = FakeImage("image")
        img.download(self.dest)
        # the conversion already exists, 'convert' must not add it
        # to the image locations again
        _, fd = img.convert(["raw"], mode="rb")
        fd.close()

        self.assertEqual([location, converted], img.locations)
