# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
import xbmc

from common.imports import *
from common.logger import *
from player.abstract_player import AbstractPlayer
from player.my_player import MyPlayer
from player.dummy_player import DummyPlayer

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class PlayerContainer:
    _instance = None
    _logger: BasicLogger = None

    @staticmethod
    def get_instance() -> ForwardRef('PlayerContainer'):
        if PlayerContainer._instance is None:
            PlayerContainer._instance = PlayerContainer()
        return PlayerContainer._instance

    def __init__(self) -> None:
        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(self.__class__.__name__)

        self._player: Union[AbstractPlayer, xbmc.Player] = MyPlayer()
        self._is_dummy_player: bool = False
        self._saved_player: Union[AbstractPlayer, xbmc.Player] = None

    def register_exit_on_movie_playing(self, listener: Callable[[Any], Any]) -> None:
        """

        :param listener:
        :return:
        """

        self._player.register_exit_on_movie_playing(listener)

    def get_player(self) -> AbstractPlayer:
        return self._player

    def get_saved_player(self) -> xbmc.Player:
        player = self._player
        if player is None:
            player = self._saved_player

        return player

    def delete(self) -> None:
        del self._saved_player
        del self._player

    def is_dummy_player(self) -> bool:
        return self._is_dummy_player

    def use_dummy_player(self, delete=False):
        clz = type(self)
        if clz._logger.isEnabledFor(DEBUG):
            clz._logger.debug('delete:', delete)

        self._saved_player = self._player
        self._player = DummyPlayer()
        self._is_dummy_player = True
        self._saved_player.set_callbacks()
        self._saved_player.disable_advanced_monitoring()
        if delete:
            del self._saved_player
            self._saved_player = None

        if clz._logger.isEnabledFor(DEBUG):
            clz._logger.debug('exiting')
