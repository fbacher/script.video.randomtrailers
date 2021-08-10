# -*- coding: utf-8 -*-

"""
Created on Jul 29, 2021

@author: Frank Feuerbacher

"""

from enum import auto, Enum
import sys
import threading

import xbmc
from xbmcgui import (Control, ControlImage, ControlButton, ControlEdit,
                     ControlGroup, ControlLabel, ControlList, ControlTextBox,
                     ControlSpin, ControlSlider, ControlProgress, ControlFadeLabel,
                     ControlRadioButton)

from common.constants import Constants
from common.flexible_timer import FlexibleTimer
from common.imports import *
from common.movie import AbstractMovie
from common.exceptions import AbortException
from common.logger import LazyLogger, Trace
from common.messages import Messages
from common.monitor import Monitor
from common.settings import Settings
from frontend.abstract_dialog_state import BaseDialogStateMgr, DialogState
from player.my_player import MyPlayer
from frontend import text_to_speech

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class Glue:
    _dialog = None

    @staticmethod
    def set_dialog(dialog: ForwardRef('TrailerDialog')) -> None:
        Glue._dialog = dialog

    @staticmethod
    def get_dialog() -> ForwardRef('TrailerDialog'):
        return Glue._dialog


class ControlId(Enum):

    def __init__(self, control_id: int) -> None:
        self._control_id: int = control_id

    def get_control_id(self) -> int:
        clz = type(self)
        return self._control_id

    def get_control(self) -> Control:
        clz = type(self)
        control = Glue.get_dialog().getControl(self.get_control_id())
        return control

    def get_label_control(self) -> ControlLabel:
        return self.get_control()

    SHOW_TRAILER = 38028
    SHOW_DETAILS = 38001
    SHOW_TRAILER_TITLE = 38029
    SHOW_TRAILER_NOTIFICATION = 38030
    SHOW_DETAILS_NOTIFICATION = 38024
    PLAYING_TITLE = 38021
    DETAIL_TITLE = 38003
    DIRECTOR_LABEL = 38025


class VisibleFields(Enum):
    NOTIFICATION = auto()
    TITLE = auto()

    # Either Movie details are displayed or the trailer is played
    SHOW_TRAILER = auto()
    SHOW_DETAILS = auto()
    SHOW_CURTAIN = auto()   # Show a open/close curtain
    NEW_TRAILER = auto()
    OPAQUE = auto()
    SHUTDOWN = auto()


class TimerState(Enum):
    IDLE = auto(),
    STARTING = auto(),
    WAITING = auto(),
    CLEANUP_IN_PROGRESS = auto(),
    CLEANUP_FINISHED = auto()


class DialogStateMgrAccess:
    _dialog_state_mgr: BaseDialogStateMgr = None
    _logger: LazyLogger = None

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def get_dialog_state_mgr(cls) -> BaseDialogStateMgr:
        if DialogStateMgrAccess._dialog_state_mgr is None:
            DialogStateMgrAccess._dialog_state_mgr = BaseDialogStateMgr.get_instance()
        return DialogStateMgrAccess._dialog_state_mgr


class BaseTimer:

    CANCELLING: Tuple[ForwardRef('TimerState')] = (
        TimerState.CLEANUP_FINISHED,
        TimerState.CLEANUP_IN_PROGRESS
    )

    _logger: LazyLogger = None
    _lock: threading.RLock = threading.RLock()
    _lock_cv: threading.Condition = threading.Condition(lock=_lock)
    _timer_state: TimerState = TimerState.IDLE
    _display_seconds: float = None
    _timer_name: str = None
    _timer: FlexibleTimer = None
    _callback_on_stop: Callable[[], None] = None

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def start(cls) -> None:
        """
        :return:
        """

        try:

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'display_seconds: '
                                                f'{cls._display_seconds} '
                                                f'start_action: {cls.start_action}',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            cls.wait_for_idle()

            with cls._lock_cv:
                if cls._incorrect_state(TimerState.IDLE):
                    return

                cls._logger.debug_extra_verbose(f'Setting _timer_state to: STARTING',
                                                trace=Trace.TRACE_UI_CONTROLLER)
                cls._timer_state = TimerState.STARTING

                if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                    cls._logger.debug_extra_verbose(f'STATE: {cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                cls._lock_cv.notify_all()

            with cls._lock_cv:
                if cls._incorrect_state(TimerState.STARTING):
                    return

                cls.start_action()
                cls._lock_cv.notify_all()

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'display_seconds: '
                                                f'{cls._display_seconds} ',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            # Start Timer thread which, unless canceled first,
            # either kill a Trailer that is running too long, or stop
            # displaying Notification after a configured amount of time.

            with cls._lock_cv:
                if cls._incorrect_state(TimerState.STARTING):
                    return

                if not (DialogStateMgrAccess.get_dialog_state_mgr()
                            .is_random_trailers_play_state(
                            DialogState.USER_REQUESTED_EXIT)):
                    cls._timer = FlexibleTimer(cls._display_seconds,
                                               cls._stop,
                                               kwargs={'callback':
                                                       cls._callback_on_stop})
                    cls._timer.setName(cls._timer_name)
                    cls._logger.debug(f'Starting timeout in '
                                      f'{cls._display_seconds} seconds',
                                      trace=Trace.TRACE_UI_CONTROLLER)
                    cls._logger.debug(f'Setting _timer_state to WAITING',
                                      trace=Trace.TRACE_UI_CONTROLLER)
                    cls._timer_state = TimerState.WAITING
                    cls._lock_cv.notify_all()
                    cls._timer.start()

            with cls._lock_cv:
                if cls._incorrect_state(TimerState.WAITING):
                    return

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'STATE: {cls._timer_state}',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            return
        except Exception:
            cls._logger.exception()

    @classmethod
    def _incorrect_state(cls, timerstate: TimerState) -> bool:
        if cls._timer_state != timerstate:
            cls._logger.warning(f'TimerState should be {timerstate} not: '
                                f'{cls._timer_state} CANCELING LOCK',
                                trace=Trace.TRACE_UI_CONTROLLER)
            cls._logger.dump_stack(msg='')
            cls.cancel()
            cls._lock_cv.notify_all()
            return True
        return False

    @classmethod
    def _stop(cls,
              callback: Callable[[], None] = None,
              called_early: bool = False,
              stop_play: bool = False
              ) -> None:
        """
        TODO: FIX
            This code doesn't itself stop any notification display. It
            relies on other code, such as the trailer player to set detail display
            to invisible.

            This method does unblock any wait on the details to be finished
            displaying.

        :param called_early: Called as result of user action instead of
                             expired timer
        :param callback: Callback to inform completion of task. Called
             IFF not called_early, otherwise, callback from
             method used to cancel early is used.
        :param stop_play: Passed to stop_action so that stop_acton can call
                          Player.stop instead of player.pause.
        :return:
        """

        try:
            cls._logger.debug(f'stop_play: {stop_play}')
            with cls._lock_cv:
                if cls._incorrect_state(TimerState.WAITING):
                    return

                cls._timer_state = TimerState.CLEANUP_IN_PROGRESS
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'Setting _timer_state to: '
                                                    f'{cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                cls._lock_cv.notify_all()

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose('Stopping',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            with cls._lock_cv:
                if cls._incorrect_state(TimerState.CLEANUP_IN_PROGRESS):
                    return

                cls.stop_action(called_early=called_early, stop_play=stop_play)
                TrailerStatus.clear_notification_msg()
                Glue.get_dialog().update_notification_labels(text=None)
                cls._lock_cv.notify_all()

            with cls._lock_cv:
                if cls._incorrect_state(TimerState.CLEANUP_IN_PROGRESS):
                    return

                if called_early:
                    # Cleanup script will be called next

                    next_state = TimerState.CLEANUP_FINISHED
                else:
                    next_state = TimerState.IDLE
                    cls._logger.debug(f'STATE: {next_state}',
                                      trace=Trace.TRACE_UI_CONTROLLER)

                cls._timer_state = next_state
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'Setting _timer_state to: '
                                                    f'{cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                cls._lock_cv.notify_all()

            cls._logger.debug(f'called_early: {called_early} callback: {callback}')
            if not called_early and callback is not None:
                cls._logger.debug(f'Calling callback')
                callback()
        except AbortException:
            raise sys.exc_info()
        except Exception as e:
            cls._logger.exception(msg='')

        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls._logger.debug_extra_verbose('exit',
                                            trace=Trace.TRACE_UI_CONTROLLER)

    @classmethod
    def cancel(cls, usage: str = '', stop_play: bool = False,
               callback: Callable[[], None] = None) -> bool:
        """
        :param usage: Displyable comment for debug
        :param stop_play: When cancelling trailer playback. If True, STOP
                          playback, otherwise, pause. Passed to stop_action.
        :param callback: Callback to pass along to stop_action
        :return: True if cancel performed, False if Timer IDLE
        """
        try:
            with cls._lock_cv:
                if cls._timer_state == TimerState.IDLE:
                    return False

                if cls._timer_state != TimerState.WAITING:
                    cls._logger.info(f'TimerState should be WAITING not: '
                                     f'{cls._timer_state}',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                    # Don't re-cancel

                    if cls._timer_state in cls.CANCELLING:
                        return False

            if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                cls._logger.debug(f'Canceling for {usage}',
                                  trace=[Trace.TRACE_UI_CONTROLLER])

            # Running timer early (before timeout)
            cls._logger.debug(f'Calling stop early, stop_play: {stop_play}')
            cls._timer.run_now()

            cls._cleanup(callback=callback)
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'exit', trace=Trace.TRACE_UI_CONTROLLER)

        except Exception:
            cls._logger.exception()

        return True

    @classmethod
    def _cleanup(cls, callback: Callable[[], None], comment: str = '',
                 kwargs: Dict[str, str] = None):
        cls._logger.debug(f'callback: {callback} comment: {comment}')
        try:
            while not Monitor.wait_for_abort(0.1):
                # Wait until:
                #  1- _task_finished.is_set() indicating that the allotted time
                #      to show movie details or the trailer has expired
                #      OR
                #      ane external event has canceled the display
                # 2- _display_timer is None
                #
                with cls._lock_cv:
                    if cls._timer_state == TimerState.IDLE:
                        cls._lock_cv.notify_all()
                        return

                    if cls._timer_state == TimerState.CLEANUP_FINISHED:
                        cls._timer_state = TimerState.IDLE
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose(f'Setting _timer_state to:'
                                                            f' {cls._timer_state}',
                                                            trace=
                                                            Trace.TRACE_UI_CONTROLLER)
                        cls._lock_cv.notify_all()
                        break

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose('State now IDLE',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            if callback is not None:
                cls._logger.debug('Calling callback')
                if kwargs is None:
                    kwargs = {}
                callback(**kwargs)
        except Exception:
            cls._logger.exception()

    @classmethod
    def start_action(cls):
        raise NotImplementedError

    @classmethod
    def stop_action(cls, called_early: bool, stop_play: bool = False):
        raise NotImplementedError

    @classmethod
    def wait_for_idle(cls) -> None:
        while Monitor.throw_exception_if_abort_requested(0.1):
            if cls._timer_state == TimerState.IDLE:
                break


class NotificationTimer(BaseTimer):
    """
       Manages How long Notifications are displayed

       Takes into account user actions which may cause any of the above
       to be cut short or, in the case of user request to show movie
       details to be untimed, or the pause the playing trailer to stop
       the timer.

   """

    _logger: LazyLogger = None
    _lock: threading.RLock = threading.RLock()
    _lock_cv: threading.Condition = threading.Condition(lock=_lock)
    _timer_state: TimerState = TimerState.IDLE
    _display_seconds: float = float(Constants.NOTIFICATION_SECONDS)
    _timer_name: str = None
    _timer: FlexibleTimer = None
    _msg: str = None
    _previous_msg: str = None

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def config(cls, msg: str) -> None:
        try:
            if msg == cls._previous_msg:
                return

            cls._previous_msg = msg

            # New notifications simply cancel the old one

            if cls._timer_state != TimerState.IDLE:
                cls.cancel(usage='Config forced cancel of running timer')

            cls._msg = msg
        except Exception:
            cls._logger.exception()

    @classmethod
    def start_action(cls) -> None:
        cls._logger.debug('About to notify')
        Glue.get_dialog().update_notification_labels(text=cls._msg)
        TrailerStatus.set_notification_msg(msg=cls._msg)

    @classmethod
    def stop_action(cls, called_early: bool,
                    stop_play: bool = False):
        cls._logger.debug('called_early: {called_early} stop_play: {stop_play} '
                          'About to clear notification')
        TrailerStatus.clear_notification_msg()
        Glue.get_dialog().update_notification_labels(text=None)


NotificationTimer.class_init()


class MovieDetailsTimer(BaseTimer):

    _logger: LazyLogger = None
    _lock: threading.RLock = threading.RLock()
    _lock_cv: threading.Condition = threading.Condition(lock=_lock)
    _timer_state: TimerState = TimerState.IDLE
    _timer: FlexibleTimer = None
    _display_seconds: float = Settings.get_time_to_display_detail_info()
    _timer_name = 'Display Movie Details'
    _scroll_plot: bool = None
    _callback_on_stop: Callable[[], None] = None

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def config (cls, scroll_plot: bool,
                display_seconds: float,
                callback_on_stop: Callable[[], None] = None) -> None:
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

        if cls._incorrect_state(TimerState.IDLE):
            return

        cls._scroll_plot = scroll_plot
        cls._display_seconds = display_seconds
        cls._callback_on_stop = callback_on_stop

    @classmethod
    def start_action(cls) -> None:
        cls._logger.debug(f'About to set_show_details & voice_detail_view')
        TrailerStatus.set_show_details(scroll_plot=cls._scroll_plot)
        Glue.get_dialog().voice_detail_view()

    @classmethod
    def stop_action(cls, called_early: bool,
                    stop_play: bool = False):
        cls._logger.debug(f'called_early: {called_early} stop_play: {stop_play} '
                    f'Calling text_to_speech.stop and TrailerStatus.opaque')
        text_to_speech.stop()
        TrailerStatus.opaque()


MovieDetailsTimer.class_init()


class TrailerTimer(BaseTimer):

    _logger: LazyLogger = None
    _lock: threading.RLock = threading.RLock()
    _lock_cv: threading.Condition = threading.Condition(lock=_lock)
    _timer_state: TimerState = TimerState.IDLE
    _timer: FlexibleTimer = None
    _display_seconds: float = Settings.get_max_trailer_play_seconds()
    _timer_name: str = 'TrailerTimer'
    _inform_user: bool = None
    _callback_on_stop: Callable[[], None] = None

    @classmethod
    def config (cls,
                display_seconds: float,
                callback_on_stop: Callable[[], None] = None) -> None:
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

        if cls._timer_state != TimerState.IDLE:
            cls.cancel(usage='Config forced cancel of running timer')

        cls.display_seconds = display_seconds
        cls._callback_on_stop = callback_on_stop

    @classmethod
    def start_action(cls) -> None:
        cls._logger.debug(f'Calling set_show_trailer,'
                          f' set_playing_trailer_title')
        TrailerStatus.set_show_trailer()

        trailer_dialog: ForwardRef('TrailerDialog') = Glue.get_dialog()
        verbose: bool = cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
        title = trailer_dialog.get_title_string(trailer_dialog._movie, verbose)
        trailer_dialog.set_playing_trailer_title_control(title)
        # text_to_speech.say_text(title, interrupt=True)

    @classmethod
    def stop_action(cls, called_early: bool,
                    stop_play: bool = False):
        """
        TODO: Fix
        Called when:
            1) Trailer has finished playing. The player will be stopped,
               called_early = False, stop_play = False
            2) Trailer has played past the maximim time limit. The player is
               still playing (unless it finished in the time between the timer
               going off and this code). called_early = False, stop_play = False.
            3) User action requires trailer to pause or stop playing:
               In either case called_early = True. The trailer will be stopped
               or paused, depending upon stop_play.

        When callback is not None, then it will be called with the argument
        stop_play. stop_play = (stop_play OR not called_early).

        :param called_early:
        :param stop_play:
        :return:
        """
        # Don't inform user if called due to user action
        cls._logger.debug(f'called_early: {called_early} stop_play: {stop_play}')

        if cls._inform_user and not called_early:
            cls._logger.debug('About to notify max_play_time exceeded')
            NotificationTimer.config(msg=Messages.get_msg(
                    Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME))
            NotificationTimer.start()

        TrailerStatus.opaque()
        player = TrailerPlayer.get_player()
        if not called_early:
            stop_play = True

        if stop_play:
            cls._logger.debug(f'Stopping player',
                              trace=Trace.TRACE_UI_CONTROLLER)
            player.stop()
        else:
            cls._logger.debug(f'Pausing player',
                              trace=Trace.TRACE_UI_CONTROLLER)
            player.pause_play()

        text_to_speech.stop()


TrailerTimer.class_init()


class TrailerPlayer:

    _logger: LazyLogger = None
    _lock: threading.RLock = threading.RLock()
    _trailer_dialog: ForwardRef('TrailerDialog') = None

    @classmethod
    def class_init(cls, trailer_dialog: ForwardRef('TrailerDialog')) -> None:
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)
        cls._trailer_dialog = trailer_dialog

    '''
    @classmethod
    def show_details_and_play(cls, scroll_plot: bool = False,
                              missing_movie_details: bool = False,
                              block_after_display_details: bool = True,
                              from_user_request: bool = False):

        try:
            cls._logger.debug_extra_verbose(f'missing_movie_details: '
                                            f'{missing_movie_details} '
                                            f'block_after_display_details: '
                                            f'{block_after_display_details} '
                                            f'from_user_request: '
                                            f'{from_user_request}',
                                            trace=Trace.TRACE_UI_CONTROLLER)
            cls._trailer_dialog.update_detail_view()
            detail_info_display_time: int
            detail_info_display_time = Settings.get_time_to_display_detail_info()
            show_movie_details = (not missing_movie_details and
                                  detail_info_display_time > 0)
            trailer_play_time: int
            trailer_play_time = Settings.get_max_trailer_play_seconds()
            if show_movie_details:

                player = cls.get_player()
                if player is not None and player.isPlaying():
                    # Pause playing trailer
                    cls._logger.debug(f'Pausing Player',
                                      trace=Trace.TRACE_UI_CONTROLLER)
                    player.pause_play()

                MovieDetailsTimer.config(scroll_plot=scroll_plot,
                                         display_seconds=detail_info_display_time)
                MovieDetailsTimer.start()

            TrailerTimer.config(display_seconds=trailer_play_time,
                                callback_on_stop=TaskLoop.play_trailer_finished)
            TrailerTimer.start()
        except Exception:
            cls._logger.exception()
    '''

    @classmethod
    def play_trailer(cls, movie: AbstractMovie = None,
                     callback: Callable[[], None] = None):
        worker = threading.Thread(target=cls._play_trailer,
                                  args=(movie, callback),
                                  name='TrailerPlayer.play_trailer')
        worker.start()

    @classmethod
    def _play_trailer(cls, *args):
        movie: AbstractMovie = args[0]
        callback: Callable[[], None] = args[1]
        try:
            (is_normalized, is_cached, trailer_path) = movie.get_optimal_trailer_path()
            cls.get_player().play_trailer(trailer_path, movie)

            # time_to_play_trailer = (datetime.datetime.now() -
            #                         self._get_next_trailer_start)
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose('started play_trailer:',
                                                movie.get_title(),
                                                # 'elapsed seconds:',
                                                # time_to_play_trailer.total_seconds(),
                                                'source:', movie.get_source(),
                                                'normalized:', is_normalized,
                                                'cached:', is_cached,
                                                'path:', trailer_path)

                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(
                            'wait_for_is_playing_video 2 movie:',
                            movie.get_title(),
                            trace=Trace.TRACE_UI_CONTROLLER)
                if not cls.get_player().wait_for_is_playing_video(path=trailer_path,
                                                                  timeout=5.0):
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(
                                'Timed out Waiting for Player.',
                                trace=Trace.TRACE_UI_CONTROLLER)

            trailer_play_time: float
            trailer_play_time = float(Settings.get_max_trailer_play_seconds())
            TrailerTimer.config(display_seconds=trailer_play_time,
                                callback_on_stop=callback)
            TrailerTimer.start()

            cls.get_player().wait_for_is_not_playing_video()
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(
                        f'Trailer not playing; checking play_state 5 movie:'
                        f' {movie.get_title()}',
                        trace=Trace.TRACE_UI_CONTROLLER)

            TrailerTimer.cancel(usage=f'Trailer finished playing',
                                callback=callback, stop_play=True)
        except Exception:
            cls._logger.exception()

    @classmethod
    def get_player(cls) -> MyPlayer:
        return cls._trailer_dialog.get_player()


class TrailerStatus:
    """
    Manages the visibility of information based upon changes to data and
    events.

    Note that most controls displayed when movie details is visible are
    handled directly by Trailer_Dialog.update. However, several controls
    that are optionally visible when playing trailers are handled here.

    This class also controls visibility of movie details or the playing
    trailer.
    """

    # There are several fields that are displayed when movie details are shown
    # or the trailer is being played.

    FIELDS_SHOWN_WHEN_TRAILER_PLAYED = [
        VisibleFields.NOTIFICATION,
        VisibleFields.TITLE
    ]

    show_notification_seconds: int = 0
    show_details_seconds: int = Settings.get_time_to_display_detail_info()
    show_trailer_seconds: int = Settings.get_max_trailer_play_seconds()
    remaining_trailer_seconds: int = 0

    logger: LazyLogger = None

    # show_title_while_playing: bool = Settings.get_show_movie_title()
    show_notification: bool = False

    show_trailer: bool = False
    scroll_plot: bool = False

    notification_msg: str = None

    _dialog: ForwardRef('TrailerDialog') = None

    @classmethod
    def class_init(cls, dialog: ForwardRef('TrailerDialog')):
        cls._dialog = dialog
        if cls.logger is None:
            cls.logger = module_logger.getChild(cls.__name__)

    @classmethod
    def set_notification_msg(cls, msg: str = None) -> None:
        cls.notification_msg = msg
        cls.value_changed(VisibleFields.NOTIFICATION)

    @classmethod
    def clear_notification_msg(cls) -> None:
        cls.notification_msg = None
        cls.show_notification = False
        cls.value_changed(VisibleFields.NOTIFICATION)

    @classmethod
    def get_notification_msg(cls) -> str:
        return cls.notification_msg

    @classmethod
    def get_show_notification(cls) -> bool:
        return cls.show_notification

    @classmethod
    def set_show_trailer(cls) -> None:
        cls.show_trailer = True
        cls.reset_state()
        cls.value_changed(VisibleFields.SHOW_TRAILER)

    @classmethod
    def set_show_curtain(cls) -> None:
        cls.show_trailer = True
        cls.reset_state()
        cls.value_changed(VisibleFields.SHOW_CURTAIN)

    @classmethod
    def set_show_details(cls, scroll_plot: bool = False) -> None:
        cls.show_trailer = False
        cls.scroll_plot = scroll_plot
        cls.reset_state()
        cls.value_changed(VisibleFields.SHOW_DETAILS)

    @classmethod
    def reset_state(cls, new_trailer: bool = False) -> None:
        cls.show_notification = False
        cls.notification_msg = None
        if new_trailer:
            cls.remaining_trailer_seconds = cls.show_trailer_seconds
            cls._show_trailer = False

    @classmethod
    def opaque(cls) -> None:
        cls.reset_state()
        cls.value_changed(VisibleFields.OPAQUE)

    @classmethod
    def value_changed(cls, changed_field: VisibleFields) -> None:
        """
            Controls the visible elements of TrailerDialog
        :return:
        """
        # First, determine if we need to shut things down

        shutdown = changed_field == VisibleFields.SHUTDOWN
        try:
            if (DialogStateMgrAccess.get_dialog_state_mgr().
                    is_random_trailers_play_state(
                    minimum_exit_state=DialogState.SHUTDOWN_CUSTOM_PLAYER)):
                shutdown = True
        except AbortException:
            shutdown = True

        commands = []
        if shutdown:
            pass

        elif changed_field in (VisibleFields.SHOW_TRAILER, VisibleFields.SHOW_CURTAIN):
            # Hide entire Movie details screen first
            # Any notifications are canceled

            Glue.get_dialog().set_visibility(False, ControlId.SHOW_DETAILS)
            Glue.get_dialog().set_visibility(False,
                                            ControlId.SHOW_TRAILER_NOTIFICATION)
            if changed_field != VisibleFields.SHOW_CURTAIN:
                show_title_while_playing: bool = Settings.get_show_movie_title()
                if show_title_while_playing:
                    Glue.get_dialog().set_visibility(True,
                                                    ControlId.SHOW_TRAILER_TITLE)

            Glue.get_dialog().set_visibility(True, ControlId.SHOW_TRAILER)

        elif changed_field == VisibleFields.SHOW_DETAILS:
            # Show movie details
            Glue.get_dialog().set_visibility(False, ControlId.SHOW_TRAILER)
            Glue.get_dialog().set_visibility(False,
                                            ControlId.SHOW_DETAILS_NOTIFICATION)
            if cls.scroll_plot:
                commands.append("Skin.SetBool(ScrollPlot)")
            else:
                commands.append("Skin.Reset(ScrollPlot)")

            Glue.get_dialog().set_visibility(True, ControlId.SHOW_DETAILS)

        elif changed_field == VisibleFields.NOTIFICATION:
            visible: bool = cls.notification_msg is not None
            if cls.show_trailer:
                Glue.get_dialog().set_visibility(visible,
                                                ControlId.SHOW_TRAILER_NOTIFICATION)
            else:
                Glue.get_dialog().set_visibility(visible,
                                                ControlId.SHOW_DETAILS_NOTIFICATION)

        elif changed_field == VisibleFields.OPAQUE:
            Glue.get_dialog().set_visibility(False, ControlId.SHOW_DETAILS)
            Glue.get_dialog().set_visibility(False, ControlId.SHOW_TRAILER)

        for command in commands:
            if cls.logger.isEnabledFor(LazyLogger.DEBUG):
                cls.logger.debug_extra_verbose(command,
                                               trace=Trace.TRACE_UI_CONTROLLER)
            xbmc.executebuiltin(command, wait=False)

    @classmethod
    def cancel_trailer_timer(cls, usage: str = '',
                             callback: Callable[[], None] = None,
                             stop_play: bool = False) -> None:
        TrailerTimer.cancel(usage=usage, callback=callback, stop_play=stop_play)

    @classmethod
    def cancel_movie_details_timer(cls, usage: str = '',
                                   callback: Callable[[], None] = None) -> None:
        MovieDetailsTimer.cancel(usage=usage, callback=callback)
