from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import unicode
from xml.dom.minidom import Node
#from multiprocessing.pool import ThreadPool

import resource
#import threading
import time
import traceback
import urllib.request
import urllib.parse
# from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xml.dom.minidom
import string

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


class Constants:
    TOO_MANY_TMDB_REQUESTS = 25
    addonName = u'script.video.randomtrailers'
    ADDON = None
    ADDON_PATH = None
    TRAILER_INFO_DISPLAY_SECONDS = 6000
    SECONDS_BEFORE_RESHUFFLE = 1 * 60
    PLAY_LIST_LOOKBACK_WINDOW_SIZE = 10

    @staticmethod
    def staticInit():
        Constants.ADDON = xbmcaddon.Addon()  # Constants.addonName)
        Constants.ADDON_PATH = Constants.ADDON.getAddonInfo(
            u'path').decode(u'utf-8')


Constants.staticInit()
memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
xbmc.log(u'In randomtrailer init memory: ' + str(memory), xbmc.LOGNOTICE)


currentVolume = xbmc.getInfoLabel(u'Player.Volume')
currentVolume = int(
    (float(currentVolume.split(u' ')[0]) + 60.0) / 60.0 * 100.0)

selectedGenre = ''
exit_requested = False
movie_file = ''
opener = urllib.request.build_opener()
opener.addheaders = [('User-Agent', 'iTunes')]
APPLE_URL_PREFIX = "http://trailers.apple.com"
monitor = None


class AbortException(Exception):
    pass


class TrailerWindow(xbmcgui.Window):  # (xbmcgui.WindowXMLDialog):

    trailer = None
    source = None

    @staticmethod
    def setNumberOfTrailersToPlay(numberOfTrailersToPlay):
        TrailerWindow._numberOfTrailersToPlay = numberOfTrailersToPlay

    # [optional] this function is only needed of you are passing optional data to your window
    def __init__(self, *args, **kwargs):
        # get the optional data and add it to a variable you can use elsewhere
        # in your script
        xbmc.log("In TrailerWindow.__init__", xbmc.LOGDEBUG)

    def doIt(self, numberOfTrailersToPlay):
        xbmc.log('In doIt', xbmc.LOGDEBUG)
        self.numberOfTrailersToPlay = numberOfTrailersToPlay

        xbmc.log(
            'randomtrailers.TrailerWindow.onInit about to get TrailerManager.iterator',
            xbmc.LOGDEBUG)

        limitTrailersToPlay = False
        if self.numberOfTrailersToPlay == 0:
            limitTrailersToPlay = True

        i = 5
        while i > 0:
            i -= 1
            xbmc.Player().play('/movies/XBMC/Movies/30s/6,000 Enemies (1939)-trailer.mp4')
            xbmc.sleep(10000)
            xbmc.log('About to play youtube flick', xbmc.LOGDEBUG)
            xbmc.Player().play('plugin://plugin.video.youtube/?action=play_video&videoid=fAIX12F6958')
            xbmc.log('returned from  youtube flick', xbmc.LOGDEBUG)
            xbmc.sleep(10000)
            while xbmc.Player().isPlaying():
                xbmc.sleep(250)
            xbmc.log('complete showing youtube flick', xbmc.LOGDEBUG)

    def onInit(self):
        xbmc.log('In randomtrailers.TrailerWindow.onInit', xbmc.LOGNOTICE)


class BlankWindow(xbmcgui.WindowXML):

    def onInit(self):
        pass

#
# MAIN program
#

# Don't start if Kodi is busy playing something


try:
    # bs = BlankWindow(u'script-BlankWindow.xml',
    #                 Constants.ADDON_PATH, u'default',)
    # bs.show()

    w = TrailerWindow()
    w.doIt(2)
    '''
    i = 5
    while i > 0:
        i -= 1
        xbmc.log('About to play movie', xbmc.LOGDEBUG)
        xbmc.Player().play('/movies/XBMC/Movies/30s/6,000 Enemies (1939)-trailer.mp4')

        xbmc.sleep(10000)
        xbmc.log('About to play youtube flick', xbmc.LOGDEBUG)
        xbmc.Player().play('plugin://plugin.video.youtube/?action=play_video&videoid=fAIX12F6958')
        xbmc.log('returned from  youtube flick', xbmc.LOGDEBUG)
        xbmc.sleep(10000)

    while xbmc.Player().isPlaying():
        xbmc.sleep(250)
        xbmc.log('complete showing youtube flick', xbmc.LOGDEBUG)
    '''
except AbortException:
    xbmc.log('Random Trailers: ' +
             'Exiting Random Trailers Screen Saver due to Kodi Abort!', xbmc.LOGNOTICE)
