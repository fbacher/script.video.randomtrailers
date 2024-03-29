# -*- coding: utf-8 -*-

"""
Created on Jul 29, 2021

@author: Frank Feuerbacher

"""
import sys
import time
from collections import deque, OrderedDict
from enum import auto, Enum
import threading

from common.exceptions import AbortException
from common.imports import *
from common.movie import AbstractMovie
from common.playlist import Playlist
from common.logger import LazyLogger, Trace
from common.messages import Messages
from common.monitor import Monitor
from common.settings import Settings
from frontend.dialog_utils import (MovieDetailsTimer, NotificationTimer,
                                   TrailerStatus, TrailerTimer)
from frontend.front_end_exceptions import (SkipMovieException, StopPlayingGroup,
                                           UserExitException)
from frontend.history_list import HistoryList
from frontend.abstract_dialog_state import BaseDialogStateMgr, DialogState
from player.my_player import MyPlayer
from frontend.movie_manager import MovieManager, MovieStatus
from frontend.history_empty import HistoryEmpty
from frontend.utils import ReasonEvent

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)
SKIP_NOTIFICATION_SECONDS: int = 5


class DialogStateMgr(BaseDialogStateMgr):

    _logger: LazyLogger = None
    _dialog_state: DialogState = DialogState.NORMAL
    _trailer_dialog: ForwardRef('frontend.TrailerDialog') = None

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)
            BaseDialogStateMgr._real_manager = cls

    @classmethod
    def is_random_trailers_play_state(cls,
                                      minimum_exit_state: DialogState =
                                      DialogState.GROUP_QUOTA_REACHED,
                                      exact_match: bool = False,
                                      throw_exception_on_abort: bool = True
                                      ) -> bool:
        """
            Checks the current state of random trailers plugin against default
            or passed in values.

            Note that a check for Abort state is performed on each
            call.

            A return value of True indicating whether specified state has been
            reached.

        :param minimum_exit_state: Return True if DialogState is at least this value
        :param exact_match: Only return True if DialogState is exactly this value
        :param throw_exception_on_abort: Throw AbortException
                instead, as appropriate.
        :return:
        """
        match = False
        if Monitor is None or Monitor.is_abort_requested():
            cls._dialog_state = DialogState.SHUTDOWN

        if cls._dialog_state == DialogState.SHUTDOWN:
            if throw_exception_on_abort and Monitor is not None:
                Monitor.throw_exception_if_abort_requested()
            else:
                match = True
        elif exact_match:
            match = cls._dialog_state == minimum_exit_state
        else:
            match = cls._dialog_state >= minimum_exit_state
        return match

    @classmethod
    def set_random_trailers_play_state(cls, dialog_state: DialogState) -> None:
        # TODO: Change to use named int type
        """

        :param dialog_state:
        :return:
        """

        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls._logger.debug_extra_verbose(f'state: {dialog_state}',
                                            trace=Trace.TRACE_SCREENSAVER)

        if dialog_state > cls._dialog_state:
            cls._dialog_state = dialog_state

        if dialog_state >= DialogState.SHUTDOWN_CUSTOM_PLAYER:
            TaskLoop.get_player().set_callbacks(on_show_info=None)
            TaskLoop.get_player().disable_advanced_monitoring()
            cls.get_trailer_dialog()._player_container.use_dummy_player()
            TrailerStatus.opaque()

        if dialog_state >= DialogState.USER_REQUESTED_EXIT:
            # Stop playing movie.

            # Just in case we are paused
            TaskLoop.get_player().resume_play()

            # TODO: There may be more to this...
            try:
                MovieDetailsTimer.cancel('User Requested Exit', cancel_callback=None)
            except Exception:
                pass  # Ignore, probably received AbortException
            try:
                TrailerTimer.cancel('User Requested Exit', cancel_callback=None,
                                    stop_play=True)
            except Exception:
                pass  # Ignore, probably received AbortException

        # Multiple groups can be played before exiting. Allow
        # them to be reset back to normal.

        if cls._dialog_state == DialogState.GROUP_QUOTA_REACHED:
            cls._dialog_state = dialog_state

        cls.get_trailer_dialog()._wait_event.set(ReasonEvent.RUN_STATE_CHANGE)


DialogStateMgr.class_init()


class Task(Enum):
    QUEUE_NEXT_TRAILER = auto()
    QUEUE_PREV_TRAILER = auto()

    # Get the next trailer queued to play (don't actually _start play)

    GET_TRAILER = auto()
    SHOW_DETAILS = auto()
    SHOW_DETAILS_NEXT_TRAILER = auto()
    SHOW_DETAILS_PREVIOUS_TRAILER = auto()
    SHOW_DETAILS_USER_REQUEST = auto()
    SHOW_DETAILS_FINISHED = auto()
    # CHANGE_TRAILER = auto()
    PLAY_TRAILER = auto()
    PLAY_TRAILER_FINISHED = auto()
    PLAY_USER_REQUEST = auto()
    PLAY_MOVIE = auto()
    PAUSE_PLAY_MOVIE = auto()
    EXIT = auto()
    ADD_TO_PLAYLIST = auto()
    NOTIFY = auto()
    ADD_COUCH_POTATO = auto()
    USER_EXIT = auto()


class TaskQueue(deque):

    _logger: LazyLogger = None
    instance: ForwardRef('TaskQueue') = None
    lock: threading.RLock = threading.RLock()

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)
            cls.instance: deque = deque(maxlen=HistoryList.MAX_HISTORY + 1)


class TaskLoop(threading.Thread):
    TASKS = (
        Task.SHOW_DETAILS,
        Task.SHOW_DETAILS_NEXT_TRAILER,
        Task.SHOW_DETAILS_PREVIOUS_TRAILER,
        Task.SHOW_DETAILS_USER_REQUEST,
        Task.SHOW_DETAILS_FINISHED,
        Task.PLAY_TRAILER,
        Task.PLAY_USER_REQUEST,
        Task.QUEUE_NEXT_TRAILER,
        Task.QUEUE_PREV_TRAILER,
        Task.GET_TRAILER,
        Task.PLAY_TRAILER_FINISHED,
        Task.PLAY_MOVIE,
        Task.EXIT
    )
    TASKS_WITH_ARG = (
        Task.NOTIFY,
        Task.ADD_TO_PLAYLIST
    )

    ALL_TASKS = TASKS + TASKS_WITH_ARG

    QUEUE_OPERATIONS = (Task.QUEUE_NEXT_TRAILER, Task.QUEUE_PREV_TRAILER)

    _logger: LazyLogger = None
    _worker_thread: ForwardRef('TaskLoop') = None
    _movie_manager: MovieManager = None
    _trailer_dialog: ForwardRef('TrailerDialog') = None
    _last_skip_notification_seconds: float = 0.0

    # TODO: I really dislike this. Used to pass Tasks via kwargs.
    #       kwargs must be strings. So convert to string then back again. Ugh!

    _task_for_name: None

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)
            cls._logger.enter()

            # Last time since Epoch that a notification was issued for
            # skipping trailers

            cls._task_for_name = {}
            for task in cls.ALL_TASKS:
                cls._task_for_name[task.name] = task

            TaskQueue.class_init()

    def __init__(self, name: str = None) -> None:
        # def __init__(self, group=None, target=None, name=None,
        #              args=(), kwargs=None, *, daemon=None):
        clz = type(self)
        clz._logger.enter()
        super().__init__(name=name)

        self._future_details_timed: bool = False
        self._future_details_visible: bool = False
        self._future_trailer_visible = False
        self._notification_visible = False
        self._notification_msg = None
        self._current_movie: AbstractMovie = None
        # self._trailer_changed: bool = False
        self._movie: AbstractMovie = None
        self._dialog_state: DialogState = DialogState.NORMAL
        self._number_of_trailers_played = 0
        self._finished: threading.Event = threading.Event()
        self._trailer_playing: bool = False
        self._viewed_playlist: Playlist = Playlist.get_playlist(
                Playlist.VIEWED_PLAYLIST_FILE, append=True, rotate=False)
        self._viewed_playlist.add_timestamp()

        # Playing a trailer is multi-step

        self._trailer_almost_playing: bool = False

    @classmethod
    def start_playing_trailers(cls):
        cls._logger.enter()
        cls._worker_thread = TaskLoop(name='TaskLoop')
        cls._worker_thread.start()
        cls._worker_thread._finished.wait()

    @classmethod
    def get_worker_thread(cls) -> ForwardRef('TaskLoop'):
        return cls._worker_thread

    @classmethod
    def add_task(cls, *args: Task, **kwargs) -> None:
        """
        Adds one or more tasks to the queue.

        Tasks can be either in args or kwargs.
        When args contains tasks, kwargs contains optional arguments for the
        tasks (you have to know the proper keyword, etc.).

        When kwargs contains tasks it is of the form Task: None | List of args
          (As of python 3.6, kwarg order is preserved)

        :param args:
        :param kwargs:
        :return:
        """
        with TaskQueue.lock:

            # kwarg keywords MUST be strings, so Tasks are passed as Task.name
            # Convert them back to Tasks (cause I prefer that over names).

            my_kwargs = OrderedDict()
            for kwarg in kwargs:
                task: Task = cls._task_for_name.get(kwarg, None)
                if task is None:
                    my_kwargs[kwarg] = kwargs.get(kwarg)
                else:
                    my_kwargs[task] = kwargs.get(kwarg)

            # Move all tasks in args to kwargs

            if len(args) > 0:
                # Verify that someone is not trying to have Tasks in both
                # args and kwargs (order of args would be lost).
                for task in my_kwargs:
                    if task in cls.ALL_TASKS:
                        cls._logger.error(f'Can not pass Tasks through args and kwargs')
                        return

            # Convert to simple task without args

            for task in args:
                my_kwargs[task] = None

            for task in my_kwargs:
                # Since users can pass arguments to a task via kwargs, we need
                # to skip over any invalid Tasks.
                #
                # TODO: consider getting rid of passing random args as kwargs
                #       items

                if task not in cls.ALL_TASKS:
                    continue

                if my_kwargs[task] is not None:
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                        cls._logger.debug_extra_verbose(f'args to Tasks not yet '
                                                        f'supported. Args ignored')

                if task in cls.TASKS:
                    if task == Task.USER_EXIT:
                        # Handle now
                        TaskQueue.instance.clear()

                    elif task == Task.GET_TRAILER:
                        # Sequence of: QUEUE_XX, GET_TRAILER, SHOW_TRAILER
                        # Purge everything but QUEUE* entries from queue
                        tasks_to_keep = []
                        for existing_task in TaskQueue.instance:
                            if existing_task in TaskLoop.QUEUE_OPERATIONS:
                                tasks_to_keep.append(existing_task)
                            else:
                                cls._logger.debug_extra_verbose(f'purging task '
                                                                 f'{task}')

                        if len(tasks_to_keep) != len(TaskQueue.instance):
                            TaskQueue.instance.clear()
                            TaskQueue.instance.extend(tasks_to_keep)

                if task in cls.TASKS_WITH_ARG:
                    arg: Union[str, int] = None
                    if task == Task.NOTIFY:
                        arg = my_kwargs['msg']
                    if task == Task.ADD_TO_PLAYLIST:
                        arg = my_kwargs['playlist_number']

                    task = (task, arg)

                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'adding task: {task}')
                TaskQueue.instance.append(task)

    def run(self) -> None:
        clz = type(self)
        clz._logger.enter()
        clz._trailer_dialog = DialogStateMgr.get_trailer_dialog()
        clz._movie_manager = clz._trailer_dialog.get_movie_manager()
        try:
            skip_movie: bool = False
            while True:
                if DialogStateMgr.is_random_trailers_play_state(
                        minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                    # Shut her down
                    return

                Monitor.throw_exception_if_abort_requested(0.1)
                self._dialog_state = DialogState.NORMAL
                arg = None
                task:Task = None

                with TaskQueue.lock:
                    if len(TaskQueue.instance) == 0:
                        if not self.is_trailer_playing(debug=False):
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                                clz._logger.debug_extra_verbose(f'pushing request to'
                                                                f' queue_next_trailer')
                            # Insert a trailer to play
                            self.set_trailer_playing(about_to_play=True)
                            self.add_task(Task.QUEUE_NEXT_TRAILER,
                                          Task.GET_TRAILER,
                                          Task.SHOW_DETAILS)
                    else:
                        item = TaskQueue.instance.popleft()
                        if isinstance(item, Tuple):
                            task = item[0]
                            arg = item[1]
                        else:
                            task = item
                            arg = 'no arg'
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz._logger.debug_extra_verbose(f'Popped task: {task} arg: '
                                                            f'{arg}')

                if task is not None: # Got task, did not add
                    if task == Task.QUEUE_NEXT_TRAILER:
                        self.set_trailer_playing(about_to_play=True)
                        clz._movie_manager.queue_next_trailer()

                    elif task == Task.QUEUE_PREV_TRAILER:
                        self.set_trailer_playing(about_to_play=True)
                        clz._movie_manager.queue_previous_trailer()

                    elif task == Task.GET_TRAILER:
                        try:
                            skip_movie = False
                            self._get_trailer()
                        except (HistoryEmpty, SkipMovieException):
                            skip_movie = True

                    elif task == Task.SHOW_DETAILS:
                        #
                        # Showing movie details as a result of automatic 'show next'
                        # behavior, or as a result of user pressing RIGHT or LEFT.
                        #
                        if skip_movie:
                            #
                            # There is no trailer to show, just keep showing
                            # whatever is on screen (with a notification, done
                            # elsewhere).
                            #
                            continue

                        # Normally redundant, but here to prevent automatically
                        # inserting queue-get-show next trailer when task queue
                        # is empty. This occurs when user enters RIGHT or LEFT
                        # button to advance/replay trailer

                        self.set_trailer_playing(about_to_play=True,
                                                 playing=False)
                        self._set_future_visibility(details_visible=True,
                                                    details_timed=True)
                        self._trailer_dialog.update_detail_view(self._movie)
                        self._show_details()

                    elif task == Task.SHOW_DETAILS_NEXT_TRAILER:
                        #
                        # User pressed RIGHT (advance to next trailer) button.
                        # Cancel any display of details or playing trailer, then
                        # show details of next trailer

                        MovieDetailsTimer.cancel(reason='RIGHT to play next trailer',
                                                 stop_play=True)
                        TrailerTimer.cancel(reason='RIGHT to play next trailer',
                                            stop_play=True)

                        TaskLoop.add_task(Task.QUEUE_NEXT_TRAILER,
                                          Task.GET_TRAILER, Task.SHOW_DETAILS)

                    elif task == Task.SHOW_DETAILS_PREVIOUS_TRAILER:
                        #
                        # User pressed RIGHT (advance to next trailer) button.
                        # Cancel any display of details or playing trailer, then
                        # show details of next trailer

                        MovieDetailsTimer.cancel(reason='RIGHT to play next trailer')
                        TrailerTimer.cancel(reason='RIGHT to play next trailer',
                                            stop_play=True)

                        TaskLoop.add_task(Task.QUEUE_PREV_TRAILER,
                                          Task.GET_TRAILER, Task.SHOW_DETAILS)

                    elif task == Task.SHOW_DETAILS_USER_REQUEST:
                        #
                        # Showing details as result of user pressing SHOW_INFO.
                        # There is no time limit for displaying details when
                        # SHOW_INFO is used.

                        if skip_movie:
                            #
                            # There is no trailer to show, just keep showing
                            # whatever is on screen (with a notification, done
                            # elsewhere).
                            #
                            continue

                        self._set_future_visibility(details_visible=True,
                                                    details_timed=False)
                        # self._trailer_dialog.update_detail_view(self._movie)
                        self._show_details()

                    elif task == Task.SHOW_DETAILS_FINISHED:
                        self.set_trailer_playing(about_to_play=True,
                                                 playing=False)
                        if not self.is_trailer_playing(actively_playing=True):
                            # Actually play trailer now that display of details
                            # is over

                            self.add_task(Task.PLAY_TRAILER)

                        # self._set_future_visibility(details_visible=True,
                        #                             details_timed=True)
                        # self._trailer_dialog.update_detail_view(self._movie)
                        # self._show_details()

                    # elif task == Task.CHANGE_TRAILER:
                    #     self._set_trailer_changed()
                    #     self._set_future_visibility(details_visible=False)

                    elif task == Task.PLAY_TRAILER:
                        # Automated play trailer, which occurs after automated
                        # Show Details. Both have time limits. Baring user input
                        # the cycle will continue: get trailer, show details,
                        # play trailer.
                        #
                        # An Exception is raised if there is any issue about playing
                        # the trailer.

                        self.confirm_playable()
                        self._play_trailer()

                    elif task == Task.PLAY_TRAILER_FINISHED:
                        self.get_player().stop()
                        self.set_trailer_playing(playing=False, about_to_play=False)

                    elif task == Task.PLAY_USER_REQUEST:
                        #
                        # Playing trailer as a result of SHOW_INFO. With SHOW_INFO,
                        # the trailer is paused/resumed which switching between trailer
                        # and details views.

                        if self.is_trailer_playing(actively_playing=True):
                            # Cancels DetailsTimer and creates new TrailerTimer based
                            # upon remaining trailer time

                            self._resume_play()
                        else:
                            # Can't resume what hasn't been started
                            MovieDetailsTimer.cancel(reason='SHOW_INFO play trailer')

                            self.add_task(Task.PLAY_TRAILER)

                    elif task == Task.PLAY_MOVIE:
                        # Immediate action
                        self._play_current_movie()

                    elif task == Task.PAUSE_PLAY_MOVIE:
                        # Immediate action
                        self._pause()

                    elif task == Task.EXIT:
                        # Immediate action
                        self._exit_frontend()

                    elif task == Task.ADD_TO_PLAYLIST:
                        # Immediate action
                        self._add_to_playlist(arg)

                    elif task == Task.NOTIFY:
                        self._notify(arg)

                    elif task == Task.ADD_COUCH_POTATO:
                        self._add_to_couch_potato()

                    elif task == Task.USER_EXIT:
                        MovieDetailsTimer.cancel(reason=f'User Exit',
                                                 cancel_callback=None)
                        TrailerTimer.cancel(reason=f'User Exit',
                                            cancel_callback=None, stop_play=True)
                        break # Exit loop

        except SkipMovieException:
            self._logger.exception()
        except UserExitException:
            reraise(*sys.exc_info())
        except HistoryEmpty:
            self._logger.exception()
        except AbortException:
            pass  # Let thread die
        except Exception:
            clz._logger.exception()
        finally:
            if self._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                self._logger.debug_extra_verbose('Exiting')
            self._finished.set()

    def set_trailer_playing(self, playing: bool = None,
                            about_to_play: bool = None) -> None:
        clz = type(self)
        if playing is not None:
            self._trailer_playing = playing
            if not playing:
                self._trailer_almost_playing = playing

        if about_to_play is not None:
            self._trailer_almost_playing = about_to_play

        if self._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose(f'playing: {playing} about_to_play: '
                                            f'{about_to_play} '
                                            f'trailer_playing: {self._trailer_playing} '
                                            f'trailer_almost_playing: '
                                            f'{self._trailer_almost_playing}')

    def is_trailer_playing(self, actively_playing: bool = False,
                           debug: bool = True) -> bool:
        """
        Determines if a trailer is currently playing, or playing is immenant.
        Called frequently

        :param debug: Used to supress debug tracing
        :param actively_playing: If True, then check to see if the trailer is
                                 actively playing now.
                                 If False, then check to see if the trailer is
                                 actively playing soon
        :return:
        """
        clz = type(self)

        trailer_playing: bool = False
        trailer_path: str = ''
        if actively_playing:
            is_normalized: bool = False
            is_cached: bool = False

            # At startup, _movie can be None

            if self._movie is not None:
                is_normalized, is_cached, trailer_path = \
                    self._movie.get_optimal_trailer_path()

            # It is possible that a trailer is about to play, but is not detected
            # by the following, causing incorrect behavior.

            trailer_playing = clz.get_player().is_playing_file(trailer_path)
            if not (actively_playing and trailer_playing):
                clz.get_player().wait_for_is_playing_video(path=trailer_path,
                                                           timeout=5.0)
                trailer_playing = clz.get_player().is_playing_file(trailer_path)

            if debug and clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'actively_playing: {actively_playing} '
                                                f'really playing: {trailer_playing} '
                                                f'should be playing: '
                                                f'{self._trailer_playing} '
                                                f'almost playing: '
                                                f'{self._trailer_almost_playing}')

            if self._trailer_playing and not trailer_playing:
                # trailer_playing = True
                if self._logger.isEnabledFor(LazyLogger.DEBUG):
                    clz._logger.debug(f'Disagreement about trailer playing: '
                                          f'{self._movie.get_title()} ')
        result: bool
        if actively_playing:
            result = trailer_playing
        else:
            result = self._trailer_playing or self._trailer_almost_playing
        if debug and self._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            if self._movie is not None:
                is_normalized, is_cached, trailer_path = \
                    self._movie.get_optimal_trailer_path()
            playing_path = clz.get_player().getPlayingFile()
            clz._logger.debug_extra_verbose(f'actively_playing: {actively_playing} '
                                            f'result: {result} '
                                            f'trailer_path: {trailer_path} '
                                            f'playing_path: {playing_path}')
        return result

    def _hide_all(self) -> None:
        self._future_details_visible = False
        self._future_trailer_visible = False
        self._notification_visible = False
        self._notification_msg = None

    def _set_future_visibility(self, details_visible: bool = True,
                               details_timed: bool = False) -> None:
        if details_visible:
            self._future_details_visible = True
        else:
            self._future_details_visible = False

        if details_timed:
            self._future_details_timed = True
        else:
            self._future_details_timed = False

    def _play_current_movie(self) -> None:
        """
        Play the current movie's movie (not trailer). This will cause
        RandomTrailers to exit

        :return:
        """
        clz = type(self)

        movie_file = self._movie.get_movie_path()
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose(
                f'Playing movie for currently playing trailer.',
                'movie_file:', movie_file, 'source:',
                self._movie.get_source())
        if movie_file == '':
            message = Messages.get_msg(Messages.NO_MOVIE_TO_PLAY)
            NotificationTimer.start_timer(notification_msg=message,
                                          debug_label=self._movie.get_title())
        elif not DialogStateMgr.is_random_trailers_play_state(DialogState.NORMAL):
            message = Messages.get_msg(Messages.PLAYER_IDLE)
            NotificationTimer.start_timer(notification_msg=message,
                                          debug_label=self._movie.get_title())
        else:
            clz._trailer_dialog.queue_movie(self._movie)
            DialogStateMgr.set_random_trailers_play_state(
                DialogState.START_MOVIE_AND_EXIT)
            MovieDetailsTimer.cancel(reason=f'Cancel playing trailer to play movie',
                                     cancel_callback=None)
            TrailerTimer.cancel(reason=f'Cancel playing trailer to play movie',
                                cancel_callback=None, stop_play=True)

    def _play(self) -> None:
        clz = type(self)
        if self.get_player() is not None and self.get_player().is_paused():
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'Resuming Play',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            self.get_player().resume_play()

    def _pause(self) -> None:
        clz = type(self)
        if self.get_player() is not None and self.get_player().isPlaying():
            # Pause playing trailer
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'Pausing Player',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            self.get_player().pause_play()

    def _show_details(self):
        """
        Show the details of the current movie

        :return:
        """
        clz = type(self)

        if ((DialogStateMgr.is_random_trailers_play_state(
                DialogState.NO_TRAILERS_TO_PLAY, exact_match=True))
                and clz._trailer_dialog.is_movie_details_visible()):
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'Not re-displaying unchanged movie '
                                                f'details.')
            return

        # In case user requested to advance to a new movie, or revert to a previous
        # movie before the current one is finished. It won't harm anything to
        # pause, even if nothing is playing.

        self._pause()
        TrailerTimer.cancel(reason='to show details')

        missing_movie_details: bool = self._movie.is_folder_source()
        detail_info_display_seconds: int
        if self._future_details_timed:
            detail_info_display_seconds = Settings.get_time_to_display_detail_info()
        else:
            detail_info_display_seconds = 60 * 60 * 24 * 365

        show_movie_details = (not missing_movie_details and
                              detail_info_display_seconds > 0)
        if show_movie_details:
            scroll_plot = not self._movie.is_tfh()
            clz._logger.debug_extra_verbose(f'About to show details for:'
                                            f' {self._movie.get_title()}')
            MovieDetailsTimer.start_timer(scroll_plot=scroll_plot,
                                          display_seconds=detail_info_display_seconds,
                                          debug_label=self._movie.get_title(),
                                          callback_on_stop=
                                          clz.callback_show_details_finished)
            if self._movie.is_starving():
                # Starving flag cleared on above query
                NotificationTimer.start_timer(notification_msg=
                                              f'Having difficulty preparing '
                                              f'trailers to play. May see '
                                              f'repeats.',
                                              debug_label=self._movie.get_title())

    @classmethod
    def callback_show_details_finished(cls, stop_play: bool = False):
        """
        Callback routine
        :param stop_play:
        :return:
        """
        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls._logger.debug_extra_verbose(f'enter')
        cls.add_task(Task.SHOW_DETAILS_FINISHED)

    def _play_trailer(self):
        """
        Automatically play prefetched trailer (not caused by user input).

        :return:
        """
        clz = type(self)

        TrailerTimer.cancel(reason=f'play next trailer',
                            stop_play= True) # not playing_current_trailer)

        self.set_trailer_playing(playing=True)

        worker = threading.Thread(target=self._play_trailer_worker,
                                  args=(self._movie, self.play_trailer_finished),
                                  name='TrailerPlayer.play_trailer')
        worker.start()

    def _play_trailer_worker(self, *args):
        """
        Play a trailer automatically (not as a result of a user action).

        RandomTrailers automatic behavior is to:
            get the next trailer ready to play
            Show the details of the trailer for xx seconds
            Play the trailer for yy seconds
            Repeat

        This method is responsible for playing the trailer. It runs in a separate
        thread because it must wait until the trailer actually finishes, or is
        stopped by it's time limit.

        :param args: Contains the trailer to be played and a callback to be
                     called when complete.
        :return:
        """
        clz = type(self)
        movie: AbstractMovie = args[0]
        callback: Callable[[], None] = args[1]
        try:
            # Start playing the trailer

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'_start playing: '
                                                f'{movie.get_title()}',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            is_normalized, is_cached, trailer_path = movie.get_optimal_trailer_path()
            clz.get_player().play_trailer(trailer_path, movie)

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'wait for trailer to _start playing: '
                                                f'{movie.get_title()}',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            # Confirm that trailer is playing

            if not self.get_player().wait_for_is_playing_video(path=trailer_path,
                                                               timeout=5.0):
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose('Timed out Waiting for Player.',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
            else:

                # Kick off the timer which will limit how long the trailer plays

                trailer_play_time: float
                trailer_play_time = float(Settings.get_max_trailer_play_seconds())
                TrailerTimer.start_timer(display_seconds=trailer_play_time,
                                         debug_label=self._movie.get_title(),
                                         callback_on_stop=callback)

                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(f'Waiting for trailer to stop playing')

                # Wait until trailer completes, or is killed by the timer

                clz.get_player().wait_for_is_not_playing_video(path=trailer_path)
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(f'Finished playing trailer:'
                                                    f' {movie.get_title()}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)

                # Cancel max-play-time timer, unless it killed the playing of the trailer

                TrailerTimer.cancel(reason=f'Exceeded max playback time',
                                    cancel_callback=callback, stop_play=True)

        except AbortException:
            pass  # Let thread die

        except Exception:
            clz._logger.exception()

    def play_trailer_finished(self, stop_play: bool = False):
        clz = type(self)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose(f'enter')
        clz.add_task(Task.PLAY_TRAILER_FINISHED)

    def _resume_play(self):
        clz = type(self)
        trailer_play_time: float
        trailer_play_time = float(Settings.get_max_trailer_play_seconds())
        trailer_play_time -= clz.get_player().getTime()
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose(f'played time: {clz.get_player().getTime()} '
                                            f'remaining_time: {trailer_play_time}',
                                            trace=Trace.TRACE_UI_CONTROLLER)

        MovieDetailsTimer.cancel(reason='SHOW_INFO, resume play')
        TrailerTimer.start_timer(callback_on_stop=self.play_trailer_finished,
                                 display_seconds=trailer_play_time,
                                 debug_label=self._movie.get_title())
        clz.get_player().resume_play()

    def _exit_frontend(self) -> None:
        clz = type(self)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('Exit application',
                                            trace=Trace.TRACE_SCREENSAVER)

            # Ensure we are not blocked

        DialogStateMgr.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)
        MovieDetailsTimer.cancel(reason=f'exit plugin')
        TrailerTimer.cancel(f'exit plugin', stop_play=True)

    def _add_to_playlist(self, playlist_number: int) -> None:
        """

        :param action_id:
        :param movie:
        :return:
        """
        clz = type(self)
        playlist_name = Settings.get_playlist_name(playlist_number)
        if playlist_name is None or playlist_name == '':
            message: str = Messages.get_formatted_msg(Messages.NOT_A_PLAYLIST,
                                                      str(playlist_number))
            NotificationTimer.start_timer(notification_msg=message,
                                          debug_label=self._movie.get_title())
        else:
            added = Playlist.get_playlist(playlist_name,
                                          playlist_format=True).add_to_smart_playlist(
                    self._movie)
            if added:
                message: str = Messages.get_formatted_msg(
                        Messages.MOVIE_ADDED_TO_PLAYLIST, playlist_name)
            else:
                message: str = Messages.get_formatted_msg(
                        Messages.MOVIE_ALREADY_ON_PLAYLIST, playlist_name)
            NotificationTimer.start_timer(notification_msg=message,
                                          debug_label=self._movie.get_title())

    def _notify(self, msg: str = None) -> None:
        self._notification_msg = msg
        title = ''
        if self._movie is not None:
            title = self._movie.get_title()

        NotificationTimer.start_timer(notification_msg=msg, debug_label=title)

    def _add_to_couch_potato(self) -> None:
        # Immediate Action
        pass

    def _make_changes(self, more_tasks: bool) -> None:
        """
        Update UI to reflect changes. May choose to delay update of
        some items based upon more tasks to examine.

        :param more_tasks:
        :return:
        """
        clz = type(self)

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            clz._logger.debug_verbose(f'got trailer to play: '
                                      f'{self._movie.get_title()}')

        video_is_curtain: bool = (self._movie.get_source() == 'curtain')

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('wait for not playing 1')

        _, _, trailer_path = self._movie.get_optimal_trailer_path()
        clz.get_player().wait_for_is_not_playing_video(path=trailer_path)

        self._future_details_timed: bool = False
        self._future_details_visible: bool = False
        self._future_trailer_visible = False
        self._notification_visible = False
        self._notification_msg = None
        self._current_movie: AbstractMovie = None

    def _get_trailer(self) -> None:
        clz = type(self)
        next_movie: AbstractMovie = None
        try:
            attempts: int = 100
            timeout: float = 0.2
            while attempts > 0:
                try:
                    attempts += 1
                    if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                        clz._logger.debug_extra_verbose(f'In _get_trailer')
                    next_movie_status, next_movie = clz._movie_manager.get_next_trailer()

                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(f'status: {next_movie_status} '
                                                        f'movie: '
                                                        f'{next_movie}')
                    # Are there no trailers to play now, and in the future?

                    if next_movie_status == MovieStatus.OK and next_movie is None:
                        DialogStateMgr.set_random_trailers_play_state(
                                DialogState.NO_TRAILERS_TO_PLAY)
                        raise SkipMovieException()  # Try again

                    elif next_movie_status == MovieStatus.IDLE:
                        DialogStateMgr.set_random_trailers_play_state(
                                DialogState.NO_TRAILERS_TO_PLAY)
                        clz._logger.error('Should not get state IDLE')
                        raise StopPlayingGroup()

                    # TODO: User feedback instead of blank screen?

                    if next_movie_status == MovieStatus.TIMED_OUT:
                        DialogStateMgr.set_random_trailers_play_state(
                                DialogState.NO_TRAILERS_TO_PLAY)
                        raise SkipMovieException()  # Try again

                    if next_movie_status == MovieStatus.BUSY:
                        if next_movie is None:
                            DialogStateMgr.set_random_trailers_play_state(
                                    DialogState.NO_TRAILERS_TO_PLAY)
                            raise SkipMovieException()  # Try again
                        else:
                            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                                clz._logger.debug_extra_verbose(
                                    f'status: {next_movie_status} '
                                    f'movie: '
                                    f'{next_movie}')

                    DialogStateMgr.set_random_trailers_play_state(
                            DialogState.NORMAL)
                    self._movie = next_movie
                    self._viewed_playlist.record_played_trailer(self._movie)
                    self._movie_status = next_movie_status
                    break

                except AbortException:
                    reraise(*sys.exc_info())

                except HistoryEmpty:
                    # This is pre-checked when user input occurs, but perhaps under
                    # the right timing it could happen?

                    msg = Messages.get_msg(Messages.NO_MORE_MOVIE_HISTORY)
                    self._notify(msg=msg)
                    reraise(*sys.exc_info())

                except SkipMovieException:
                    # Notify every few seconds

                    delta: int = int(time.time() - clz._last_skip_notification_seconds)
                    if delta > SKIP_NOTIFICATION_SECONDS:
                        clz._logger.debug_extra_verbose(f'Skipping Movie')
                        self._notify(msg="Skipping Movie")
                        clz._last_skip_notification_seconds = time.time()

                    reraise(*sys.exc_info())

                except StopPlayingGroup:
                    clz._logger.debug_extra_verbose(f'Stop Playing Group')
                    self._notify(msg="Exiting RandomTrailers")
                    reraise(*sys.exc_info())

                except Exception:
                    clz._logger.exception()

                Monitor.throw_exception_if_abort_requested(timeout=timeout)
                attempts += 1
                if attempts == 20:
                    NotificationTimer.start_timer(notification_msg=
                                                  'Waiting for movie data.',
                                                  debug_label=self._movie.get_title())
                    timeout = 0.5
        finally:
            if next_movie is None:
                DialogStateMgr.set_random_trailers_play_state(
                        DialogState.NO_TRAILERS_TO_PLAY)
                self.set_trailer_playing(about_to_play=False,
                                         playing=False)

    def confirm_playable(self) -> None:
        """
        Verify that there is nothing impacting the playability of next trailer.

        Possible reasons: User Requested exit, Trailer to be Skipped do to some action

        :return:
        """
        clz = type(self)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('checking play_state 2 movie:',
                                            self._movie.get_title())
        if DialogStateMgr.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                        exact_match=True):
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'SKIP_PLAYING_TRAILER: '
                                                f'{self._movie.get_title()}',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            raise SkipMovieException()
        if DialogStateMgr.is_random_trailers_play_state(
                minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(
                        'Breaking due to play_state 2 movie:',
                        self._movie.get_title(),
                        trace=Trace.TRACE_UI_CONTROLLER)
            raise UserExitException()

        if self._dialog_state == DialogState.SHUTDOWN:  # Exit group
            raise StopPlayingGroup()

    def skip_trailer(self) -> bool:
        clz = type(self)
        return DialogStateMgr.is_random_trailers_play_state(
                DialogState.SKIP_PLAYING_TRAILER,
                exact_match=True)

    @classmethod
    def get_player(cls) -> MyPlayer:
        return DialogStateMgr.get_trailer_dialog().get_player()
