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

from common.constants import Constants, Movie
from common.debug_utils import Debug
from common.disk_utils import DiskUtils
from common.exceptions import AbortException
from common.imports import *
from common.monitor import Monitor
from common.logger import (LazyLogger, Trace)
from common.settings import Settings

from discovery.restart_discovery_exception import RestartDiscoveryException
from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.folder_movie_data import FolderMovieData

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


# noinspection Annotator,PyArgumentList,PyArgumentList
class DiscoverFolderTrailers(BaseDiscoverMovies):
    """
        The subtrees specified by the path/multipath are
        assumed to contain movie trailers.
        Create skeleton movie info for every file found,
        containing only the file and directory names.
    """

    _singleton_instance = None
    logger = None

    def __init__(self):
        # type: () -> None
        """

        """
        local_class = DiscoverFolderTrailers
        if local_class.logger is None:
            local_class.logger = module_logger.getChild(local_class.__name__)
        thread_name = local_class.__name__
        kwargs = {Movie.SOURCE: Movie.FOLDER_SOURCE}
        super().__init__(group=None, target=None, thread_name=thread_name,
                         args=(), kwargs=None)
        self._movie_data = FolderMovieData()

    def discover_basic_information(self):
        # type: () -> None
        """

        :return:
        """
        local_class = DiscoverFolderTrailers

        self.start()
        # self._trailer_fetcher.start_fetchers(self)
        if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
            local_class.logger.debug(': started')

    def run(self):
        # type: () -> None
        """

        :return:
        """
        local_class = DiscoverFolderTrailers

        if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
            try:
                import resource

                memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                local_class.logger.debug(': memory: ' + str(memory))
            except ImportError:
                pass

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
                    if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                        local_class.logger.debug('Restarting discovery')
                    self.prepare_for_restart_discovery()
                    if not Settings.get_include_trailer_folders():
                        finished = True
                        self.remove_self()

        except AbortException:
            return  # Just exit thread
        except Exception:
            local_class.logger.exception('')

        self.finished_discovery()
        duration = datetime.datetime.now() - start_time
        if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
            local_class.logger.debug('Time to discover:', duration.seconds,
                                     'seconds', trace=Trace.STATS)

    def discover_basic_information_worker(self, path):
        # type: (str) -> None
        """

        :param path:
        :return:
        """
        local_class = DiscoverFolderTrailers

        try:
            folders = []
            if str(path).startswith('multipath://'):
                # get all paths from the multipath
                paths = path[12:-1].split('/')
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

                    # Assume every file is a movie trailer. Manufacture
                    # a movie name and other info from the filename.
                    DiskUtils.RandomGenerator.shuffle(files)
                    for item in files:
                        try:
                            file_path = os.path.join(
                                folder, item)

                            title = xbmcvfs.translatePath(file_path)
                            # TODO: DELETE ME

                            title = os.path.basename(title)
                            title = os.path.splitext(title)[0]
                            new_trailer = {Movie.TITLE: title,
                                           Movie.TRAILER: file_path,
                                           Movie.TYPE: 'trailer file',
                                           Movie.SOURCE:
                                           Movie.FOLDER_SOURCE,
                                           Movie.FANART: '',
                                           Movie.THUMBNAIL: '',
                                           Movie.FILE: '',
                                           Movie.YEAR: ''}
                            if local_class.logger.isEnabledFor(LazyLogger.DEBUG):
                                Debug.validate_basic_movie_properties(
                                    new_trailer)
                            self.add_to_discovered_trailers(
                                new_trailer)

                        except AbortException:
                            reraise(*sys.exc_info())
                        except Exception as e:
                            local_class.logger.exception('')

                    for item in dirs:
                        # recursively scan all sub-folders
                        sub_tree = os.path.join(folder, item)
                        self.discover_basic_information_worker(
                            sub_tree)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            local_class.logger.exception('')
        return

    def on_settings_changed(self):
        # type: () -> None
        """
            Settings changes only impact Folder Trailers to stop it. Since
            we are here, Folder Trailer discover was active prior to the
            settings change, therefore, only do something if we are no longer
            active.
        """
        local_class = DiscoverFolderTrailers
        local_class.logger.enter()

        try:
            stop_thread = not Settings.get_include_trailer_folders()
            if stop_thread:
                self.restart_discovery(stop_thread)
        except Exception as e:
            local_class.logger.exception('')
