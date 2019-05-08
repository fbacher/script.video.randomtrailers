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

from typing import Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence
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
