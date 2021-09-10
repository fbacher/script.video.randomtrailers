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
from common.exceptions import AbortException
from common.logger import LazyLogger, Trace
from common.messages import Messages
from common.monitor import Monitor
from common.settings import Settings
from frontend.abstract_dialog_state import BaseDialogStateMgr, DialogState
from frontend.text_to_speech import TTS
from player.my_player import MyPlayer

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class Glue:
    _dialog = None

    @staticmethod
    def set_dialog(dialog: ForwardRef('TrailerDialog')) -> None:
        Glue._dialog = dialog

    @staticmethod
    def get_dialog() -> ForwardRef('TrailerDialog'):
        return Glue._dialog

    @staticmethod
    def get_player() -> MyPlayer:
        return Glue._dialog.get_player()


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

    _lock: threading.RLock = None # threading.RLock()
    _lock_cv: threading.Condition = None # threading.Condition(lock=_lock)
    _busy_event: threading.Event = None
    _timer_state: TimerState = None # TimerState.IDLE
    _display_seconds: float = None
    _timer_name: str = None
    _timer: FlexibleTimer = None
    _callback_on_stop: Callable[[], None] = None
    _cancel_callback: Callable[[], None] = None
    _cancel_stop_on_play: bool = None
    _cancel_event: threading.Event = None
    _cancel_msg: str = None
    _stop_called: bool = None
    _title: str = None   # For debug logs

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def is_busy(cls) -> bool:
        return cls._busy_event.is_set()

    @classmethod
    def is_canceled(cls) -> bool:
        return cls._cancel_event.is_set()

    @classmethod
    def can_be_canceled(cls) -> bool:
        return cls.is_busy() and not cls.is_canceled()

    @classmethod
    def start(cls) -> None:
        """
        :return:
        """
        try:
            with cls._lock_cv:
                try:
                    if not cls._busy_event.is_set():
                        cls._logger.error(f'_busy_event is NOT set title {cls._title}')
                        cls._cancel_event.clear()  # Just in case
                        return

                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'title: {cls._title}'
                                                        f'display_seconds: '
                                                        f'{cls._display_seconds} '
                                                        f'start_action: {cls.start_action}',
                                                        trace=Trace.TRACE_UI_CONTROLLER)
                finally:
                    cls._lock_cv.notify_all()

            with cls._lock_cv:
                try:
                    if cls._incorrect_state(TimerState.IDLE):
                        return

                    cls._logger.debug_extra_verbose(f'Setting _timer_state to: STARTING '
                                                    f'title: {cls._title}',
                                                    trace=Trace.TRACE_UI_CONTROLLER)
                    cls._timer_state = TimerState.STARTING
                finally:
                    cls._lock_cv.notify_all()

            with cls._lock_cv:
                try:
                    if cls._incorrect_state(TimerState.STARTING):
                        return

                    cls.start_action()
                finally:
                    cls._lock_cv.notify_all()

            # Start Timer thread which, unless canceled first,
            # either kill a Trailer that is running too long, or stop
            # displaying Notification after a configured amount of time.

            with cls._lock_cv:
                try:
                    run_start: bool = True
                    if cls._incorrect_state(TimerState.STARTING):
                        run_start = False
                        return

                    if not (DialogStateMgrAccess.get_dialog_state_mgr()
                                .is_random_trailers_play_state(
                                DialogState.USER_REQUESTED_EXIT)):
                        cls._timer = FlexibleTimer(cls._display_seconds,
                                                   cls._stop,
                                                   cls._title,
                                                   kwargs={'callback':
                                                           cls._callback_on_stop})
                        cls._timer.setName(cls._timer_name)
                        cls._logger.debug(f'title: {cls._title} Starting timeout in '
                                          f'{cls._display_seconds} seconds',
                                          trace=Trace.TRACE_UI_CONTROLLER)
                        cls._timer_state = TimerState.WAITING
                finally:
                    if run_start:
                        cls._timer.start()
                    cls._lock_cv.notify_all()

            with cls._lock_cv:
                if cls._incorrect_state(TimerState.WAITING):
                    return
                cls._lock_cv.notify_all()

            if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                cls._logger.debug_extra_verbose(f'STATE: {cls._timer_state}',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            return
        except Exception:
            cls._logger.exception()

    @classmethod
    def _incorrect_state(cls, timerstate: TimerState) -> bool:
        if cls._timer_state != timerstate:
            cls._logger.warning(f'title: {cls._title} TimerState should be '
                                f'{timerstate} not: '
                                f'{cls._timer_state} CANCELING LOCK',
                                trace=Trace.TRACE_UI_CONTROLLER)
            cls._logger.dump_stack(heading=f'TimerState should be {timerstate} not: '
                                           f'{cls._timer_state} CANCELING LOCK')
            cls.cancel()
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
            with cls._lock_cv:
                try:
                    if not cls._busy_event.is_set():
                        cls._logger.error(f'title: {cls._title} _busy_event is NOT set')
                finally:
                    cls._lock_cv.notify_all()

            cls._logger.debug(f'title: {cls._title} stop_play: {stop_play}')
            with cls._lock_cv:
                try:
                    if cls._incorrect_state(TimerState.WAITING):
                        return

                    cls._timer_state = TimerState.CLEANUP_IN_PROGRESS
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'title: {cls._title} '
                                                        f'Setting _timer_state to: '
                                                        f'{cls._timer_state}',
                                                        trace=Trace.TRACE_UI_CONTROLLER)
                finally:
                    cls._lock_cv.notify_all()

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'title: {cls._title} Stopping',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            with cls._lock_cv:
                try:
                    cls._stopped_called = True
                    if cls._incorrect_state(TimerState.CLEANUP_IN_PROGRESS):
                        return

                    cls.stop_action(called_early=called_early, stop_play=stop_play)
                    TrailerStatus.clear_notification_msg()
                    Glue.get_dialog().update_notification_labels(text=None)
                finally:
                    cls._lock_cv.notify_all()

            with cls._lock_cv:
                try:
                    if cls._incorrect_state(TimerState.CLEANUP_IN_PROGRESS):
                        return

                    if called_early:
                        # Cleanup script will be called next

                        if not cls._cancel_event.is_set():
                            cls._logger.error(f'title: {cls._title} '
                                              f'cancel_event is NOT set.')
                        next_state = TimerState.CLEANUP_FINISHED
                    else:
                        cls._timer = None
                        next_state = TimerState.IDLE

                    cls._timer_state = next_state
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'title: {cls._title} '
                                                        f'Setting _timer_state to: '
                                                        f'{cls._timer_state}',
                                                        trace=Trace.TRACE_UI_CONTROLLER)

                        cls._logger.debug(f'called_early: {called_early} '
                                          f'callback: {callback}')
                    if not called_early and callback is not None:
                        # Terminating without being canceled.
                        cls._logger.debug(f'title: {cls._title} Calling callback')
                        callback()
                        cls._busy_event.clear()
                    else:
                        # When canceled, the cancel method will call
                        # _cleanup, which will reset:
                        # busy_event.clear() & cancel_event.clear(), stop_called
                        pass
                finally:
                    cls._lock_cv.notify_all()
        except AbortException:
            raise sys.exc_info()
        except Exception as e:
            cls._logger.exception(msg='')

        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls._logger.debug_extra_verbose(f'title: {cls._title} exit',
                                            trace=Trace.TRACE_UI_CONTROLLER)

    @classmethod
    def cancel(cls, usage: str = '', stop_play: bool = False,
               callback: Callable[[], None] = None,
               kwargs: Dict[Union[str, Enum], Any] = None) -> bool:
        """
        :param kwargs: Kwargs for callable
        :param usage: Displyable comment for debug
        :param stop_play: When cancelling trailer playback. If True, STOP
                          playback, otherwise, pause. Passed to stop_action.
        :param callback: Callback to pass along to stop_action
        :return: True if cancel performed, Otherwise, False
        """
        try:
            cls._logger.debug(f'usage: {usage} stop_play: {stop_play} '
                              f'callback: {callback}')
            with cls._lock_cv:
                try:
                    if cls._stop_called:
                        cls._logger.debug(f'title: {cls._title} '
                                          f'Too late to cancel, already stopped')
                        return False

                    if not cls._busy_event.is_set():
                        cls._logger.error(f'title: {cls._title} _busy_event is NOT set')

                        # Just to make sure
                        cls._cancel_event.clear()
                        return False

                    if cls._cancel_event.is_set():
                        cls._logger.debug(f'title: {cls._title} '
                                          f'Already Marked to be Canceled, ignoring')
                        return False

                    if cls._timer_state == TimerState.IDLE:
                        cls._logger.error(f'title: {cls._title} Canceled, but IDLE.')
                        return False

                    if cls._timer_state != TimerState.WAITING:
                        cls._logger.info(f'title: {cls._title} '
                                         f'TimerState should be WAITING not: '
                                         f'{cls._timer_state}',
                                         trace=Trace.TRACE_UI_CONTROLLER)
                        return False

                    cls._cancel_event.set()

                except Exception:
                    cls._logger.exception()

                finally:
                    cls._lock_cv.notify_all()

            if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                cls._logger.debug(f'title: {cls._title} Canceling for {usage}',
                                  trace=[Trace.TRACE_UI_CONTROLLER])

            # Running timer early (before timeout)
            cls._logger.debug(f'title: {cls._title} '
                              f'Calling stop early, stop_play: {stop_play}')
            cls._timer.run_now(kwargs={'stop_play': stop_play})
            cls._timer = None

            if kwargs is None:
                kwargs = {}

            kwargs['stop_play'] = stop_play
            cls._cleanup(callback=callback, kwargs=kwargs)
            #
            # _cleanup takes care of resetting:
            # _cancel_event, _busy_event, _stop_called
            #
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'title: {cls._title} '
                                                f'exit cancel_event.is_set: '
                                                f'{cls._cancel_event.is_set()}',
                                                trace=Trace.TRACE_UI_CONTROLLER)

        except Exception:
            cls._logger.exception()

        return True

    @classmethod
    def _cleanup(cls, callback: Callable[[], None] = None, comment: str = '',
                 kwargs: Dict[str, Union[str, bool]] = None):
        cls._logger.debug(f'title: {cls._title} callback: {callback} comment: {comment}')
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
                    try:
                        if not cls._busy_event.is_set():
                            cls._logger.error(f'title: {cls._title} '
                                              f'_busy_event is NOT set')
                            cls._cancel_event.clear()
                            cls._stop_called: bool = False
                            return

                        if not cls._cancel_event.is_set():
                            cls._logger.debug(f'title: {cls._title} '
                                              f'_cancel_event is NOT set')
                            cls._stop_called: bool = False
                            return

                        if cls._timer_state == TimerState.CLEANUP_FINISHED:
                            cls._timer_state = TimerState.IDLE
                            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                                cls._logger.debug_extra_verbose(f'title: {cls._title} '
                                                                f'Setting _timer_state to:'
                                                                f' {cls._timer_state}',
                                                                trace=
                                                                Trace.TRACE_UI_CONTROLLER)
                            if callback is not None:
                                cls._logger.debug(f'title: {cls._title} '
                                                  f'Calling callback')
                                if kwargs is None:
                                    kwargs = {}
                                callback(**kwargs)
                            cls._logger.debug(f'title: {cls._title} '
                                              f'clearing cancel_event')
                            cls._cancel_event.clear()
                            cls._busy_event.clear()
                            cls._stop_called: bool = False
                        break
                    finally:
                        cls._lock_cv.notify_all()

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
    _busy_event: threading.Event = threading.Event()
    _timer_state: TimerState = TimerState.IDLE
    _display_seconds: float = float(Constants.NOTIFICATION_SECONDS)
    _timer_name: str = None
    _timer: FlexibleTimer = None
    _msg: str = None
    _previous_msg: str = None
    _cancel_callback: Callable[[], None] = None
    _cancel_stop_on_play: bool = False
    _cancel_event: threading.Event = threading.Event()
    _cancel_msg: str = None
    _stop_called: bool = False
    _title: str = ''

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def config(cls, msg: str, title: str = '') -> None:
        with cls._lock_cv:
            try:
                cls._title = title
                if msg == cls._previous_msg:
                    return

                cls._previous_msg = msg

                if cls._cancel_event.is_set():
                    cls._logger.debug_verbose(f'title: {cls._title} '
                                              f'Waiting for cancel to complete')
                    while cls._cancel_event.is_set():
                        Monitor.throw_exception_if_abort_requested(timeout=0.2)

                if cls._busy_event.is_set():
                    cls._logger.debug_verbose(f'title: {cls._title} '
                                              f'Waiting for previous operation '
                                              f'to complete')
                    while cls._busy_event.is_set():
                        Monitor.throw_exception_if_abort_requested(timeout=0.2)

                cls._busy_event.set()

                # New notifications simply cancel the old one

                if cls._timer_state != TimerState.IDLE:
                    cls.cancel(usage='Config forced cancel of running timer')

                cls._msg = msg
            except Exception:
                cls._logger.exception()
            finally:
                cls._lock_cv.notify_all()

    @classmethod
    def start_action(cls) -> None:
        cls._logger.debug(f'title: {cls._title} About to notify')
        with cls._lock_cv:
            try:
                if not cls._busy_event.is_set():
                    cls._logger.error(f'title: {cls._title} _busy_event is NOT set')

                Glue.get_dialog().update_notification_labels(text=cls._msg)
                TrailerStatus.set_notification_msg(msg=cls._msg)
            finally:
                cls._lock_cv.notify_all()

    @classmethod
    def stop_action(cls, called_early: bool,
                    stop_play: bool = False):
        cls._logger.debug(f'title: {cls._title} called_early: {called_early} '
                          f'stop_play: {stop_play} '
                          f'About to clear notification')
        with cls._lock_cv:
            try:
                if not cls._busy_event.is_set():
                    cls._logger.error(f'title: {cls._title} _busy_event is NOT set')

                TrailerStatus.clear_notification_msg()
                Glue.get_dialog().update_notification_labels(text=None)
            finally:
                cls._lock_cv.notify_all()


NotificationTimer.class_init()


class MovieDetailsTimer(BaseTimer):

    _logger: LazyLogger = None
    _lock: threading.RLock = threading.RLock()
    _lock_cv: threading.Condition = threading.Condition(lock=_lock)
    _timer_state: TimerState = TimerState.IDLE
    _timer: FlexibleTimer = None
    _busy_event: threading.Event = threading.Event()
    _display_seconds: float = Settings.get_time_to_display_detail_info()
    _timer_name = 'Display Movie Details'
    _scroll_plot: bool = None
    _callback_on_stop: Callable[[], None] = None
    _cancel_callback: Callable[[], None] = None
    _cancel_stop_on_play: bool = False
    _cancel_event: threading.Event = threading.Event()
    _cancel_msg: str = None
    _stop_called: bool = None
    _title: str = ''

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def config (cls, scroll_plot: bool,
                display_seconds: float,
                title: str = '',
                callback_on_stop: Callable[[], None] = None) -> None:
        cls._title = title
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

        with cls._lock_cv:
            try:
                if cls._busy_event.is_set():
                    cls._logger.debug_verbose(f'Title: {cls._title} '
                                              f'Waiting for previous operation'
                                              f' to complete')
                    while cls._busy_event.is_set():
                        Monitor.throw_exception_if_abort_requested(timeout=0.2)

                if cls._cancel_event.is_set():
                    cls._logger.debug_verbose(f'Title: {cls._title} '
                                              f'Waiting for cancel to complete')

                    while cls._cancel_event.is_set():
                        Monitor.throw_exception_if_abort_requested(timeout=0.2)

                cls._busy_event.set()

                if cls._incorrect_state(TimerState.IDLE):
                    return

                cls._scroll_plot = scroll_plot
                cls._display_seconds = display_seconds
                cls._callback_on_stop = callback_on_stop
            finally:
                cls._lock_cv.notify_all()

    @classmethod
    def start_action(cls) -> None:
        with cls._lock_cv:
            try:
                if not cls._busy_event.is_set():
                    cls._logger.error(f'Title: {cls._title} _busy_event is NOT set')

                cls._logger.debug(f'Title: {cls._title} '
                                  f'About to set_show_details & voice_detail_view')
                TrailerStatus.set_show_details(scroll_plot=cls._scroll_plot)
                Glue.get_dialog().voice_detail_view()
            finally:
                cls._lock_cv.notify_all()

    @classmethod
    def stop_action(cls, called_early: bool,
                    stop_play: bool = False):
        cls._logger.debug(f'Title: {cls._title} '
                          f'called_early: {called_early} stop_play: {stop_play} '
                          f'Calling TTS.stop and TrailerStatus.opaque')
        with cls._lock_cv:
            try:
                if not cls._busy_event.is_set():
                    cls._logger.error(f'Title: {cls._title} _busy_event is NOT set')

                TTS.stop()
                TrailerStatus.opaque()
            finally:
                cls._lock_cv.notify_all()


MovieDetailsTimer.class_init()


class TrailerTimer(BaseTimer):

    _logger: LazyLogger = None
    _lock: threading.RLock = threading.RLock()
    _lock_cv: threading.Condition = threading.Condition(lock=_lock)
    _timer_state: TimerState = TimerState.IDLE
    _timer: FlexibleTimer = None
    _busy_event: threading.Event = threading.Event()
    _display_seconds: float = Settings.get_max_trailer_play_seconds()
    _timer_name: str = 'TrailerTimer'
    _inform_user: bool = None
    _callback_on_stop: Callable[[], None] = None
    _cancel_callback: Callable[[], None] = None
    _cancel_stop_on_play: bool = False
    _cancel_event: threading.Event = threading.Event()
    _cancel_msg: str = None
    _title: str = ''

    @classmethod
    def config (cls,
                display_seconds: float,
                title: str = '',
                callback_on_stop: Callable[[], None] = None) -> None:
        cls._title = title
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

        with cls._lock_cv:
            try:
                if cls._cancel_event.is_set():
                    cls._logger.debug_verbose(f'Title: {cls._title} '
                                              f'Waiting for cancel to complete')
                    while cls._cancel_event.is_set():
                        Monitor.throw_exception_if_abort_requested(timeout=0.2)

                if cls._busy_event.is_set():
                    cls._logger.debug_verbose(f'Title: {cls._title} '
                                              f'Waiting for previous operation'
                                              f' to complete')
                    while cls._busy_event.is_set():
                        Monitor.throw_exception_if_abort_requested(timeout=0.2)

                cls._busy_event.set()

                if cls._timer_state != TimerState.IDLE:
                    cls.cancel(usage='Config forced cancel of running timer')

                cls.display_seconds = display_seconds
                cls._callback_on_stop = callback_on_stop
            finally:
                cls._lock_cv.notify_all()

    @classmethod
    def start_action(cls) -> None:
        with cls._lock_cv:
            try:
                if not cls._busy_event.is_set():
                    cls._logger.error(f'Title: {cls._title} _busy_event is NOT set')

                cls._logger.debug(f'Title: {cls._title} Calling set_show_trailer,'
                                  f' set_playing_trailer_title')
                TrailerStatus.set_show_trailer()

                trailer_dialog: ForwardRef('TrailerDialog') = Glue.get_dialog()
                verbose: bool = cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                title = trailer_dialog.get_title_string(trailer_dialog._movie, verbose)
                trailer_dialog.set_playing_trailer_title_control(title)
                # text_to_speech.say_text(title, interrupt=True)
            finally:
                cls._lock_cv.notify_all()

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
        cls._logger.debug(f'Title: {cls._title} '
                          f'called_early: {called_early} stop_play: {stop_play}')

        if cls._inform_user and not called_early:
            cls._logger.debug(f'Title {cls._title} '
                              f'About to notify max_play_time exceeded')
            NotificationTimer.config(msg=Messages.get_msg(
                    Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME), title=cls._title)
            NotificationTimer.start()

        TrailerStatus.opaque()
        player = Glue.get_player()
        if not called_early:
            stop_play = True

        if stop_play:
            cls._logger.debug(f'Title: {cls._title} Stopping player',
                              trace=Trace.TRACE_UI_CONTROLLER)
            player.stop()
        else:
            cls._logger.debug(f'Title: {cls._title} Pausing player',
                              trace=Trace.TRACE_UI_CONTROLLER)
            player.pause_play()

        TTS.stop()


TrailerTimer.class_init()


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
