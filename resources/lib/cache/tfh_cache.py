# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import datetime

import io
import simplejson as json
from simplejson import JSONDecodeError
import os
import threading

import xbmcvfs
from common.imports import *

from common.debug_utils import Debug
from common.logger import LazyLogger
from common.monitor import Monitor
from common.movie import TFHMovie
from common.movie_constants import MovieField, MovieType
from common.settings import Settings
from common.disk_utils import DiskUtils
from common.utils import Utils

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TFHCache:
    """
    Trailers From Hell has an index of all of the trailers that they produce.
    We don't rely on the index being static. It is not really searchable.
    When this cache is determined to be expired, the entire index must be
    retrieved and this list recreated.
    """
    UNINITIALIZED_STATE = 'uninitialized_state'
    INDEX_CREATION_DATE = 'INDEX_CREATION_DATE'
    CACHE_COMPLETE = "CACHE_COMPLETE"
    INCOMPLETE_CREATION_DATE_STR = '1900:01:01'
    _initialized = threading.Event()
    lock = threading.RLock()
    _logger: LazyLogger = None
    _cached_movies: Dict[str, TFHMovie] = {}
    _last_saved_trailer_timestamp = datetime.datetime.now()
    _unsaved_movie_changes: int = 0

    # Cache is marked with timestamp of last update of movie ids from TFH
    # Also marked whether the cache was completely updated.

    _time_of_index_creation = datetime.datetime(2000, 1, 1)  # expired
    _cache_complete = False

    @classmethod
    def class_init(cls) -> None:
        """
        :return:
        """
        cls._logger = module_logger.getChild(type(cls).__name__)
        cls.load_cache()
        cls._logger.debug('load_cache complete')

    @classmethod
    def logger(cls) -> LazyLogger:
        """

        :return:
        """
        cls._initialized.wait()
        return cls._logger

    @classmethod
    def save_cache(cls, flush: bool = False, complete: bool = False) -> None:
        """
        :param flush:
        :param complete:
        :return:

        Typical json entry
        Items marked with * are kodi/TMDb artifacts

            "BZwDpOQNgpw": {
              "adult": false,
              "cast": [],
              "fanart": "default_fanart",
              "genre": [],
              "mpaa": "NR",
              "normalized_trailer":
              "/home/fbacher/.kodi/userdata/addon_data/script.video.randomtrailers
              /cache/hB/tfh_BZwDpOQNgpw_normalized_Larry Karaszewski on SMOKEY IS THE
              BANDIT (SMOKEY AND THE BANDIT PART 3) (2017)-movie.mkv",
              "original_language": "",
              "plot": "But wait! There's more! TFH has a podcast! \n\nIt's THE MOVIES
              THAT MADE ME, where you can join Oscar-nominated screenwriter Josh Olson
              and his, ummm, \"co-host\" Joe Dante in conversation with filmmakers,
              comedians, and all-around interesting people about the movies that made
              them who they are. Check it out now, and please subscribe wherever
              podcasts can be found.\n\nBut wait! There's more! TFH has a podcast!
              \n\nIt's THE MOVIES THAT MADE ME, where you can join Oscar-nominated
              screenwriter Josh Olson and his, ummm, \"co-host\" Joe Dante in
              conversation with filmmakers, comedians, and all-around interesting
              people about the movies that made them who they are. Check it out now,
              and please subscribe wherever podcasts can be found.\n\niTunes:
              http://itunes.trailersfromhell.com\nSpotify:
              http://spotify.trailersfromhell.com\nLibsyn:
              http://podcast.trailersfromhell.com\nGoogle Play:
              http://googleplay.trailersfromhell.com\nRSS: http://goo.gl/3faeG7\n\nAs
              always, you can find more commentary, more reviews, more podcasts,
              and more deep-dives into the films you don't know you love yet over at
              the Trailers From Hell mothership: \n\nhttp://www.trailersfromhell.com",
              "rating": 4.8974357,
              "genre": [],
              "rts.actors": "",
              "rts.certification": "Unrated",
              "rts.certificationImage": "ratings/us/unrated.png",
              "rts.directors": "",
              "rts.genres": "",
              "rts.runtime": "143 [B]Minutes[/B] - ",
              "rts.studios": "",
              "rts.tfhId": "BZwDpOQNgpw",
              "rts.tfh_title": "SMOKEY IS THE BANDIT (SMOKEY AND THE BANDIT PART 3)",
              "rts.title": "SMOKEY IS THE BANDIT (SMOKEY AND THE BANDIT PART 3) (2017)
              - TFH ",
              "rts.tmdb_id_not_found": true,
              "rts.voiced.actors": [],
              "rts.voiced.directors": [],
              "rts.voiced.studios": [],
              "rts.voiced.writers": [],
              "rts.writers": "",
              "rts.youtube.trailers_in_index": 1449,
              "rts.youtube_index": 204,
              "runtime": 8580,
              "source": "TFH",
              "studio": [
                 []
              ],
              "tags": [
                 "smokey and the bandit 3",
                 "larry karaszewski",
                 "jackie gleason"
              ],
              "thumbnail": "https://i.ytimg.com/vi_webp/BZwDpOQNgpw/maxresdefault.webp",
              "title": "SMOKEY IS THE BANDIT (SMOKEY AND THE BANDIT PART 3)",
              "movie": "https://youtu.be/BZwDpOQNgpw",
              "trailerDiscoveryState": "04_discoveryReadyToDisplay",
              "trailerPlayed": true,
              "trailerType": "default_trailerType",
              "uniqueid": {
                 "tmdb": "None"
              },
              "writer": [
                 []
              ],
              "year": 2017
           }

        """
        cls._initialized.wait()
        with cls.lock:
            if (not flush and
                    (cls._unsaved_movie_changes < 50)
                    and
                    (datetime.datetime.now() - cls._last_saved_trailer_timestamp)
                    < datetime.timedelta(minutes=5)):
                return

            try:
                path = os.path.join(Settings.get_remote_db_cache_path(),
                                    'index', 'tfh_trailers.json')

                path = xbmcvfs.validatePath(path)
                tmp_path = os.path.join(Settings.get_remote_db_cache_path(),
                                        'index', 'tfh_trailers.json.tmp')

                tmp_path = xbmcvfs.validatePath(tmp_path)
                parent_dir, file_name = os.path.split(path)
                if not os.path.exists(parent_dir):
                    DiskUtils.create_path_if_needed(parent_dir)

                Monitor.throw_exception_if_abort_requested()
                with io.open(tmp_path, mode='at', newline=None,
                             encoding='utf-8', ) as cacheFile:

                    if complete:
                        cls._set_creation_date()
                        # Set to True when complete, but don't set to False
                        # when not complete.

                        cls._cache_complete = True

                    creation_date_str = datetime.datetime.strftime(
                        cls._time_of_index_creation, '%Y:%m:%d')

                    dummy_tfh_movie: TFHMovie
                    dummy_tfh_movie = TFHMovie(movie_id=cls.INDEX_CREATION_DATE)
                    dummy_tfh_movie.set_title('cache complete marker')
                    dummy_tfh_movie.set_property(cls.INDEX_CREATION_DATE,
                                                 creation_date_str)
                    dummy_tfh_movie.set_property(cls.CACHE_COMPLETE, cls._cache_complete)
                    
                    cls._cached_movies[cls.INDEX_CREATION_DATE] = dummy_tfh_movie
                    movie: TFHMovie
                    for movie in cls._cached_movies.values():
                        movie.set_cached(True)

                    json_text = json.dumps(cls._cached_movies,
                                           encoding='utf-8',
                                           ensure_ascii=False,
                                           default=TFHCache.encoder,
                                           indent=3, sort_keys=True)
                    cacheFile.write(json_text)
                    cacheFile.flush()

                    # Get rid of dummy entry from local dict
                    del cls._cached_movies[cls.INDEX_CREATION_DATE]
                    cls._last_saved_trailer_timestamp = datetime.datetime.now()
                    cls._unsaved_movie_changes = 0

                try:
                    os.replace(tmp_path, path)
                except OSError:
                    cls._logger.exception(f'Failed to replace missing movie'
                                          f' information cache: {path}')
            except IOError as e:
                cls._logger.exception('')
            except Exception as e:
                cls._logger.exception('')
                for movie in cls._cached_movies.values():
                    Debug.dump_dictionary(movie.get_as_movie_type())

        Monitor.throw_exception_if_abort_requested()

    @classmethod
    def load_cache(cls) -> None:
        """

        :return: True if cache is full and no further discovery needed
        """
        with cls.lock:
            cls._initialized.set()
            try:
                path = os.path.join(Settings.get_remote_db_cache_path(),
                                    'index', 'tfh_trailers.json')
                path = xbmcvfs.validatePath(path)

                parent_dir, file_name = os.path.split(path)
                DiskUtils.create_path_if_needed(parent_dir)

                if os.path.exists(path):
                    with io.open(path, mode='rt', newline=None,
                                 encoding='utf-8') as cacheFile:
                        cls._cached_movies = json.load(
                            cacheFile,
                            object_hook=TFHCache.decoder)
                                                   
                    movie: TFHMovie
                    movie_ids_to_delete: List[str] = []
                    for key, movie in cls._cached_movies.items():
                        if key == cls.INDEX_CREATION_DATE:
                            continue  # Skip marker entry

                        if not movie.is_sane(MovieField.TFH_SKELETAL_MOVIE):
                            movie_ids_to_delete.append(movie.get_id())

                    if len(movie_ids_to_delete) > 0:
                        cls.remove_movies(movie_ids_to_delete, flush=True)
                        
                        # Cache is not complete. Delete marker
                        if cls.INDEX_CREATION_DATE in cls._cached_movies:
                            del cls._cached_movies[cls.INDEX_CREATION_DATE]
                                                                       
                    cls.last_saved_movie_timestamp = None
                    cls._unsaved_movie_changes = 0
                    cls.load_creation_date()
                else:
                    cls._cached_movies = dict()
                    # Set to an old time so that cache is expired
                    cls._time_of_index_creation = datetime.datetime(2000, 1, 1)


            except IOError as e:
                cls._logger.exception('')
            except JSONDecodeError as e:
                os.remove(path)
                cls._logger.exception('')
            except Exception as e:
                cls._logger.exception('')

        Monitor.throw_exception_if_abort_requested()
        return

    @classmethod
    def load_creation_date(cls) -> None:
        # Loads the last time the index was created from a cached entry.
        # If no cached entry with the timestamp exists, set it to now.

        creation_date = None
        creation_date_entry: TFHMovie = cls._cached_movies.get(cls.INDEX_CREATION_DATE)
        if creation_date_entry is not None:
            creation_date = creation_date_entry.get_property(cls.INDEX_CREATION_DATE)
            cls._cache_complete = creation_date_entry.get_property(cls.CACHE_COMPLETE,
                                                                   False)
        if creation_date is None:
            cls._set_creation_date()
            cls._cache_complete = False
            return
        else:
            # Remove dummy entry from cache
            del cls._cached_movies[cls.INDEX_CREATION_DATE]

        # Just to be consistent, all cached_trailer entries are TFHMovie (i.e. Dict)
        # So, get the actual timestamp from it

        cls._time_of_index_creation = Utils.strptime(creation_date, '%Y:%m:%d')
        return

    @classmethod
    def _set_creation_date(cls) -> None:
        cls._time_of_index_creation = datetime.datetime.now()

    @classmethod
    def get_creation_date(cls) -> datetime.datetime:
        return cls._time_of_index_creation

    @classmethod
    def is_complete(cls) -> bool:
        return cls._cache_complete

    @classmethod
    def add_movies(cls, movies: Dict[str, TFHMovie],
                   total: int = None, flush: bool = False) -> None:
        cls._initialized.wait()
        with cls.lock:
            for key, movie in movies.items():
                if not movie.is_sane(MovieField.TFH_SKELETAL_MOVIE):
                    cls._logger.debug(f'TFH movie not sane: {movie.get_title}')
                cls._cached_movies[key] = movie
                cls._unsaved_movie_changes += 1

            cls.save_cache(flush=flush)

    @classmethod
    def add_movie(cls, movie: TFHMovie, total: int = None, flush=False) -> None:
        if not movie.is_sane(MovieField.TFH_SKELETAL_MOVIE):
            cls._logger.debug(f'TFH movie not sane: {movie.get_title}')
        cls._initialized.wait()
        with cls.lock:
            key = movie.get_id()
            cls._cached_movies[key] = movie
            cls._unsaved_movie_changes += 1
            cls.save_cache(flush=flush)

    @classmethod
    def remove_movies(cls, movie_ids: List[str], flush: bool = False) -> None:
        cls._initialized.wait()
        with cls.lock:
            for movie_id in movie_ids:
                if movie_id in cls._cached_movies:
                    del cls._cached_movies[movie_id]
                    cls._unsaved_movie_changes += 1

            cls.save_cache(flush=flush)

    @classmethod
    def update_movie(cls, movie: TFHMovie,
                       flush=False) -> None:
        """
            Nearly identical (for now) to add_movie.

            Typically, due to shallow_copy of get_cached_trailers, the
            movie is already in the _cached_trailers map. It is important
            to bump the unsaved_trailer_changes count.

        :param movie:
        :param flush:
        :return:
        """
        cls._initialized.wait()
        with cls.lock:
            key = movie.get_id()
            cls._cached_movies[key] = movie
            cls._unsaved_movie_changes += 1
            cls.save_cache(flush=flush)

    @classmethod
    def get_cached_movie(cls, movie_id: str) -> TFHMovie:
        cls._initialized.wait()
        with cls.lock:
            return cls._cached_movies.get(movie_id)

    @classmethod
    def get_cached_movies(cls) -> Dict[str, TFHMovie]:
        cls._initialized.wait()
        with cls.lock:
            return cls._cached_movies.copy()

    @staticmethod
    def abort_checker(dct: Dict[str, Any]) -> Dict[str, Any]:
        """

        :param dct:
        :return:
        """
        Monitor.throw_exception_if_abort_requested()
        return dct

    @staticmethod
    def encoder(dct: TFHMovie) -> MovieType:
        Monitor.throw_exception_if_abort_requested()
        if isinstance(dct, TFHMovie):
            return dct.get_as_movie_type()
        return dct

    @staticmethod
    def decoder(dct: MovieType) -> MovieType:
        try:
            Monitor.throw_exception_if_abort_requested()
            # if len(dct.values()) > 0:
            #     for value in dct.values():
            #         if isinstance(value, TFHMovie):
            #             return dct
            #         break

            if MovieField.TFH_ID in dct:
                movie = TFHMovie(movie_info=dct)
                return movie
        except Exception as e:
            TFHCache._logger.exception()
        return dct


TFHCache.class_init()
