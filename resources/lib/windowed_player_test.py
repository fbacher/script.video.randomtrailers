'''
Created on Mar 1, 2019

@author: fbacher
'''
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
from common.messages import Messages
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
#import xbmcdrm
import string
import action_map


REMOTE_DBG = False

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        xbmc.log(u'Trying to attach to debugger', xbmc.LOGDEBUG)
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


addon = xbmcaddon.Addon()
path = addon.getAddonInfo('path').decode("utf-8")
libPath = os.path.join(path, "resources", "lib")
curtainPath = os.path.join(path, "resources", "media",
                           "CurtainOpeningSequence.flv").decode(u'utf-8')


class MyDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        super(MyDialog, self).__init__(*args, **kwargs)
        self._control = None

    def onInit(self):
        try:
            xbmc.log(u'In MyDialog.onInit'.encode(u'utf-8'), xbmc.LOGDEBUG)

            # _720p = 0X1  # 1280 X 720
            self.getTitleControl(
                text=u'pigs fly Out of my Window').setVisible(True)

            self._thread = threading.Thread(
                target=self.playTrailers, name='MyDialog')
            self._thread.start()
        except:
            Logger.logException()

    def playTrailers(self):
        try:
            xbmc.log(u'In MyDialog.playTrailers'.encode(
                u'utf-8'), xbmc.LOGDEBUG)
            global curtainPath

            windowstring = Utils.getKodiJSON(
                '{"jsonrpc":"2.0","method":"GUI.GetProperties",\
                "params":{"properties":["currentwindow"]},"id":1}')

            self.getTitleControl(
                text=u'pigs fly Out of my Window').setVisible(True)
            xbmc.log(u'In MyDialog.playTrailers about to show'.encode(
                u'utf-8'), xbmc.LOGDEBUG)

            xbmc.log(u'In MyDialog.playTrailers about to play'.encode(
                u'utf-8'), xbmc.LOGDEBUG)

            # This play will fail

            xbmc.Player().play(u'/home/fbacher/dwhelper/A Star Is Born - Movie Trailers - iTunes.m4v'.encode(u'utf-8'), windowed=True)

            xbmc.log(u'In MyDialog.playTrailers waiting 60 seconds after play'.encode(
                u'utf-8'), xbmc.LOGDEBUG)

            xbmc.sleep(60000)
            xbmc.log(u'In MyDialog.playTrailers exiting'.encode(
                u'utf-8'), xbmc.LOGDEBUG)

            self.close()
        except:
            Logger.logException()

    def getTitleControl(self, text=u''):
        xbmc.log(u'In MyDialog.getTitleControl'.encode(
            u'utf-8'), xbmc.LOGDEBUG)

        if self._control is None:
            xbmc.log(
                u'In MyDialog.getTitleControl- _control null'.encode(u'utf-8'), xbmc.LOGDEBUG)

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
            xbmc.log(u'In MyDialog.getTitleControl addingControl'.encode(
                u'utf-8'), xbmc.LOGDEBUG)

            self.addControl(self._control)

        xbmc.log(u'In MyDialog.getTitleControl Exit'.encode(
            u'utf-8'), xbmc.LOGDEBUG)

        return self._control


class BlankWindow(xbmcgui.WindowXML):
    pass

#
# MAIN program
#

# Don't start if Kodi is busy playing something


def myMain():
    global curtainPath

    #xbmc.Player().play(u'/home/fbacher/dwhelper/A Star Is Born - Movie Trailers - iTunes.m4v'.encode(u'utf-8'), windowed=True)
    #idx = xbmcgui.getCurrentWindowId()
    #msg = u'currentWindowID: ' + str(idx)
    #xbmc.log(msg.encode(u'utf-8'), xbmc.LOGDEBUG)
    # xbmc.sleep(15)
    #dialog = MyDialog()
    # dialog.playTrailers()
    # dialog.doModal()

    bs = BlankWindow(u'script-BlankWindow.xml',
                     Constants.ADDON_PATH, u'Default')
    bs.show()

    idx = xbmcgui.getCurrentWindowId()
    msg = u'currentWindowID: ' + str(idx)
    xbmc.log(msg.encode(u'utf-8'), xbmc.LOGDEBUG)

    xbmc.log(u'In myMain about to create MyDialog'.encode(
        u'utf-8'), xbmc.LOGDEBUG)

    dialog = MyDialog(u'script-trailerwindow.xml',
                      Constants.ADDON_PATH, u'Default')
    # xbmc.log(u'About to call MyDialog.playTrailers'.encode(
    #    u'utf-8'), xbmc.LOGDEBUG)

    # dialog.playTrailers()
    #xbmc.log(u'In myMain about to doModal'.encode(u'utf-8'), xbmc.LOGDEBUG)

    #idx = xbmcgui.getCurrentWindowId()
    #msg = u'currentWindowID: ' + str(idx)
    #xbmc.log(msg.encode(u'utf-8'), xbmc.LOGDEBUG)

    xbmc.log(u'about to doModal'.encode(u'utf-8'), xbmc.LOGDEBUG)
    dialog.doModal()

    idx = xbmcgui.getCurrentWindowId()
    msg = u'After doModal currentWindowID: ' + str(idx)
    xbmc.log(msg.encode(u'utf-8'), xbmc.LOGDEBUG)

    xbmc.log(u'In myMain about to sleep 2 seconds'.encode(
        u'utf-8'), xbmc.LOGDEBUG)

    xbmc.sleep(2000)
    xbmc.log(u'In myMain about to exit'.encode(u'utf-8'), xbmc.LOGDEBUG)

    # This will play
