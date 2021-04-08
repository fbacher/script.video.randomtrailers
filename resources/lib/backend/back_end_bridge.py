# -*- coding: utf-8 -*-

"""
Created on Mar 21, 2019

@author: Frank Feuerbacher
"""

import sys
import threading

from common.constants import Constants, Movie
from common.exceptions import AbortException
from common.garbage_collector import GarbageCollector
from common.imports import *
from common.logger import LazyLogger
from common.monitor import Monitor
from common.plugin_bridge import PluginBridge, PluginBridgeStatus
from discovery.playable_trailer_service import PlayableTrailerService

module_logger: Final[LazyLogger] = LazyLogger.get_addon_module_logger(file_path=__file__)


class BackendBridgeStatus(PluginBridgeStatus):
    """

    """


class BackendBridge(PluginBridge):
    """
        BackendBridge provides support for the random trailers backend to
        communicate with other random trailers plugins. Communication is
        accomplished using the AddonSignals service.
    """
    _logger: LazyLogger = None
    _next_trailer: MovieType = None
    _trailer_iterator: Iterable = None
    _trailer: MovieType = None
    _on_settings_changed_callback = None
    _busy_getting_trailer: bool = False
    _status: str = BackendBridgeStatus.IDLE

    def __init__(self,
                 playable_trailer_service: PlayableTrailerService) -> None:
        super().__init__()
        type(self).class_init(playable_trailer_service)

    @classmethod
    def class_init(cls,
                   playable_trailer_service: PlayableTrailerService) -> None:
        """
         Simple initialization

         :param playable_trailer_service:
        """
        cls._logger = module_logger.getChild(cls.__name__)
        try:
            cls.register_listeners()
            if playable_trailer_service is None:
                cls._logger.error('Need to define playable_trailer_service to be',
                                  'PlayableTrailerService()')
            cls._trailer_iterator = iter(playable_trailer_service)
            cls._on_settings_changed_callback: Callable[[None], None] =\
                Monitor.onSettingsChanged

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

    ###########################################################
    #
    #    Back-End receiving requests from and sending responses
    #    to Front-End
    #
    ###########################################################

    @classmethod
    def get_trailer(cls, _) -> None:
        """
            Back-end receives request for next trailer from the front-end and
            waits for response.
        """
        try:
            thread = threading.Thread(
                target=cls.get_trailer_worker,
                name='BackendBridge.get_trailer')

            thread.start()
            GarbageCollector.add_thread(thread)
        except AbortException:
            pass  # Don't pass up to AddonSignals
        except Exception:
            cls._logger.exception('')

    @classmethod
    def get_trailer_worker(cls) -> None:
        """
            Back-end receives request for next trailer from the front-end and
            waits for response.
        """

        # if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
        #    cls._logger.enter()

        #
        # Don't want to recurse on onMonitor event stack or
        # get stuck
        #
        if cls._busy_getting_trailer:
            cls.send_trailer(BackendBridgeStatus.BUSY, None)
            return

        cls._busy_getting_trailer = True
        try:
            trailer = next(cls._trailer_iterator)
        except StopIteration:
            cls.send_trailer(BackendBridgeStatus.BUSY, None)
            cls._busy_getting_trailer = False
            return

        cls._trailer = trailer
        cls._status = BackendBridgeStatus.OK
        cls.send_trailer(BackendBridgeStatus.OK, trailer)
        cls._busy_getting_trailer = False

    @classmethod
    def send_trailer(cls, status: str, trailer: MovieType) -> None:
        """
            Send trailer to front-end
        """
        try:
            cls.send_signal('nextTrailer',
                            data={'trailer': trailer,
                                  'status': status},
                            source_id=Constants.FRONTEND_ID)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

    @classmethod
    def on_settings_changed(cls, _: Any) -> None:
        """
            Back-end receiving notification from front-end that the settings have
            changed.
        """
        try:
            thread = threading.Thread(
                target=cls._on_settings_changed_callback,
                name='BackendBridge.on_settings_changed')

            thread.start()
            GarbageCollector.add_thread(thread)
        except AbortException:
            pass  # Don't pass up to AddonSignals
        except Exception:
            cls._logger.exception('')

    @classmethod
    def register_listeners(cls) -> None:
        """
            Register listeners (callbacks) with service. Note that
            communication is asynchronous

            :return: None
        """
        if cls._logger.isEnabledFor(LazyLogger.DISABLED):
            cls._logger.enter()

        #
        # Back-end listens for get_next_trailer requests and
        # settings_changed notifications
        #
        cls.register_slot(Constants.BACKEND_ID,
                          'get_next_trailer', cls.get_trailer)
        cls.register_slot(Constants.BACKEND_ID, 'settings_changed',
                          cls.on_settings_changed)
