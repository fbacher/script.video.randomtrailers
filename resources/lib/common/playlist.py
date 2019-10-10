# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from .imports import *

import datetime
import io
import os
import threading
import simplejson as json

from kodi_six import xbmc

from .constants import Constants, Movie
from .logger import (Logger, LazyLogger, Trace)
from .messages import Messages
from .disk_utils import DiskUtils
from .settings import (Settings)

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'common.playlist')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class Playlist(object):
    """

    Basic Playlist format:
    filename suffix is '.m3u'

    #EXTCPlayListM3U::M3U
    #EXTINF:0,Her Man
    /movies/XBMC/Movies/30s/Her Man (1930).avi
    #EXTINF:0,Inside the Lines
    /movies/XBMC/Movies/30s/Inside the Lines (1930).mkv
    #EXTINF:0,Lord Byron of Broadway
    /movies/XBMC/Movies/30s/Lord Byron of Broadway (1930)_1587.mkv

    """
    VIEWED_PLAYLIST_FILE = 'Viewed.playlist'
    MISSING_TRAILERS_PLAYLIST = 'missingTrailers.playlist'
    PLAYLIST_PREFIX = 'RandomTrailer_'
    PLAYLIST_SUFFIX = '.m3u'
    PLAYLIST_HEADER = '#EXTCPlayListM3U::M3U'
    PLAYLIST_ENTRY_PREFIX = '#EXTINF:0,'

    _playlist_lock = threading.RLock()
    _playlists = {}

    def __init__(self, *args, **kwargs):
        # type: (*TextType, **Any) -> None
        """

        :param args:
        :param kwargs:
        """
        self._logger = module_logger.getChild(self.__class__.__name__)

        if len(args) == 0:
            self._logger.error(
                ' Playlist constructor requires an argument')
            return

        playlist_name = args[0]
        self._playlist_name = playlist_name
        append = kwargs.get('append', True)
        rotate = kwargs.get('rotate', False)
        assert append ^ rotate
        self.playlist_format = kwargs.get('playlist_format', False)

        if self.playlist_format:
            path = Constants.PLAYLIST_PATH + '/' + playlist_name
        else:
            path = Constants.FRONTEND_DATA_PATH + '/' + playlist_name
        path = path.decode('utf-8')
        path = xbmc.validatePath(path)
        path = xbmc.translatePath(path)
        already_exists = False
        if append:
            mode = 'at'
            if os.path.exists(path):
                already_exists = True
        else:
            mode = 'wt'
        DiskUtils.create_path_if_needed(Constants.FRONTEND_DATA_PATH)
        if rotate:
            try:
                save_path = Constants.FRONTEND_DATA_PATH + '/' + playlist_name + '.old'
                save_path = save_path.decode('utf-8')
                save_path = xbmc.validatePath(save_path)
                try:
                    os.remove(save_path)
                except (Exception) as e:
                    self._logger.exception('')
                try:
                    os.rename(path, save_path)
                except (Exception) as e:
                    self._logger.exception('')
            except (Exception) as e:
                self._logger.exception('')

        self._file = io.open(path, mode=mode, buffering=1, newline=None,
                             encoding='utf-8')
        if not already_exists and self.playlist_format:
            line = Playlist.PLAYLIST_HEADER + '\n'
            self._file.writelines(line)

    @staticmethod
    def get_playlist(playlist_name, append=True, rotate=False, playlist_format=False):
        # type: (TextType, bool, bool, bool) -> Playlist
        """

        :param playlist_name:
        :param append:
        :param rotate:
        :param playlist_format:
        :return:
        """
        playlist = None
        with Playlist._playlist_lock:
            if Playlist._playlists.get(playlist_name) is None:
                Playlist._playlists[playlist_name] = Playlist(
                    playlist_name, append=append, rotate=rotate,
                    playlist_format=playlist_format)
            playlist = Playlist._playlists.get(playlist_name)
        return playlist

    def add_timestamp(self):
        # type: () -> None
        """

        :return:
        """
        now = datetime.datetime.now().strftime('%m/)%d/%y %H:%M:%S')
        self.writeLine('random trailers started: {!s}'.format(now))

    def record_played_trailer(self, trailer, use_movie_path=False, msg=''):
        # type: (Dict[TextType, Any], bool, TextType) -> None
        """

        :param trailer:
        :param use_movie_path:
        :param msg:
        :return:
        """
        name = trailer.get(Movie.TITLE, 'unknown Title')
        year = '(' + str(trailer.get(Movie.YEAR, 'unknown Year')) + ')'
        movie_type = trailer.get(Movie.TYPE, 'Unknown MovieType')
        movie_path = trailer.get(Movie.FILE, '')
        if movie_path is None:
            movie_path = 'Unknown movie path'
        trailer_path = trailer.get(Movie.TRAILER, '')
        cache_path_prefix = Settings.get_downloaded_trailer_cache_path()
        trailer_path = trailer_path.replace(cache_path_prefix, '<cache_path>')
        missing_detail_msg = Messages.get_instance().get_msg(Messages.MISSING_DETAIL)
        if trailer_path == missing_detail_msg:
            trailer_path = ''
        if name is None:
            name = 'name is None'
        if year is None:
            year = 'year is None'
        if movie_type is None:
            movie_type = 'movie_type is None'

        path = trailer_path
        if use_movie_path:
            path = movie_path

        formatted_title = Messages.get_instance().get_formated_title(trailer)

        with Playlist._playlist_lock:
            # file closed
            if self._file is None:
                return

        if self.playlist_format:
            line = "EXTINF:0," + name + '\n'
            line += path + '\n'
        else:
            line = name + '  ' + year + '  # path: ' + formatted_title + ' ' +\
                   path + ' ' + msg + '\n'
        self._file.writelines(line)

    def writeLine(self, line):
        # type: (TextType) -> None
        """

        :param line:
        :return:
        """
        self._file.writelines(line + '\n')

    def close(self):
        # type: () -> None
        """

        :return:
        """
        try:
            if self._file is not None:
                self._file.close()
                self._file = None
                with Playlist._playlist_lock:
                    del Playlist._playlists[self._playlist_name]
        except (Exception):
            pass

    @staticmethod
    def shutdown():
        # type: () -> None
        """

        :return:
        """
        try:
            with Playlist._playlist_lock:
                for playlist in Playlist._playlists.copy().itervalues():
                    playlist.close()
        finally:
            with Playlist._playlist_lock:
                Playlist._playlists = {}
