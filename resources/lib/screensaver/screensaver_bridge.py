# -*- coding: utf-8 -*-

"""
Created on Mar 21, 2019

@author: Frank Feuerbacher
"""

import sys

from common.imports import *
from common.constants import Constants, Movie
from common.exceptions import AbortException
from common.logger import (LazyLogger, Trace)
from common.monitor import Monitor
from common.plugin_bridge import PluginBridge, PluginBridgeStatus

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class ScreensaverBridgeStatus(PluginBridgeStatus):
    """

    """


class ScreensaverBridge(PluginBridge):
    """
        ScreensaverBridge provides support for the random trailers screensaver service to
        communicate with the other random trailers plugins. Communication is
        accomplished using the AddonSignals service.
    """

    _instance = None
    _ack_received = None
    _context = None

    def __init__(self):
        # type: () -> None
        """

        """
        super().__init__()

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)
            cls._context = Constants.SCREENSAVER_SERVICE
            cls._ack_received = None

    ###########################################################
    #
    #    Screensaver service requests to front-end to activate
    #    screensaver. Also, receive response from front-end
    #
    ###########################################################

    @classmethod
    def request_activate_screensaver(cls):
        # type: () -> bool
        """
            Used by screensaver service to tell front-end to activate
            screensaver
        """
        try:
            cls._ack_received = False
            cls.send_signal('activate_screensaver', data={},
                            source_id=Constants.BACKEND_ID)

            # Wait for response

            # count = 0
            # while count < 30 and cls._ack_received is None:
            #     Monitor.wait_for_abort(0.05)
            #     count += 1

            # if not cls._ack_received:
            #     if cls._logger.isEnabledFor(LazyLogger.DEBUG):
            #         cls._logger.debug(
            #             'randomtrailers front-end appears inactive')
            #     return False
            return True
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

    '''
    @classmethod
    def receiveAck(cls, data):
        # type: (Any) -> None
        """

        :param data:
        :return:
        """
        try:
            what = data.get('what', None)
            if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                cls._logger.debug(cls._context, 'received ack for:', what)
            if what != 'screensaver':
                if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                    cls._logger.error('Unexpected response:', what)
            else:
                cls._ack_received = what

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

    @classmethod
    def register_listeners(cls):
        # type: () -> None
        """
            Register listeners (callbacks) with service. Note that
            communication is asynchronous

            :return: None
        """

        cls.register_slot(Constants.FRONTEND_ID, 'ack', cls.receiveAck)
    '''


ScreensaverBridge.class_init()