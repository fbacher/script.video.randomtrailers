# -*- coding: utf-8 -*-

"""
Created on Feb 19, 2019

@author: Frank Feuerbacher
"""

import sys
import json
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
    _logger = module_logger.getChild('Debug')
    _currentAddonName = Constants.CURRENT_ADDON_NAME

    @classmethod
    def dump_dictionary_keys(cls, d):
        # type: (Dict[str, Any]) -> None
        """
            Dump key and value fields of a dictionary in human
            readable form.

        :param d:
        :return:
        """
        for k, v in d.items():
            if isinstance(v, dict):
                cls.dump_dictionary_keys(v)
            else:
                cls._logger.debug('{0} : {1}'.format(k, v))

    @classmethod
    def dump_json(cls, text='', data=None):
        # type: (str, Union[Dict[str, Any], None]) -> None
        """
            Log Json values using the json.dumps utility

        :param text:
        :param data:
        :return:
        """
        cls._logger.debug(text, json.dumps(data, ensure_ascii=False,
                                           encoding='unicode', indent=4,
                                           sort_keys=True), xbmc.LOGINFO)

    @classmethod
    def dump_all_threads(cls, delay=None):
        # type: (float) -> None
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
        string_buffer = '\n*** STACKTRACE - START ***\n'
        code = []
        for threadId, stack in sys._current_frames().items():
            code.append("\n# ThreadID: %s" % threadId)
            for filename, lineno, name, line in traceback.extract_stack(stack):
                code.append('File: "%s", line %d, in %s' % (filename,
                                                            lineno, name))
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
                cls._logger.debug('CompareMovies- key:', key,
                                  'is missing from new. Value:',
                                  value)

        for key in trailer:
            if key in keys_of_primary_interest and (trailer.get(key) is not None
                                                    and trailer.get(key) != new_trailer.get(key)):

                value = str(trailer.get(key))
                if len(value) > max_value_length:
                    value = value[:max_value_length]
                new_value = str(new_trailer.get(key))
                if len(new_value) > max_value_length:
                    new_value = new_value[:max_value_length]
                cls._logger.debug('Values for:', key, 'different:', value,
                                  'new:', new_value)

        for key in new_trailer:
            if key in keys_of_interest and trailer.get(key) is None:
                value = str(new_trailer.get(key))
                if len(value) > max_value_length:
                    value = value[:max_value_length]
                cls._logger.debug('key:', key, 'is missing from old. Value:',
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
        basic_properties = (
            Movie.TYPE,
            Movie.FANART,
            Movie.THUMBNAIL,
            Movie.TRAILER,
            Movie.SOURCE,
            # Movie.FILE,
            Movie.YEAR,
            Movie.TITLE)

        failing_properties = []
        is_failed = False
        for property_name in basic_properties:
            if movie.get(property_name) is None:
                failing_properties.append(property_name)
                is_failed = True
                movie.setdefault(property_name, 'default_' + property_name)

        if len(failing_properties) > 0:
            msg = ', '.join(failing_properties)
            if stack_trace:
                LazyLogger.dump_stack('Missing basic property: ' + msg)
            else:
                cls._logger.debug('Missing properties:', msg)

        assert not is_failed, 'LEAK: Invalid property values'

    @classmethod
    def validate_detailed_movie_properties(cls, movie, stack_trace=True):
        # type: (MovieType, bool) -> None
        """
            Similar to validate_basic_movie_properties. Validates additional
            fields
        :param movie:
        :param stack_trace:
        :return:
        """
        details_properties = (Movie.WRITER,
                              Movie.DETAIL_DIRECTORS,
                              Movie.CAST,
                              Movie.PLOT,
                              Movie.GENRE,
                              Movie.STUDIO,
                              Movie.RUNTIME,
                              # Movie.ADULT,
                              Movie.MPAA)

        cls.validate_basic_movie_properties(movie, stack_trace=stack_trace)
        failing_properties = []
        is_failed = False
        for property_name in details_properties:
            if movie.get(property_name) is None:
                failing_properties.append(property_name)
                movie.setdefault(property_name, 'default_' + property_name)
                is_failed = True

        if len(failing_properties) > 0:
            msg = ', '.join(failing_properties)
            if stack_trace:
                LazyLogger.dump_stack('Missing details property: ' + msg)
            else:
                cls._logger.debug('Missing properties:', msg)

        country_id = Settings.get_country_iso_3166_1().lower()
        certifications = WorldCertifications.get_certifications(country_id)
        if not certifications.is_valid(movie[Movie.MPAA]):
            cls._logger.debug('Invalid MPAA rating: {} for movie: {} set to NR'
                              .format(movie[Movie.MPAA], movie[Movie.TITLE]))
            movie[Movie.MPAA] = certifications.get_unrated_certification()\
                .get_preferred_id()

        assert not is_failed, 'LEAK, Invalid property values'
