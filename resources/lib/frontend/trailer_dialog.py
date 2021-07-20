# -*- coding: utf-8 -*-

"""
Created on Apr 17, 2019

@author: Frank Feuerbacher
"""

import datetime
import queue
from collections import deque
from enum import auto, Enum, IntEnum
import os
import re
import sys
import threading

import xbmc
import xbmcgui
from xbmcgui import (Control, ControlImage, ControlButton, ControlEdit,
                     ControlGroup, ControlLabel, ControlList, ControlTextBox,
                     ControlSpin, ControlSlider, ControlProgress, ControlFadeLabel,
                     ControlRadioButton)

from common.constants import Constants
from common.debug_utils import Debug
from common.imports import *
from common.movie import AbstractMovie, FolderMovie, TFHMovie
from common.movie_constants import MovieField
from common.playlist import Playlist
from common.exceptions import AbortException
from common.logger import LazyLogger, Trace
from common.messages import Messages
from common.monitor import Monitor
from common.utils import Utils
from action_map import Action
from common.settings import Settings
from frontend.history_list import HistoryList
from player.my_player import MyPlayer
from player.player_container import PlayerContainer
from frontend.black_background import BlackBackground
from frontend.movie_manager import MovieManager, MovieStatus
from frontend.history_empty import HistoryEmpty
from frontend.utils import ReasonEvent
from frontend import text_to_speech

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class DialogState(Enum):
    """

    """
    NORMAL = 0
    SKIP_PLAYING_TRAILER = 1
    GROUP_QUOTA_REACHED = 2
    QUOTA_REACHED = 3
    NO_TRAILERS_TO_PLAY = 4
    USER_REQUESTED_EXIT = 5
    START_MOVIE_AND_EXIT = 6
    SHUTDOWN_CUSTOM_PLAYER = 7
    STARTED_PLAYING_MOVIE = 8
    SHUTDOWN = 9

    label_map: Dict[ForwardRef('DialogState'), str] = {
        NORMAL: 'NORMAL',
        SKIP_PLAYING_TRAILER: 'SKIP_PLAYING_TRAILER',
        GROUP_QUOTA_REACHED: 'GROUP_QUOTA_REACHED',
        QUOTA_REACHED: 'QUOTA_REACHED',
        NO_TRAILERS_TO_PLAY: 'NO_TRAILERS_TO_PLAY',
        USER_REQUESTED_EXIT: 'USER_REQUESTED_EXIT',
        START_MOVIE_AND_EXIT: 'START_MOVIE_AND_EXIT',
        SHUTDOWN_CUSTOM_PLAYER: 'SHUTDOWN_CUSTOM_PLAYER',
        STARTED_PLAYING_MOVIE: 'STARTED_PLAYING_MOVIE',
        SHUTDOWN: 'SHUTDOWN'}

    def __ge__(self, other):

        if self.__class__ is other.__class__:
            return self.value >= other.value

        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

    @classmethod
    def get_label(cls, dialog_state: ForwardRef('DialogState')) -> str:
        """

        :param dialog_state:
        :return:
        """
        return DialogState.label_map[dialog_state]


class FieldType(Enum):

    def __init__(self, control_id: int) -> None:
        self._control_id = control_id

    def get_control_id(self) -> int:
        clz = type(self)
        return self._control_id
        # return clz._lookup_fields[self.name].get_control_id()

    SHOW_TRAILER = (38028)
    SHOW_DETAILS = (38001)
    SHOW_TRAILER_TITLE = (38029)
    SHOW_TRAILER_NOTIFICATION = (38030)
    SHOW_DETAILS_NOTIFICATION = (38024)


class VisibleFields(Enum):
    NOTIFICATION = auto()
    TITLE = auto()

    # Either Movie details are displayed or the trailer is played
    SHOW_TRAILER = auto()
    SHOW_CURTAIN = auto()   # Show a open/close curtain
    NEW_TRAILER = auto()
    OPAQUE = auto()
    SHUTDOWN = auto()


class TrailerLifeCycle:
    """
        Manages How long:
            Movie details are displayed
            Trailers are played
            Notifications are displayed

        Takes into account user actions which may cause any of the above
        to be cut short or, in the case of user request to show movie
        details to be untimed, or the pause the playing trailer to stop
        the timer.

        More specifically:
          - There are two timers:
            - Notification timer
                - Controls how long a notification to be displayed
                - Canceled by:
                    Movie Details no longer displayed
                    Trailer no longer displayed
            - Movie timer
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

    logger: LazyLogger = None

    # Only set outside of timer,
    # Only cleared inside of timer

    _notify_event = threading.Event()
    _notify_thread: threading.Thread = None
    _notify_msg_queue: deque = deque(maxlen=30) # Insane size

    _movie_event = threading.Event()
    _movie_timer: threading.Timer = None

    _lock: threading.RLock = threading.RLock()

    @classmethod
    def class_init(cls):
        if cls.logger is None:
            cls.logger = module_logger.getChild(cls.__name__)

    @classmethod
    def _notification(cls, message: str, block: bool = False) -> None:
        try:
            if cls._notify_msg_queue.index(message, 0, 0) == 0:
                return

        except (ValueError, IndexError):
            pass

        cls._notify_msg_queue.append(message)

    @classmethod
    def notification(cls, message: str, block: bool = False) -> None:
        """
            TODO: Rework to always run in separate thread. Block is used when
                running on GUI thread, which means that multiple notifications
                stack up. This is mostly an issue when the same key is pressed
                too  many times, resulting in boring "There are no previous
                trailers to play" messages, or some such.

                We do want multiple notifications to be stacked, but only when
                they are different. Just look for consecutive duplicates. If
                someone presses different keys between duplicates, don't bother
                to help.

            Displays given message for a period of time, but can be
            canceled early, depending upon events.

        :param message: Message to display
        :param block: Blocks if true, otherwise runs asynchronously
        :return:
        """

        # Can get multiple event stacked issuing the same messages on each key.
        # Example: Previous_Movie pressed multiple times when there are none to play

        if (TrailerStatus.get_notification_msg() is not None and
                TrailerStatus.get_notification_msg() == message):
            return

        try:
            if cls.logger.isEnabledFor(LazyLogger.DEBUG):
                cls.logger.debug(f'message: { message}',
                                 trace=Trace.TRACE_UI_CONTROLLER)

            with TrailerLifeCycle._lock:
                if cls._notify_thread is not None:
                    # Unblock any prior use of timer, just in case
                    cls.logger.debug(f'Unblocking any stray notifications '
                                     f'by _notify_event.set',
                                     trace=Trace.TRACE_UI_CONTROLLER)

                    # Can only set outside of the timer thread
                    cls._notify_event.set()

            count: int = 0
            while not cls._notify_event.is_set():
                Monitor.throw_exception_if_abort_requested(timeout=0.1)
                if count > 10:
                    break
                count += 1

            TrailerStatus.get_dialog().update_notification_labels(text=message)
            TrailerStatus.set_notification_msg(msg=message)
            if block:
                cls.logger.debug(f'blocking on notification',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                cls._notification_timer()
            else:
                cls._notify_thread = threading.Thread(target=cls._notification_timer,
                                                      name='notify_and_wait')
                cls.logger.debug(f'Starting notification wait thread',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                cls._notify_thread.start()
        except Exception as e:
            cls.logger.exception('')

        return

    @classmethod
    def _notification_timer(cls) -> None:
        """
            Separate thread to
              - set Notification msg visible
              - wait until a timer (or some other) event occurs
              - set Notification msg invisible
        :param timeout:
        :return:
        """
        try:
            timeout: float = float(Constants.MAX_PLAY_TIME_WARNING_TIME)
            if cls._notify_event.is_set():
                cls.logger.debug(f'FORCING _notify_event to be UNSET: {timeout}',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                with TrailerLifeCycle._lock:
                    cls._notify_event.clear()

            # Wait for timeout or setting of _notify_event externally

            cls.logger.debug(f'About to wait',
                             trace=Trace.TRACE_UI_CONTROLLER)
            result: bool = cls._notify_event.wait(timeout=timeout)
            cls.logger.debug(f'Wait finished result: {result}',
                             trace=Trace.TRACE_UI_CONTROLLER)

            with TrailerLifeCycle._lock:
                TrailerStatus.clear_notification_msg()
                cls._notify_thread = None
                cls._notify_event.clear()
                cls.logger.debug(f'Cleared event and set notify_thread = None '
                                 f'Just cleared notification_msg',
                                 trace=Trace.TRACE_UI_CONTROLLER)
        except Exception as e:
            cls.logger.exception()

    @classmethod
    def clear_notification(cls) -> None:
        if cls._notify_thread is not None:
            # Unblock any prior use of timer, just in case
            cls._notify_event.set()

    @classmethod
    def start_movie_timer(cls, max_play_time: float,
                          playing_trailer: bool,
                          block: bool = False) -> None:
        """

        :param max_play_time: Seconds to display detailed movie info or
                              to play trailer.
        :param playing_trailer: When True, then a trailer is being played,
                                otherwise, MovieDetails are displayed
        :param block: Block until timer expire or user action
        :return: A unique integer that is passed back to cancel this timer.
                 It is simply used to confirm that the correct timer is
                 canceled.
        """

        timeout_action: Callable[[]]
        timer_name: str

        if playing_trailer:
            timeout_action = cls.kill_long_playing_trailer
            timer_name = 'Kill Trailer Timer'
            if max_play_time > Constants.MAX_PLAY_TIME_WARNING_TIME + 2:
                max_play_time -= Constants.MAX_PLAY_TIME_WARNING_TIME
                cls.logger.debug(f'adjusted max_play_time: {max_play_time}',
                                 trace=Trace.TRACE_UI_CONTROLLER)
        else:
            timeout_action = cls.end_movie_details_display
            timer_name = 'Movie Details Timer'

        if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls.logger.debug_extra_verbose(f'Trailer: {playing_trailer} '
                                           f'max_play_time: {max_play_time} '
                                           f'block: {block}',
                                           trace=Trace.TRACE_UI_CONTROLLER)

        # _lock is used to control access to _movie_timer & _movie_event
        #
        # _event.set() is used to indicate that the timer has been
        # canceled or the time-out period has expired.
        #
        # After _event.set() is called, _movie_timer is set to None.
        #
        #
        attempts: int = 5
        while attempts > 0:
            with TrailerLifeCycle._lock:
                if cls._movie_timer is None:
                    cls.logger.debug(f'_movie_timer is None',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                    break
            cls.logger.debug(f'_movie_timer not None attempt: {attempts}',
                             trace=Trace.TRACE_UI_CONTROLLER)
            attempts -= 1
            Monitor.wait_for_abort(0.1)

        with TrailerLifeCycle._lock:
            if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls.logger.debug_extra_verbose(f'got lock, max_play_time: '
                                               f'{max_play_time} ',
                                               trace=Trace.TRACE_UI_CONTROLLER)
            if cls.logger.isEnabledFor(LazyLogger.DEBUG):
                if cls._movie_timer is not None:
                    cls.logger.debug(f'movie_timer was NOT None!',
                                     trace=Trace.TRACE_UI_CONTROLLER)
                if cls._movie_event.is_set():
                    cls.logger.debug(f'movie_event already SET',
                                     trace=Trace.TRACE_UI_CONTROLLER)

            cls._movie_timer = None  # Should already be None
            cls._movie_event.set()  # Free any blocked thread (should not occur)
            cls._movie_event.clear()  # Free/clear should not be necessary
            cls.logger.debug(f'_movie_timer None and _movie_event cleared',
                             trace=Trace.TRACE_UI_CONTROLLER)
            inform_user: bool = True
            if not TrailerStatus.get_dialog().is_random_trailers_play_state(
                    DialogState.USER_REQUESTED_EXIT):
                cls._movie_timer = threading.Timer(max_play_time,
                                                   timeout_action,
                                                   kwargs={'inform_user': inform_user
                                                           })
                cls._movie_timer.setName(timer_name)
                cls.logger.debug(f'Starting _movie_timer timeout in {max_play_time} '
                                 f'seconds',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                cls._movie_timer.start()

        if block:  # Block until either timer expires or user action
            # Don't hog lock, so put in loop

            cls.logger.debug(f'Blocking', trace=Trace.TRACE_UI_CONTROLLER)
            while not Monitor.wait_for_abort(0.1):
                # Always access _movie_event & movie_timer through lock
                with TrailerLifeCycle._lock:
                    # _movie_event is set when the timer has expired or
                    # was canceled
                    if cls._movie_event.is_set():
                        cls.logger.debug(f'UnBlocked _movie_event.is_set',
                                         trace=Trace.TRACE_UI_CONTROLLER)
                        # When done, always clear _movie_event
                        cls._movie_event.clear()

                        # Whoever sets _movie_event is responsible
                        # for setting _movie_timer to None

                        if cls._movie_timer is not None:
                            cls.logger.debug('UnBlocked Expected _movie_timer to be None',
                                             trace=Trace.TRACE_UI_CONTROLLER)
                            cls._movie_timer = None
                            cls.logger.debug(f'UnBlocked _movie_event.clear and _movie_timer None',
                                             trace=Trace.TRACE_UI_CONTROLLER)
                        break

            Monitor.wait_for_abort(0.1)
        return

    @classmethod
    def kill_long_playing_trailer(cls,
                                  inform_user: bool = True) -> None:
        """

        :param inform_user:
        :return:
        """

        try:
            cls.logger.enter()
            if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls.logger.debug_extra_verbose('Now Killing',
                                               trace=Trace.TRACE_UI_CONTROLLER)

            if inform_user:
                cls.notification(Messages.get_msg(
                    Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME))

            cls.logger.debug(f'Stopping player',
                             trace=Trace.TRACE_UI_CONTROLLER)
            TrailerStatus.get_dialog().get_player().stop()

            # Only access _movie_timer and _movie_event within lock

            with TrailerLifeCycle._lock:

                # Always set movie_timer to None when calling
                # _movie_event.set()

                cls.logger.debug(f'setting _movie_timer = None and '
                                 f'_movie_event.set',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                cls._movie_timer = None
                cls._movie_event.set()  # Unblock
        except AbortException:
            raise sys.exc_info()
        except Exception as e:
            cls.logger.exception(msg='')

        if cls.logger.isEnabledFor(LazyLogger.DEBUG):
            cls.logger.debug('exit', trace=Trace.TRACE_UI_CONTROLLER)

    @classmethod
    def cancel_movie_timer(cls, usage: str = '') -> None:
        """

        :return:
        """
        if cls.logger.isEnabledFor(LazyLogger.DEBUG):
            cls.logger.debug(f'Canceling movie_timer for {usage}',
                             trace=[Trace.TRACE_SCREENSAVER,
                                    Trace.TRACE_UI_CONTROLLER])

        # Only access _movie_timer and _movie_event within lock.

        with TrailerLifeCycle._lock:
            # If movie_timer is None, then the timer has already gone
            # off or canceled (shouldn't be able to cancel twice).
            # This code is not rock-solid. It depends upon the caller
            # to not cancel a timer that is expired/canceled after a
            # new one is created, thus canceling the wrong timer.
            #
            # Solutions to this problem:
            # - Use new TrailerLifeCycle instance for each timer (tracking the handle
            #   may be problematic).
            # - Use the Timer as a unique identifier (This also looks tedious and
            #   error-prone due to having to lug this id around in local variables).
            # - Change model to create a new 'Trailer' instance for each trailer
            #   played and store any timer objects needed along with it. This
            #   would be better, but since there are generally two timers for
            #   each trailer played, there is still some exposure.
            # - Since there are usually two movie_timers used for each trailer
            #   (one for display movie details and the other for the trailer
            #   itself), then it would be an improvement to pass the timer's
            #   use to act as a sanity check to confirm that the right timer
            #   instance is being killed. It is easy to know this information.
            #

            if cls._movie_timer is not None:
                cls.logger.debug(f'_movie_timer not None',
                                 trace=Trace.TRACE_UI_CONTROLLER)

                cls.logger.debug(f'movie_timer.cancel',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                cls._movie_timer.cancel()
                cls.logger.debug(f'movie_event.set',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                cls._movie_event.set()  # Unblock
                cls.logger.debug(f'set movie_timer = None',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                cls._movie_timer = None

    @classmethod
    def end_movie_details_display(cls,
                                  inform_user: bool = True) -> None:
        """
            Stops the display of movie details based on a timer.
            Not used when user requests displays of Movie Details
            via SHOW_INFO.

        :return:
        """

        try:
            cls.logger.enter()
            if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls.logger.debug_extra_verbose('Stopping',
                                               trace=Trace.TRACE_UI_CONTROLLER)

            with TrailerLifeCycle._lock:
                cls.logger.debug(f'set movie_timer = None',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                cls._movie_timer = None
                cls.logger.debug(f'movie_event.set',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                cls._movie_event.set()  # Unblock
                cls.logger.debug_extra_verbose(f'_movie_timer = None and _movie_event.set')

        except AbortException:
            raise sys.exc_info()
        except Exception as e:
            cls.logger.exception(msg='')

        if cls.logger.isEnabledFor(LazyLogger.DEBUG):
            cls.logger.debug('exit', trace=Trace.TRACE_UI_CONTROLLER)


TrailerLifeCycle.class_init()


class TrailerStatus:
    '''
    Manages the visibility of information based upon changes to data and
    events.

    Note that most controls displayed when movie details is visible are
    handled directly by Trailer_Dialog.update. However, several controls
    that are optionally visible when playing trailers are handled here.

    This class also controls visibility of movie details or the playing
    trailer.
    '''

    # There are several fields that are displayed when movie details are shown
    # or the trailer is being played.

    FIELDS_SHOWN_WHEN_TRAILER_PLAYED = [
        VisibleFields.NOTIFICATION,
        VisibleFields.TITLE
    ]

    show_notification_seconds: int = 0
    show_details_seconds: int = Settings.get_time_to_display_detail_info()
    show_trailer_seconds: int = Settings.get_max_trailer_length()
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
    def set_show_details(cls,  scroll_plot: bool = False) -> None:
        cls.show_trailer = False
        cls.scroll_plot = scroll_plot
        cls.reset_state()
        cls.value_changed(VisibleFields.SHOW_TRAILER)

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
            if cls._dialog.is_random_trailers_play_state(
                    minimum_exit_state=DialogState.SHUTDOWN_CUSTOM_PLAYER):
                shutdown = True
        except AbortException:
            shutdown = True

        commands = []
        if shutdown:
            pass

        elif changed_field in (VisibleFields.SHOW_TRAILER, VisibleFields.SHOW_CURTAIN):
            if cls.show_trailer:
                # Hide entire Movie details screen first
                # Any notifications are canceled

                cls.get_dialog().set_visibility(False, FieldType.SHOW_DETAILS)
                cls.get_dialog().set_visibility(False, FieldType.SHOW_TRAILER_NOTIFICATION)
                if changed_field != VisibleFields.SHOW_CURTAIN:
                    show_title_while_playing: bool = Settings.get_show_movie_title()
                    if show_title_while_playing:
                        cls.get_dialog().set_visibility(True, FieldType.SHOW_TRAILER_TITLE)

                cls.get_dialog().set_visibility(True, FieldType.SHOW_TRAILER)

            else:
                # Show movie details
                cls.get_dialog().set_visibility(False, FieldType.SHOW_TRAILER)
                cls.get_dialog().set_visibility(False, FieldType.SHOW_DETAILS_NOTIFICATION)
                if cls.scroll_plot:
                    commands.append("Skin.SetBool(ScrollPlot)")
                else:
                    commands.append("Skin.Reset(ScrollPlot)")

                cls.get_dialog().set_visibility(True, FieldType.SHOW_DETAILS)

        elif changed_field == VisibleFields.NOTIFICATION:
            visible: bool = cls.notification_msg is not None
            if cls.show_trailer:
                cls.get_dialog().set_visibility(visible, FieldType.SHOW_TRAILER_NOTIFICATION)
            else:
                cls.get_dialog().set_visibility(visible, FieldType.SHOW_DETAILS_NOTIFICATION)

        elif changed_field == VisibleFields.OPAQUE:
            cls.get_dialog().set_visibility(False, FieldType.SHOW_DETAILS)
            cls.get_dialog().set_visibility(False, FieldType.SHOW_TRAILER)

        for command in commands:
            if cls.logger.isEnabledFor(LazyLogger.DEBUG):
                cls.logger.debug_extra_verbose(command,
                                               trace=Trace.TRACE_UI_CONTROLLER)
            xbmc.executebuiltin(command, wait=False)

    @classmethod
    def cancel_movie_timer(cls, usage: str = '') -> None:
        TrailerLifeCycle.cancel_movie_timer(usage=usage)

    @classmethod
    def get_dialog(cls) -> ForwardRef('TrailerDialog'):
        return cls._dialog


class TrailerDialog(xbmcgui.WindowXMLDialog):
    """
        Note that the underlying 'script-movie-window.xml' has a "videowindow"
        control. This causes the player to ignore many of the normal keymap actions.
    """
    DETAIL_GROUP_CONTROL: int = 38001

    DUMMY_TRAILER: AbstractMovie = FolderMovie({
        MovieField.TITLE: '',
        MovieField.THUMBNAIL: '',
        MovieField.FANART: '',
        MovieField.ACTORS: '',
        MovieField.PLOT: '',
    })

    _playlist_map: Dict[int, int] = {xbmcgui.REMOTE_1: 1,
                                     xbmcgui.REMOTE_2: 2,
                                     xbmcgui.REMOTE_3: 3,
                                     xbmcgui.REMOTE_4: 4,
                                     xbmcgui.REMOTE_5: 5,
                                     xbmcgui.REMOTE_6: 6,
                                     xbmcgui.REMOTE_7: 7,
                                     xbmcgui.REMOTE_8: 8,
                                     xbmcgui.REMOTE_9: 9,
                                     xbmcgui.REMOTE_0: 10,

                                     xbmcgui.ACTION_JUMP_SMS2: 2,
                                     xbmcgui.ACTION_JUMP_SMS3: 3,
                                     xbmcgui.ACTION_JUMP_SMS4: 4,
                                     xbmcgui.ACTION_JUMP_SMS5: 5,
                                     xbmcgui.ACTION_JUMP_SMS6: 6,
                                     xbmcgui.ACTION_JUMP_SMS7: 7,
                                     xbmcgui.ACTION_JUMP_SMS8: 8,
                                     xbmcgui.ACTION_JUMP_SMS9: 9}
    TFH_JUNK_PATTERN: Pattern = re.compile(r'(\n ?\n.*)|'
              r'(?:Like us on Facebook.*)|'
              r'(?:http://www.trailersfromhell.com.*)|'
              r'(?:ABOUT TRAILERS FROM HELL:.*)|'
              r'(?:As always, you can find more commentary.*)|'
              r'(?:But wait! There\'s more! TFH.*)|'
              r'(?:Want more TFH.*)|'
              r'(?:Want to know more? The TFH.*)|'
              r'(?:DID YOU KNOW: we have a podcast.*)', re.DOTALL)

    logger: LazyLogger = None

    def __init__(self, *args: Any) -> None:
        """

        :param args:
        """
        super().__init__(*args)
        clz = type(self)
        if clz.logger is None:
            clz.logger = module_logger.getChild(clz.__name__)
        clz.logger.enter()

        self._dialog_state: Enum = DialogState.NORMAL
        self._player_container: PlayerContainer = PlayerContainer.get_instance()
        self._player_container.register_exit_on_movie_playing(
            self.exit_screensaver_to_play_movie)

        self.get_player().set_callbacks(on_show_info=self.show_detailed_info)
        self._title_control: ControlLabel = None
        self._source: str = None
        self._movie: AbstractMovie = None
        self._lock: threading.RLock = threading.RLock()
        self._viewed_playlist: Playlist = Playlist.get_playlist(
            Playlist.VIEWED_PLAYLIST_FILE, append=False, rotate=True)

        self._viewed_playlist.add_timestamp()
        self._thread: threading.Thread = None

        # Used mostly as a timer
        self._wait_event: ReasonEvent = ReasonEvent()
        Monitor.register_abort_listener(self.on_abort_event)

        self._movie_manager: MovieManager = MovieManager()
        self._queued_movie: AbstractMovie = None
        self._get_next_trailer_start: datetime.datetime = None
        self.trailers_per_iteration: int = None
        self.group_trailers: bool = None
        self.total_trailers_to_play: int = None
        self.delay_between_groups: int = None
        self.exiting_playing_movie: bool = False
        TrailerStatus.class_init(self)

    def onInit(self) -> None:
        """

        :return:
        """
        clz = type(self)
        clz.logger.enter()

        # Prevent flash of grid
        #
        # TrailerStatus.opaque()

        if self._thread is None:
            # noinspection PyTypeChecker
            self._thread = threading.Thread(
                target=self.play_trailers, name='TrailerDialog')
            self._thread.start()

    def configure_trailer_play_parameters(self) -> None:
        """

        :return:
        """
        total_trailers_to_play: int = Settings.get_number_of_trailers_to_play()

        trailers_per_group: int = total_trailers_to_play
        group_trailers: bool = Settings.is_group_trailers()

        if group_trailers:
            trailers_per_group = Settings.get_trailers_per_group()

        trailers_per_iteration: int = total_trailers_to_play
        if trailers_per_group > 0:
            trailers_per_iteration = trailers_per_group
            if total_trailers_to_play > 0:
                trailers_per_iteration = min(
                    trailers_per_iteration, total_trailers_to_play)

        delay_between_groups: int = Settings.get_group_delay()

        self.trailers_per_iteration = trailers_per_iteration
        self.group_trailers = group_trailers
        self.total_trailers_to_play = total_trailers_to_play
        self.delay_between_groups = delay_between_groups

    def play_trailers(self) -> None:
        """

        :return:
        """
        clz = type(self)
        self.configure_trailer_play_parameters()
        trailers_played: int = 0
        try:
            while not self.is_random_trailers_play_state():
                self.play_a_group_of_trailers()

                if self.is_random_trailers_play_state(DialogState.NO_TRAILERS_TO_PLAY):
                    break

                self._player_container.get_player().wait_for_is_not_playing_video()

                # Pre-seed all fields with empty values so that if display of
                # detailed movie text occurs prior to download of external
                # images, etc. This way default values are shown instead of
                # leftovers from previous movie.

                self._movie = TrailerDialog.DUMMY_TRAILER
                self.update_detail_view()  # Does not display

                if self.group_trailers:
                    if self.total_trailers_to_play > 0:
                        trailers_played += self.trailers_per_iteration
                        remaining_to_play = self.total_trailers_to_play - trailers_played
                        if remaining_to_play <= 0:
                            break

                    self._wait_event.wait(self.delay_between_groups)
                    if self.is_random_trailers_play_state(
                            DialogState.USER_REQUESTED_EXIT):
                        break
                    if self.is_random_trailers_play_state(DialogState.NORMAL):
                        # Wake up and resume playing trailers early
                        pass
                    self.set_random_trailers_play_state(DialogState.NORMAL)

                elif self.is_random_trailers_play_state(DialogState.QUOTA_REACHED):
                    break

        except AbortException:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz.logger.debug_verbose('Received abort')

        except Exception as e:
            clz.logger.exception('')
        finally:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose(
                    'About to close TrailerDialog')

            clz.logger.debug_extra_verbose(f'Canceling Trailer Dialog to exit'
                                           f' randomtrailers',
                                           trace=Trace.TRACE_UI_CONTROLLER)
            TrailerStatus.cancel_movie_timer(usage=f'Canceling Trailer Dialog to exit '
                                                   f'randomtrailers')
            self._viewed_playlist.close()
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose('Closed TrailerDialog')
            self.shutdown()
            return  # Exit thread

    def play_a_group_of_trailers(self) -> None:
        """
            Main Loop to get and display Trailer Information and Trailers

        :return:
        """
        clz = type(self)
        TrailerStatus.opaque()

        number_of_trailers_played = 0
        try:
            # Main movie playing loop

            if Settings.get_show_curtains():
                self._movie_manager.play_curtain_next(MovieManager.OPEN_CURTAIN)

            while not self.is_random_trailers_play_state():
                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    self._dialog_state = DialogState.NORMAL

                # Blank the screen

                TrailerStatus.opaque()

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
                    TrailerLifeCycle.notification(msg, block=True)
                    continue

                # Are there no trailers to play now, and in the future?

                if status == MovieStatus.OK and self._movie is None:
                    self.set_random_trailers_play_state(
                        DialogState.NO_TRAILERS_TO_PLAY)
                    break

                elif status == MovieStatus.IDLE:
                    self.set_random_trailers_play_state(
                        DialogState.NO_TRAILERS_TO_PLAY)
                    clz.logger.warning('Should not get state IDLE')
                    break

                # TODO: User feedback instead of blank screen?

                if status == MovieStatus.TIMED_OUT:
                    continue

                if status == MovieStatus.BUSY:
                    continue

                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    continue

                if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    clz.logger.debug_verbose('got trailer to play: ' +
                                             self._movie.get_trailer_path())

                video_is_curtain = (self._movie.get_source() == 'curtain')

                # TODO: fix comment
                # Screen will be black since both
                # TrailerDialog.PLAYER_GROUP_CONTROL and
                # TrailerDialog.DETAIL_GROUP_CONTROL are, by default,
                # not visible in script-trailerwindow.xml

                # Wait until previous video is complete.
                # Our event listeners will stop the player, as appropriate.

                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose(
                        'wait for not playing 1')
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

                if self._source == MovieField.FOLDER_SOURCE:
                    show_movie_details = False

                if video_is_curtain:
                    show_movie_details = False
                    show_title_while_playing = False

                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose(
                        'checking play_state 1')
                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    continue
                if self.is_random_trailers_play_state():
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                        clz.logger.debug_extra_verbose(
                            'breaking due to play_state 1 movie:',
                            self._movie.get_title())
                    break

                # This will block if showing Movie Details
                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose(
                        f'about to show_movie_info movie: {self._movie.get_title()} '
                        f'show_detail: {show_movie_details} '
                        f'title while playing: {show_title_while_playing} block: {True}')

                # TODO:  Change to separate calls for show details and show title during trailer
                self.show_movie_info(show_detail_info=show_movie_details,
                                     show_title_while_playing=show_title_while_playing,
                                     block=True)
                if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                    clz.logger.debug_extra_verbose(
                        'finished show_movie_info, movie:',
                        self._movie.get_title())

                # Play Trailer

                # TODO: change to asynchronous so that it can occur while
                # showing details

                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose('checking play_state 2 movie:',
                                                   self._movie.get_title())
                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(f'SKIP_PLAYING_TRAILER: '
                                                       f'{self._movie.get_title()}')
                    continue
                if self.is_random_trailers_play_state(
                        minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(
                            'Breaking due to play_state 2 movie:',
                            self._movie.get_title())
                    break

                if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                    clz.logger.debug_extra_verbose(f'About to play: '
                                                   f'{self._movie.get_title()} '
                                                   f'path: '
                                                   f'{self._movie.get_trailer_path()}')

                # show_movie_info, above, already calls this
                # TrailerStatus.set_show_trailer()

                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose('About to play trailer:',
                                                   self._movie.get_title())
                normalized = False
                cached = False
                trailer_path = None
                if self._movie.has_normalized_trailer():
                    trailer_path = self._movie.get_normalized_trailer_path()
                    self.get_player().play_trailer(trailer_path, self._movie)
                    normalized = True
                elif self._movie.has_cached_trailer():
                    trailer_path = self._movie.get_cached_trailer()
                    self.get_player().play_trailer(trailer_path, self._movie)
                    cached = True
                else:
                    trailer_path = self._movie.get_trailer_path()
                    self.get_player().play_trailer(trailer_path, self._movie)

                time_to_play_trailer = (datetime.datetime.now() -
                                        self._get_next_trailer_start)
                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose('started play_trailer:',
                                                   self._movie.get_title(),
                                                   'elapsed seconds:',
                                                   time_to_play_trailer.total_seconds(),
                                                   'source:', self._movie.get_source(),
                                                   'normalized:', normalized,
                                                   'cached:', cached,
                                                   'path:', trailer_path)

                # Again, we rely on our listeners to interrupt, as
                # appropriate. Trailer/Movie should be about to be played or
                # playing.

                try:
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(
                            'checking play_state 3 movie:',
                            self._movie.get_title())
                    if self.is_random_trailers_play_state(
                            DialogState.SKIP_PLAYING_TRAILER,
                            exact_match=True):
                        continue
                    if self.is_random_trailers_play_state(
                            minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                'breaking at play_state 3 movie:',
                                self._movie.get_title())
                        break

                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(
                            'wait_for_is_playing_video 2 movie:',
                            self._movie.get_title())
                    if not self.get_player().wait_for_is_playing_video(path=trailer_path,
                                                                       timeout=5.0):
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                'Timed out Waiting for Player.')

                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(
                            'checking play_state 4 movie:',
                            self._movie.get_title())
                    if self.is_random_trailers_play_state(
                            DialogState.SKIP_PLAYING_TRAILER,
                            exact_match=True):
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(f'SKIP_PLAYING_TRAILER: '
                                                           f'{self._movie.get_title()}')
                        continue
                    if self.is_random_trailers_play_state(
                            minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz.logger.debug_extra_verbose(
                                'breaking at play_state 4 movie:',
                                self._movie.get_title())
                        break

                    '''
                    # Now that the movie has started, see if it will run too long so
                    # that we need to set up to kill it playing.

                    trailer_total_time = self.get_player().getTotalTime()
                    max_play_time = Settings.get_max_trailer_length()
                    if trailer_total_time > max_play_time:
                        if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                            clz.logger.debug_verbose(
                                'Killing long movie:',
                                self._movie.get_title(), 'limit:',
                                max_play_time)
                        TrailerLifeCycle.start_movie_timer(
                            max_play_time, playing_trailer=True)
                    '''
                except AbortException:
                    raise sys.exc_info()
                except Exception as e:
                    clz.logger.exception('')

                # Again, we rely on our listeners to stop the player, as
                # appropriate

                self.get_player().wait_for_is_not_playing_video()
                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose(
                        f'Trailer not playing; checking play_state 5 movie:'
                        f' {self._movie.get_title()}')
                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    continue
                if self.is_random_trailers_play_state(
                        minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(
                            'breaking at play_state 5 movie:',
                            self._movie.get_title())
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
                clz.logger.error('There will be no trailers to play')
                TrailerLifeCycle.notification(Messages.get_msg(
                    Messages.NO_TRAILERS_TO_PLAY))
                self.set_random_trailers_play_state(
                    DialogState.NO_TRAILERS_TO_PLAY)
            else:
                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose(
                        'out of inner play loop movie:',
                        self._movie.get_title())

            if Settings.get_show_curtains():
                self._movie_manager.play_curtain_next(MovieManager.CLOSE_CURTAIN)

                _, curtain = self._movie_manager.get_next_trailer()
                TrailerStatus.set_show_curtain()

                self.get_player().play_trailer(curtain.get_trailer_path(),
                                               curtain)
                if not self.get_player().wait_for_is_playing_video(
                        path=curtain.get_trailer_path(),
                        timeout=5.0):
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz.logger.debug_extra_verbose(
                            'Timed out Waiting for Player.')
                self.get_player().wait_for_is_not_playing_video()

            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose(
                    'Completed everything except play_movie, if there is one')
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

        try:
            if self._movie is not None:
                if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                    clz.logger.debug_extra_verbose(
                        'Checking to see if there is a movie to play:',
                        self._movie.get_title())
            if self.is_random_trailers_play_state(DialogState.START_MOVIE_AND_EXIT,
                                                  exact_match=True):
                if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                    clz.logger.debug_extra_verbose(
                        'about to play movie:', self._queued_movie)
                TrailerStatus.opaque()
                self.play_movie(self._queued_movie)

        except AbortException:
            clz.logger.debug('Received shutdown or abort')
        except Exception as e:
            clz.logger.exception('')

    def get_player(self) -> MyPlayer:
        return self._player_container.get_player()

    def is_random_trailers_play_state(self,
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
        clz = type(self)
        match = False
        if Monitor is None or Monitor.is_abort_requested():
            self._dialog_state = DialogState.SHUTDOWN

        if self._dialog_state == DialogState.SHUTDOWN:
            if throw_exception_on_abort and Monitor is not None:
                Monitor.throw_exception_if_abort_requested()
            else:
                match = True
        elif exact_match:
            match = self._dialog_state == minimum_exit_state
        else:
            match = self._dialog_state >= minimum_exit_state
        return match

    def show_movie_info(self,
                        show_detail_info: bool = False,
                        show_title_while_playing: bool = False,
                        block: bool = False) -> None:
        """

        :param block:
        :param show_detail_info:
        :param show_title_while_playing:
        """
        clz = type(self)
        if show_detail_info:
            self.show_detailed_info(block=block)
        else:
            self.hide_detail_info()
        #
        # You can have both showMovieDetails (movie details screen
        # shown prior to playing movie) as well as the
        # simple VideoOverlayTitle while the movie is playing.
        #
        if show_title_while_playing:
            # Don't display Movie Detail (Trailers from folders have none)

            title = self.get_title_string(self._movie)
            self.set_playing_trailer_title_control(title)
            if show_detail_info:
                TrailerStatus.set_show_trailer()
            else:
                text_to_speech.say_text(title, interrupt=True)

    def show_detailed_info(self, from_user_request: bool = False,
                           block: bool = False) -> None:
        """

        :param block:
        :param from_user_request:
        """
        clz = type(self)

        if self._source != MovieField.FOLDER_SOURCE:
            if (clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                    and clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
                clz.logger.debug(f'about to show_detailed_info: from_user_request: '
                                 f'{from_user_request}')
            display_seconds = Settings.get_time_to_display_detail_info()
            if from_user_request:
                # User must perform some action to unblock
                display_seconds = 60 * 60 * 24 * 365  # One year

            if self.get_player() is not None and self.get_player().isPlaying(): # fpf
                # Pause playing trailer
                clz.logger.debug(f'Pausing Player', trace=Trace.TRACE_UI_CONTROLLER)
                self.get_player().pause_play()

            self.update_detail_view()
            self._show_detail_info(self._movie, display_seconds,
                                   block=block)

        #  TODO: Add msg if folder source

    def _show_detail_info(self, movie: AbstractMovie,
                          display_seconds: int = 0,
                          block: bool = False) -> None:
        """
        Shows the already updated detail view.

        Primarily called from the thread which plays trailers. In this case,
        after making the detail view visibile, this method blocks for display_seconds
        (or an action cancels).

        This method can also be called as the result of an action from the gui
        thread. In this case, display_seconds is 0 and no blocking occurs after
        making the detail view visible. It is up to some other action (or event)
        to change the visibility.

        :param movie:
        :param display_seconds:
        :return: unique identifier for the created movie_timer
        """
        clz = type(self)

        # TFH tend to have a LOT of boilerplate after the movie specific info

        if isinstance(movie, TFHMovie):
            scroll_plot = False
        else:
            scroll_plot = True

        TrailerStatus.set_show_details(scroll_plot=scroll_plot)

        # Wait for kodi player to say that it is paused and then the title

        # Monitor.wait_for_abort(3.0)
        self.voice_detail_view()

        Monitor.throw_exception_if_abort_requested()
        TrailerLifeCycle.start_movie_timer(
            max_play_time=display_seconds, playing_trailer=False,
            block=block)
        if block:
            Monitor.throw_exception_if_abort_requested()

        # Force speech to stop
        # text_to_speech.say_text('.', interrupt=True)
        return

    def hide_detail_info(self) -> None:
        """

        :return:
        """
        clz = type(self)
        clz.logger.enter()
        TrailerLifeCycle.cancel_movie_timer(usage=f'hide_detail')

    def update_detail_view(self) -> None:
        """

        :return:
        """
        clz = type(self)
        try:
            Monitor.throw_exception_if_abort_requested()
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.enter()

            control: Union[ControlImage, Control] = self.getControl(38002)
            thumbnail = self._movie.get_thumbnail()
            if thumbnail is None:
                control.setVisible(False)
            else:
                control.setImage(thumbnail)
                control.setVisible(True)

            control: Union[ControlImage, Control] = self.getControl(38004)
            image = self._movie.get_fanart()
            if image is None:
                control.setVisible(False)
            else:
                control.setVisible(True)
                control.setImage(self._movie.get_fanart())

            verbose = False
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                verbose = True
            title_string = self.get_title_string(self._movie, verbose)

            title_control: Union[ControlLabel,
                                 Control] = self.getControl(38003)
            title_control.setLabel(title_string)

            # title.setAnimations(
            #    [('Hidden', 'effect=fade end=0 time=1000')])

            control: Union[ControlLabel, Control] = self.getControl(38025)
            control.setLabel(self.bold(Messages.get_msg(Messages.DIRECTOR_LABEL)))
            control.setVisible(True)

            control: Union[ControlLabel, Control] = self.getControl(38005)
            movie_directors: List[str] = self._movie.get_directors()
            if movie_directors is None:
                control.setVisible(False)
            else:
                control.setLabel(', '.join(movie_directors))
                control.setVisible(True)

            control: Union[ControlLabel, Control] = self.getControl(38026)
            control.setLabel(self.bold(Messages.get_msg(Messages.WRITER_LABEL)))
            control.setVisible(True)

            control: Union[ControlLabel, Control] = self.getControl(38027)
            control.setLabel(self.bold(Messages.get_msg(Messages.STARS_LABEL)))
            control.setVisible(True)

            movie_actors: List[str] = self._movie.get_actors()
            control: Union[ControlLabel, Control] = self.getControl(38006)
            control.setLabel(', '.join(movie_actors))
            control.setVisible(True)

            control: Union[ControlLabel, Control] = self.getControl(38007)
            movie_writers = ', '.join(self._movie.get_writers())
            if movie_writers is None:
                control.setVisible(False)
            else:
                control.setLabel(movie_writers)
                control.setVisible(True)

            control: Union[ControlTextBox, Control] = self.getControl(38009)
            plot: str = self._movie.get_plot()
            if plot is None:
                plot = ''

            cleaned_plot = plot
            if isinstance(self._movie, TFHMovie):
                '''
                patterns = [
                    r'\n ?\n.*',
                    # r'\nA(nd, a)?s always, find more great cinematic classics at
                    # http://www.trailersfromhell.com',
                    # r'\n \nAnd, as always, find more cinematic greatness at
                    # http://www.trailersfromhell.com',
                    # r'\n \nAs always, you can find more commentary, more reviews,
                    # more podcasts, and more deep-dives into the films you don\'t know
                    # you love yet over on the Trailers From Hell mothership:',
                    r'Like us on Facebook.*',
                    r'http://www.trailersfromhell.com.*',
                    r'ABOUT TRAILERS FROM HELL:.*',
                    r'As always, you can find more commentary.*',
                    r'But wait! There\'s more! TFH.*',
                    r'Want more TFH.*',
                    r'Want to know more? The TFH.*',
                    r'DID YOU KNOW: we have a podcast.*'
                ]

                # Remove all patterns
                # for pattern in patterns:
                #     cleaned_plot = re.sub(pattern, r'', cleaned_plot)
                '''
                cleaned_plot = re.sub(TrailerDialog.TFH_JUNK_PATTERN,
                                      r'', cleaned_plot)

                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose('Plot original text:', plot)
                    clz.logger.debug_extra_verbose('Plot text:', cleaned_plot)

                    cleaned_plot += '\n=======Original Text===========\n' + plot

            if cleaned_plot is None:
                control.setVisible(False)
            else:
                control.setText(cleaned_plot)
                control.setVisible(True)

            control: Union[ControlLabel, Control] = self.getControl(38010)
            movie_studios = ', '.join(self._movie.get_studios())
            if movie_studios is None:
                control.setVisible(False)
            else:
                control.setLabel(movie_studios)
                control.setVisible(True)

            label = Messages.get_formatted_msg(Messages.RUNTIME_GENRE,
                                               self._movie.get_detail_runtime(),
                                               self._movie.get_detail_genres())
            control: Union[ControlLabel, Control] = self.getControl(38011)
            control.setLabel(label)

            image = 'stars/{:.1f}.png'.format(
                self._movie.get_rating())
            rating_control: Union[ControlImage,
                                  Control] = self.getControl(38012)
            rating_control.setImage(image)
            rating_control.setColorDiffuse('0xC0FFD700')

            control: Union[ControlImage, Control] = self.getControl(38013)
            certification_image_path = self._movie.get_certification_image_path()
            if certification_image_path is None:
                control.setVisible(False)
            else:
                certification_image_path = f'ratings/{certification_image_path}.png'
                control.setImage(certification_image_path)
                control.setVisible(True)

            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.exit()

        except AbortException:
            raise sys.exc_info()
        except Exception as e:
            clz.logger.exception('')
        finally:
            pass

    def set_visibility(self, visible: bool, field: FieldType ) -> None:
        control_id: int = field.get_control_id()
        control: Union[ControlLabel, Control] = self.getControl(control_id)
        control.setVisible(visible)
        if self.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            self.logger.debug_extra_verbose(f'Setting Field: {field} visible: {visible}')

    def voice_detail_view(self) -> None:
        """

        :return:
        """
        clz = type(self)
        try:
            Monitor.throw_exception_if_abort_requested()
            if self.logger.isEnabledFor(LazyLogger.DEBUG):
                clz.logger.enter()

            title_label = Messages.get_formatted_msg(Messages.TITLE_LABEL)
            text_to_speech.say_text(title_label, interrupt=True)

            title_string = self.get_title_string(self._movie)
            text_to_speech.say_text(title_string, interrupt=False)

            rating: float = self._movie.get_rating()

            # convert to scale of 5 instead of 10, Round to nearest 0.5

            rating = int(rating * 10) / 20.0

            # "Rated 4.5 out of 5 stars"
            text_to_speech.say_text(
                Messages.get_formatted_msg(Messages.VOICED_STARS, str(rating)))

            # MPAA rating
            certification = self._movie.get_detail_certification()
            text_to_speech.say_text(
                Messages.get_formatted_msg(
                    Messages.VOICED_CERTIFICATION, certification))

            runtime_genres = Messages.get_formatted_msg(
                Messages.RUNTIME_GENRE,
                self._movie.get_detail_runtime(),
                self._movie.get_detail_genres())
            text_to_speech.say_text(runtime_genres, interrupt=False)

            director_label = \
                Messages.get_formatted_msg(Messages.DIRECTOR_LABEL)
            text_to_speech.say_text(director_label, interrupt=False)

            # When TTS uses cached speech files, say the Directors one at a time
            # to reduce cached messages

            for director in self._movie.get_voiced_directors():
                text_to_speech.say_text(director, interrupt=False)

            writer_label = \
                Messages.get_formatted_msg(Messages.WRITER_LABEL)
            text_to_speech.say_text(writer_label, interrupt=False)

            # When TTS uses cached speech files, say the writers one at a time
            # to reduce cached messages

            for writer in self._movie.get_voiced_detail_writers():
                text_to_speech.say_text(writer, interrupt=False)

            stars_label = \
                Messages.get_formatted_msg(Messages.STARS_LABEL)
            text_to_speech.say_text(stars_label, interrupt=False)

            # When TTS uses cached speech files, say the Actors one at a time
            # to reduce cached messages

            for actor in self._movie.get_voiced_actors():
                text_to_speech.say_text(actor)

            plot_label = Messages.get_formatted_msg(Messages.PLOT_LABEL)
            text_to_speech.say_text(plot_label, interrupt=False)

            plot: str = self._movie.get_plot()
            if plot is None:
                plot = ''

            cleaned_plot = plot
            if isinstance(self._movie, TFHMovie):
                patterns = [
                    r'\n ?\n.*',
                    # r'\nA(nd, a)?s always, find more great cinematic classics at
                    # http://www.trailersfromhell.com',
                    # r'\n \nAnd, as always, find more cinematic greatness at
                    # http://www.trailersfromhell.com',
                    # r'\n \nAs always, you can find more commentary, more reviews,
                    # more podcasts, and more deep-dives into the films you don\'t know
                    # you love yet over on the Trailers From Hell mothership:',
                    r'Like us on Facebook.*',
                    r'http://www.trailersfromhell.com.*',
                    r'ABOUT TRAILERS FROM HELL:.*',
                    r'As always, you can find more commentary.*',
                    r'But wait! There\'s more! TFH.*',
                    r'Want more TFH.*',
                    r'Want to know more? The TFH.*',
                    r'DID YOU KNOW: we have a podcast.*'
                ]

                # Remove all patterns
                # for pattern in patterns:
                #     cleaned_plot = re.sub(pattern, r'', cleaned_plot)
                cleaned_plot = re.sub(TrailerDialog.TFH_JUNK_PATTERN,
                                      r'', cleaned_plot)

            # self.logger.debug('Plot original text:', plot)
            # self.logger.debug('Plot text:', cleaned_plot)
            text_to_speech.say_text(cleaned_plot, interrupt=False)

            # When TTS uses cached speech files, say the Studios one at a time
            # to reduce cached messages

            for studio in self._movie.get_voiced_studios():
                text_to_speech.say_text(studio, interrupt=False)

        except AbortException:
            raise sys.exc_info()
        except Exception as e:
            clz.logger.exception('')
        finally:
            pass

    def doModal(self) -> bool:
        """

        :return:
        """
        clz = type(self)

        super().doModal()
        return self.exiting_playing_movie

    def show(self) -> None:
        """

        :return:
        """
        super().show()

    def close(self) -> None:
        """

        :return:
        """
        super().close()

    def set_random_trailers_play_state(self, dialog_state: DialogState) -> None:
        # TODO: Change to use named int type
        """

        :param dialog_state:
        :return:
        """
        clz = type(self)

        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz.logger.debug_extra_verbose(f'state: {dialog_state}',
                                           trace=Trace.TRACE_SCREENSAVER)

        if dialog_state > self._dialog_state:
            self._dialog_state = dialog_state

        if dialog_state >= DialogState.SHUTDOWN_CUSTOM_PLAYER:
            self.get_player().set_callbacks(on_show_info=None)
            self.get_player().disable_advanced_monitoring()
            self._player_container.use_dummy_player()
            TrailerStatus.opaque()

        if dialog_state >= DialogState.USER_REQUESTED_EXIT:
            # Stop playing movie.

            # Just in case we are paused
            self.get_player().resume_play()
            TrailerLifeCycle.kill_long_playing_trailer(inform_user=False)

        # Multiple groups can be played before exiting. Allow
        # them to be reset back to normal.

        if self._dialog_state == DialogState.GROUP_QUOTA_REACHED:
            self._dialog_state = dialog_state

        # if dialog_state > self._dialog_state:
        #     self._dialog_state = dialog_state
        self._wait_event.set(ReasonEvent.RUN_STATE_CHANGE)

    def exit_screensaver_to_play_movie(self) -> None:
        """

        :return:
        """
        clz = type(self)

        self.set_random_trailers_play_state(DialogState.SHUTDOWN_CUSTOM_PLAYER)

        black_background = BlackBackground.get_instance()
        if black_background is not None:
            black_background.set_visibility(opaque=True)
            black_background.close()
            del black_background
            black_background = None

        self.exiting_playing_movie = True
        self.close()
        xbmc.executebuiltin('Action(FullScreen,12005)')

    def on_abort_event(self) -> None:
        """

        :return:
        """
        clz = type(self)

        clz.logger.enter()
        # Only do this for abort, since both events should not be set at same time
        TrailerLifeCycle.cancel_movie_timer(usage='aborting')  # Unblock waits
        TrailerLifeCycle.clear_notification()
        self.set_random_trailers_play_state(DialogState.SHUTDOWN)
        self._wait_event.set(ReasonEvent.SHUTDOWN)

    def play_next_trailer(self) -> None:
        """

        :return:
        """
        clz = type(self)
        clz.logger.enter()

        # If idle due to wait between movie groups, then interrupt
        # and play next movie.

        if self.is_random_trailers_play_state(DialogState.GROUP_QUOTA_REACHED,
                                              exact_match=True):
            # Wake up wait in between groups
            self.set_random_trailers_play_state(DialogState.NORMAL)

        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz.logger.debug_extra_verbose(f'About to play next trailer: will '
                                           f'hide_detail and stop player')
        self.hide_detail_info()
        if self.get_player() is not None:
            self.get_player().stop()
        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz.logger.debug_extra_verbose('Finished playing movie',
                                           trace=Trace.TRACE_SCREENSAVER)

    def getFocus(self) -> None:
        """

        :return:
        """
        clz = type(self)
        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.debug('Do not use.')
        return

    def onAction(self, action: xbmcgui.Action) -> None:
        """

        :param action:
        :return:

            SHOW_INFO -> Toggle Display custom InfoDialog

            STOP -> Skip to next movie
            ACTION_MOVE_RIGHT -> Skip to next movie

            ACTION_MOVE_LEFT -> Play previous movie

            PREVIOUS_MENU | NAV_BACK | ACTION_BUILT_IN_FUNCTION ->
                                                 Exit Random Trailer script
                or stop Screensaver

            PAUSE -> Toggle Play/Pause playing movie
            PLAY -> Toggle Play/Pause playing movie

            ENTER -> Play movie for current movie (if available)

            REMOTE_0 .. REMOTE_9 -> Record playing movie info to
                        userdata/addon_data/script.video.randomtrailers/<playlist<n>

            ACTION_QUEUE_ITEM -> Add movie to Couch Potato
        """
        clz = type(self)
        action_id: int = action.getId()
        key: str = 'key not set'  # Debug use only

        # Grab handle to movie, it might go away.

        movie: AbstractMovie = self._movie
        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            if action.getId() != 107:  # Mouse Move
                clz.logger.debug_extra_verbose('Action.id:', action.getId(),
                                               hex(action.getId()),
                                               'Action.button_code:',
                                               action.getButtonCode(),
                                               hex(action.getButtonCode()),
                                               trace=Trace.TRACE)

                action_mapper: Action = Action.get_instance()
                matches: List[str] = action_mapper.getKeyIDInfo(action)

                # Mouse Move
                if action_id != 107:
                    for line in matches:
                        clz.logger.debug_extra_verbose(line)

                button_code: int = action.getButtonCode()

                # These return empty string if not found
                action_key: str = action_mapper.getActionIDInfo(action)
                remote_button: str = action_mapper.getRemoteKeyButtonInfo(action)
                remote_key_id: str = action_mapper.getRemoteKeyIDInfo(action)

                # Returns found button_code, or 'key_' +  action_button
                action_button = action_mapper.getButtonCodeId(action)

                separator: str = ''
                key: str = ''
                if action_key != '':
                    key = action_key
                    separator = ', '
                if remote_button != '':
                    key = key + separator + remote_button
                    separator = ', '
                if remote_key_id != '':
                    key = key + separator + remote_key_id
                if key == '':
                    key = action_button
                clz.logger.debug_extra_verbose('Key found:', key)

        #################################################################
        #   ACTIONS
        ##################################################################
        #    DEBUG thread dump
        #################################################################

        if (clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)
                and (action_id == xbmcgui.ACTION_PAGE_UP
                     or action_id == xbmcgui.ACTION_MOVE_UP)):

            from common.debug_utils import Debug
            Debug.dump_all_threads()

        ################################################################
        #
        #  SHOW_INFO
        ################################################################

        if action_id == xbmcgui.ACTION_SHOW_INFO:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose(key, 'Toggle Show_Info',
                                               trace=Trace.TRACE_UI_CONTROLLER)

            if not self.is_random_trailers_play_state(DialogState.NORMAL):
                message = Messages.get_msg(Messages.PLAYER_IDLE)
                TrailerLifeCycle.notification(message)
            elif self.getControl(TrailerDialog.DETAIL_GROUP_CONTROL).isVisible():
                clz.logger.debug('DETAIL_GROUP_CONTROL is visible',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                self.hide_detail_info()
                clz.logger.debug(f'back from hide_detail_view',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                TrailerStatus.set_show_trailer()
                self.get_player().resume_play()
                clz.logger.debug('back from resume_play',
                                 trace=Trace.TRACE_UI_CONTROLLER)
            else:
                # TODO: WRONG! Don't block thread
                # This will block until user action (SHOW_INFO, RIGHT, LEFT, ENTER,
                # etc.)
                clz.logger.debug(f'calling show_detailed_info',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                self.show_detailed_info(from_user_request=True)

        ##################################################################
        elif (action_id == xbmcgui.ACTION_STOP
              or action_id == xbmcgui.ACTION_MOVE_RIGHT):
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose(
                    key, 'Play next trailer at user\'s request',
                    trace=Trace.TRACE_UI_CONTROLLER)
            TrailerLifeCycle.clear_notification()
            self._movie_manager.play_next_trailer()
            self.set_random_trailers_play_state(
                DialogState.SKIP_PLAYING_TRAILER)
            self.play_next_trailer()

        ##################################################################

        elif action_id == xbmcgui.ACTION_MOVE_LEFT:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose(key,
                                               'Play previous trailer at user\'s request',
                                               trace=Trace.TRACE_UI_CONTROLLER)
            if not HistoryList.has_previous_trailer():
                msg = Messages.get_msg(
                    Messages.NO_MORE_MOVIE_HISTORY)
                TrailerLifeCycle.notification(msg, block=True)
            else:
                TrailerLifeCycle.clear_notification()
                self._movie_manager.play_previous_trailer()
                self.set_random_trailers_play_state(
                    DialogState.SKIP_PLAYING_TRAILER)
                self.play_next_trailer()

        ##################################################################
        #
        # PAUSE/PLAY is handled by native player, however, if Movie Details
        # showing due to SHOW_INFO, then switch back to player view
        #
        elif action_id == xbmcgui.ACTION_PAUSE:
            if self.getControl(TrailerDialog.DETAIL_GROUP_CONTROL).isVisible():
                clz.logger.debug('DETAIL_GROUP_CONTROL is visible',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                self.hide_detail_info()
                clz.logger.debug(f'back from hide_detail_view',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                TrailerStatus.set_show_trailer()

        #################################################################
        #
        # QUEUE to Couch Potato
        #
        elif action_id == xbmcgui.ACTION_QUEUE_ITEM:
            if Utils.is_couch_potato_installed() and movie is not None:
                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose(
                        key, 'Queue to couch potato',
                        trace=Trace.TRACE_UI_CONTROLLER)
                str_couch_potato = Constants.COUCH_POTATO_URL + \
                                        f'?title={movie.get_title()}'
                xbmc.executebuiltin('RunPlugin({str_couch_potato})')

        ##################################################################
        elif (action_id == xbmcgui.ACTION_PREVIOUS_MENU
              or action_id == xbmcgui.ACTION_NAV_BACK):
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose('Exit application',
                                               trace=Trace.TRACE_SCREENSAVER)
                clz.logger.debug_extra_verbose(
                    key, 'Exiting RandomTrailers at user request')

            # Ensure we are not blocked

            self.hide_detail_info()
            self.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)
        ##################################################################

        # TODO: Need proper handling of this (and other inputs that we don't
        # handle). Sigh

        elif action_id == xbmcgui.ACTION_BUILT_IN_FUNCTION:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz.logger.debug_verbose(key, 'Exiting RandomTrailers due to',
                                         'ACTION_BUILT_IN_FUNCTION',
                                         trace=Trace.TRACE_SCREENSAVER)

            # Ensure we are not blocked

            self.hide_detail_info()
            self.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)

        ##################################################################
        elif (action_id == xbmcgui.ACTION_ENTER
              or action_id == xbmcgui.ACTION_SELECT_ITEM
              or action_id == xbmcgui.ACTION_SHOW_GUI) and movie is not None:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose(key, 'Play Movie')
            movie_file = movie.get_movie_path()
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose(
                    'Playing movie for currently playing trailer.',
                    'movie_file:', movie_file, 'source:',
                    self._movie.get_source())
            if movie_file == '':
                message = Messages.get_msg(Messages.NO_MOVIE_TO_PLAY)
                TrailerLifeCycle.notification(message)
            elif not self.is_random_trailers_play_state(DialogState.NORMAL):
                message = Messages.get_msg(Messages.PLAYER_IDLE)
                TrailerLifeCycle.notification(message)
            else:
                self.queue_movie(movie)

        ##################################################################
        # From IR remote as well as keyboard
        # Close InfoDialog and resume playing movie

        elif action_id in TrailerDialog._playlist_map and movie is not None:
            movie_path: str = movie.get_movie_path()
            if movie_path == '' or not os.path.exists(movie_path):
                message = Messages.get_msg(Messages.NO_MOVIE_TO_PLAY)
                TrailerLifeCycle.notification(message)
            else:
                if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz.logger.debug_extra_verbose(key)
                self.add_to_playlist(action_id, movie)

    def set_playing_trailer_title_control(self, text: str = '') -> None:
        """

        :param text:
        :return:
        """
        clz = type(self)

        title_control: xbmcgui.ControlLabel = self.getControl(38021)
        clz.logger.debug(f'Setting title of playing trailer to: {text}')
        if text != '':
            title_control.setLabel(text)
        return

    def update_notification_labels(self, text: str = None) -> None:
        """

        :param text:
        :return:
        """
        clz = type(self)

        notification_control: Union[Control,
                                    ControlLabel] = self.getControl(38023)
        notification_control_2: Union[Control,
                                      ControlLabel] = self.getControl(38024)

        if text == '':
            text = ""
        bold_text = self.bold(text)
        notification_control.setLabel(bold_text)
        notification_control_2.setLabel(bold_text)
        text_to_speech.say_text(text, interrupt=True)
        return

    def add_to_playlist(self, action_id: int, movie: AbstractMovie) -> None:
        """

        :param action_id:
        :param movie:
        :return:
        """
        clz = type(self)
        playlist_number = TrailerDialog._playlist_map[action_id]
        playlist_name = Settings.get_playlist_name(playlist_number)
        if playlist_name is None or playlist_name == '':
            clz.logger.error(
                'Invalid playlistId, ignoring request to write to playlist.')
        else:
            added = Playlist.get_playlist(playlist_name, playlist_format=True).\
                add_to_smart_playlist(movie)
            if added:
                TrailerLifeCycle.notification(Messages.get_formatted_msg(
                    Messages.MOVIE_ADDED_TO_PLAYLIST, playlist_name))
            else:
                TrailerLifeCycle.notification(Messages.get_formatted_msg(
                    Messages.MOVIE_ALREADY_ON_PLAYLIST, playlist_name))

    def queue_movie(self, movie: AbstractMovie) -> None:
        """
            At user request, queue movie to be played after canceling play
            of current movie, closing curtain and closing customer Player.

        :param movie:
        :return:
        """
        clz = type(self)

        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz.logger.debug_extra_verbose('Queuing movie at user request:',
                                           movie.get_title())
        self._queued_movie = movie
        self.set_random_trailers_play_state(DialogState.START_MOVIE_AND_EXIT)

        # Unblock Detail Info display

        self.hide_detail_info()

    def play_movie(self, movie: AbstractMovie, already_playing: bool = False) -> None:
        """
            At user request, start playing movie on normal xbmc.player, after
            disabling the custom player that we use here.

            When already-playing is True, then the user has externally (JSON-RPC)
            started a movie and we just need to get out of the way.

        :param movie:
        :param already_playing: True when movie externally started and we need
                                to get the heck out of the way
        :return:
        """
        clz = type(self)

        black_background: BlackBackground = BlackBackground.get_instance()
        black_background.set_visibility(opaque=False)
        black_background.close()
        black_background.destroy()
        del black_background

        if not already_playing:
            movie_file = movie.get_movie_path()
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose('Playing movie at user request:',
                                               movie.get_title(),
                                               'path:', movie_file)

            self.set_random_trailers_play_state(
                DialogState.SHUTDOWN_CUSTOM_PLAYER)
            xbmc.Player().play(movie_file)

        if Monitor.is_abort_requested():
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz.logger.debug_extra_verbose(
                    'ABORT requested before playing movie!')
        while not Monitor.wait_for_abort(timeout=0.10):
            # Call xbmc.Player directly to avoid using DummyPlayer
            if xbmc.Player().isPlayingVideo():
                break

        self.set_random_trailers_play_state(DialogState.STARTED_PLAYING_MOVIE)

        # Time to exit plugin
        Monitor.abort_requested()
        clz.logger.exit('Just started player')

    def get_title_string(self, movie: AbstractMovie, verbose: bool = False) -> str:
        """

        :param movie:
        :param verbose:
        :return:
        """
        clz = type(self)
        title = ''
        if movie is None:
            return ''
        try:
            title = movie.get_detail_title()
            if title is None:
                title = movie.get_title()
                clz.logger.error('Missing DETAIL_TITLE:',
                                 Debug.dump_dictionary(movie.get_as_movie_type()))
            if verbose:  # for debugging
                cached = False
                normalized = False
                if movie.has_normalized_trailer():
                    normalized = True
                elif movie.has_cached_trailer():
                    cached = True

                if normalized:
                    title = title + ' Normalized'
                elif cached:
                    title = title + ' Cached'
                else:
                    pass

        except Exception as e:
            clz.logger.exception('')

        return self.bold(title)

    def bold(self, text: str) -> str:
        """

        :return:
        """
        return '[B]' + text + '[/B]'

    def shutdown(self) -> None:
        """
            Orderly stop execution of TrailerDialog.

            Note that this method can be called voluntarily, when the plugin
            decides to exit, as in the case of the configured number of trailers
            has played. OR, can be called by Monitor detecting an
            abort, in which case the shutdown still needs to be orderly, but
            since there are frequent checks for Monitor abort, the
            shutdown is less orderly, since the code is sprinkled with checks.
            In such case, some parts of the plugin can be shutting down already.

        :return:
        """
        clz = type(self)

        clz.logger.enter()
        TrailerLifeCycle.clear_notification()
        self.close()
        delete_player = False
        try:
            # if self.is_random_trailers_play_state() >=
            # DialogState.STARTED_PLAYING_MOVIE:
            delete_player = True

        except AbortException:
            delete_player = True
        finally:
            self._player_container.use_dummy_player(delete_player)

        self._title_control = None
        self._source = None
        self._movie = None
        self._viewed_playlist = None
