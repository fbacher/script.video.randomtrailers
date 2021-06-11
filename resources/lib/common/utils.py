# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import datetime
import math
import os
import random
import time

from common.minimal_monitor import MinimalMonitor
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


class Delay:
    _logger: LazyLogger = None

    def __init__(self, bias: float = 0.0, call_scale_factor: float = 1.0,
                 scale_factor: float = 1.0) -> None:
        '''
        Delay simply provides a mechanism to keep from throttling the cpu.
        The delay is designed to increase with each call (although this can
        be overridden). The wait time, in seconds, is:

           delay = bias + log10(number_of_calls * call_scale_factor) * scale_factor

        :param bias: Base amount of time to wait
        :param call_scale_factor: Increases the weight of each call
        :param scale_factor: See formula
        '''

        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(clz.__class__.__name__)

        self._bias: float = bias
        self._call_scale_factor = call_scale_factor
        self._scale_factor: float = scale_factor

        self._call_count: int = 0
        self._delay: float = 0.0

    def delay(self, bias: float = None,
              call_scale_factor: float = None,
              scale_factor: float = None,
              timeout: float = None) -> float:
        '''
        Waits to keep from throttling the cpu. The wait time depends upon
        the given parameters. The time to wait is returned after the call.

        Note: Can raise AbortException

            number_of_calls += call_increase
            if timeout > 0.0:
                delay = timeout
            else:
                delay = bias + log10(number_of_calls * call_scale_factor) * scale_factor

        :param bias: Base amount of time to wait; replaces value from constructor
        :param call_scale_factor: Increases the weight of each call; replaces
               value from constructor
        :param scale_factor: See formula; replaces value from constructor
        :param timeout: If specified, this overrides the calculated delay
        :return:
        '''
        clz = type(self)

        if bias is not None:
            self._bias = float(bias)
        if call_scale_factor is not None:
            self._call_scale_factor = float(call_scale_factor)
        if scale_factor is not None:
            self._scale_factor = float(scale_factor)

        self._call_count += 1

        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
            clz._logger.debug_extra_verbose(f' bias: {bias} call_count: '
                                            f'{self._call_count} call_scale_factor: '
                                            f'{self._call_scale_factor:f} scale_factor: '
                                            f'{self._scale_factor}')
        _delay: float
        if timeout is not None:
            _delay = float(timeout)
        else:
            # Adding 1.0 ensures that we don't do log10(0)
            _delay = self._bias + (math.log10(1.0 + self._call_count *
                                              self._call_scale_factor)
                                  * self._scale_factor)

        MinimalMonitor.throw_exception_if_abort_requested(_delay)
        return _delay
