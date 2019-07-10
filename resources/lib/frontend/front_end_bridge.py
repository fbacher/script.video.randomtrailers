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
from common.logger import Logger
from common.monitor import Monitor
from common.plugin_bridge import PluginBridge, PluginBridgeStatus

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
    _instance = None

    def __init__(self):
        # type: () -> None
        """

        """
        self._logger = Logger(self.__class__.__name__)
        local_logger = self._logger.get_method_logger('__init__')
        local_logger.enter()
        try:
            super().__init__()
            self._next_trailer = None
            self._context = Constants.FRONTEND_SERVICE
            self._trailer_iterator = None
            self._trailer = None
            self._busy_getting_trailer = False
            self._status = FrontendBridgeStatus.IDLE
            self.register_listeners()
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.log_exception(e)

    @staticmethod
    def get_instance():
        # type: () -> FrontendBridge
        """

        :return:
        """
        if FrontendBridge._instance is None:
            FrontendBridge._instance = FrontendBridge()
        return FrontendBridge._instance

    ############################################################
    #
    #    Front-End requests to Back-End
    #
    ###########################################################

    def get_next_trailer(self):
        # type: () -> (Union[TextType, None], Union[Dict[TextType, Any], None])
        """
         front-end requests a trailer from the back-end and waits for
            response.

        :return:
        """

        local_logger = self._logger.get_method_logger('get_next_trailer')
        try:
            local_logger.enter('context:', self._context)
            signal_payload = {}
            self.send_signal('get_next_trailer', data=signal_payload,
                             source_id=FrontendBridgeStatus.BACKEND_ID)

            # It can take some time before we get responses back
            # Wait max 30 seconds

            # TODO: handle case where there are NO trailers to play
            # Also, server should send ack on receipt of this request

            self._status = FrontendBridgeStatus.BUSY
            count = 0
            while self._status == FrontendBridgeStatus.BUSY and count < 300:
                self._monitor.throw_exception_if_shutdown_requested(0.10)
                count += 1

            if count >= 300:
                local_logger.error('Timed out waiting on get_next_trailer')
                self._next_trailer = None
                self._status = FrontendBridgeStatus.TIMED_OUT

            trailer = self._next_trailer
            status = self._status
            self._next_trailer = None
            self._status = FrontendBridgeStatus.IDLE
            if trailer is not None:
                local_logger.debug('returning status:',
                                   status, 'title:', trailer[Movie.TITLE])
            return status, trailer
        except (AbortException, ShutdownException):
            self.delete_instance()
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            local_logger.log_exception(e)

    def notify_settings_changed(self):
        # type: () -> None
        """
            Front-end informs others (back-end) that settings may have changed.

        :return:
        """

        local_logger = self._logger.get_method_logger(
            'notify_settings_changed')
        local_logger.enter()
        signal_payload = {}
        self.send_signal('settings_changed', data=signal_payload,
                         source_id=FrontendBridgeStatus.BACKEND_ID)

    def ack(self, what):
        # type: (TextType) -> None
        """
            Front-end acknowledges receipt some messages. This is used
            to confirm that the front-end is running and received message.
            Currently, this is only used to confirm receipt from screen-saver
            service.

        :param what:

        :return:
        """
        local_logger = self._logger.get_method_logger(
            'ack')
        local_logger.enter()
        signal_payload = {'what': what}
        self.send_signal('ack', data=signal_payload,
                         source_id=FrontendBridgeStatus.BACKEND_ID)

    def returned_trailer(self, data):
        # type: (Any) -> None
        """
            Front-end receives trailer from back-end

        :param data:
        :return:
        """
        local_logger = self._logger.get_method_logger('returned_trailer')
        try:
            self._monitor.throw_exception_if_shutdown_requested()
            local_logger.debug(self._context, 'received trailer for:',
                               data.get(Movie.TITLE, None))
            self._next_trailer = data.get('trailer', None)
            self._status = data.get('status', None)
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            local_logger.log_exception(e)

    def activate_screensaver(self):
        # type: () -> None
        """
            Front-end receives request from screensaver service
            to activate screensaver

        :return:
        """
        local_logger = self._logger.get_method_logger('returned_trailer')
        try:

            local_logger.enter()
            # Inform monitor
            self.ack('screensaver')
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            local_logger.log_exception(e)
