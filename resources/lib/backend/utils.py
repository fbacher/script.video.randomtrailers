# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

from common.constants import (Constants)
from common.logger import LazyLogger

import os
import random

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'backend.utils')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class Utils(object):
    """

    """
    RandomGenerator = random.Random()
    RandomGenerator.seed()
    _instance = None

    def __init__(self):
        # type: () -> None
        """

        """
        self._logger = module_logger.getChild(self.__class__.__name__)

    @staticmethod
    def get_instance():
        # type: () -> Utils
        """

        :return:
        """
        if Utils._instance is None:
            Utils._instance = Utils()
        return Utils._instance

    def create_path_if_needed(self, path):
        # type: (TextType) -> None
        """

        :param path:
        :return:
        """
        try:
            if not os.path.exists(path):
                os.makedirs(path)
        except (Exception) as e:
            self._logger.exception('')
