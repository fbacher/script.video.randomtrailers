# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: Frank Feuerbacher
'''

from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                      TextType, DEVELOPMENT, RESOURCE_LIB)
<<<<<<< HEAD
import sys
import threading
import six

from common.front_end_bridge import FrontendBridge
from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger, Trace, log_entry_exit
from common.messages import Messages
from common.monitor import Monitor
=======
from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger, Trace, logEntryExit
from common.messages import Messages
from common.monitor import Monitor
from common.front_end_bridge import FrontendBridge
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
from action_map import Action
from common.settings import Settings
from player.player_container import PlayerContainer
from frontend.black_background import BlackBackground
<<<<<<< HEAD
from frontend.movie_manager import MovieManager, MovieStatus
from frontend.history_empty import HistoryEmpty

from frontend.utils import ReasonEvent, BaseWindow, ScreensaverManager, ScreensaverState


from kodi_six import xbmc, xbmcgui


=======

from frontend.utils import ReasonEvent, BaseWindow, ScreensaverManager, ScreensaverState

import sys
import threading
from kodi_six import xbmc, xbmcgui


# TODO: Put this in separate file

>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
class DialogState:
    """

    """
<<<<<<< HEAD
    NORMAL = int(0)
    GROUP_QUOTA_REACHED = int(1)
    QUOTA_REACHED = int(2)
    NO_TRAILERS_TO_PLAY = int(3)
    USER_REQUESTED_EXIT = int(4)
    START_MOVIE_AND_EXIT = int(5)
    SHUTDOWN_CUSTOM_PLAYER = int(6)
    STARTED_PLAYING_MOVIE = int(7)
    SHUTDOWN = int(8)

    label_map = {NORMAL: u'NORMAL',
                 GROUP_QUOTA_REACHED: u'GROUP_QUOTA_REACHED',
                 QUOTA_REACHED: u'QUOTA_REACHED',
                 NO_TRAILERS_TO_PLAY: u'NO_TRAILERS_TO_PLAY',
                 USER_REQUESTED_EXIT: u'USER_REQUESTED_EXIT',
                 START_MOVIE_AND_EXIT: u'START_MOVIE_AND_EXIT',
                 SHUTDOWN_CUSTOM_PLAYER: u'SHUTDOWN_CUSTOM_PLAYER',
                 STARTED_PLAYING_MOVIE: u'STARTED_PLAYING_MOVIE',
                 SHUTDOWN: u'SHUTDOWN'}
    @staticmethod
    def getLabel(dialogState):
        return DialogState.label_map[dialogState]
=======
    NORMAL = 0
    GROUP_QUOTA_REACHED = 1
    QUOTA_REACHED = 2
    NO_TRAILERS_TO_PLAY = 3
    USER_REQUESTED_EXIT = 4
    START_MOVIE_AND_EXIT = 5
    SHUTDOWN_CUSTOM_PLAYER = 6
    STARTED_PLAYING_MOVIE = 7
    SHUTDOWN = 8

    labelMap = {NORMAL: u'NORMAL',
                GROUP_QUOTA_REACHED: u'GROUP_QUOTA_REACHED',
                QUOTA_REACHED: u'QUOTA_REACHED',
                NO_TRAILERS_TO_PLAY: u'NO_TRAILERS_TO_PLAY',
                USER_REQUESTED_EXIT: u'USER_REQUESTED_EXIT',
                START_MOVIE_AND_EXIT: u'START_MOVIE_AND_EXIT',
                SHUTDOWN_CUSTOM_PLAYER: u'SHUTDOWN_CUSTOM_PLAYER',
                STARTED_PLAYING_MOVIE: u'STARTED_PLAYING_MOVIE',
                SHUTDOWN: u'SHUTDOWN'}

    @staticmethod
    def getLabel(dialogState):
        return DialogState.labelMap[dialogState]
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7


# noinspection Annotator
class TrailerDialog(xbmcgui.WindowXMLDialog):
    '''
        Note that the underlying 'script-trailer-window.xml' has a "videowindow"
        control. This causes the player to ignore many of the normal keymap actions.
    '''
    DETAIL_GROUP_CONTROL = 38001
    PLAYER_GROUP_CONTROL = 38000

<<<<<<< HEAD

    def __init__(self, *args, **kwargs):
        # type: (*Any, **Dict[TextType, TextType]) -> None
        super().__init__(*args)
        self._logger = Logger(self.__class__.__name__)
        local_logger = self._logger.get_method_logger(u'__init__')
        local_logger.enter()
        self._dialog_state = DialogState.NORMAL
        self._player_container = PlayerContainer.get_instance()

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
        self._notification_timeout = None
        self._notification_killer = None
=======
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()
        self._dialogState = DialogState.NORMAL
        self._playerContainer = PlayerContainer.getInstance()

        self.getPlayer().setCallBacks(onShowInfo=self.showDetailedInfo)
        self._screensaverManager = ScreensaverManager.getInstance()

        self._titleControl = None
        self._source = None
        self._trailer = None
        self._lock = threading.RLock()
        self._longTrailerKiller = None
        self._messages = Messages.getInstance()
        self._viewedPlaylist = Playlist.getPlaylist(
            Playlist.VIEWED_PLAYLIST_FILE)
        self._titleControl = None
        self._notificationControl = None
        self._notificationTimeout = None
        self._notificationKiller = None
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        self._thread = None
        self._pause = threading.Event()

        # Used mostly as a timer
<<<<<<< HEAD
        self._show_details_event = threading.Event()
        self._wait_event = ReasonEvent()
        monitor = Monitor.get_instance()
        monitor.register_shutdown_listener(self)

        self._shutdown = False
        self._abort = False
        self._dummy_control = None
        self._saved_brief_info_visibility = False
        self._movie_manager = MovieManager()
        self._queued_movie = None

    def onInit(self):
        local_logger = self._logger.get_method_logger(u'onInit')
        local_logger.enter()

        if self._dummy_control is None:
            self.set_visibility(video_window=False, info=False, brief_info=False,
                                notification=False)
            self._dummy_control = xbmcgui.ControlButton(
                0, 0, 1, 1, u'')
            self.addControl(self._dummy_control)
            self._dummy_control.setVisible(True)
=======
        self._showDetailsEvent = threading.Event()
        self._waitEvent = ReasonEvent()
        monitor = Monitor.getInstance()
        monitor.registerShutdownListener(self)
        monitor.registerAbortListener(self)

        self._shutdown = False
        self._abort = False
        self._dummyControl = None
        self._playOpenCurtainNext = False
        self._playCloseCurtainNext = False
        self._queuedMovie = None
        self._savedBriefInfoVisibility = False

    def onInit(self):
        localLogger = self._logger.getMethodLogger(u'onInit')
        localLogger.enter()

        if self._dummyControl is None:
            self.setVisibility(videoWindow=False, info=False, briefInfo=False,
                               notification=False)
            self._dummyControl = xbmcgui.ControlButton(
                0, 0, 1, 1, u'')
            self.addControl(self._dummyControl)
            self._dummyControl.setVisible(True)
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

        # TODO: - Need own thread subclasses to catch unhandled exceptions
        # and to catch abortException & ShutdownException

        if self._thread is None:
            self._thread = threading.Thread(
<<<<<<< HEAD
                target=self.play_trailers, name=u'TrailerDialog')
            self._thread.start()

    def play_trailers(self):
        local_logger = self._logger.get_method_logger(u'play_trailers')

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
            #blackBackground = BlackBackground.get_instance()

            while not self.is_random_trailers_play_state():
                # blackBackground.show()

                self.play_a_group_of_trailers(trailers_to_play_on_next_iteration)

                if self.is_random_trailers_play_state(DialogState.NO_TRAILERS_TO_PLAY):
                   break

                self._player_container.get_player().waitForIsNotPlayingVideo()

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
                    # Monitor.get_instance().wait_for_shutdown(delay_between_groups)
                    self.set_random_trailers_play_state(DialogState.NORMAL)

                elif self.is_random_trailers_play_state(DialogState.QUOTA_REACHED):
                    break

        except (AbortException, ShutdownException):
            local_logger.debug(u'Received shutdown or abort')

        except (Exception) as e:
            local_logger.log_exception(e)
        finally:
            local_logger.debug(u'About to close TrailerDialog')
            # local_logger.debug(u'About to stop xbmc.Player')
            # try:
            #    self.get_player().stop()
            # except (Exception):
            #    pass
            self.cancel_long_playing_trailer_killer()
            # local_logger.debug(u'Stopped xbmc.Player')

            self._viewed_playlist.close()
            local_logger.debug(u'Closed TrailerDialog')
            self.shutdown()
            return self._dialog_state

    def play_a_group_of_trailers(self, number_of_trailers_to_play):
        local_logger = self._logger.get_method_logger(u'play_a_group_of_trailers')

        # self.setBriefInfoVisibility(False)
        self.set_visibility(video_window=False, info=False, brief_info=False,
                            notification=False)
        local_logger.debug(u' WindowID: ' +
=======
                target=self.playTrailers, name=u'TrailerDialog')
            self._thread.start()

    def playTrailers(self):
        localLogger = self._logger.getMethodLogger(u'playTrailers')

        totalTrailersToPlay = Settings.getNumberOfTrailersToPlay()

        trailersPerGroup = totalTrailersToPlay
        groupTrailers = Settings.isGroupTrailers()

        if groupTrailers:
            trailersPerGroup = Settings.getTrailersPerGroup()

        trailersPerIteration = totalTrailersToPlay
        if trailersPerGroup > 0:
            trailersPerIteration = trailersPerGroup
            if totalTrailersToPlay > 0:
                trailersPerIteration = min(
                    trailersPerIteration, totalTrailersToPlay)
        else:
            trailersPerIteration = totalTrailersToPlay

        delayBetweenGroups = Settings.getGroupDelay()
        trailersPlayed = 0
        trailersToPlayOnNextIteration = trailersPerIteration
        try:
            #blackBackground = BlackBackground.getInstance()

            while not self.isRandomTrailersPlayState():
                # blackBackground.show()

                self.playAGroupOfTrailers(trailersToPlayOnNextIteration)

                if self.isRandomTrailersPlayState(DialogState.NO_TRAILERS_TO_PLAY):
                   break

                self._playerContainer.getPlayer().waitForIsNotPlayingVideo()

                if groupTrailers:
                    if totalTrailersToPlay > 0:
                        trailersPlayed += trailersPerIteration
                        remainingToPlay = totalTrailersToPlay - trailersPlayed
                        if remainingToPlay <= 0:
                            break

                        if remainingToPlay < trailersPerIteration:
                            trailersToPlayOnNextIteration = remainingToPlay

                    self._waitEvent.wait(delayBetweenGroups)
                    if self.isRandomTrailersPlayState(DialogState.USER_REQUESTED_EXIT):
                        break
                    if self.isRandomTrailersPlayState(DialogState.NORMAL):
                        # Wake up and resume playing trailers early
                        pass
                    # Monitor.getInstance().waitForShutdown(delayBetweenGroups)
                    self.setRandomTrailersPlayState(DialogState.NORMAL)

                elif self.isRandomTrailersPlayState(DialogState.QUOTA_REACHED):
                    break

        except (AbortException, ShutdownException):
            localLogger.debug(u'Received shutdown or abort')

        except (Exception) as e:
            localLogger.logException(e)
        finally:
            localLogger.debug(u'About to close TrailerDialog')
            # localLogger.debug(u'About to stop xbmc.Player')
            # try:
            #    self.getPlayer().stop()
            # except (Exception):
            #    pass
            self.cancelLongPlayingTrailerKiller()
            # localLogger.debug(u'Stopped xbmc.Player')

            self._viewedPlaylist.close()
            localLogger.debug(u'Closed TrailerDialog')
            self.shutdown()
            return self._dialogState

    def playAGroupOfTrailers(self, numberOfTrailersToPlay):
        localLogger = self._logger.getMethodLogger(u'playAGroupOfTrailers')

        # self.setBriefInfoVisibility(False)
        self.setVisibility(videoWindow=False, info=False, briefInfo=False,
                           notification=False)
        localLogger.debug(u' WindowID: ' +
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
                          str(xbmcgui.getCurrentWindowId()))

        _1080P = 0X0  # 1920 X 1080
        _720p = 0X1  # 1280 X 720
<<<<<<< HEAD
        window_height = self.getHeight()
        window_width = self.getWidth()
        local_logger.debug(u'Window Dimensions: ' + str(window_height) +
                          u' H  x ' + str(window_width) + u' W')

        # self.show()
        limit_trailers_to_play = True
        if number_of_trailers_to_play == 0:
            limit_trailers_to_play = False
        try:
            # Main trailer playing loop

            self._movie_manager.play_curtain_next(MovieManager.OPEN_CURTAIN)

            while not self.is_random_trailers_play_state():
                #self._queued_movie = None
                local_logger.debug(u'top of loop')
                self.set_visibility(video_window=False, info=False, brief_info=False,
                                    notification=False)

                try:
                    status, self._trailer = self._movie_manager.get_next_trailer()
                    if status == MovieStatus.PREVIOUS_MOVIE:
                        msg = self._messages.get_msg(Messages.PLAYING_PREVIOUS_MOVIE)
                        msg = msg % self._trailer[Movie.TITLE]
                        self.notification(msg)
                except (HistoryEmpty):
                    msg = self._messages.get_msg(Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME)
                    self.notification(msg)
                    continue

                video_is_curtain = (self._trailer[Movie.SOURCE] == u'curtain')

                # local_logger.debug(u'Got status:', status,
=======
        windowHeight = self.getHeight()
        windowWidth = self.getWidth()
        localLogger.debug(u'Window Dimensions: ' + str(windowHeight) +
                          u' H  x ' + str(windowWidth) + u' W')

        # self.show()
        limitTrailersToPlay = True
        if numberOfTrailersToPlay == 0:
            limitTrailersToPlay = False
        try:
            self.frontEndBridge = FrontendBridge.getInstance()
            self._playOpenCurtainNext = Settings.getShowCurtains()
            # Main trailer playing loop

            while not self.isRandomTrailersPlayState():
                #self._queuedMovie = None
                self.setVisibility(videoWindow=False, info=False, briefInfo=False,
                                   notification=False)

                status, self._trailer = self.getNextTrailer()
                videoIsCurtain = (self._trailer[Movie.SOURCE] == u'curtain')

                # localLogger.debug(u'Got status:', status,
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
                #                  u'trailer:', self._trailer)

                # Are there no trailers to play now, and in the future?

<<<<<<< HEAD
                if status == MovieStatus.OK and self._trailer is None:
                    self.set_random_trailers_play_state(
                        DialogState.NO_TRAILERS_TO_PLAY)
                    break

                elif status == MovieStatus.IDLE:
                    self.set_random_trailers_play_state(
                        DialogState.NO_TRAILERS_TO_PLAY)
                    local_logger.error(u'Should not get state IDLE')
                    break

                if status == MovieStatus.TIMED_OUT:
                    continue

                if status == MovieStatus.BUSY:
                    continue

                local_logger.debug(u'got trailer to play: ' +
                                  self._trailer.get(Movie.TRAILER))
                self.setFocus(self._dummy_control)
=======
                if status == FrontendBridge.OK and self._trailer is None:
                    self.setRandomTrailersPlayState(
                        DialogState.NO_TRAILERS_TO_PLAY)
                    break

                elif status == FrontendBridge.IDLE:
                    self.setRandomTrailersPlayState(
                        DialogState.NO_TRAILERS_TO_PLAY)
                    localLogger.error(u'Should not get state IDLE')
                    break

                if status == FrontendBridge.TIMED_OUT:
                    continue

                if status == FrontendBridge.BUSY:
                    continue

                localLogger.debug(u'got trailer to play: ' +
                                  self._trailer.get(Movie.TRAILER))
                self.setFocus(self._dummyControl)
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

                # Screen will be black since both
                # TrailerDialog.PLAYER_GROUP_CONTROL and
                # TrailerDialog.DETAIL_GROUP_CONTROL are, by default,
                # not visible in script-trailerwindow.xml
                # self.show()

                # Our event listeners will stop the player, as appropriate.

<<<<<<< HEAD
                local_logger.debug(u'wait for not playing 1')
                self.get_player().waitForIsNotPlayingVideo()

                self._source = self._trailer.get(Movie.SOURCE)
                show_movie_details = (Settings.get_time_to_display_detail_info() > 0)
                show_trailer_title = Settings.get_show_trailer_title()
                if not video_is_curtain:
                    self._viewed_playlist.record_played_trailer(self._trailer)

                if self._source == Movie.FOLDER_SOURCE:
                    show_movie_details = False

                if video_is_curtain:
                    show_movie_details = False
                    show_trailer_title = False

                local_logger.debug(u'checking play_state 1')
                if self.is_random_trailers_play_state():
                    local_logger.debug(u'breaking due to play_state 1 movie:',
                                       self._trailer[Movie.TITLE])
                    break

                # This will block if showing Movie Details
                local_logger.debug(u'about to show_movie_info movie:', self._trailer[Movie.TITLE])
                self.show_movie_info(show_detail_info=show_movie_details,
                                     show_brief_info=show_trailer_title)
                local_logger.debug(u'finished show_movie_info, movie:',  self._trailer[Movie.TITLE])
=======
                self.getPlayer().waitForIsNotPlayingVideo()

                self._source = self._trailer.get(Movie.SOURCE)
                showMovieDetails = (Settings.getTimeToDisplayDetailInfo() > 0)
                showTrailerTitle = Settings.getShowTrailerTitle()
                if not videoIsCurtain:
                    self._viewedPlaylist.recordPlayedTrailer(self._trailer)

                if self._source == Movie.FOLDER_SOURCE:
                    showMovieDetails = False

                if videoIsCurtain:
                    showMovieDetails = False
                    showTrailerTitle = False

                if self.isRandomTrailersPlayState():
                    break

                # This will block if showing Movie Details
                self.showMovieInfo(showDetailInfo=showMovieDetails,
                                   showBriefInfo=showTrailerTitle)
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

                # Play Trailer
                # TODO: change to asynchronous so that it can occur while
                # showing details

<<<<<<< HEAD
                local_logger.debug(u'checking play_state 2 movie:',
                                   self._trailer[Movie.TITLE])
                if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                    local_logger.debug(u'breaking due to play_state 2 movie:', self._trailer[Movie.TITLE])
                    break

                local_logger.debug(u'About to play:',
                                  self._trailer.get(Movie.TRAILER))

                self.set_visibility(video_window=True, info=False,
                                    brief_info=show_trailer_title,
                                    notification=False)
                local_logger.debug(u'about to play movie:', self._trailer[Movie.TITLE])
                if self._trailer.get(Movie.NORMALIZED_TRAILER) is not None:
                    self.get_player().play_trailer(self._trailer[
                        Movie.NORMALIZED_TRAILER].encode(u'utf-8'), self._trailer)
                else:
                    self.get_player().play_trailer(
                        self._trailer[Movie.TRAILER].encode(u'utf-8'),
                        self._trailer)
                local_logger.debug(u'started play_trailer:', self._trailer[Movie.TITLE])
                self.setFocus(self._dummy_control)

                # Again, we rely on our listeners to interrupt, as
                # appropriate. Trailer/Movie should be about to be played or playing.

                try:
                    # if show_movie_details:
                    #     self.hide_detail_info()

                    local_logger.debug(u'checking play_state 3 movie:', self._trailer[Movie.TITLE])

                    if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                        local_logger.debug(u'breaking at play_state 3 movie:', self._trailer[Movie.TITLE])
                        break

                    local_logger.debug(u'wait_for_is_playing_video 2 movie:', self._trailer[Movie.TITLE])
                    if not self.get_player().waitForIsPlayingVideo(timeout=5.0):
                        local_logger.debug(u'Timed out Waiting for Player.')

                    local_logger.debug(u'checking play_state 4 movie:', self._trailer[Movie.TITLE])
                    if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                        local_logger.debug(u'breaking at play_state 4 movie:', self._trailer[Movie.TITLE])
                        break

                    # Now that the trailer has started, see if it will run too long so
                    # that we need to set up to kill it playing.

                    trailer_total_time = self.get_player().getTotalTime()
                    max_play_time = Settings.get_max_trailer_length()
                    if trailer_total_time > max_play_time:
                        local_logger.debug(u'Killing long trailer:', self._trailer[Movie.TITLE])
                        self.start_long_trailer_killer(max_play_time)
                except (AbortException, ShutdownException):
                    raise sys.exc_info()
                except (Exception) as e:
                    local_logger.log_exception()
=======
                if self.isRandomTrailersPlayState(minimumExitState=DialogState.USER_REQUESTED_EXIT):
                    break

                localLogger.debug(u'About to play:',
                                  self._trailer.get(Movie.TRAILER))

                self.setVisibility(videoWindow=True, info=False,
                                   briefInfo=showTrailerTitle,
                                   notification=False)
                if self._trailer.get(Movie.NORMALIZED_TRAILER) is not None:
                    self.getPlayer().playTrailer(self._trailer[
                        Movie.NORMALIZED_TRAILER].encode(u'utf-8'), self._trailer)
                else:
                    self.getPlayer().playTrailer(
                        self._trailer[Movie.TRAILER].encode(u'utf-8'),
                        self._trailer)

                self.setFocus(self._dummyControl)

                # Again, we rely on our listeners to interrupt, as
                # appropriate

                if self.isRandomTrailersPlayState(minimumExitState=DialogState.USER_REQUESTED_EXIT):
                    break

                try:
                    # if showMovieDetails:
                    #     self.hideDetailInfo()

                    if self.isRandomTrailersPlayState(minimumExitState=DialogState.USER_REQUESTED_EXIT):
                        break

                    if not self.getPlayer().waitForIsPlayingVideo(timeout=5.0):
                        localLogger.debug(u'Timed out Waiting for Player.')

                    if self.isRandomTrailersPlayState(minimumExitState=DialogState.USER_REQUESTED_EXIT):
                        break

                    trailerTotalTime = self.getPlayer().getTotalTime()
                    maxPlayTime = Settings.getMaxTrailerLength()
                    if trailerTotalTime > maxPlayTime:
                        self.startLongTrailerKiller(maxPlayTime)
                except (AbortException, ShutdownException):
                    raise sys.exc_info()
                except (Exception) as e:
                    localLogger.logException()
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

                # Again, we rely on our listeners to  stop the player, as
                # appropriate

<<<<<<< HEAD
                self.get_player().waitForIsNotPlayingVideo()
                local_logger.debug(u'checking play_state 5 movie:', self._trailer[Movie.TITLE])
                if self.is_random_trailers_play_state(minimum_exit_state=DialogState.USER_REQUESTED_EXIT):
                    local_logger.debug(u'breaking at play_state 5 movie:', self._trailer[Movie.TITLE])
                    break

                self.cancel_long_playing_trailer_killer()
=======
                self.getPlayer().waitForIsNotPlayingVideo()
                self.cancelLongPlayingTrailerKiller()
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

                # Again, we rely on our listeners to  stop this display, as
                # appropriate

<<<<<<< HEAD
                self.set_visibility(video_window=False, info=False, brief_info=False,
                                    notification=False)
                # if Settings.get_show_trailer_title():
                #    local_logger.debug(u'About to Hide Brief Info')
                #    self.set_visibility(videoWindow=False, info=None, briefInfo=False)

                #    self.setBriefInfoVisibility(False)

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
                local_logger.error(u'There will be no trailers to play')
                self.notification(self._messages.get_msg(
                    Messages.NO_TRAILERS_TO_PLAY))
                self.set_random_trailers_play_state(
                    DialogState.NO_TRAILERS_TO_PLAY)
            local_logger.debug(u'out of inner play loop movie:', self._trailer[Movie.TITLE])

            if Settings.get_show_curtains():
                self._movie_manager.play_curtain_next(MovieManager.CLOSE_CURTAIN)

                _, curtain = self._movie_manager.get_next_trailer()
                self.set_visibility(video_window=True, info=False, brief_info=False,
                                    notification=False)
                self.get_player().play_trailer(curtain[Movie.TRAILER].encode(u'utf-8'),
                                               curtain)
                if not self.get_player().waitForIsPlayingVideo(timeout=5.0):
                    local_logger.debug(u'Timed out Waiting for Player.')
                self.get_player().waitForIsNotPlayingVideo()

            local_logger.debug(u'Completed everything except play_movie, if there is one')
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            local_logger.log_exception(e)

        try:
            local_logger.debug(u'Checking to see if there is a movie to play:',
                               self._trailer[Movie.TITLE])
            if self.is_random_trailers_play_state(DialogState.START_MOVIE_AND_EXIT):
                local_logger.debug(u'about to play movie:', self._queued_movie)
                self.set_visibility(video_window=True, info=False, brief_info=False,
                                    notification=False)
                self.play_movie(self._queued_movie)

        except (AbortException, ShutdownException):
            local_logger.debug(u'Received shutdown or abort')
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
=======
                self.setVisibility(videoWindow=False, info=False, briefInfo=False,
                                   notification=False)
                # if Settings.getShowTrailerTitle():
                #    localLogger.debug(u'About to Hide Brief Info')
                #    self.setVisibility(videoWindow=False, info=None, briefInfo=False)

                #    self.setBriefInfoVisibility(False)

                if (limitTrailersToPlay and not videoIsCurtain):
                    numberOfTrailersToPlay -= 1
                    if numberOfTrailersToPlay < 1:
                        if Settings.isGroupTrailers():
                            self.setRandomTrailersPlayState(
                                DialogState.GROUP_QUOTA_REACHED)
                        else:
                            self.setRandomTrailersPlayState(
                                DialogState.QUOTA_REACHED)

            if self._trailer is None:
                localLogger.error(u'There will be no trailers to play')
                self.notification(self._messages.getMsg(
                    Messages.NO_TRAILERS_TO_PLAY))
                self.setRandomTrailersPlayState(
                    DialogState.NO_TRAILERS_TO_PLAY)

            if Settings.getShowCurtains():
                self._playCloseCurtainNext = True
                _, curtain = self.getNextTrailer()
                self.setVisibility(videoWindow=True, info=False, briefInfo=False,
                                   notification=False)
                self.getPlayer().playTrailer(curtain[Movie.TRAILER].encode(u'utf-8'),
                                             curtain)
                if not self.getPlayer().waitForIsPlayingVideo(timeout=5.0):
                    localLogger.debug(u'Timed out Waiting for Player.')
                self.getPlayer().waitForIsNotPlayingVideo()

        except (AbortException, ShutdownException):
            pass
        except (Exception) as e:
            localLogger.logException(e)

        try:
            if self.isRandomTrailersPlayState(DialogState.START_MOVIE_AND_EXIT):
                self.setVisibility(videoWindow=True, info=False, briefInfo=False,
                                   notification=False)
                self.playMovie(self._queuedMovie)

        except (AbortException, ShutdownException):
            localLogger.debug(u'Received shutdown or abort')
        except (Exception) as e:
            localLogger.logException(e)

    def getPlayer(self):
        return self._playerContainer.getPlayer()

    def getNextTrailer(self):
        if self._playOpenCurtainNext:
            status = FrontendBridge.OK
            trailer = {Movie.SOURCE: u'curtain',
                       Movie.TITLE: u'openCurtain',
                       Movie.TRAILER: Settings.getOpenCurtainPath()}
            self._playOpenCurtainNext = False
        elif self._playCloseCurtainNext:
            status = FrontendBridge.OK
            trailer = {Movie.SOURCE: u'curtain',
                       Movie.TITLE: u'closeCurtain',
                       Movie.TRAILER: Settings.getCloseCurtainPath()}
            self._playCloseCurtainNext = False
        else:
            status, trailer = self.frontEndBridge.getNextTrailer()

        return status, trailer

    def isRandomTrailersPlayState(self, minimumExitState=DialogState.GROUP_QUOTA_REACHED,
                                  exactMatch=False, throwExceptionOnShutdown=True):
        monitor = Monitor.getInstance()
        if monitor is None or monitor.isShutdownRequested():
            self._dialogState = DialogState.SHUTDOWN

        if throwExceptionOnShutdown:
            monitor.throwExceptionIfShutdownRequested()

        if exactMatch:
            match = self._dialogState == minimumExitState
        else:
            match = self._dialogState >= minimumExitState
        return match

    def showMovieInfo(self, showDetailInfo=False, showBriefInfo=False):
        # self.setBriefInfoVisibility(False)
        if showDetailInfo:
            self.showDetailedInfo()
        else:
            self.hideDetailInfo()
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        #
        # You can have both showMovieDetails (movie details screen
        # shown prior to playing trailer) as well as the
        # simple ShowTrailerTitle while the trailer is playing.
        #
<<<<<<< HEAD
        if show_brief_info:
            title = self.get_title_string(self._trailer)
            self.get_title_control().setLabel(title)

        self.set_visibility(video_window=False, info=True, brief_info=show_brief_info,
                            notification=False)

    # def setBriefInfoVisibility(self, visible):
    #    local_logger = self._logger.get_method_logger(u'setBriefInfoVisibility')
    #    local_logger.debug(u'visible:', visible)
    #    # self.get_title_control().setVisible(visible)
    #    self.set_visibility(videoWindow=False, info=False, briefInfo=visible)

    def notification(self, message):
        # TODO: implement
        local_logger = self._logger.get_method_logger(u'notification')

        try:
            local_logger.debug(u'message:', message)

            #Notification(header,message[,time,image])
            xbmc.executebuiltin(u'Notification("bozo",' + message + u', 1000)')

            self.get_notification_control(message)
            self.set_visibility(notification=True)
            self._notification_killer = threading.Timer(self._notification_timeout,
                                                        self.set_visibility,
                                                        kwargs={u'notification': False})
            self._notification_killer.setName(u'notification_killer')
            self._notification_killer.start()

        except (Exception) as e:
            local_logger.log_exception(e)

        return

    @log_entry_exit
    def show_detailed_info(self, from_user_request=False):
        local_logger = self._logger.get_method_logger(u'show_detailed_info')

        if self._source != Movie.FOLDER_SOURCE:
            local_logger.debug(u'about to show_detailed_info')
            display_seconds = Settings.get_time_to_display_detail_info()
            if from_user_request:
                display_seconds = 0
            else:  # TODO: I suspect the pause below belongs in the if from_user_request
                if self.get_player() is not None:
                    self.get_player().pausePlay()

            self.update_detail_view()
            self.show_detail_info(self._trailer, display_seconds)

    def show_detail_info(self, trailer, display_seconds=0):
        local_logger = self._logger.get_method_logger(u'show_detail_info')
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)
        self.set_visibility(video_window=False, info=True, brief_info=False,
                            notification=False)

        if display_seconds == 0:
            # One year
            display_seconds = 365 * 24 * 60 * 60
        self._show_details_event.clear()  # In case it was set
        self._show_details_event.wait(display_seconds)
        self._show_details_event.clear()  # In case it was set
        # self.hide_detail_info()
        self._show_details_event.set()  # Force show_detail_info to unblock
        self.set_visibility(video_window=False, info=False, brief_info=False,
                            notification=False)

    def hide_detail_info(self, reason=u''):
        local_logger = self._logger.get_method_logger(u'hide_detail_info')
        local_logger.enter()
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)
        self._show_details_event.set()  # Force show_detail_info to unblock
        self.set_visibility(info=False)

    def set_visibility(self, video_window=None, info=None, brief_info=None,
                       notification=None):
=======
        if showBriefInfo:
            title = self.getTitleString(self._trailer)
            self.getTitleControl().setLabel(title)

        self.setVisibility(videoWindow=False, info=True, briefInfo=showBriefInfo,
                           notification=False)

    # def setBriefInfoVisibility(self, visible):
    #    localLogger = self._logger.getMethodLogger(u'setBriefInfoVisibility')
    #    localLogger.debug(u'visible:', visible)
    #    # self.getTitleControl().setVisible(visible)
    #    self.setVisibility(videoWindow=False, info=False, briefInfo=visible)

    def notification(self, message):
        # TODO: implement
        localLogger = self._logger.getMethodLogger(u'notification')

        try:
            localLogger.debug(u'message:', message)

            # Notification(header,message[,time,image])
            #xbmc.executebuiltin(u'Notification("bozo",' + message + u', 1000)')

            self.getNotificationControl(message)
            self.setVisibility(notification=True)
            self._notificationKiller = threading.Timer(self._notificationTimeout,
                                                       self.setVisibility,
                                                       kwargs={u'notification': False})
            self._notificationKiller.setName(u'NotificationKiller')
            self._notificationKiller.start()

        except (Exception) as e:
            localLogger.logException(e)

        return

    @logEntryExit
    def showDetailedInfo(self, fromUserRequest=False):
        localLogger = self._logger.getMethodLogger(u'showDetailedInfo')

        if self._source != Movie.FOLDER_SOURCE:
            localLogger.debug(u'about to showDetailedInfo')
            displaySeconds = Settings.getTimeToDisplayDetailInfo()
            if fromUserRequest:
                displaySeconds = 0
            else:  # TODO: I suspect the pause below belongs in the if fromUserRequest
                if self.getPlayer() is not None:
                    self.getPlayer().pausePlay()

            self.updateDetailView()
            self.showDetailInfo(self._trailer, displaySeconds)

    def showDetailInfo(self, trailer, displaySeconds=0):
        localLogger = self._logger.getMethodLogger(u'showDetailInfo')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        self.setVisibility(videoWindow=False, info=True, briefInfo=False,
                           notification=False)

        if displaySeconds == 0:
            # One year
            displaySeconds = 365 * 24 * 60 * 60
        self._showDetailsEvent.clear()  # In case it was set
        self._showDetailsEvent.wait(displaySeconds)
        self._showDetailsEvent.clear()  # In case it was set
        # self.hideDetailInfo()
        self._showDetailsEvent.set()  # Force showDetailInfo to unblock
        self.setVisibility(videoWindow=False, info=False, briefInfo=False,
                           notification=False)

    def hideDetailInfo(self, reason=u''):
        localLogger = self._logger.getMethodLogger(u'hideDetailInfo')
        localLogger.enter()
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        self._showDetailsEvent.set()  # Force showDetailInfo to unblock
        self.setVisibility(info=False)

    def setVisibility(self, videoWindow=None, info=None, briefInfo=None,
                      notification=None):
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        # type: (Union[bool, None], Union[bool, None], Union[bool, None], Union[bool, None]) -> None
        """
            Controls the visible elements of TrailerDialog

<<<<<<< HEAD
        :param video_window:
        :param info:
        :param brief_info:
        :param notification:
        :return:
        """
        local_logger = self._logger.get_method_logger(u'set_visibility')

        commands = []
        if video_window is not None:
            if video_window:
                video_command = "Skin.SetBool(Video)"
            else:
                video_command = "Skin.Reset(Video)"
            commands.append(video_command)
        if info is not None:
            if info:
                info_command = "Skin.SetBool(Info)"
            else:
                info_command = "Skin.Reset(Info)"
            commands.append(info_command)

        for command in commands:
            local_logger.debug(command)
            xbmc.executebuiltin(command)

        local_logger.debug(u'BriefInfo:', brief_info)
        if brief_info is not None:
            self._saved_brief_info_visibility = brief_info
            if not self.get_notification_control().isVisible():
                self.get_title_control().setVisible(brief_info)

        local_logger.debug(u'notification:', notification)
        if notification is not None:
            if self._notification_killer is not None:
                self._notification_killer.cancel()
                self._notification_killer = None
            if notification:
                if self._saved_brief_info_visibility:
                    self.get_title_control().setVisible(False)
                self.get_notification_control().setVisible(True)
            else:
                self.get_notification_control().setVisible(False)
                if self._saved_brief_info_visibility:
                    self.get_title_control().setVisible(True)

    def update_detail_view(self):
        local_logger = self._logger.get_method_logger(u'update_detail_view')
        try:
            Monitor.get_instance().throw_exception_if_shutdown_requested()

            local_logger.enter()
            local_logger.debug(Trace.TRACE)

            control = self.getControl(38002) # type: xbmcgui.ControlImage
=======
        :param videoWindow:
        :param info:
        :param briefInfo:
        :param notification:
        :return:
        """
        localLogger = self._logger.getMethodLogger(u'setVisibility')

        commands = []
        if videoWindow is not None:
            if videoWindow:
                videoCommand = "Skin.SetBool(Video)"
            else:
                videoCommand = "Skin.Reset(Video)"
            commands.append(videoCommand)
        if info is not None:
            if info:
                infoCommand = "Skin.SetBool(Info)"
            else:
                infoCommand = "Skin.Reset(Info)"
            commands.append(infoCommand)

        for command in commands:
            localLogger.debug(command)
            xbmc.executebuiltin(command)

        localLogger.debug(u'BriefInfo:', briefInfo)
        if briefInfo is not None:
            self._savedBriefInfoVisibility = briefInfo
            if not self.getNotificationControl().isVisible():
                self.getTitleControl().setVisible(briefInfo)

        localLogger.debug(u'notification:', notification)
        if notification is not None:
            if self._notificationKiller is not None:
                self._notificationKiller.cancel()
                self._notificationkiller = None
            if notification:
                if self._savedBriefInfoVisibility:
                    self.getTitleControl().setVisible(False)
                self.getNotificationControl().setVisible(True)
            else:
                self.getNotificationControl().setVisible(False)
                if self._savedBriefInfoVisibility:
                    self.getTitleControl().setVisible(True)

    def updateDetailView(self):
        try:
            Monitor.getInstance().throwExceptionIfShutdownRequested()

            localLogger = self._logger.getMethodLogger(u'updateDetailView')
            localLogger.enter()
            localLogger.debug(Trace.TRACE)

            control = self.getControl(38002)
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
            thumbnail = self._trailer[Movie.THUMBNAIL]
            control.setImage(thumbnail)

            self.getControl(38004).setImage(self._trailer[Movie.FANART])

<<<<<<< HEAD
            title_string = self.get_title_string(self._trailer)

            title = self.getControl(38003)
            title.setLabel(title_string)
            # title.setAnimations(
            #    [('Hidden', 'effect=fade end=0 time=1000')])

            movie_directors = self._trailer[Movie.DETAIL_DIRECTORS]
            self.getControl(38005).setLabel(movie_directors)

            movie_actors = self._trailer[Movie.DETAIL_ACTORS]
            self.getControl(38006).setLabel(movie_actors)

            movie_directors = self._trailer[Movie.DETAIL_DIRECTORS]
            self.getControl(38005).setLabel(movie_directors)

            movie_writers = self._trailer[Movie.DETAIL_WRITERS]
            self.getControl(38007).setLabel(movie_writers)
=======
            titleString = self.getTitleString(self._trailer)

            title = self.getControl(38003)
            title.setLabel(titleString)
            # title.setAnimations(
            #    [('Hidden', 'effect=fade end=0 time=1000')])

            movieDirectors = self._trailer[Movie.DETAIL_DIRECTORS]
            self.getControl(38005).setLabel(movieDirectors)

            movieActors = self._trailer[Movie.DETAIL_ACTORS]
            self.getControl(38006).setLabel(movieActors)

            movieDirectors = self._trailer[Movie.DETAIL_DIRECTORS]
            self.getControl(38005).setLabel(movieDirectors)

            movieWriters = self._trailer[Movie.DETAIL_WRITERS]
            self.getControl(38007).setLabel(movieWriters)
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

            plot = self._trailer[Movie.PLOT]
            self.getControl(38009).setText(plot)

<<<<<<< HEAD
            movie_studios = self._trailer[Movie.DETAIL_STUDIOS]
            self.getControl(38010).setLabel(movie_studios)
=======
            movieStudios = self._trailer[Movie.DETAIL_STUDIOS]
            self.getControl(38010).setLabel(movieStudios)
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

            label = (self._trailer[Movie.DETAIL_RUNTIME] + u' - ' +
                     self._trailer[Movie.DETAIL_GENRES])
            self.getControl(38011).setLabel(label)

<<<<<<< HEAD
            image_rating = self._trailer[Movie.DETAIL_RATING_IMAGE]
            self.getControl(38013).setImage(image_rating)

            local_logger.exit()
=======
            imgRating = self._trailer[Movie.DETAIL_RATING_IMAGE]
            self.getControl(38013).setImage(imgRating)

            localLogger.exit()
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
<<<<<<< HEAD
            local_logger.log_exception(e)
=======
            localLogger.logException(e)
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        finally:
            pass

    def doModal(self):
<<<<<<< HEAD
        local_logger = self._logger.get_method_logger(u'doModal')
        local_logger.enter()
=======
        localLogger = self._logger.getMethodLogger(u'doModal')
        localLogger.enter()
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

        # In case playing was paused due to screensaver deactivated
        # and now it is being reactivated.

        # self.unBlockPlayingTrailers()
        super().doModal()
<<<<<<< HEAD
        local_logger.exit()
        return self._dialog_state

    def show(self):
        local_logger = self._logger.get_method_logger(u'show')
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)
        super().show()

    def close(self):
        local_logger = self._logger.get_method_logger(u'close')
        local_logger.trace(trace=Trace.TRACE_SCREENSAVER)
        super().close()

    def set_random_trailers_play_state(self, dialog_state):
=======
        localLogger.exit()
        return self._dialogState

    def show(self):
        localLogger = self._logger.getMethodLogger(u'show')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        super().show()

    def close(self):
        localLogger = self._logger.getMethodLogger(u'close')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        super().close()

    def setRandomTrailersPlayState(self, dialogState):
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        # type: (int) -> None
        # TODO: Change to use named int type
        """

<<<<<<< HEAD
        :param dialog_state:
        :return:
        """
        local_logger = self._logger.get_method_logger(
            u'set_random_trailers_play_state')
        local_logger.trace(u'state:', DialogState.getLabel(dialog_state),
                           trace=Trace.TRACE_SCREENSAVER)

        if dialog_state >= DialogState.SHUTDOWN_CUSTOM_PLAYER:
            self.get_player().setCallBacks(on_show_info=None)
            self.get_player().disableAdvancedMonitoring()
            self._player_container.use_dummy_player()

        if dialog_state >= DialogState.USER_REQUESTED_EXIT:
            # Stop playing trailer.

            # Just in case we are paused
            self.get_player().resumePlay()
            self.kill_long_playing_trailer(inform_user=False)

        # if dialog_state >= DialogState.STARTED_PLAYING_MOVIE:
=======
        :param dialogState:
        :return:
        """
        localLogger = self._logger.getMethodLogger(
            u'setRandomTrailersPlayState')
        localLogger.trace(u'state:', DialogState.getLabel(dialogState),
                          trace=Trace.TRACE_SCREENSAVER)
        # self.onScreensaverDeactivated()
        #
        # self._exitDialog = True
        # self.killLongPlayingTrailer(informUser=False)
        # self.showMovieInfo(showDetailInfo=False, showBriefInfo=False)
        # self._waitEvent.set(ReasonEvent.RUN_STATE_CHANGE)

        if dialogState >= DialogState.SHUTDOWN_CUSTOM_PLAYER:
            self.getPlayer().setCallBacks(onShowInfo=None)
            self.getPlayer().disableAdvancedMonitoring()
            self._playerContainer.useDummyPlayer()

        if dialogState >= DialogState.USER_REQUESTED_EXIT:
            # Stop playing trailer.

            # Just in case we are paused
            self.getPlayer().resumePlay()
            self.killLongPlayingTrailer(informUser=False)

        # if dialogState >= DialogState.STARTED_PLAYING_MOVIE:
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        #    self.shutdown()

        # Multiple groups can be played before exiting. Allow
        # them to be reset back to normal.

<<<<<<< HEAD
        if self._dialog_state == DialogState.GROUP_QUOTA_REACHED:
            self._dialog_state = dialog_state

        if dialog_state > self._dialog_state:
            self._dialog_state = dialog_state
        self._wait_event.set(ReasonEvent.RUN_STATE_CHANGE)

    def on_shutdown_event(self):
=======
        if self._dialogState == DialogState.GROUP_QUOTA_REACHED:
            self._dialogState = dialogState

        if dialogState > self._dialogState:
            self._dialogState = dialogState
        self._waitEvent.set(ReasonEvent.RUN_STATE_CHANGE)

    def onShutdownEvent(self):
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        # type: () -> None
        """

        :return:
        """
<<<<<<< HEAD
        local_logger = self._logger.get_method_logger(u'on_shutdown_event')
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
            u'start_long_trailer_killer')
        local_logger.trace(u'waiting on lock', trace=Trace.TRACE_UI_CONTROLLER)
        with self._lock:
            local_logger.trace(u'got lock, max_play_time:',
                               max_play_time,
                               trace=Trace.TRACE_UI_CONTROLLER)
            self._long_trailer_killer = None
            if not self.is_random_trailers_play_state(DialogState.USER_REQUESTED_EXIT):
                if max_play_time > Constants.MAX_PLAY_TIME_WARNING_TIME + 2:
                    max_play_time -= Constants.MAX_PLAY_TIME_WARNING_TIME
                    local_logger.trace(u'adjusted max_play_time:', max_play_time,
                                       trace=Trace.TRACE_UI_CONTROLLER)
                self._long_trailer_killer = threading.Timer(max_play_time,
                                                            self.kill_long_playing_trailer)
                self._long_trailer_killer.setName(u'TrailerKiller')
                self._long_trailer_killer.start()

    def kill_long_playing_trailer(self, inform_user=True):
        # type: (bool) -> None
        """

        :param inform_user:
        :return:
        """
        local_logger = self._logger.get_method_logger(
            u'kill_long_playing_trailer')
        try:
            local_logger.enter()
            local_logger.trace(u'Now Killing',
                              trace=Trace.TRACE_UI_CONTROLLER)

            if inform_user:
                self.get_title_control().setLabel(self._messages.get_msg(
                    Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME))
                self.set_visibility(brief_info=True, notification=False)
            self.get_player().stop()

            with self._lock:
                self._long_trailer_killer = None
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            Logger.log_exception(e)

        local_logger.trace(u'exit', trace=Trace.TRACE_SCREENSAVER)

    def cancel_long_playing_trailer_killer(self):
=======
        localLogger = self._logger.getMethodLogger(u'onShutdownEvent')
        localLogger.enter()
        self.setRandomTrailersPlayState(DialogState.SHUTDOWN)
        self._shutdown = True
        self._waitEvent.set(ReasonEvent.SHUTDOWN)

    def onAbortEvent(self):
        # type: () -> None
        """

        :return:
        """
        localLogger = self._logger.getMethodLogger(u'onAbortEvent')
        localLogger.enter()
        self.setRandomTrailersPlayState(DialogState.SHUTDOWN)
        self._abort = True
        self._waitEvent.set(ReasonEvent.KODI_ABORT)

    # TODO: put this in own class

    def startLongTrailerKiller(self, maxPlayTime):
        # type: (Union[int, float]) -> None
        """

        :param maxPlayTime:
        :return:
        """
        localLogger = self._logger.getMethodLogger(
            u'startLongTrailerKiller')
        localLogger.trace(u'waiting on lock', trace=Trace.TRACE_UI_CONTROLLER)
        with self._lock:
            localLogger.trace(u'got lock, maxPlayTime:',
                              maxPlayTime,
                              trace=Trace.TRACE_UI_CONTROLLER)
            self._longTrailerKiller = None
            if not self.isRandomTrailersPlayState(DialogState.USER_REQUESTED_EXIT):
                if maxPlayTime > Constants.MAX_PLAY_TIME_WARNING_TIME + 2:
                    maxPlayTime -= Constants.MAX_PLAY_TIME_WARNING_TIME
                    localLogger.trace(u'adjusted maxPlayTime:',  maxPlayTime,
                                      trace=Trace.TRACE_UI_CONTROLLER)
                self._longTrailerKiller = threading.Timer(maxPlayTime,
                                                          self.killLongPlayingTrailer)
                self._longTrailerKiller.setName(u'TrailerKiller')
                self._longTrailerKiller.start()

    def killLongPlayingTrailer(self, informUser=True):
        # type: (bool) -> None
        """

        :param informUser:
        :return:
        """
        localLogger = self._logger.getMethodLogger(
            u'killLongPlayingTrailer')
        try:
            localLogger.enter()
            localLogger.trace(u'Now Killing',
                              trace=Trace.TRACE_UI_CONTROLLER)

            if informUser:
                self.getTitleControl().setLabel(self._messages.getMsg(
                    Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME))
                self.setVisibility(briefInfo=True, notification=False)
            self.getPlayer().stop()

            with self._lock:
                self._longTrailerKiller = None
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            Logger.logException(e)

        localLogger.trace(u'exit', trace=Trace.TRACE_SCREENSAVER)

    def cancelLongPlayingTrailerKiller(self):
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        # type: () -> None
        """

        :return:
        """
<<<<<<< HEAD
        local_logger = self._logger.get_method_logger(
            u'cancel_long_playing_trailer_killer')
        local_logger.trace(u'enter, waiting on lock',
                          trace=[Trace.TRACE_SCREENSAVER,
                                 Trace.TRACE_UI_CONTROLLER])
        with self._lock:
            if self._long_trailer_killer is not None:
                self._long_trailer_killer.cancel()

    def play_next_trailer(self):
=======
        localLogger = self._logger.getMethodLogger(
            u'cancelLongPlayingTrailerKiller')
        localLogger.trace(u'enter, waiting on lock',
                          trace=[Trace.TRACE_SCREENSAVER,
                                 Trace.TRACE_UI_CONTROLLER])
        with self._lock:
            if self._longTrailerKiller is not None:
                self._longTrailerKiller.cancel()

    def playNextTrailer(self):
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        # type: () -> None
        """

        :return:
        """
<<<<<<< HEAD
        local_logger = self._logger.get_method_logger(u'play_next_trailer')
        local_logger.enter()
=======
        localLogger = self._logger.getMethodLogger(u'playNextTrailer')
        localLogger.enter()
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

        # If idle due to wait between trailer groups, then interrupt
        # and play next trailer.

<<<<<<< HEAD
        if self.is_random_trailers_play_state(DialogState.GROUP_QUOTA_REACHED,
                                              exact_match=True):
            # Wake up wait in between groups
            self.set_random_trailers_play_state(DialogState.NORMAL)

        self.cancel_long_playing_trailer_killer()
        self.hide_detail_info()
        if self.get_player() is not None:
            self.get_player().stop()
        local_logger.trace(u'Finished playing old trailer',
=======
        if self.isRandomTrailersPlayState(DialogState.GROUP_QUOTA_REACHED,
                                          exactMatch=True):
            # Wake up wait in between groups
            self.setRandomTrailersPlayState(DialogState.NORMAL)

        self.cancelLongPlayingTrailerKiller()
        self.hideDetailInfo()
        if self.getPlayer() is not None:
            self.getPlayer().stop()
        localLogger.trace(u'Finished playing old trailer',
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
                          trace=Trace.TRACE_SCREENSAVER)

    def getFocus(self):
        # type: () -> None
        """

        :return:
        """
<<<<<<< HEAD
        local_logger = self._logger.get_method_logger(u'getFocus')
        local_logger.debug(u'Do not use.')
=======
        localLogger = self._logger.getMethodLogger(u'getFocus')
        localLogger.debug(u'Do not use.')
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        return

    def onAction(self, action):
        # type: (Action) -> None
        """

        :param action:
        :return:

            SHOW_INFO -> Toggle Display custom InfoDialog

            STOP -> Skip to next trailer
            ACTION_MOVE_RIGHT -> Skip to next trailer

<<<<<<< HEAD
            ACTION_MOVE_LEFT -> Play previous trailer

=======
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
            PREVIOUS_MENU -> Exit Random Trailer script
                or stop Screensaver
            NAV_BACK -> Exit Random Trailer Script
                or stop screensaver

            PAUSE -> Toggle Play/Pause playing trailer
            PLAY -> Toggle Play/Pause playing trailer

            ENTER -> Play movie for current trailer (if available)

            REMOTE_0 .. REMOTE_9 -> Record playing movie info to
                        userdata/addon_data/script.video.randomtrailers/<playlist<n>

            ACTION_QUEUE_ITEM -> Add movie to Couch Potato
        """

<<<<<<< HEAD
        local_logger = self._logger.get_method_logger(u'onAction')

        if action.getId() != 107:
            local_logger.trace(u'Action.id:', str(action.getId()),
                              u'Action.button_code:',
                              str(action.getButtonCode()), trace=Trace.TRACE)

        # if not self._screensaver_manager.isAddonActive():
        #    local_logger.exit(u'Addon inActive')
        #    return

        action_mapper = Action.get_instance()
        matches = action_mapper.getKeyIDInfo(action)

        for line in matches:
            local_logger.debug(line)

        action_id = action.getId()
        button_code = action.getButtonCode()

        # These return empty string if not found
        action_key = action_mapper.getActionIDInfo(action)
        remote_button = action_mapper.getRemoteKeyButtonInfo(action)
        remote_key_id = action_mapper.getRemoteKeyIDInfo(action)

        # Returns found button_code, or u'key_' +  action_button
        action_button = action_mapper.getButtonCodeId(action)

        separator = u''
        key = u''
        if action_key != u'':
            key = action_key
            separator = u', '
        if remote_button != u'':
            key = key + separator + remote_button
            separator = u', '
        if remote_key_id != u'':
            key = key + separator + remote_key_id
        if key == u'':
            key = action_button
        if action.getId() != 107:
            local_logger.debug(u'Key found:', key)

        ##################################################################
        if action_id == xbmcgui.ACTION_SHOW_INFO:
            local_logger.debug(key, u'Toggle Show_Info')

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
            local_logger.debug(key, u'Play next trailer at user\'s request')
            self.play_next_trailer()

        ##################################################################

        elif action_id == xbmcgui.ACTION_MOVE_LEFT:
            local_logger.debug(key, u'Play previous trailer at user\'s request')
            self._movie_manager.play_previous_trailer()
            self.play_next_trailer()
=======
        localLogger = self._logger.getMethodLogger(u'onAction')

        if action.getId() != 107:
            localLogger.trace(u'Action.id:', str(action.getId()),
                              u'Action.buttonCode:',
                              str(action.getButtonCode()), trace=Trace.TRACE)

        # if not self._screensaverManager.isAddonActive():
        #    localLogger.exit(u'Addon inActive')
        #    return

        actionMapper = Action.getInstance()
        matches = actionMapper.getKeyIDInfo(action)

        for line in matches:
            localLogger.debug(line)

        actionId = action.getId()
        buttonCode = action.getButtonCode()

        # These return empty string if not found
        actionKey = actionMapper.getActionIDInfo(action)
        remoteButton = actionMapper.getRemoteKeyButtonInfo(action)
        remoteKeyId = actionMapper.getRemoteKeyIDInfo(action)

        # Returns found buttonCode, or u'key_' +  actionButton
        actionButton = actionMapper.getButtonCodeId(action)

        separator = u''
        key = u''
        if actionKey != u'':
            key = actionKey
            separator = u', '
        if remoteButton != u'':
            key = key + separator + remoteButton
            separator = u', '
        if remoteKeyId != u'':
            key = key + separator + remoteKeyId
        if key == u'':
            key = actionButton
        if action.getId() != 107:
            localLogger.debug(u'Key found:', key)

        ##################################################################
        if actionId == xbmcgui.ACTION_SHOW_INFO:
            localLogger.debug(key, u'Toggle Show_Info')

            if not self.isRandomTrailersPlayState(DialogState.NORMAL):
                heading = self._messages.getMsg(Messages.HEADER_IDLE)
                message = self._messages.getMsg(Messages.PLAYER_IDLE)
                self.notification(message)
            elif self.getControl(TrailerDialog.DETAIL_GROUP_CONTROL).isVisible():
                self.hideDetailInfo()
            else:
                self.showDetailedInfo(fromUserRequest=True)

        ##################################################################
        elif (actionId == xbmcgui.ACTION_STOP or actionId == xbmcgui.ACTION_MOVE_RIGHT):
            localLogger.debug(key, u'Play next trailer at user\'s request')
            self.playNextTrailer()
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

        ##################################################################
        #
        # PAUSE/PLAY is handled by native player
        #
<<<<<<< HEAD
        elif action_id == xbmcgui.ACTION_QUEUE_ITEM:
            local_logger.debug(key, u'Queue to couch potato')
            str_couch_potato = 'plugin://plugin.video.couchpotato_manager/movies/add?title=' + \
                self._trailer[Movie.TITLE]
            xbmc.executebuiltin('XBMC.RunPlugin(' + str_couch_potato + ')')

        ##################################################################
        elif (action_id == xbmcgui.ACTION_PREVIOUS_MENU
              or action_id == xbmcgui.ACTION_NAV_BACK):
            local_logger.trace(u'Exit application',
                              trace=Trace.TRACE_SCREENSAVER)
            local_logger.debug(key, u'Exiting RandomTrailers at user request')

            # Ensure we are not blocked

            self.hide_detail_info()
            self.set_random_trailers_play_state(DialogState.USER_REQUESTED_EXIT)

        ##################################################################
        elif (action_id == xbmcgui.ACTION_ENTER
              or action_id == xbmcgui.ACTION_SELECT_ITEM
              or action_id == xbmcgui.ACTION_SHOW_GUI):
            local_logger.debug(key, u'Play Movie')
            movie_file = self._trailer[Movie.FILE]
            local_logger.debug(u'Playing movie for currently playing trailer.',
                              u'movie_file:', movie_file, u'source:',
                              self._trailer[Movie.SOURCE])
            if movie_file is None or movie_file == u'':
                heading = self._messages.get_msg(Messages.HEADING_INFO)
                message = self._messages.get_msg(Messages.NO_MOVIE_TO_PLAY)
                self.notification(message)
            elif not self.is_random_trailers_play_state(DialogState.NORMAL):
                heading = self._messages.get_msg(Messages.HEADER_IDLE)
                message = self._messages.get_msg(Messages.PLAYER_IDLE)
                self.notification(message)
            else:
                self.queue_movie(self._trailer)
=======
        elif actionId == xbmcgui.ACTION_QUEUE_ITEM:
            localLogger.debug(key, u'Queue to couch potato')
            strCouchPotato = 'plugin://plugin.video.couchpotato_manager/movies/add?title=' + \
                self._trailer[Movie.TITLE]
            xbmc.executebuiltin('XBMC.RunPlugin(' + strCouchPotato + ')')

        ##################################################################
        elif (actionId == xbmcgui.ACTION_PREVIOUS_MENU
              or actionId == xbmcgui.ACTION_NAV_BACK):
            localLogger.trace(u'Exit application',
                              trace=Trace.TRACE_SCREENSAVER)
            localLogger.debug(key, u'Exiting RandomTrailers at user request')

            # Ensure we are not blocked

            self.hideDetailInfo()
            self.setRandomTrailersPlayState(DialogState.USER_REQUESTED_EXIT)

        ##################################################################
        elif (actionId == xbmcgui.ACTION_ENTER
              or actionId == xbmcgui.ACTION_SELECT_ITEM
              or actionId == xbmcgui.ACTION_SHOW_GUI):
            localLogger.debug(key, u'Play Movie')
            movieFile = self._trailer[Movie.FILE]
            localLogger.debug(u'Playing movie for currently playing trailer.',
                              u'movieFile:', movieFile, u'source:',
                              self._trailer[Movie.SOURCE])
            if movieFile is None or movieFile == u'':
                heading = self._messages.getMsg(Messages.HEADING_INFO)
                message = self._messages.getMsg(Messages.NO_MOVIE_TO_PLAY)
                self.notification(message)
            elif not self.isRandomTrailersPlayState(DialogState.NORMAL):
                heading = self._messages.getMsg(Messages.HEADER_IDLE)
                message = self._messages.getMsg(Messages.PLAYER_IDLE)
                self.notification(message)
            else:
                self.queueMovie(self._trailer)
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

        ##################################################################
        # From IR remote as well as keyboard
        # Close InfoDialog and resume playing trailer

<<<<<<< HEAD
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

    def get_title_control(self, text=u''):
        local_logger = self._logger.get_method_logger(u'get_title_control')
        if self._title_control is None:
            text_color = u'0xFFFFFFFF'  # White
            shadow_color = u'0x00000000'  # Black
            disabled_color = u'0x0000000'  # Won't matter, screen will be invisible
            x_pos = 20
            y_pos = 20
            width = 680
            height = 20
            font = u'font14'
=======
        elif (actionId == xbmcgui.REMOTE_1 or
              actionId == xbmcgui.REMOTE_2 or
              actionId == xbmcgui.REMOTE_3 or
              actionId == xbmcgui.REMOTE_4 or
              actionId == xbmcgui.REMOTE_5 or
              actionId == xbmcgui.REMOTE_6 or
              actionId == xbmcgui.REMOTE_7 or
              actionId == xbmcgui.REMOTE_8 or
              actionId == xbmcgui.REMOTE_9 or
                actionId == xbmcgui.REMOTE_0):
            localLogger.debug(key)
            self.addToPlaylist(actionId, self._trailer)

    def getTitleControl(self, text=u''):
        localLogger = self._logger.getMethodLogger(u'getTitleControl')
        if self._titleControl is None:
            textColor = u'0xFFFFFFFF'  # White
            shadowColor = u'0x00000000'  # Black
            disabledColor = u'0x0000000'  # Won't matter, screen will be invisible
            xPos = 20
            yPos = 20
            width = 680
            height = 20
            font = u'font13'
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
            XBFONT_LEFT = 0x00000000
            XBFONT_RIGHT = 0x00000001
            XBFONT_CENTER_X = 0x00000002
            XBFONT_CENTER_Y = 0x00000004
            XBFONT_TRUNCATED = 0x00000008
            XBFONT_JUSTIFIED = 0x00000010
            alignment = XBFONT_CENTER_Y
<<<<<<< HEAD
            has_path = False
            angle = 0
            self._title_control = xbmcgui.ControlLabel(x_pos, y_pos, width, height,
                                                       text, font, text_color,
                                                       disabled_color, alignment,
                                                       has_path, angle)
            self.addControl(self._title_control)
            local_logger.exit()

        return self._title_control

    def get_notification_control(self, text=None, timeout=5.0):
=======
            hasPath = False
            angle = 0
            self._titleControl = xbmcgui.ControlLabel(xPos, yPos, width, height,
                                                      text, font, textColor,
                                                      disabledColor, alignment,
                                                      hasPath, angle)
            self.addControl(self._titleControl)
            localLogger.exit()

        return self._titleControl

    def getNotificationControl(self, text=None, timeout=5.0):
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        # type: (TextType, float) -> xbmcgui.ControlLabel
        """

        :param text:
        :return:
        """
<<<<<<< HEAD
        local_logger = self._logger.get_method_logger(u'get_notification_control')
        if self._notification_control is None:
            # text_color = u'0xFFFFFFFF'  # White
            text_color = u'0xFF6666FF'
            shadow_color = u'0x00000000'  # Black
            disabled_color = u'0x0000000'  # Won't matter, screen will be invisible
            x_pos = 20
            y_pos = 20
            width = 680
            height = 20
            font = u'font27'
            XBFONT_CENTER_Y = 0x00000004
            alignment = XBFONT_CENTER_Y
            has_path = False
=======
        localLogger = self._logger.getMethodLogger(u'getNotificationControl')
        if self._notificationControl is None:
            # textColor = u'0xFFFFFFFF'  # White
            textColor = u'0xFF6666FF'
            shadowColor = u'0x00000000'  # Black
            disabledColor = u'0x0000000'  # Won't matter, screen will be invisible
            xPos = 20
            yPos = 20
            width = 680
            height = 20
            font = u'font13'
            XBFONT_CENTER_Y = 0x00000004
            alignment = XBFONT_CENTER_Y
            hasPath = False
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
            angle = 0
            if text is None:
                text = u''
            text = u'[B]' + text + u'[/B]'
<<<<<<< HEAD
            self._notification_control = xbmcgui.ControlLabel(x_pos, y_pos, width, height,
                                                              text, font, text_color,
                                                              disabled_color, alignment,
                                                              has_path, angle)
            self.addControl(self._notification_control)
            self._notification_timeout = timeout
            local_logger.exit()
        else:
            if text is not None:
                text = u'[B]' + text + u'[/B]'
                self._notification_control.setLabel(text)

        return self._notification_control

    _playlist_map = {xbmcgui.REMOTE_1:
                    Playlist.PLAYLIST_PREFIX + u'1' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_2:
                        Playlist.PLAYLIST_PREFIX + u'2' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_3:
                        Playlist.PLAYLIST_PREFIX + u'3' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_4:
                        Playlist.PLAYLIST_PREFIX + u'4' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_5:
                        Playlist.PLAYLIST_PREFIX + u'5' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_6:
                        Playlist.PLAYLIST_PREFIX + u'6' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_7:
                        Playlist.PLAYLIST_PREFIX + u'7' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_8:
                        Playlist.PLAYLIST_PREFIX + u'8' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_9:
                        Playlist.PLAYLIST_PREFIX + u'9' + Playlist.PLAYLIST_SUFFIX,
                     xbmcgui.REMOTE_0:
                        Playlist.PLAYLIST_PREFIX + u'10' + Playlist.PLAYLIST_SUFFIX}

    def add_to_playlist(self, play_list_id, trailer):
        # type: (TextType, dict) -> None
        """

        :param play_list_id:
        :param trailer:
        :return:
        """
        local_logger = self._logger.get_method_logger(u'addToPlayList')

        playlist_file = TrailerDialog._playlist_map.get(play_list_id, None)
        if playlist_file is None:
            local_logger.error(
                u'Invalid playlistId, ignoring request to write to playlist.')
        else:
            Playlist.get_playlist(playlist_file).record_played_trailer(trailer)

    def queue_movie(self, trailer):
=======
            self._notificationControl = xbmcgui.ControlLabel(xPos, yPos, width, height,
                                                             text, font, textColor,
                                                             disabledColor, alignment,
                                                             hasPath, angle)
            self.addControl(self._notificationControl)
            self._notificationTimeout = timeout
            localLogger.exit()
        else:
            if text is not None:
                text = u'[B]' + text + u'[/B]'
                self._notificationControl.setLabel(text)

        return self._notificationControl

    _playlistMap = {xbmcgui.REMOTE_1:
                    Playlist.PLAYLIST_PREFIX + u'1' + Playlist.PLAYLIST_SUFFIX,
                    xbmcgui.REMOTE_2:
                        Playlist.PLAYLIST_PREFIX + u'2' + Playlist.PLAYLIST_SUFFIX,
                    xbmcgui.REMOTE_3:
                        Playlist.PLAYLIST_PREFIX + u'3' + Playlist.PLAYLIST_SUFFIX,
                    xbmcgui.REMOTE_4:
                        Playlist.PLAYLIST_PREFIX + u'4' + Playlist.PLAYLIST_SUFFIX,
                    xbmcgui.REMOTE_5:
                        Playlist.PLAYLIST_PREFIX + u'5' + Playlist.PLAYLIST_SUFFIX,
                    xbmcgui.REMOTE_6:
                        Playlist.PLAYLIST_PREFIX + u'6' + Playlist.PLAYLIST_SUFFIX,
                    xbmcgui.REMOTE_7:
                        Playlist.PLAYLIST_PREFIX + u'7' + Playlist.PLAYLIST_SUFFIX,
                    xbmcgui.REMOTE_8:
                        Playlist.PLAYLIST_PREFIX + u'8' + Playlist.PLAYLIST_SUFFIX,
                    xbmcgui.REMOTE_9:
                        Playlist.PLAYLIST_PREFIX + u'9' + Playlist.PLAYLIST_SUFFIX,
                    xbmcgui.REMOTE_0:
                        Playlist.PLAYLIST_PREFIX + u'10' + Playlist.PLAYLIST_SUFFIX}

    def addToPlaylist(self, playListId, trailer):
        # type: (TextType, dict) -> None
        """

        :param playListId:
        :param trailer:
        :return:
        """
        localLogger = self._logger.getMethodLogger(u'addToPlayList')

        playlistFile = TrailerDialog._playlistMap.get(playListId, None)
        if playlistFile is None:
            localLogger.error(
                u'Invalid playlistId, ignoring request to write to playlist.')
        else:
            Playlist.getPlaylist(playlistFile).recordPlayedTrailer(trailer)

    def queueMovie(self, trailer):
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        # type: (Dict[TextType, TextType]) -> None
        """
            At user request, queue movie to be played after canceling play
            of current trailer, closing curtain and closing customer Player.

        :param trailer:
        :return:
        """
<<<<<<< HEAD
        local_logger = self._logger.get_method_logger(u'queue_movie')
        local_logger.debug(u'Queing movie at user request:',
                          trailer[Movie.TITLE])
        self._queued_movie = trailer
        self.set_random_trailers_play_state(DialogState.START_MOVIE_AND_EXIT)

        # Unblock Detail Info display

        self.hide_detail_info()

    def play_movie(self, trailer):
=======
        # TODO: Supply code
        localLogger = self._logger.getMethodLogger(u'queueMovie')
        localLogger.debug(u'Queing movie at user request:',
                          trailer[Movie.TITLE])
        self._queuedMovie = trailer
        movie = trailer[Movie.FILE]

        # Unblock Detail Info display

        self.hideDetailInfo()
        self.setRandomTrailersPlayState(DialogState.START_MOVIE_AND_EXIT)

    def playMovie(self, trailer):
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        # type: (Dict[TextType, TextType]) -> None
        """
            At user request, start playing movie on normal xbmc.player, after
            disabling the custom player that we use here.

        :param trailer:
        :return:
        """
<<<<<<< HEAD
        local_logger = self._logger.get_method_logger(u'play_movie')

        black_background = BlackBackground.get_instance()
        black_background.set_visibility(opaque=False)
        black_background.close()
        black_background.destroy()

        movie = trailer[Movie.FILE]
        local_logger.debug(u'Playing movie at user request:',
                          trailer[Movie.TITLE],
                          u'path:', movie)

        self.set_random_trailers_play_state(DialogState.SHUTDOWN_CUSTOM_PLAYER)

        #playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        # playlist.add(Settings.get_close_curtain_path())
=======
        localLogger = self._logger.getMethodLogger(u'playMovie')

        blackBackground = BlackBackground.getInstance()
        blackBackground.setVisibility(opaque=False)
        blackBackground.close()
        blackBackground.destroy()

        movie = trailer[Movie.FILE]
        localLogger.debug(u'Playing movie at user request:',
                          trailer[Movie.TITLE],
                          u'path:', movie)

        self.setRandomTrailersPlayState(DialogState.SHUTDOWN_CUSTOM_PLAYER)

        #playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        # playlist.add(Settings.getCloseCurtainPath())
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        # playlist.add(movie)

        xbmc.Player().play(movie)

<<<<<<< HEAD
        monitor = Monitor.get_instance()
        if monitor.is_shutdown_requested() or monitor.abortRequested():
            local_logger.debug(u'SHUTDOWN requested before playing movie!')
        while not monitor.wait_for_shutdown(timeout=0.10):
            if xbmc.Player().isPlayingVideo():
                break

        self.set_random_trailers_play_state(DialogState.STARTED_PLAYING_MOVIE)

        # Time to exit plugin
        monitor.shutdown_requested()
        local_logger.exit(u'Just started player')

    def get_title_string(self, trailer):
=======
        monitor = Monitor.getInstance()
        if monitor.isShutdownRequested() or monitor.abortRequested():
            localLogger.debug(u'SHUTDOWN requested before playing movie!')
        while not monitor.waitForShutdown(timeout=0.10):
            if xbmc.Player().isPlayingVideo():
                break

        localLogger.exit(u'Just started player')

        self.setRandomTrailersPlayState(DialogState.STARTED_PLAYING_MOVIE)

        # Time to exit plugin
        monitor.shutDownRequested()

    def getTitleString(self, trailer):
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        # type: (dict) -> TextType
        """

        :param trailer:
        :return:
        """
        title = u'[B]' + trailer[Movie.DETAIL_TITLE] + u'[/B]'
        title2 = trailer[Movie.DETAIL_TITLE]
        return title

    def shutdown(self):
        # type: () -> None
        """

        :return:
        """
<<<<<<< HEAD
        local_logger = self._logger.get_method_logger(u'shutdown')
        local_logger.enter()
        self.close()
        delete_player = False
        if self.is_random_trailers_play_state() >= DialogState.STARTED_PLAYING_MOVIE:
            delete_player = True

        self._player_container.use_dummy_player(delete_player)
        self._title_control = None
        self._source = None
        self._trailer = None
        self._viewed_playlist = None
=======
        localLogger = self._logger.getMethodLogger(u'shutdown')
        localLogger.enter()
        self.close()
        deletePlayer = False
        if self.isRandomTrailersPlayState() >= DialogState.STARTED_PLAYING_MOVIE:
            deletePlayer = True

        self._playerContainer.useDummyPlayer(deletePlayer)

        self._numberOfTrailersToPlay = 0
        self._titleControl = None
        self._source = None
        self._trailer = None
        self._viewedPlaylist = None
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
