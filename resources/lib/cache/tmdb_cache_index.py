# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
from cache.tmdb_trailer_index import TMDbTrailerIndex
from common.imports import *

import datetime
import dateutil.parser
import io
import simplejson as json
from simplejson import (JSONDecodeError)
import os
import sys
import threading

import xbmcvfs

from common.imports import *
from common.constants import Constants
from common.exceptions import AbortException
from common.logger import LazyLogger
from common.messages import Messages
from common.monitor import Monitor
from common.movie import AbstractMovie, TMDbMovieId, BaseMovie
from common.settings import Settings
from common.disk_utils import DiskUtils

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class CachedPage:
    """

    """
    _logger = None

    def __init__(self,
                 year: Union[int, None],
                 page_number: int,
                 # processed means that the trailers for this page have been
                 # placed in unprocessed list.
                 processed: bool = False,
                 total_pages_for_year: int = None
                 ) -> None:
        """

        """
        if type(self)._logger is None:
            type(self)._logger = module_logger.getChild(type(self).__name__)

        self._page_number = page_number
        self._year = year
        self.processed = processed
        self._total_pages_for_year = total_pages_for_year
        self._timestamp = datetime.datetime.now()  # Time read, None if not read

    def get_page_number(self) -> int:
        """

        :return:
        """
        return self._page_number

    def get_year(self) -> int:
        """

        :return:
        """
        return self._year

    def get_total_pages_for_year(self) -> int:
        """

        :return:
        """
        return self._total_pages_for_year

    def is_processed(self) -> bool:
        return self.processed

    def get_cache_key(self) -> str:
        """

        :return:
        """
        if self._year is None:
            year_str = ""
        else:
            year_str = str(self._year)
        return year_str + '_' + str(self._page_number)


class CacheParametersType:
    """

    """

    # Used only for comparing cached value to current value
    #
    def __init__(self,
                 dict_value: Dict[str, Any]
                 ) -> None:
        """
            Settings with no impact:
            trailer_type
            get_tmdb_include_old_movie_movies

        """
        self._included_genres = dict_value['included_genres']
        self._excluded_genres = dict_value['excluded_genres']
        self._included_tags = dict_value['included_tags']
        self._excluded_tags = dict_value['excluded_tags']
        self._minimum_year = dict_value['minimum_year']
        self._maximum_year = dict_value['maximum_year']
        self._remote_trailer_preference = dict_value['remote_trailer_preference']
        self._vote_comparison = dict_value['vote_comparison']
        self._vote_value = dict_value['vote_value']
        self._rating_limit_string = dict_value['rating_limit_string']
        self._language = dict_value['language']
        self._country = dict_value['country']
        dict_value.setdefault('cache_state',
                              CacheIndex.UNINITIALIZED_STATE)
        self._cache_state = dict_value['cache_state']


class CacheParameters(CacheParametersType):
    """

    """

    _logger = None
    _cached_value: CacheParametersType = None

    # Used only for comparing cached value to current value
    #
    def __init__(self,
                 dict_value: Dict[str, Any]
                 ) -> None:
        """
            Settings with no impact:
            trailer_type
            get_tmdb_include_old_movie_movies

        """
        if type(self)._logger is None:
            type(self)._logger = module_logger.getChild(type(self).__name__)

        super().__init__(dict_value)

    @classmethod
    def to_json(cls) -> str:
        """

        :return:
        """
        cached_value: CacheParametersType = cls._cached_value
        values_in_dict = {'included_genres': cached_value._included_genres,
                          'excluded_genres': cached_value._excluded_genres,
                          'included_tags': cached_value._included_tags,
                          'excluded_tags': cached_value._excluded_tags,
                          'minimum_year': cached_value._minimum_year,
                          'maximum_year': cached_value._maximum_year,
                          'remote_trailer_preference': cached_value._remote_trailer_preference,
                          'vote_comparison': cached_value._vote_comparison,
                          'vote_value': cached_value._vote_value,
                          'rating_limit_string': cached_value._rating_limit_string,
                          'language': cached_value._language,
                          'country': cached_value._country,
                          'cache_state': cached_value._cache_state
                          }

        json_text = json.dumps(values_in_dict,
                               encoding='utf-8',
                               ensure_ascii=False,
                               default=CacheIndex.handler,
                               indent=3, sort_keys=True)
        return json_text

    @classmethod
    def get_parameter_values(cls) -> CacheParametersType:
        """

        :return:
        """
        return cls._cached_value

    def __ne__(self,
               other_value: ForwardRef('CacheParameters')
               ) -> bool:
        return not self.__eq__(other_value)

    def __eq__(self,
               other_value  # type: CacheParameters
               ) -> bool:
        finished = False
        is_equal = True
        while not finished:

            if other_value is None:
                is_equal = False
                break

            # Don't understand why this is failing
            if not isinstance(other_value, CacheParameters):
                # is_equal = False
                # break
                pass

            included_genres_set = CacheParameters.create_set(
                self._included_genres)
            other_included_genres_set = CacheParameters.create_set(
                other_value._included_genres)
            if len(included_genres_set ^ other_included_genres_set) != 0:
                is_equal = False
                break

            excluded_genres_set = CacheParameters.create_set(
                self._excluded_genres)
            other_excluded_genres_set = CacheParameters.create_set(
                other_value._excluded_genres)
            if len(excluded_genres_set ^ other_excluded_genres_set) != 0:
                is_equal = False
                break

            included_tags_set = CacheParameters.create_set(self._included_tags)
            other_included_tags_set = CacheParameters.create_set(
                other_value._included_tags)
            if len(included_tags_set ^ other_included_tags_set) != 0:
                is_equal = False
                break

            excluded_tags_set = CacheParameters.create_set(self._excluded_tags)
            other_excluded_tags_set = CacheParameters.create_set(
                other_value._excluded_tags)
            if len(excluded_tags_set ^ other_excluded_tags_set) != 0:
                is_equal = False
                break

            if self._minimum_year != other_value._minimum_year:
                is_equal = False
                break

            if self._maximum_year != other_value._maximum_year:
                is_equal = False
                break

            if self._remote_trailer_preference != other_value._remote_trailer_preference:
                is_equal = False

            if self._vote_comparison != other_value._vote_comparison:
                is_equal = False
                break

            if self._vote_value != other_value._vote_value:
                is_equal = False
                break

            if self._rating_limit_string != other_value._rating_limit_string:
                is_equal = False
                break

            if self._language != other_value._language:
                is_equal = False
                break

            if self._country != other_value._country:
                is_equal = False
                break

            finished = True

        return is_equal

    def is_rebuild_cache(self,
                         other_value  # type: CacheParameters
                         ) -> bool:
        """
        Determines whether settings have changed enough to cause json cache to be
        rebuilt.

        It is expensive to rebuild the cache, but having many old .json entries
        creates multiple problems:
            * At startup, in an attempt to save time, the cache is walked and
              all of the tmdb_ids from the json files are added to the AbstractTrailerFetcher
              to be examined for matches.
            * The previous step can be expensive. Further, if most fail the configured
              filter, much time can be wasted resulting in a blank screen
            * Even if many or all .json files pass the filter, the results can
              be skewed to an old more limited range of years, genres, etc.
        """
        finished = False
        rebuild_needed = False
        while not finished:

            if other_value is None:
                is_equal = False
                break

            # Don't understand why this is failing
            if not isinstance(other_value, CacheParameters):
                # is_equal = False
                # break
                pass

            '''
             TMDB related settings 
        * indicates saved in search_parameters
        - indicates change does not warrant destroying tmdb cache
        + indicates change does warrant destroying tmdb cache
        
        - TMDB_MAX_NUMBER_OF_TRAILERS,
        - TMDB_MAX_DOWNLOAD_MOVIES
        *- TMDB_ALLOW_FOREIGN_LANGUAGES,
        - TMDB_TRAILER_TYPE,
        -    INCLUDE_TMDB_TRAILERS,
        -    INCLUDE_CLIPS,
        -    INCLUDE_FEATURETTES,
        -    INCLUDE_TEASERS,
        * TMDB_SORT_ORDER,
        * TMDB_VOTE_VALUE,
        * TMDB_VOTE_FILTER,
        *+ TMDB_ENABLE_SELECT_BY_YEAR_RANGE (increase of range not too destructive),
            * TMDB_YEAR_RANGE_MINIMUM or None
            * TMDB_YEAR_RANGE_MAXIMUM or None
        *+ TMDB_INCLUDE_OLD_MOVIE_TRAILERS,
        FILTER_GENRES
        * GENREXXX
        * keywords
        * certifications: not-yet-rated, Unknown certification, max_certification
        '''
            included_genres_set = CacheParameters.create_set(
                self._included_genres)
            other_included_genres_set = CacheParameters.create_set(
                other_value._included_genres)
            if len(included_genres_set ^ other_included_genres_set) != 0:
                rebuild_needed = True
                break

            excluded_genres_set = CacheParameters.create_set(
                self._excluded_genres)
            other_excluded_genres_set = CacheParameters.create_set(
                other_value._excluded_genres)
            if len(excluded_genres_set ^ other_excluded_genres_set) != 0:
                rebuild_needed = True
                break

            included_tags_set = CacheParameters.create_set(self._included_tags)
            other_included_tags_set = CacheParameters.create_set(
                other_value._included_tags)
            if len(included_tags_set ^ other_included_tags_set) != 0:
                rebuild_needed = True
                break

            excluded_tags_set = CacheParameters.create_set(self._excluded_tags)
            other_excluded_tags_set = CacheParameters.create_set(
                other_value._excluded_tags)
            if len(excluded_tags_set ^ other_excluded_tags_set) != 0:
                rebuild_needed = True
                break

            if self._minimum_year != other_value._minimum_year:
                rebuild_needed = True
                break

            if self._maximum_year != other_value._maximum_year:
                rebuild_needed = True
                break

            if self._remote_trailer_preference != other_value._remote_trailer_preference:
                rebuild_needed = True

            if self._vote_comparison != other_value._vote_comparison:
                rebuild_needed = True
                break

            if self._vote_value != other_value._vote_value:
                rebuild_needed = True
                break

            if self._rating_limit_string != other_value._rating_limit_string:
                rebuild_needed = True
                break

            '''
            if self._language != other_value._language:
                rebuild_needed = True
                break
            '''

            if self._country != other_value._country:
                rebuild_needed = True
                break

            finished = True

        return rebuild_needed

    @classmethod
    def save_cache(cls) -> None:
        """

        :return:
        """

        path = os.path.join(Settings.get_remote_db_cache_path(),
                            'index', 'tmdb_discovery_parameters.json')
        path = xbmcvfs.validatePath(path)
        parent_dir, file_name = os.path.split(path)
        if not os.path.exists(parent_dir):
            DiskUtils.create_path_if_needed(parent_dir)

        with CacheIndex.lock:
            try:
                Monitor.throw_exception_if_abort_requested()

                with io.open(path, mode='wt', newline=None,
                             encoding='utf-8', ) as cacheFile:
                    json_text = cls.to_json()
                    cacheFile.write(json_text)
                    cacheFile.flush()
            except AbortException:
                reraise(*sys.exc_info())
            except (IOError) as e:
                cls._logger.exception('')
            except Exception as e:
                cls._logger.exception('')

    @classmethod
    def load_cache(cls,
                   current_parameters: ForwardRef('CacheParameters')
                   ) -> Tuple[bool, bool]:
        """

        :param current_parameters:
        :return bool: True when cache has changed
        """
        saved_parameters = cls.read_cached_value_from_disk()
        cache_changed: bool = False
        rebuild_cache: bool = False
        if saved_parameters != current_parameters:
            current_parameters._cache_state =\
                CacheIndex.CACHE_PARAMETERS_INITIALIZED_STATE
            cls.set_cached_value(current_parameters)
            cache_changed = True
            rebuild_cache = current_parameters.is_rebuild_cache(saved_parameters)
        else:
            cls.set_cached_value(saved_parameters)

        return cache_changed, rebuild_cache

    @classmethod
    def set_cached_value(cls,
                         new_parameters: ForwardRef('CacheParameters')
                         ) -> None:
        """

        :param new_parameters:
        :return:
        """
        cls._cached_value = new_parameters
        cls.save_cache()

    @classmethod
    def set_state(cls, value: str) -> None:
        """
        :param value:
        :return:
        """

        cls._cached_value._cache_state = value
        cls.save_cache()

    @classmethod
    def get_state(cls) -> str:
        """

        :return:
        """
        return cls._cached_value._cache_state

    @classmethod
    def read_cached_value_from_disk(cls) -> ForwardRef('CacheParameters'):
        """

        :return:
        """

        path = os.path.join(Settings.get_remote_db_cache_path(),
                            'index', 'tmdb_discovery_parameters.json')
        path = xbmcvfs.validatePath(path)
        parent_dir, file_name = os.path.split(path)
        if not os.path.exists(parent_dir):
            DiskUtils.create_path_if_needed(parent_dir)

        saved_preferences = None
        with CacheIndex.lock:
            try:
                if not os.access(path, os.R_OK):
                    cls._logger.error(Messages.get_formatted_msg(
                        Messages.CAN_NOT_READ_FILE, path))
                    return None

                file_mod_time = datetime.datetime.fromtimestamp(
                    os.path.getmtime(path))
                now = datetime.datetime.now()
                expiration_time = now - datetime.timedelta(
                    Settings.get_expire_remote_db_cache_entry_days())

                if file_mod_time < expiration_time:
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                        cls._logger.debug('cache file EXPIRED for:', path)
                    return None

                Monitor.throw_exception_if_abort_requested()

                with io.open(path, mode='rt', newline=None,
                             encoding='utf-8') as cacheFile:
                    saved_preferences = json.load(cacheFile, encoding='utf-8')
                    saved_preferences = CacheParameters(saved_preferences)
            except AbortException:
                reraise(*sys.exc_info())
            except IOError as e:
                cls._logger.exception('')
                exception_occurred = True
            except Exception as e:
                cls._logger.exception('')
                exception_occurred = True

        return saved_preferences

    @staticmethod
    def create_set(a_list: List[Any]) -> Set[Any]:
        """

        :param a_list:
        :return:
        """
        new_set = set()
        for item in a_list:
            new_set.add(item)

        return new_set


class CachedPagesData:
    """

    There are three types of pages data, each stored in a Dict:

    pages_data: {'genre': CachedPagesData(key='genre'),
     'keyword': CachedPagesData(key='keyword'),
     'generic': CachedPagesData(key='generic')}

     Initialized after definition of class

     """

    pages_data: Dict[str, ForwardRef('CachedPagesData')] = None

    def __init__(self,
                 key: str = '',
                 total_pages: int = 0,
                 query_by_year: bool = False
                 ) -> None:
        """

        :param key:
        :param total_pages:
        """
        self._logger: LazyLogger = module_logger.getChild(type(self).__name__)
        self._number_of_unsaved_changes: int = 0
        self._time_of_last_save = None
        self._key: str = key
        self._total_pages: int = total_pages
        self._total_pages_by_year = {}
        self._query_by_year: bool = query_by_year
        self._years_to_query = None
        self._search_pages_configured: bool = False

        self._logger.debug('remote_db_cache_path:',
                           Settings.get_remote_db_cache_path())
        self._path: str = os.path.join(Settings.get_remote_db_cache_path(),
                                  'index', f'tmdb_{key}.json')
        self._temp_path: str = os.path.join(Settings.get_remote_db_cache_path(),
                                       'index', f'tmdb_{key}.json.tmp')
        self._cached_page_by_key: Dict[str, CachedPage] = None

    def get_total_pages(self) -> int:
        """

        :return:
        """
        self.load_search_pages()
        return self._total_pages

    def set_total_pages(self, total_pages: int) -> None:
        """
        :param total_pages:
        :return:
        """
        self.load_search_pages()
        self._total_pages = total_pages

    def is_query_by_year(self) -> bool:
        """

        :return:
        """
        self.load_search_pages()
        return self._query_by_year

    def set_query_by_year(self, query_by_year: bool) -> None:
        """
        :param query_by_year:
        :return:
        """
        self.load_search_pages()
        self._query_by_year = query_by_year

    def get_years_to_query(self) -> Optional[List[int]]:
        """

        :return:
        """
        self.load_search_pages()
        return self._years_to_query

    def set_years_to_query(self, years_to_query: List[int]) -> None:
        """

        :param years_to_query:
        :return:
        """
        self.load_search_pages()
        self._years_to_query = years_to_query

    def set_search_pages_configured(self,
                                    flush: bool = False
                                    ) -> None:
        """

        :return:
        """
        self.load_search_pages()
        self._search_pages_configured = True
        if flush:
            self.save_search_pages(flush=flush)

    def is_search_pages_configured(self) -> bool:
        """
            Determines whether or not the plan for which TMDB database
            years and pages within those years has been created and cached.

        :return: True indicates that the complete query plan has been persisted
                 and is interruptable.
                 False indicates that the plan may be partially built and
                 persisted. The construction of the plan can be resumed even
                 after a restart.
        """
        self.load_search_pages()
        return self._search_pages_configured

    def add_search_pages(self,
                         search_pages: List[CachedPage],
                         flush: bool = False
                         ) -> None:
        """

        :param search_pages:
        :param flush:
        :return:
        """
        if self._cached_page_by_key is None:
            self.load_search_pages()
        for search_page in search_pages:
            key = search_page.get_cache_key()
            self._cached_page_by_key[key] = search_page
            if search_page._year not in self._total_pages_by_year:
                self._total_pages_by_year[search_page._year] =\
                    search_page._total_pages_for_year

        self._number_of_unsaved_changes += len(search_pages)
        self.save_search_pages(flush=flush)

    def get_total_pages_for_year(self,
                                 year: int
                                 ) -> Optional[int]:
        """
        :param year:
        :return:
        """
        self.load_search_pages()

        total_pages = None
        if year in self._total_pages_by_year:
            total_pages = self._total_pages_by_year[year]

        return total_pages

    def get_number_of_search_pages(self) -> int:
        """

        :return:
        """
        try:
            if self._cached_page_by_key is None:
                self.load_search_pages()

            return int(len(self._cached_page_by_key))

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            self._logger.exception('')

    def get_undiscovered_search_pages(self) -> List[CachedPage]:
        """

        :return:
        """
        undiscovered_search_pages = []

        try:
            if self._cached_page_by_key is None:
                self.load_search_pages()

            for search_page in self._cached_page_by_key.values():
                if not search_page.processed:
                    undiscovered_search_pages.append(search_page)
            Monitor.throw_exception_if_abort_requested()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            self._logger.exception('')

        return undiscovered_search_pages

    def get_number_of_undiscovered_search_pages(self) -> int:
        """

        :return:
        """
        number_of_undiscovered_pages = 0
        try:
            if self._cached_page_by_key is None:
                self.load_search_pages()

            for search_page in self._cached_page_by_key.values():
                if not search_page.processed:
                    number_of_undiscovered_pages += 1
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            self._logger.exception('')

        return int(number_of_undiscovered_pages)

    def get_number_of_discovered_search_pages(self) -> int:
        """

        :return:
        """
        number_of_discovered_pages = 0
        try:
            if self._cached_page_by_key is None:
                self.load_search_pages()

            for search_page in self._cached_page_by_key.values():
                if search_page.processed:
                    number_of_discovered_pages += 1
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            self._logger.exception('')

        return int(number_of_discovered_pages)

    def get_entry_by_year_and_page(self, year: int,
                                   page_number: int) -> CachedPage:
        """

        :param year:
        :param page_number:
        :return:
        """
        cached_page = None
        try:
            if self._cached_page_by_key is None:
                self.load_search_pages()

            key = str(year) + '_' + str(page_number)

            cached_page = self._cached_page_by_key.get(key)
        except Exception as e:
            self._logger.exception('')

        return cached_page

    def get_entries_for_year(self, year: int) -> List[CachedPage]:
        """

        :param year:
        :return:
        """
        cached_pages = []
        try:
            if self._cached_page_by_key is None:
                self.load_search_pages()

            key_prefix = str(year) + '_'

            for key, cached_page in self._cached_page_by_key.items():
                if key.startswith(key_prefix):
                    cached_pages.append(cached_page)
        except Exception as e:
            self._logger.exception('')

        return cached_pages

    def mark_page_as_discovered(self, cached_page: CachedPage) -> None:
        """

        :param cached_page:
        :return:
        """
        self.load_search_pages()
        cached_page.processed = True
        self._number_of_unsaved_changes += 1
        self.save_search_pages(flush=True)

    def get_number_of_unsaved_changes(self) -> int:
        """

        :return:
        """
        self.load_search_pages()
        return int(self._number_of_unsaved_changes)

    def get_time_since_last_save(self) -> datetime.timedelta:
        """

        :return:
        """
        self.load_search_pages()
        return datetime.datetime.now() - self._time_of_last_save

    def to_json(self) -> Dict[str, Any]:
        """

        :return:
        """
        json_dict: Dict[str, Any] = dict()
        try:
            if self._cached_page_by_key is not None:
                json_dict['timestamp'] = datetime.datetime.now()
                json_dict['cache_type'] = self._key
                json_dict['total_pages'] = self._total_pages
                json_dict['query_by_year'] = self._query_by_year
                json_dict['years_to_get'] = self._years_to_query
                json_dict['search_pages_configured'] = self._search_pages_configured

                for key, cached_page in self._cached_page_by_key.items():
                    entry_dict = {'year': cached_page.get_year(),
                                  'page': cached_page.get_page_number(),
                                  'processed': cached_page.processed,
                                  'total_pages_for_year':
                                      cached_page._total_pages_for_year}
                    json_dict[key] = entry_dict

        except Exception as e:
            self._logger.exception('')
        return json_dict

    def from_json(self, encoded_values: Dict[str, Any]) -> ForwardRef('CachedPagesData'):
        """

        :param encoded_values:
        :return:
        """
        cached_page_by_key = dict()
        cached_pages_data = CachedPagesData.pages_data[self._key]
        self._total_pages_by_year.clear()

        try:
            timestamp = datetime.datetime.now()
            for key, entry in encoded_values.items():
                if key == 'timestamp':
                    timestamp = entry
                elif key == 'cache_type':
                    assert entry == self._key
                elif key == 'total_pages':
                    self._total_pages = entry
                elif key == 'query_by_year':
                    self._query_by_year = entry
                elif key == 'years_to_get':
                    self._years_to_query = entry
                elif key == 'search_pages_configured':
                    self._search_pages_configured = entry
                else:
                    # can be none
                    total_pages_for_year = entry.get('total_pages_for_year')
                    cached_page = CachedPage(entry['year'],
                                             entry['page'],
                                             processed=entry['processed'],
                                             total_pages_for_year=total_pages_for_year)
                    cached_page_by_key[key] = cached_page
                    if cached_page._year not in self._total_pages_by_year:
                        self._total_pages_by_year[cached_page._year] =\
                            cached_page._total_pages_for_year

            cached_pages_data._cached_page_by_key = cached_page_by_key
            cached_pages_data._time_of_last_save = datetime.datetime.now()

        except Exception as e:
            self._logger.exception('')

        return cached_pages_data

    def save_search_pages(self, flush: bool = False) -> None:
        """

        :return:
        """
        with CacheIndex.lock:
            if (not flush and
                    self.get_number_of_unsaved_changes() <
                    Constants.TRAILER_CACHE_FLUSH_UPDATES
                    and
                    self.get_time_since_last_save() < datetime.timedelta(minutes=5)):
                return
            saved_pages = len(self._cached_page_by_key.items())
            path = xbmcvfs.validatePath(self._path)
            temp_path = xbmcvfs.validatePath(self._temp_path)
            try:
                parent_dir, file_name = os.path.split(path)
                DiskUtils.create_path_if_needed(parent_dir)

                Monitor.throw_exception_if_abort_requested()
                with io.open(temp_path, mode='wt', newline=None,
                             encoding='utf-8') as cacheFile:
                    json_dict = self.to_json()

                    # TODO: Need ability to interrupt when ABORT. Object_handler
                    # not a valid arg to dumps

                    json_text = json.dumps(json_dict,
                                           encoding='utf-8',
                                           ensure_ascii=False,
                                           default=CacheIndex.handler,
                                           indent=3, sort_keys=True)
                    cacheFile.write(json_text)
                    cacheFile.flush()
                    self._number_of_unsaved_changes = 0
                    self._time_of_last_save = datetime.datetime.now()

                try:
                    os.replace(temp_path, path)
                except OSError:
                    self._logger.exception(f'Failed to replace move information'
                                           f' planned for download: {path}')
                Monitor.throw_exception_if_abort_requested()
            except AbortException:
                reraise(*sys.exc_info())
            except IOError as e:
                self._logger.exception('')
            except JSONDecodeError as e:
                os.remove(path)
            except Exception as e:
                self._logger.exception('')

        self._logger.debug_verbose("Entries Saved: ", saved_pages)

    def load_search_pages(self) -> None:
        """

        :return:
        """

        if self._cached_page_by_key is not None:
            return

        path: str = xbmcvfs.validatePath(self._path)
        try:
            parent_dir, file_name = os.path.split(path)
            DiskUtils.create_path_if_needed(parent_dir)

            if os.path.exists(path):
                Monitor.throw_exception_if_abort_requested()
                with CacheIndex.lock, io.open(path, mode='rt', newline=None,
                                              encoding='utf-8') as cacheFile:
                    encoded_values = json.load(
                        cacheFile, encoding='utf-8',
                        object_hook=CacheIndex.datetime_parser)
                    loaded_cached_pages_data = self.from_json(encoded_values)
                    self._cached_page_by_key = \
                        loaded_cached_pages_data._cached_page_by_key
            else:
                self._cached_page_by_key: Dict[str, CachedPage] = dict()

        except AbortException:
            reraise(*sys.exc_info())
        except IOError as e:
            self._logger.exception('')
        except JSONDecodeError as e:
            os.remove(path)
            self._cached_page_by_key = dict()
        except Exception as e:
            self._logger.exception('')

        self._logger.debug_verbose(
            f'Loaded entries key: {self._key} # pages: '
            f'{len(self._cached_page_by_key)}')
        self._time_of_last_save = datetime.datetime.now()

    def clear(self) -> None:
        """

        :return:
        """
        self.load_search_pages()
        self._cached_page_by_key = {}
        self._total_pages = 0
        self._number_of_unsaved_changes = 1
        self._total_pages_by_year = {}
        self._years_to_query = None
        self._search_pages_configured = False
        self.save_search_pages(flush=True)


# Can't initialize within class

CachedPagesData.pages_data: Dict[str, CachedPagesData] = \
    {'genre': CachedPagesData(key='genre'),
     'keyword': CachedPagesData(key='keyword'),
     'generic': CachedPagesData(key='generic')}


class CacheIndex:
    """

    """
    UNINITIALIZED_STATE = 'uninitialized_state'
    CACHE_PARAMETERS_INITIALIZED_STATE = 'cache_parameters_initialized_state'
    _found_tmdb_trailer_ids: Set[int] = set()

    # TMDb ids of movies partially discovered by TMDbDiscovery. Additional
    # discovery using the full details returned by TMDb movie query.
    # Note that if discovery parameters change, then this should be destroyed and
    # discovery restarted

    _unprocessed_tmdb_trailer_ids: Set[int] = set()
    lock = threading.RLock()
    last_saved = datetime.datetime.now()
    _last_saved_trailer_timestamp = datetime.datetime.now()
    _last_saved_unprocessed_movie_timestamp = datetime.datetime.now()

    _parameters = None
    # _unprocessed_movies: Dict[int, TMDbMoviePageData] = {}
    # _unprocessed_movie_changes: int = 0
    _unsaved_movie_changes: int = 0
    _unprocesseed_movie_changes: int = 0
    _logger = None

    @classmethod
    def class_init(cls) -> None:
        """
        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(type(cls).__name__)

    @classmethod
    def load_cache(cls,
                   cache_changed: bool,
                   ) -> None:
        """
        :param cache_changed:
        :return:
        """
        cls.logger().debug_verbose(f'cache_changed: {cache_changed}')
        with CacheIndex.lock:
            if cache_changed:
                # Replace Cache
                cls._parameters = CacheParameters.get_parameter_values()
                cls._found_tmdb_trailer_ids = set()
                cls._unprocessed_tmdb_trailer_ids = set()
                cls._unprocesseed_movie_changes = 1
                cls._unsaved_movie_changes = 1
                cls._last_saved_unprocessed_movie_timestamp = datetime.datetime.now()
                cls._last_saved_trailer_timestamp = datetime.datetime.now()
                cls.save_parameter_cache()
                cls.save_tmdb_ids_with_trailers(flush=True)
                cls.save_unprocessed_movies_cache(flush=True)

                # Clear each type of CachedPagesData: 'genre', 'keyword' and 'generic'

                cached_page_data: CachedPagesData
                cached_page_key: str
                for cached_page_key in CachedPagesData.pages_data.keys():
                    cached_page_data: CachedPagesData
                    cached_page_data = CachedPagesData.pages_data[cached_page_key]
                    cached_page_data.clear()
                    cached_page_data.save_search_pages(flush=True)

            cls.load_tmdb_ids_with_trailers()
            cls.load_unprocessed_movies_cache()

    @classmethod
    def add_search_pages(cls,
                         tmdb_search_query: str,
                         search_pages: List[CachedPage],
                         flush: bool = False
                         ) -> None:
        """

        :return:
        """
        pages = list(search_pages)
        cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
        cached_pages_data.add_search_pages(pages, flush)

    @classmethod
    def get_search_pages(cls,
                         tmdb_search_query: str
                         ) -> List[CachedPage]:
        """
        :param tmdb_search_query:
        :return:
        """

        cls._logger.debug(f'tmdb_search_query: {tmdb_search_query}')
        cached_pages_data: CachedPagesData
        cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
        return list(cached_pages_data.get_undiscovered_search_pages())

    @classmethod
    def get_number_of_discovered_search_pages(cls) -> int:
        """

        :return:
        """
        number_of_discovered_pages = 0
        for page_type in ('genre', 'keyword', 'generic'):
            cached_pages_data: CachedPagesData
            cached_pages_data = CachedPagesData.pages_data[page_type]
            number_of_discovered_pages +=\
                cached_pages_data.get_number_of_discovered_search_pages()

        return int(number_of_discovered_pages)

    @classmethod
    def logger(cls) -> LazyLogger:
        """

        :return:
        """
        return cls._logger

    @classmethod
    def save_parameter_cache(cls) -> None:
        """

        :return:
        """
        CacheParameters.save_cache()

    @classmethod
    def save_cached_pages_data(cls, tmdb_search_query: str,
                               flush: bool = False) -> None:
        cached_pages_data = CachedPagesData.pages_data[tmdb_search_query]
        cached_pages_data.save_search_pages(flush=flush)

    @classmethod
    def add_tmdb_id_with_trailer(cls, tmdb_id: int) -> None:
        """

        :param tmdb_id:
        :return:
         """
        tmdb_id = int(tmdb_id)
        with CacheIndex.lock:
            if tmdb_id not in cls._found_tmdb_trailer_ids:
                cls._found_tmdb_trailer_ids.add(tmdb_id)
                cls._unsaved_movie_changes += 1
                cls.save_tmdb_ids_with_trailers()  # If needed

            cls.remove_unprocessed_movie(tmdb_id)

    @classmethod
    def remove_tmdb_id_with_trailer(cls, tmdb_id: int) -> None:
        """
        Remove the TMDbMovieId with the given tmdb_id from the
        cached and persisted entries.

        As trailers from TMDb are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :param tmdb_id:
        :return:
         """
        tmdb_id = int(tmdb_id)
        with CacheIndex.lock:
            try:
                cls._found_tmdb_trailer_ids.remove(tmdb_id)
                cls._unsaved_movie_changes += 1
            except KeyError:
                pass

            cls.remove_unprocessed_movie(tmdb_id)  # if needed
            cls.save_tmdb_ids_with_trailers()  # If needed

    @classmethod
    def get_tmdb_ids_with_trailers(cls) -> Set[TMDbMovieId]:
        """
        Return all TMDbMovieIds that are known to have trailers.

        As trailers from TMDb are discovered, their ids are
        persisted. Only by discovering full details will it be
        known whether to include the trailers or not.

        :return:
        """
        tmdb_movie_ids: Set[TMDbMovieId] = set()
        with cls.lock:
            tmdb_id: int
            for tmdb_id in cls._found_tmdb_trailer_ids:
                tmdb_movie_id: TMDbMovieId = TMDbMovieId(str(tmdb_id))
                tmdb_movie_ids.add(tmdb_movie_id)

        return tmdb_movie_ids

    @classmethod
    def load_tmdb_ids_with_trailers(cls) -> None:
        """
        Loads the cache of TMDb Ids which are known to have trailers.

        :return:
        """
        path = os.path.join(Settings.get_remote_db_cache_path(),
                            'index', 'tmdb_found_trailers.json')
        path = xbmcvfs.validatePath(path)
        try:
            parent_dir, file_name = os.path.split(path)
            DiskUtils.create_path_if_needed(parent_dir)
            if os.path.exists(path):
                with CacheIndex.lock, io.open(path, mode='rt', newline=None,
                                              encoding='utf-8') as cacheFile:
                    found_trailers_list = json.load(
                        cacheFile, encoding='utf-8',
                        object_hook=CacheIndex.datetime_parser)
                    cls._last_saved_trailer_timestamp = datetime.datetime.now()
                    cls._found_tmdb_trailer_ids: Set[int] = set(
                        found_trailers_list)
                    cls._unsaved_movie_changes = 0
                    cls._unprocessed_tmdb_trailer_ids.difference_update(
                        cls._found_tmdb_trailer_ids)
            else:
                cls._found_tmdb_trailer_ids: Set[int] = set()

            Monitor.throw_exception_if_abort_requested()

        except AbortException:
            reraise(*sys.exc_info())
        except IOError as e:
            CacheIndex.logger().exception('')
        except JSONDecodeError as e:
            os.remove(path)
        except Exception as e:
            CacheIndex.logger().exception('')

    @classmethod
    def save_tmdb_ids_with_trailers(cls, flush: bool = False) -> None:
        """
        :param flush:
        :return:
        """
        with cls.lock:
            if cls._unsaved_movie_changes == 0:
                return

            if (not flush and
                    (cls._unsaved_movie_changes <
                     Constants.TRAILER_CACHE_FLUSH_UPDATES)
                and
                (datetime.datetime.now() - cls._last_saved_trailer_timestamp) <
                    datetime.timedelta(minutes=5)):
                return

            try:
                path = os.path.join(Settings.get_remote_db_cache_path(),
                                    'index', 'tmdb_found_trailers.json')
                path = xbmcvfs.validatePath(path)
                parent_dir, file_name = os.path.split(path)
                if not os.path.exists(parent_dir):
                    DiskUtils.create_path_if_needed(parent_dir)
                with io.open(path, mode='wt', newline=None,
                             encoding='utf-8', ) as cacheFile:
                    found_trailer_id_list = list(
                        cls._found_tmdb_trailer_ids)
                    json_text = json.dumps(found_trailer_id_list,
                                           ensure_ascii=False,
                                           default=CacheIndex.handler,
                                           indent=3, sort_keys=True)
                    cacheFile.write(json_text)
                    cacheFile.flush()
                    cls._last_saved_trailer_timestamp = datetime.datetime.now()
                    cls._unsaved_movie_changes = 0

                Monitor.throw_exception_if_abort_requested()
            except AbortException:
                reraise(*sys.exc_info())
            except IOError as e:
                CacheIndex.logger().exception('')
            except Exception as e:
                CacheIndex.logger().exception('')

    @classmethod
    def add_unprocessed_tmdb_movies(cls,
                                    arg_tmdb_ids: Union[TMDbMovieId,
                                                          Iterable[TMDbMovieId]])\
            -> None:
        """

        :param arg_tmdb_ids:
        :return:
         """
        tmdb_ids: List[int]
        if not isinstance(arg_tmdb_ids, Iterable):
            tmdb_ids = [arg_tmdb_ids.get_tmdb_id()]
        else:
            tmdb_movie_id: TMDbMovieId
            tmdb_ids = []
            for tmdb_movie_id in arg_tmdb_ids:
                tmdb_ids.append(tmdb_movie_id.get_tmdb_id())

        with CacheIndex.lock:
            orig_size: int = len(cls._unprocessed_tmdb_trailer_ids)
            cls._unprocessed_tmdb_trailer_ids.update(tmdb_ids)
            delta_size: int = len(cls._unprocessed_tmdb_trailer_ids) - orig_size
            cls._unprocesseed_movie_changes += delta_size
            cls.save_unprocessed_movies_cache()  # If needed

    @classmethod
    def get_unprocessed_movies(cls) -> List[TMDbMovieId]:
        unprocessed_ids: List[TMDbMovieId]
        unprocessed_ids = []
        tmdb_id: int
        for tmdb_id in cls._unprocessed_tmdb_trailer_ids:
            tmdb_movie_id: TMDbMovieId
            tmdb_movie_id = TMDbMovieId(str(tmdb_id))
            unprocessed_ids.append(tmdb_movie_id)

        return unprocessed_ids

    @classmethod
    def remove_unprocessed_movie(cls, arg_tmdb_id: Union[TMDbMovieId, int]) -> None:
        """
        :param arg_tmdb_id:
        :return:
         """
        tmdb_id: int

        if arg_tmdb_id is None:
            cls._logger.debug(f'arg_tmdb_id is None')

        tmdb_id: int = None
        if isinstance(arg_tmdb_id, TMDbMovieId):
            tmdb_id = int(arg_tmdb_id.get_tmdb_id())
        elif isinstance(arg_tmdb_id, AbstractMovie):
            abstract_movie: AbstractMovie = arg_tmdb_id
            tmdb_id = abstract_movie.get_tmdb_id()
        elif isinstance(arg_tmdb_id, int) or isinstance(arg_tmdb_id, str):
            tmdb_id = int(arg_tmdb_id)
        else:
            cls._logger.debug(f'Unexpected tmdb_id argument')
            return
        if tmdb_id is None:
            cls._logger.debug('tmdb_id is None')
            return
        with CacheIndex.lock:
            try:
                cls._unprocessed_tmdb_trailer_ids.remove(tmdb_id)
                cls._unprocesseed_movie_changes += 1
            except KeyError:
                pass

            cls.save_unprocessed_movies_cache()  # If needed

    @classmethod
    def get_number_of_unprocessed_movies(cls) -> int:
        return len(cls._unprocessed_tmdb_trailer_ids)

    @classmethod
    def load_unprocessed_movies_cache(cls) -> None:
        """

        :return:
        """
        path = os.path.join(Settings.get_remote_db_cache_path(),
                            'index', 'tmdb_unprocessed_movies.json')
        path = xbmcvfs.validatePath(path)
        try:
            parent_dir, file_name = os.path.split(path)
            DiskUtils.create_path_if_needed(parent_dir)

            if os.path.exists(path):
                with CacheIndex.lock, io.open(path, mode='rt', newline=None,
                                              encoding='utf-8') as cacheFile:
                    unprocessed_trailers_list = json.load(
                        cacheFile, encoding='utf-8',
                        object_hook=CacheIndex.datetime_parser)
                    cls._last_saved_unprocssed_trailer_timestamp = datetime.datetime.now()
                    cls._unprocessed_tmdb_trailer_ids: Set[int] = set(
                        unprocessed_trailers_list)
                    cls._unprocesseed_movie_changes = 0
            else:
                cls._unprocessed_tmdb_trailer_ids: Set[int] = set()

            Monitor.throw_exception_if_abort_requested()
        except AbortException:
            reraise(*sys.exc_info())
        except IOError as e:
            CacheIndex.logger().exception('')
        except JSONDecodeError as e:
            os.remove(path)
        except Exception as e:
            CacheIndex.logger().exception('')

    @classmethod
    def save_unprocessed_movies_cache(cls, flush: bool = False) -> None:
        """
        :param flush:
        :return:
        """
        with cls.lock:
            if cls._unprocesseed_movie_changes == 0:
                return

            if (not flush and
                    (cls._unprocesseed_movie_changes <
                     Constants.TRAILER_CACHE_FLUSH_UPDATES)
                    and
                    (datetime.datetime.now() -
                     cls._last_saved_unprocssed_trailer_timestamp) <
                    datetime.timedelta(minutes=5)):
                return

            try:
                path = os.path.join(Settings.get_remote_db_cache_path(),
                                    'index', 'tmdb_unprocessed_movies.json')
                path = xbmcvfs.validatePath(path)
                parent_dir, file_name = os.path.split(path)
                if not os.path.exists(parent_dir):
                    DiskUtils.create_path_if_needed(parent_dir)
                with io.open(path, mode='wt', newline=None,
                             encoding='utf-8', ) as cacheFile:
                    unprocessed_trailer_ids = list(
                        cls._unprocessed_tmdb_trailer_ids)
                    json_text = json.dumps(unprocessed_trailer_ids,
                                           ensure_ascii=False,
                                           default=CacheIndex.handler,
                                           indent=3, sort_keys=True)
                    cacheFile.write(json_text)
                    cacheFile.flush()
                    cls._last_saved_unprocssed_trailer_timestamp = datetime.datetime.now()
                    cls._unprocesseed_movie_changes = 0

                Monitor.throw_exception_if_abort_requested()
            except AbortException:
                reraise(*sys.exc_info())
            except IOError as e:
                CacheIndex.logger().exception('')
            except Exception as e:
                CacheIndex.logger().exception('')

    @staticmethod
    def abort_checker(dct: Dict[str, Any]) -> Dict[str, Any]:
        """

        :param dct:
        :return:
        """
        Monitor.throw_exception_if_abort_requested()
        return dct

    @staticmethod
    def handler(obj: Any) -> Any:
        """

        :param obj:
        :return:
        """
        Monitor.throw_exception_if_abort_requested()
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()

    @staticmethod
    def datetime_parser(dct: Dict) -> Dict:
        """

        :param dct:
        :return:
        """
        date_string = dct.get('timestamp', None)
        if date_string is not None:
            timestamp = dateutil.parser.parse(date_string)
            dct['timestamp'] = timestamp
            return dct
        else:
            return dct


CacheIndex.class_init()
