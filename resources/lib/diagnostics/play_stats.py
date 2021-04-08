# -*- coding: utf-8 -*-

import datetime
import io
import os
import threading
import sys

from common.constants import Constants, Movie
from common.exceptions import AbortException, DuplicateException
from common.imports import *
from common.monitor import Monitor
from backend.movie_entry_utils import (MovieEntryUtils)
from common.logger import (Trace, LazyLogger)

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class PlayStatistics:
    """

    """
    logger: LazyLogger = None
    _total_removed: int = 0
    _play_count: Dict[str, int] = dict()
    _key_to_movie: Dict[str, MovieType] = {}
    _lock: threading.RLock = threading.RLock()
    _number_of_added_movies = 0
    report: io.TextIOBase = None
    _first_call: bool = True

    @classmethod
    def init_class(cls) -> None:
        """
        :param movie_source:
        :return:
        """
        clz = PlayStatistics

        if clz.logger is None:
            clz.logger = module_logger.getChild(clz.__name__)

    @classmethod
    def clear(cls) -> None:
        """

        :return:
        """
        clz = PlayStatistics

        with cls._lock:
            cls._number_of_added_movies = 0

    @classmethod
    def add(cls, movie: MovieType) -> None:
        """

        :param movie:
        :return:
        """
        clz = PlayStatistics

        # if clz.logger.isEnabledFor(LazyLogger.DEBUG):
        # clz.logger.debug('movie:', movie[Movie.TITLE], 'source:',
        #                   movie[Movie.SOURCE])
        key = cls.get_key(movie)
        with cls._lock:
            cls._play_count.setdefault(key, 0)
            cls._number_of_added_movies += 1

    @classmethod
    def get_play_count(cls, movie: MovieType) -> int:
        """

        :param movie:
        :return:
        """
        clz = PlayStatistics

        count = None
        try:
            with cls._lock:
                count = cls._play_count.get(cls.get_key(movie), 0)
        except KeyError as e:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                clz.logger.debug(
                    'Could not find entry for:', movie[Movie.TITLE])

        return count

    @classmethod
    def increase_play_count(cls, movie: MovieType) -> None:
        """

        :param movie:
        :return:
        """
        clz = PlayStatistics

        try:
            key = cls.get_key(movie)
            with cls._lock:
                count = cls._play_count.get(key, 0) + 1
                cls._play_count[key] = count
                cls._key_to_movie[key] = movie

        except KeyError as e:
            if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                clz.logger.debug('Could not find entry for:',
                                 movie[Movie.TITLE])
        return

    @classmethod
    def report_play_count_stats(cls) -> None:
        """

        :return:
        """
        clz = PlayStatistics
        if not clz.logger.is_trace_enabled(Trace.TRACE_PLAY_STATS):
            return

        try:
            path = Constants.PLAY_STATISTICS_REPORT_PATH
            save_path = path + '.old'
            directory = os.path.dirname(path)
            os.makedirs(directory, mode=0o751, exist_ok=True)
            if clz._first_call and os.path.exists(save_path):
                os.replace(path, save_path)
                clz.first_call = False

            with cls._lock, \
                io.open(path, 'at',
                        newline=None, encoding='utf-8') as cls.report:
                Monitor.throw_exception_if_abort_requested()
                timestamp = datetime.datetime.now().strftime('%c')
                cls.report.write(f'Cumulative report for a Kodi session. {timestamp}\n\n')
                movie_keys = sorted(cls._play_count, key=lambda key: cls._play_count[key],
                                    reverse=False)
                # Number of times this set of movies were played
                previous_play_count = -1
                # Running count of number of discovered movies
                movie_count = 0
                movie_count_in_group = 0
                # Total number of movies that were played
                total_play_count = 0
                # play_count is number of times a movie was played
                movies_with_same_count = []
                for movie_key in movie_keys:
                    Monitor.throw_exception_if_abort_requested()
                    play_count = cls._play_count[movie_key]
                    if play_count == previous_play_count:
                        movie_count_in_group += 1
                        movies_with_same_count.append(movie_key)
                    else:
                        if previous_play_count != -1:
                            line = f'{movie_count_in_group} movies played:' \
                                f' {previous_play_count} times.\n'
                            cls.report.write(line)
                            if previous_play_count != 0:
                                cls.wrap_text(movies_with_same_count,
                                              include_source=True)
                            del movies_with_same_count[:]
                            movie_count += movie_count_in_group
                            total_play_count += previous_play_count * movie_count_in_group

                        movie_count_in_group = 1
                        movies_with_same_count.append(movie_key)
                        previous_play_count = play_count

                # movie_count_in_group += 1
                if movie_count_in_group > 0:
                    movie_count += movie_count_in_group
                    total_play_count += previous_play_count * movie_count_in_group
                    line = f'{movie_count_in_group} movies played {previous_play_count} ' \
                        f'times\n'
                    cls.report.write(line)
                    if previous_play_count > 0:
                        cls.wrap_text(movies_with_same_count, include_source=True)

                line = f'Total movies played: {total_play_count} Total Movies: ' \
                    f'{movie_count} Total Removed: {cls._total_removed} Total Added: ' \
                    f'{cls._number_of_added_movies}\n\n\n'
                cls.report.write(line)

        except AbortException:
            reraise(*sys.exc_info())

        except Exception as e:
            clz.logger.exception('')

    MAX_LINE_LENGTH: Final[int] = 80

    @classmethod
    def wrap_text(cls, movies_with_same_count: List[str],
                  include_source: bool = False) -> None:
        """

        :param logger:
        :param movies_with_same_count:
        :param include_source:
        :return:
        """
        clz = PlayStatistics

        movies_in_line: List[str] = []
        line_length = 3  # Initial spaces
        movie_title: str = ''
        for key in movies_with_same_count:
            Monitor.throw_exception_if_abort_requested()
            try:
                movie: Optional[MovieType] = cls._key_to_movie.get(key, None)
                if movie is not None:
                    movie_title = movie.get(Movie.TITLE, 'unknown')
                else:
                    movie_title = 'Not in dictionary'
                if include_source:
                    movie_title = movie_title + f': {movie.get(Movie.SOURCE)}'

                if line_length + len(movie_title) >= clz.MAX_LINE_LENGTH:
                    line = '   {}\n'.format(', '.join(movies_in_line))
                    cls.report.write(line)
                    del movies_in_line[:]
                    line_length = 3  # Initial spaces

            except AbortException:
                reraise(*sys.exc_info())

            except Exception as e:
                clz.logger.exception()

            movies_in_line.append(movie_title)
            line_length += len(movie_title) + 2  # Slightly inaccurate

        if len(movies_in_line) > 0:
            try:
                line = '   {}\n'.format(', '.join(movies_in_line))
                cls.report.write(line)
            except Exception as e:
                clz.logger.exception()

    @staticmethod
    def get_key(movie: MovieType) -> str:
        """

        :param movie:
        :return:
        """

        key = None
        movie_source = movie[Movie.SOURCE]
        if movie_source == Movie.TMDB_SOURCE:
            key = str(MovieEntryUtils.get_tmdb_id(movie))
        elif movie_source == Movie.ITUNES_SOURCE:
            key = movie[Movie.ITUNES_ID]
        elif movie_source == Movie.LIBRARY_SOURCE:
            key = movie_source + str(movie[Movie.MOVIEID])
        elif movie_source == Movie.TFH_SOURCE:
            key = movie_source + str(movie[Movie.TFH_ID])

        return key


PlayStatistics.init_class()
