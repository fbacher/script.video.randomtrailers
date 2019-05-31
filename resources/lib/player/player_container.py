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
<<<<<<< HEAD
    def get_instance():
=======
    def getInstance():
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
        if PlayerContainer._instance is None:
            PlayerContainer._instance = PlayerContainer()
        return PlayerContainer._instance

    def __init__(self):
        self._logger = Logger(self.__class__.__name__)
        self._player = MyPlayer()
<<<<<<< HEAD
        self._is_dummy_player = False
        self._saved_player = None

    def get_player(self):
        return self._player

    def get_saved_player(self):
        player = self._player
        if player is None:
            player = self._saved_player
=======
        self._isDummyPlayer = False
        self._savedPlayer = None

    def getPlayer(self):
        return self._player

    def getSavedPlayer(self):
        player = self._player
        if player is None:
            player = self._savedPlayer
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7

        return player

    def delete(self):
<<<<<<< HEAD
        del self._saved_player
        del self._player

    def is_dummy_player(self):
        return self._is_dummy_player

    def use_dummy_player(self, delete=False):
        local_logger = self._logger.get_method_logger(u'use_dummy_player')
        local_logger.enter(u'delete:', delete)

        self._saved_player = self._player
        self._player = DummyPlayer()
        self._is_dummy_player = True
        self._saved_player.setCallBacks()
        self._saved_player.disableAdvancedMonitoring()
        if delete:
            del self._saved_player
            self._saved_player = None
=======
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
>>>>>>> f4a945295c369f68f26fda46ea22b0ac34eb3de7
