# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import datetime
import os
import random
import time

from kodi65.kodiaddon import Addon

from common.constants import Constants
from common.imports import *
from common.logger import LazyLogger
from common.settings import Settings

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class Utils:
    """

    """
    RandomGenerator = random.Random()
    RandomGenerator.seed()

    _exit_requested = False
    _logger = module_logger.getChild('Utils')

    @staticmethod
    def create_path_if_needed(path: str) -> None:
        """

        :param path:
        :return:
        """

        try:
            if not os.path.exists(path):
                os.makedirs(path)
        except Exception as e:
            Utils._logger.exception('')

    @staticmethod
    def is_url(path: str) -> bool:
        """

        :param path:
        :return:
        """
        if path.startswith('http://') or path.startswith('https://') or path.startswith(
                'plugin://'):
            return True
        return False

    @staticmethod
    def is_trailer_from_cache(path):
        cache_path_prefix = Settings.get_downloaded_trailer_cache_path()
        if path.startswith(cache_path_prefix):
            return True
        return False

    @staticmethod
    def is_couch_potato_installed() -> bool:
        """

        :return:
        """
        installed = False
        try:
            couch_potato_addon = Addon(Constants.COUCH_POTATO_ID)
            version = couch_potato_addon.VERSION
            installed = True
        except Exception as e:
            pass

        return installed

    @staticmethod
    def strptime(date_string: str, date_format: str) -> datetime.datetime:
        """
        THIS IS A WORKAROUND to a known python bug that shows up in embedded
        systems. Apparently proper reinitialization would solve it, but it is
        still a known bug:  https://bugs.python.org/issue27400

        The work around is to use an alternate solution that uses time.strptime.
        See documentation on datetime.strptime, it gives the equivalent code
        below.

        :param date_string:
        :param date_format:
        :return:
        """
        result = datetime.datetime(*(time.strptime(date_string,
                                                   date_format)[0:6]))
        return result
