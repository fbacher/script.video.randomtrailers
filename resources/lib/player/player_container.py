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
from common.logger import Logger
from player.my_player import MyPlayer
from player.dummy_player import DummyPlayer


class PlayerContainer(object):
    _instance = None
    @staticmethod
    def getInstance():
        if PlayerContainer._instance is None:
            PlayerContainer._instance = PlayerContainer()
        return PlayerContainer._instance

    def __init__(self):
        self._logger = Logger(self.__class__.__name__)
        self._player = MyPlayer()
        self._isDummyPlayer = False
        self._savedPlayer = None

    def getPlayer(self):
        return self._player

    def getSavedPlayer(self):
        player = self._player
        if player is None:
            player = self._savedPlayer

        return player

    def delete(self):
        del self._savedPlayer
        del self._player

    def isDummyPlayer(self):
        return self._isDummyPlayer

    def useDummyPlayer(self, delete=False):
        localLogger = self._logger.getMethodLogger(u'useDummyPlayer')
        localLogger.enter(u'delete:', delete)

        self._savedPlayer = self._player
        self._player = DummyPlayer()
        self._isDummyPlayer = True
        self._savedPlayer.setCallBacks()
        self._savedPlayer.disableAdvancedMonitoring()
        if delete:
            del self._savedPlayer
            self._savedPlayer = None
