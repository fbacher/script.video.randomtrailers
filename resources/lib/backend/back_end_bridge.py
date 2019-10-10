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
from common.logger import LazyLogger
from common.monitor import Monitor
from common.plugin_bridge import PluginBridge, PluginBridgeStatus
from discovery.playable_trailer_service import PlayableTrailerService
from discovery.base_discover_movies import BaseDiscoverMovies

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger(
    ).getChild('backend.backend_bridge')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class BackendBridgeStatus(PluginBridgeStatus):
    """

    """

# noinspection Annotator,PyInitNewSignature


class BackendBridge(PluginBridge):
    """
        BackendBridge provides support for the random trailers backend to
        communicate with other random trailers plugins. Communication is
        accomplished using the AddonSignals service.
    """
    _instance = None

    def __init__(self, playable_trailer_service, discover_movies):
        # type: (PlayableTrailerService, BaseDiscoverMovies) -> None
        """
        Simple initialization

        :param trailer_manager:
        :param discover_movies:
        """

        self._logger = module_logger.getChild(self.__class__.__name__)
        super().__init__()
        self._next_trailer = None
        self._context = Constants.BACKEND_SERVICE
        self._trailer_iterator = None
        self._trailer = None
        self._on_settings_changed_callback = None
        self._busy_getting_trailer = False
        self._status = BackendBridgeStatus.IDLE

        try:
            self.register_listeners()
            if playable_trailer_service is None:
                self._logger.error('Need to define playable_trailer_service to be',
                                   'PlayableTrailerService()')
            # trailerIterator = BaseTrailerManager.get_instance()
            self._trailer_iterator = iter(playable_trailer_service)
            self._on_settings_changed_callback = Monitor.get_instance().onSettingsChanged

        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')

    @staticmethod
    def get_instance(playable_trailer_service, discover_movies):
        # type: (PlayableTrailerService, BaseDiscoverMovies) -> BackendBridge
        """

        :param playable_trailer_service:
        :param discover_movies
        :return:
        """
        if BackendBridge._instance is None:
            BackendBridge._instance = BackendBridge(playable_trailer_service,
                                                    discover_movies)
        return BackendBridge._instance

    ###########################################################
    #
    #    Back-End receiving requests from and sending responses
    #    to Front-End
    #
    ###########################################################

    def get_trailer(self, ignored):
        # type: (Any) -> None
        """
            Back-end receives request for next trailer from the front-end and
            waits for response.
        """

        self._logger.enter()
        try:
            thread = threading.Thread(
                target=self.get_trailer_worker,
                args=(ignored,),
                name='BackendBridge.get_trailer')

            thread.start()
        except (Exception):
            self._logger.exception('')

    def get_trailer_worker(self, ignored):
        # type: (Any) -> None
        """
            Back-end receives request for next trailer from the front-end and
            waits for response.
        """

        if self._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            self._logger.enter()

        #
        # Don't want to recurse on onMonitor event stack or
        # get stuck
        #
        if self._busy_getting_trailer:
            self.send_trailer(BackendBridgeStatus.BUSY, None)

        self._busy_getting_trailer = True
        trailer = next(self._trailer_iterator)
        self._trailer = trailer
        self._status = BackendBridgeStatus.OK
        self.send_trailer(BackendBridgeStatus.OK, trailer)
        self._busy_getting_trailer = False

    def send_trailer(self, status, trailer):
        # type: (TextType, Union[dict, None]) -> None
        """
            Send trailer to front-end
        """
        try:
            self.send_signal('nextTrailer', data={'trailer': trailer,
                                                  'status': status},
                             source_id=Constants.FRONTEND_ID)

        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')

    def on_settings_changed(self, ignored):
        # type: (Any) -> None
        """
            Back-end receiving notification from front-end that the settings have
            changed.
        """
        try:
            thread = threading.Thread(
                target=self._on_settings_changed_callback,
                name='BackendBridge.on_settings_changed')

            thread.start()
        except (Exception):
            self._logger.exception('')

    def register_listeners(self):
        # type: () -> None
        """
            Register listeners (callbacks) with service. Note that
            communication is asynchronous

            :return: None
        """

        self._logger.enter()

        #
        # Back-end listens for get_next_trailer requests and
        # settings_changed notifications
        #
        self.register_slot(addon.ID, 'get_next_trailer', self.get_trailer)
        self.register_slot(addon.ID, 'settings_changed',
                           self.on_settings_changed)
