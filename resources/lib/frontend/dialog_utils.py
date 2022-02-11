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

from common.imports import *
from common.constants import Constants
from common.flexible_timer import FlexibleTimer
from common.imports import *
from common.exceptions import AbortException
from common.logger import *
from common.messages import Messages
from common.monitor import Monitor
from common.settings import Settings
from frontend.abstract_dialog_state import BaseDialogStateMgr, DialogState
from frontend.text_to_speech import TTS
from player.my_player import MyPlayer

module_logger = BasicLogger.get_module_logger(module_path=__file__)


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
    IDLE = auto()
    STARTING = auto()
    WAITING = auto()
    CLEANUP_IN_PROGRESS = auto()
    CLEANUP_FINISHED = auto()


class DialogStateMgrAccess:
    _dialog_state_mgr: BaseDialogStateMgr = None
    _logger: BasicLogger = None

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

    # All inheriting classes must override these class variables or
    # they will clobber each other

    _logger: BasicLogger = None

    # All changes to state must be accessed using _lock_cv
    # Variables declared here, but not instantiated or initialized
    # Initialization left to implementing classes

    _lock_cv: threading.Condition = None # threading.Condition()
    _busy_event: threading.Event = None # threading.Event()
    _cancel_event: threading.Event = None # threading.Event()
    _timer_state: TimerState = None # TimerState.IDLE
    _stop_called: bool = None

    _display_seconds: float = None
    _timer_name: str = None
    _timer: FlexibleTimer = None

    # function passed to FlexibleTimer, which it will call once the timer
    # expires Normally (after _display_seconds have elapsed). This function is NOT
    # called when cancelled; instead _cancel_callback is called.

    _callback_on_stop: Callable[[], None] = None
    _cancel_callback: Callable[[], None] = None
    _cancel_stop_on_play: bool = None
    _cancel_msg: str = None
    _debug_label: str = None   # For debug logs

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
    def _start(cls) -> None:
        """
        :return:
        """
        try:
            with cls._lock_cv:
                try:
                    if not cls._busy_event.is_set():
                        cls._logger.error(f'_busy_event is NOT set. debug_label '
                                          f'{cls._debug_label}')
                        cls._cancel_event.clear()  # Just in case
                        return

                    if cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'debug_label: {cls._debug_label} '
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
                                                    f'debug_label: {cls._debug_label}',
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
                                                   cls._debug_label,
                                                   kwargs={'callback':
                                                           cls._callback_on_stop})
                        cls._timer.setName(cls._timer_name)
                        cls._logger.debug(f'debug_label: {cls._debug_label} '
                                          f'Starting timeout in '
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

            if cls._logger.isEnabledFor(DISABLED):
                cls._logger.debug_extra_verbose(f'STATE: {cls._timer_state}',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            return

        except AbortException:
            reraise(*sys.exc_info())

        except Exception:
            cls._logger.exception(msg='')

    @classmethod
    def _incorrect_state(cls, timerstate: TimerState) -> bool:
        if cls._timer_state != timerstate:
            cls._logger.error(f'debug_label: {cls._debug_label} TimerState should be '
                              f'{timerstate} not: '
                              f'{cls._timer_state}. CANCELING LOCK',
                              trace=Trace.TRACE_UI_CONTROLLER)
            cls._logger.dump_stack(msg=f'TimerState should be {timerstate} not: '
                                   f'{cls._timer_state}. CANCELING LOCK')
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
                    cls._stop_called = True
                    if not cls._busy_event.is_set():
                        cls._logger.error(f'debug_label: {cls._debug_label} '
                                          f'_busy_event is NOT set. Returning')
                        return
                finally:
                    cls._lock_cv.notify_all()

            cls._logger.debug(f'debug_label: {cls._debug_label} stop_play: {stop_play}')
            with cls._lock_cv:
                try:
                    if cls._incorrect_state(TimerState.WAITING):
                        return

                    cls._timer_state = TimerState.CLEANUP_IN_PROGRESS
                    if cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'debug_label: {cls._debug_label} '
                                                        f'Setting _timer_state to: '
                                                        f'{cls._timer_state}',
                                                        trace=Trace.TRACE_UI_CONTROLLER)
                finally:
                    cls._lock_cv.notify_all()

            if cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'debug_label: {cls._debug_label} '
                                                f'Stopping',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            with cls._lock_cv:
                try:
                    if cls._incorrect_state(TimerState.CLEANUP_IN_PROGRESS):
                        return

                    cls.stop_action(called_early=called_early, stop_play=stop_play)
                    # Clear
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
                            cls._logger.error(f'debug_label: {cls._debug_label} '
                                              f'cancel_event is NOT set.')
                        next_state = TimerState.CLEANUP_FINISHED
                    else:
                        cls._timer = None
                        next_state = TimerState.IDLE

                    cls._timer_state = next_state
                    if cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(f'debug_label: {cls._debug_label} '
                                                        f'Setting _timer_state to: '
                                                        f'{cls._timer_state}',
                                                        trace=Trace.TRACE_UI_CONTROLLER)

                    if not called_early:
                        if callback is not None:
                            # Terminating without being canceled.
                            cls._logger.debug(f'debug_label: {cls._debug_label} '
                                              f'Calling callback: {callback}')
                            callback()

                        cls._stop_called = False
                        cls._timer = None
                        cls._logger.debug(f'busy_event.clear()')
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

        if cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            cls._logger.debug_extra_verbose(f'debug_label: {cls._debug_label} exit',
                                            trace=Trace.TRACE_UI_CONTROLLER)

    @classmethod
    def cancel(cls, reason: str = '', stop_play: bool = False,
               cancel_callback: Callable[[], None] = None,
               kwargs: Dict[Union[str, Enum], Any] = None) -> bool:
        """
        # Starts the cancelation of this timer. The _config method waits for
        # the cancel to complete before proceeding

        :param kwargs: Kwargs for callable
        :param reason: Displyable comment for debug
        :param stop_play: When cancelling trailer playback. If True, STOP
                          playback, otherwise, pause. Passed to stop_action.
        :param cancel_callback: Callback to pass along to stop_action. This function
                         will be called after the cancel is complete. Note that
                         the Timer's callback for normal timer expiration is NOT
                         called. See FlexibleTimer
        :return: True if cancel initiated, callback called and cancellation
                 complete. At this point _busy_event and _cancel_event are not set,
                 stop_called is False.

                 Otherwise, False, because it was
                 not necessary.
        """
        try:
            cls._logger.debug(f'reason: {reason} stop_play: {stop_play} '
                              f'cancel_callback: {cancel_callback}')
            with cls._lock_cv:
                try:
                    if cls._stop_called:
                        cls._logger.debug(f'debug_label: {cls._debug_label} '
                                          f'Too late to cancel, already stopped')
                        return False

                    # If not busy, then finished. No cancel needed.

                    if not cls._busy_event.is_set():
                        cls._logger.debug(f'debug_label: {cls._debug_label}'
                                          f' _busy_event is NOT set')

                        # Just to make sure
                        cls._cancel_event.clear()
                        return False

                    if cls._cancel_event.is_set():
                        cls._logger.debug(f'debug_label: {cls._debug_label} '
                                          f'Already Marked to be Canceled, waiting for'
                                          f'cancellation to complete')

                        # Wait is in Finally block

                        return False

                    if cls._timer_state != TimerState.WAITING:
                        cls._logger.info(f'debug_label: {cls._debug_label} '
                                         f'TimerState should be WAITING not: '
                                         f'{cls._timer_state}',
                                         trace=Trace.TRACE_UI_CONTROLLER)
                        return False

                    cls._cancel_event.set()

                except AbortException:
                    reraise(*sys.exc_info())

                except Exception:
                    cls._logger.exception(msg='')

                finally:
                    cls._lock_cv.notify_all()

            if cls._logger.isEnabledFor(DISABLED):
                cls._logger.debug(f'debug_label: {cls._debug_label} Canceling for '
                                  f'{reason}',
                                  trace=[Trace.TRACE_UI_CONTROLLER])

            # Running timer early (before timeout)
            cls._logger.debug(f'debug_label: {cls._debug_label} '
                              f'Calling stop early, stop_play: {stop_play}')
            cls._timer.run_now(kwargs={'stop_play': stop_play})
            cls._timer = None

            if kwargs is None:
                kwargs = {}

            kwargs['stop_play'] = stop_play
            cls._cleanup(cancel_callback=cancel_callback, kwargs=kwargs)
            #
            # _cleanup takes care of resetting:
            # _cancel_event, _busy_event, _stop_called
            #
            if cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'debug_label: {cls._debug_label} '
                                                f'exit cancel_event.is_set: '
                                                f'{cls._cancel_event.is_set()}',
                                                trace=Trace.TRACE_UI_CONTROLLER)

        except AbortException:
            reraise(*sys.exc_info())

        except Exception:
            cls._logger.exception(msg='')

        finally:
            i: int = 0
            while cls._busy_event.is_set():
                i += 1
                # Every 5 seconds log msg
                if i % 20 == 0:
                    cls._logger.debug(f'Waiting for _busy_event cleared count: {i}')
                Monitor.throw_exception_if_abort_requested(0.25)
        return True

    @classmethod
    def _cleanup(cls, cancel_callback: Callable[[], None] = None, comment: str = '',
                 kwargs: Dict[str, Union[str, bool]] = None):
        cls._logger.debug(f'debug_label: {cls._debug_label} cancel_callback: '
                          f'{cancel_callback} comment: {comment}')
        try:
            while not Monitor.wait_for_abort(0.1):
                # Wait until:
                #  1- _busy_event.is_set() indicating that the allotted time
                #      to show movie details or the trailer has expired
                #      OR
                #      ane external event has canceled the display
                # 2- _display_timer is None
                #
                with cls._lock_cv:
                    try:
                        if not cls._busy_event.is_set():
                            cls._logger.error(f'debug_label: {cls._debug_label} '
                                              f'_busy_event is NOT set')
                            cls._cancel_event.clear()
                            cls._stop_called: bool = False
                            return

                        if not cls._cancel_event.is_set():
                            cls._logger.error(f'debug_label: {cls._debug_label} '
                                              f'_cancel_event is NOT set')
                            cls._stop_called: bool = False
                            return

                        if cls._timer_state == TimerState.CLEANUP_FINISHED:
                            cls._timer_state = TimerState.IDLE
                            if cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                                cls._logger.debug_extra_verbose(f'debug_label: '
                                                                f'{cls._debug_label} '
                                                                f'Setting _timer_state to:'
                                                                f' {cls._timer_state}',
                                                                trace=
                                                                Trace.TRACE_UI_CONTROLLER)
                            if cancel_callback is not None:
                                cls._logger.debug(f'debug_label: {cls._debug_label} '
                                                  f'Calling cancel_callback')
                                if kwargs is None:
                                    kwargs = {}
                                cancel_callback(**kwargs)
                            cls._logger.debug(f'debug_label: {cls._debug_label} '
                                              f'clearing cancel_event')
                            cls._cancel_event.clear()
                            cls._logger.debug(f'busy_event.clear()')
                            cls._busy_event.clear()
                            cls._stop_called: bool = False
                        break
                    finally:
                        cls._lock_cv.notify_all()

        except AbortException:
            reraise(*sys.exc_info())

        except Exception:
            cls._logger.exception(msg='')

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
    _logger: BasicLogger = None

    # All changes to state must be accessed using _lock_cv
    # Variables declared here, but not instantiated or initialized
    # Initialization left to implementing classes

    _lock_cv: threading.Condition = threading.Condition()
    _busy_event: threading.Event = threading.Event()
    _cancel_event: threading.Event = threading.Event()
    _timer_state: TimerState = TimerState.IDLE

    _display_seconds: float = float(Constants.NOTIFICATION_SECONDS)
    _timer_name: str = None  # Useful for debug logging
    _timer: FlexibleTimer = None

    _notification_msg: str = None
    # _previous_msg: str = None

    # Callback to use when canceled
    _cancel_callback: Callable[[], None] = None
    _cancel_stop_on_play: bool = False

    # Debug msg to use on cancel

    _cancel_msg: str = None
    _stop_called: bool = False
    _debug_label: str = ''

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def start_timer(cls, notification_msg: str, debug_label: str = '') -> None:
        with cls._lock_cv:
            cls._config(notification_msg=notification_msg,
                        debug_label=debug_label)
            cls._start()

    @classmethod
    def _config(cls, notification_msg: str, debug_label: str = '') -> None:
        """
        Configure timer for Notification.

        1- Cancels any existent Notification task
        2- Waits for any cancelation to complete
        3- Configures timer for next message:
           Sets message

        :param notification_msg:
        :param debug_label:
        :return:
        """
        with cls._lock_cv:
            try:
                if cls._busy_event.is_set():
                    # Notifications always cancels any previous Notification

                    if cls._timer_state == TimerState.WAITING:
                        cls.cancel(reason=f'Canceling for new Notification: '
                                          f'{debug_label}')

                    while cls._busy_event.is_set():
                        cls._lock_cv.wait(0.0)
                        Monitor.throw_exception_if_abort_requested(timeout=0.2)

                # Cancel complete. Now can proceed to work on new notification

                cls._logger.debug(f'busy_event.set()')
                cls._busy_event.set()
                cls._debug_label = debug_label
                # if notification_msg == cls._previous_msg:
                #    return

                cls._notification_msg = notification_msg
                # cls._previous_msg = notification_msg

            except AbortException:
                reraise(*sys.exc_info())

            except Exception:
                cls._logger.exception(msg='')
            finally:
                cls._lock_cv.notify_all()

    @classmethod
    def start_action(cls) -> None:
        cls._logger.debug(f'debug_label: {cls._debug_label} About to notify')
        with cls._lock_cv:
            try:
                if not cls._busy_event.is_set():
                    cls._logger.error(f'debug_label: {cls._debug_label} _busy_event '
                                      f'is NOT set. Returning')
                    return

                Glue.get_dialog().update_notification_labels(text=cls._notification_msg)
                TrailerStatus.set_notification_msg(msg=cls._notification_msg)
            finally:
                cls._lock_cv.notify_all()

    @classmethod
    def stop_action(cls, called_early: bool,
                    stop_play: bool = False):
        cls._logger.debug(f'debug_label: {cls._debug_label} called_early: {called_early} '
                          f'stop_play: {stop_play} '
                          f'About to clear notification')
        with cls._lock_cv:
            try:
                if not cls._busy_event.is_set():
                    cls._logger.error(f'debug_label: {cls._debug_label} _busy_event '
                                      f'is NOT set. Returning')
                    return

                TrailerStatus.clear_notification_msg()
                Glue.get_dialog().update_notification_labels(text=None)
            finally:
                cls._lock_cv.notify_all()


NotificationTimer.class_init()


class MovieDetailsTimer(BaseTimer):
    """
    Manages the display of the details for a movie. The UI is handled elsewhere,
    this class simply controls how long the contents are displayed and responds
    to other events that impact the display.

    """
    _logger: BasicLogger = None

    # All changes to state must be accessed using _lock_cv
    # Variables declared here, but not instantiated or initialized
    # Initialization left to implementing classes

    _lock_cv: threading.Condition = threading.Condition()
    _busy_event: threading.Event = threading.Event()
    _cancel_event: threading.Event = threading.Event()
    _timer_state: TimerState = TimerState.IDLE

    _timer: FlexibleTimer = None
    _display_seconds: float = Settings.get_time_to_display_detail_info()
    _timer_name = 'Display Movie Details'
    _scroll_plot: bool = None
    _callback_on_stop: Callable[[], None] = None
    _cancel_callback: Callable[[], None] = None
    _cancel_stop_on_play: bool = False
    _cancel_msg: str = None
    _stop_called: bool = None
    _debug_label: str = ''

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def start_timer(cls,
                    scroll_plot: bool,
                    display_seconds: float,
                    debug_label: str = '',
                    callback_on_stop: Callable[[], None] = None) -> None:
        """

        :param scroll_plot:
        :param display_seconds:
        :param debug_label:
        :param callback_on_stop:
        :return:
        """
        with cls._lock_cv:
            cls._config(scroll_plot=scroll_plot,
                        display_seconds=display_seconds,
                        debug_label=debug_label,
                        callback_on_stop=callback_on_stop)
            cls._start()

    @classmethod
    def _config (cls, scroll_plot: bool,
                 display_seconds: float,
                 debug_label: str = '',
                 callback_on_stop: Callable[[], None] = None) -> None:
        cls._debug_label = debug_label
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

        """
        Configure timer for displaying Movie Details.

        1- Cancels any existent DetailsTimer task
        2- Waits for any cancelation to complete
        3- Configures timer for next message:
           Sets message

        :param scroll_plot: Passed through to the UI. Controls whether to scroll
                            the plot or not. For now, set to False for TFH trailers
                            to prevent very verbose boiler-plate cluttering the
                            screen.
        :param debug_label: Used to help during debugging
        :return:
        """

        with cls._lock_cv:
            try:
                if cls._busy_event.is_set():
                    cls._logger.debug_verbose(f'debug_label: {cls._debug_label} '
                                              f'Canceling prior to MovieDetailsTimer'
                                              f' completion')
                    if cls._timer_state == TimerState.WAITING:
                        cls.cancel(reason=f'Canceling for new MovieDetailsTimer: '
                                          f'{debug_label}')

                    while cls._busy_event.is_set():
                        cls._lock_cv.wait(0.0)
                        Monitor.throw_exception_if_abort_requested(timeout=0.2)

                cls._logger.debug(f'busy_event.set()')
                cls._busy_event.set()
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
                    cls._logger.error(f'_debug_label: {cls._debug_label} _busy_event '
                                      f'is NOT set. Returning')
                    return

                cls._logger.debug(f'_debug_label: {cls._debug_label} '
                                  f'About to set_show_details & voice_detail_view')
                TrailerStatus.set_show_details(scroll_plot=cls._scroll_plot)
                Glue.get_dialog().voice_detail_view()
            finally:
                cls._lock_cv.notify_all()

    @classmethod
    def stop_action(cls, called_early: bool,
                    stop_play: bool = False):
        cls._logger.debug(f'_debug_label: {cls._debug_label} '
                          f'called_early: {called_early} stop_play: {stop_play} '
                          f'Calling TTS.stop and TrailerStatus.opaque')
        with cls._lock_cv:
            try:
                if not cls._busy_event.is_set():
                    cls._logger.error(f'_debug_label: {cls._debug_label} _busy_event is '
                                      f'NOT set. Returning')
                    return

                TTS.stop()
                TrailerStatus.opaque()
            finally:
                cls._lock_cv.notify_all()


MovieDetailsTimer.class_init()


class TrailerTimer(BaseTimer):

    _logger: BasicLogger = None

    # All changes to state must be accessed using _lock_cv
    # Variables declared here, but not instantiated or initialized
    # Initialization left to implementing classes

    _lock_cv: threading.Condition = threading.Condition()
    _busy_event: threading.Event = threading.Event()
    _cancel_event: threading.Event = threading.Event()
    _timer_state: TimerState = TimerState.IDLE

    _timer: FlexibleTimer = None
    _display_seconds: float = Settings.get_max_trailer_play_seconds()
    _timer_name: str = 'TrailerTimer'
    _inform_user: bool = None
    _callback_on_stop: Callable[[], None] = None
    _cancel_callback: Callable[[], None] = None
    _cancel_stop_on_play: bool = False
    _cancel_msg: str = None
    _debug_label: str = ''

    @classmethod
    def class_init(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def start_timer(cls,
                    display_seconds: float,
                    debug_label: str = '',
                    callback_on_stop: Callable[[], None] = None) -> None:
        with cls._lock_cv:
            cls._config(display_seconds=display_seconds,
                        debug_label=debug_label,
                        callback_on_stop=callback_on_stop)
            cls._start()

    @classmethod
    def _config (cls,
                 display_seconds: float,
                 debug_label: str = '',
                 callback_on_stop: Callable[[], None] = None) -> None:
        cls._debug_label = debug_label
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

        with cls._lock_cv:
            try:
                if cls._busy_event.is_set():
                    cls._logger.debug_verbose(f'debug_label: {cls._debug_label} '
                                              f'Canceling previous TrailerTimer')
                if cls._timer_state == TimerState.WAITING:
                    cls.cancel(reason=f'Canceling for new TrailerTimer: '
                                      f'{debug_label}')

                while cls._busy_event.is_set():
                    cls._lock_cv.wait(0.0)
                    Monitor.throw_exception_if_abort_requested(timeout=0.2)

                cls._logger.debug(f'busy_event.set()')
                cls._busy_event.set()
                cls._display_seconds = display_seconds
                cls._callback_on_stop = callback_on_stop
            finally:
                cls._lock_cv.notify_all()

    @classmethod
    def start_action(cls) -> None:
        with cls._lock_cv:
            try:
                if not cls._busy_event.is_set():
                    cls._logger.error(f'_debug_label: {cls._debug_label} _busy_event '
                                      f'is NOT set. Returning')
                    return

                cls._logger.debug(f'_debug_label: {cls._debug_label} Calling '
                                  f'set_show_trailer,'
                                  f' set_playing_trailer_title')
                TrailerStatus.set_show_trailer()

                trailer_dialog: ForwardRef('TrailerDialog') = Glue.get_dialog()
                verbose: bool = cls._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)
                title = trailer_dialog.get_title_string(trailer_dialog._movie, verbose)
                trailer_dialog.set_playing_trailer_title_control(title)
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
        cls._logger.debug(f'_debug_label: {cls._debug_label} '
                          f'called_early: {called_early} stop_play: {stop_play}')

        with cls._lock_cv:
            try:
                if not cls._busy_event.is_set():
                    cls._logger.error(f'_debug_label: {cls._debug_label} _busy_event is '
                                      f'NOT set. Returning')
                    return

                if cls._inform_user and not called_early:
                    cls._logger.debug(f'_debug_label {cls._debug_label} '
                                      f'About to notify max_play_time exceeded')
                    NotificationTimer.start_timer(notification_msg=Messages.get_msg(
                            Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME),
                            debug_label=cls._debug_label)

                TrailerStatus.opaque()
                player = Glue.get_player()
                if not called_early:
                    stop_play = True

                if stop_play:
                    cls._logger.debug(f'Title: {cls._debug_label} Stopping player',
                                      trace=Trace.TRACE_UI_CONTROLLER)
                    player.stop()
                else:
                    cls._logger.debug(f'Title: {cls._debug_label} Pausing player',
                                      trace=Trace.TRACE_UI_CONTROLLER)
                    player.pause_play()

                TTS.stop()
            finally:
                cls._lock_cv.notify_all()


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

    logger: BasicLogger = None

    # show_title_while_playing: bool = Settings.get_show_movie_title()
    show_notification: bool = False

    show_trailer: bool = False
    scroll_plot: bool = False

    _notification_msg: str = None

    _dialog: ForwardRef('TrailerDialog') = None

    @classmethod
    def class_init(cls, dialog: ForwardRef('TrailerDialog')):
        cls._dialog = dialog
        if cls.logger is None:
            cls.logger = module_logger.getChild(cls.__name__)

    @classmethod
    def set_notification_msg(cls, msg: str = None) -> None:
        cls._notification_msg = msg
        cls.value_changed(VisibleFields.NOTIFICATION)

    @classmethod
    def clear_notification_msg(cls) -> None:
        # Called by stop methods
        cls._notification_msg = None
        cls.show_notification = False
        # TODO test to see if needed
        # cls.value_changed(VisibleFields.NOTIFICATION)

    @classmethod
    def get_notification_msg(cls) -> str:
        return cls._notification_msg

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
        cls._notification_msg = None
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
            visible: bool = cls._notification_msg is not None
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
            if cls.logger.isEnabledFor(DEBUG):
                cls.logger.debug_extra_verbose(command,
                                               trace=Trace.TRACE_UI_CONTROLLER)
            xbmc.executebuiltin(command, wait=False)
