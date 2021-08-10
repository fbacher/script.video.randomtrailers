# -*- coding: utf-8 -*-

"""
Created on Jul 29, 2021

@author: Frank Feuerbacher

"""
import datetime
from collections import deque
from enum import auto, Enum
import sys
import threading

from common.imports import *
from common.movie import AbstractMovie
from common.playlist import Playlist
from common.logger import LazyLogger, Trace
from common.messages import Messages
from common.monitor import Monitor
from common.settings import Settings
from frontend.dialog_utils import (MovieDetailsTimer, NotificationTimer, TrailerPlayer,
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

            MovieDetailsTimer.cancel('User Requested Exit', callback=None)
            TrailerTimer.cancel('User Requested Exit', callback=None,
                                stop_play=True)

        # Multiple groups can be played before exiting. Allow
        # them to be reset back to normal.

        if cls._dialog_state == DialogState.GROUP_QUOTA_REACHED:
            cls._dialog_state = dialog_state

        # if dialog_state > self._dialog_state:
        #     self._dialog_state = dialog_state
        cls.get_trailer_dialog()._wait_event.set(ReasonEvent.RUN_STATE_CHANGE)


DialogStateMgr.class_init()


class Task(Enum):
    QUEUE_NEXT_TRAILER = auto(),
    QUEUE_PREV_TRAILER = auto(),

    # Get the next trailer queued to play (don't actually start play)

    GET_TRAILER = auto(),
    SHOW_DETAILS = auto(),
    SHOW_DETAILS_USER_REQUEST = auto(),
    SHOW_DETAILS_FINISHED = auto(),
    CHANGE_TRAILER = auto(),
    PLAY_TRAILER = auto(),
    PLAY_TRAILER_FINISHED = auto(),
    RESUME_PLAY = auto(),
    PLAY_MOVIE = auto(),
    PAUSE_PLAY_MOVIE = auto(),
    EXIT = auto(),
    ADD_TO_PLAYLIST = auto(),
    NOTIFY = auto(),
    ADD_COUCH_POTATO = auto()


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
        Task.SHOW_DETAILS_USER_REQUEST,
        Task.SHOW_DETAILS_FINISHED,
        Task.PLAY_TRAILER,
        Task.RESUME_PLAY,
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
    QUEUE_OPERATIONS = (Task.QUEUE_NEXT_TRAILER, Task.QUEUE_PREV_TRAILER)

    _logger: LazyLogger = None
    _worker_thread: ForwardRef('TaskLoop') = None
    _movie_manager: MovieManager = None
    _trailer_dialog: ForwardRef('TrailerDialog') = None

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)
            cls._logger.enter()
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
        self._trailer_changed: bool = False
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
        with TaskQueue.lock:
            for task in args:
                if task is None:
                    return

                if len(args) > 1 and len(kwargs) > 1:
                    cls._logger.error(f'Maximum of one *args if **kwargs specified')
                    return

                if task in cls.TASKS:
                    cls._logger.debug(f'adding task: {task}')
                    if task == Task.GET_TRAILER:
                        # Purge everything but QUEUE* entries from queue
                        tasks_to_keep = []
                        for existing_task in TaskQueue.instance:
                            if existing_task in TaskLoop.QUEUE_OPERATIONS:
                                tasks_to_keep.append(existing_task)

                        if len(tasks_to_keep) != len(TaskQueue.instance):
                            TaskQueue.instance.clear()
                            TaskQueue.instance.extend(tasks_to_keep)
                    TaskQueue.instance.append(task)

                if task in cls.TASKS_WITH_ARG:
                    arg: Union[str, int] = None
                    if task == Task.NOTIFY:
                        arg = kwargs['msg']
                    if task == Task.ADD_TO_PLAYLIST:
                        arg = kwargs['playlist_number']

                    cls._logger.debug(f'adding task: {task}')
                    TaskQueue.instance.append((task, arg))

    def run(self) -> None:
        clz = type(self)
        clz._logger.enter()
        clz._trailer_dialog = DialogStateMgr.get_trailer_dialog()
        clz._movie_manager = clz._trailer_dialog.get_movie_manager()
        clz._logger.debug(f'Completed get_dialog is_set: '
                          f'{clz._worker_thread._finished.is_set()}')
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
                        if not self.is_playing_trailer():
                            clz._logger.debug('pushing request to queue_next_trailer')
                            # Insert a trailer to play
                            self.playing_trailer(about_to_play=True,
                                                 playing=False)
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
                        clz._logger.debug(f'Popped task: {task} arg: {arg}')

                if task is not None: # Got task, did not add
                    if task == Task.QUEUE_NEXT_TRAILER:
                        clz._logger.debug('popped request for queue_next_trailer')
                        self.playing_trailer(about_to_play=True,
                                             playing=False)
                        clz._movie_manager.queue_next_trailer()

                    elif task == Task.QUEUE_PREV_TRAILER:
                        clz._logger.debug('popped request for queue_previous')
                        clz._movie_manager.queue_previous_trailer()

                    elif task == Task.GET_TRAILER:
                        try:
                            clz._logger.debug('popped request for get_trailer')
                            skip_movie = False
                            self._get_trailer()
                        except (HistoryEmpty, SkipMovieException):
                            skip_movie = True

                    elif task == Task.SHOW_DETAILS:
                        clz._logger.debug('popped request for show_details')
                        if skip_movie:
                            #
                            # There is no trailer to show, just keep showing
                            # whatever is on screen (with a notification, done
                            # elsewhere).
                            #
                            continue

                        self._set_future_visibility(details_visible=True,
                                                    details_timed=True)
                        self._trailer_dialog.update_detail_view(self._movie)
                        self._show_details()

                    elif task == Task.SHOW_DETAILS_USER_REQUEST:
                        clz._logger.debug('popped request for show_details_user_request')
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
                        clz._logger.debug('popped request for show_details_finished')

                        # TODO: Had to disable due to manual cursor_right
                        # broke this.

                        self.playing_trailer(about_to_play=True,
                                             playing=False)
                        if not self.is_playing_trailer(actively_playing=True):
                            # Actually play trailer now that display of details
                            # is over

                            self.add_task(Task.PLAY_TRAILER)

                        # self._set_future_visibility(details_visible=True,
                        #                             details_timed=True)
                        # self._trailer_dialog.update_detail_view(self._movie)
                        # self._show_details()

                    elif task == Task.CHANGE_TRAILER:
                        clz._logger.debug('popped request for change_trailer')
                        self._set_trailer_changed()
                        self._set_future_visibility(details_visible=False)

                    elif task == Task.PLAY_TRAILER:
                        # An Exception is raise if there is any issue about playing
                        # the trailer.

                        clz._logger.debug('popped request for play_trailer')
                        self.confirm_playable()
                        self._play_trailer()

                    elif task == Task.PLAY_TRAILER_FINISHED:
                        clz._logger.debug('popped request for play_trailer_finished')
                        self.playing_trailer(playing=False)

                    elif task == Task.RESUME_PLAY:
                        clz._logger.debug('popped request for resume_play')
                        if self.is_playing_trailer(actively_playing=True):
                            self._resume_play()
                        else:
                            # Can't resume what hasen't been started
                            self.add_task(Task.PLAY_TRAILER)

                    elif task == Task.PLAY_MOVIE:
                        # Immediate action
                        clz._logger.debug('popped request for play_movie')
                        self._play_current_movie()

                    elif task == Task.PAUSE_PLAY_MOVIE:
                        # Immediate action
                        clz._logger.debug('popped request for pause_play_movie')
                        self._pause()

                    elif task == Task.EXIT:
                        # Immediate action
                        clz._logger.debug('popped request for exit')
                        self._exit_frontend()

                    elif task == Task.ADD_TO_PLAYLIST:
                        # Immediate action
                        clz._logger.debug('popped request for add_to_playlist')
                        self._add_to_playlist(arg)

                    elif task == Task.NOTIFY:
                        clz._logger.debug('popped request for notify')
                        self._notify(arg)

                    elif task == Task.ADD_COUCH_POTATO:
                        clz._logger.debug('popped request for add_couch_potato')
                        self._add_to_couch_potato()

                    # clz._logger.debug('popped request for make_changes')
                    # self._make_changes(more_tasks=(len(self._task_queue) > 0))

        except SkipMovieException:
            self._logger.exception()
        except UserExitException:
            reraise(*sys.exc_info())
        except HistoryEmpty:
            self._logger.exception()
        except Exception:
            clz._logger.exception()
        finally:
            self._logger.debug('Exiting')
            self._finished.set()

    def playing_trailer(self, playing: bool = None,
                        about_to_play: bool = None) -> None:
        clz = type(self)
        if playing is not None:
            self._trailer_playing = playing
            if not playing:
                self._trailer_almost_playing = playing

        if about_to_play is not None:
            self._trailer_almost_playing = about_to_play

        clz._logger.debug(f'playing: {playing} about_to_play: {about_to_play} '
                          f'trailer_playing: {self._trailer_playing} '
                          f'trailer_almost_playing: {self._trailer_almost_playing}')

    def is_playing_trailer(self, actively_playing: bool = False) -> bool:
        if actively_playing:
            return self._trailer_playing
        return self._trailer_playing or self._trailer_almost_playing

    def _set_trailer_changed(self) -> None:
        self._hide_all()
        self._trailer_changed = True

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
        # Immediate action
        clz = type(self)

        movie_file = self._movie.get_movie_path()
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose(
                f'Playing movie for currently playing trailer.',
                'movie_file:', movie_file, 'source:',
                self._movie.get_source())
        if movie_file == '':
            message = Messages.get_msg(Messages.NO_MOVIE_TO_PLAY)
            NotificationTimer.config(msg=message)
            NotificationTimer.start()
        elif not DialogStateMgr.is_random_trailers_play_state(DialogState.NORMAL):
            message = Messages.get_msg(Messages.PLAYER_IDLE)
            NotificationTimer.config(msg=message)
            NotificationTimer.start()
        else:
            clz._trailer_dialog.queue_movie(self._movie)
            DialogStateMgr.set_random_trailers_play_state(
                DialogState.START_MOVIE_AND_EXIT)
            MovieDetailsTimer.cancel(f'Cancel playing trailer to play movie',
                                     callback=None)
            TrailerTimer.cancel(f'Cancel playing trailer to play movie',
                                callback=None, stop_play=True)

    def _play(self) -> None:
        clz = type(self)
        if self.get_player() is not None and self.get_player().is_paused():
            clz._logger.debug(f'Resuming Play', trace=Trace.TRACE_UI_CONTROLLER)
            self.get_player().resume_play()

    def _pause(self) -> None:
        clz = type(self)
        if self.get_player() is not None and self.get_player().isPlaying():
            # Pause playing trailer
            clz._logger.debug(f'Pausing Player', trace=Trace.TRACE_UI_CONTROLLER)
            self.get_player().pause_play()

    def _show_details(self):
        clz = type(self)

        if ((DialogStateMgr.is_random_trailers_play_state(
                DialogState.NO_TRAILERS_TO_PLAY, exact_match=True))
                and clz._trailer_dialog.is_movie_details_visible()):
            clz._logger.debug(f'Not re-displaying unchanged movie details.')
            return

        self._pause()
        TrailerTimer.cancel(usage='to show details')
        missing_movie_details: bool = self._movie.is_folder_source()
        detail_info_display_time: int
        if self._future_details_timed:
            detail_info_display_time = Settings.get_time_to_display_detail_info()
        else:
            detail_info_display_time = 60 * 60 * 24 * 365

        show_movie_details = (not missing_movie_details and
                              detail_info_display_time > 0)
        if show_movie_details:
            scroll_plot = not self._movie.is_tfh()

            #  TODO: this appears to be incorrect
            #
            # Kill movie player timer 1) because time is paused on player
            #                         2) timer will interfere with show details
            #
            MovieDetailsTimer.cancel(usage=f'Cancel any previous movie')
            # TrailerTimer.cancel(usage=f'Cancel any previous movie')
            MovieDetailsTimer.config(scroll_plot=scroll_plot,
                                     display_seconds=detail_info_display_time,
                                     callback_on_stop=self.show_details_finished)
            MovieDetailsTimer.start()

    def show_details_finished(self):
        clz = type(self)
        clz._logger.debug(f'enter')
        clz.add_task(Task.SHOW_DETAILS_FINISHED)

    def _play_trailer(self):
        clz = type(self)
        self.playing_trailer(playing=True)
        TrailerPlayer.play_trailer(movie=self._movie,
                                   callback=self.play_trailer_finished)

    def play_trailer_finished(self, stop_play: bool = False):
        clz = type(self)
        clz._logger.debug(f'enter')
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

        MovieDetailsTimer.cancel(usage='SHOW_INFO, resume play')
        TrailerTimer.config(callback_on_stop=self.play_trailer_finished,
                            display_seconds=trailer_play_time)
        clz.get_player().resume_play()
        TrailerTimer.start()

    def _exit_frontend(self) -> None:
        clz = type(self)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('Exit application',
                                            trace=Trace.TRACE_SCREENSAVER)

            # Ensure we are not blocked

        DialogStateMgr.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)
        MovieDetailsTimer.cancel(usage=f'exit plugin')
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
            NotificationTimer.config(msg=message)
        else:
            added = Playlist.get_playlist(playlist_name, playlist_format=True). \
                add_to_smart_playlist(self._movie)
            if added:
                message: str = Messages.get_formatted_msg(
                        Messages.MOVIE_ADDED_TO_PLAYLIST, playlist_name)
            else:
                message: str = Messages.get_formatted_msg(
                        Messages.MOVIE_ALREADY_ON_PLAYLIST, playlist_name)
            NotificationTimer.config(msg=message)

        NotificationTimer.start()

    def _notify(self, msg: str = None) -> None:
        self._notification_msg = msg
        NotificationTimer.config(msg=msg)
        NotificationTimer.start()

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
        clz.get_player().wait_for_is_not_playing_video()

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
                    clz._logger.debug(f'In _get_trailer')
                    next_movie_status, next_movie = clz._movie_manager.get_next_trailer()

                    clz._logger.debug(f'status: {next_movie_status} movie: {next_movie}')
                    # Are there no trailers to play now, and in the future?

                    if next_movie_status == MovieStatus.OK and next_movie is None:
                        DialogStateMgr.set_random_trailers_play_state(
                                DialogState.NO_TRAILERS_TO_PLAY)
                        raise SkipMovieException  # Try again

                    elif next_movie_status == MovieStatus.IDLE:
                        DialogStateMgr.set_random_trailers_play_state(
                                DialogState.NO_TRAILERS_TO_PLAY)
                        clz._logger.warning('Should not get state IDLE')
                        raise StopPlayingGroup()

                    # TODO: User feedback instead of blank screen?

                    if next_movie_status == MovieStatus.TIMED_OUT:
                        DialogStateMgr.set_random_trailers_play_state(
                                DialogState.NO_TRAILERS_TO_PLAY)
                        raise SkipMovieException  # Try again

                    if next_movie_status == MovieStatus.BUSY:
                        DialogStateMgr.set_random_trailers_play_state(
                                DialogState.NO_TRAILERS_TO_PLAY)
                        raise SkipMovieException  # Try again

                    DialogStateMgr.set_random_trailers_play_state(
                            DialogState.NORMAL)
                    self._movie = next_movie
                    self._viewed_playlist.record_played_trailer(self._movie)
                    self._movie_status = next_movie_status
                    break

                except HistoryEmpty:
                    # This is pre-checked when user input occurs, but perhaps under
                    # the right timing it could happen?

                    msg = Messages.get_msg(Messages.NO_MORE_MOVIE_HISTORY)
                    self._notify(msg=msg)
                    reraise(*sys.exc_info())

                except SkipMovieException:
                    clz._logger.debug_extra_verbose(f'Skipping Movie')
                    self._notify(msg="Skipping Movie")
                    reraise(*sys.exc_info())

                except Exception:
                    clz._logger.exception()

                Monitor.throw_exception_if_abort_requested(timeout=timeout)
                attempts += 1
                if attempts == 20:
                    NotificationTimer.config(msg='Waiting for movie data.')
                    NotificationTimer.start()
                    timeout = 0.5
        finally:
            if next_movie is None:
                DialogStateMgr.set_random_trailers_play_state(
                        DialogState.NO_TRAILERS_TO_PLAY)
                self.playing_trailer(about_to_play=False,
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
