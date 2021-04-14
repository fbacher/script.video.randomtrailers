# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import datetime

import io
import simplejson as json
from simplejson import (JSONDecodeError)
import os
import threading

import xbmcvfs
from common.imports import *

from common.constants import (Constants, Movie, RemoteTrailerPreference)
from common.logger import (Logger, LazyLogger)
from common.monitor import Monitor
from common.settings import (Settings)
from common.disk_utils import (DiskUtils)
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
    lock = threading.RLock()
    _logger = None
    _cached_trailers: Dict[str, MovieType] = {}
    _last_saved_trailer_timestamp = datetime.datetime.now()
    _unsaved_trailer_changes: int = 0

    # Cache is marked with timestamp of last update of trailer ids from TFH
    # Also marked whether the cache was completely updated.

    _time_of_index_creation = datetime.datetime(2000, 1, 1)  # expired
    _cache_complete = False
    _number_of_trailers_on_site: int = 0

    @classmethod
    def class_init(cls) -> None:
        """
        :return:
        """
        cls._logger = module_logger.getChild(type(cls).__name__)
        cls.load_cache()

    @classmethod
    def logger(cls) -> LazyLogger:
        """

        :return:
        """
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
              "normalized_trailer": "/home/fbacher/.kodi/userdata/addon_data/script.video.randomtrailers/cache/hB/tfh_BZwDpOQNgpw_normalized_Larry Karaszewski on SMOKEY IS THE BANDIT (SMOKEY AND THE BANDIT PART 3) (2017)-movie.mkv",
              "original_language": "",
              "plot": "But wait! There's more! TFH has a podcast! \n\nIt's THE MOVIES THAT MADE ME, where you can join Oscar-nominated screenwriter Josh Olson and his, ummm, \"co-host\" Joe Dante in conversation with filmmakers, comedians, and all-around interesting people about the movies that made them who they are. Check it out now, and please subscribe wherever podcasts can be found.\n\nBut wait! There's more! TFH has a podcast! \n\nIt's THE MOVIES THAT MADE ME, where you can join Oscar-nominated screenwriter Josh Olson and his, ummm, \"co-host\" Joe Dante in conversation with filmmakers, comedians, and all-around interesting people about the movies that made them who they are. Check it out now, and please subscribe wherever podcasts can be found.\n\niTunes: http://itunes.trailersfromhell.com\nSpotify: http://spotify.trailersfromhell.com\nLibsyn: http://podcast.trailersfromhell.com\nGoogle Play: http://googleplay.trailersfromhell.com\nRSS: http://goo.gl/3faeG7\n\nAs always, you can find more commentary, more reviews, more podcasts, and more deep-dives into the films you don't know you love yet over at the Trailers From Hell mothership: \n\nhttp://www.trailersfromhell.com",
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
              "rts.title": "SMOKEY IS THE BANDIT (SMOKEY AND THE BANDIT PART 3) (2017) - TFH ",
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
              "trailer": "https://youtu.be/BZwDpOQNgpw",
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
        with cls.lock:
            if (not flush and
                    (cls._unsaved_trailer_changes < 50)
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
                        cls.set_creation_date()
                        # Set to True when complete, but don't set to False
                        # when not complete.

                        cls._cache_complete = True

                    creation_date_str = datetime.datetime.strftime(
                        cls._time_of_index_creation, '%Y:%m:%d')

                    cls._cached_trailers[cls.INDEX_CREATION_DATE] = {
                        cls.INDEX_CREATION_DATE: creation_date_str,
                        cls.CACHE_COMPLETE: cls._cache_complete
                    }

                    json_text = json.dumps(cls._cached_trailers,
                                           encoding='utf-8',
                                           ensure_ascii=False,
                                           default=TFHCache.abort_checker,
                                           indent=3, sort_keys=True)
                    cacheFile.write(json_text)
                    cacheFile.flush()

                    # Get rid of dummy entry from local dict
                    del cls._cached_trailers[cls.INDEX_CREATION_DATE]
                    cls._last_saved_trailer_timestamp = datetime.datetime.now()
                    cls._unsaved_trailer_changes = 0

                try:
                    os.replace(tmp_path, path)
                except OSError:
                    cls._logger.exception(f'Failed to replace missing trailer'
                                          f' information cache: {path}')
            except IOError as e:
                TFHCache.logger().exception('')
            except Exception as e:
                TFHCache.logger().exception('')

        Monitor.throw_exception_if_abort_requested()

    @classmethod
    def load_cache(cls) -> None:
        """

        :return: True if cache is full and no further discovery needed
        """
        with cls.lock:
            try:
                path = os.path.join(Settings.get_remote_db_cache_path(),
                                    'index', 'tfh_trailers.json')
                path = xbmcvfs.validatePath(path)

                parent_dir, file_name = os.path.split(path)
                DiskUtils.create_path_if_needed(parent_dir)

                if os.path.exists(path):
                    with io.open(path, mode='rt', newline=None,
                                 encoding='utf-8') as cacheFile:
                        cls._cached_trailers: Dict[str, MovieType] = json.load(
                            cacheFile,
                            # object_hook=TFHCache.abort_checker,
                        )
                        cls.last_saved_movie_timestamp = None
                        cls._unsaved_trailer_changes = 0
                        cls.load_creation_date()
                else:
                    cls._cached_trailers = dict()
                    # Set to an old time so that cache is expired
                    cls._time_of_index_creation = datetime.datetime(2000, 1, 1)

            except IOError as e:
                TFHCache.logger().exception('')
            except JSONDecodeError as e:
                os.remove(path)
            except Exception as e:
                TFHCache.logger().exception('')

        Monitor.throw_exception_if_abort_requested()
        return

    @classmethod
    def load_creation_date(cls) -> None:
        # Loads the last time the index was created from a cached entry.
        # If no cached entry with the timestamp exists, set it to now.

        creation_date = None
        creation_date_entry = cls._cached_trailers.get(cls.INDEX_CREATION_DATE)
        if creation_date_entry is not None:
            creation_date = creation_date_entry.get(cls.INDEX_CREATION_DATE)
            cls._cache_complete = creation_date_entry.get(cls.CACHE_COMPLETE, False)
        if creation_date is None:
            cls.set_creation_date()
            cls._cache_complete = False
            return
        else:
            # Remove dummy entry from cache
            del cls._cached_trailers[cls.INDEX_CREATION_DATE]

        # Just to be consistent, all cached_trailer entries are MovieType (i.e. Dict)
        # So, get the actual timestamp from it

        cls._time_of_index_creation = Utils.strptime(creation_date, '%Y:%m:%d')
        return

    @classmethod
    def set_creation_date(cls) -> None:
        cls._time_of_index_creation = datetime.datetime.now()

    @classmethod
    def get_creation_date(cls) -> datetime.datetime:
        return cls._time_of_index_creation

    @classmethod
    def is_complete(cls) -> bool:
        return cls._cache_complete

    @classmethod
    def add_trailers(cls, trailers: Dict[str, MovieType],
                     total: int = None, flush=False) -> None:

        with cls.lock:
            if total is not None:
                cls._number_of_trailers_on_site = total
            for key, trailer in trailers.items():
                cls._cached_trailers[key] = trailer
                cls._unsaved_trailer_changes += 1

            cls.save_cache(flush=flush)

    @classmethod
    def add_trailer(cls, movie: MovieType, total: int = None, flush=False) -> None:
        with cls.lock:
            key = movie[Movie.TFH_ID]
            if total is not None:
                cls._number_of_trailers_on_site = total
            cls._cached_trailers[key] = movie
            cls._unsaved_trailer_changes += 1
            cls.save_cache(flush=flush)

    @classmethod
    def update_trailer(cls, movie: MovieType, flush=False) -> None:
        """
            Nearly identical (for now) to add_trailer.

            Typically, due to shallow_copy of get_cached_trailers, the
            movie is already in the _cached_trailers map. It is important
            to bump the unsaved_trailer_changes count.

        :param movie:
        :param flush:
        :return:
        """

        with cls.lock:
            key = movie[Movie.TFH_ID]
            cls._cached_trailers[key] = movie
            cls._unsaved_trailer_changes += 1
            cls.save_cache(flush=flush)

    @classmethod
    def get_cached_trailer(cls, trailer_id: str) -> MovieType:

        return cls._cached_trailers.get(trailer_id)

    @classmethod
    def get_cached_trailers(cls) -> Dict[str, MovieType]:
        return cls._cached_trailers.copy()

    @staticmethod
    def abort_checker(dct: Dict[str, Any]) -> Dict[str, Any]:
        """

        :param dct:
        :return:
        """
        Monitor.throw_exception_if_abort_requested()
        return dct


TFHCache.class_init()
