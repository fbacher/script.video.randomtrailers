# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import os
import random
import sys

from common.imports import *
from common.constants import (Constants)
from common.exceptions import AbortException
from common.logger import LazyLogger


module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


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
        # type: (str) -> None
        """

        :param path:
        :return:
        """
        try:
            if not os.path.exists(path):
                os.makedirs(path)
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            self._logger.exception('')
