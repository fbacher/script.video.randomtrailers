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
from frontend.dialog_utils import (MovieTimer, NotificationTimer, TrailerPlayer,
                                   TrailerStatus)
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

            MovieTimer.cancel_movie_timer('User Requested Exit', callback=None)
            TaskLoop.get_player().stop()

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
                        self._play_pause()

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
            NotificationTimer.add_notification(msg=message)
        elif not DialogStateMgr.is_random_trailers_play_state(DialogState.NORMAL):
            message = Messages.get_msg(Messages.PLAYER_IDLE)
            NotificationTimer.add_notification(msg=message)
        else:
            clz._trailer_dialog.queue_movie(self._movie)
            DialogStateMgr.set_random_trailers_play_state(
                DialogState.START_MOVIE_AND_EXIT)
            MovieTimer.cancel_movie_timer(usage=f'Cancel playing trailer to play movie')

    def _play_pause(self) -> None:
        # Immediate action
        pass

    def _show_details(self):
        clz = type(self)

        if ((DialogStateMgr.is_random_trailers_play_state(
                DialogState.NO_TRAILERS_TO_PLAY, exact_match=True))
                and clz._trailer_dialog.is_movie_details_visible()):
            clz._logger.debug(f'Not re-displaying unchanged movie details.')
            return

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
            player = clz.get_player()
            if player is not None and player.isPlaying():
                # Pause playing trailer
                clz._logger.debug(f'Pausing Player',
                                  trace=Trace.TRACE_UI_CONTROLLER)
                player.pause_play()

            # Kill movie player timer 1) because time is paused on player
            #                         2) timer will interfere with show details
            #
            MovieTimer.cancel_movie_timer(usage=f'hide_trailer')
            MovieTimer.display_movie_details(scroll_plot=scroll_plot,
                                             max_display_time=detail_info_display_time,
                                             from_user_request=False,
                                             wait_for_idle=True,
                                             callback=self.show_details_finished)

    def show_details_finished(self):
        clz = type(self)
        clz._logger.debug(f'enter')
        clz.add_task(Task.SHOW_DETAILS_FINISHED)

    def _play_trailer(self):
        clz = type(self)
        self.playing_trailer(playing=True)
        TrailerPlayer.play_trailer(movie=self._movie,
                                   callback=self.play_trailer_finished)

    def play_trailer_finished(self):
        clz = type(self)
        clz._logger.debug(f'enter')
        clz.add_task(Task.PLAY_TRAILER_FINISHED)

    def _resume_play(self):
        clz = type(self)
        TrailerStatus.set_show_trailer()
        clz.get_player().resume_play()

    def _exit_frontend(self) -> None:
        clz = type(self)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('Exit application',
                                            trace=Trace.TRACE_SCREENSAVER)

            # Ensure we are not blocked

        DialogStateMgr.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)
        MovieTimer.cancel_movie_timer(usage=f'exit plugin')

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
            NotificationTimer.add_notification(msg=message)
        else:
            added = Playlist.get_playlist(playlist_name, playlist_format=True). \
                add_to_smart_playlist(self._movie)
            if added:
                message: str = Messages.get_formatted_msg(
                        Messages.MOVIE_ADDED_TO_PLAYLIST, playlist_name)
                NotificationTimer.add_notification(msg=message)
            else:
                message: str = Messages.get_formatted_msg(
                        Messages.MOVIE_ALREADY_ON_PLAYLIST, playlist_name)
                NotificationTimer.add_notification(msg=message)

    def _notify(self, msg: str = None) -> None:
        self._notification_msg = msg
        NotificationTimer.add_notification(msg=msg)

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
                    self._notify(msg="Skipping Movie")
                    reraise(*sys.exc_info())

                except Exception:
                    clz._logger.exception()

                Monitor.throw_exception_if_abort_requested(timeout=timeout)
                attempts += 1
                if attempts == 20:
                    NotificationTimer.add_notification(msg='Waiting for movie data.')
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
    def get_player(clz) -> MyPlayer:
        return DialogStateMgr.get_trailer_dialog().get_player()

'''
    def xxx(self) -> None:
        """

        :return:
        """
        clz = type(self)

        number_of_trailers_played = 0
        try:
            # Main movie playing loop
            while not clz.trailer_dialog.is_random_trailers_play_state():

                # Get the video (or curtain) to display
                try:
                    self._get_next_trailer_start = datetime.datetime.now()
                    status, self._movie = self._movie_manager.get_next_trailer()
                    # if status == MovieStatus.PREVIOUS_MOVIE:
                    #     msg = Messages.get_msg(
                    #         Messages.PLAYING_PREVIOUS_MOVIE)
                    #     msg = msg % self._movie.get_title()
                    #     self.show_notification(msg)
                except HistoryEmpty:
                    msg = Messages.get_msg(
                            Messages.NO_MORE_MOVIE_HISTORY)
                    NotificationTimer.add_notification(msg=msg)
                    continue

                if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    clz._logger.debug_verbose(f'got trailer to play: '
                                              f'{self._movie.get_title()}')

                video_is_curtain = (self._movie.get_source() == 'curtain')

                # TODO: fix comment
                # Screen will be black since both
                # TrailerDialog.PLAYER_GROUP_CONTROL and
                # ControlId.SHOW_DETAILS are, by default,
                # not visible in script-trailerwindow.xml

                # Wait until previous video is complete.
                # Our event listeners will stop the player, as appropriate.

                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose('wait for not playing 1')
                self.get_player().wait_for_is_not_playing_video()

                # Determine if Movie Title is to be displayed during play of
                # movie

                show_title_while_playing: bool = Settings.get_show_movie_title()

                # Add movie to "playlist"

                if not video_is_curtain:
                    self._viewed_playlist.record_played_trailer(self._movie)

                    # Determine if Movie Information is displayed prior to movie

                self._source = self._movie.get_source()
                show_movie_details = (
                        Settings.get_time_to_display_detail_info() > 0)

                # Trailers from a folder are ill-structured and have no
                # identifying information.

                show_movie_details = not self._movie.is_folder_source()

                if video_is_curtain:
                    show_movie_details = False
                    show_title_while_playing = False

                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                            'checking play_state 1')

                # This will block if showing Movie Details
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                            f'about to show_movie_info movie: {self._movie.get_title()} '
                            f'show_detail: {show_movie_details} '
                            f'show title while playing: {show_title_while_playing} '
                            f'block: {True}',
                            trace=Trace.TRACE_UI_CONTROLLER)

                scroll_plot = not self._movie.is_tfh()
                missing_movie_details: bool = self._movie.is_folder_source()

                TrailerPlayer.show_details_and_play(scroll_plot=scroll_plot,
                                                    block_after_display_details=True,
                                                    missing_movie_details=
                                                    missing_movie_details,
                                                    from_user_request=False)

                if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                    clz._logger.debug_extra_verbose(
                            f'finished show_details_and_play, movie: '
                            f'{self._movie.get_title()}',
                            trace=Trace.TRACE_UI_CONTROLLER)

                # Play Trailer

                # TODO: change to asynchronous so that it can occur while
                # showing details

                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose('checking play_state 2 movie:',
                                                    self._movie.get_title())

                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(f'About to play: '
                                                    f'{self._movie.get_title()} '
                                                    f'path: '
                                                    f'{self._movie.get_trailer_path()}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)

                # show_movie_info, above, already calls this
                # TrailerStatus.set_show_trailer()

                (is_normalized, is_cached, trailer_path) = self._movie.get_optimal_trailer_path()
                self.get_player().play_trailer(trailer_path, self._movie)

                time_to_play_trailer = (datetime.datetime.now() -
                                        self._get_next_trailer_start)
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose('started play_trailer:',
                                                    self._movie.get_title(),
                                                    'elapsed seconds:',
                                                    time_to_play_trailer.total_seconds(),
                                                    'source:', self._movie.get_source(),
                                                    'normalized:', is_normalized,
                                                    'cached:', is_cached,
                                                    'path:', trailer_path)

                # Again, we rely on our listeners to interrupt, as
                # appropriate. Trailer/Movie should be about to be played or
                # playing.

                try:

                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                                'wait_for_is_playing_video 2 movie:',
                                self._movie.get_title(),
                                trace=Trace.TRACE_UI_CONTROLLER)
                    if not self.get_player().wait_for_is_playing_video(path=trailer_path,
                                                                       timeout=5.0):
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz._logger.debug_extra_verbose(
                                    'Timed out Waiting for Player.',
                                    trace=Trace.TRACE_UI_CONTROLLER)

                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                                'checking play_state 4 movie:',
                                self._movie.get_title())
                    if self.is_random_trailers_play_state(
                            DialogState.SKIP_PLAYING_TRAILER,
                            exact_match=True):
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz._logger.debug_extra_verbose(f'SKIP_PLAYING_TRAILER: '
                                                            f'{self._movie.get_title()},'
                                                            f'trace=Trace.TRACE_UI_CONTROLLER')
                        continue
                    if self.is_random_trailers_play_state(
                            minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz._logger.debug_extra_verbose(
                                    'breaking at play_state 4 movie:',
                                    self._movie.get_title(),
                                    trace=Trace.TRACE_UI_CONTROLLER)
                        break

                    # Now that the movie has started, see if it will run too long so
                    # that we need to set up to kill it playing.

                    # trailer_total_time = self.get_player().getTotalTime()
                    # max_display_time = Settings.get_max_trailer_play_seconds()
                    # if trailer_total_time > max_display_time:
                    #     if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    #         clz._logger.debug_verbose(
                    #             'Killing long movie:',
                    #             self._movie.get_title(), 'limit:',
                    #             max_display_time)

                    # MovieTimer.display_movie_info(max_display_time, play_trailer=True)

                except AbortException:
                    raise sys.exc_info()
                except Exception as e:
                    clz._logger.exception('')

                # Again, we rely on our listeners to stop the player, as
                # appropriate

                self.get_player().wait_for_is_not_playing_video()
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                            f'Trailer not playing; checking play_state 5 movie:'
                            f' {self._movie.get_title()}',
                            trace=Trace.TRACE_UI_CONTROLLER)
                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    continue
                if self.is_random_trailers_play_state(
                        minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                                'breaking at play_state 5 movie:',
                                self._movie.get_title(),
                                trace=Trace.TRACE_UI_CONTROLLER)
                    break

                TrailerStatus.cancel_movie_timer(usage=f'Trailer finished '
                                                       'playing')

                # Again, we rely on our listeners to  stop this display, as
                # appropriate

                TrailerStatus.opaque()

                self.configure_trailer_play_parameters()
                if self.trailers_per_iteration != 0 and not video_is_curtain:
                    number_of_trailers_played += 1
                    if number_of_trailers_played > self.trailers_per_iteration:
                        if Settings.is_group_trailers():
                            self.set_random_trailers_play_state(
                                    DialogState.GROUP_QUOTA_REACHED)
                        else:
                            self.set_random_trailers_play_state(
                                    DialogState.QUOTA_REACHED)

            ##############################################
            #
            # End of while loop. Exiting this method
            #
            ##############################################

            if self._movie is None:
                clz._logger.error('There will be no trailers to play')
                msg: str = Messages.get_msg(Messages.NO_TRAILERS_TO_PLAY)
                NotificationTimer.add_notification(msg=msg)
                self.set_random_trailers_play_state(DialogState.NO_TRAILERS_TO_PLAY)
            else:
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                            'out of inner play loop movie:',
                            self._movie.get_title())

            if Settings.get_show_curtains():
                self._movie_manager.queue_curtain(MovieManager.CLOSE_CURTAIN)

                _, curtain = self._movie_manager.get_next_trailer()
                TrailerStatus.set_show_curtain()

                self.get_player().play_trailer(curtain.get_trailer_path(),
                                               curtain)
                if not self.get_player().wait_for_is_playing_video(
                        path=curtain.get_trailer_path(),
                        timeout=5.0):
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                                'Timed out Waiting for Player.',
                                trace=Trace.TRACE_UI_CONTROLLER)
                self.get_player().wait_for_is_not_playing_video()
                TrailerStatus.opaque()

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(
                        'Completed everything except play_movie, if there is one')
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception('')

        try:
            if self._movie is not None:
                if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                    clz._logger.debug_extra_verbose(
                            'Checking to see if there is a movie to play:',
                            self._movie.get_title())
            if self.is_random_trailers_play_state(DialogState.START_MOVIE_AND_EXIT,
                                                  exact_match=True):
                if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                    clz._logger.debug_extra_verbose(
                            'about to play movie:', self._queued_movie)
                TrailerStatus.opaque()
                self.play_movie(self._queued_movie)

        except AbortException:
            clz._logger.debug('Received shutdown or abort')
        except Exception as e:
            clz._logger.exception('')
'''
