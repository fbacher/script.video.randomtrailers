# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

from future import standard_library
standard_library.install_aliases()  # noqa: E402

from builtins import str
from builtins import unicode
from xml.dom import minidom
from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger
from common.monitor import Monitor
from player.player_container import PlayerContainer
from common.settings import Settings
from common.watchdog import WatchDog
from frontend.trailer_dialog import TrailerDialog
from frontend.utils import ScreensaverManager
import sys
import os
import threading
from kodi_six import xbmc, xbmcgui

'''
    Rough outline:
        Start separate threads to discover basic information about all selected
        video sources:
            1- library
            2- trailer folders
            3- iTunes
            4- TMDB
            5- (future) IMDB
        Each of the above store the discovered info into separate queues.
        The main function here is to discover the identity of all candidates
        for playing so that a balanced mix of trailers is available for playing
        and random selection. It is important to do this quickly. Additional
        information discovery is performed later, in background threads or
        just before playing the video.

        Immediately after starting the discovery threads, the player
        thread is started. The player thread:
            * Loops playing videos until stopped
            * On each iteration it gets movie a to play from
              TrailerManager's ReadyToPlay queue
            * Listens for events:stop & exit, pause, play, playMovie, showInfo,
              Skip to next trailer, etc.

        TrailerManager holds various queues and lists:
            * Queues for each video source (library, iTunes, etc.) for
                the initial discovery from above
            * Queues for discovering additional information
            * DiscoveredTrailers, a list of all videos after filtering (genre,
                rating, etc). This list grows during initial discovery
            * A small queue (about 5 elements) for each video source so that
                required additional information can be discovered just before
                playing the video. The queues provide enough of a buffer so
                that playing will not be interrupted waiting on discovery
            * The ReadyToPlayQueue which is a small queue containing fully
                discovered trailers and awaiting play. WAs trailers are played
                it is refilled from the small final discovery queues above


'''

# TODO: Move to ui_utils

logger = Logger(u'random_trailer_ui')


def getTitleFont():
    localLogger = logger.getMethodLogger(u'getTitleFont')
    localLogger.debug(u'In randomtrailer.getTitleFont')
    title_font = 'font13'
    base_size = 20
    multiplier = 1
    skin_dir = xbmc.translatePath("special://skin/")
    list_dir = os.listdir(skin_dir)
    fonts = []
    fontxml_path = u''
    font_xml = u''
    for item in list_dir:
        item = os.path.join(skin_dir, item)
        if os.path.isdir(item):
            font_xml = os.path.join(item, "Font.xml")
        if os.path.exists(font_xml):
            fontxml_path = font_xml
            break
    theDom = minidom.parse(fontxml_path)
    fontlist = theDom.getElementsByTagName('font')
    for font in fontlist:
        name = font.getElementsByTagName('name')[0].childNodes[0].nodeValue
        size = font.getElementsByTagName('size')[0].childNodes[0].nodeValue
        fonts.append({'name': name, 'size': float(size)})
    fonts = sorted(fonts, key=lambda k: k[u'size'])
    for f in fonts:
        if f[u'name'] == 'font13':
            multiplier = f[u'size'] / base_size
            break
    for f in fonts:
        if f[u'size'] >= 38 * multiplier:
            title_font = f[u'name']
            break
    return title_font


class BlankWindow(xbmcgui.WindowXML):
    '''
        Ensure a nice black window behind our player and transparent
        TrailerDialog. Keeps the Kodi screen from showing up from time
        to time (between trailers, etc.).
    '''

    def onInit(self):
        pass

    def close(self):
        localLogger = logger.getMethodLogger(u'BlankWindow.close')
        localLogger.enter()
        super(BlankWindow, self).close()

    def show(self):
        localLogger = logger.getMethodLogger(u'BlankWindow.show')
        localLogger.enter()
        super(BlankWindow, self).show()


def playTrailers(blackBackground, runningAsScreensaver=False):
    myTrailerDialog = None
    localLogger = logger.getMethodLogger(u'playTrailers')
    _exit = False
    screenSaverManager = ScreensaverManager.getInstance()
    _playerContainer = PlayerContainer.getInstance()

    numberOfTrailersToPlay = Settings.getNumberOfTrailersToPlay()
    if not (_exit or Monitor.getInstance().isShutdownRequested()):
        myTrailerDialog = TrailerDialog(u'script-trailerwindow.xml',
                                        Constants.ADDON_PATH, u'Default',
                                        numberOfTrailersToPlay=numberOfTrailersToPlay,
                                        screensaver=runningAsScreensaver)
    GROUP_TRAILERS = False
    if Constants.ADDON.getSetting(u'group_trailers') == u'true':
        GROUP_TRAILERS = True
    GROUP_NUMBER = int(Constants.ADDON.getSetting(u'group_number'))
    trailersInGroup = GROUP_NUMBER
    GROUP_DELAY = Settings.getGroupDelay()
    showOpenCurtain = False  # Already played at startup
    try:
        while not (_exit or Monitor.getInstance().isShutdownRequested()):
            blackBackground.show()

            if showOpenCurtain:
                localLogger.debug(u'Playing OpenCurtain')

                _playerContainer.getPlayer().playTrailer(Settings.getOpenCurtainPath().encode(u'utf-8'),
                                                                  {Movie.TITLE: u'openCurtain',
                                                                   Movie.TRAILER: Settings.getOpenCurtainPath()})
                _playerContainer.getPlayer().waitForIsNotPlayingVideo()

            # Open curtain before each group

            showOpenCurtain = Settings.getShowCurtains()
            while not Monitor.getInstance().isShutdownRequested():
                Monitor.getInstance().throwExceptionIfShutdownRequested()

                if GROUP_TRAILERS:
                    trailersInGroup = trailersInGroup - 1

                # Play a group of trailers.
                # This will unblock when:
                #    a group has finished playing
                #    screen saver disabled
                #    user request to exit plugin
                #    shutdown/abort

                _exit = myTrailerDialog.doModal()

                # This should not be needed, but....

                _playerContainer.getPlayer().waitForIsNotPlayingVideo()

                if _exit or (
                        screenSaverManager.isLaunchedAsScreensaver()
                        and screenSaverManager.isScreensaverDeactivated()):
                    break

                if not GROUP_TRAILERS:
                    break

                if trailersInGroup == 0:
                    trailersInGroup = GROUP_NUMBER
                    i = GROUP_DELAY
                    while Monitor.getInstance().waitForShutdown(0.500):
                        i = i - 500
                        if i < 0:
                            break

            showCloseCurtain = False
            if _exit or (
                    screenSaverManager.isLaunchedAsScreensaver()
                    and screenSaverManager.isScreensaverDeactivated()):
                showCloseCurtain = True
            if Monitor.getInstance().isShutdownRequested():
                showCloseCurtain = False

            if showCloseCurtain:
                if Settings.getShowCurtains():
                    localLogger.debug(u'Playing CloseCurtain')
                    _playerContainer.getPlayer().playTrailer(Settings.getCloseCurtainPath().encode(u'utf-8'),
                                {Movie.TITLE: u'closeCurtain',
                                 Movie.TRAILER: Settings.getCloseCurtainPath()})
                    _playerContainer.getPlayer().waitForIsNotPlayingVideo()

            blackBackground.close()

            # Block if in screensaver mode and screen saver inactive

            #screensaverManager = ScreensaverManager.getInstance()
            # if screensaverManager.isLaunchedAsScreensaver():
            #    screensaverManager.waitForScreensaverActive()

    finally:
        if myTrailerDialog is not None:
            del myTrailerDialog
            myTrailerDialog = None
            localLogger.exit()


class StartUI(threading.Thread):
    def __init__(self, screensaver=False):
        super(StartUI, self).__init__(name=u'startUI')
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()

        self._screensaver = screensaver
        WatchDog.registerThread(self)

    # Don't start if Kodi is busy playing something

    def run(self):
        localLogger = self._logger.getMethodLogger(u'run')
        try:
            localLogger.debug(u'screensaver:', self._screensaver)
            localLogger.debug(u'ADDON_PATH: ' + Constants.ADDON_PATH)

            finished = False
            while not finished:
                self.startPlayingTrailers()
                break
                Monitor.getInstance().throwExceptionIfShutdownRequested(delay=60)

        except AbortException:
            localLogger.error(
                'Exiting Random Trailers Screen Saver due to Kodi Abort!')
        except ShutdownException:
            localLogger.error(
                u'Exiting Random Trailers Screen Saver at addon\'s request')
        except Exception as e:
            localLogger.logException(e)

        finally:
            localLogger.debug(u'Stopping xbmc.Player')

            Monitor.getInstance().shutDownRequested()
            localLogger.exit()

    def startPlayingTrailers(self):
        localLogger = self._logger.getMethodLogger(u'startPlayingTrailers')
        try:
            localLogger.debug(u'screensaver:', self._screensaver)
            localLogger.debug(u'ADDON_PATH: ' + Constants.ADDON_PATH)

            # if self._screensaver:
            #    ScreensaverManager.getInstance().waitForScreensaverActive()

            # ScreensaverManager.getInstance().onScreensaverActivated()
            # ScreensaverManager.getInstance().wakeup(self._screensaver)

            blackBackground = None

            if not xbmc.Player().isPlaying() and not self.check_for_xsqueeze():
                localLogger.debug(u'Python path: ' + unicode(sys.path))

                # TODO: Use settings

                currentDialogId = xbmcgui.getCurrentWindowDialogId()
                currentWindowId = xbmcgui.getCurrentWindowId()
                localLogger.debug(u'CurrentDialogId, CurrentWindowId: ' + str(currentDialogId) +
                                  u' ' + str(currentWindowId))

                blackBackground = BlankWindow(u'script-BlankWindow.xml',
                                              Constants.ADDON_PATH, u'Default')
                localLogger.debug(u'Activating BlankWindow')
                blackBackground.show()

                if Settings.getAdjustVolume():
                    muted = xbmc.getCondVisibility("Player.Muted")
                    if not muted and Settings.getVolume() == 0:
                        xbmc.executebuiltin(u'xbmc.Mute()')
                    else:
                        xbmc.executebuiltin(
                            u'XBMC.SetVolume(' + str(Settings.getVolume()) + ')')

                self._playerContainer = PlayerContainer.getInstance()
                if Settings.getShowCurtains():
                    self._playerContainer.getPlayer().playTrailer(Settings.getOpenCurtainPath(),
                                                                  {Movie.TITLE: u'openCurtain',
                                                                   Movie.TRAILER: Settings.getOpenCurtainPath()})

                # Finish curtain playing before proceeding
                if Settings.getShowCurtains():
                    self._playerContainer.getPlayer().waitForIsPlayingVideo(3)
                    self._playerContainer.getPlayer().waitForIsNotPlayingVideo()
                playTrailers(blackBackground,
                             runningAsScreensaver=self._screensaver)
                del self._playerContainer
                self._playerContainer = None
                del blackBackground
                blackBackground = None
                if Settings.getAdjustVolume():
                    muted = xbmc.getCondVisibility(u'Player.Muted')

                    if muted and Settings.getVolume() == 0:
                        xbmc.executebuiltin('xbmc.Mute()')
                    else:
                        currentVolume = xbmc.getInfoLabel(u'Player.Volume')
                        currentVolume = int(
                            (float(currentVolume.split(u' ')[0]) + 60.0) / 60.0 * 100.0)
                        xbmc.executebuiltin(
                            'XBMC.SetVolume(' + str(currentVolume) + ')')

                localLogger.debug(u'Shutting down')
                Playlist.shutdown()
            else:
                localLogger.notice(
                    'Exiting Random Trailers Screen Saver Something is playing!!!!!!')
        except AbortException:
            localLogger.error(
                'Exiting Random Trailers Screen Saver due to Kodi Abort!')
        except ShutdownException:
            localLogger.error(
                u'Exiting Random Trailers Screen Saver at addon\'s request')
        except Exception as e:
            localLogger.logException(e)

        finally:
            localLogger.debug(u'Stopping xbmc.Player')
            xbmc.Player().stop()
            localLogger.debug(u'Deleting black screen')
            if blackBackground is not None:
                blackBackground.close()
                del blackBackground
                blackBackground = None
            # Monitor.getInstance().shutDownRequested()
            localLogger.exit()

    def check_for_xsqueeze(self):
        localLogger = self._logger.getMethodLogger(u'check_for_xsqueeze')
        localLogger.enter()
        KEYMAPDESTFILE = os.path.join(xbmc.translatePath(
            u'special://userdata/keymaps'), "xsqueeze.xml")
        if os.path.isfile(KEYMAPDESTFILE):
            return True
        else:
            return False

    def shutdownThread(self):
        pass
