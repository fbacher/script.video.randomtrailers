# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: Frank Feuerbacher
'''
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import (Logger, LazyLogger, Trace)
from common.messages import Messages
from common.monitor import Monitor
from action_map import Action
from common.settings import Settings
from player.player_container import PlayerContainer

from frontend.utils import ReasonEvent, BaseWindow, ScreensaverManager, ScreensaverState

import sys
import threading
from kodi_six import xbmc, xbmcgui

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild('frontend.black_background')
else:
    module_logger = LazyLogger.get_addon_module_logger()


# noinspection Annotator,Annotator
class BlackBackground(xbmcgui.WindowXML):
    """
        Ensure a nice black window behind our player and transparent
        TrailerDialog. Keeps the Kodi screen from showing up from time
        to time (between trailers, etc.).
    """

    _instance = None
    _destroyed = False

    @staticmethod
    def get_instance():
        # type: () -> BlackBackground
        """

        :return:
        """
        if BlackBackground._instance is None and not BlackBackground._destroyed:
            BlackBackground._instance = BlackBackground('script-BlankWindow.xml',
                                                        Constants.ADDON_PATH, 'Default')
        return BlackBackground._instance

    def __init__(self, *args, **kwargs):
        # type: (...) ->  None
        """

        :param args:
        :param kwargs:
        """
        super().__init__(*args)
        self._logger = module_logger.getChild(self.__class__.__name__)
        BlackBackground._instance = self
        self._windowId = xbmcgui.getCurrentWindowId()
        self.set_visibility(opaque=True)

    def onInit(self):
        # type: () -> None
        """

        :return:
        """
        # self._windowId = xbmcgui.getCurrentWindowId()
        # self.set_visibility(opaque=True)

    def close(self):
        # type: () -> None
        """

        :return:
        """
        self._logger.enter()
        super().close()

    def destroy(self):
        # type: () -> None
        """

        :return:
        """
        del BlackBackground._instance
        BlackBackground._instance = None
        BlackBackground._destroyed = True

    def show(self):
        self._logger.enter()
        super().show()

    def set_visibility(self, opaque=False):
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

    def get_window_id(self):
        # type: () -> TextType
        """

        :return:
        """
        return str(self._windowId)
