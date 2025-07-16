# -*- coding: utf-8 -*-
"""
Created on 10/15/21

@author: Frank Feuerbacher
"""

import datetime

from common.movie_constants import MovieField
from common.playlist import Playlist
from common.exceptions import AbortException, CommunicationException, reraise
from common.imports import *
from common.settings import Settings
from common.logger import *

from discovery.abstract_movie_data import AbstractMovieData
from discovery.abstract_trailer_fetcher import AbstractTrailerFetcher
from discovery.playable_trailers_container_interface import \
    PlayableTrailersContainerInterface
from .__init__ import *

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class LibraryNoTrailerTrailerFetcher(AbstractTrailerFetcher):
    """
    The Discover* classes do the initial discovery to get the basic information
    about movies to have their trailers played. This class is responsible for
    discovering everything else needed to actually play the trailer (i.e. the
    trailer might needed downloading, Extra metadata may be needed from TMDB,
    etc.).

    TODO: Originally designed to have multiple fetchers per movie type. As
          such, an instance was initially created to "manage" the other
          instances. This manager is not needed when a single fetcher is used,
          someday someone should get rid of the extra 'manager'.
    """

    _logger: BasicLogger = None

    def __init__(self, *args: Any, movie_data: AbstractMovieData = None,
                 **kwargs: Any) -> None:
        """

                 :param movie_data
                 :param name:
        """
        clz = type(self)
        clz._logger = module_logger.getChild(clz.__name__)
        thread_name: Final[str] = f'{MovieField.LIBRARY_NO_TRAILER}_fetcher'

        super().__init__(*args, movie_data=movie_data, name=thread_name,
                         **kwargs)
        self._movie_data: AbstractMovieData = movie_data

        self._playable_trailers: PlayableTrailersContainerInterface = \
            PlayableTrailersContainerInterface.get_container(
                movie_data.get_movie_source())
        self._playable_trailers.set_movie_data(movie_data)
        self._missing_trailers_playlist: Playlist = Playlist.get_playlist(
            Playlist.MISSING_TRAILERS_PLAYLIST, append=False, rotate=True)
        self._start_fetch_time: datetime.datetime = None
        self._stop_fetch_time: datetime.datetime = None
        self._stop_add_ready_to_play_time: datetime.datetime = None
        self._stop_thread: bool = False
        self._child_trailer_fetchers: List['LibraryNoTrailerTrailerFetcher'] = []
