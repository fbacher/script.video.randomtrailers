# -*- coding: utf-8 -*-
import os
import threading
import xbmcgui

from common.imports import *
from player.advanced_player import AdvancedPlayer
from common.logger import LazyLogger, Trace
from common.constants import Movie
from common.disk_utils import DiskUtils

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class MyPlayer(AdvancedPlayer):
    """

    """
    _logger: LazyLogger = None

    def __init__(self) -> None:
        """

        """
        super().__init__()
        clz = type(self)
        if clz._logger is None:
            clz._logger: LazyLogger = module_logger.getChild(self.__class__.__name__)

        self._expected_title: str = None
        self._expected_file_path: str = None
        self._is_url: bool = False
        self._is_activated: bool = True
        self._listener_lock: threading.RLock = threading.RLock()
        self._listeners: List[Callable[[Any], Any]] = []

    def play_trailer(self, path: str, trailer: MovieType) -> None:
        """

        :param path:
        :param trailer:
        :return:
        """
        clz = type(self)
        title: str = trailer[Movie.TITLE]
        if trailer.get(Movie.NORMALIZED_TRAILER) is not None:
            file_path = trailer[Movie.NORMALIZED_TRAILER]
        elif trailer.get(Movie.CACHED_TRAILER) is not None:
            file_path = trailer[Movie.CACHED_TRAILER]
        else:
            file_path = trailer[Movie.TRAILER]

        file_name: str = os.path.basename(file_path)
        passed_file_name: str = os.path.basename(path)
        if file_name != passed_file_name:
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose('passed file name:',
                                                 passed_file_name,
                                                 'trailer file_name:',
                                                 file_name,)

        listitem: xbmcgui.ListItem = xbmcgui.ListItem(title)
        listitem.setInfo(
            'video', {'title': title, 'genre': 'randomtrailers',
                      'Genre': 'randomtrailers',
                      'trailer': passed_file_name, 'path': path,
                      'mediatype': 'video', 'tag': 'randomtrailers'})
        listitem.setPath(file_path)

        self.set_playing_title(title)
        self.set_playing_file_path(file_path)
        if clz._logger.isEnabledFor(LazyLogger.DISABLED):
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

    def onAVStarted(self) -> None:
        """
            Detect when the player is playing something not initiated by this
            script. This can be due to a JSON RPC call or similar.Starting the
            player via keyboard or remote (that does not use JSON RPC)is
            detected by other means (onAction).

            Compare the movie that the player is playing versus what we expect
            it to play. If they don't match, then assume that something else
            launched the movie.

        :return:
        """
        clz = type(self)
        try:
            # All local trailers played by Random Trailers will have a fake genre of
            # 'randomtrailers'. However, if a trailer is from a remote source
            # such that youtube plugin does the actual playing, then the
            # genre will NOT be set to 'randomtrailers'. The use of caching
            # of remote trailers will eliminate this issue.

            genre: str = self.getVideoInfoTag().getGenre()
            # clz._logger.debug('genre:', genre)
            if genre != 'randomtrailers':
                playing_file: str = super().getPlayingFile()
                if not (self._is_url and DiskUtils.is_url(playing_file)):
                    self._is_activated = False
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                        clz._logger.debug(
                            'Player is playing movie:', playing_file)
                    self.notify_non_random_trailer_video()
        except Exception as e:
            pass

    def register_exit_on_movie_playing(self,
                                       listener: Callable[[Any], Any]) -> None:
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
                clz.exception('')

    def dump_data(self, context: str) -> None:
        """

        :param context:
        :return:
        """
        clz = type(self)
        try:
            if self.isPlayingVideo():
                info_tag_video = self.getVideoInfoTag()
                if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                    clz._logger.debug('context:', context, 'title:',
                                       info_tag_video.getTitle(),
                                       'genre:', info_tag_video.getGenre(),
                                       'trailer:', info_tag_video.getTrailer())
            else:
                if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                    clz._logger.debug('Not playing video')
        except Exception as e:
            clz._logger.exception('')

    def is_activated(self) -> bool:
        """

        :return:
        """
        return self._is_activated
