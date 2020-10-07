# -*- coding: utf-8 -*-

"""
Created on Mar 21, 2019

@author: Frank Feuerbacher
"""


import os
import sys

from common.constants import Constants, Movie
from common.exceptions import AbortException
from common.imports import *
from common.logger import LazyLogger, Trace
from common.monitor import Monitor
from common.plugin_bridge import PluginBridge, PluginBridgeStatus

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)

"""
    FrontendBridge provides support for the random trailers front_end_service to
    communicate with the other random trailers plugins. Communication is
    accomplished using the AddonSignals service. 
"""


class FrontendBridgeStatus(PluginBridgeStatus):
    """
    """

# noinspection Annotator


class FrontendBridge(PluginBridge):
    """

    """
    _logger = None
    _next_trailer = None
    _trailer_iterator = None
    _trailer = None
    _busy_getting_trailer = False
    _status = FrontendBridgeStatus.IDLE

    def __init__(self):
        # type: () -> None
        """

        """
        super().__init__()
        type(self).class_init()

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.enter()
            try:
                cls._next_trailer = None
                cls._trailer_iterator = None
                cls._trailer = None
                cls._busy_getting_trailer = False
                cls._status = FrontendBridgeStatus.IDLE
                cls.register_listeners()
            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                cls._logger.exception('')

    ############################################################
    #
    #    Front-End requests to Back-End
    #
    ###########################################################

    @classmethod
    def get_next_trailer(cls):
        # type: () -> (Union[str, None], Union[Dict[str, Any], None])
        """
         front-end requests a trailer from the back-end and waits for
            response.

        :return:
        """
        try:
            signal_payload = {}
            cls.send_signal('get_next_trailer', data=signal_payload,
                             source_id=Constants.BACKEND_ID)

            # It can take some time before we get responses back
            # Wait max 30 seconds

            # TODO: handle case where there are NO trailers to play
            # Also, server should send ack on receipt of this request

            cls._status = FrontendBridgeStatus.BUSY
            count = 0
            while cls._status == FrontendBridgeStatus.BUSY and count < 300:
                Monitor.throw_exception_if_abort_requested(timeout=0.10)
                count += 1

            if count >= 300:
                cls._logger.error('Timed out waiting on get_next_trailer')
                cls._next_trailer = None
                cls._status = FrontendBridgeStatus.TIMED_OUT

            trailer = cls._next_trailer
            status = cls._status
            cls._next_trailer = None
            cls._status = FrontendBridgeStatus.IDLE
            if trailer is not None:
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose('returning status:',
                                                    status, 'title:',
                                                    trailer[Movie.TITLE])
            return status, trailer
        except AbortException:
            cls.delete_instance()
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

    @classmethod
    def notify_settings_changed(cls):
        # type: () -> None
        """
            Front-end informs others (back-end) that settings may have changed.

        :return:
        """
        if LazyLogger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls._logger.enter()
        signal_payload = {}
        cls.send_signal('settings_changed', data=signal_payload,
                         source_id=Constants.BACKEND_ID)

    @classmethod
    def ack(cls, what):
        # type: (str) -> None
        """
            Front-end acknowledges receipt some messages. This is used
            to confirm that the front-end is running and received message.
            Currently, this is only used to confirm receipt from screen-saver
            service.

        :param what:

        :return:
        """
        # if LazyLogger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
        #     cls._logger.enter()
        signal_payload = {'what': what}
        cls.send_signal('ack', data=signal_payload, source_id=Constants.BACKEND_ID)

    @classmethod
    def returned_trailer(cls, data):
        # type: (Any) -> None
        """
            Front-end receives trailer from back-end

        :param data:
        :return:
        """
        try:
            Monitor.throw_exception_if_abort_requested()
            cls._next_trailer = data.get('trailer', None)
            cls._status = data.get('status', None)
            if cls._status == FrontendBridgeStatus.BUSY:
                Monitor.throw_exception_if_abort_requested(timeout=2.0)
            elif cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                if cls._next_trailer is None:
                    title = 'No Trailer Received'
                else:
                    title = cls._next_trailer.get(Movie.TITLE, 'No Title')
                cls._logger.debug_extra_verbose('status:', cls._status,
                                                'received trailer for:',
                                                title)
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

    @classmethod
    def activate_screensaver(cls, data: Any = None) -> None:
        """
            Front-end receives request from screensaver service
            to activate screensaver

            data arg required, but unused.

        :return:
        """
        try:

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.enter()
            # Inform monitor
            cls.ack('screensaver')
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
        # if LazyLogger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
        #     cls._logger.enter()

        frontend_id = Constants.FRONTEND_ID
        cls.register_slot(
            frontend_id, 'nextTrailer', cls.returned_trailer)
        cls.register_slot(
            frontend_id, 'activate_screensaver', cls.activate_screensaver)
