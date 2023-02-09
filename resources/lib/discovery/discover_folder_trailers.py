# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: fbacher
"""

import datetime
import os
import sys

import xbmcvfs

from common.certification import Certification, Certifications, WorldCertifications
from common.debug_utils import Debug
from common.disk_utils import DiskUtils
from common.exceptions import AbortException, reraise
from common.monitor import Monitor
from common.movie import FolderMovie, LibraryMovie
from common.movie_constants import MovieField, MovieType
from common.logger import *
from common.settings import Settings
from discovery.folder_trailer_fetcher import FolderTrailerFetcher
from discovery.movie_detail import MovieDetail
from discovery.restart_discovery_exception import StopDiscoveryException
from discovery.base_discover_movies import BaseDiscoverMovies
from discovery.folder_movie_data import FolderMovieData
from .__init__ import *

module_logger: Final[BasicLogger] = BasicLogger.get_module_logger(module_path=__file__)


class DiscoverFolderTrailers(BaseDiscoverMovies):
    """
        The subtrees specified by the path/multipath are
        assumed to contain movie trailers.
        Create skeleton movie info for every file found,
        containing only the file and directory names.
    """

    _singleton_instance: ForwardRef('DiscoverFolderTrailers') = None
    logger: BasicLogger = None

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
        self._movie_data = FolderMovieData(trailer_fetcher_class=
                                           FolderTrailerFetcher)

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Returns True when the Settings indicate this type of trailer should
        be discovered

        :return:
        """
        return Settings.is_include_trailer_folders()

    def discover_basic_information(self) -> None:
        """

        :return:
        """
        clz = type(self)

        self.start()
        # self._parent_trailer_fetcher.start_fetchers(self)
        if clz.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
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

                    used_memory: int = self._movie_data.get_size_of()
                    used_mb: float = float(used_memory) / 1000000.0
                    self.logger.debug(f'movie_data size: {used_memory} MB: {used_mb}')
                except StopDiscoveryException:
                    # Restart discovery
                    if clz.logger.isEnabledFor(DEBUG):
                        clz.logger.debug('Restarting discovery')
                    if not Settings.is_include_trailer_folders():
                        finished = True
                        # self.destroy()

        except AbortException:
            return  # Just exit thread
        except Exception:
            clz.logger.exception('')

        self.finished_discovery()
        duration = datetime.datetime.now() - start_time
        if clz.logger.isEnabledFor(DEBUG):
            clz.logger.debug(f'Time to discover: {duration.seconds} seconds',
                             trace=Trace.STATS)

    def discover_basic_information_worker(self, path: str) -> None:
        """

        :param path:
        :return:
        """
        clz = type(self)

        try:
            _country_id: str = Settings.get_country_iso_3166_1().lower()
            _certifications: Certifications = \
                WorldCertifications.get_certifications(_country_id)
            unrated_certification: Certification = \
                _certifications.get_unrated_certification()
            unrated_certification_id = unrated_certification.get_preferred_id()
            folders: List[str] = []
            if str(path).startswith('multipath://'):
                # get all paths from the multipath
                paths: List[str] = path[12:-1].split('/')
                for item in paths:
                    folders.append(item)
            else:
                folders.append(path)
            DiskUtils.RandomGenerator.shuffle(folders)
            for folder in folders:
                Monitor.throw_exception_if_abort_requested()
                translated_path: str = xbmcvfs.translatePath(folder)
                # translated_path MUST end in backslash (weird)
                if translated_path[-1] != '/':
                    translated_path += '/'

                if xbmcvfs.exists(translated_path):
                    # get all files and sub-folders
                    dirs, files = xbmcvfs.listdir(translated_path)

                    # Assume every file is a movie movie. Manufacture
                    # a movie name and other info from the filename.
                    DiskUtils.RandomGenerator.shuffle(files)
                    for item in files:
                        try:
                            file_path: str = os.path.join(
                                folder, item)

                            file_path: str = xbmcvfs.translatePath(file_path)
                            # TODO: DELETE ME

                            title = os.path.basename(file_path)
                            title = os.path.splitext(title)[0]
                            new_movie_data: MovieType = {MovieField.TITLE: title,
                                                         MovieField.TRAILER: file_path,
                                                         MovieField.TRAILER_TYPE:
                                                             MovieField.TRAILER_TYPE_TRAILER,
                                                         MovieField.SOURCE:
                                                             MovieField.FOLDER_SOURCE}
                            new_movie: FolderMovie = FolderMovie(
                                movie_info=new_movie_data)
                            new_movie.set_certification_id(unrated_certification_id)

                            # Supply fake values to displayed fields to make code happy.

                            MovieDetail.clone_fields(new_movie, new_movie,
                                                     MovieField.DEFAULT_MOVIE)
                            if clz.logger.isEnabledFor(DEBUG):
                                clz.logger.debug_extra_verbose(f'title: {title} '
                                                               f'path: {file_path}')
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
        clz.logger.debug('Enter')

        try:
            stop_thread: bool = not Settings.is_include_trailer_folders()
            if stop_thread:
                self.stop_thread()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz.logger.exception('')

    def needs_restart(self) -> bool:
        """
            A restart is needed when settings that impact our results have
            changed.

            :returns: True if settings have changed requiring restart
                      False if relevant settings have changed or if it should
                      be allowed to die without restart
        """

        return False
