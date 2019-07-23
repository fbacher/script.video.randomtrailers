# -*- coding: utf-8 -*-

"""
Created on Mar 21, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import sys
import threading
import six

from kodi65 import addon
from kodi_six import xbmc
import AddonSignals as AddonSignals

from common.constants import Constants, Movie
from common.exceptions import AbortException, ShutdownException
from common.logger import (LazyLogger, Logger, Trace)
from common.monitor import Monitor
from common.plugin_bridge import PluginBridge, PluginBridgeStatus

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild('screensaver.screensaver_bridge')
else:
    module_logger = LazyLogger.get_addon_module_logger()


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
        self._logger = module_logger.getChild(self.__class__.__name__)
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
        self._logger.enter()
        try:
            self._ack_received = False
            self.send_signal('activate_screensaver', data={},
                            source_id=ScreensaverBridgeStatus.BACKEND_ID)

            # Wait for response

            count = 0
            while count < 30 and self._ack_received is None:
                Monitor.get_instance().wait_for_shutdown(0.05)
                count += 1

            if not self._ack_received:
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('randomtrailers front-end appears inactive')
                return False
            return True
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')

    def receiveAck(self, data):
        # type: (Any) -> None
        """

        :param data:
        :return:
        """
        try:
            what = data.get('what', None)
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(self._context, 'received ack for:', what)
            if what != 'screensaver':
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.error('Unexpected response:', what)
            else:
                self._ack_received = what

        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')