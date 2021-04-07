# -*- coding: utf-8 -*-

"""
Created on Feb 19, 2019

@author: Frank Feuerbacher
"""
from io import StringIO
import simplejson as json
import sys
import threading
import traceback

import xbmc
from common.constants import Constants, Movie
from common.imports import *
from common.logger import LazyLogger
from common.rating import WorldCertifications
from common.settings import Settings
from common.monitor import Monitor

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection PyClassHasNoInit
class Debug:
    """
        Define several methods useful for debugging
    """
    _logger: LazyLogger = module_logger.getChild('Debug')
    _currentAddonName = Constants.CURRENT_ADDON_NAME

    @classmethod
    def dump_dictionary(cls, d: Dict[str, Any], prefix: str = '',
                        heading: str = '',
                        log_level=LazyLogger.DEBUG_EXTRA_VERBOSE) -> None:
        """
            Dump key and value fields of a dictionary in human
            readable form.

        :param d:
        :param prefix:
        :param heading:
        :param log_level:
        :return:
        """
        if cls._logger.isEnabledFor(log_level):
            cls._logger.debug(heading, log_level=log_level)
            if d is None:
                cls._logger.debug('None')
            else:
                for k, v in d.items():
                    if isinstance(v, dict):
                        child_prefix = f'{prefix}{k}: '
                        cls.dump_dictionary(v, prefix=child_prefix)
                    else:
                        cls._logger.debug(f'{prefix}{k} : {v}',
                                          log_level=log_level)

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
        if cls._logger.isEnabledFor(log_level):
            if data is None:
                cls._logger.log('json None', log_level=log_level)
            else:
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
    def _dump_all_threads(cls) -> None:
        """
            Worker method that dumps all threads.

        :return:
        """
        addon_prefix = f'{Constants.ADDON_ID}/'
        xbmc.log('dump_all_threads', xbmc.LOGDEBUG)
        sio = StringIO()
        sio.write('\n*** STACKTRACE - START ***\n\n')
        code = []
        #  Monitor.dump_wait_counts()
        #  for threadId, stack in sys._current_frames().items():
        for th in threading.enumerate():
            sio.write(f'\n# ThreadID: {th.name}\n\n')
            stack = sys._current_frames().get(th.ident, None)
            if stack is not None:
                traceback.print_stack(stack, file=sio)

        string_buffer: str = sio.getvalue() + '\n*** STACKTRACE - END ***\n'
        sio.close()
        msg = Debug._currentAddonName + ' : dump_all_threads'
        xbmc.log(msg, xbmc.LOGDEBUG)
        xbmc.log(string_buffer, xbmc.LOGDEBUG)

    @classmethod
    def compare_movies(cls,
                       trailer: MovieType,
                       new_trailer: MovieType,
                       max_value_length: int = 60) -> None:
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
        if trailer is None or new_trailer is None:
            cls._logger.debug_verbose('At least one argument is None')
            return

        keys_of_primary_interest = [Movie.TRAILER,
                                    Movie.SOURCE, Movie.TITLE,
                                    Movie.YEAR, Movie.TRAILER_TYPE]
        keys_of_interest = [Movie.TRAILER,
                            Movie.SOURCE, Movie.TITLE,
                            Movie.FANART, Movie.PLOT,
                            Movie.FILE, Movie.THUMBNAIL,
                            Movie.YEAR, Movie.TRAILER_TYPE]
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
    def validate_basic_movie_properties(cls,
                                        movie: MovieType,
                                        stack_trace: bool = True) -> None:
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

        if movie is None:
            cls._logger.debug_verbose('movie is None')
            return

        basic_properties = {}

        for key in (Movie.TRAILER_TYPE, Movie.FANART, Movie.THUMBNAIL, Movie.TRAILER,
                    Movie.SOURCE, Movie.YEAR, Movie.RATING, Movie.TITLE):
            basic_properties[key] = Movie.DEFAULT_MOVIE[key]

        failing_properties = []
        is_failed = False
        for property_name in basic_properties.keys():
            if movie.get(property_name) is None:
                failing_properties.append(property_name)
                is_failed = True
                movie.setdefault(
                    property_name, basic_properties[property_name])

        if len(failing_properties) > 0:
            msg = f'{movie.get(Movie.TITLE, "title missing")} ' \
                f'{",".join(failing_properties)}'
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

        if movie is None:
            cls._logger.debug_verbose('movie is None')
            return False

        details_properties = {}

        for key in (Movie.TRAILER_TYPE, Movie.FANART, Movie.THUMBNAIL, Movie.TRAILER,
                    Movie.SOURCE, Movie.YEAR, Movie.RATING, Movie.TITLE,
                    Movie.WRITER, Movie.DETAIL_DIRECTORS, Movie.DETAIL_TITLE,
                    Movie.CAST, Movie.PLOT, Movie.GENRE, Movie.STUDIO,
                    Movie.DETAIL_ACTORS, Movie.DETAIL_GENRES,
                    Movie.DETAIL_CERTIFICATION, Movie.DETAIL_CERTIFICATION_IMAGE,
                    Movie.DETAIL_RUNTIME, Movie.DETAIL_WRITERS,
                    Movie.DETAIL_STUDIOS, Movie.RUNTIME, Movie.MPAA):
            details_properties[key] = Movie.DEFAULT_MOVIE[key]

        cls.validate_basic_movie_properties(movie, stack_trace=stack_trace)
        failing_properties = []
        is_ok = True
        for property_name in details_properties.keys():
            if movie.get(property_name) is None:
                failing_properties.append(property_name)
                movie.setdefault(
                    property_name, details_properties[property_name])
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
