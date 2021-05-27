# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import copy
import datetime
import io
import os
import threading

import xbmcvfs
import xmltodict

from common.imports import *
from common.constants import Constants
from common.logger import (LazyLogger, Trace)
from common.messages import Messages
from common.monitor import Monitor
from common.disk_utils import DiskUtils
from common.movie import AbstractMovie
from common.settings import (Settings)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class Playlist:
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
    VIEWED_PLAYLIST_FILE: Final[str] = 'Viewed.playlist'
    MISSING_TRAILERS_PLAYLIST: Final[str] = 'missingTrailers.playlist'
    PLAYLIST_PREFIX: Final[str] = 'RandomTrailer_'
    PLAYLIST_SUFFIX: Final[str] = '.m3u'
    SMART_PLAYLIST_SUFFIX: Final[str] = '.xsp'
    PLAYLIST_HEADER: Final[str] = '#EXTCPlayListM3U::M3U'
    PLAYLIST_ENTRY_PREFIX: Final[str] = '#EXTINF:0,'

    SMART_PLAYLIST_HEADER: Final[str] = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
    SMART_PLAYLIST_MOVIE_HEADER: Final[str] = '<smartplaylist type="movies">'
    SMART_PLAYLIST_NAME: Final[str] = '<name>{}</name>'
    SMART_PLAYLIST_MATCH: Final[str] = '<match>all</match>'
    SMART_PLALIST_RULE_HEADER: Final[str] = '<rule field="filename" operator="is">'
    SMART_PLAYLIST_RULE_ENTRY: Final[str] = '<value>{}</value>'
    SMART_PLAYLIST_RULE_TAIL: Final[str] = '</rule>'
    SMART_PLAYLIST_TAIL: Final[str] = '<order direction="ascending">random</order>/' \
                          '</smartplaylist>'

    smart_playlist_skeleton: Final[Dict] = {
        'smartplaylist': {'@type': 'movies',
                          'name': ['{0}'],
                          'match': ['one'],
                          'order': {'@direction': 'ascending',
                                    '#text': 'random'}
                          }
    }

    _playlist_lock: threading.RLock = threading.RLock()
    _playlists: Dict[str, 'Playlist'] = {}
    _logger: LazyLogger = None

    def __init__(self, *args: str, **kwargs: Any) -> None:
        """

        :param args:
        :param kwargs:
        """
        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(clz.__name__)

        self._file = None

        if len(args) == 0:
            clz._logger.error(
                'Playlist constructor requires an argument')
            return

        playlist_name = args[0]
        self._playlist_name = playlist_name
        append = kwargs.get('append', True)
        rotate = kwargs.get('rotate', False)
        assert append ^ rotate
        self.playlist_format = kwargs.get('playlist_format', False)

        if self.playlist_format:
            self.path = Constants.PLAYLIST_PATH + '/' + \
                playlist_name + Playlist.SMART_PLAYLIST_SUFFIX
        else:
            self.path = Constants.FRONTEND_DATA_PATH + '/' + \
                playlist_name  # + Playlist.PLAYLIST_SUFFIX
        self.path = xbmcvfs.validatePath(self.path)
        self.path = xbmcvfs.translatePath(self.path)
        DiskUtils.create_path_if_needed(Constants.FRONTEND_DATA_PATH)
        if not self.playlist_format:
            self.mode = 'wt'
            if append:
                self.mode = 'at'
            else:
                self.mode = 'wt'
            if rotate:
                try:
                    save_path = Constants.FRONTEND_DATA_PATH + '/' + playlist_name + '.old'
                    save_path = xbmcvfs.validatePath(save_path)
                    try:
                        if os.path.exists(self.path):
                            os.replace(self.path, save_path)
                    except Exception as e:
                        clz._logger.exception('')
                except Exception as e:
                    clz._logger.exception('')

            try:
                self._file = io.open(self.path, mode=self.mode, buffering=1, newline=None,
                                     encoding='utf-8')
            except Exception as e:
                clz._logger.exception('')

    def load_smart_playlist(self) -> None:
        clz = type(self)
        playlist_dict = None
        try:
            if os.path.exists(self.path):
                with io.open(self.path, mode='rt', newline=None,
                             encoding='utf-8') as playlist_file:
                    buffer = playlist_file.read()
                    playlist_dict = xmltodict.parse(buffer)
        except Exception as e:
            clz._logger.exception('')

        return playlist_dict

    def add_to_smart_playlist(self, trailer) -> bool:
        clz = type(self)
        movie_filename = trailer.get(Movie.FILE, None)
        if movie_filename is not None:
            movie_filename = os.path.basename(movie_filename)
        playlist_dict = self.load_smart_playlist()
        if playlist_dict is None:
            playlist_dict = copy.deepcopy(Playlist.smart_playlist_skeleton)
            name = playlist_dict['smartplaylist']['name'][0].format(
                self._playlist_name)
            playlist_dict['smartplaylist']['name'][0] = name

        #   SMART_PLAYLIST_RULE_HEADER = '<rule field="filename" operator="is">'
        #     SMART_PLAYLIST_RULE_ENTRY = '<value>{}</value>'

        rule_list = playlist_dict['smartplaylist'].get('rule', [])

        if not isinstance(rule_list, list):
            rule_list = [rule_list]

        for rule in rule_list:
            if rule['value'] == movie_filename:
                return False

        new_rule = {
            '@field': 'filename',
            '@operator': 'is',
            'value': [movie_filename]
        }
        rule_list.append(new_rule)
        playlist_dict['smartplaylist']['rule'] = rule_list
        try:
            with io.open(self.path, mode='wt', buffering=1, newline=None,
                         encoding='utf-8') as file:
                file.write(xmltodict.unparse(playlist_dict, pretty=True))

        except Exception as e:
            clz._logger.exception('')
        return True

    def write_playlist(self, playlist_dict: Dict[str, 'Playlist']) -> None:
        clz = type(self)
        try:
            with io.open(self.path, mode=self.mode, buffering=1, newline=None,
                         encoding='utf-8') as file:
                file.write(xmltodict.unparse(playlist_dict, pretty=True))

        except Exception as e:
            clz._logger.exception('')

    @staticmethod
    def get_playlist(playlist_name: str,
                     append: bool = True,
                     rotate: bool = False,
                     playlist_format: bool = False) -> 'Playlist':
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

    def add_timestamp(self) -> None:
        """

        :return:
        """
        now = datetime.datetime.now().strftime('%m/%d/%y %H:%M:%S')
        self.writeLine('random trailers started: {!s}'.format(now))

    def record_played_trailer(self,
                              movie: AbstractMovie,
                              use_movie_path: bool = False,
                              msg: str = '') -> None:
        """

        :param movie:
        :param use_movie_path:
        :param msg:
        :return:
        """
        if self.playlist_format:
            use_movie_path = True

        name: str = movie.get_title()
        year: str = str(movie.get_year())
        trailer_type: str = movie.get_trailer_type()
        trailer_path: str = movie.get_trailer_path()
        movie_path: str = movie.get_movie_path()
        if movie_path is None:
            if use_movie_path:  # Nothing to do if there is no movie path
                return
            movie_path = 'Unknown movie path'
        cache_path_prefix = Settings.get_downloaded_trailer_cache_path()
        trailer_path = trailer_path.replace(cache_path_prefix, '<cache_path>')
        missing_detail_msg = Messages.get_msg(Messages.MISSING_DETAIL)
        if trailer_path == missing_detail_msg:
            trailer_path = ''
        if name is None:
            name = 'name is None'
        if year is None:
            year = 'year is None'
        if trailer_type is None:
            trailer_type = 'trailer_type is None'

        path = trailer_path
        if use_movie_path:
            path = movie_path

        with Playlist._playlist_lock:
            # file closed
            if self._file is None:
                return

        if self.playlist_format:
            line = Playlist.PLAYLIST_ENTRY_PREFIX + name + '\n'
            line += path + '\n'
        else:
            line = f'{name}  {year}  # path: {movie.get_detail_title()} {path} {msg}\n'
        self._file.writelines(line)

    def writeLine(self, line: str) -> None:
        """

        :param line:
        :return:
        """
        self._file.writelines(line + '\n')

    def close(self) -> None:
        """

        :return:
        """
        try:
            if self._file is not None:
                self._file.close()
                self._file = None
                with Playlist._playlist_lock:
                    del Playlist._playlists[self._playlist_name]
        except Exception:
            pass

    @staticmethod
    def shutdown() -> None:
        """

        :return:
        """
        try:
            with Playlist._playlist_lock:
                for playlist in Playlist._playlists.copy().values():
                    playlist.close()
        finally:
            with Playlist._playlist_lock:
                Playlist._playlists = {}


Monitor.register_abort_listener(Playlist.shutdown)
