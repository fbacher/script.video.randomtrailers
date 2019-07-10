# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: Frank Feuerbacher
'''
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import sys
import threading
import six

from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger, Trace, log_entry_exit
from common.messages import Messages
from common.monitor import Monitor
from common.utils import Utils
from action_map import Action
from common.settings import Settings
from player.player_container import PlayerContainer
from frontend.black_background import BlackBackground
from frontend.movie_manager import MovieManager, MovieStatus
from frontend.history_empty import HistoryEmpty

from frontend.utils import ReasonEvent, BaseWindow, ScreensaverManager, ScreensaverState


from kodi_six import xbmc, xbmcgui


class DialogState:
    """

    """
    NORMAL = int(0)
    GROUP_QUOTA_REACHED = int(1)
    QUOTA_REACHED = int(2)
    NO_TRAILERS_TO_PLAY = int(3)
    USER_REQUESTED_EXIT = int(4)
    START_MOVIE_AND_EXIT = int(5)
    SHUTDOWN_CUSTOM_PLAYER = int(6)
    STARTED_PLAYING_MOVIE = int(7)
    SHUTDOWN = int(8)

    label_map = {NORMAL: 'NORMAL',
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
        self._logger = Logger(self.__class__.__name__)
        local_logger = self._logger.get_method_logger('__init__')
        local_logger.enter()
        self._dialog_state = DialogState.NORMAL
        self._player_container = PlayerContainer.get_instance()
        self._player_container.register_exit_on_movie_playing(
            self.exit_screensaver_to_play_movie)

        self.get_player().setCallBacks(on_show_info=self.show_detailed_info)
        self._screensaver_manager = ScreensaverManager.get_instance()

        self._title_control = None
        self._source = None
        self._trailer = None
        self._lock = threading.RLock()
        self._long_trailer_killer = None
        self._messages = Messages.get_instance()
        self._viewed_playlist = Playlist.get_playlist(
            Playlist.VIEWED_PLAYLIST_FILE)
        self._title_control = None
        self._notification_control = None
        self._notification_timeout = 0.0
        self._notification_killer = None
        self._thread = None
        self._pause = threading.Event()

        # Used mostly as a timer
        self._show_details_event = threading.Event()
        self._wait_event = ReasonEvent()
        self._ready_to_exit_event = threading.Event()
        monitor = Monitor.get_instance()
        monitor.register_shutdown_listener(self.on_shutdown_event)

        self._shutdown = False
        self._abort = False
        self._saved_brief_info_visibility = False
        self._movie_manager = MovieManager()
        self._queued_movie = None
        #
        # Prevent flash of grid
        #
        self.set_visibility(video_window=False, info=False, brief_info=False,
                            notification=False, information=False)

    def onInit(self):
        local_logger = self._logger.get_method_logger('onInit')
        local_logger.enter()

        # Prevent flash of grid
        #
        self.set_visibility(video_window=False, info=False, brief_info=False,
                            notification=False, information=False)
        if self._thread is None:
            self._thread = threading.Thread(
                target=self.play_trailers, name='TrailerDialog')
            self._thread.start()

    def play_trailers(self):
        local_logger = self._logger.get_method_logger('play_trailers')

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
        trailers_played = 0
        trailers_to_play_on_next_iteration = trailers_per_iteration
        try:
            while not self.is_random_trailers_play_state():
                self.play_a_group_of_trailers(
                    trailers_to_play_on_next_iteration)

                if self.is_random_trailers_play_state(DialogState.NO_TRAILERS_TO_PLAY):
                    break

                self._player_container.get_player().waitForIsNotPlayingVideo()

                # Pre-seed all fields with empty values so that if display of
                # detailed movie information occurs prior to download of external
                # images, etc. This way default values are shown instead of
                # leftovers from previous movie.

                self._trailer = TrailerDialog.DUMMY_TRAILER
                self.update_detail_view()  # Does not display

                if group_trailers:
                    if total_trailers_to_play > 0:
                        trailers_played += trailers_per_iteration
                        remaining_to_play = total_trailers_to_play - trailers_played
                        if remaining_to_play <= 0:
                            break

                        if remaining_to_play < trailers_per_iteration:
                            trailers_to_play_on_next_iteration = remaining_to_play

                    self._wait_event.wait(delay_between_groups)
                    if self.is_random_trailers_play_state(DialogState.USER_REQUESTED_EXIT):
                        break
                    if self.is_random_trailers_play_state(DialogState.NORMAL):
                        # Wake up and resume playing trailers early
                        pass
                    self.set_random_trailers_play_state(DialogState.NORMAL)

                elif self.is_random_trailers_play_state(DialogState.QUOTA_REACHED):
                    break

        except (AbortException, ShutdownException):
            local_logger.debug('Received shutdown or abort')

        except (Exception) as e:
            local_logger.log_exception(e)
        finally:
            local_logger.debug('About to close TrailerDialog')
            # local_logger.debug('About to stop xbmc.Player')
            # try:
            #    self.get_player().stop()
            # except (Exception):
            #    pass
            self.cancel_long_playing_trailer_killer()
            # local_logger.debug('Stopped xbmc.Player')

            self._viewed_playlist.close()
            local_logger.debug('Closed TrailerDialog')
            self.shutdown()
            return  # Exit thread

    def play_a_group_of_trailers(self, number_of_trailers_to_play):
        local_logger = self._logger.get_method_logger(
            'play_a_group_of_trailers')

        self.set_visibility(video_window=False, info=False, brief_info=False,
                            notification=False, information=False)
        local_logger.debug(' WindowID: ' +
                           str(xbmcgui.getCurrentWindowId()))

        _1080P = 0X0  # 1920 X 1080
        _720p = 0X1  # 1280 X 720
        window_height = self.getHeight()
        window_width = self.getWidth()
        local_logger.debug('Window Dimensions: ' + str(window_height) +
                           ' H  x ' + str(window_width) + ' W')

        # self.show()
        limit_trailers_to_play = True
        if number_of_trailers_to_play == 0:
            limit_trailers_to_play = False
        try:
            # Main trailer playing loop

            if Settings.get_show_curtains():
                self._movie_manager.play_curtain_next(
                    MovieManager.OPEN_CURTAIN)

            while not self.is_random_trailers_play_state():
                local_logger.debug('top of loop')
                self.set_visibility(video_window=False, info=False, brief_info=False,
                                    notification=False, information=False)

                try:
                    status, self._trailer = self._movie_manager.get_next_trailer()
                    if status == MovieStatus.PREVIOUS_MOVIE:
                        msg = self._messages.get_msg(
                            Messages.PLAYING_PREVIOUS_MOVIE)
                        msg = msg % self._trailer[Movie.TITLE]
                        self.notification(msg)
                except (HistoryEmpty):
                    msg = self._messages.get_msg(
                        Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME)
                    self.notification(msg)
                    continue

                    # local_logger.debug('Got status:', status,
                    #                  'trailer:', self._trailer)

                    # Are there no trailers to play now, and in the future?

                if status == MovieStatus.OK and self._trailer is None:
                    self.set_random_trailers_play_state(
                        DialogState.NO_TRAILERS_TO_PLAY)
                    break

                elif status == MovieStatus.IDLE:
                    self.set_random_trailers_play_state(
                        DialogState.NO_TRAILERS_TO_PLAY)
                    local_logger.error('Should not get state IDLE')
                    break

                if status == MovieStatus.TIMED_OUT:
                    continue

                if status == MovieStatus.BUSY:
                    continue

                local_logger.debug('got trailer to play: ' +
                                   self._trailer.get(Movie.TRAILER))

                video_is_curtain = (self._trailer[Movie.SOURCE] == 'curtain')

                # TODO: fix comment
                # Screen will be black since both
                # TrailerDialog.PLAYER_GROUP_CONTROL and
                # TrailerDialog.DETAIL_GROUP_CONTROL are, by default,
                # not visible in script-trailerwindow.xml
                # self.show()

                # Our event listeners will stop the player, as appropriate.

                local_logger.debug('wait for not playing 1')
                self.get_player().waitForIsNotPlayingVideo()

                self._source = self._trailer.get(Movie.SOURCE)
                show_movie_details = (
                    Settings.get_time_to_display_detail_info() > 0)
                show_trailer_title = Settings.get_show_movie_title()
                if not video_is_curtain:
                    self._viewed_playlist.record_played_trailer(self._trailer)

                if self._source == Movie.FOLDER_SOURCE:
                    show_movie_details = False

                if video_is_curtain:
                    show_movie_details = False
                    show_trailer_title = False

                local_logger.debug('checking play_state 1')
                if self.is_random_trailers_play_state():
                    local_logger.debug('breaking due to play_state 1 movie:',
                                       self._trailer[Movie.TITLE])
                    break

                # This will block if showing Movie Details
                local_logger.debug(
                    'about to show_movie_info movie:', self._trailer[Movie.TITLE])
                self.show_movie_info(show_detail_info=show_movie_details,
                                     show_brief_info=show_trailer_title)
                local_logger.debug(
                    'finished show_movie_info, movie:',  self._trailer[Movie.TITLE])

                # Play Trailer
                # TODO: change to asynchronous so that it can occur while
                # showing details

                local_logger.debug('checking play_state 2 movie:',
                                   self._trailer[Movie.TITLE])
                if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                    local_logger.debug(
                        'breaking due to play_state 2 movie:', self._trailer[Movie.TITLE])
                    break

                local_logger.debug('About to play:',
                                   self._trailer.get(Movie.TRAILER))

                self.set_visibility(video_window=True, info=False,
                                    brief_info=show_trailer_title,
                                    notification=False,
                                    information=show_trailer_title)
                local_logger.debug('about to play movie:',
                                   self._trailer[Movie.TITLE])
                normalized = False
                trailer_path = None
                if self._trailer.get(Movie.NORMALIZED_TRAILER) is not None:
                    trailer_path = self._trailer[Movie.NORMALIZED_TRAILER]
                    self.get_player().play_trailer(trailer_path, self._trailer)
                    normalized = True
                else:
                    trailer_path = self._trailer[Movie.TRAILER]
                    self.get_player().play_trailer(trailer_path, self._trailer)
                    # TODO: DELETE ME
                    try:
                        if Utils.is_trailer_from_cache(trailer_path):
                            normalized = True
                    except (Exception) as e:
                        if type(trailer_path).__name__ not in ('unicode', 'newstr'):
                            local_logger.debug('LEAK trailer_path not unicode:',
                                               type(trailer_path).__name__)

                local_logger.debug('started play_trailer:', self._trailer[Movie.TITLE],
                                   'source:', self._trailer[Movie.SOURCE], 'normalized:', normalized,
                                   'path:', trailer_path)

                # Again, we rely on our listeners to interrupt, as
                # appropriate. Trailer/Movie should be about to be played or
                # playing.

                try:
                    local_logger.debug(
                        'checking play_state 3 movie:', self._trailer[Movie.TITLE])

                    if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                        local_logger.debug(
                            'breaking at play_state 3 movie:', self._trailer[Movie.TITLE])
                        break

                    local_logger.debug(
                        'wait_for_is_playing_video 2 movie:', self._trailer[Movie.TITLE])
                    if not self.get_player().waitForIsPlayingVideo(timeout=5.0):
                        local_logger.debug('Timed out Waiting for Player.')

                    local_logger.debug(
                        'checking play_state 4 movie:', self._trailer[Movie.TITLE])
                    if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                        local_logger.debug(
                            'breaking at play_state 4 movie:', self._trailer[Movie.TITLE])
                        break

                    # Now that the trailer has started, see if it will run too long so
                    # that we need to set up to kill it playing.

                    trailer_total_time = self.get_player().getTotalTime()
                    max_play_time = Settings.get_max_trailer_length()
                    if trailer_total_time > max_play_time:
                        local_logger.debug('Killing long trailer:',
                                           self._trailer[Movie.TITLE], 'limit:',
                                           max_play_time)
                        self.start_long_trailer_killer(max_play_time)
                except (AbortException, ShutdownException):
                    raise sys.exc_info()
                except (Exception) as e:
                    local_logger.log_exception()

                # Again, we rely on our listeners to  stop the player, as
                # appropriate

                self.get_player().waitForIsNotPlayingVideo()
                local_logger.debug(
                    'checking play_state 5 movie:', self._trailer[Movie.TITLE])
                if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                    local_logger.debug(
                        'breaking at play_state 5 movie:', self._trailer[Movie.TITLE])
                    break

                self.cancel_long_playing_trailer_killer()

                # Again, we rely on our listeners to  stop this display, as
                # appropriate

                self.set_visibility(video_window=False, info=False, brief_info=False,
                                    notification=False, information=False)
                if limit_trailers_to_play and not video_is_curtain:
                    number_of_trailers_to_play -= 1
                    if number_of_trailers_to_play < 1:
                        if Settings.is_group_trailers():
                            self.set_random_trailers_play_state(
                                DialogState.GROUP_QUOTA_REACHED)
                        else:
                            self.set_random_trailers_play_state(
                                DialogState.QUOTA_REACHED)

            if self._trailer is None:
                local_logger.error('There will be no trailers to play')
                self.notification(self._messages.get_msg(
                    Messages.NO_TRAILERS_TO_PLAY))
                self.set_random_trailers_play_state(
                    DialogState.NO_TRAILERS_TO_PLAY)
            else:
                local_logger.debug(
                    'out of inner play loop movie:', self._trailer[Movie.TITLE])

            if Settings.get_show_curtains():
                self._movie_manager.play_curtain_next(
                    MovieManager.CLOSE_CURTAIN)

                _, curtain = self._movie_manager.get_next_trailer()
                self.set_visibility(video_window=True, info=False, brief_info=False,
                                    notification=False, information=False)
                self.get_player().play_trailer(curtain[Movie.TRAILER].encode('utf-8'),
                                               curtain)
                if not self.get_player().waitForIsPlayingVideo(timeout=5.0):
                    local_logger.debug('Timed out Waiting for Player.')
                self.get_player().waitForIsNotPlayingVideo()

            local_logger.debug(
                'Completed everything except play_movie, if there is one')
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            local_logger.log_exception(e)

        try:
            if self._trailer is not None:
                local_logger.debug('Checking to see if there is a movie to play:',
                                   self._trailer[Movie.TITLE])
            if self.is_random_trailers_play_state(DialogState.START_MOVIE_AND_EXIT,
                                                  exact_match=True):
                local_logger.debug('about to play movie:', self._queued_movie)
                self.set_visibility(video_window=True, info=False, brief_info=False,
                                    notification=False, information=False)
                self.play_movie(self._queued_movie)

        except (AbortException, ShutdownException):
            local_logger.debug('Received shutdown or abort')
        except (Exception) as e:
            local_logger.log_exception(e)

    def get_player(self):
        return self._player_container.get_player()

    def is_random_trailers_play_state(self, minimum_exit_state=DialogState.GROUP_QUOTA_REACHED,
                                      exact_match=False, throw_exception_on_shutdown=True):
        monitor = Monitor.get_instance()
        if monitor is None or monitor.is_shutdown_requested():
            self._dialog_state = DialogState.SHUTDOWN

        if throw_exception_on_shutdown:
            monitor.throw_exception_if_shutdown_requested()

        if exact_match:
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
        local_logger = self._logger.get_method_logger('notification')

        try:
            local_logger.debug('message:', message)
            self.get_notification_control(text=message)
            self.set_visibility(notification=True, information=True)
            self.wait_or_exception(
                timeout=Constants.MAX_PLAY_TIME_WARNING_TIME)
            self.set_visibility(notification=False)
        except (Exception) as e:
            local_logger.log_exception(e)

        return

    def wait_or_exception(self, timeout=0):
        # type: (float) -> None
        """

        :param delay:
        :return:
        """
        # During shutdown, Monitor deletes itself, so to avoid a silly error in
        # the log, avoid calling it.

        monitor = Monitor.get_instance()
        if monitor is not None:
            monitor.throw_exception_if_shutdown_requested(delay=timeout)
        return

    @log_entry_exit
    def show_detailed_info(self, from_user_request=False):
        local_logger = self._logger.get_method_logger('show_detailed_info')

        if self._source != Movie.FOLDER_SOURCE:
            local_logger.debug('about to show_detailed_info')
            display_seconds = Settings.get_time_to_display_detail_info()
            if from_user_request:
                display_seconds = 0
            else:  # TODO: I suspect the pause below belongs in the if from_user_request
                if self.get_player() is not None:
                    self.get_player().pausePlay()

            self.update_detail_view()
            self.show_detail_info(self._trailer, display_seconds)

    def show_detail_info(self, trailer, display_seconds=0):
        local_logger = self._logger.get_method_logger('show_detail_info')
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)
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
        local_logger = self._logger.get_method_logger('hide_detail_info')
        local_logger.enter()
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)
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
        local_logger = self._logger.get_method_logger('set_visibility')

        self.wait_or_exception(timeout=0)
        if self.is_random_trailers_play_state(
                minimum_exit_state=DialogState.SHUTDOWN_CUSTOM_PLAYER):
            video_window = True
            info = False
            brief_info = False
            notification = False
            information = False

        commands = []
        focus = None

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
                focus = title
                info_command = "Skin.SetBool(Info)"
            else:
                info_command = "Skin.Reset(Info)"
            commands.append(info_command)

        if brief_info is not None:
            title = None
            if brief_info:
                title = self.getControl(38021)
                focus = title
                info_command = "Skin.SetBool(SummaryLabel)"
            else:
                info_command = "Skin.Reset(SummaryLabel)"
            commands.append(info_command)

        if notification is not None:
            if notification:
                info_command = "Skin.SetBool(Notification)"
                focus = self.getControl(38023)
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
            local_logger.debug(command)
            xbmc.executebuiltin(command)

        if focus is not None:
            self.setFocus(focus)

    def update_detail_view(self):
        local_logger = self._logger.get_method_logger('update_detail_view')
        try:
            Monitor.get_instance().throw_exception_if_shutdown_requested()

            local_logger.enter()
            local_logger.debug(Trace.TRACE)

            control = self.getControl(38002)  # type: xbmcgui.ControlImage
            thumbnail = self._trailer[Movie.THUMBNAIL]
            control.setImage(thumbnail)

            self.getControl(38004).setImage(self._trailer[Movie.FANART])

            title_string = self.get_title_string(self._trailer)

            title = self.getControl(38003)
            title.setLabel(title_string)
            self.setFocus(title)

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

            local_logger.exit()

        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except (Exception) as e:
            local_logger.log_exception(e)
        finally:
            pass

    def doModal(self):
        local_logger = self._logger.get_method_logger('doModal')
        local_logger.enter()

        # In case playing was paused due to screensaver deactivated
        # and now it is being reactivated.

        # self.unBlockPlayingTrailers()
        super().doModal()
        local_logger.exit()
        return self._dialog_state

    def show(self):
        local_logger = self._logger.get_method_logger('show')
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)
        super().show()

    def close(self):
        local_logger = self._logger.get_method_logger('close')
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)
        super().close()
        self._ready_to_exit_event.set()

    def set_random_trailers_play_state(self, dialog_state):
        # type: (int) -> None
        # TODO: Change to use named int type
        """

        :param dialog_state:
        :return:
        """
        local_logger = self._logger.get_method_logger(
            'set_random_trailers_play_state')
        local_logger.trace('state:', DialogState.getLabel(dialog_state),
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

        self.close()
        xbmc.executebuiltin('Action(FullScreen,12005)')

    def on_shutdown_event(self):
        # type: () -> None
        """

        :return:
        """
        local_logger = self._logger.get_method_logger('on_shutdown_event')
        local_logger.enter()
        self.set_random_trailers_play_state(DialogState.SHUTDOWN)
        self._shutdown = True
        self._wait_event.set(ReasonEvent.SHUTDOWN)

       # TODO: put this in own class

    def start_long_trailer_killer(self, max_play_time):
        # type: (Union[int, float]) -> None
        """

        :param max_play_time:
        :return:
        """
        local_logger = self._logger.get_method_logger(
            'start_long_trailer_killer')
        local_logger.trace('waiting on lock', trace=Trace.TRACE_UI_CONTROLLER)
        with self._lock:
            local_logger.trace('got lock, max_play_time:',
                               max_play_time,
                               trace=Trace.TRACE_UI_CONTROLLER)
            self._long_trailer_killer = None
            if not self.is_random_trailers_play_state(DialogState.USER_REQUESTED_EXIT):
                if max_play_time > Constants.MAX_PLAY_TIME_WARNING_TIME + 2:
                    max_play_time -= Constants.MAX_PLAY_TIME_WARNING_TIME
                    local_logger.trace('adjusted max_play_time:', max_play_time,
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
        local_logger = self._logger.get_method_logger(
            'kill_long_playing_trailer')
        try:
            local_logger.enter()
            local_logger.trace('Now Killing',
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
            Logger.log_exception(e)

        local_logger.trace('exit', trace=Trace.TRACE_SCREENSAVER)

    def cancel_long_playing_trailer_killer(self):
        # type: () -> None
        """

        :return:
        """
        local_logger = self._logger.get_method_logger(
            'cancel_long_playing_trailer_killer')
        local_logger.trace('enter, waiting on lock',
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
        local_logger = self._logger.get_method_logger('play_next_trailer')
        local_logger.enter()

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
        local_logger.trace('Finished playing old trailer',
                           trace=Trace.TRACE_SCREENSAVER)

    def getFocus(self):
        # type: () -> None
        """

        :return:
        """
        local_logger = self._logger.get_method_logger('getFocus')
        local_logger.debug('Do not use.')
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

        local_logger = self._logger.get_method_logger('onAction')

        if action.getId() != 107:  # Mouse Move
            local_logger.trace('Action.id:', action.getId(),
                               hex(action.getId()),
                               'Action.button_code:',
                               action.getButtonCode(),
                               hex(action.getButtonCode()), trace=Trace.TRACE)

        # if not self._screensaver_manager.isAddonActive():
        #    local_logger.exit('Addon inActive')
        #    return

        action_mapper = Action.get_instance()
        matches = action_mapper.getKeyIDInfo(action)

        if action.getId() != 107:  # Mouse Move
            for line in matches:
                local_logger.debug(line)

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
        if action.getId() != 107:  # Mouse Move
            local_logger.debug('Key found:', key)

        ##################################################################
        if action_id == xbmcgui.ACTION_SHOW_INFO:
            local_logger.debug(key, 'Toggle Show_Info')

            if not self.is_random_trailers_play_state(DialogState.NORMAL):
                heading = self._messages.get_msg(Messages.HEADER_IDLE)
                message = self._messages.get_msg(Messages.PLAYER_IDLE)
                self.notification(message)
            elif self.getControl(TrailerDialog.DETAIL_GROUP_CONTROL).isVisible():
                self.hide_detail_info()
            else:
                self.show_detailed_info(from_user_request=True)

        ##################################################################
        elif (action_id == xbmcgui.ACTION_STOP or action_id == xbmcgui.ACTION_MOVE_RIGHT):
            local_logger.debug(key, 'Play next trailer at user\'s request')
            self.play_next_trailer()

        ##################################################################

        elif action_id == xbmcgui.ACTION_MOVE_LEFT:
            local_logger.debug(
                key, 'Play previous trailer at user\'s request')
            self._movie_manager.play_previous_trailer()
            self.play_next_trailer()

        ##################################################################
        #
        # PAUSE/PLAY is handled by native player
        #
        elif action_id == xbmcgui.ACTION_QUEUE_ITEM:
            if Utils.is_couch_potato_installed():
                local_logger.debug(key, 'Queue to couch potato')
                str_couch_potato = 'plugin://plugin.video.couchpotato_manager/movies/add?title=' + \
                    self._trailer[Movie.TITLE]
                xbmc.executebuiltin('XBMC.RunPlugin(' + str_couch_potato + ')')

        ##################################################################
        elif (action_id == xbmcgui.ACTION_PREVIOUS_MENU
              or action_id == xbmcgui.ACTION_NAV_BACK):
            local_logger.trace('Exit application',
                               trace=Trace.TRACE_SCREENSAVER)
            local_logger.debug(key, 'Exiting RandomTrailers at user request')

            # Ensure we are not blocked

            self.hide_detail_info()
            self.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)
        ##################################################################

        # TODO: Need proper handling of this (and other inputs that we don't
        # handle. Sigh

        elif (action_id == xbmcgui.ACTION_BUILT_IN_FUNCTION):
            local_logger.trace('ACTION_BUILT_IN_FUNCTION',
                               trace=Trace.TRACE_SCREENSAVER)
            local_logger.debug(key, 'Exiting RandomTrailers due to',
                               'ACTION_BUILT_IN_FUNCTION')

            # Ensure we are not blocked

            self.hide_detail_info()
            self.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)

        ##################################################################
        elif (action_id == xbmcgui.ACTION_ENTER
              or action_id == xbmcgui.ACTION_SELECT_ITEM
              or action_id == xbmcgui.ACTION_SHOW_GUI):
            local_logger.debug(key, 'Play Movie')
            movie_file = self._trailer[Movie.FILE]
            local_logger.debug('Playing movie for currently playing trailer.',
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
            local_logger.debug(key)
            self.add_to_playlist(action_id, self._trailer)

    def get_title_control(self, text=''):
        title_control = self.getControl(38021)
        if text != '':
            title_control.setLabel(text)
        return title_control
    '''
        title.setLabel(title_string)
        
        local_logger = self._logger.get_method_logger('get_title_control')
        if self._title_control is None:
            text_color = '0xFFFFFFFF'  # White
            shadow_color = '0x00000000'  # Black
            disabled_color = '0x0000000'  # Won't matter, screen will be invisible
            x_pos = 20
            y_pos = 20
            width = 680
            height = 20
            font = 'font14'
            XBFONT_LEFT = 0x00000000
            XBFONT_RIGHT = 0x00000001
            XBFONT_CENTER_X = 0x00000002
            XBFONT_CENTER_Y = 0x00000004
            XBFONT_TRUNCATED = 0x00000008
            XBFONT_JUSTIFIED = 0x00000010
            alignment = XBFONT_CENTER_Y
            has_path = False
            angle = 0
            self._title_control = xbmcgui.ControlLabel(x_pos, y_pos, width, height,
                                                       text, font, text_color,
                                                       disabled_color, alignment,
                                                       has_path, angle)
            self.addControl(self._title_control)
            local_logger.exit()

        return self._title_control
    '''

    def get_notification_control(self, text=None):
        # type: (TextType) -> xbmcgui.ControlLabel
        """

        :param text:
        :return:
        """
        local_logger = self._logger.get_method_logger(
            'get_notification_control')
        title_control = self.getControl(38023)
        if text != '':
            title_control.setLabel(text)
        return title_control

    '''
        if self._notification_control is None:
            # text_color = '0xFFFFFFFF'  # White
            text_color = '0xFF6666FF'
            shadow_color = '0x00000000'  # Black
            disabled_color = '0x0000000'  # Won't matter, screen will be invisible
            x_pos = 20
            y_pos = 20
            width = 680
            height = 20
            font = 'font27'
            XBFONT_CENTER_Y = 0x00000004
            alignment = XBFONT_CENTER_Y
            has_path = False
            angle = 0
            if text is None:
                text = ''
            text = '[B]' + text + '[/B]'
            self._notification_control = xbmcgui.ControlLabel(x_pos, y_pos, width, height,
                                                              text, font, text_color,
                                                              disabled_color, alignment,
                                                              has_path, angle)
            self.addControl(self._notification_control)
            self._notification_timeout = timeout
            local_logger.exit()
        else:
            if text is not None:
                text = '[B]' + text + '[/B]'
                self._notification_control.setLabel(text)

        return self._notification_control
    '''

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
        local_logger = self._logger.get_method_logger('addToPlayList')

        playlist_file = TrailerDialog._playlist_map.get(play_list_id, None)
        if playlist_file is None:
            local_logger.error(
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
        local_logger = self._logger.get_method_logger('queue_movie')
        local_logger.debug('Queing movie at user request:',
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
        local_logger = self._logger.get_method_logger('play_movie')

        black_background = BlackBackground.get_instance()
        black_background.set_visibility(opaque=False)
        black_background.close()
        black_background.destroy()

        movie = trailer[Movie.FILE]
        if not already_playing:
            local_logger.debug('Playing movie at user request:',
                               trailer[Movie.TITLE],
                               'path:', movie)

            self.set_random_trailers_play_state(
                DialogState.SHUTDOWN_CUSTOM_PLAYER)
            xbmc.Player().play(movie)

        monitor = Monitor.get_instance()
        if monitor.is_shutdown_requested() or monitor.abortRequested():
            local_logger.debug('SHUTDOWN requested before playing movie!')
        while not monitor.wait_for_shutdown(timeout=0.10):
            # Call xbmc.Player directly to avoid using DummyPlayer
            if xbmc.Player().isPlayingVideo():
                break

        self.set_random_trailers_play_state(DialogState.STARTED_PLAYING_MOVIE)

        # Time to exit plugin
        monitor.shutdown_requested()
        local_logger.exit('Just started player')

    def get_title_string(self, trailer):
        # type: (dict) -> TextType
        """

        :param trailer:
        :return:
        """
        title = '[B]' + trailer[Movie.DETAIL_TITLE] + '[/B]'
        title2 = trailer[Movie.DETAIL_TITLE]

        if Settings.is_debug():
            normalized = False
            if self._trailer.get(Movie.NORMALIZED_TRAILER) is not None:
                normalized = True
            else:
                trailer_path = self._trailer[Movie.TRAILER].encode('utf-8')
                if Utils.is_trailer_from_cache(trailer_path.decode('utf-8')):
                    normalized = True

            if normalized:
                title = title + ' Normalized'

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

        :return:
        """
        local_logger = self._logger.get_method_logger('shutdown')
        local_logger.enter()
        self.close()
        delete_player = False
        try:
            if self.is_random_trailers_play_state() >= DialogState.STARTED_PLAYING_MOVIE:
                delete_player = True

            self._player_container.use_dummy_player(delete_player)
        except (ShutdownException, AbortException):
            pass

        self._title_control = None
        self._source = None
        self._trailer = None
        self._viewed_playlist = None
