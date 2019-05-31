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
    def get_instance():
        if PlayerContainer._instance is None:
            PlayerContainer._instance = PlayerContainer()
        return PlayerContainer._instance

    def __init__(self):
        self._logger = Logger(self.__class__.__name__)
        self._player = MyPlayer()
        self._is_dummy_player = False
        self._saved_player = None

    def get_player(self):
        return self._player

    def get_saved_player(self):
        player = self._player
        if player is None:
            player = self._saved_player

        return player

    def delete(self):
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
