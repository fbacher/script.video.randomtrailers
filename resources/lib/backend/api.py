# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
import sys

from common.exceptions import AbortException
from common.garbage_collector import GarbageCollector
from common.imports import *
from common.logger import LazyLogger
from common.monitor import Monitor
from backend.movie_stats import LibraryMovieStats
from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.discover_library_movies import DiscoverLibraryMovies
from discovery.discover_folder_trailers import DiscoverFolderTrailers
from discovery.discover_itunes_movies import DiscoverItunesMovies
from discovery.discover_tmdb_movies import DiscoverTmdbMovies
from discovery.discover_tfh_movies import DiscoverTFHMovies

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class DiscoveryInstance:
    INDEX = 0
    CLASS = 1

    def __init__(self, value: Tuple[int, Type[BaseDiscoverMovies]]) -> None:
        clz = type(self)
        self._index: int = value[clz.INDEX]
        self._class: Type[BaseDiscoverMovies] = value[clz.CLASS]
        self._instance: BaseDiscoverMovies = None
        self._started: bool = False
        self._instance: BaseDiscoverMovies = None

    def get_index(self) -> int:
        clz = type(self)
        return self._index

    def get_class(self) -> Type[BaseDiscoverMovies]:
        clz = type(self)
        return self._class

    def get_instance(self) -> BaseDiscoverMovies:
        return self._instance

    def clear_instance(self) -> None:
        self._instance = None
        self._started = False

    def begin_discovery(self) -> BaseDiscoverMovies:
        self._instance = self.get_class()()
        self._instance.discover_basic_information()
        self._started = True
        return self._instance

    def join_instance(self) -> None:
        if self._instance is not None:
            self._instance.join(0.25)

    def is_started(self) -> bool:
        return self._started


class DiscoveryManager:

    LIBRARY: Final[int] = 0
    # LIBRARY_URL: Final[int] = 1  # Handled via LIBRARY
    # LIBRARY_NO_TRAILER: Final[int] = 2
    FOLDER: Final[int] = 1
    ITUNES: Final[int] = 2
    TMDB: Final[int] = 3
    TFH: Final[int] = 4

    DISCOVERY_INFO: Final[List[Tuple[int, Type[BaseDiscoverMovies]]]] = [
        (LIBRARY, DiscoverLibraryMovies),
        (FOLDER, DiscoverFolderTrailers),
        (ITUNES, DiscoverItunesMovies),
        (TMDB, DiscoverTmdbMovies),
        (TFH, DiscoverTFHMovies)
        ]

    _discovery_instance_table: List[DiscoveryInstance] = [
        DiscoveryInstance(DISCOVERY_INFO[LIBRARY]),
        DiscoveryInstance(DISCOVERY_INFO[FOLDER]),
        DiscoveryInstance(DISCOVERY_INFO[ITUNES]),
        DiscoveryInstance(DISCOVERY_INFO[TMDB]),
        DiscoveryInstance(DISCOVERY_INFO[TFH])
    ]

    _logger: LazyLogger = None
    _initialized: bool = False

    _lib_instance: DiscoverLibraryMovies = None
    _lib_discovery_started = False
    _folder_instance: DiscoverFolderTrailers = None
    _folder_discovery_started = False
    _itunes_instance: DiscoverItunesMovies = None
    _itunes_discovery_started = False
    _tmdb_instance: DiscoverTmdbMovies = None
    _tmdb_discovery_started = False
    _tfh_instance: DiscoverTFHMovies = None
    _tfh_discovery_started = False

    @classmethod
    def load_trailers(cls) -> None:
        """
            Start up the configured movie discovery threads.

            Called whenever settings have changed to start any threads
            that have just ben enabled.

        :return:
        """

        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__class__.__name__)

        for info in cls._discovery_instance_table:
            try:
                instance = info.get_instance()
                discovery_class: Type[BaseDiscoverMovies] = info.get_class()
                if discovery_class.is_enabled():
                    if (instance is not None
                            and (instance.needs_restart() or not info.is_started())):
                        instance.stop_thread()
                        instance.destroy()
                        GarbageCollector.add_thread(instance)
                        info.clear_instance()
                        instance = None
                    if instance is None:
                        instance = info.begin_discovery()
                elif instance is not None:
                    instance.stop_thread()
                    instance.destroy()
                    GarbageCollector.add_thread(instance)
                    info.clear_instance()
            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                cls._logger.exception()

        if not cls._initialized:
            Monitor.throw_exception_if_abort_requested(timeout=1.0)
            Monitor.set_startup_complete()
            Monitor.register_settings_changed_listener(cls.load_trailers,
                                                       'DiscoveryManager.load_trailers')
            cls._initialized = True

    @classmethod
    def get_genres_in_library(cls) -> List[str]:
        """

        :return:
        """
        return LibraryMovieStats.get_genres_in_library()
