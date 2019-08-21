# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: Frank Feuerbacher
'''
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import datetime
import sys
import threading
import six

from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import (Logger, LazyLogger, Trace, log_entry_exit)
from common.messages import Messages
from common.monitor import Monitor
from common.utils import Utils
from action_map import Action
from common.settings import Settings
from player.player_container import PlayerContainer
from frontend.black_background import BlackBackground
from frontend.movie_manager import MovieManager, MovieStatus
from frontend.history_empty import HistoryEmpty

from frontend.utils import ReasonEvent, BaseWindow, ScreensaverState
from kodi_six import xbmc, xbmcgui

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger(
    ).getChild('frontend.trailer_dialog')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class DialogState:
    """

    """
    NORMAL = int(0)
    SKIP_PLAYING_TRAILER = int(1)
    GROUP_QUOTA_REACHED = int(2)
    QUOTA_REACHED = int(3)
    NO_TRAILERS_TO_PLAY = int(4)
    USER_REQUESTED_EXIT = int(5)
    START_MOVIE_AND_EXIT = int(6)
    SHUTDOWN_CUSTOM_PLAYER = int(7)
    STARTED_PLAYING_MOVIE = int(8)
    SHUTDOWN = int(9)

    label_map = {NORMAL: 'NORMAL',
                 SKIP_PLAYING_TRAILER: 'SKIP_PLAYING_TRAILER',
                 GROUP_QUOTA_REACHED: 'GROUP_QUOTA_REACHED',
                 QUOTA_REACHED: 'QUOTA_REACHED',
                 NO_TRAILERS_TO_PLAY: 'NO_TRAILERS_TO_PLAY',
                 USER_REQUESTED_EXIT: 'USER_REQUESTED_EXIT',
                 START_MOVIE_AND_EXIT: 'START_MOVIE_AND_EXIT',
                 SHUTDOWN_CUSTOM_PLAYER: 'SHUTDOWN_CUSTOM_PLAYER',
                 STARTED_PLAYING_MOVIE: 'STARTED_PLAYING_MOVIE',
                 SHUTDOWN: 'SHUTDOWN'}

    @staticmethod
    def getLabel(dialogState):
        return DialogState.label_map[dialogState]


# noinspection Annotator
class TrailerDialog(xbmcgui.WindowXMLDialog):
    '''
        Note that the underlying 'script-trailer-window.xml' has a "videowindow"
        control. This causes the player to ignore many of the normal keymap actions.
    '''
    DETAIL_GROUP_CONTROL = 38001

    DUMMY_TRAILER = {
        Movie.TITLE: '',
        Movie.THUMBNAIL: '',
        Movie.FANART: '',
        Movie.DETAIL_DIRECTORS: '',
        Movie.DETAIL_ACTORS: '',
        Movie.PLOT: '',
        Movie.DETAIL_STUDIOS: ''
    }

    def __init__(self, *args, **kwargs):
        # type: (*Any, **Dict[TextType, TextType]) -> None
        super().__init__(*args)
        self._logger = module_logger.getChild(self.__class__.__name__)
        self._logger.enter()
        self._dialog_state = DialogState.NORMAL
        self._player_container = PlayerContainer.get_instance()
        self._player_container.register_exit_on_movie_playing(
            self.exit_screensaver_to_play_movie)

        self.get_player().setCallBacks(on_show_info=self.show_detailed_info)
        self._title_control = None
        self._source = None
        self._trailer = None
        self._lock = threading.RLock()
        self._long_trailer_killer = None
        self._messages = Messages.get_instance()
        self._viewed_playlist = Playlist.get_playlist(
            Playlist.VIEWED_PLAYLIST_FILE)
        self._viewed_playlist.add_timestamp()
        self._title_control = None
        self._notification_control = None
        self._notification_timeout = 0.0
        self._notification_killer = None
        self._thread = None
        self._wait_or_interrupt_event = threading.Event()

        # Used mostly as a timer
        self._show_details_event = threading.Event()
        self._wait_event = ReasonEvent()
        self._ready_to_exit_event = threading.Event()
        monitor = Monitor.get_instance()
        monitor.register_shutdown_listener(self.on_shutdown_event)

        self._saved_brief_info_visibility = False
        self._movie_manager = MovieManager()
        self._queued_movie = None
        self._get_next_trailer_start = None
        self.trailers_per_iteration = None
        self.group_trailers = None
        self.total_trailers_to_play = None
        self.delay_between_groups = None
        self.exiting_playing_movie = False

        #
        # Prevent flash of grid
        #
        self.set_visibility(video_window=False, info=False, brief_info=False,
                            notification=False, information=False)

    def onInit(self):
        self._logger.enter()

        # Prevent flash of grid
        #
        self.set_visibility(video_window=False, info=False, brief_info=False,
                            notification=False, information=False)
        if self._thread is None:
            self._thread = threading.Thread(
                target=self.play_trailers, name='TrailerDialog')
            self._thread.start()

    def configure_trailer_play_parameters(self):
        total_trailers_to_play = Settings.get_number_of_trailers_to_play()

        trailers_per_group = total_trailers_to_play
        group_trailers = Settings.is_group_trailers()

        if group_trailers:
            trailers_per_group = Settings.get_trailers_per_group()

        trailers_per_iteration = total_trailers_to_play
        if trailers_per_group > 0:
            trailers_per_iteration = trailers_per_group
            if total_trailers_to_play > 0:
                trailers_per_iteration = min(
                    trailers_per_iteration, total_trailers_to_play)
        else:
            trailers_per_iteration = total_trailers_to_play

        delay_between_groups = Settings.get_group_delay()

        self.trailers_per_iteration = trailers_per_iteration
        self.group_trailers = group_trailers
        self.total_trailers_to_play = total_trailers_to_play
        self.delay_between_groups = delay_between_groups

    def play_trailers(self):
        self.configure_trailer_play_parameters()
        trailers_played = 0
        trailers_to_play_on_next_iteration = self.trailers_per_iteration
        try:
            while not self.is_random_trailers_play_state():
                self.play_a_group_of_trailers()

                if self.is_random_trailers_play_state(DialogState.NO_TRAILERS_TO_PLAY):
                    break

                self._player_container.get_player().wait_for_is_not_playing_video()

                # Pre-seed all fields with empty values so that if display of
                # detailed movie information occurs prior to download of external
                # images, etc. This way default values are shown instead of
                # leftovers from previous movie.

                self._trailer = TrailerDialog.DUMMY_TRAILER
                self.update_detail_view()  # Does not display

                if self.group_trailers:
                    if self.total_trailers_to_play > 0:
                        trailers_played += self.trailers_per_iteration
                        remaining_to_play = self.total_trailers_to_play - trailers_played
                        if remaining_to_play <= 0:
                            break

                        if remaining_to_play < self.trailers_per_iteration:
                            trailers_to_play_on_next_iteration = remaining_to_play

                    self._wait_event.wait(self.delay_between_groups)
                    if self.is_random_trailers_play_state(DialogState.USER_REQUESTED_EXIT):
                        break
                    if self.is_random_trailers_play_state(DialogState.NORMAL):
                        # Wake up and resume playing trailers early
                        pass
                    self.set_random_trailers_play_state(DialogState.NORMAL)

                elif self.is_random_trailers_play_state(DialogState.QUOTA_REACHED):
                    break

        except (AbortException, ShutdownException):
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Received shutdown or abort')

        except (Exception) as e:
            self._logger.exception('')
        finally:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('About to close TrailerDialog')

            self.cancel_long_playing_trailer_killer()
            # self._logger.debug('Stopped xbmc.Player')

            self._viewed_playlist.close()
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Closed TrailerDialog')
            self.shutdown()
            return  # Exit thread

    def play_a_group_of_trailers(self):
        self.set_visibility(video_window=False, info=False, brief_info=False,
                            notification=False, information=False)
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(' WindowID: ' +
                               str(xbmcgui.getCurrentWindowId()))

        _1080P = 0X0  # 1920 X 1080
        _720p = 0X1  # 1280 X 720
        window_height = self.getHeight()
        window_width = self.getWidth()
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('Window Dimensions: ' + str(window_height) +
                               ' H  x ' + str(window_width) + ' W')

        # self.show()
        number_of_trailers_played = 0
        try:
            # Main trailer playing loop

            if Settings.get_show_curtains():
                self._movie_manager.play_curtain_next(
                    MovieManager.OPEN_CURTAIN)

            while not self.is_random_trailers_play_state():
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('top of loop')
                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    self._dialog_state = DialogState.NORMAL

                # Blank the screen

                self.set_visibility(video_window=False, info=False, brief_info=False,
                                    notification=False, information=False)

                # Get the video (or curtain) to display
                try:
                    self._get_next_trailer_start = datetime.datetime.now()
                    status, self._trailer = self._movie_manager.get_next_trailer()
                    # if status == MovieStatus.PREVIOUS_MOVIE:
                    #     msg = self._messages.get_msg(
                    #         Messages.PLAYING_PREVIOUS_MOVIE)
                    #     msg = msg % self._trailer[Movie.TITLE]
                    #     self.notification(msg)
                except (HistoryEmpty):
                    msg = self._messages.get_msg(
                        Messages.NO_MORE_MOVIE_HISTORY)
                    self.notification(msg)
                    continue

                # Are there no trailers to play now, and in the future?

                if status == MovieStatus.OK and self._trailer is None:
                    self.set_random_trailers_play_state(
                        DialogState.NO_TRAILERS_TO_PLAY)
                    break

                elif status == MovieStatus.IDLE:
                    self.set_random_trailers_play_state(
                        DialogState.NO_TRAILERS_TO_PLAY)
                    self._logger.error('Should not get state IDLE')
                    break

                # TODO: User feedback instead of blank screen?

                if status == MovieStatus.TIMED_OUT:
                    continue

                if status == MovieStatus.BUSY:
                    continue

                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    continue

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('got trailer to play: ' +
                                       self._trailer.get(Movie.TRAILER))

                video_is_curtain = (self._trailer[Movie.SOURCE] == 'curtain')

                # TODO: fix comment
                # Screen will be black since both
                # TrailerDialog.PLAYER_GROUP_CONTROL and
                # TrailerDialog.DETAIL_GROUP_CONTROL are, by default,
                # not visible in script-trailerwindow.xml
                # self.show()

                # Wait until previous video is complete.
                # Our event listeners will stop the player, as appropriate.

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('wait for not playing 1')
                self.get_player().wait_for_is_not_playing_video()

                # Determine if Movie Information is displayed prior to trailer

                self._source = self._trailer.get(Movie.SOURCE)
                show_movie_details = (
                    Settings.get_time_to_display_detail_info() > 0)

                # Determine if Movie Title is to be displayed during play of
                # trailer

                show_trailer_title = Settings.get_show_movie_title()

                # Add trailer to "playlist"

                if not video_is_curtain:
                    self._viewed_playlist.record_played_trailer(self._trailer)

                # Trailers from a folder are ill-structured and have no
                # identifying information.

                if self._source == Movie.FOLDER_SOURCE:
                    show_movie_details = False

                if video_is_curtain:
                    show_movie_details = False
                    show_trailer_title = False

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('checking play_state 1')
                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    continue
                if self.is_random_trailers_play_state():
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('breaking due to play_state 1 movie:',
                                           self._trailer[Movie.TITLE])
                    break

                # This will block if showing Movie Details
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('about to show_movie_info movie:',
                                       self._trailer[Movie.TITLE])
                self.show_movie_info(show_detail_info=show_movie_details,
                                     show_brief_info=show_trailer_title)
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('finished show_movie_info, movie:',
                                       self._trailer[Movie.TITLE])

                # Play Trailer

                # TODO: change to asynchronous so that it can occur while
                # showing details

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('checking play_state 2 movie:',
                                       self._trailer[Movie.TITLE])
                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    continue
                if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('breaking due to play_state 2 movie:',
                                           self._trailer[Movie.TITLE])
                    break

                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('About to play:',
                                       self._trailer.get(Movie.TRAILER))

                self.set_visibility(video_window=True, info=False,
                                    brief_info=show_trailer_title,
                                    notification=False,
                                    information=show_trailer_title)
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('about to play movie:',
                                       self._trailer[Movie.TITLE])
                normalized = False
                cached = False
                trailer_path = None
                if self._trailer.get(Movie.NORMALIZED_TRAILER) is not None:
                    trailer_path = self._trailer[Movie.NORMALIZED_TRAILER]
                    self.get_player().play_trailer(trailer_path, self._trailer)
                    normalized = True
                elif self._trailer.get(Movie.CACHED_TRAILER) is not None:
                    trailer_path = self._trailer[Movie.CACHED_TRAILER]
                    self.get_player().play_trailer(trailer_path, self._trailer)
                    cached = True
                else:
                    trailer_path = self._trailer[Movie.TRAILER]
                    self.get_player().play_trailer(trailer_path, self._trailer)

                time_to_play_trailer = datetime.datetime.now() - self._get_next_trailer_start
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('started play_trailer:',
                                       self._trailer[Movie.TITLE],
                                       'elapsed seconds:',
                                       time_to_play_trailer.total_seconds(),
                                       'source:', self._trailer[Movie.SOURCE],
                                       'normalized:', normalized,
                                       'cached:', cached,
                                       'path:', trailer_path)

                # Again, we rely on our listeners to interrupt, as
                # appropriate. Trailer/Movie should be about to be played or
                # playing.

                try:
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('checking play_state 3 movie:',
                                           self._trailer[Movie.TITLE])
                    if self.is_random_trailers_play_state(
                            DialogState.SKIP_PLAYING_TRAILER,
                            exact_match=True):
                        continue
                    if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('breaking at play_state 3 movie:',
                                               self._trailer[Movie.TITLE])
                        break

                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('wait_for_is_playing_video 2 movie:',
                                           self._trailer[Movie.TITLE])
                    if not self.get_player().waitForIsPlayingVideo(timeout=5.0):
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('Timed out Waiting for Player.')

                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('checking play_state 4 movie:',
                                           self._trailer[Movie.TITLE])
                    if self.is_random_trailers_play_state(
                            DialogState.SKIP_PLAYING_TRAILER,
                            exact_match=True):
                        continue
                    if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                        self._logger.debug(
                            'breaking at play_state 4 movie:', self._trailer[Movie.TITLE])
                        break

                    # Now that the trailer has started, see if it will run too long so
                    # that we need to set up to kill it playing.

                    trailer_total_time = self.get_player().getTotalTime()
                    max_play_time = Settings.get_max_trailer_length()
                    if trailer_total_time > max_play_time:
                        if self._logger.isEnabledFor(Logger.DEBUG):
                            self._logger.debug('Killing long trailer:',
                                               self._trailer[Movie.TITLE], 'limit:',
                                               max_play_time)
                        self.start_long_trailer_killer(max_play_time)
                except (AbortException, ShutdownException):
                    raise sys.exc_info()
                except (Exception) as e:
                    self._logger.exception('')

                # Again, we rely on our listeners to  stop the player, as
                # appropriate

                self.get_player().wait_for_is_not_playing_video()
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('checking play_state 5 movie:',
                                       self._trailer[Movie.TITLE])
                if self.is_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER,
                                                      exact_match=True):
                    continue
                if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('breaking at play_state 5 movie:',
                                           self._trailer[Movie.TITLE])
                    break

                self.cancel_long_playing_trailer_killer()

                # Again, we rely on our listeners to  stop this display, as
                # appropriate

                self.set_visibility(video_window=False, info=False, brief_info=False,
                                    notification=False, information=False)
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

            if self._trailer is None:
                self._logger.error('There will be no trailers to play')
                self.notification(self._messages.get_msg(
                    Messages.NO_TRAILERS_TO_PLAY))
                self.set_random_trailers_play_state(
                    DialogState.NO_TRAILERS_TO_PLAY)
            else:
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('out of inner play loop movie:',
                                       self._trailer[Movie.TITLE])

            if Settings.get_show_curtains():
                self._movie_manager.play_curtain_next(
                    MovieManager.CLOSE_CURTAIN)

                _, curtain = self._movie_manager.get_next_trailer()
                self.set_visibility(video_window=True, info=False, brief_info=False,
                                    notification=False, information=False)
                self.get_player().play_trailer(curtain[Movie.TRAILER].encode('utf-8'),
                                               curtain)
                if not self.get_player().waitForIsPlayingVideo(timeout=5.0):
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Timed out Waiting for Player.')
                self.get_player().wait_for_is_not_playing_video()

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(
                    'Completed everything except play_movie, if there is one')
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')

        try:
            if self._trailer is not None:
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Checking to see if there is a movie to play:',
                                       self._trailer[Movie.TITLE])
            if self.is_random_trailers_play_state(DialogState.START_MOVIE_AND_EXIT,
                                                  exact_match=True):
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug(
                        'about to play movie:', self._queued_movie)
                self.set_visibility(video_window=True, info=False, brief_info=False,
                                    notification=False, information=False)
                self.play_movie(self._queued_movie)

        except (AbortException, ShutdownException):
            self._logger.debug('Received shutdown or abort')
        except (Exception) as e:
            self._logger.exception('')

    def get_player(self):
        return self._player_container.get_player()

    def is_random_trailers_play_state(self,
                                      minimum_exit_state=DialogState.GROUP_QUOTA_REACHED,  # type: int
                                      exact_match=False,  # type: bool
                                      throw_exception_on_shutdown=True  # type: bool
                                      ):
        # type: (...) -> bool
        """
            Checks the current state of random trailers plugin against default
            or passed in values.

            Note that a check for a Shutdown/Abort state is performed on each
            call.

            A return value of True indicating whether specified state has been
            reached.

        :param minimum_exit_state: Return True if DialogState is at least this value
        :param exact_match: Only return True if DialogState is exactly this value
        :param throw_exception_on_shutdown: Throw ShutdownException or AbortException
                instead, as appropriate.
        :return:
        """
        match = False
        monitor = Monitor.get_instance()
        if monitor is None or monitor.is_shutdown_requested():
            self._dialog_state = DialogState.SHUTDOWN

        if self._dialog_state == DialogState.SHUTDOWN:
            if throw_exception_on_shutdown and monitor is not None:
                monitor.throw_exception_if_shutdown_requested()
            else:
                match = True
        elif exact_match:
            match = self._dialog_state == minimum_exit_state
        else:
            match = self._dialog_state >= minimum_exit_state
        return match

    def show_movie_info(self, show_detail_info=False, show_brief_info=False):
        # self.setBriefInfoVisibility(False)
        if show_detail_info:
            self.show_detailed_info()
        else:
            self.hide_detail_info()
        #
        # You can have both showMovieDetails (movie details screen
        # shown prior to playing trailer) as well as the
        # simple ShowTrailerTitle while the trailer is playing.
        #
        if show_brief_info:
            title = self.get_title_string(self._trailer)
            self.get_title_control().setLabel(title)

        self.set_visibility(video_window=False, info=show_detail_info,
                            brief_info=show_brief_info,
                            notification=False,
                            information=show_brief_info | show_detail_info)
        pass

    def notification(self, message):
        # TODO: implement

        try:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('message:', message)
            self.get_notification_control(text=message)
            self.set_visibility(notification=True, information=True)
            self.wait_or_interrupt(
                timeout=Constants.MAX_PLAY_TIME_WARNING_TIME)
            self.set_visibility(notification=False)
        except (Exception) as e:
            self._logger.exception('')

        return

    def wait_or_interrupt(self, timeout=0):
        # type: (float) -> None
        """

        :param timeout:
        :return:
        """
        # During shutdown, Monitor deletes itself, so to avoid a silly error in
        # the log, avoid calling it.

        self._wait_or_interrupt_event.clear()
        self._wait_or_interrupt_event.wait(timeout=timeout)
        self._wait_or_interrupt_event.clear()

        return

    @log_entry_exit
    def show_detailed_info(self, from_user_request=False):

        if self._source != Movie.FOLDER_SOURCE:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('about to show_detailed_info')
            display_seconds = Settings.get_time_to_display_detail_info()
            if from_user_request:
                display_seconds = 0
            else:
                if self.get_player() is not None:
                    self.get_player().pausePlay()

            self.update_detail_view()
            self.show_detail_info(self._trailer, display_seconds)

    def show_detail_info(self, trailer, display_seconds=0):
        self.set_visibility(video_window=False, info=True, brief_info=False,
                            notification=False, information=True)

        if display_seconds == 0:
            # One year
            display_seconds = 365 * 24 * 60 * 60
        self._show_details_event.clear()  # In case it was set
        self._show_details_event.wait(display_seconds)
        self._show_details_event.clear()  # In case it was set
        # self.hide_detail_info()
        self._show_details_event.set()  # Force show_detail_info to unblock
        self.set_visibility(video_window=False, info=False, brief_info=False,
                            notification=False, information=False)
        pass

    def hide_detail_info(self, reason=''):
        self._logger.enter()
        self._show_details_event.set()  # Force show_detail_info to unblock
        self.set_visibility(info=False, information=False)

    def set_visibility(self,
                       video_window=None,  # type: Union[bool, None]
                       info=None,  # type: Union[bool, None]
                       brief_info=None,  # type: Union[bool, None]
                       notification=None,  # type: Union[bool, None]
                       information=None  # type: Union[bool, None]
                       ):
        # type: (...) -> None
        """
            Controls the visible elements of TrailerDialog

        :param video_window:
        :param info:
        :param brief_info:
        :param notification:
        :param information:
        :return:
        """
        # self.wait_or_exception(timeout=0)
        shutdown = False
        try:
            if self.is_random_trailers_play_state(
                    minimum_exit_state=DialogState.SHUTDOWN_CUSTOM_PLAYER):
                shutdown = True
        except (AbortException, ShutdownException):
            shutdown = True

        if shutdown:
            video_window = True
            info = False
            brief_info = False
            notification = False
            information = False

        commands = []

        nested_controls = [info, brief_info, notification]
        if True in nested_controls:
            # If any of the textual information controls change visibility, then
            # black out before
            # changes within the control are changed and then make visible
            # again at the end, if requested.

            info_command = "Skin.Reset(NonVideo)"
            commands.append(info_command)

        if video_window is not None:
            if video_window:
                video_command = "Skin.SetBool(Video)"
            else:
                video_command = "Skin.Reset(Video)"
            commands.append(video_command)
        if info is not None:
            title = None
            if info:
                title = self.getControl(38003)
                info_command = "Skin.SetBool(Info)"
            else:
                info_command = "Skin.Reset(Info)"
            commands.append(info_command)

        if brief_info is not None:
            title = None
            if brief_info:
                title = self.getControl(38021)
                info_command = "Skin.SetBool(SummaryLabel)"
            else:
                info_command = "Skin.Reset(SummaryLabel)"
            commands.append(info_command)

        if notification is not None:
            if notification:
                info_command = "Skin.SetBool(Notification)"
            else:
                info_command = "Skin.Reset(Notification)"
            commands.append(info_command)

        # The disable case was taken care of above. Handle enable here after
        # everything contained within the group is set

        if information is not None:
            if information:
                info_command = "Skin.SetBool(NonVideo)"
            else:
                info_command = "Skin.Reset(NonVideo)"
            commands.append(info_command)

        for command in commands:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(command)
            xbmc.executebuiltin(command)

    def update_detail_view(self):
        try:
            Monitor.get_instance().throw_exception_if_shutdown_requested()

            self._logger.enter()

            control = self.getControl(38002)  # type: xbmcgui.ControlImage
            thumbnail = self._trailer[Movie.THUMBNAIL]
            control.setImage(thumbnail)

            self.getControl(38004).setImage(self._trailer[Movie.FANART])

            title_string = self.get_title_string(self._trailer)

            title = self.getControl(38003)
            title.setLabel(title_string)

            # title.setAnimations(
            #    [('Hidden', 'effect=fade end=0 time=1000')])

            movie_directors = self._trailer[Movie.DETAIL_DIRECTORS]
            self.getControl(38005).setLabel(movie_directors)

            movie_actors = self._trailer[Movie.DETAIL_ACTORS]
            self.getControl(38006).setLabel(movie_actors)

            movie_writers = self._trailer[Movie.DETAIL_WRITERS]
            self.getControl(38007).setLabel(movie_writers)

            plot = self._trailer[Movie.PLOT]
            self.getControl(38009).setText(plot)

            movie_studios = self._trailer[Movie.DETAIL_STUDIOS]
            self.getControl(38010).setLabel(movie_studios)

            label = self._messages.get_formatted_msg(Messages.RUNTIME_GENRE,
                                                     self._trailer[Movie.DETAIL_RUNTIME],
                                                     self._trailer[Movie.DETAIL_GENRES])
            self.getControl(38011).setLabel(label)

            image_rating = self._trailer[Movie.DETAIL_RATING_IMAGE]
            self.getControl(38013).setImage(image_rating)

            self._logger.exit()

        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except (Exception) as e:
            self._logger.exception('')
        finally:
            pass

    def doModal(self):
        self._logger.enter()
        super().doModal()
        self._logger.exit()
        return self.exiting_playing_movie

    def show(self):
        super().show()

    def close(self):
        super().close()
        self._ready_to_exit_event.set()

    def set_random_trailers_play_state(self, dialog_state):
        # type: (int) -> None
        # TODO: Change to use named int type
        """

        :param dialog_state:
        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('state:', DialogState.getLabel(dialog_state),
                               trace=Trace.TRACE_SCREENSAVER)

        if dialog_state >= DialogState.SHUTDOWN_CUSTOM_PLAYER:
            self.get_player().setCallBacks(on_show_info=None)
            self.get_player().disableAdvancedMonitoring()
            self._player_container.use_dummy_player()
            self.set_visibility(video_window=False, info=False,
                                brief_info=False, notification=False)

        if dialog_state >= DialogState.USER_REQUESTED_EXIT:
            # Stop playing trailer.

            # Just in case we are paused
            self.get_player().resumePlay()
            self.kill_long_playing_trailer(inform_user=False)

        # Multiple groups can be played before exiting. Allow
        # them to be reset back to normal.

        if self._dialog_state == DialogState.GROUP_QUOTA_REACHED:
            self._dialog_state = dialog_state

        if dialog_state > self._dialog_state:
            self._dialog_state = dialog_state
        self._wait_event.set(ReasonEvent.RUN_STATE_CHANGE)

    def exit_screensaver_to_play_movie(self):
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

    def on_shutdown_event(self):
        # type: () -> None
        """

        :return:
        """
        self._logger.enter()
        self.set_random_trailers_play_state(DialogState.SHUTDOWN)
        self._wait_event.set(ReasonEvent.SHUTDOWN)

       # TODO: put this in own class

    def start_long_trailer_killer(self, max_play_time):
        # type: (Union[int, float]) -> None
        """

        :param max_play_time:
        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('waiting on lock',
                               trace=Trace.TRACE_UI_CONTROLLER)
        with self._lock:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('got lock, max_play_time:',
                                   max_play_time,
                                   trace=Trace.TRACE_UI_CONTROLLER)
            self._long_trailer_killer = None
            if not self.is_random_trailers_play_state(DialogState.USER_REQUESTED_EXIT):
                if max_play_time > Constants.MAX_PLAY_TIME_WARNING_TIME + 2:
                    max_play_time -= Constants.MAX_PLAY_TIME_WARNING_TIME
                    self._logger.debug('adjusted max_play_time:', max_play_time,
                                       trace=Trace.TRACE_UI_CONTROLLER)
                self._long_trailer_killer = threading.Timer(max_play_time,
                                                            self.kill_long_playing_trailer)
                self._long_trailer_killer.setName('TrailerKiller')
                self._long_trailer_killer.start()

    def kill_long_playing_trailer(self, inform_user=True):
        # type: (bool) -> None
        """

        :param inform_user:
        :return:
        """
        try:
            self._logger.enter()
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Now Killing',
                                   trace=Trace.TRACE_UI_CONTROLLER)

            if inform_user:
                self.notification(self._messages.get_msg(
                    Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME))

            self.get_player().stop()

            with self._lock:
                self._long_trailer_killer = None
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except (Exception) as e:
            self._logger.exception(msg='')

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('exit', trace=Trace.TRACE_SCREENSAVER)

    def cancel_long_playing_trailer_killer(self):
        # type: () -> None
        """

        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('enter, waiting on lock',
                               trace=[Trace.TRACE_SCREENSAVER,
                                      Trace.TRACE_UI_CONTROLLER])
        with self._lock:
            if self._long_trailer_killer is not None:
                self._long_trailer_killer.cancel()

    def play_next_trailer(self):
        # type: () -> None
        """

        :return:
        """
        self._logger.enter()

        # If idle due to wait between trailer groups, then interrupt
        # and play next trailer.

        if self.is_random_trailers_play_state(DialogState.GROUP_QUOTA_REACHED,
                                              exact_match=True):
            # Wake up wait in between groups
            self.set_random_trailers_play_state(DialogState.NORMAL)

        self.cancel_long_playing_trailer_killer()
        self.hide_detail_info()
        if self.get_player() is not None:
            self.get_player().stop()
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('Finished playing old trailer',
                               trace=Trace.TRACE_SCREENSAVER)

    def getFocus(self):
        # type: () -> None
        """

        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('Do not use.')
        return

    def onAction(self, action):
        # type: (Action) -> None
        """

        :param action:
        :return:

            SHOW_INFO -> Toggle Display custom InfoDialog

            STOP -> Skip to next trailer
            ACTION_MOVE_RIGHT -> Skip to next trailer

            ACTION_MOVE_LEFT -> Play previous trailer

            PREVIOUS_MENU | NAV_BACK | ACTION_BUILT_IN_FUNCTION -> Exit Random Trailer script
                or stop Screensaver

            PAUSE -> Toggle Play/Pause playing trailer
            PLAY -> Toggle Play/Pause playing trailer

            ENTER -> Play movie for current trailer (if available)

            REMOTE_0 .. REMOTE_9 -> Record playing movie info to
                        userdata/addon_data/script.video.randomtrailers/<playlist<n>

            ACTION_QUEUE_ITEM -> Add movie to Couch Potato
        """
        if action.getId() != 107:  # Mouse Move
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Action.id:', action.getId(),
                                   hex(action.getId()),
                                   'Action.button_code:',
                                   action.getButtonCode(),
                                   hex(action.getButtonCode()), trace=Trace.TRACE)

        action_mapper = Action.get_instance()
        matches = action_mapper.getKeyIDInfo(action)

        # Mouse Move
        if action.getId() != 107 and self._logger.isEnabledFor(Logger.DEBUG):
            for line in matches:
                self._logger.debug(line)

        action_id = action.getId()
        button_code = action.getButtonCode()

        # These return empty string if not found
        action_key = action_mapper.getActionIDInfo(action)
        remote_button = action_mapper.getRemoteKeyButtonInfo(action)
        remote_key_id = action_mapper.getRemoteKeyIDInfo(action)

        # Returns found button_code, or 'key_' +  action_button
        action_button = action_mapper.getButtonCodeId(action)

        separator = ''
        key = ''
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
        # Mouse Move
        if action.getId() != 107 and self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('Key found:', key)

        ##################################################################
        if action_id == xbmcgui.ACTION_SHOW_INFO:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(key, 'Toggle Show_Info')

            if not self.is_random_trailers_play_state(DialogState.NORMAL):
                heading = self._messages.get_msg(Messages.HEADER_IDLE)
                message = self._messages.get_msg(Messages.PLAYER_IDLE)
                self.notification(message)
            elif self.getControl(TrailerDialog.DETAIL_GROUP_CONTROL).isVisible():
                self.hide_detail_info()
                self.get_player().resumePlay()
            else:
                self.show_detailed_info(from_user_request=True)

        ##################################################################
        elif (action_id == xbmcgui.ACTION_STOP or action_id == xbmcgui.ACTION_MOVE_RIGHT):
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(key, 'Play next trailer at user\'s request')
            self._wait_or_interrupt_event.set()
            self.set_random_trailers_play_state(
                DialogState.SKIP_PLAYING_TRAILER)
            self.play_next_trailer()

        ##################################################################

        elif action_id == xbmcgui.ACTION_MOVE_LEFT:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(key,
                                   'Play previous trailer at user\'s request')
            self._wait_or_interrupt_event.set()
            self._movie_manager.play_previous_trailer()
            self.set_random_trailers_play_state(
                DialogState.SKIP_PLAYING_TRAILER)
            self.play_next_trailer()

        ##################################################################
        #
        # PAUSE/PLAY is handled by native player
        #
        elif action_id == xbmcgui.ACTION_QUEUE_ITEM:
            if Utils.is_couch_potato_installed():
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug(key, 'Queue to couch potato')
                str_couch_potato = 'plugin://plugin.video.couchpotato_manager/movies/add?title=' + \
                    self._trailer[Movie.TITLE]
                xbmc.executebuiltin('XBMC.RunPlugin(' + str_couch_potato + ')')

        ##################################################################
        elif (action_id == xbmcgui.ACTION_PREVIOUS_MENU
              or action_id == xbmcgui.ACTION_NAV_BACK):
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Exit application',
                                   trace=Trace.TRACE_SCREENSAVER)
                self._logger.debug(
                    key, 'Exiting RandomTrailers at user request')

            # Ensure we are not blocked

            self.hide_detail_info()
            self.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)
        ##################################################################

        # TODO: Need proper handling of this (and other inputs that we don't
        # handle. Sigh

        elif action_id == xbmcgui.ACTION_BUILT_IN_FUNCTION:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('ACTION_BUILT_IN_FUNCTION',
                                   trace=Trace.TRACE_SCREENSAVER)
                self._logger.debug(key, 'Exiting RandomTrailers due to',
                                   'ACTION_BUILT_IN_FUNCTION')

            # Ensure we are not blocked

            self.hide_detail_info()
            self.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)

        ##################################################################
        elif (action_id == xbmcgui.ACTION_ENTER
              or action_id == xbmcgui.ACTION_SELECT_ITEM
              or action_id == xbmcgui.ACTION_SHOW_GUI):
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(key, 'Play Movie')
            movie_file = self._trailer[Movie.FILE]
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Playing movie for currently playing trailer.',
                                   'movie_file:', movie_file, 'source:',
                                   self._trailer[Movie.SOURCE])
            if movie_file is None or movie_file == '':
                heading = self._messages.get_msg(Messages.HEADING_INFO)
                message = self._messages.get_msg(Messages.NO_MOVIE_TO_PLAY)
                self.notification(message)
            elif not self.is_random_trailers_play_state(DialogState.NORMAL):
                heading = self._messages.get_msg(Messages.HEADER_IDLE)
                message = self._messages.get_msg(Messages.PLAYER_IDLE)
                self.notification(message)
            else:
                self.queue_movie(self._trailer)

        ##################################################################
        # From IR remote as well as keyboard
        # Close InfoDialog and resume playing trailer

        elif (action_id == xbmcgui.REMOTE_1 or
              action_id == xbmcgui.REMOTE_2 or
              action_id == xbmcgui.REMOTE_3 or
              action_id == xbmcgui.REMOTE_4 or
              action_id == xbmcgui.REMOTE_5 or
              action_id == xbmcgui.REMOTE_6 or
              action_id == xbmcgui.REMOTE_7 or
              action_id == xbmcgui.REMOTE_8 or
              action_id == xbmcgui.REMOTE_9 or
                action_id == xbmcgui.REMOTE_0):
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug(key)
            self.add_to_playlist(action_id, self._trailer)

    def get_title_control(self, text=''):
        title_control = self.getControl(38021)
        if text != '':
            title_control.setLabel(text)
        return title_control

    def get_notification_control(self, text=None):
        # type: (TextType) -> xbmcgui.ControlLabel
        """

        :param text:
        :return:
        """
        title_control = self.getControl(38023)
        if text != '':
            title_control.setLabel(text)
        return title_control

    _playlist_map = {xbmcgui.REMOTE_1:
                     Playlist.PLAYLIST_PREFIX + '1' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_2:
                     Playlist.PLAYLIST_PREFIX + '2' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_3:
                     Playlist.PLAYLIST_PREFIX + '3' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_4:
                     Playlist.PLAYLIST_PREFIX + '4' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_5:
                     Playlist.PLAYLIST_PREFIX + '5' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_6:
                     Playlist.PLAYLIST_PREFIX + '6' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_7:
                     Playlist.PLAYLIST_PREFIX + '7' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_8:
                     Playlist.PLAYLIST_PREFIX + '8' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_9:
                     Playlist.PLAYLIST_PREFIX + '9' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_0:
                     Playlist.PLAYLIST_PREFIX + '10' + Playlist.PLAYLIST_SUFFIX}

    def add_to_playlist(self, play_list_id, trailer):
        # type: (TextType, dict) -> None
        """

        :param play_list_id:
        :param trailer:
        :return:
        """
        playlist_file = TrailerDialog._playlist_map.get(play_list_id, None)
        if playlist_file is None:
            self._logger.error(
                'Invalid playlistId, ignoring request to write to playlist.')
        else:
            Playlist.get_playlist(playlist_file).record_played_trailer(trailer)

    def queue_movie(self, trailer):
        # type: (Dict[TextType, TextType]) -> None
        """
            At user request, queue movie to be played after canceling play
            of current trailer, closing curtain and closing customer Player.

        :param trailer:
        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('Queing movie at user request:',
                               trailer[Movie.TITLE])
        self._queued_movie = trailer
        self.set_random_trailers_play_state(DialogState.START_MOVIE_AND_EXIT)

        # Unblock Detail Info display

        self.hide_detail_info()

    def play_movie(self, trailer, already_playing=False):
        # type: (Dict[TextType, TextType], bool) -> None
        """
            At user request, start playing movie on normal xbmc.player, after
            disabling the custom player that we use here.

            When already-playing is True, then the user has externally (JSON-RPC)
            started a movie and we just need to get out of the way.

        :param trailer:
        :param already_playing: True when movie externally started and we need
                                to get the heck out of the way
        :return:
        """
        black_background = BlackBackground.get_instance()
        black_background.set_visibility(opaque=False)
        black_background.close()
        black_background.destroy()

        if not already_playing:
            movie = trailer[Movie.FILE]
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Playing movie at user request:',
                                   trailer[Movie.TITLE],
                                   'path:', movie)

            self.set_random_trailers_play_state(
                DialogState.SHUTDOWN_CUSTOM_PLAYER)
            xbmc.Player().play(movie)

        monitor = Monitor.get_instance()

        if monitor.is_shutdown_requested():
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('SHUTDOWN requested before playing movie!')
        while not monitor.wait_for_shutdown(timeout=0.10):
            # Call xbmc.Player directly to avoid using DummyPlayer
            if xbmc.Player().isPlayingVideo():
                break

        self.set_random_trailers_play_state(DialogState.STARTED_PLAYING_MOVIE)

        # Time to exit plugin
        monitor.shutdown_requested()
        self._logger.exit('Just started player')

    def get_title_string(self, trailer):
        # type: (dict) -> TextType
        """

        :param trailer:
        :return:
        """
        title = ''
        try:
            title = '[B]' + trailer[Movie.DETAIL_TITLE] + '[/B]'

            if Settings.is_debug():
                cached = False
                normalized = False
                if self._trailer.get(Movie.NORMALIZED_TRAILER) is not None:
                    normalized = True
                elif self._trailer[Movie.CACHED_TRAILER] is not None:
                    cached = True

                if normalized:
                    title = title + ' Normalized'
                elif cached:
                    title = title + ' Cached'

        except (Exception) as e:
            self._logger.exception('')

        return title

    def bold(self, text):
        # type: (TextType) -> TextType
        """

        :return:
        """
        return '[B]' + text + '[/B]'

    def shutdown(self):
        # type: () -> None
        """
            Orderly stops execution of TrialerDialog.

            Note that this method can be called voluntarily, when the plugin
            decides to exit, as in the case of the configured number of trailers
            has played. OR, can be called by Monitor detecting a shutdown or
            abort, in which case the shutdown still needs to be orderly, but
            since there are frequent checks for Monitor shutdown/abort, the
            shutdown is less orderly, since the code is sprinkled with checks.
            In such case, some parts of the plugin can be shutting down already.

        :return:
        """
        self._logger.enter()
        self.close()
        delete_player = False
        try:
            # if self.is_random_trailers_play_state() >=
            # DialogState.STARTED_PLAYING_MOVIE:
            delete_player = True

        except (ShutdownException):
            Monitor.abortRequested()
            delete_player = True
        except (AbortException):
            delete_player = True
        finally:
            self._player_container.use_dummy_player(delete_player)

        self._title_control = None
        self._source = None
        self._trailer = None
        self._viewed_playlist = None
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.exit()
