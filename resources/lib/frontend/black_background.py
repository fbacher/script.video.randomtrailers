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

from frontend.utils import ReasonEvent, BaseWindow, ScreensaverManager, ScreensaverState

import sys
import threading
from kodi_six import xbmc, xbmcgui


class BlackBackground(xbmcgui.WindowXML):
    """
        Ensure a nice black window behind our player and transparent
        TrailerDialog. Keeps the Kodi screen from showing up from time
        to time (between trailers, etc.).
    """

    _instance = None

    @staticmethod
    def getInstance():
        # type: () -> BlackBackground
        """

        :return:
        """
        if BlackBackground._instance is None:
            BlackBackground._instance = BlackBackground(u'script-BlankWindow.xml',
                                                        Constants.ADDON_PATH, u'Default')
        return BlackBackground._instance

    def __init__(self, *args, **kwargs):
        # type: (...) ->  None
        """

        :param args:
        :param kwargs:
        """
        super().__init__(*args)
        self._logger = Logger(self.__class__.__name__)
        BlackBackground._instance = self
        self._windowId = xbmcgui.getCurrentWindowId()
        self.setVisibility(opaque=True)

    def onInit(self):
        # type: () -> None
        """

        :return:
        """
        # self._windowId = xbmcgui.getCurrentWindowId()
        # self.setVisibility(opaque=True)

    def close(self):
        # type: () -> None
        """

        :return:
        """
        localLogger = self._logger.getMethodLogger(u'BlankWindow.close')
        localLogger.enter()
        super().close()

    def destroy(self):
        # type: () -> None
        """

        :return:
        """
        del BlackBackground._instance
        BlackBackground._instance = None

    def show(self):
        localLogger = self._logger.getMethodLogger(u'BlankWindow.show')
        localLogger.enter()
        super().show()

    def setVisibility(self, opaque=False):
        # type: (bool) -> None
        """
            Controls the visible elements of TrailerDialog

        :param opaque:
        :return:
        """
        if opaque:
            command = "Skin.SetBool(Opaque)"
        else:
            command = "Skin.Reset(Opaque)"
        xbmc.executebuiltin(command)

    def getWindowId(self):
        # type: () -> TextType
        """

        :return:
        """
        return str(self._windowId)
