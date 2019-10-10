# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from .imports import *

import os
import random

from kodi65.kodiaddon import Addon

from .constants import Constants
from .logger import LazyLogger
from .settings import Settings

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'common.utils')
else:
    module_logger = LazyLogger.get_addon_module_logger()

# noinspection PyClassHasNoInit
class Utils(object):
    """

    """
    RandomGenerator = random.Random()
    RandomGenerator.seed()

    _exit_requested = False
    _logger = module_logger.getChild('Utils')

    @staticmethod
    def create_path_if_needed(path):
        # type: (TextType) -> None
        """

        :param path:
        :return:
        """

        try:
            if not os.path.exists(path):
                os.makedirs(path)
        except (Exception) as e:
            Utils._logger.exception('')

    @staticmethod
    def is_url(path):
        # tpe: (TextType) -> bool
        """

        :param path:
        :return:
        """
        if path.startswith('http://') or path.startswith('https://') or path.startswith('plugin://'):
            return True
        return False

    @staticmethod
    def is_trailer_from_cache(path):
        cache_path_prefix = Settings.get_downloaded_trailer_cache_path()
        if path.startswith(cache_path_prefix):
            return True
        return False

    @staticmethod
    def is_couch_potato_installed():
        # type: () -> bool
        """

        :return:
        """
        installed = False
        try:
            couch_potato_addon = Addon(Constants.COUCH_POTATO_ID)
            version = couch_potato_addon.VERSION
            installed = True
        except (Exception) as e:
            pass

        return installed