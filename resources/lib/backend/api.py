# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

from common.logger import (Logger, LazyLogger, Trace)
from common.constants import Constants, Movie
from common.settings import Settings
from common.monitor import Monitor
from backend.movie_utils import LibraryMovieStats
from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.discover_library_movies import DiscoverLibraryMovies
from discovery.discover_folder_trailers import DiscoverFolderTrailers
from discovery.discover_itunes_movies import DiscoverItunesMovies
from discovery.discover_tmdb_movies import DiscoverTmdbMovies
from discovery.discover_tfh_movies import DiscoverTFHMovies

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


def load_trailers():
    # type: () ->None
    """
        Start up the configured trailer discovery threads.

        Called whenever settings have changed to start any threads
        that have just ben enabled.

    :return:
    """

    module_logger.enter()

    instances = BaseDiscoverMovies.get_instances()
    if (Settings.get_include_library_trailers()
            and instances.get(Movie.LIBRARY_SOURCE) is None):
        if module_logger.isEnabledFor(Logger.DEBUG):
            module_logger.debug('LibTrailers True')
        lib_instance = DiscoverLibraryMovies()
        lib_instance.discover_basic_information()
    else:
        if module_logger.isEnabledFor(Logger.DEBUG):
            module_logger.debug('LibTrailers False')

    # Manufacture trailer entries for folders which contain trailer
    # files. Note that files are assumed to be videos.
    if (Settings.get_include_trailer_folders()
            and instances.get(Movie.FOLDER_SOURCE) is None):
        DiscoverFolderTrailers().discover_basic_information()

    if (Settings.get_include_itunes_trailers()
            and instances.get(Movie.ITUNES_SOURCE) is None):
        DiscoverItunesMovies().discover_basic_information(
        )

    if (Settings.get_include_tmdb_trailers()
            and instances.get(Movie.TMDB_SOURCE) is None):
        DiscoverTmdbMovies().discover_basic_information()

    if (Settings.is_include_tfh_trailers()
            and instances.get(Movie.TFH_SOURCE) is None):
        DiscoverTFHMovies().discover_basic_information()

    Monitor.throw_exception_if_abort_requested(timeout=1.0)
    Monitor.set_startup_complete()


def get_genres_in_library():
    # type: () -> List[str]
    """

    :return:
    """
    return LibraryMovieStats.get_genres_in_library()
