from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import unicode
from multiprocessing.pool import ThreadPool
from xml.dom import minidom
from kodi65 import addon
from kodi65 import utils
from common.rt_constants import Constants
from common.rt_constants import Movie
from common.rt_utils import Utils
from common.rt_utils import Playlist
from common.exceptions import AbortException, ShutdownException
from common.rt_utils import WatchDog
from common.rt_utils import Trace
from common.logger import Logger, logEntryExit
from player.advanced_player import AdvancedPlayer
from action_map import Action
from settings import Settings
from backend.api import *
import sys
import datetime
import io
import json
import os
import queue
import random
import re
import requests
import resource
import threading
import time
import traceback
import urllib
#from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin
import xbmcaddon
#import xbmcwsgi
import xbmcdrm
import string
import action_map


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

REMOTE_DBG = True

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        xbmc.log(u'Trying to attach to debugger', xbmc.LOGDEBUG)
        Debug.myLog(u'Python path: ' + unicode(sys.path), xbmc.LOGDEBUG)
        # os.environ["DEBUG_CLIENT_SERVER_TRANSLATION"] = "True"
        # os.environ[u'PATHS_FROM_ECLIPSE_TO_PYTON'] =\
        #    u'/home/fbacher/.kodi/addons/script.video/randomtrailers/resources/lib/random_trailers_ui.py:' +\
        #    u'/home/fbacher/.kodi/addons/script.video/randomtrailers/resources/lib/random_trailers_ui.py'

        '''
            If the server (your python process) has the structure
                /user/projects/my_project/src/package/module1.py
    
            and the client has:
                c:\my_project\src\package\module1.py
    
            the PATHS_FROM_ECLIPSE_TO_PYTHON would have to be:
                PATHS_FROM_ECLIPSE_TO_PYTHON = [(r'c:\my_project\src', r'/user/projects/my_project/src')
            # with the addon script.module.pydevd, only use `import pydevd`
            # import pysrc.pydevd as pydevd
        '''
        sys.path.append(u'/home/fbacher/.kodi/addons/script.module.pydevd/lib/pydevd.py'
                        )
        import pydevd
        # stdoutToServer and stderrToServer redirect stdout and stderr to eclipse
        # console
        try:
            pydevd.settrace('localhost', stdoutToServer=True,
                            stderrToServer=True)
        except Exception as e:
            xbmc.log(
                u' Looks like remote debugger was not started prior to plugin start', xbmc.LOGDEBUG)

    except ImportError:
        msg = u'Error:  You must add org.python.pydev.debug.pysrc to your PYTHONPATH.'
        xbmc.log(msg, xbmc.LOGDEBUG)
        sys.stderr.write(msg)
        sys.exit(1)
    except BaseException:
        Debug.logException(u'Waiting on Debug connection')

logger = Logger(u'random_trailer_ui')


def getTitleFont():
    Debug.myLog('In randomtrailer.getTitleFont', xbmc.LOGNOTICE)
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


'''
    Ask user if they want to only see trailers for a specific genre.
    If so then let the user choose from genres that are actually
    present in the library.
'''


def promptForGenre():
    Debug.myLog('In randomtrailer.promptForGenre', xbmc.LOGNOTICE)
    selectedGenre = u''

    # ask user whether they want to select a genre
    a = xbmcgui.Dialog().yesno(Constants.ADDON.getLocalizedString(
        32100), Constants.ADDON.getLocalizedString(32101))
    # deal with the output
    if a == 1:
        # prompt user to select genre
        sortedGenres = MovieUtils.getGenresInLibrary()
        selectedIndex = xbmcgui.Dialog().select(
            Constants.ADDON.getLocalizedString(32100), sortedGenres, autoclose=False)
        Debug.myLog(u'got back from promptForGenre selectedIndex: ' +
                    str(selectedIndex), xbmc.LOGDEBUG)
        # check whether user cancelled selection
        if selectedIndex != -1:
            # get the user's chosen genre
            selectedGenre = sortedGenres[selectedIndex]

    return selectedGenre


'''
    Ensure a nice black window behind our player and transparent
    TrailerDialog. Keeps the Kodi screen from showing up from time
    to time (between trailers, etc.).
'''


class BlankWindow(xbmcgui.WindowXML):

    def onInit(self):
        pass


'''
    A transparent window (all WindowDialogs are transparent) to contain
    our listeners and Title display. 
'''

TRACE_STRING = u'TRACE_EVENT '


class BaseWindow():
    def addToPlayList(self, playListId, trailer):
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

    def exitRandomTrailers(self):
        Monitor.getSingletonInstance().shutDownRequested()

    def notifyUser(self, msg):
        # TODO: Supply code
        localLogger = self._logger.getMethodLogger(u'notifyUser')
        localLogger.debug(msg)

    def playMovie(self, trailer):
        # TODO: Supply code
        localLogger = self._logger.getMethodLogger(u'playMovie')
        localLogger.debug(u'Playing movie at user request:',
                          trailer[Movie.TITLE])


# (xbmcgui.WindowXMLDialog):
class TrailerDialog(xbmcgui.WindowDialog, BaseWindow):

    # [optional] this function is only needed of you are passing optional data to your window
    def __init__(self, *args, **kwargs):
        # get the optional data and add it to a variable you can use elsewhere
        # in your script
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()
        self._player = kwargs[u'player']
        self._player.setCallBacks(onShowInfo=self)
        self._numberOfTrailersToPlay = kwargs[u'numberOfTrailersToPlay']
        self._control = None
        self._source = None
        self._trailer = None
        self._viewedPlaylist = Playlist.getPlaylist(
            Playlist.VIEWED_PLAYLIST_FILE)
        self._infoDialogController = InfoDialogController(
            kwargs={u'trailerDialog': self})

        # TODO: - Need own thread subclasses to catch unhandled exceptions
        # and to catch abortException & ShutdownException

        self._thread = threading.Thread(
            target=self.doIt, name='TrailerDialog')
        self._thread.start()

    def doIt(self):
        localLogger = self._logger.getMethodLogger(u'doIt')

        localLogger.debug(u' WindowID: ' +
                          str(xbmcgui.getCurrentWindowId()))
        self._infoDialog = None
        self._infoDialogClosed = False

        windowstring = Utils.getKodiJSON(
            '{"jsonrpc":"2.0","method":"GUI.GetProperties",\
            "params":{"properties":["currentwindow"]},"id":1}')
        localLogger.debug('Trailer_Window_id = ' +
                          str(windowstring[u'result'][u'currentwindow'][u'id']))
        localLogger.debug(u' about to get TrailerManager.iterator')

        _1080P = 0X0  # 1920 X 1080
        _720p = 0X1  # 1280 X 720
        windowHeight = self.getHeight()
        windowWidth = self.getWidth()
        Debug.myLog(u'Window Dimensions: ' + str(windowHeight) +
                    u' H  x ' + str(windowWidth) + u' W', xbmc.LOGDEBUG)

        self.getTitleControl(u'').setVisible(False)
        self.setFocus(self.getTitleControl())
        limitTrailersToPlay = False
        if self._numberOfTrailersToPlay == 0:
            limitTrailersToPlay = True

        trailerManager = BaseTrailerManager.getInstance()
        trailerIterator = iter(trailerManager)
        self._trailer = next(trailerIterator)
        try:
            while self._trailer is not None and not Monitor.getSingletonInstance().isShutdownRequested():
                localLogger.debug(u' got trailer to play: ' +
                                  self._trailer.get(Movie.TRAILER))
                if self._infoDialog is not None:
                    self.closeInfoDialog()

                if self._player.isPlaying():
                    try:
                        Trace.log(
                            localLogger.getMsgPrefix() + u' Player is busy on entry: ' +
                            xbmc.Player().getPlayingFile(), Trace.TRACE)
                    except Exception as e:
                        pass

                TrailerDialog.trailer = self._trailer
                self._player.waitForIsNotPlayingVideo()
                self.setFocus(self.getTitleControl())
                self.show()

                self._source = self._trailer.get(Movie.SOURCE)
                localLogger.debug(' ShowInfoDetail: ', str(Settings.getTimeToDisplayDetailInfo() > 0) + ' source: ' +
                                  self._source)
                showInfoDialog = False
                self._viewedPlaylist.recordPlayedTrailer(self._trailer)

                if Settings.getTimeToDisplayDetailInfo() > 0 and self._source != Movie.FOLDER_SOURCE:
                    localLogger.debug(u' Show InfoDialog enabled')
                    showInfoDialog = True

                if showInfoDialog:
                    localLogger.debug(u'About to show Info Dialog')
                    self.showDetailedInfo()

                if not Monitor.getSingletonInstance().isShutdownRequested():
                    localLogger.debug(u' About to play: ' +
                                      self._trailer.get(Movie.TRAILER))
                    self._player.play(self._trailer.get(Movie.TRAILER))
                    #
                    # You can have both showInfoDialog (movie details screen
                    # shown prior to playing trailer) as well as the
                    # simple ShowTrailerTitle while the trailer is playing.
                    #
                    if Settings.getShowTrailerTitle():
                        localLogger.debug(u'About show Brief Info')
                        title = u'[B]' + \
                            self._trailer[Movie.DETAIL_TITLE] + u'[/B]'

                        self.getTitleControl().setLabel(title)
                        self.getTitleControl().setVisible(True)
                        self.setFocus(self.getTitleControl())
                        self.show()
                        localLogger.debug(u'Showed Brief Info')

                # If user exits while playing trailer, for a
                # movie in the library, then play the movie
                #
                # if Monitor.getSingletonInstance().isShutdownRequested():
                #    Debug.myLog(
                #        'randomtrailers.TrailerDialog exitRequested', xbmc.LOGDEBUG)
                #    self._player.play(trailer[u'file'])

                if not self._player.waitForIsPlayingVideo(timeout=5.0):
                    # Timed out
                    localLogger.debug(u'Timed out Waiting for Player.')
                else:
                    self._player.waitForIsNotPlayingVideo()

                if Settings.getShowTrailerTitle():
                    localLogger.debug(u'About to Hide Brief Info')
                    self.getTitleControl().setVisible(False)

                self._trailer = next(trailerIterator)

                if limitTrailersToPlay:
                    self._numberOfTrailersToPlay -= 1
                    if self.numberOfTrailersToPlay < 1:
                        break
        except (AbortException, ShutdownException):
            pass
        except:
            localLogger.logException()
        finally:
            localLogger.debug(u'About to close TrailerDialog')
            localLogger.debug(u'About to stop xbmc.Player')
            self._player.stop()
            localLogger.debug(u'Stopped xbmc.Player')

            self.close()
            localLogger.debug(u'Closed TrailerDialog')
            self.shutdown()

    def timeOut(self):
        pass

    '''
        Callback method from InfoDialog to inform us that it has closed, most
        likely from a timeout. But it could be due to user action.
    '''

    def onInfoDialogClosed(self, reason=u''):
        localLogger = self._logger.getMethodLogger(u'onInfoDialogClosed')
        localLogger.debug(TRACE_STRING + u'reason: ' + reason)
        self._infoDialogClosed = True
        if Settings.getShowTrailerTitle():
            localLogger.debug(u'About show Brief Info')
            self.getTitleControl().setVisible(True)
            self.setFocus(self.getTitleControl())
            self.show()
            localLogger.debug(u'Showed Brief Info')

        self._player.resumePlay()
        localLogger.debug(TRACE_STRING + u'deleted InfoDialog')

    def getFocus(self):
        localLogger = self._logger.getMethodLogger(u'getFocus')
        localLogger.debug(u'Do not use.')
        return
        result = super(TrailerDialog, self).getFocus()
        localLogger.debug(u' result:' + result)

    def setFocus(self, control):
        localLogger = self._logger.getMethodLogger(u'setFocus')
        try:
            super(TrailerDialog, self).setFocus(control)
        except:
            localLogger.logException()

    def setFocusId(self, controlId):
        localLogger = self._logger.getMethodLogger(u'setFocusId')
        try:
            super(TrailerDialog, self).setFocusId(controlId)
        except:
            localLogger.logException()

    '''
        Called when the trailer has finished playing before the InfoDialog
        has voluntarily timed out.
    '''

    def closeInfoDialog(self):
        localLogger = self._logger.getMethodLogger(u'closeInfoDialog')
        try:
            localLogger.enter()
            localLogger.debug(TRACE_STRING)
            if self._infoDialog is not None:
                self._infoDialog.dismiss(reason=u'forced')
        except Exception as e:
            pass  # perhaps the dialog closed while we are trying to close it
        finally:
            self._infoDialog = None
            localLogger.exit()

    def onClick(self, controlId):
        Trace.log(u'randomTrailers.TrailerDialog.onClick controlID: ' +
                  str(controlId), Trace.TRACE)

    def onBack(self, actionId):
        localLogger = self._logger.getMethodLogger(u'onBack')

        Trace.log(localLogger.getMsgPrefix() + u' actionId: ' +
                  str(actionId), Trace.TRACE)

    def onFocus(self, controlId):
        localLogger = self._logger.getMethodLogger(u'onFocus')
        localLogger.debug(u' controlId:' + controlId)

    def onDeinitWindow(self, windowId):
        localLogger = self._logger.getMethodLogger(u'onDeinitWindow')
        localLogger.debug(u'windowId:', windowId)

    def OnDeinitWindow(self, windowId):
        localLogger = self._logger.getMethodLogger(u'OnDeinitWindow')
        localLogger.debug(u'windowId:', windowId)

    def onControl(self, control):
        localLogger = self._logger.getMethodLogger(u'onControl')

        Trace.log(localLogger.getMsgPrefix() + u' controlId: ' +
                  str(control.getId()), Trace.TRACE)

    def onShowInfo(self):
        localLogger = self._logger.getMethodLogger(u'onShowInfo')
        Trace.log(localLogger.getMsgPrefix(), Trace.TRACE)
        localLogger.debug(TRACE_STRING)

        # xbmc.executebuiltin('Dialog.Close(seekbar,true)')  # Doesn't work :)
        #  xbmc.getCondVisibility Player.ShowInfo
        # TODO: Probably should use different thread
        self.showDetailedInfo(fromUserRequest=True)

    def onAction(self, action):
        '''
            SHOW_INFO -> Toggle Display custom InfoDialog

            STOP -> Skip to next trailer
            ACTION_MOVE_RIGHT -> Skip to next trailer

            PREVIOUS_MENU -> Exit Random Trailer script
            NAV_BACK -> Exit Random Trailer Script

            PAUSE -> Toggle Play/Pause playing trailer
            PLAY -> Toggle Play/Pause playing trailer

            ENTER -> Play movie for current trailer (if available)

            REMOTE_0 .. REMOTE_9 -> Record playing movie info to
                        userdata/addon_data/script.video.randomtrailers/<playlist<n>

            ACTION_QUEUE_ITEM -> Add movie to Couch Potato 
        '''

        localLogger = self._logger.getMethodLogger(u'onAction')
        actionId = action.getId()

        Trace.log(localLogger.getMsgPrefix() + u' Action.id: ' +
                  str(action.getId()) + u' Action.buttonCode: ' +
                  str(action.getButtonCode()), Trace.TRACE)

        actionMapper = Action.getInstance()
        matches = actionMapper.getKeyIDInfo(action)

        for line in matches:
            Debug.myLog(line, xbmc.LOGDEBUG)

        actionId = action.getId()
        buttonCode = action.getButtonCode()
        if actionId == xbmcgui.ACTION_QUEUE_ITEM:
            localLogger.debug(u'ACTION_QUEUE_ITEM')
            strCouchPotato = 'plugin://plugin.video.couchpotato_manager/movies/add?title=' + \
                self._trailer[Movie.TITLE]
            #xbmc.executebuiltin('XBMC.RunPlugin(' + strCouchPotato + ')')

        elif (actionId == xbmcgui.ACTION_PREVIOUS_MENU or actionId == xbmcgui.ACTION_NAV_BACK):
            localLogger.debug(u'Exiting RandomTrailers at user request')
            self.exitRandomTrailers()

        elif actionId == xbmcgui.ACTION_STOP or actionId == xbmcgui.ACTION_MOVE_RIGHT:
            localLogger.debug(u'Play next trailer at user\'s request')
            self._player.stop()

        elif actionId == xbmcgui.ACTION_ENTER:
            localLogger.debug(u'Playing movie for currently playing trailer.')
            movieFile = self._trailer[Movie.FILE]
            if movieFile == u'':
                self.notifyUser(u'Movie not available for playing trailer')
            else:
                self.playMovie(self._trailer)

        elif actionId == xbmcgui.ACTION_SHOW_INFO:
            localLogger.debug(TRACE_STRING +
                              u'ACTION_SHOW_INFO. Closing dialog')
            if self._infoDialog is not None:
                self.closeInfoDialog()
            # No point showing Detail dialog now, wait until we get
            # onShowInfo from AdvancedPlayer
            # self.showDetailedInfo()

        # ACTION_I or actionId == ACTION_DOWN:
        elif buttonCode == 61513:
            localLogger.debug(TRACE_STRING +
                              u'keyboard "i". Closing dialog, calling dismiss')
            if self._infoDialog is not None:
                self.closeInfoDialog()
            else:
                self.showDetailedInfo(True)

        # From IR remote as well as keyboard
        # Close InfoDialog and resume playing trailer

        if (actionId == xbmcgui.REMOTE_1 or
            actionId == xbmcgui.REMOTE_2 or
            actionId == xbmcgui.REMOTE_3 or
            actionId == xbmcgui.REMOTE_4 or
            actionId == xbmcgui.REMOTE_5 or
            actionId == xbmcgui.REMOTE_6 or
            actionId == xbmcgui.REMOTE_7 or
            actionId == xbmcgui.REMOTE_8 or
            actionId == xbmcgui.REMOTE_9 or
                actionId == xbmcgui.REMOTE_0):
            self.addToPlaylist(actionId)

    @logEntryExit
    def showDetailedInfo(self, fromUserRequest=False):
        localLogger = self._logger.getMethodLogger(u'showDetailedInfo')

        if self._infoDialog is None and self._source != Movie.SOURCE:
            localLogger.debug(TRACE_STRING + u'about to showDetailedInfo')
            self.getTitleControl().setVisible(False)
            displaySeconds = Settings.getTimeToDisplayDetailInfo()
            if fromUserRequest:
                displaySeconds = 0

            self._player.pausePlay()
            self._infoDialogController.show(self._trailer, displaySeconds)

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

    def shutdown(self):
        localLogger = self._logger.getMethodLogger(u'shutdown')
        localLogger.enter()
        self.close()
        self._player.setCallBacks(onShowInfo=None)
        self._player = None
        self._numberOfTrailersToPlay = 0
        self._control = None
        self._source = None
        self._trailer = None
        self._viewedPlaylist = None
        self._infoDialogController = None


class InfoDialogController(threading.Thread):
    def __init__(self,  group=None, target=None, name=None,
                 args=(), kwargs={}, verbose=None):
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()
        self._trailerDialog = kwargs.get(u'trailerDialog', None)

        name = u'InfoDialogController'
        super(InfoDialogController, self).__init__(group, target, name,
                                                   args, kwargs, verbose)
        WatchDog.registerThread(self)
        self._showTrailerEvent = threading.Event()
        self._infoDialog = InfoDialog(u'script-DialogVideoInfo.xml',
                                      Constants.ADDON_PATH, u'Default', u'720p',
                                      controller=self)
        self._timer = None
        self.start()

    def run(self):
        localLogger = self._logger.getMethodLogger(u'run')

        while not Monitor.getSingletonInstance().isShutdownRequested():
            localLogger.debug(u'waiting')
            self._showTrailerEvent.wait()
            localLogger.debug(u'About to show')
            self._showTrailerEvent.clear()
            self._infoDialog.setTrailer(self._trailer)
            self._infoDialog.doModal()

    def show(self, trailer, displaySeconds=0):
        localLogger = self._logger.getMethodLogger(u'show')
        localLogger.enter()
        self._infoDialog.close()
        self._trailer = trailer
        self._showTrailerEvent.set()
        self._infoDialog.setTrailer(self._trailer)
        if displaySeconds == 0:
            # One year
            displaySeconds = 365 * 24 * 60 * 60

        self._timer = None
        if not Monitor.getSingletonInstance().isShutdownRequested():
            self._timer = threading.Timer(displaySeconds,
                                          self.dismiss, kwargs={u'reason': u'timeout'})
            self._timer.setName(u'InfoDialogTimer')
            self._timer.start()

    def dismiss(self, reason=None):
        localLogger = self._logger.getMethodLogger(u'dismiss')
        localLogger.enter()
        if self._timer:
            self._timer.cancel()
        if self._infoDialog is not None:
            self._infoDialog.close()
        self._trailerDialog.onInfoDialogClosed(reason=reason)

    # Not to be called from InfoDialogController thread
    def shutdownThread(self):
        localLogger = self._logger.getMethodLogger(u'shutdown')
        localLogger.enter()
        try:
            self.dismiss(u'SHUTDOWN')
            self._infoDialog.close()
            del self._infoDialog
            self._infoDialog = None
            self._showTrailerEvent.set()
            if self._timer is not None:
                self._timer.cancel()
        except:
            localLogger.logException()


class InfoDialog(xbmcgui.WindowXMLDialog, BaseWindow):
    def __init__(self, *args, **kwargs):
        # get the optional data and add it to a variable you can use elsewhere
        # in your script
        self._logger = Logger(self.__class__.__name__)
        localLogger = self._logger.getMethodLogger(u'__init__')
        localLogger.enter()
        self._controller = kwargs.get(u'controller', None)

    def onInit(self):
        self.show()

    def show(self):
        try:
            Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

            localLogger = self._logger.getMethodLogger(u'onInit')
            localLogger.enter()
            localLogger.debug(TRACE_STRING)

            control = self.getControl(38001)
            thumbnail = self._trailer[Movie.THUMBNAIL]
            control.setImage(thumbnail)

            self.getControl(38003).setImage(self._trailer[Movie.FANART])

            title_font = getTitleFont()
            title_string = self._trailer[Movie.DETAIL_TITLE]
            title = xbmcgui.ControlLabel(
                10, 40, 760, 40, title_string, title_font)
            title = self.addControl(title)

            title = self.getControl(38002)
            title.setAnimations(
                [('windowclose', 'effect=fade end=0 time=1000')])

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
            localLogger.debug(TRACE_STRING + u'exiting')

            self.setFocusId(38001)

            # if InfoDialog.timeOut:
            # if not Monitor.getSingletonInstance().isShutdownRequested():
            #   time.sleep(Settings.getTimeToDisplayDetailInfo())

        except:
            localLogger.logException()
        finally:
            pass

    def setTrailer(self, trailer):
        self._trailer = trailer

    def dismiss(self, reason=None):
        self._controller.dismiss(reason)

    #
    # Does not appear to work

    def getFocus(self, control):
        localLogger = self._logger.getMethodLogger(u'getFocus')
        localLogger.debug(u' DO NOT USE.')
        return
        result = super(InfoDialog, self).getFocus(control)
        localLogger.debug(u' result:' + result)
        return result

    def setFocus(self, control):
        localLogger = self._logger.getMethodLogger(u'setFocus')
        try:
            localLogger.enter()
            super(InfoDialog, self).setFocus(control)
        except:
            localLogger.logException()

    def setFocusId(self, controlId):
        localLogger = self._logger.getMethodLogger(u'setFocusId')
        try:
            result = super(InfoDialog, self).setFocusId(controlId)
            localLogger.debug(u' result:', result)
        except:
            localLogger.logException()

    def onClick(self, controlId):
        localLogger = self._logger.getMethodLogger(u'onClick')
        localLogger.debug(u' controlID: ', str(controlId))

    def onBack(self, actionId):
        localLogger = self._logger.getMethodLogger(u'onBack')

        localLogger.debug(u'actionId: ', str(actionId))

    def onControl(self, control):
        localLogger = self._logger.getMethodLogger(u'onControl')

        localLogger.debug(u'controlId: ' + str(control.getId()))

    def onFocus(self, controlId):
        localLogger = self._logger.getMethodLogger(u'onFocus')
        localLogger.debug(u' controlId:' + controlId)

    def onDeinitWindow(self, windowId):
        localLogger = self._logger.getMethodLogger(u'onDeinitWindow')
        localLogger.debug(u'windowId:', windowId)

    def OnDeinitWindow(self, windowId):
        localLogger = self._logger.getMethodLogger(u'OnDeinitWindow')
        localLogger.debug(u'windowId:', windowId)

    def onAction(self, action):
        localLogger = self._logger.getMethodLogger(u'onAction')
        localLogger.debug(u' Action.id: ' +
                          str(action.getId()) + u' Action.buttonCode: ' + str(action.getButtonCode()))

        actionMapper = Action.getInstance()
        matches = actionMapper.getKeyIDInfo(action)
        for line in matches:
            localLogger.debug(line)

        actionId = action.getId()
        buttonCode = action.getButtonCode()
        if (actionId == xbmcgui.ACTION_PREVIOUS_MENU or actionId == xbmcgui.ACTION_NAV_BACK):
            localLogger.debug(u'Exiting RandomTrailers at user request')
            self.exitRandomTrailers()

        elif actionId == xbmcgui.ACTION_QUEUE_ITEM:
            localLogger.debug(u'ACTION_Q')
            strCouchPotato = 'plugin://plugin.video.couchpotato_manager/movies/add?title=' + \
                self._trailer[Movie.TITLE]
            #xbmc.executebuiltin('XBMC.RunPlugin(' + strCouchPotato + ')')

        # ACTION_I or actionId == ACTION_DOWN:
        elif actionId == xbmcgui.ACTION_SHOW_INFO:
            localLogger.debug(TRACE_STRING +
                              u'ACTION_SHOW_INFO. Closing dialog, calling dismiss')
            self.close()
            self.dismiss(reason=u'Dismiss Info')

        # ACTION_I or actionId == ACTION_DOWN:
        elif buttonCode == 61513:
            localLogger.debug(TRACE_STRING +
                              u'keyboard "i". Closing dialog, calling dismiss')
            self.close()
            self.dismiss(reason=u'Dismiss Info')

        elif actionId == xbmcgui.ACTION_ENTER:
            localLogger.debug(u'Playing movie for currently playing trailer.')
            movieFile = self._trailer[Movie.FILE]
            if movieFile == u'':
                self.notifyUser(u'Movie not available for playing trailer')
            else:
                self.playMovie(self._trailer)

        elif actionId == xbmcgui.ACTION_STOP or actionId == xbmcgui.ACTION_MOVE_RIGHT:
            localLogger.debug(u'Play next trailer at user\'s request')
            self._player.stop()

            # self.close()
            # self._player.onAction(action)
            # self.dismiss(reason=u'STOP')

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
            self.addToPlaylist(actionId)


def playTrailers():
    myTrailerDialog = None
    localLogger = logger.getMethodLogger(u'playTrailers')

    numberOfTrailersToPlay = Settings.getNumberOfTrailersToPlay()
    GROUP_TRAILERS = False
    if Constants.ADDON.getSetting(u'group_trailers') == u'true':
        GROUP_TRAILERS = True
    GROUP_NUMBER = int(Constants.ADDON.getSetting(u'group_number'))
    trailersInGroup = GROUP_NUMBER
    GROUP_DELAY = Settings.getGroupDelay()
    _player = AdvancedPlayer()
    suppressOpenCurtain = True  # Already played at startup
    try:
        while not Monitor.getSingletonInstance().isShutdownRequested():
            if not suppressOpenCurtain and Settings.getShowCurtains():
                localLogger.debug(u'Playing OpenCurtain')
                _player.play(Settings.getOpenCurtainPath())

            suppressOpenCurtain = False  # Open curtain before each group
            while not Monitor.getSingletonInstance().isShutdownRequested():
                Monitor.getSingletonInstance().throwExceptionIfShutdownRequested()

                if GROUP_TRAILERS:
                    trailersInGroup = trailersInGroup - 1

                localLogger.debug(u'Created and showed BlankWindow')
                myTrailerDialog = TrailerDialog(player=_player,
                                                numberOfTrailersToPlay=numberOfTrailersToPlay)
                myTrailerDialog.doModal()
                # myTrailerDialog.doIt()

                del myTrailerDialog
                myTrailerDialog = None
                if GROUP_TRAILERS and trailersInGroup == 0:
                    trailersInGroup = GROUP_NUMBER
                    i = GROUP_DELAY
                    while i > 0 and not Monitor.getSingletonInstance().waitForShutdown(0.500):
                        i = i - 500

            if not Monitor.getSingletonInstance().isShutdownRequested():
                if Settings.getShowCurtains():
                    localLogger.debug(u'Playing CloseCurtain')
                    _player.play(Settings.getCloseCurtainPath())
                    _player.waitForIsNotPlayingVideo()

    finally:
        if myTrailerDialog is not None:
            del myTrailerDialog
            localLogger.exit()


def check_for_xsqueeze():
    localLogger = logger.getMethodLogger(u'check_for_xsqueeze')
    localLogger.enter()
    KEYMAPDESTFILE = os.path.join(xbmc.translatePath(
        u'special://userdata/keymaps'), "xsqueeze.xml")
    if os.path.isfile(KEYMAPDESTFILE):
        return True
    else:
        return False

#
# MAIN program
#

# Don't start if Kodi is busy playing something


def myMain():
    Logger.setAddonName(Constants.addonName)
    localLogger = logger.getMethodLogger(u'myMain')

    localLogger.debug(u'ADDON_PATH: ' + Constants.ADDON_PATH)

    bs = None
    try:

        if not xbmc.Player().isPlaying() and not check_for_xsqueeze():
            localLogger.debug(u'Python path: ' + unicode(sys.path))
            Trace.configure()
            Trace.enable(Trace.STATS, Trace.TRACE)
            WatchDog.create()
            currentDialogId = xbmcgui.getCurrentWindowDialogId()
            currentWindowId = xbmcgui.getCurrentWindowId()
            localLogger.debug(u'CurrentDialogId, CurrentWindowId: ' + str(currentDialogId) +
                              u' ' + str(currentWindowId))

            bs = BlankWindow(u'script-BlankWindow.xml',
                             Constants.ADDON_PATH, u'Default')
            localLogger.debug(u'Activating BlankWindow')
            bs.show()

            if Settings.getAdjustVolume():
                muted = xbmc.getCondVisibility("Player.Muted")
                if not muted and Settings.getVolume() == 0:
                    xbmc.executebuiltin(u'xbmc.Mute()')
                else:
                    xbmc.executebuiltin(
                        u'XBMC.SetVolume(' + str(Settings.getVolume()) + ')')
            _player = AdvancedPlayer()
            if Settings.getShowCurtains():
                _player.play(Settings.getOpenCurtainPath())

            # See if user wants to restrict trailers to a
            # genre

            selectedGenre = u''
            if Settings.getFilterGenres():
                selectedGenre = promptForGenre()

            LoadTrailers(selectedGenre)

            # Finish curtain playing before proceeding
            if Settings.getShowCurtains():
                _player.waitForIsNotPlayingVideo()
            del _player
            playTrailers()
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
    except BaseException as e:
        localLogger.logException(e)

    finally:
        localLogger.debug(
            u'*********************** SHUTDOWN MAIN **************')
        WatchDog.shutdown()
        Playlist.shutdown()
        localLogger.debug(u'Stopping xbmc.Player')
        xbmc.Player().stop()
        localLogger.debug(u'Deleting black screen')
        if bs is not None:
            del bs
        localLogger.exit()
