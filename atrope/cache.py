# Copyright 2014 Alvaro Lopez Garcia
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import pathlib

from oslo_config import cfg
from oslo_log import log

from atrope import exception, paths, utils

opts = [
    cfg.StrOpt(
        "path",
        default=paths.state_path_def("lists"),
        help="Where instances are stored on disk",
    ),
]

CONF = cfg.CONF
CONF.register_opts(opts, group="cache")

LOG = log.getLogger(__name__)


class CacheManager:
    """Manage the local cache of downloaded images.

    The cache directory holds, for every image list, the files
    downloaded from the subscribed images, together with the images
    converted from them by the dispatchers (e.g. a qcow2 image
    converted into raw, stored next to the original image as
    'image.qcow2.raw').

    During a sync every file that does not belong to an image of one
    of the enabled, verified lists is removed from the cache. Files
    belonging to a valid image (both the downloaded image and any
    image already converted from it) are kept, so converted images do
    not need to be generated again on every sync.
    """

    def __init__(self):
        self.path = pathlib.Path(CONF.cache.path)
        utils.makedirs(self.path)
        self._valid_paths = {self.path}

    def _download_list(self, lst):
        LOG.info(f"Syncing list with ID '{lst.name}'")
        if not lst.enabled:
            LOG.info(
                f"List '{lst.name}' is disabled, images will be " "marked for removal"
            )
            return

        LOG.info(
            f"List '{lst.name}' is enabled, checking if downloaded "
            "images are valid"
        )
        basedir = self.path / lst.name
        imgdir = basedir / "images"
        if not (lst.trusted and lst.verified and not lst.expired):
            return

        utils.makedirs(imgdir)
        self._valid_paths.update((basedir, imgdir))
        for img in lst.get_subscribed_images():
            try:
                img.download(imgdir)
            except (
                exception.ImageVerificationFailed,
                exception.ImageDownloadFailed,
                exception.ImageExpired,
            ):
                pass
            else:
                self._mark_image_valid(img)

    def _mark_image_valid(self, image):
        """Mark all the files of an image as valid.

        All the locations of the image are kept in the cache: the
        downloaded image itself and any image already converted from
        it (e.g. from qcow2 to raw).

        :param image: the image to mark as valid.
        """
        for location in image.locations or [image.location]:
            if location is None:
                continue
            LOG.debug(f"Marking '{location}' as valid")
            self._valid_paths.add(pathlib.Path(location))

    def _clean_invalid(self, base):
        LOG.info(f"Checking for invalid files in cache dir ({base}).")
        invalid_paths = [f for f in base.glob("**/*") if f not in self._valid_paths]

        if not invalid_paths:
            LOG.info(f"No invalid files in cache dir ({base}).")
            return

        for i in invalid_paths:
            LOG.warning(f"Removing '{i}' from cache.")
            utils.rm(i)

    def sync_one(self, lst):
        self._download_list(lst)
        self._clean_invalid(self.path / lst.name)

    def sync(self, lists):
        LOG.info("Starting cache sync")

        for lst in lists.values():
            self.sync_one(lst)
        self._clean_invalid(self.path)

        LOG.info("Sync completed")
