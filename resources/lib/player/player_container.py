# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

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

    def register_exit_on_movie_playing(self, listener):
        # type: (Callable[[Union[Any, None]], Union[Any, None]]) -> None
        """

        :param listener:
        :return:
        """

        self._player.register_exit_on_movie_playing(listener)

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
        local_logger = self._logger.get_method_logger('use_dummy_player')
        local_logger.enter('delete:', delete)

        self._saved_player = self._player
        self._player = DummyPlayer()
        self._is_dummy_player = True
        self._saved_player.setCallBacks()
        self._saved_player.disableAdvancedMonitoring()
        if delete:
            del self._saved_player
            self._saved_player = None
