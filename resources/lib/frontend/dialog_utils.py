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

    @classmethod
    def get_dialog_state_mgr(cls) -> BaseDialogStateMgr:
        if DialogStateMgrAccess._dialog_state_mgr is None:
            DialogStateMgrAccess._dialog_state_mgr = BaseDialogStateMgr.get_instance()
        return cls._dialog_state_mgr


class NotificationTimer(DialogStateMgrAccess):
    """
       Manages How long Notifications are displayed

       Takes into account user actions which may cause any of the above
       to be cut short or, in the case of user request to show movie
       details to be untimed, or the pause the playing trailer to stop
       the timer.

   """

    class Notification:
        _msg: str = None
        _block: bool = False

        def __init__(self, msg: str = None, block: bool = False):
            self._msg = msg
            self._block = block

        def get_msg(self) -> str:
            return self._msg

        def is_block(self) -> bool:
            return self._block

        def __eq__(self, other: ForwardRef('Notification')) -> bool:
            clz = type(self)
            if isinstance(clz, other):
                return self._msg == other._msg
            return False

        def __lt__(self, other: ForwardRef('Notification')) -> bool:
            clz = type(self)
            if isinstance(clz, other):
                other_notification: ForwardRef('Notification') = other
                return self._msg < other_notification._msg
            return False

    NOTIFICATION_DONE: bool = True

    _logger: LazyLogger = None
    _trailer_time: bool = False
    _lock: threading.RLock = threading.RLock()
    _lock_cv: threading.Condition = threading.Condition(lock=_lock)
    _previous_msg: str = None
    _timer_state: TimerState = TimerState.IDLE
    _display_timer: FlexibleTimer = None

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def add_notification(cls, msg: str) -> None:
        try:
            notification = cls.Notification(msg=msg, block=False)

            # Ignore duplicate message

            if msg == cls._previous_msg:
                return

            cls._previous_msg = msg

            # New notifications simply cancel the old one

            if cls._timer_state != TimerState.IDLE:
                cls.cancel_notification_timer()

            display_time: float = float(Constants.NOTIFICATION_SECONDS)
            cls._notify(notification, display_time)
        except Exception:
            cls._logger.exception()

    @classmethod
    def _notify(cls, notification: Notification,
                max_display_seconds: float = None,
                callback: Callable[[], None] = None) -> None:
        """
        :param notification: Notification to display
        :param max_display_seconds: Maximum seconds to display notification
        :param callback: Method to inform when complete
        :return:
        """

        try:
            message: str = notification.get_msg()

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'display_time: '
                                                f'{max_display_seconds} '
                                                f'callback: {callback}')
            cls.wait_for_idle()

            with cls._lock_cv:
                if cls._timer_state != TimerState.IDLE:
                    cls._logger.warning(f'TimerState should be IDLE not: '
                                        f'{cls._timer_state}',
                                        trace=Trace.TRACE_UI_CONTROLLER)
                    return

                cls._logger.debug_extra_verbose(f'Setting _timer_state to: STARTING',
                                                trace=Trace.TRACE_UI_CONTROLLER)
                cls._timer_state = TimerState.STARTING

                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'STATE: {cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                cls._lock_cv.notify_all()

            timeout_action = cls.end_display_notification
            timer_name = 'Display Notification'
            Glue.get_dialog().update_notification_labels(text=message)
            TrailerStatus.set_notification_msg(msg=message)

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'max_display_seconds: '
                                                f'{max_display_seconds} ',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            # Start Timer thread which, unless canceled first,
            # either kill a Trailer that is running too long, or stop
            # displaying Notification after a configured amount of time.

            with cls._lock_cv:
                if cls._timer_state != TimerState.STARTING:
                    cls._logger.info(f'TimerState should be STARTING not: '
                                     f'{cls._timer_state}')
                    return

                if not cls.get_dialog_state_mgr().is_random_trailers_play_state(
                        DialogState.USER_REQUESTED_EXIT):
                    cls._display_timer = FlexibleTimer(max_display_seconds,
                                                       timeout_action,
                                                       kwargs={'callback': callback})
                    cls._display_timer.setName(timer_name)
                    cls._logger.debug(f'Starting notification timeout in '
                                      f'{max_display_seconds} seconds',
                                      trace=Trace.TRACE_UI_CONTROLLER)
                    cls._logger.debug(f'Setting _timer_state to WAITING',
                                      trace=Trace.TRACE_UI_CONTROLLER)
                    cls._timer_state = TimerState.WAITING
                    cls._logger.debug_extra_verbose(f'Setting _timer_state to:'
                                                    f' {cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                    cls._lock_cv.notify_all()
                    cls._display_timer.start()

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'STATE: {cls._timer_state}',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            return
        except Exception:
            cls._logger.exception()

    @classmethod
    def _eat_cleanup_finished(cls, callback: Callable[[], None], comment: str = ''):
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
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose(f'State already IDLE '
                                                            f'comment: {comment}',
                                                            trace=Trace.TRACE_UI_CONTROLLER)
                        return

                    if cls._timer_state == TimerState.CLEANUP_FINISHED:
                        cls._timer_state = TimerState.IDLE
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose(f'Setting _timer_state to:'
                                                            f' {cls._timer_state}',
                                                            trace=Trace.TRACE_UI_CONTROLLER)
                        cls._lock_cv.notify_all()
                        break

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose('State now IDLE',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            cls._logger.debug(f'exiting callback: {callback} comment: {comment}')
            if callback is not None:
                cls._logger.debug('Calling callback')
                callback()
        except Exception:
            cls._logger.exception()

    @classmethod
    def end_display_notification(cls,
                                 callback: Callable[[], None] = None,
                                 called_early: bool = False) -> None:
        """
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

        :return:
        """

        try:
            with cls._lock_cv:
                if cls._timer_state != TimerState.WAITING:
                    cls._logger.info(f'TimerState should be WAITING not:'
                                     f' {cls._timer_state}',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                    return

                cls._timer_state = TimerState.CLEANUP_IN_PROGRESS
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'Setting _timer_state to: '
                                                    f'{cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                cls._lock_cv.notify_all()

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose('Stopping notification display',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            TrailerStatus.clear_notification_msg()
            Glue.get_dialog().update_notification_labels(text=None)

            with cls._lock_cv:
                if cls._timer_state != TimerState.CLEANUP_IN_PROGRESS:
                    cls._logger.info(f'TimerState should be CLEANUP_IN_PROGRESS not: '
                                     f'{cls._timer_state}')
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
    def cancel_notification_timer(cls, usage: str = '',
                                  callback: Callable[[], None] = None) -> None:
        """

        :return:
        """
        try:
            with cls._lock_cv:
                if cls._timer_state == TimerState.IDLE:
                    return

                if cls._timer_state != TimerState.WAITING:
                    cls._logger.info(f'TimerState should be WAITING not: {cls._timer_state}',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                    return

            if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                cls._logger.debug(f'Canceling cancel_notification_timer for {usage}',
                                  trace=[Trace.TRACE_UI_CONTROLLER])
                # Running timer early (before timeout)
                cls._display_timer.run_now()

            cls._eat_cleanup_finished(callback=callback, comment='cancel_notification_timer')
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'exit', trace=Trace.TRACE_UI_CONTROLLER)

        except Exception:
            cls._logger.exception()

    @classmethod
    def wait_for_idle(cls) -> None:
        while Monitor.throw_exception_if_abort_requested(0.1):
            if cls._timer_state == TimerState.IDLE:
                break


NotificationTimer.class_init()


class MovieTimer(DialogStateMgrAccess):
    """
       Manages How long:
           Movie details are displayed
           Trailers are played

       Takes into account user actions which may cause any of the above
       to be cut short or, in the case of user request to show movie
       details to be untimed, or the pause the playing trailer to stop
       the timer.

       More specifically:
       - MovieTimer
         - Times how long to display Movie Details
           Not used when user requests Movie Details (Show_Info)
         - Times how long to display playing Trailer
           - Canceled when
               Trailer stops playing
               User requests to pause
           - Kills playing trailer when it times out
           - New timer created when user causes trailer to play
             after pause. Timeout reduced by time already played
   """

    MOVIE_DONE: bool = True

    _logger: LazyLogger = None
    _trailer_time: bool = False
    _lock: threading.RLock = threading.RLock()
    _lock_cv: threading.Condition = threading.Condition(lock=_lock)
    _timer_state: TimerState = TimerState.IDLE
    _display_timer: FlexibleTimer = None

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def display_movie_details(cls,
                              scroll_plot: bool = False,
                              max_display_time: float = 0.0,
                              block: bool = False,
                              from_user_request: bool = False,
                              wait_for_idle: bool = True,
                              callback: Callable[[], None] = None) -> None:
        """
        :param scroll_plot: Controls scrolling of displayed plot
        :param max_display_time: Seconds to display detailed movie info.
        :param block: Block until timer expire or user action
        :param from_user_request: Display originated from a user action
        :param wait_for_idle: First, wait until state is IDLE
        :param callback: Method to inform when complete
        :return:
        """

        try:
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'block: {block} display_time: '
                                                f'{max_display_time} '
                                                f'callback: {callback}')
            if wait_for_idle:
                cls.wait_for_idle()

            with cls._lock_cv:
                if cls._timer_state != TimerState.IDLE:
                    cls._logger.info(f'TimerState should be IDLE not: {cls._timer_state}',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                    return

                cls._logger.debug_extra_verbose(f'Setting _timer_state to: STARTING',
                                                trace=Trace.TRACE_UI_CONTROLLER)
                cls._timer_state = TimerState.STARTING

                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'STATE: {cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                cls._lock_cv.notify_all()

            timeout_action = cls.end_display_movie_details
            timer_name = 'Display Movie Details'
            TrailerStatus.set_show_details(scroll_plot=scroll_plot)
            Glue.get_dialog().voice_detail_view()

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'max_display_time: {max_display_time} '
                                                f'block: {block}',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            # Start Timer thread which, unless canceled first,
            # either kill a Trailer that is running too long, or stop
            # displaying Movie Information after a configured amount of time.

            with cls._lock_cv:
                if cls._timer_state != TimerState.STARTING:
                    cls._logger.info(f'TimerState should be STARTING not: '
                                     f'{cls._timer_state}')
                    return

                Glue.get_dialog().get_player().pause_play()
                inform_user: bool = True
                if not cls.get_dialog_state_mgr().is_random_trailers_play_state(
                        DialogState.USER_REQUESTED_EXIT):
                    cls._display_timer = FlexibleTimer(max_display_time,
                                                       timeout_action,
                                                       kwargs={'inform_user': inform_user,
                                                               'callback': callback,
                                                               'block': block})
                    cls._display_timer.setName(timer_name)
                    cls._logger.debug(f'Starting _display_timer timeout in '
                                      f'{max_display_time} seconds',
                                      trace=Trace.TRACE_UI_CONTROLLER)
                    cls._logger.debug(f'Setting _timer_state to WAITING',
                                      trace=Trace.TRACE_UI_CONTROLLER)
                    cls._timer_state = TimerState.WAITING
                    cls._logger.debug_extra_verbose(f'Setting _timer_state to:'
                                                    f' {cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                    cls._lock_cv.notify_all()
                    cls._display_timer.start()

            if block:  # Block until either timer expires or user action
                cls._logger.debug(f'Blocking', trace=Trace.TRACE_UI_CONTROLLER)
                cls._eat_cleanup_finished(comment='from display_movie_details')

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'STATE: {cls._timer_state}',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            return
        except Exception:
            cls._logger.exception()

    @classmethod
    def display_trailer(cls,
                        max_display_time: float,
                        block: bool = False,
                        wait_for_idle: bool = True,
                        callback: Callable[[], None] = None) -> None:
        """

        :param max_display_time: Seconds to play trailer.
        :param block: Block until timer expire or user action
        :param wait_for_idle: Block until IDLE state. Waits until previous
                              operation ends normally
        :param callback: Method to inform when complete
        :return:
        """

        timeout_action: Callable[[]]
        timer_name: str

        try:
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'block: {block} display_time: '
                                                f'{max_display_time}',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            if wait_for_idle:
                cls.wait_for_idle()

            with cls._lock_cv:
                if cls._timer_state != TimerState.IDLE:
                    cls._logger.info(f'TimerState should be IDLE not: {cls._timer_state}',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                    return

                cls._timer_state = TimerState.STARTING
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'Setting _timer_state to: {cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                cls._lock_cv.notify_all()

            timeout_action = cls.kill_long_playing_trailer
            timer_name = 'Kill Trailer Timer'
            if max_display_time > Constants.NOTIFICATION_SECONDS + 2:
                max_display_time -= Constants.NOTIFICATION_SECONDS
                cls._logger.debug(f'adjusted max_display_time: {max_display_time}',
                                  trace=Trace.TRACE_UI_CONTROLLER)

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'max_display_time: {max_display_time} '
                                                f'block: {block}',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            # Start Timer thread which, unless canceled first,
            # will kill a Trailer that is running too long.

            with cls._lock_cv:
                if cls._timer_state != TimerState.STARTING:
                    cls._logger.info(f'TimerState should be STARTING not: '
                                     f'{cls._timer_state}',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                    return

                inform_user: bool = True
                if not cls.get_dialog_state_mgr().is_random_trailers_play_state(
                        DialogState.USER_REQUESTED_EXIT):
                    cls._display_timer = FlexibleTimer(max_display_time,
                                                       timeout_action,
                                                       kwargs={'inform_user': inform_user,
                                                               'block': block,
                                                               'callback': callback})
                    cls._display_timer.setName(timer_name)
                    cls._logger.debug(f'Starting _display_timer timeout in '
                                      f'{max_display_time} seconds',
                                      trace=Trace.TRACE_UI_CONTROLLER)
                    cls._timer_state = TimerState.WAITING
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'Setting _timer_state to: {cls._timer_state}',
                                                        trace=Trace.TRACE_UI_CONTROLLER)

                    cls._lock_cv.notify_all()
                    cls._display_timer.start()

            TrailerStatus.set_show_trailer()

            trailer_dialog: ForwardRef('TrailerDialog') = Glue.get_dialog()
            title = trailer_dialog.get_title_string(trailer_dialog._movie)
            text_to_speech.say_text(title)
            trailer_dialog.set_playing_trailer_title_control(title)
            text_to_speech.say_text(title, interrupt=True)

            if block:  # Block until either timer expires or user action
                # Don't hog lock, so put in loop

                cls._logger.debug(f'Blocking', trace=Trace.TRACE_UI_CONTROLLER)
                cls._eat_cleanup_finished(comment='from display_trailer')

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'exit '
                                                f'STATE: {cls._timer_state}',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            return
        except Exception:
            cls._logger.exception()

    @classmethod
    def _eat_cleanup_finished(cls, callback: Callable[[], None], comment: str = ''):
        cls._logger.debug(f'callback: {callback} comment: {comment}')
        try:
            attempts: int = 0
            while not Monitor.wait_for_abort(0.1):
                attempts += 1
                with cls._lock_cv:
                    if cls._timer_state == TimerState.IDLE:
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose(f'State already IDLE '
                                                            f'comment: {comment}',
                                                            trace=Trace.TRACE_UI_CONTROLLER)
                        return

                    if cls._timer_state == TimerState.CLEANUP_FINISHED:
                        cls._timer_state = TimerState.IDLE
                        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls._logger.debug_extra_verbose(f'Setting _timer_state to:'
                                                            f' {cls._timer_state}',
                                                            trace=Trace.TRACE_UI_CONTROLLER)
                        cls._lock_cv.notify_all()
                        break

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'State now IDLE attempts: {attempts}',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            cls._logger.debug(f'exiting callback: {callback} comment: {comment}')
            if callback is not None:
                cls._logger.debug('Calling callback')
                callback()
        except Exception:
            cls._logger.exception()

    @classmethod
    def kill_long_playing_trailer(cls,
                                  inform_user: bool = True,
                                  block: bool = False,
                                  callback: Callable[[], None] = None,
                                  called_early: bool = False) -> None:
        """
        This method is called when a Timer Thread expires, upon which this
        method tells the video player to stop playing the current trailer.

        :param inform_user:
        :param block: Indicates that waiting thread is blocked
        :param callback: Callback to inform completion of task. Called
                         IFF not called_early, otherwise, callback from
                         cancel_movie_timer is used
        :param called_early: Indicates that method called explicitly, before
                             timeout occurred
        :return:
        """

        try:
            cls._logger.enter()
            with cls._lock_cv:
                if cls._timer_state != TimerState.WAITING:
                    # Cancel must have occurred
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'TimerState should be WAITING'
                                                        f' not:'
                                                        f'STATE: {cls._timer_state}',
                                                        trace=Trace.TRACE_UI_CONTROLLER)

                    return

                cls._timer_state = TimerState.CLEANUP_IN_PROGRESS
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'Setting _timer_state to: '
                                                    f'{cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)

                cls._lock_cv.notify_all()

            if not called_early and cls._logger.isEnabledFor(
                    LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose('Now Killing',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            # Don't inform user if called due to user action

            if inform_user and not called_early:
                NotificationTimer.add_notification(msg=Messages.get_msg(
                        Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME))

            player = TrailerPlayer.get_player()
            if called_early:
                cls._logger.debug(f'pausing player',
                                  trace=Trace.TRACE_UI_CONTROLLER)
                player.pause_play()
            else:
                cls._logger.debug(f'Stopping player',
                                  trace=Trace.TRACE_UI_CONTROLLER)
                player.stop()

            with cls._lock_cv:
                if cls._timer_state != TimerState.CLEANUP_IN_PROGRESS:
                    cls._logger.info(f'TimerState should be CLEANUP_IN_PROGRESS not: '
                                     f'{cls._timer_state}',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                    return

                if called_early:
                    # Cleanup script will be called next

                    next_state = TimerState.CLEANUP_FINISHED
                else:
                    next_state = TimerState.IDLE
                cls._timer_state = next_state
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'Setting _timer_state to: '
                                                    f'{cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                cls._lock_cv.notify_all()

            cls._logger.debug(f'called_early: {called_early}')
            if not called_early and callback is not None:
                cls._logger.debug(f'Calling callback')
                callback()
        except AbortException:
            raise sys.exc_info()
        except Exception as e:
            cls._logger.exception(msg='')

        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls._logger.debug_extra_verbose('exit', trace=Trace.TRACE_UI_CONTROLLER)

    @classmethod
    def end_display_movie_details(cls,
                                  inform_user: bool = True,
                                  block: bool = False,
                                  callback: Callable[[], None] = None,
                                  called_early: bool = False) -> None:
        """
            This code doesn't itself stop any display of movie details. It
            relies on other code, such as the trailer player to set detail display
            to invisible.

            This method does unblock any wait on the details to be finished
            displaying.

        :param called_early: Called as result of user action instead of
                             expired timer
        :param block:
        :param inform_user:
        :param callback: Callback to inform completion of task. Called
             IFF not called_early, otherwise, callback from
             method used to cancel early is used.

        :return:
        """

        try:
            with cls._lock_cv:
                if cls._timer_state != TimerState.WAITING:
                    cls._logger.info(f'TimerState should be WAITING not:'
                                     f' {cls._timer_state}',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                    return

                cls._timer_state = TimerState.CLEANUP_IN_PROGRESS
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(f'Setting _timer_state to: '
                                                    f'{cls._timer_state}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                cls._lock_cv.notify_all()

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose('Stopping display',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            TrailerStatus.opaque()

            with cls._lock_cv:
                if cls._timer_state != TimerState.CLEANUP_IN_PROGRESS:
                    cls._logger.info(f'TimerState should be CLEANUP_IN_PROGRESS not: '
                                     f'{cls._timer_state}')
                    return

                if called_early:
                    # Cleanup script will be called next

                    next_state = TimerState.CLEANUP_FINISHED
                else:
                    next_state = TimerState.IDLE
                    cls._logger.debug(f'Next STATE: {next_state}',
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
    def cancel_movie_timer(cls, usage: str = '',
                           callback: Callable[[], None] = None) -> None:
        """

        :return:
        """
        try:
            with cls._lock_cv:
                if cls._timer_state == TimerState.IDLE:
                    return

                if cls._timer_state != TimerState.WAITING:
                    cls._logger.info(f'TimerState should be WAITING not: {cls._timer_state}',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                    return

            if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                cls._logger.debug(f'Canceling movie_timer for {usage}',
                                  trace=[Trace.TRACE_UI_CONTROLLER])
                # Running timer early (before timeout)
                cls._display_timer.run_now()

            cls._eat_cleanup_finished(callback=callback, comment='cancel_movie_timer')
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'exit', trace=Trace.TRACE_UI_CONTROLLER)

        except Exception:
            cls._logger.exception()

    @classmethod
    def wait_for_idle(cls) -> None:
        while Monitor.throw_exception_if_abort_requested(0.1):
            if cls._timer_state == TimerState.IDLE:
                break


MovieTimer.class_init()


class TrailerPlayer:

    _logger: LazyLogger = None
    _lock: threading.RLock = threading.RLock()
    _trailer_dialog: ForwardRef('TrailerDialog') = None

    @classmethod
    def class_init(cls, trailer_dialog: ForwardRef('TrailerDialog')) -> None:
        cls._trailer_dialog = trailer_dialog
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

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

                MovieTimer.display_movie_details(scroll_plot=scroll_plot,
                                                 max_display_time=
                                                 detail_info_display_time,
                                                 block=block_after_display_details,
                                                 from_user_request=from_user_request)
            MovieTimer.display_trailer(max_display_time=trailer_play_time,
                                       block=False)
        except Exception:
            cls._logger.exception()

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

            trailer_play_time: int
            trailer_play_time = Settings.get_max_trailer_play_seconds()
            MovieTimer.display_trailer(max_display_time=trailer_play_time, block=False,
                                       callback=callback)

            cls.get_player().wait_for_is_not_playing_video()
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(
                        f'Trailer not playing; checking play_state 5 movie:'
                        f' {movie.get_title()}',
                        trace=Trace.TRACE_UI_CONTROLLER)

            TrailerStatus.cancel_movie_timer(usage=f'Trailer finished playing',
                                             callback=callback)
        except Exception:
            cls._logger.exception()

    @classmethod
    def get_player(cls) -> MyPlayer:
        return cls._trailer_dialog.get_player()


class TrailerStatus(DialogStateMgrAccess):
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
            if cls.get_dialog_state_mgr().is_random_trailers_play_state(
                    minimum_exit_state=DialogState.SHUTDOWN_CUSTOM_PLAYER):
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
    def cancel_movie_timer(cls, usage: str = '',
                           callback: Callable[[], None] = None) -> None:
        MovieTimer.cancel_movie_timer(usage=usage, callback=callback)
