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
from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger, Trace, logEntryExit
from common.messages import Messages
from common.monitor import Monitor
from common.front_end_bridge import FrontendBridge
from action_map import Action
from common.settings import Settings
from player.player_container import PlayerContainer
from frontend.black_background import BlackBackground

from frontend.utils import ReasonEvent, BaseWindow, ScreensaverManager, ScreensaverState

import sys
import threading
from kodi_six import xbmc, xbmcgui


# TODO: Put this in separate file

class DialogState:
    """

    """
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


# noinspection Annotator
class TrailerDialog(xbmcgui.WindowXMLDialog):
    '''
        Note that the underlying 'script-trailer-window.xml' has a "videowindow"
        control. This causes the player to ignore many of the normal keymap actions.
    '''
    DETAIL_GROUP_CONTROL = 38001
    PLAYER_GROUP_CONTROL = 38000

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
        self._thread = None
        self._pause = threading.Event()

        # Used mostly as a timer
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

        # TODO: - Need own thread subclasses to catch unhandled exceptions
        # and to catch abortException & ShutdownException

        if self._thread is None:
            self._thread = threading.Thread(
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
                          str(xbmcgui.getCurrentWindowId()))

        _1080P = 0X0  # 1920 X 1080
        _720p = 0X1  # 1280 X 720
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
                #                  u'trailer:', self._trailer)

                # Are there no trailers to play now, and in the future?

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

                # Screen will be black since both
                # TrailerDialog.PLAYER_GROUP_CONTROL and
                # TrailerDialog.DETAIL_GROUP_CONTROL are, by default,
                # not visible in script-trailerwindow.xml
                # self.show()

                # Our event listeners will stop the player, as appropriate.

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

                # Play Trailer
                # TODO: change to asynchronous so that it can occur while
                # showing details

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

                # Again, we rely on our listeners to  stop the player, as
                # appropriate

                self.getPlayer().waitForIsNotPlayingVideo()
                self.cancelLongPlayingTrailerKiller()

                # Again, we rely on our listeners to  stop this display, as
                # appropriate

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
        #
        # You can have both showMovieDetails (movie details screen
        # shown prior to playing trailer) as well as the
        # simple ShowTrailerTitle while the trailer is playing.
        #
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
        # type: (Union[bool, None], Union[bool, None], Union[bool, None], Union[bool, None]) -> None
        """
            Controls the visible elements of TrailerDialog

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
            thumbnail = self._trailer[Movie.THUMBNAIL]
            control.setImage(thumbnail)

            self.getControl(38004).setImage(self._trailer[Movie.FANART])

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

            plot = self._trailer[Movie.PLOT]
            self.getControl(38009).setText(plot)

            movieStudios = self._trailer[Movie.DETAIL_STUDIOS]
            self.getControl(38010).setLabel(movieStudios)

            label = (self._trailer[Movie.DETAIL_RUNTIME] + u' - ' +
                     self._trailer[Movie.DETAIL_GENRES])
            self.getControl(38011).setLabel(label)

            imgRating = self._trailer[Movie.DETAIL_RATING_IMAGE]
            self.getControl(38013).setImage(imgRating)

            localLogger.exit()

        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)
        finally:
            pass

    def doModal(self):
        localLogger = self._logger.getMethodLogger(u'doModal')
        localLogger.enter()

        # In case playing was paused due to screensaver deactivated
        # and now it is being reactivated.

        # self.unBlockPlayingTrailers()
        super().doModal()
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
        # type: (int) -> None
        # TODO: Change to use named int type
        """

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
        #    self.shutdown()

        # Multiple groups can be played before exiting. Allow
        # them to be reset back to normal.

        if self._dialogState == DialogState.GROUP_QUOTA_REACHED:
            self._dialogState = dialogState

        if dialogState > self._dialogState:
            self._dialogState = dialogState
        self._waitEvent.set(ReasonEvent.RUN_STATE_CHANGE)

    def onShutdownEvent(self):
        # type: () -> None
        """

        :return:
        """
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
        # type: () -> None
        """

        :return:
        """
        localLogger = self._logger.getMethodLogger(
            u'cancelLongPlayingTrailerKiller')
        localLogger.trace(u'enter, waiting on lock',
                          trace=[Trace.TRACE_SCREENSAVER,
                                 Trace.TRACE_UI_CONTROLLER])
        with self._lock:
            if self._longTrailerKiller is not None:
                self._longTrailerKiller.cancel()

    def playNextTrailer(self):
        # type: () -> None
        """

        :return:
        """
        localLogger = self._logger.getMethodLogger(u'playNextTrailer')
        localLogger.enter()

        # If idle due to wait between trailer groups, then interrupt
        # and play next trailer.

        if self.isRandomTrailersPlayState(DialogState.GROUP_QUOTA_REACHED,
                                          exactMatch=True):
            # Wake up wait in between groups
            self.setRandomTrailersPlayState(DialogState.NORMAL)

        self.cancelLongPlayingTrailerKiller()
        self.hideDetailInfo()
        if self.getPlayer() is not None:
            self.getPlayer().stop()
        localLogger.trace(u'Finished playing old trailer',
                          trace=Trace.TRACE_SCREENSAVER)

    def getFocus(self):
        # type: () -> None
        """

        :return:
        """
        localLogger = self._logger.getMethodLogger(u'getFocus')
        localLogger.debug(u'Do not use.')
        return

    def onAction(self, action):
        # type: (Action) -> None
        """

        :param action:
        :return:

            SHOW_INFO -> Toggle Display custom InfoDialog

            STOP -> Skip to next trailer
            ACTION_MOVE_RIGHT -> Skip to next trailer

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

        ##################################################################
        #
        # PAUSE/PLAY is handled by native player
        #
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

        ##################################################################
        # From IR remote as well as keyboard
        # Close InfoDialog and resume playing trailer

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
            XBFONT_LEFT = 0x00000000
            XBFONT_RIGHT = 0x00000001
            XBFONT_CENTER_X = 0x00000002
            XBFONT_CENTER_Y = 0x00000004
            XBFONT_TRUNCATED = 0x00000008
            XBFONT_JUSTIFIED = 0x00000010
            alignment = XBFONT_CENTER_Y
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
        # type: (TextType, float) -> xbmcgui.ControlLabel
        """

        :param text:
        :return:
        """
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
            angle = 0
            if text is None:
                text = u''
            text = u'[B]' + text + u'[/B]'
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
        # type: (Dict[TextType, TextType]) -> None
        """
            At user request, queue movie to be played after canceling play
            of current trailer, closing curtain and closing customer Player.

        :param trailer:
        :return:
        """
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
        # type: (Dict[TextType, TextType]) -> None
        """
            At user request, start playing movie on normal xbmc.player, after
            disabling the custom player that we use here.

        :param trailer:
        :return:
        """
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
        # playlist.add(movie)

        xbmc.Player().play(movie)

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
