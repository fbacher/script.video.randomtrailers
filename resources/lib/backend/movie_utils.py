# -*- coding: utf-8 -*-

"""
Created on Feb 11, 2019

@author: fbacher
"""

import os

from common.imports import *
from common.constants import (Constants, Movie)
from common.playlist import Playlist
from common.logger import (LazyLogger, Trace)
from backend.json_utils import JsonUtils

from common.settings import Settings

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class LibraryMovieStats(object):
    """

    """

    def __init__(self):
        # type: () -> None
        """

        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        self._genre_map = {}
        self._actor_map = {}
        self._tag_map = {}

    '''
       Determine which genres are represented in the movie library
    '''

    def get_genres_in_library(self):
        # type: () -> List[str]
        """

        :return:
        """
        self._logger.enter()
        my_genres = []

        query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetGenres", \
                 "params": {\
                    "type" : "movie"\
                        }, \
                         "id": 1}'
        query_result = JsonUtils.get_kodi_json(query, dump_results=False)

        genre_result = query_result['result']
        for genreEntry in genre_result.get('genres', []):
            genre = genreEntry['label']
            my_genres.append(genre)

        my_genres.sort()
        return my_genres

    def collect_data(self, movie):
        # type: (dict) -> None
        """

        :param movie:
        :return:
        """
        self.collect_actors(movie)
        self.collect_genres(movie)
        self.collect_tags(movie)

    def report_data(self):
        # type: () -> None
        """

        :return:
        """
        self.report_actor_frequency()
        self.report_genre_map()
        self.report_tag_map()
        genres = self.get_genres_in_library()
        self.report_genres(genres)
        tags = self.discover_tags()
        self.report_tags(tags)

        # After report, disable setting so that time is not wasted on future
        # runs for this rarely wanted report.

        Settings.disable_movie_stats()

    def collect_actors(self, movie):
        # type: (dict)-> None
        """

        :param movie:
        :return:
        """
        actors = movie.get(Movie.CAST, [])
        movie_name = movie[Movie.TITLE]
        movie_year = movie[Movie.YEAR]
        movie_id = movie_name + ' (' + str(movie_year) + ')'

        actor_count = 0
        for actor_entry in actors:
            if 'name' in actor_entry:
                actor_count += 1
                actor = actor_entry['name']
                if self._actor_map.get(actor) is None:
                    self._actor_map[actor] = []
                self._actor_map[actor].append(movie_id)
            if actor_count == Settings.get_report_max_top_actors():
                break

    def report_actor_frequency(self, msg=''):
        # type: (str) -> None
        """

        :param msg:
        :return:
        """
        # First sort by number of movies that each actor is
        # in

        a = sorted(self._actor_map, key=lambda key: len(
            self._actor_map[key]), reverse=True)

        playlist = Playlist.get_playlist(
            'Actor_Frequency.report', append=False)

        for actor in a:
            movies_in = self._actor_map[actor]
            string_buffer = actor + ' : ' + str(len(movies_in))
            for movie in sorted(movies_in):
                if len(string_buffer) > 100:
                    playlist.writeLine(string_buffer)
                    string_buffer = '       '
                string_buffer = string_buffer + ' ' + movie

            playlist.writeLine(string_buffer)

        playlist.close()

    def collect_tags(self, movie):
        # type: (dict) -> None
        """

        :param movie:
        :return:
        """
        tags = movie.get(Movie.TAG, [])
        movie_name = movie[Movie.TITLE]
        movie_year = movie[Movie.YEAR]
        movie_id = movie_name + ' (' + str(movie_year) + ')'

        tag_count = 0
        for tag in tags:
            tag_count += 1
            if self._tag_map.get(tag) is None:
                self._tag_map[tag] = []
            self._tag_map[tag].append(movie_id)

    def report_genre_map(self, msg=''):
        # type: (str) -> None
        """

        :param msg:
        :return:
        """
        # First sort by number of movies that each genre is
        # in

        a = sorted(self._genre_map, key=lambda key: len(
            self._genre_map[key]), reverse=True)

        playlist = Playlist.get_playlist(
            'Genre_Frequency.report', append=False)

        for genre in a:
            movies_in = self._genre_map[genre]
            string_buffer = genre + ' : ' + str(len(movies_in))
            separator = ' '
            for movie in sorted(movies_in):
                if len(string_buffer) > 100:
                    string_buffer += separator
                    playlist.writeLine(string_buffer)
                    string_buffer = '       '
                    separator = ' '
                string_buffer = string_buffer + separator + movie
                separator = ', '

            playlist.writeLine(string_buffer)

        playlist.close()

    def collect_genres(self, movie):
        #  type: (MovieType) -> None
        """

        :param movie:
        :return:
        """
        genres = movie.get(Movie.GENRE, [])
        movie_name = movie[Movie.TITLE]
        movie_year = movie[Movie.YEAR]
        movie_id = movie_name + ' (' + str(movie_year) + ')'

        genre_count = 0
        for genre in genres:
            genre_count += 1
            if self._genre_map.get(genre) is None:
                self._genre_map[genre] = []
            self._genre_map[genre].append(movie_id)

    @staticmethod
    def report_genres(genres):
        # type: (List[str]) -> None
        """

        :param genres:
        :return:
        """
        string_buffer = ''
        separator = ''
        playlist = Playlist.get_playlist(
            'Genres.report', append=False)
        for genre in genres:
            string_buffer = string_buffer + separator + genre
            separator = ', '
            if len(string_buffer) > 100:
                string_buffer = string_buffer + separator
                playlist.writeLine(string_buffer)
                string_buffer = '       '
                separator = ''

        playlist.close()

    @staticmethod
    def discover_tags():
        # type: () -> List[str]
        """

        :return:
        """
        query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetTags", \
                    "params": {\
                    "type" : "movie"\
                        }, \
                         "id": 1}'
        query_result = JsonUtils.get_kodi_json(query)
        tags = []
        for tag in query_result.get('result', {}).get('tags', []):
            tags.append(tag['label'])

        tags = sorted(tags)
        return tags

    @staticmethod
    def report_tags(tags):
        # type: (List[str]) -> None
        """

        :param tags:
        :return:
        """
        string_buffer = ''
        separator = ''
        playlist = Playlist.get_playlist(
            'Tags.report', append=False)
        for tag in tags:
            string_buffer = string_buffer + separator + tag
            separator = ', '
            if len(string_buffer) > 100:
                string_buffer = string_buffer + separator
                playlist.writeLine(string_buffer)
                string_buffer = '       '
                separator = ''

        playlist.close()

    def report_tag_map(self, msg=''):
        # type: (str) -> None
        """

        :param msg:
        :return:
        """
        # First sort by number of movies that each tag is
        # in

        a = sorted(self._tag_map, key=lambda key: len(
            self._tag_map[key]), reverse=True)

        playlist = Playlist.get_playlist(
            'Tag_Frequency.report', append=False)

        for tag in a:
            movies_in = self._tag_map[tag]
            string_buffer = tag + ' : ' + str(len(movies_in))
            separator = ' '
            for movie in sorted(movies_in):
                if len(string_buffer) > 100:
                    string_buffer = string_buffer + separator
                    playlist.writeLine(string_buffer)
                    string_buffer = '       '
                string_buffer = string_buffer + separator + movie
                separator = ' '

            playlist.writeLine(string_buffer)

        playlist.close()
