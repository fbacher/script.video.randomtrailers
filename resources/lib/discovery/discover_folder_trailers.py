# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: fbacher
"""

import datetime
import os
import requests
import sys

import xbmcvfs

from common.debug_utils import Debug
from common.disk_utils import DiskUtils
from common.exceptions import AbortException, reraise
from common.imports import *
from common.monitor import Monitor
from common.movie import LibraryMovie
from common.movie_constants import MovieField, MovieType
from common.logger import LazyLogger, Trace
from common.settings import Settings

from discovery.restart_discovery_exception import RestartDiscoveryException
from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.folder_movie_data import FolderMovieData

module_logger: Final[LazyLogger] = LazyLogger.get_addon_module_logger(file_path=__file__)


class DiscoverFolderTrailers(BaseDiscoverMovies):
    """
        The subtrees specified by the path/multipath are
        assumed to contain movie trailers.
        Create skeleton movie info for every file found,
        containing only the file and directory names.
    """

    _singleton_instance: ForwardRef('DiscoverFolderTrailers') = None
    logger: LazyLogger = None

    def __init__(self) -> None:
        """

        """
        clz = type(self)
        if clz.logger is None:
            clz.logger = module_logger.getChild(clz.__name__)

        thread_name = 'Disc Folder'
        kwargs = {MovieField.SOURCE: MovieField.FOLDER_SOURCE}
        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=kwargs)
        self._movie_data = FolderMovieData()

    def discover_basic_information(self) -> None:
        """

        :return:
        """
        clz = type(self)

        self.start()
        # self._trailer_fetcher.start_fetchers(self)
        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz.logger.debug_extra_verbose(': started')

    def run(self) -> None:
        """

        :return:
        """
        clz = type(self)

        start_time = datetime.datetime.now()
        try:
            finished = False
            while not finished:
                try:
                    self.discover_basic_information_worker(
                        Settings.get_trailers_paths())
                    self.wait_until_restart_or_shutdown()
                except RestartDiscoveryException:
                    # Restart discovery
                    if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                        clz.logger.debug('Restarting discovery')
                    self.prepare_for_restart_discovery()
                    if not Settings.get_include_trailer_folders():
                        finished = True
                        self.remove_self()

        except AbortException:
            return  # Just exit thread
        except Exception:
            clz.logger.exception('')

        self.finished_discovery()
        duration = datetime.datetime.now() - start_time
        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.debug(f'Time to discover: {duration.seconds} seconds',
                             trace=Trace.STATS)

    def discover_basic_information_worker(self, path: str) -> None:
        """

        :param path:
        :return:
        """
        clz = type(self)

        try:
            folders: List[str] = []
            if str(path).startswith('multipath://'):
                # get all paths from the multipath
                paths: List[str] = path[12:-1].split('/')
                for item in paths:
                    folders.append(requests.utils.unquote_unreserved(item))
            else:
                folders.append(path)
            DiskUtils.RandomGenerator.shuffle(folders)
            for folder in folders:
                Monitor.throw_exception_if_abort_requested()

                if xbmcvfs.exists(xbmcvfs.translatePath(folder)):
                    # get all files and sub-folders
                    dirs, files = xbmcvfs.listdir(folder)

                    # Assume every file is a movie movie. Manufacture
                    # a movie name and other info from the filename.
                    DiskUtils.RandomGenerator.shuffle(files)
                    for item in files:
                        try:
                            file_path: str = os.path.join(
                                folder, item)

                            title: str = xbmcvfs.translatePath(file_path)
                            # TODO: DELETE ME

                            title = os.path.basename(title)
                            title = os.path.splitext(title)[0]
                            new_movie_data: MovieType = {MovieField.TITLE: title,
                                                         MovieField.TRAILER: file_path,
                                                         MovieField.TRAILER_TYPE:
                                                             'movie file',
                                                         MovieField.SOURCE:
                                                             MovieField.FOLDER_SOURCE,
                                                         MovieField.FANART: '',
                                                         MovieField.THUMBNAIL: '',
                                                         MovieField.FILE: '',
                                                         MovieField.YEAR: ''}
                            new_movie: LibraryMovie = LibraryMovie(
                                movie_info=new_movie_data)
                            if clz.logger.isEnabledFor(LazyLogger.DEBUG):
                                Debug.validate_basic_movie_properties(
                                    new_movie)
                            self.add_to_discovered_movies(
                                new_movie)

                        except AbortException:
                            reraise(*sys.exc_info())
                        except Exception as e:
                            clz.logger.exception('')

                    for item in dirs:
                        # recursively scan all sub-folders
                        sub_tree = os.path.join(folder, item)
                        self.discover_basic_information_worker(
                            sub_tree)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')
        return

    def on_settings_changed(self) -> None:
        """
            Settings changes only impact Folder Trailers to stop it. Since
            we are here, Folder Trailer discover was active prior to the
            settings change, therefore, only do something if we are no longer
            active.
        """
        clz = type(self)
        clz.logger.enter()

        try:
            stop_thread: bool = not Settings.get_include_trailer_folders()
            if stop_thread:
                self.restart_discovery(stop_thread)
        except Exception as e:
            clz.logger.exception('')
