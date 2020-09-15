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

import xbmc
import xbmcvfs
import xmltodict

from common.imports import *
from common.constants import Constants, Movie
from common.logger import (LazyLogger, Trace)
from common.messages import Messages
from common.monitor import Monitor
from common.disk_utils import DiskUtils
from common.settings import (Settings)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


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
    SMART_PLAYLIST_SUFFIX = '.xsp'
    PLAYLIST_HEADER = '#EXTCPlayListM3U::M3U'
    PLAYLIST_ENTRY_PREFIX = '#EXTINF:0,'

    SMART_PLAYLIST_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
    SMART_PLAYLIST_MOVIE_HEADER = '<smartplaylist type="movies">'
    SMART_PLAYLIST_NAME = '<name>{}</name>'
    SMART_PLAYLIST_MATCH = '<match>all</match>'
    SMART_PLALIST_RULE_HEADER = '<rule field="filename" operator="is">'
    SMART_PLAYLIST_RULE_ENTRY = '<value>{}</value>'
    SMART_PLAYLIST_RULE_TAIL = '</rule>'
    SMART_PLAYLIST_TAIL = '<order direction="ascending">random</order>/' \
                          '</smartplaylist>'

    smart_playlist_skeleton = {
        'smartplaylist': {'@type': 'movies',
                          'name': ['{0}'],
                          'match': ['one'],
                          'order': {'@direction': 'ascending',
                                    '#text': 'random'}
                          }
    }

    _playlist_lock = threading.RLock()
    _playlists = {}

    def __init__(self, *args, **kwargs):
        # type: (*str, **Any) -> None
        """

        :param args:
        :param kwargs:
        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        self._file = None

        if len(args) == 0:
            self._logger.error(
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
        self.path = xbmc.translatePath(self.path)
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
                        if os.path.exists(save_path):
                            os.remove(save_path)
                    except Exception as e:
                        self._logger.exception('')
                    try:
                        if os.path.exists(self.path):
                            os.rename(self.path, save_path)
                    except Exception as e:
                        self._logger.exception('')
                except Exception as e:
                    self._logger.exception('')

            try:
                self._file = io.open(self.path, mode=self.mode, buffering=1, newline=None,
                                     encoding='utf-8')
            except Exception as e:
                self._logger.exception('')

    def load_smart_playlist(self):
        playlist_dict = None
        try:
            if os.path.exists(self.path):
                with io.open(self.path, mode='rt', newline=None,
                             encoding='utf-8') as playlist_file:
                    buffer = playlist_file.read()
                    playlist_dict = xmltodict.parse(buffer)
        except Exception as e:
            self._logger.exception('')

        return playlist_dict

    def add_to_smart_playlist(self, trailer):
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
            self._logger.exception('')
        return True

    def write_playlist(self, playlist_dict):
        try:
            with io.open(self.path, mode=self.mode, buffering=1, newline=None,
                         encoding='utf-8') as file:
                file.write(xmltodict.unparse(playlist_dict, pretty=True))

        except Exception as e:
            self._logger.exception('')

    @staticmethod
    def get_playlist(playlist_name, append=True, rotate=False, playlist_format=False):
        # type: (str, bool, bool, bool) -> Playlist
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
        # type: (Dict[str, Any], bool, str) -> None
        """

        :param trailer:
        :param use_movie_path:
        :param msg:
        :return:
        """
        if self.playlist_format:
            use_movie_path = True

        name = trailer.get(Movie.TITLE, 'unknown Title')
        year = '(' + str(trailer.get(Movie.YEAR, 'unknown Year')) + ')'
        movie_type = trailer.get(Movie.TYPE, 'Unknown MovieType')
        movie_path = trailer.get(Movie.FILE, None)
        if movie_path is None:
            if use_movie_path:  # Nothing to do if there is no movie path
                return
            movie_path = 'Unknown movie path'
        trailer_path = trailer.get(Movie.TRAILER, '')
        cache_path_prefix = Settings.get_downloaded_trailer_cache_path()
        trailer_path = trailer_path.replace(cache_path_prefix, '<cache_path>')
        missing_detail_msg = Messages.get_msg(Messages.MISSING_DETAIL)
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

        formatted_title = Messages.get_formated_title(trailer)

        with Playlist._playlist_lock:
            # file closed
            if self._file is None:
                return

        if self.playlist_format:
            line = Playlist.PLAYLIST_ENTRY_PREFIX + name + '\n'
            line += path + '\n'
        else:
            line = name + '  ' + year + '  # path: ' + formatted_title + ' ' +\
                path + ' ' + msg + '\n'
        self._file.writelines(line)

    def writeLine(self, line):
        # type: (str) -> None
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
        except Exception:
            pass

    @staticmethod
    def shutdown():
        # type: () -> None
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
