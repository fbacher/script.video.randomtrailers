# -*- coding: utf-8 -*-
"""
Created on 7/20/22

@author: Frank Feuerbacher

Tools to create simulated movies (dummy entries) based upon downloaded TMDb
entries. In this way you can use RandomTrailers to download movie information
based upon search criteria, say, for Japanese.  From that info you can then
generate fake movies to exercise Kodi and or plugins  in some way that you want.
"""
import io
import queue
import threading
from pathlib import Path
import re

import xbmcvfs

from cache.cache import Cache
from cache.tmdb_utils import TMDbUtils
from common.imports import *

import datetime
import os
import random
import sys

from common.constants import Constants
from common.exceptions import AbortException, reraise
from common.logger import LazyLogger
from common.monitor import Monitor
from common.settings import Settings
from common.utils import Delay
from common.garbage_collector import GarbageCollector
from common.disk_utils import (FindFiles, FindFilesIterator)
from common.movie import MovieField, TMDbMovie, TMDbMovieId

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class Tools:
    _logger = None

    @classmethod
    def __init__(cls) -> None:
        """

        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def create_fake_movie_entries(cls) -> None:
        if cls._logger is None:
            cls.__init__()

        top: str = Settings.get_downloaded_trailer_cache_path()
        TMDB_GLOB_JSON_PATTERN: str = '**/tmdb_[0-9]*.json'

        # cls._logger.debug(f'top: {top}')

        finder: FindFiles = FindFiles(top)
        #  Delay one second on each call.
        # delay = Delay(bias=1.0, call_scale_factor=0.0, scale_factor=0.0)
        path: Path
        tmdb_movie_ids: List[TMDbMovieId] = []
        # tmdb_movie_ids: List[int] = []
        for path in finder:
            # cls._logger.debug(f'path: {path}')
            Monitor.throw_exception_if_abort_requested()
            if path.match(TMDB_GLOB_JSON_PATTERN):
                try:
                    if path.is_file():
                        tmdb_id: str
                        tmdb_id = os.path.basename(path)
                        tmdb_id = tmdb_id.replace('.json', '')
                        tmdb_id = re.sub(r'.*tmdb_', '', tmdb_id)
                        tmdb_id.replace('[^0-9]*', '')
                        tmdb_movie_id: TMDbMovieId = TMDbMovieId(tmdb_id)
                        tmdb_movie_ids.append(tmdb_movie_id)
                        cls._logger.debug(f'tmdb_id: {tmdb_id}')
                    else:
                        continue
                except OSError as e:
                    continue  # File doesn't exist
                except Exception as e:
                    cls._logger.exception('')
                    continue

        movies: List[TMDbMovie] = []
        cls._logger.debug(f'requesting: {len(tmdb_movie_ids)} fake movie entries')
        # movies = Cache.get_cached_tmdb_movie(tmdb_movie_ids, len(tmdb_movie_ids))
        movies = TMDbUtils.load_from_cache(tmdb_movie_ids, len(tmdb_movie_ids))
        cls._logger.debug(f'got {len(movies)} movie entries')
        tmdb_movie: TMDbMovie
        simulated_file_names: str = f'{Constants.FRONTEND_DATA_PATH}/simulated_movie_paths'
        Monitor.throw_exception_if_abort_requested()
        try:
            with io.open(simulated_file_names, mode='wt', newline=None,
                         encoding='utf-8') as smimulated_paths:
                file_path: str
                for tmdb_movie in movies:
                    fake_movie_filename: str
                    fake_movie_filename = \
                        f'{tmdb_movie.get_title()} ({str(tmdb_movie.get_year())}).mkv'
                    cls._logger.debug(f'fake movie: {fake_movie_filename}')
                    smimulated_paths.write(f'{fake_movie_filename}\n')
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')
