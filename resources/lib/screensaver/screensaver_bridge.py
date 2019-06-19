# -*- coding: utf-8 -*-

"""
Created on Mar 21, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                                 TextType, DEVELOPMENT, RESOURCE_LIB)

import sys
import threading
import six

from kodi65 import addon
from kodi_six import xbmc
import AddonSignals as AddonSignals

from common.constants import Constants, Movie
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger
from common.monitor import Monitor
from common.plugin_bridge import PluginBridge, PluginBridgeStatus

class ScreensaverBridgeStatus(PluginBridgeStatus):
    """

    """

class ScreensaverBridge(PluginBridge):
    """
        ScreensaverBridge provides support for the random trailers screensaver ervice to
        communicate with the other random trailers plugins. Communication is
        accomplished using the AddonSignals service.
    """

    _instance = None

    def __init__(self):
        # type: () -> None
        """

        """
        self._logger = Logger(self.__class__.__name__)
        super().__init__()
        self._context = Constants.SCREENSAVER_SERVICE
        self._ack_received = None

    @staticmethod
    def get_instance():
        # type: () -> ScreensaverBridge
        """

        :return:
        """
        if ScreensaverBridge._instance is None:
            ScreensaverBridge._instance = ScreensaverBridge()
        return ScreensaverBridge._instance



    ###########################################################
    #
    #    Screensaver service requests to front-end to activate
    #    screensaver. Also, receive response from front-end
    #
    ###########################################################

    def request_activate_screensaver(self):
        # type: () -> bool
        """
            Used by screensaver service to tell front-end to activate
            screensaver
        """
        local_logger = self._logger.get_method_logger(
            u'request_activate_screensaver')
        local_logger.enter()
        try:
            self._ack_received = False
            self.send_signal(u'activate_screensaver', data={},
                            source_id=ScreensaverBridgeStatus.BACKEND_ID)

            # Wait for response

            count = 0
            while count < 30 and self._ack_received is None:
                Monitor.get_instance().waitForAbort(0.05)
                count += 1

            if not self._ack_received:
                local_logger.debug(u'randomtrailers front-end appears inactive')
                return False
            return True
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            local_logger.log_exception(e)

    def receiveAck(self, data):
        # type: (Any) -> None
        """

        :param data:
        :return:
        """
        local_logger = self._logger.get_method_logger(u'receiveAck')
        try:
            what = data.get(u'what', None)
            local_logger.debug(self._context, u'received ack for:',
                              )
            if what != u'screensaver':
                local_logger.error(u'Unexpected response:', what)
            else:
                self._ack_received = what

        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            local_logger.log_exception(e)