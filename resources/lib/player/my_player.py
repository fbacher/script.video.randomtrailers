# -*- coding: utf-8 -*-
import os
import threading
from abc import ABC

import xbmcgui

from common.imports import *
from common.movie import AbstractMovie
from player.advanced_player import AdvancedPlayer
from common.logger import *
from common.disk_utils import DiskUtils
from .__init__ import *

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class MyPlayer(AdvancedPlayer, ABC):
    """

    """
    _logger: BasicLogger = None

    def __init__(self) -> None:
        """

        """
        super().__init__()
        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(self.__class__.__name__)

        self._expected_title: str = None
        self._expected_file_path: str = None
        self._is_url: bool = False
        self._listener_lock: threading.RLock = threading.RLock()
        self._listeners: List[Callable[[Any], Any]] = []

    def play_trailer(self, path: str, trailer: AbstractMovie) -> None:
        """

        :param path:
        :param trailer:
        :return:
        """
        clz = type(self)
        title: str = trailer.get_title()
        if trailer.has_normalized_trailer():
            file_path = trailer.get_normalized_trailer_path()
        elif trailer.has_cached_trailer():
            file_path = trailer.get_cached_trailer()
        else:
            file_path = trailer.get_trailer_path()

        file_name: str = os.path.basename(file_path)
        passed_file_name: str = os.path.basename(path)
        if file_name != passed_file_name:
            if clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'passed file name: {passed_file_name} '
                                                f'trailer file_name: {file_name}')

        listitem: xbmcgui.ListItem = xbmcgui.ListItem(title)
        listitem.setInfo(
            'video', {'title': title, 'genre': 'randomtrailers',
                      'Genre': 'randomtrailers',
                      'trailer': passed_file_name, 'path': path,
                      'mediatype': 'video', 'tag': 'randomtrailers'})

        listitem.setPath(file_path)

        self.set_playing_title(title)
        self.set_playing_file_path(file_path)
        if clz._logger.isEnabledFor(DISABLED):
            clz._logger.debug_extra_verbose(
                'path:', file_name, 'title:', title)

        self.play(item=path, listitem=listitem)

    def play(self, item: str = "",
             listitem: xbmcgui.ListItem = None,
             windowed: bool = False,
             startpos: int = -1) -> None:
        """

        :param item:
        :param listitem:
        :param windowed:
        :param startpos:
        :return:
        """
        clz = type(self)
        title = listitem.getLabel()
        clz._logger.debug(f'Playing: {title} path: {item}',
                          trace=Trace.TRACE_PLAY_STATS)
        super().play(item, listitem, windowed, startpos)

    def set_playing_title(self, title: str) -> None:
        """

        :param title:
        :return:
        """
        self._expected_title = title

    def set_playing_file_path(self, file_path: str) -> None:
        """

        :param file_path:
        :return:
        """
        file_path = file_path
        self._is_url = DiskUtils.is_url(file_path)
        self._expected_file_path = file_path

    # def is_playing_trailer(self, path: str) -> bool:
    #     if self._is_playing and self._expected_file_path == path:
    #         return True
    #     return False

    def onAVStarted(self) -> None:
        """
            Detect when the player is playing something not initiated by this
            script. This can be due to a JSON RPC call or similar.Starting the
            player via keyboard or remote (that does not use JSON RPC)is
            detected by other means (onAction).

            Compare the video that the player is playing versus what we expect
            it to play. If they don't match, then assume that something else
            launched the video.

        :return:
        """
        clz = type(self)
        try:
            # All local trailers played by Random Trailers will have a fake genre of
            # 'randomtrailers'. However, if a video is from a remote source
            # such that youtube plugin does the actual playing, then the
            # genre will NOT be set to 'randomtrailers'. The use of caching
            # of remote trailers will eliminate this issue.

            super().onAVStarted()
            clz._logger.debug(f'onAVStarted path: {self.getPlayingFile()}')
            genre: str = self.getVideoInfoTag().getGenre()
            # clz._logger.debug('genre:', genre)
            if genre != 'randomtrailers':
                playing_file: str = super().getPlayingFile()
                if not (self._is_url and DiskUtils.is_url(playing_file)):
                    if clz._logger.isEnabledFor(DEBUG):
                        clz._logger.debug(
                            'Player is playing video:', playing_file)
                    self.notify_non_random_trailer_video()
        except Exception as e:
            pass

    def register_exit_on_movie_playing(self, listener: Callable[[Any], Any])-> None:
        """
            Exit quickly when the player is launched via JSON RPC call, or
            otherwise.
        :param listener:
        :return:
        """
        clz = type(self)
        with self._listener_lock:
            self._listeners.append(listener)

    def notify_non_random_trailer_video(self) -> None:
        clz = type(self)
        for listener in self._listeners:
            try:
                listener()
            except Exception as e:
                clz._logger.exception('')

    def dump_data(self, context: str) -> None:
        """

        :param context:
        :return:
        """
        clz = type(self)
        try:
            if self.isPlayingVideo():
                info_tag_video = self.getVideoInfoTag()
                if clz._logger.isEnabledFor(DEBUG):
                    clz._logger.debug(f'context: {context} '
                                      f'title: {info_tag_video.getTitle()} '
                                      f'genre: {info_tag_video.getGenre()} '
                                      f'trailer: {info_tag_video.getTrailer()}')
            else:
                if clz._logger.isEnabledFor(DEBUG):
                    clz._logger.debug('Not playing video')
        except Exception as e:
            clz._logger.exception('')
