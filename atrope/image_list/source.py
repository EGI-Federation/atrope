# -*- coding: utf-8 -*-

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

import abc

import six
from oslo_log import log

from atrope import exception

LOG = log.getLogger(__name__)


def _set_error(func):
    def decorated(self):
        try:
            func(self)
        except Exception as e:
            self.error = e
            raise

    return decorated


@six.add_metaclass(abc.ABCMeta)
class BaseImageListSource(object):
    """An image list."""

    def __init__(
        self,
        name,
        url="",
        enabled=True,
        subscribed_images=[],
        prefix="",
        project="",
        vos=[],
        **kwargs,
    ):
        self.name = name
        self.url = url
        self.enabled = enabled
        self.prefix = prefix
        self.subscribed_images = subscribed_images
        self.error = None
        self.vos = vos

        self.project = project

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.name)

    @abc.abstractmethod
    def fetch(self):
        """Fetch the image list."""

    def get_valid_subscribed_images(self):
        return [i for i in self.get_subscribed_images() if i.verified and not i.expired]

    def get_subscribed_images(self):
        """Get the subscribed images from the fetched image list."""
        if not self.enabled:
            return []

        if self.image_list is None:
            LOG.error(f"Image list {self.name} has not been fetched!")
            return []

        if not self.subscribed_images:
            return self.image_list.get_images()
        else:
            return [
                img
                for img in self.image_list.get_images()
                if img.identifier in self.subscribed_images
            ]

    def get_images(self):
        """Get the images defined in the fetched image list."""
        if not self.enabled:
            return []

        if self.image_list is None:
            raise exception.ImageListNotFetched(id=self.name)

        return self.image_list.get_images()

    def print_list(self):
        pass
