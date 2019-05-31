# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from kodi_six import xbmcgui, utils

from player.advanced_player import AdvancedPlayer
from common.logger import Logger
from common.constants import Movie
from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                                 TextType, MovieType, DEVELOPMENT, RESOURCE_LIB)
from common.disk_utils import DiskUtils
from common.monitor import Monitor
import os


# noinspection Annotator
class MyPlayer(AdvancedPlayer):
    """

    """
    def __init__(self):
        # type: () -> None
        """

        """
        super().__init__()
        self._logger = Logger(self.__class__.__name__)
        self._expected_title = None
        self._expected_file_path = None
        self._is_url = False
        self._is_activated = True

    def play_trailer(self, path, trailer):
        # type: (TextType, MovieType) -> None
        """

        :param path:
        :param trailer:
        :return:
        """
        local_logger = self._logger.get_method_logger(u'play_trailer')

        title = trailer[Movie.TITLE]
        file_path = trailer.get(Movie.NORMALIZED_TRAILER, None)
        if file_path is None:
            file_path = trailer[Movie.TRAILER]
        file_path = utils.py2_decode(file_path)
        file_name = os.path.basename(file_path)
        passed_file_name = utils.py2_decode(os.path.basename(path))
        if file_name != passed_file_name:
            local_logger.debug(u'passed file name:', passed_file_name,
                              u'trailer file_name:', file_name,)

        listitem = xbmcgui.ListItem(title)
        listitem.setInfo(
            u'video', {u'title': title, u'genre': u'randomtrailers',
            u'Genre': u'randomtrailers',
                       u'trailer': passed_file_name, u'path': utils.py2_decode(path),
                       u'mediatype': u'video', u'tag': u'randomtrailers'})
        listitem.setPath(file_path)

        self.set_playing_title(title)
        self.set_playing_file_path(file_path)
        local_logger.debug(u'path:', file_name, u'title:', title)

        self.play(item=path, listitem=listitem)

    def play(self, item="", listitem=None, windowed=False
             , startpos=-1):
        # type: (TextType, xbmcgui.ListItem, bool, int) -> None
        """

        :param item:
        :param listitem:
        :param windowed:
        :param startpos:
        :return:
        """
        super().play(item, listitem, windowed, startpos)

    def set_playing_title(self, title):
        # type: (TextType) ->None
        """

        :param title:
        :return:
        """
        self._expected_title = title

    def set_playing_file_path(self, file_path):
        # type: (TextType) -> None
        """

        :param file_path:
        :return:
        """
        file_path = utils.py2_decode(file_path)
        self._is_url = DiskUtils.is_url(file_path)
        self._expected_file_path = file_path

    def onAVStarted(self):
        # type: () ->None
        """

        :return:
        """
        local_logger = self._logger.get_method_logger(u'onAVStarted')

        self.dump_data(u'onAVStarted')

        try:
            genre = utils.py2_decode(self.getVideoInfoTag().getGenre())
            if genre != u'randomtrailers':
                playing_file = super().getPlayingFile()
                playing_file = utils.py2_decode(playing_file)
                if self._is_url and DiskUtils.is_url(playing_file):
                    local_logger.debug(u'URLs used. Consider pass')
                else:
                    # Do not use this player anymore until
                    self._is_activated = False
                    local_logger.debug(u'Genre and URL test failed.',
                                      u'Genre:', genre,
                                      u'playing_file:', playing_file,
                                      u'expectedPlayingFile:',
                                      self._expected_file_path)
                    Monitor.get_instance().onScreensaverDeactivated()
            else:
                local_logger.debug(u'Genre passed')
        except (Exception) as e:
            pass


    def is_playing_expected_title(self):
        # type: () -> bool
        """

        :return:
        """
        local_logger = self._logger.get_method_logger(u'is_playing_expected_title')

        playing_title = super().getPlayingTitle()
        video_info = super().getVideoInfoTag()
        if video_info is not None:
            title2 = utils.py2_decode(video_info.getTitle())
            local_logger.debug(u'title2:', title2, u'title:',
                              self._expected_title)
        if playing_title != self._expected_title:
            local_logger.debug(u'Expected to play:', self._expected_title, u'Playing:',
                              playing_title)
            return False
        else:
            return True

    def is_playing_expected_file(self):
        # type: () -> bool
        """

        :return:
        """
        local_logger = self._logger.get_method_logger(
            u'is_playing_expected_file')
        playing_file = super().getPlayingFile()
        playing_file = utils.py2_decode(playing_file)
        playing_file = os.path.basename(playing_file)
        video_info = super().getVideoInfoTag()
        if video_info is not None:
            playing_file2 = video_info.getFile()
            playing_file2 = utils.py2_decode(playing_file2)
            playing_file2 = os.path.dirname(playing_file2)
            local_logger.debug(u'expected:', self._expected_file_path, u'file2:',
                              playing_file2)
        if playing_file != os.path.dirname(self._expected_file_path):
            local_logger.debug(u'Expected to play:', self._expected_file_path, u'Playing:',
                              playing_file)
            return False
        else:
            return True


    def dump_data(self, context):
        # type: (TextType) -> None
        """

        :param context:
        :return:
        """
        local_logger = self._logger.get_method_logger(
            u'dump_data')
        try:
            if self.isPlayingVideo():
                infoTagVideo = self.getVideoInfoTag()
                local_logger.debug(u'context:', context, u'title:', infoTagVideo.getTitle(),
                              u'genre:', infoTagVideo.getGenre(),
                              u'trailer:', infoTagVideo.getTrailer())
            else:
                local_logger.debug(u'Not playing video')
        except (Exception) as e:
            local_logger.log_exception(e)

    def isActivated(self):
        # type: () -> bool
        """

        :return:
        """
        return self._is_activated
