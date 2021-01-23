# -*- coding: utf-8 -*-

"""
Created on Feb 19, 2019

@author: Frank Feuerbacher
"""
import json
import sys
import threading
import traceback

import xbmc
from common.constants import Constants, Movie
from common.imports import *
from common.logger import (LazyLogger)
from common.rating import WorldCertifications
from common.settings import Settings

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection PyClassHasNoInit
class Debug(object):
    """
        Define several methods useful for debugging
    """
    _logger: LazyLogger = module_logger.getChild('Debug')
    _currentAddonName = Constants.CURRENT_ADDON_NAME

    @classmethod
    def dump_dictionary(cls, d):
        # type: (Dict[str, Any]) -> None
        """
            Dump key and value fields of a dictionary in human
            readable form.

        :param d:
        :return:
        """
        for k, v in d.items():
            if isinstance(v, dict):
                cls.dump_dictionary(v)
            else:
                cls._logger.debug('{0} : {1}'.format(k, v))

    @classmethod
    def dump_json(cls, text: str = '', data: str = '',
                  log_level: int = LazyLogger.DEBUG) -> None:
        """
            Log Json values using the json.dumps utility

        :param text:
        :param data:
        :param log_level:
        :return:
        """
        cls._logger.log(text, json.dumps(data, ensure_ascii=False,
                                         encoding='unicode', indent=4,
                                         sort_keys=True), log_level=log_level)

    @classmethod
    def dump_all_threads(cls, delay: float = None) -> None:
        """
            Dumps all Python stacks, including those in other plugins

        :param delay:
        :return:
        """
        if delay is None or delay == 0:
            cls._dump_all_threads()
        else:
            dump_threads = threading.Timer(delay, cls._dump_all_threads)
            dump_threads.setName('dump_threads')
            dump_threads.start()

    @classmethod
    def _dump_all_threads(cls):
        # type: () -> None
        """
            Worker method that dumps all threads.

        :return:
        """
        addon_prefix = f'{Constants.ADDON_ID}/'
        string_buffer = '\n*** STACKTRACE - START ***\n'
        code = []
        for threadId, stack in sys._current_frames().items():
            code.append(f'\n# ThreadID: {threadId}')
            for filename, lineno, name, line in traceback.extract_stack(stack):
                filename: str
                filename = filename.replace(Constants.ADDON_PATH, addon_prefix)
                code.append(f'File: {filename}, line {lineno!s} in {name}')
                if line:
                    code.append("  %s" % (line.strip()))

        for line in code:
            string_buffer = string_buffer + '\n' + line
        string_buffer = string_buffer + '\n*** STACKTRACE - END ***\n'

        msg = Debug._currentAddonName + ' : dump_all_threads'
        xbmc.log(msg, xbmc.LOGDEBUG)
        xbmc.log(string_buffer, xbmc.LOGDEBUG)

    @classmethod
    def compare_movies(cls, trailer, new_trailer, max_value_length=60):
        # type: (MovieType, MovieType, int) ->None
        """
            Compares some of the more important fields between to Kodi VideoInfo
            dictionaries. Any differences are logged.

        :param trailer:
        :param new_trailer:
        :param max_value_length:
        :return:
        """
        if not cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            return

        keys_of_primary_interest = [Movie.TRAILER,
                                    Movie.SOURCE, Movie.TITLE,
                                    Movie.YEAR, Movie.TYPE]
        keys_of_interest = [Movie.TRAILER,
                            Movie.SOURCE, Movie.TITLE,
                            Movie.FANART, Movie.PLOT,
                            Movie.FILE, Movie.THUMBNAIL,
                            Movie.YEAR, Movie.TYPE]
        for key in trailer:
            if key in keys_of_interest and new_trailer.get(key) is None:
                value = str(trailer.get(key))
                if len(value) > max_value_length:
                    value = value[:max_value_length]
                cls._logger.debug_verbose('CompareMovies- key:', key,
                                          'is missing from new. Value:',
                                          value)

        for key in trailer:
            if key in keys_of_primary_interest and (trailer.get(key) is not None
                                                    and trailer.get(
                        key) != new_trailer.get(key)):

                value = str(trailer.get(key))
                if len(value) > max_value_length:
                    value = value[:max_value_length]
                new_value = str(new_trailer.get(key))
                if len(new_value) > max_value_length:
                    new_value = new_value[:max_value_length]
                cls._logger.debug_verbose('Values for:', key, 'different:', value,
                                          'new:', new_value)

        for key in new_trailer:
            if key in keys_of_interest and trailer.get(key) is None:
                value = str(new_trailer.get(key))
                if len(value) > max_value_length:
                    value = value[:max_value_length]
                cls._logger.debug_verbose('key:', key, 'is missing from old. Value:',
                                          value)

    @classmethod
    def validate_basic_movie_properties(cls, movie, stack_trace=True):
        # type: (MovieType, bool) -> None
        """
            Verifies that certain fields in a Kodi VideoInfo dictionary
            have values. Fields with Missing fields are logged and dummy
            values are added. Meant to avoid Exceptions.
        :param movie:
        :param stack_trace:
        :return:
        """
        if not cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            return

        basic_properties = {
            Movie.TYPE: 'default_' + Movie.TYPE,
            Movie.FANART: 'default_' + Movie.TYPE,
            Movie.THUMBNAIL: 'default_ ' + Movie.THUMBNAIL,
            Movie.TRAILER: 'default_' + Movie.TRAILER,
            Movie.SOURCE: 'default_' + Movie.SOURCE,
            # Movie.FILE,
            Movie.YEAR: 1492,
            Movie.RATING: 0.0,
            # Movie.DISCOVERY_STATE: Movie.NOT_INITIALIZED,
            Movie.TITLE: 'default_' + Movie.TITLE}

        failing_properties = []
        is_failed = False
        for property_name in basic_properties.keys():
            if movie.get(property_name) is None:
                failing_properties.append(property_name)
                is_failed = True
                movie.setdefault(property_name, basic_properties[property_name])

        if len(failing_properties) > 0:
            msg = ', '.join(failing_properties)
            if stack_trace:
                LazyLogger.dump_stack('Missing basic property: ' + msg)
            else:
                cls._logger.debug_verbose('Missing properties:', msg)

        assert not is_failed, 'LEAK: Invalid property values'

    @classmethod
    def validate_detailed_movie_properties(cls, movie: MovieType,
                                           stack_trace: bool = True,
                                           force_check: bool = False) -> bool:
        """
            Similar to validate_basic_movie_properties. Validates additional
            fields
        :param movie:
        :param stack_trace:
        :param force_check: Check even if debug level less than DEBUG_VERBOSE
        :return: True if no problems found
        """
        if not (cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE) or force_check):
            return True

        details_properties = {Movie.WRITER: ['default_' + Movie.WRITER],
                              Movie.DETAIL_DIRECTORS: ['default_' + Movie.DETAIL_DIRECTORS],
                              Movie.DETAIL_TITLE: 'default_' + Movie.TITLE,
                              Movie.CAST: ['default_' + Movie.CAST],
                              Movie.PLOT: 'default_' + Movie.PLOT,
                              Movie.GENRE: ['default_' + Movie.GENRE],
                              Movie.STUDIO: ['default_' + Movie.STUDIO],
                              Movie.DETAIL_ACTORS: ['default_' + Movie.ACTORS],
                              Movie.DETAIL_GENRES: ['default_' + Movie.GENRE],
                              Movie.DETAIL_CERTIFICATION: 'default_' +
                                                          Movie.DETAIL_CERTIFICATION,
                              Movie.DETAIL_CERTIFICATION_IMAGE: 'default_' +
                                                                Movie.DETAIL_CERTIFICATION_IMAGE,
                              Movie.DETAIL_RUNTIME: 'default_' + Movie.RUNTIME,
                              Movie.DETAIL_WRITERS: ['default_' + Movie.WRITER],
                              # Movie.TMDB_TAGS: 'default_' + Movie.TAG,   # For TMDB
                              Movie.DETAIL_STUDIOS: ['default_' + Movie.STUDIO],
                              Movie.RUNTIME: 0,
                              # Movie.ADULT,
                              Movie.MPAA: 'default_' + Movie.MPAA}

        cls.validate_basic_movie_properties(movie, stack_trace=stack_trace)
        failing_properties = []
        is_ok = True
        for property_name in details_properties.keys():
            if movie.get(property_name) is None:
                failing_properties.append(property_name)
                movie.setdefault(property_name, details_properties[property_name])
                is_ok = False

        if len(failing_properties) > 0:
            msg = ', '.join(failing_properties)
            if stack_trace:
                LazyLogger.dump_stack('Missing details property: ' + msg)
            else:
                cls._logger.debug_verbose('Missing properties:', msg)

        country_id = Settings.get_country_iso_3166_1().lower()
        certifications = WorldCertifications.get_certifications(country_id)
        if not certifications.is_valid(movie[Movie.MPAA]):
            if movie[Movie.MPAA] != '':
                cls._logger.debug_verbose(
                    f'Invalid certification: {movie[Movie.MPAA]} for movie: '
                    '{movie[Movie.TITLE]} set to NR')
            movie[Movie.MPAA] = certifications.get_unrated_certification() \
                .get_preferred_id()

        # assert is_ok, 'LEAK, Invalid property values'
        return is_ok
