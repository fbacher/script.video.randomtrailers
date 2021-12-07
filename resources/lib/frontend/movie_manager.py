# -*- coding: utf-8 -*-

'''
Created on May 25, 2019

@author: Frank Feuerbacher
'''
import enum
import queue
import sys
import os
import threading

from common.debug_utils import Debug
from common.exceptions import AbortException, LogicError
from common.imports import *
from common.logger import LazyLogger
from common.monitor import Monitor
from common.movie import AbstractMovie, FolderMovie
from common.movie_constants import MovieField
from frontend.front_end_bridge import FrontendBridge, FrontendBridgeStatus
from common.settings import Settings
from frontend.history_list import HistoryList
from frontend.history_empty import HistoryEmpty

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class MovieStatus(FrontendBridgeStatus):
    PREVIOUS_MOVIE: Final[str] = 'PREVIOUS_MOVIE'
    NEXT_MOVIE: Final[str] = 'NEXT_MOVIE'


class TrailerPlayState(enum.Enum):
    PLAY_OPEN_CURTAIN_NEXT = 1
    PLAY_CLOSE_CURTAIN_NEXT = 2
    PLAY_NEXT_TRAILER = 3
    PLAY_PREVIOUS_TRAILER = 4
    NOTHING = 5


class MovieManager:

    OPEN_CURTAIN: Final[bool] = True
    CLOSE_CURTAIN: Final[bool] = False

    _logger: LazyLogger = None
    instance: ForwardRef('MovieManager') = None

    def __init__(self) -> None:
        """
        """
        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(self.__class__.__name__)

        super().__init__()
        self._movie_history_cursor: bool = None
        FrontendBridge()
        self._thread = None
        self._queuedMovie = None
        self._pre_fetched_trailer_queue: queue.Queue = queue.Queue(2)
        self.fetched_event: threading.Event = threading.Event()
        self.pre_fetch_trailer()
        self._play_state: TrailerPlayState = TrailerPlayState.NOTHING
        self._changed = False
        self._instance = self

    def has_next_trailer(self) -> bool:
        """
        Returns True unless:
            1) set to return Previous Trailer
            2) there is no previous trailer

        :return:
        """
        if self._play_state == TrailerPlayState.PLAY_PREVIOUS_TRAILER:
            return HistoryList.has_previous_trailer()
        return True

    def get_next_trailer(self) -> (str, AbstractMovie):
        """
        TrailerDialog calls whenever it needs the next trailer to play.
        This can occur because the previous trailer has finished playing,
        or because user event which stops the previous trailer and changes
        what is to be played next (previous, next trailer).

        :return:
        """
        clz = type(self)
        trailer: AbstractMovie = None
        status: str = None
        prefetched: bool = False
        self._changed = True
        if self._play_state == TrailerPlayState.NOTHING:
            self._play_state = TrailerPlayState.PLAY_NEXT_TRAILER

        # If user input occurs during processing we want to ignore all but the most
        # recent action. Likely this will only impact expensive operations, such
        # as get next trailer.

        if self._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            self._logger.debug(f'play_state: {self._play_state}')
        while self._changed:
            self._changed = False  # Flip to True if additional user event occurs
            if self._play_state == TrailerPlayState.PLAY_OPEN_CURTAIN_NEXT:
                status = MovieStatus.OK
                trailer = FolderMovie({MovieField.SOURCE: 'curtain',
                                       MovieField.TITLE: 'openCurtain',
                                       MovieField.TRAILER: Settings.get_open_curtain_path()})
            elif self._play_state == TrailerPlayState.PLAY_CLOSE_CURTAIN_NEXT:
                status = MovieStatus.OK
                trailer = FolderMovie({MovieField.SOURCE: 'curtain',
                                       MovieField.TITLE: 'closeCurtain',
                                       MovieField.TRAILER: Settings.get_close_curtain_path()})
            elif self._play_state == TrailerPlayState.PLAY_PREVIOUS_TRAILER:
                status = MovieStatus.PREVIOUS_MOVIE
                try:
                    trailer = HistoryList.get_previous_trailer()

                    # Trailer is None when just played oldest movie in history
                    # In this event, HistoryEmpty should be thrown.

                except HistoryEmpty:
                    self._play_state = TrailerPlayState.NOTHING
                    reraise(*sys.exc_info())
            else:
                if self._play_state == TrailerPlayState.PLAY_NEXT_TRAILER:
                    status = MovieStatus.NEXT_MOVIE
                else:
                    status = MovieStatus.OK

                trailer = HistoryList.get_next_trailer()
                countdown = 10  # Five Seconds

                # trailer is None when already played most recent trailer in history.
                # Need to get trailer from back-end

                while trailer is None and countdown >= 0 and not self._changed:
                    countdown -= 1
                    if not self._pre_fetched_trailer_queue.empty():
                        trailer = self._pre_fetched_trailer_queue.get(timeout=0.5)
                        if trailer is not None:
                            title = trailer.get_title()

                            # HistoryList.append does not add trailers that
                            # are in it's recent history. However, when
                            # the back-end is having trouble getting trailers
                            # to us, it can send duplicates. Therefore, if,
                            # a few lines down, HistoryList.get_next_trailer
                            # doesn't return anything, we can return this
                            # trailer, if it is marked as starving.

                            HistoryList.append(trailer)

                            # Force go get from history to make sure history cursor
                            # is in sync what was just appended, otherwise, if user
                            # presses next/prev movie rapidly, the history will
                            # diverge from what is returned here.

                            next_trailer = HistoryList.get_next_trailer()
                            if next_trailer is not None:
                                trailer = next_trailer
                            elif not trailer.is_starving(reset=False):

                                # If trailer is not marked as starving, then
                                # don't force it to be played.
                                trailer = None

                    Monitor.throw_exception_if_abort_requested(timeout=0.0)

                title: str = 'None'
                if trailer is not None:
                    title = trailer.get_title()

                if self._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    self._logger.debug(f'movie: {title} '
                                       f'play_state: {self._play_state} '
                                       f'changed: {self._changed}')
                if self._changed:
                    # User wants something else in the time it took us to find
                    # trailer
                    continue

                if trailer is None:
                    status = MovieStatus.TIMED_OUT

        self._play_state = TrailerPlayState.NOTHING
        title = None
        if trailer is not None:

            # Make sure path to cached trailer is up to date

            if self.purge_removed_cached_trailers(trailer):

                # No trailer at all to play

                HistoryList.remove(trailer)
                return self.get_next_trailer()

        if trailer is not None:
            title = trailer.get_title()
        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
            clz._logger.exit('status:', status, 'movie', title)

        return status, trailer

    def purge_removed_cached_trailers(self, trailer: AbstractMovie) -> None:
        #
        # Handles the very rare event that a cached trailer/normalized trailer
        # was removed before the trailer is about to be played.
        # Simply updates the trailer path or returns True when the trailer is
        # completely gone and must be skipped over.

        clz = type(self)
        trailer_path: str
        if trailer.get_normalized_trailer_path() != '':
            trailer_path = trailer.get_normalized_trailer_path()
            if not os.path.exists(trailer_path):
                trailer.set_normalized_trailer_path('')
                clz._logger.debug_verbose(f'Does not exist: {trailer_path}')
        elif trailer.get_cached_trailer() != '':
            trailer_path = trailer.get_cached_trailer()
            if not os.path.exists(trailer_path):
                trailer.set_cached_trailer('')
                clz._logger.debug_verbose('Does not exist:', trailer_path)
        else:
            trailer_path = trailer.get_trailer_path()
            if not trailer.has_trailer_path():
                trailer_path = None
            elif not (trailer_path.startswith('plugin') or os.path.exists(trailer_path)):
                trailer.set_trailer_path('')
                clz._logger.debug_verbose('Does not exist:', trailer_path)
                trailer_path = None
        return trailer_path is None

    def pre_fetch_trailer(self) -> None:
        self._thread = threading.Thread(
            target=self._pre_fetch_trailer, name='Pre-Fetch trailer')
        self._thread.start()

    def _pre_fetch_trailer(self) -> None:
        clz = type(self)
        try:
            while not Monitor.throw_exception_if_abort_requested():
                clz._logger.debug(f'get_next_trailer called')
                status, trailer = FrontendBridge.get_next_trailer()
                clz._logger.debug(f'Got status: {status} trailer: {trailer}')
                if trailer is not None and Debug.validate_detailed_movie_properties(
                        trailer):
                    added = False
                    if status == FrontendBridgeStatus.BUSY:
                        trailer.set_starving(True)
                    while not added:
                        try:
                            self._pre_fetched_trailer_queue.put(trailer, timeout=0.1)
                            added = True
                        except queue.Full:
                            if Monitor.throw_exception_if_abort_requested(timeout=0.5):
                                break
        except AbortException:
            pass  # In thread, let die
        except Exception as e:
            clz._logger.exception(e)

    # Put movie in recent history. If full, delete oldest
    # entry. User can traverse backwards through shown
    # trailers

    def queue_previous_trailer(self) -> None:
        """
        The next trailer returned by get_next_trailer will be the
        logically previous trailer from our queue of trailers
        :return:
        """

        # TODO: probably not needed
        clz = type(self)
        #  clz._logger.enter()
        self._play_state = TrailerPlayState.PLAY_PREVIOUS_TRAILER
        self._changed = True

    def queue_next_trailer(self) -> None:
        """
         The next trailer returned by get_next_trailer
         will be the logically next trailer from our queue of trailers
        :return:
        """

        # TODO: probably not needed
        clz = type(self)
        #  clz._logger.enter()
        self._play_state = TrailerPlayState.PLAY_NEXT_TRAILER
        self._changed = True

    def queue_curtain(self, curtain_type):
        clz = type(self)
        if curtain_type == MovieManager.OPEN_CURTAIN:
            self._play_state = TrailerPlayState.PLAY_OPEN_CURTAIN_NEXT
        elif curtain_type == MovieManager.CLOSE_CURTAIN:
            self._play_state = TrailerPlayState.PLAY_CLOSE_CURTAIN_NEXT
        else:
            if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                clz._logger.debug('Must specify OPEN or CLOSE curtain')
            raise LogicError()

        self._changed = True


class TrailerPlayEvent(threading.Thread):
    def __init__(self):
        pass

    def run(self) -> None:
        pass

    def cancel_event(self):
        pass
