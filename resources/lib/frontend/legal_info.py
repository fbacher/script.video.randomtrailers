# -*- coding: utf-8 -*-

'''
Created on Apr 17, 2019

@author: Frank Feuerbacher
'''


from common.constants import Constants, Movie
from common.exceptions import AbortException
from common.imports import *
from common.logger import (LazyLogger, Trace)

import xbmcgui

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection Annotator
class LegalInfo(xbmcgui.WindowXML):
    """
        Page shown at startup displaying legal information, such as logos, etc.
    """

    _instance = None
    _destroyed = False
    _window_id: str = None

    @staticmethod
    def get_instance():
        # type: () -> LegalInfo
        """

        :return:
        """
        if LegalInfo._instance is None and not LegalInfo._destroyed:
            LegalInfo._instance = LegalInfo('legal.xml',
                                            Constants.ADDON_PATH, 'Default')
        return LegalInfo._instance

    def __init__(self, *args, **kwargs):
        # type: (...) ->  None
        """

        :param args:
        :param kwargs:
        """
        super().__init__(*args)
        self._logger = module_logger.getChild(type(self).__name__)
        LegalInfo._instance = self
        type(self)._window_id = xbmcgui.getCurrentWindowId()

    def onInit(self):
        # type: () -> None
        """

        :return:
        """

    def close(self):
        # type: () -> None
        """

        :return:
        """
        super().close()

    def destroy(self):
        # type: () -> None
        """

        :return:
        """
        del LegalInfo._instance
        LegalInfo._instance = None
        LegalInfo._destroyed = True

    def show(self):
        super().show()
        label = self.getControl(38021)  # type: xbmcgui.ControlLabel
        label.setLabel('[B]Random Trailers is powered by:[/B]')


