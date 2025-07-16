# -*- coding: utf-8 -*-

"""
Created on Mar 21, 2019

@author: Frank Feuerbacher
"""

import pickle
import sys
import threading
from datetime import datetime

from common.constants import Constants
from common.debug_utils import Debug
from common.exceptions import AbortException
from common.garbage_collector import GarbageCollector
from common.imports import *
from common.logger import *
from common.movie import AbstractMovie, LibraryMovie
from common.plugin_bridge import PluginBridge, PluginBridgeStatus
from discovery.playable_trailer_service import PlayableTrailerService
from .__init__ import *

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class BackendBridgeStatus(PluginBridgeStatus):
    """

    """


class BackendBridge(PluginBridge):
    """
        BackendBridge provides support for the random trailers backend to
        communicate with other random trailers plugins. Communication is
        accomplished using the AddonSignals service.
    """
    _logger: BasicLogger = None
    _next_trailer: AbstractMovie = None
    _trailer_iterator: Iterator = None
    _trailer: AbstractMovie = None
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
                cls._logger.error(f'Need to define playable_trailer_service to be '
                                  f'PlayableTrailerService()')
            cls._trailer_iterator = iter(playable_trailer_service)
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
            Back-end receives request for next movie from the front-end and
            waits for response.
        """
        try:
            thread = threading.Thread(
                target=cls.get_trailer_worker,
                name='BackendBridge')

            thread.start()
            GarbageCollector.add_thread(thread)
        except AbortException:
            pass  # Don't pass up to AddonSignals
        except Exception:
            cls._logger.exception('')

    @classmethod
    def get_trailer_worker(cls) -> None:
        """
            Back-end receives request for next movie from the front-end and
            waits for response.
        """

        # if cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
        #    cls._logger.debug('enter')

        #
        # Don't want to recurse on onMonitor event stack or
        # get stuck
        #
        if cls._busy_getting_trailer:
            cls.send_trailer(BackendBridgeStatus.BUSY, None)
            return

        cls._busy_getting_trailer = True
        try:
            trailer: AbstractMovie = next(cls._trailer_iterator)
        except StopIteration:
            cls.send_trailer(BackendBridgeStatus.BUSY, None)
            cls._busy_getting_trailer = False
            return

        cls._trailer = trailer
        cls._status = BackendBridgeStatus.OK
        if trailer.is_starving():
            status: str = BackendBridgeStatus.BUSY
        else:
            status: str = BackendBridgeStatus.OK

        cls.send_trailer(status, trailer)
        cls._busy_getting_trailer = False

    @classmethod
    def send_trailer(cls, status: str, movie: AbstractMovie) -> None:
        """
            Send movie to front-end
        """
        try:
            # As a side-effect of a patch for datetime.datetime.strptime, an
            # un-picklable object can be created for last_played_time.
            # The patch is in YoutubeDLWrapper from youtube-dl.

            if isinstance(movie, LibraryMovie):
                last_played_str: str = movie.get_last_played().isoformat()
                last_played = datetime.fromisoformat(last_played_str)
                movie.set_last_played(last_played)

            pickled: bytes = pickle.dumps(movie)
            pickled_str: str = pickled.hex()
            cls.send_signal('nextTrailer',
                            data={'movie': pickled_str,
                                  'status': status},
                            source_id=Constants.FRONTEND_ID)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')
            Debug.dump_dictionary(movie.get_as_movie_type(),
                                  include_type=True, level=ERROR)

    @classmethod
    def dump_threads(cls, _) -> None:
        from common.debug_utils import Debug
        Debug.dump_all_threads()

    @classmethod
    def register_listeners(cls) -> None:
        """
            Register listeners (callbacks) with service. Note that
            communication is asynchronous

            :return: None
        """
        if cls._logger.isEnabledFor(DISABLED):
            cls._logger.debug_extra_verbose('entered')

        #
        # Back-end listens for get_next_trailer requests
        #
        cls.register_slot(Constants.BACKEND_ID,
                          'get_next_trailer', cls.get_trailer)
        cls.register_slot(
            Constants.BACKEND_ID, 'dump_threads', cls.dump_threads)
