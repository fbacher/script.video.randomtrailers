# -*- coding: utf-8 -*-

"""
Created on Feb 19, 2019

@author: Frank Feuerbacher
"""
import faulthandler
import io
from io import StringIO
import simplejson as json
import sys
import threading
import traceback

from sys import getsizeof, stderr
from itertools import chain
from collections import deque

try:
    from reprlib import repr
except ImportError:
    pass

import xbmc
from common.constants import Constants
from common.imports import *
from common.logger import LazyLogger
from common.movie import AbstractMovie, LibraryMovie
from common.movie_constants import MovieField, MovieType
from common.certification import WorldCertifications
from common.settings import Settings

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class Debug:
    """
        Define several methods useful for debugging
    """
    _logger: LazyLogger = module_logger.getChild('Debug')
    _currentAddonName = Constants.CURRENT_ADDON_NAME

    @classmethod
    def dump_dictionary(cls, d: Dict[str, Any], prefix: str = '',
                        heading: str = '',
                        log_level=LazyLogger.DISABLED) -> None:
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
                  log_level: int = LazyLogger.DISABLED) -> None:
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
            sio.write(f'\n# ThreadID: {th.name} Daemon: {th.isDaemon()}\n\n')
            stack = sys._current_frames().get(th.ident, None)
            if stack is not None:
                traceback.print_stack(stack, file=sio)

        string_buffer: str = sio.getvalue() + '\n*** STACKTRACE - END ***\n'
        sio.close()
        msg = Debug._currentAddonName + ' : dump_all_threads'
        xbmc.log(msg, xbmc.LOGDEBUG)
        xbmc.log(string_buffer, xbmc.LOGDEBUG)

        try:
            dump_path = Constants.FRONTEND_DATA_PATH + '/stack_dump'

            dump_file = io.open(dump_path, mode='at', buffering=1, newline=None,
                                encoding='ascii')

            faulthandler.dump_traceback(file=dump_file, all_threads=True)
        except Exception as e:
             pass

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

        keys_of_primary_interest = [MovieField.TRAILER,
                                    MovieField.SOURCE, MovieField.TITLE,
                                    MovieField.YEAR, MovieField.TRAILER_TYPE]
        keys_of_interest = [MovieField.TRAILER,
                            MovieField.SOURCE, MovieField.TITLE,
                            MovieField.FANART, MovieField.PLOT,
                            MovieField.FILE, MovieField.THUMBNAIL,
                            MovieField.YEAR, MovieField.TRAILER_TYPE]
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
                                        movie_arg: Union[MovieType, AbstractMovie],
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

        if movie_arg is None:
            cls._logger.debug_verbose('movie is None')
            return

        movie: MovieType
        if isinstance(movie_arg, LibraryMovie):
            return

        if isinstance(movie_arg, AbstractMovie):
            movie = movie_arg.get_as_movie_type()
        else:
            movie = movie_arg

        basic_properties = {}

        for key in (MovieField.TRAILER_TYPE, MovieField.FANART, MovieField.THUMBNAIL,
                    MovieField.TRAILER, MovieField.SOURCE, MovieField.YEAR,
                    MovieField.RATING, MovieField.TITLE):
            basic_properties[key] = MovieField.DEFAULT_MOVIE[key]

        failing_properties = []
        is_failed = False
        for property_name in basic_properties.keys():
            if movie.get(property_name) is None:
                failing_properties.append(property_name)
                is_failed = True
                movie.setdefault(
                    property_name, basic_properties[property_name])

        if len(failing_properties) > 0:
            msg = f'{movie.get(MovieField.TITLE, "title missing")} ' \
                f'{",".join(failing_properties)}'
            if stack_trace:
                LazyLogger.dump_stack('Missing basic property: ' + msg)
            else:
                cls._logger.debug_verbose('Missing properties:', msg)

        assert not is_failed, 'LEAK: Invalid property values'

    @classmethod
    def validate_detailed_movie_properties(cls,
                                           movie_arg: Union[MovieType, AbstractMovie],
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

        if movie_arg is None:
            cls._logger.debug_verbose('movie is None')
            return False
        movie: MovieType
        if isinstance(movie_arg, AbstractMovie):
            movie = movie_arg.get_as_movie_type()
        else:
            movie = movie_arg

        cls.validate_basic_movie_properties(movie, stack_trace=stack_trace)
        failing_properties = []
        is_ok = True
        for property_name in MovieField.DEFAULT_MOVIE.keys():
            if movie.get(property_name) is None:
                failing_properties.append(property_name)
                movie.setdefault(
                    property_name, MovieField.DEFAULT_MOVIE[property_name])
                is_ok = False

        if (cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                                     and len(failing_properties) > 0):
            msg = ', '.join(failing_properties)
            if stack_trace:
                LazyLogger.dump_stack('Missing details property: ' + msg)
            else:
                cls._logger.debug_verbose('Missing properties:', msg)

        country_id = Settings.get_country_iso_3166_1().lower()
        certifications = WorldCertifications.get_certifications(country_id)
        if not certifications.is_valid(movie[MovieField.CERTIFICATION_ID]):
            is_ok = False
            if movie[MovieField.CERTIFICATION_ID] != '':
                cls._logger.debug_verbose(
                    f'Invalid certification: {movie[MovieField.CERTIFICATION_ID]} for movie: '
                    '{movie[MovieField.TITLE]} set to NR')
            movie[MovieField.CERTIFICATION_ID] = certifications.get_unrated_certification() \
                .get_preferred_id()

        # assert is_ok, 'LEAK, Invalid property values'
        return is_ok

    @classmethod
    def total_size(cls, o, handlers: Dict[Any, Any] = None, verbose: bool = False):
        """ Returns the approximate memory footprint an object and all of its contents.

        Automatically finds the contents of the following builtin containers and
        their subclasses:  tuple, list, deque, dict, set and frozenset.
        To search other containers, add handlers to iterate over their contents:

            handlers = {SomeContainerClass: iter,
                        OtherContainerClass: OtherContainerClass.get_elements}

        """
        if handlers is None:
            handlers = {}

        dict_handler = lambda d: chain.from_iterable(d.items())

        all_handlers = {tuple: iter,
                        list: iter,
                        deque: iter,
                        dict: dict_handler,
                        set: iter,
                        frozenset: iter,
                       }
        all_handlers.update(handlers)     # user handlers take precedence
        seen = set()                      # track which object id's have already been seen
        default_size = getsizeof(0)       # estimate sizeof object without __sizeof__

        def sizeof(o):
            if id(o) in seen:       # do not double count the same object
                return 0
            seen.add(id(o))
            s = getsizeof(o, default_size)

            if verbose:
                cls._logger.debug_verbose(f'size: {s} type: {type(o)} repr: {repr(o)}')

            for typ, handler in all_handlers.items():
                if isinstance(o, typ):
                    s += sum(map(sizeof, handler(o)))
                    break
            return s

        return sizeof(o)
