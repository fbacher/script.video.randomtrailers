# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from future import standard_library
standard_library.install_aliases()  # noqa: E402

from common.logger import Logger
from player.my_player import MyPlayer
from player.dummy_player import DummyPlayer


class PlayerContainer():
    _instance = None
    @staticmethod
    def getInstance():
        if PlayerContainer._instance is None:
            PlayerContainer._instance = PlayerContainer()
        return PlayerContainer._instance

    def __init__(self):
        self._logger = Logger(self.__class__.__name__)
        self._player = MyPlayer()

    def getPlayer(self):
        return self._player

    def useDummyPlayer(self):
        localLogger = self._logger.getMethodLogger(u'useDummyPlayer')
        localLogger.enter()

        realPlayer = self._player
        self._player = DummyPlayer()
        realPlayer.setCallBacks()
        realPlayer.disableAdvancedMonitoring()
        del realPlayer
