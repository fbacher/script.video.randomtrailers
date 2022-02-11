# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: Frank Feuerbacher
'''


from common.constants import Constants
from common.imports import *
from common.logger import *

import xbmc
import xbmcgui

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class BlackBackground(xbmcgui.WindowXML):
    """
        Ensure a nice black window behind our player and transparent
        TrailerDialog. Keeps the Kodi screen from showing up from time
        to time (between trailers, etc.).
    """

    _instance = None
    _destroyed: bool = False
    _window_id: str = None

    @staticmethod
    def get_instance() -> ForwardRef('BlackBackground'):
        """

        :return:
        """
        if BlackBackground._instance is None and not BlackBackground._destroyed:
            BlackBackground._instance = BlackBackground('script-BlankWindow.xml',
                                                        Constants.ADDON_PATH, 'Default')
        return BlackBackground._instance

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """

        :param args:
        :param kwargs:
        """
        super().__init__(*args)
        self._logger = module_logger.getChild(type(self).__name__)
        BlackBackground._instance = self
        type(self)._window_id = xbmcgui.getCurrentWindowId()
        self.set_visibility(opaque=True)

    def onInit(self) -> None:
        """

        :return:
        """

    def close(self) -> None:
        """

        :return:
        """
        super().close()

    def destroy(self) -> None:
        """

        :return:
        """
        del BlackBackground._instance
        BlackBackground._instance = None
        BlackBackground._destroyed = True

    def show(self) -> None:
        super().show()

    def set_visibility(self, opaque: bool = False) -> None:
        """
            Controls the visible elements of TrailerDialog

        :param opaque:
        :return:
        """
        if opaque:
            command = "Skin.SetBool(Opaque)"
        else:
            command = "Skin.Reset(Opaque)"
        self._logger.debug(f'Setting Opaque: {command}')
        xbmc.executebuiltin(command)

    @classmethod
    def get_window_id(cls) -> str:
        """

        :return:
        """
        return str(cls._window_id)

