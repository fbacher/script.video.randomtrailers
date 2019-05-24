# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                      TextType, DEVELOPMENT, RESOURCE_LIB)
from xml.dom import minidom
from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger
from common.monitor import Monitor
from player.player_container import PlayerContainer
from common.settings import Settings
from common.watchdog import WatchDog
from frontend.trailer_dialog import TrailerDialog, DialogState
from frontend.black_background import BlackBackground
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
            * Listens for events:stop & exit, pause, play, queueMovie, showInfo,
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


def playTrailers(runningAsScreensaver=False):
    myTrailerDialog = None
    localLogger = logger.getMethodLogger(u'playTrailers')
    try:
        blackBackground = BlackBackground.getInstance()
        blackBackground.show()
        myTrailerDialog = TrailerDialog(u'script-trailerwindow.xml',
                                        Constants.ADDON_PATH, u'Default')
        _exit = myTrailerDialog.doModal()

        """
            currentWindow = xbmcgui.getCurrentWindowId()
            # fullscreenvideo 		12005
            # ReplaceWindow(u'fullscreenvideo')
            blackBackground.setVisibility(opaque=False)
            windowId = blackBackground.getWindowId()

            blackBackground.close()
            xbmc.executebuiltin(u'ReplaceWindow(' + str(currentWindow) + u')')
            del blackBackground
            xbmc.executebuiltin(u'ReplaceWindow(' + str(currentWindow) + u')')
         """
    finally:
        if myTrailerDialog is not None:
            del myTrailerDialog
            myTrailerDialog = None
            localLogger.exit()


# noinspection Annotator
class StartUI(threading.Thread):
    def __init__(self, screensaver=False):
        super().__init__(name=u'startUI')
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
        # blackBackground = None
        try:
            localLogger.debug(u'screensaver:', self._screensaver)
            localLogger.debug(u'ADDON_PATH: ' + Constants.ADDON_PATH)

            if not xbmc.Player().isPlaying() and not self.check_for_xsqueeze():
                localLogger.debug(u'Python path: ' + unicode(sys.path))

                # TODO: Use settings

                currentDialogId = xbmcgui.getCurrentWindowDialogId()
                currentWindowId = xbmcgui.getCurrentWindowId()
                localLogger.debug(u'CurrentDialogId, CurrentWindowId: ' + str(currentDialogId) +
                                  u' ' + str(currentWindowId))

                if Settings.getAdjustVolume():
                    muted = xbmc.getCondVisibility("Player.Muted")
                    if not muted and Settings.getVolume() == 0:
                        xbmc.executebuiltin(u'xbmc.Mute()')
                    else:
                        xbmc.executebuiltin(
                            u'XBMC.SetVolume(' + str(Settings.getVolume()) + ')')

                self._playerContainer = PlayerContainer.getInstance()
                # if Settings.getShowCurtains():
                #    self._playerContainer.getPlayer().playTrailer(Settings.getOpenCurtainPath(),
                #                                                  {Movie.TITLE: u'openCurtain',
                # Movie.TRAILER: Settings.getOpenCurtainPath()})

                # Finish curtain playing before proceeding

                #    self._playerContainer.getPlayer().waitForIsPlayingVideo(3)
                #    self._playerContainer.getPlayer().waitForIsNotPlayingVideo()
                playTrailers(runningAsScreensaver=self._screensaver)
                # del self._playerContainer
                # self._playerContainer = None
                # del blackBackground
                # blackBackground = None
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
            #
            # Player is set to a dummy in the event that it is no longer in
            # Random Trailers control

            if (self._playerContainer is not None
                    and self._playerContainer.getPlayer() is not None):
                self._playerContainer.getPlayer().stop()

            localLogger.debug(u'Deleting black screen')

            blackBackground = BlackBackground.getInstance()
            blackBackground.close()
            blackBackground.destroy()
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
