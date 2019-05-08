# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: fbacher
'''

from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from typing import Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence
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


from frontend.utils import ReasonEvent, BaseWindow, ScreensaverManager, ScreensaverState


import sys
import threading
from kodi_six import xbmc, xbmcgui


# TODO: Put this in separate file


class TrailerDialog(xbmcgui.WindowXMLDialog):
    '''
        Note that the underlying 'script-trailer-window.xml' has a "videowindow"
        control. This causes the player to ignore many of the normal keymap actions.
    '''
    DETAIL_GROUP_CONTROL = 38001
    PLAYER_GROUP_CONTROL = 38000

    def __init__(self, *args, **kwargs):
        super(TrailerDialog, self).__init__(*args)
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()
        self._exitDialog = False
        self._playerContainer = PlayerContainer.getInstance()

        self.getPlayer().setCallBacks(onShowInfo=self.showDetailedInfo)
        self._numberOfTrailersToPlay = kwargs[u'numberOfTrailersToPlay']
        self._screensaverManager = ScreensaverManager.getInstance()
        self._screensaverManager.registerScreensaverListener(self)
        self._runningAsScreensaver = kwargs.get(u'screensaver', False)
        screenSaverstate = ScreensaverState.getInstance()
        if self._screensaverManager.isLaunchedAsScreensaver():
            screenSaverstate.setState(ScreensaverState.ACTIVATED)

        self._control = None
        self._source = None
        self._trailer = None
        self._lock = threading.RLock()
        self._longTrailerKiller = None
        self._messages = Messages.getInstance()
        self._viewedPlaylist = Playlist.getPlaylist(
            Playlist.VIEWED_PLAYLIST_FILE)
        self._titleControl = None
        self._thread = None
        self._pause = threading.Event()

        # Used mostly as a timer
        self._showDetailsEvent = threading.Event()
        self._waitEvent = ReasonEvent()
        monitor = Monitor.getInstance()
        monitor.registerScreensaverListener(self)
        monitor.registerShutdownListener(self)
        monitor.registerAbortListener(self)

        self._shutdown = False
        self._abort = False
        self._dummyControl = None
        self._showInfoUIThread = None

    def onInit(self):
        localLogger = self._logger.getMethodLogger(u'onInit')
        localLogger.enter()

        if self._dummyControl is None:
            self._dummyControl = xbmcgui.ControlButton(
                0, 0, 1, 1, u'')
            self.addControl(self._dummyControl)
            self._dummyControl.setVisible(True)
        self.setDetailInvisible()

        # TODO: - Need own thread subclasses to catch unhandled exceptions
        # and to catch abortException & ShutdownException

        if self._thread is None:
            self._thread = threading.Thread(
                target=self.playTrailers, name=u'TrailerDialog')
            self._thread.start()

    def playTrailers(self):
        localLogger = self._logger.getMethodLogger(u'playTrailers')

        localLogger.debug(u' WindowID: ' +
                          str(xbmcgui.getCurrentWindowId()))

        _1080P = 0X0  # 1920 X 1080
        _720p = 0X1  # 1280 X 720
        windowHeight = self.getHeight()
        windowWidth = self.getWidth()
        localLogger.debug(u'Window Dimensions: ' + str(windowHeight) +
                          u' H  x ' + str(windowWidth) + u' W')

        self.setBriefInfoVisibility(False)
        limitTrailersToPlay = True
        if self._numberOfTrailersToPlay == 0:
            limitTrailersToPlay = False
        try:
            self.frontEndBridge = FrontendBridge.getInstance()

            # Main trailer playing loop

            while not Monitor.getInstance().isShutdownRequested():
                status, self._trailer = self.frontEndBridge.getNextTrailer()
                # localLogger.debug(u'Got status:', status,
                #                  u'trailer:', self._trailer)

                # Are there no trailers to play now, and in the future?

                if status == FrontendBridge.OK and self._trailer is None:
                    break

                elif status == FrontendBridge.IDLE:
                    localLogger.error(u'Should not get state IDLE')
                    break

                if status == FrontendBridge.TIMED_OUT:
                    continue

                if status == FrontendBridge.BUSY:
                    continue

                localLogger.debug(u'got trailer to play: ' +
                                  self._trailer.get(Movie.TRAILER))
                self.setDetailInvisible()
                self.setFocus(self._dummyControl)
                self.show()

                # Our event listeners will stop the player, as appropriate.

                self.getPlayer().waitForIsNotPlayingVideo()

                self._source = self._trailer.get(Movie.SOURCE)
                showMovieDetails = False
                self._viewedPlaylist.recordPlayedTrailer(self._trailer)

                if (Settings.getTimeToDisplayDetailInfo() > 0
                        and self._source != Movie.FOLDER_SOURCE):
                    showMovieDetails = True

                # This will block if showing Movie Details
                self.showMovieInfo(showDetailInfo=showMovieDetails,
                                   showBriefInfo=Settings.getShowTrailerTitle())

                # Play Trailer

                # TODO: change to asynchronous so that it can occur while
                # showing details

                if not Monitor.getInstance().isShutdownRequested():
                    localLogger.debug(u'About to play:',
                                      self._trailer.get(Movie.TRAILER))
                    if self.getPlayer() is None:
                        break

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

                if self.getPlayer() is None:
                    break

                if not self.getPlayer().waitForIsPlayingVideo(timeout=5.0):
                    # Timed out
                    localLogger.debug(u'Timed out Waiting for Player.')

                try:
                    if showMovieDetails and (
                            self._screensaverManager.isLaunchedAsScreensaver()
                            and not self._screensaverManager.isScreensaverDeactivated()):
                        self.hideDetailInfo()

                    if self.getPlayer() is None:
                        break

                    trailerTotalTime = self.getPlayer().getTotalTime()
                    maxPlayTime = Settings.getMaxTrailerLength()
                    if trailerTotalTime > maxPlayTime:
                        self.startLongTrailerKiller(maxPlayTime)
                except (AbortException, ShutdownException):
                    raise sys.exc_info()
                except Exception as e:
                    localLogger.logException()

                # Again, we rely on our listeners to  stop the player, as
                # appropriate

                self.getPlayer().waitForIsNotPlayingVideo()
                self.cancelLongPlayingTrailerKiller()

                # Again, we rely on our listeners to  stop this display, as
                # appropriate
                if Settings.getShowTrailerTitle():
                    localLogger.debug(u'About to Hide Brief Info')
                    self.setBriefInfoVisibility(False)

                if self._exitDialog:
                    break

                screenSaverState = self.getScreensaverState().getState()
                if screenSaverState == ScreensaverState.DEACTIVATED:
                    break
                    # Block until unpaused
                    # self.blockPlayingTrailers()

                if limitTrailersToPlay:
                    self._numberOfTrailersToPlay -= 1
                    if self._numberOfTrailersToPlay < 1:
                        break

            if self._trailer is None:
                localLogger.error(u'There will be no trailers to play')
                self.notifiation(Messages.getInstance().getMsg(
                    Messages.NO_TRAILERS_TO_PLAY))
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except (Exception) as e:
            localLogger.logException(e)
        finally:
            localLogger.debug(u'About to close TrailerDialog')
            localLogger.debug(u'About to stop xbmc.Player')
            if self.getPlayer() is not None:
                self.getPlayer().stop()

            self.cancelLongPlayingTrailerKiller()
            localLogger.debug(u'Stopped xbmc.Player')
            self._exitDialog = True

            self.close()
            self._viewedPlaylist.close()
            localLogger.debug(u'Closed TrailerDialog')
            self.shutdown()
            return self._exitDialog

    def getPlayer(self):
        return self._playerContainer.getPlayer()

    def showMovieInfo(self, showDetailInfo=False, showBriefInfo=False):
        if showDetailInfo:
            self.setBriefInfoVisibility(False)
            self.showDetailedInfo()
        #
        # You can have both showMovieDetails (movie details screen
        # shown prior to playing trailer) as well as the
        # simple ShowTrailerTitle while the trailer is playing.
        #
        if showBriefInfo:
            title = self.getTitleString(self._trailer)
            self.getTitleControl().setLabel(title)
            self.setBriefInfoVisibility(True)
        else:
            self.setBriefInfoVisibility(False)

    def setBriefInfoVisibility(self, visible):
        self.getTitleControl().setVisible(visible)

    def notification(self, message, displayTime=10):
        self.getTitleControl().setLabel(message)
        self.setBriefInfoVisibiity(True)

    @logEntryExit
    def showDetailedInfo(self, fromUserRequest=False):
        localLogger = self._logger.getMethodLogger(u'showDetailedInfo')

        if (self._source != Movie.SOURCE):
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
        # self._showTrailerEvent.set()
        self.setDetailVisible()
        if displaySeconds == 0:
            # One year
            displaySeconds = 365 * 24 * 60 * 60
        self._showDetailsEvent.clear()  # In case it was set
        self._showDetailsEvent.wait(displaySeconds)
        self._showDetailsEvent.clear()  # In case it was set
        self.hideDetailInfo()

    def hideDetailInfo(self, reason=u''):
        localLogger = self._logger.getMethodLogger(u'hideDetailInfo')
        localLogger.enter()
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        self._showDetailsEvent.set()  # Force showDetailInfo to unblock

        self.setDetailInvisible()
        self.setBriefInfoVisibility(Settings.getShowTrailerTitle())

    def setDetailVisible(self):

        self.getControl(TrailerDialog.PLAYER_GROUP_CONTROL).setVisible(False)
        self.getControl(TrailerDialog.DETAIL_GROUP_CONTROL).setVisible(True)

    def setDetailInvisible(self):
        self.getControl(TrailerDialog.DETAIL_GROUP_CONTROL).setVisible(False)
        self.getControl(TrailerDialog.PLAYER_GROUP_CONTROL).setVisible(True)
        if self._showInfoUIThread is not None:
            self._showInfoUIThread.cancel()
        self._showInfoUIThread = None

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

            '''
            if self._titleControl is None:
                self._titleControl = xbmcgui.ControlLabel(
                    x=10, y=40, width=760, height=40, label=titleString,
                    font=title_font)
                self.addControl(self._titleControl)
            else:
                self._titleControl.setLabel(titleString)
            '''

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

        self.unBlockPlayingTrailers()
        super().doModal()
        localLogger.exit()
        return self._exitDialog

    def show(self):
        localLogger = self._logger.getMethodLogger(u'show')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        self._screensaverManager.setAddonActive(True)

        super().show()

    def close(self):
        localLogger = self._logger.getMethodLogger(u'close')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        self._screensaverManager.setAddonActive(False)

        super().close()

    def blockPlayingTrailers(self):
        '''
            Used to block the main trailer playing loop when the screensaver
            is not active.
        '''
        localLogger = self._logger.getMethodLogger(u'blockPlayingTrailers')
        localLogger.trace(u'enter', trace=Trace.TRACE_SCREENSAVER)
        # Just in case we are paused
        if self.getPlayer() is not None:
            self.getPlayer().resumePlay()

        self.close()
        self._pause.clear()
        self._pause.wait()
        localLogger.trace(u'Exiting', trace=Trace.TRACE_SCREENSAVER)

    def unBlockPlayingTrailers(self):
        '''
            Unblocks the main trailer playing loop when the screensaver
            is active.
        '''
        localLogger = self._logger.getMethodLogger(u'unBlockPlayingTrailers')
        localLogger.trace(u'enter', trace=Trace.TRACE_SCREENSAVER)
        self._pause.set()

    def exitRandomTrailers(self):
        localLogger = self._logger.getMethodLogger(u'exitRandomTrailers')
        localLogger.trace(trace=Trace.TRACE_SCREENSAVER)
        self._exitDialog = True
        self.killLongPlayingTrailer(informUser=False)
        self.showMovieInfo(showDetailInfo=False, showBriefInfo=False)
        self._waitEvent.set(ReasonEvent.APPLICATION_EXIT)

    def onScreensaverActivated(self):
        localLogger = self._logger.getMethodLogger(u'onScreensaverActivated')
        localLogger.trace(u'enter', trace=Trace.TRACE_SCREENSAVER)

        self._waitEvent.set(ReasonEvent.SCREENSAVER_ACTIVATED)

    def onScreensaverDeactivated(self):
        localLogger = self._logger.getMethodLogger(u'onScreensaverDeactivated')
        localLogger.trace(u'enter', trace=Trace.TRACE_SCREENSAVER)

        # If the player is already being used by some other app or core Kodi, then don't
        # do anything that might impact it.

        if not self.getPlayer().isActivated():
            self.getPlayer().setCallBacks(onShowInfo=None)
            self.getPlayer().disableAdvancedMonitoring()

        # Just in case we are paused
        self.getPlayer().resumePlay()

        # Stop showing Movie details
        # getScreensaverState already returns correct info

        self.close()
        self.killLongPlayingTrailer(informUser=False)

        self._waitEvent.set(ReasonEvent.SCREENSAVER_DEACTIVATED)
        localLogger.trace(u'after setting SCREENSAVER_DEACTIVATED',
                          trace=Trace.TRACE_SCREENSAVER)

    def getScreensaverState(self):
        localLogger = self._logger.getMethodLogger(u'getScreensaverState')
        state = self._screensaverManager.getScreensaverState()
        localLogger.trace(u'state:', state.getState(),
                          trace=Trace.TRACE_SCREENSAVER)
        return state

    def onShutdownEvent(self):
        localLogger = self._logger.getMethodLogger(u'onShutdownEvent')
        localLogger.enter()
        self._shutdown = True
        self._waitEvent.set(ReasonEvent.SHUTDOWN)

    def onAbortEvent(self):
        localLogger = self._logger.getMethodLogger(u'onAbortEvent')
        localLogger.enter()
        self._abort = True
        self._waitEvent.set(ReasonEvent.KODI_ABORT)

    # TODO: put this in own class

    def startLongTrailerKiller(self, maxPlayTime):
        localLogger = self._logger.getMethodLogger(
            u'startLongTrailerKiller')
        localLogger.trace(u'waiting on lock', trace=Trace.TRACE_UI_CONTROLLER)
        with self._lock:
            localLogger.trace(u'got lock, maxPlayTime:',
                              maxPlayTime,
                              trace=Trace.TRACE_UI_CONTROLLER)
            self._longTrailerKiller = None
            if not Monitor.getInstance().isShutdownRequested():
                if maxPlayTime > Constants.MAX_PLAY_TIME_WARNING_TIME + 2:
                    maxPlayTime -= Constants.MAX_PLAY_TIME_WARNING_TIME
                    localLogger.trace(u'adjusted maxPlayTime:',  maxPlayTime,
                                      trace=Trace.TRACE_UI_CONTROLLER)
                self._longTrailerKiller = threading.Timer(maxPlayTime,
                                                          self.killLongPlayingTrailer)
                self._longTrailerKiller.setName(u'TrailerKiller')
                self._longTrailerKiller.start()

    def killLongPlayingTrailer(self, informUser=True):
        try:
            localLogger = self._logger.getMethodLogger(
                u'killLongPlayingTrailer')
            localLogger.enter()
            localLogger.trace(u'Now Killing',
                              trace=Trace.TRACE_UI_CONTROLLER)

            if informUser:
                self.getTitleControl().setLabel(self._messages.getMsg(
                    Messages.TRAILER_EXCEEDS_MAX_PLAY_TIME))
                self.setBriefInfoVisibility(True)

                # Wait unless interrupted by screen saver inactive, abort

                self._screensaverManager.waitForScreensaverInactive(
                    timeout=Constants.MAX_PLAY_TIME_WARNING_TIME)
            self.setBriefInfoVisibility(False)
            if self.getPlayer() is not None:
                self.getPlayer().stop()

            with self._lock:
                self._longTrailerKiller = None
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            Logger.logException(e)

        localLogger.trace(u'exit', trace=Trace.TRACE_SCREENSAVER)

    def cancelLongPlayingTrailerKiller(self):
        localLogger = self._logger.getMethodLogger(
            u'cancelLongPlayingTrailerKiller')
        localLogger.trace(u'enter, waiting on lock',
                          trace=[Trace.TRACE_SCREENSAVER,
                                 Trace.TRACE_UI_CONTROLLER])
        with self._lock:
            if self._longTrailerKiller is not None:
                self._longTrailerKiller.cancel()

    def playNextTrailer(self):
        localLogger = self._logger.getMethodLogger(u'playNextTrailer')
        localLogger.enter()
        # if self._infoDialogController is not None:
        #    self._infoDialogController.dismissInfoDialog()

        self.cancelLongPlayingTrailerKiller()
        self.hideDetailInfo()
        if self.getPlayer() is not None:
            self.getPlayer().stop()
        localLogger.trace(u'Finished playing old trailer',
                          trace=Trace.TRACE_SCREENSAVER)

    def getFocus(self):
        localLogger = self._logger.getMethodLogger(u'getFocus')
        localLogger.debug(u'Do not use.')
        return

    def onAction(self, action):
        '''
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
        '''

        localLogger = self._logger.getMethodLogger(u'onAction')

        if action.getId() != 107:
            localLogger.trace(u'Action.id:', str(action.getId()),
                              u'Action.buttonCode:',
                              str(action.getButtonCode()), trace=Trace.TRACE)

        if not self._screensaverManager.isAddonActive():
            localLogger.exit(u'Addon inActive')
            return

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
        if actionId == xbmcgui.ACTION_SHOW_INFO or buttonCode == 61513:
            localLogger.debug(key, u'Closing dialog')

            self.hideDetailInfo()

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
            if not ScreensaverManager.getInstance().isLaunchedAsScreensaver():
                self.exitRandomTrailers()
            else:
                self.exitRandomTrailers()
                # self._screensaverManager.onScreensaverDeactivated()

        ##################################################################
        elif (actionId == xbmcgui.ACTION_ENTER
              or actionId == xbmcgui.ACTION_SELECT_ITEM
              or actionId == xbmcgui.ACTION_SHOW_GUI
              or buttonCode == 61453):
            localLogger.debug(key, u'Play Movie')
            localLogger.debug(u'Playing movie for currently playing trailer.')
            movieFile = self._trailer[Movie.FILE]
            if movieFile == u'':
                self.notifyUser(u'Movie not available for playing trailer')
            else:
                self.playMovie(self._trailer)

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
        if self._control is None:
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
            self._control = xbmcgui.ControlLabel(xPos, yPos, width, height,
                                                 text, font, textColor,
                                                 disabledColor, alignment,
                                                 hasPath, angle)
            self.addControl(self._control)
            localLogger.exit()

        return self._control

    def addToPlaylist(self, playListId, trailer):
        localLogger = self._logger.getMethodLogger(u'addToPlayList')
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
        playlistFile = _playlistMap.get(playListId, None)
        if playlistFile is None:
            localLogger.error(
                u'Invalid playlistId, ignoring request to write to playlist.')
        else:
            Playlist.getPlaylist(playlistFile).recordPlayedTrailer(trailer)

    def notifyUser(self, msg):
        # TODO: Supply code
        localLogger = self._logger.getMethodLogger(u'notifyUser')
        localLogger.debug(msg)

    def playMovie(self, trailer):
        # TODO: Supply code
        localLogger = self._logger.getMethodLogger(u'playMovie')
        localLogger.debug(u'Playing movie at user request:',
                          trailer[Movie.TITLE])

        self.exitRandomTrailers()
        listItem = xbmcgui.ListItem(label=trailer[Movie.TITLE],
                                    thumbnailImage=trailer[Movie.THUMBNAIL],
                                    path=trailer[Movie.FILE])
        listItem.setInfo(type=u'video',
                         infoLabels={u'genre': trailer[Movie.GENRE],
                                     u'path': trailer[Movie.FILE],
                                     u'plot': trailer[Movie.PLOT]})
        listItem.setProperty(u'isPlayable', u'true')

        xbmc.Player.play(trailer[Movie.FILE].encode(u'utf-8'), listitem=listItem,
                         windowed=False)
        # "PlayMedia(media[,isdir][,1],[playoffset=xx])"
        # command = 'XBMC.NotifyAll({0}.SIGNAL,{1},{2})'.format(source_id, signal,_encodeData(data))
        # xbmc.executebuiltin(command)

    def getTitleString(self, trailer):
        title = u'[B]' + trailer[Movie.DETAIL_TITLE] + u'[/B]'
        title2 = trailer[Movie.DETAIL_TITLE]
        return title


    def shutdown(self):
        localLogger = self._logger.getMethodLogger(u'shutdown')
        localLogger.enter()
        self.close()
        self._playerContainer.useDummyPlayer()

        self._numberOfTrailersToPlay = 0
        self._control = None
        self._source = None
        self._trailer = None
        self._viewedPlaylist = None
