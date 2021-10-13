# -*- coding: utf-8 -*-
"""
Created on 6/12/21

@author: Frank Feuerbacher

Provides methods to create and execute queries to Kodi database

"""
import sys

import simplejson

from backend.json_utils_basic import JsonUtilsBasic
from common.exceptions import AbortException
from common.imports import *
from common.logger import LazyLogger
from common.monitor import Monitor

module_logger: Final[LazyLogger] = LazyLogger.get_addon_module_logger(file_path=__file__)


class DBAccess:
    # The properties below are largely the same as what is found in
    # movie_constants MOVIE_FIELD. However, the ones here are the
    # the Kodi db property names and several in MOVIE_FIELD have
    # been changed to be more clear. Example: "mpaa" is used to
    # store certification, but "mpaa" is the name of the US
    # certification authority. In this case, this addon uses
    # "certification" instead of "mpaa" to hold the same info.

    MINIMAL_PROPERTIES: Final[List[str]] = [
        "title",
        "lastplayed",
        "rating",
        "mpaa",
        "year",
        "trailer",
        "uniqueid"
    ]

    DETAIL_PROPTIES: Final[List[str]] = [
        "title",
        "lastplayed",
        "rating",
        "mpaa",
        "year",
        "trailer",
        "uniqueid",
        "studio",
        "cast",
        "plot",
        "writer",
        "director",
        "fanart",
        "ratings",
        "runtime",
        "thumbnail",
        "file",
        "genre",
        "tag",
        "userrating",
        "votes"
    ]

    _logger: LazyLogger = None

    @classmethod
    def _class_init_(cls):
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def create_query(cls, sparse_properties: bool,
                     included_genres: List[str],
                     excluded_genres: List[str],
                     included_tags: List[str],
                     excluded_tags: List[str]
                     ) -> str:
        """

        :param sparse_properties:
        :param included_genres:
        :param excluded_genres:
        :param included_tags:
        :param excluded_tags:
        :return:
        """
        formatted_genre_list = ', '.join('"' + genre + '"' for genre in included_genres)
        formatted_excluded_genre_list = ', '.join(
            '"' + genre + '"' for genre in excluded_genres)

        formatted_tag_list = ', '.join('"' + tag + '"' for tag in included_tags)
        formatted_excluded_tag_list = ', '.join('"' + tag + '"' for tag in excluded_tags)

        query_prefix = f'{{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", ' \
                       f'"params": {{' \
                       f'"properties": '

        props: List[str]
        if sparse_properties:
            props = cls.MINIMAL_PROPERTIES
        else:
            props = cls.DETAIL_PROPTIES

        query_properties: str = ', '.join(f'"{prop}"' for prop in props)
        query_suffix = '}, "id": 1}'

        query_filter_prefix = ''

        if (len(included_genres) > 0 or len(included_tags) > 0 or len(excluded_genres) > 0
                or len(excluded_tags) > 0):
            query_filter_prefix = ', "filter": '

        exclude_filters = []
        include_filters = []
        if len(included_genres) > 0:
            genre_filter = (f'{{"field": "genre", "operator": "contains", "value": '
                            f'[{formatted_genre_list}]}}')
            include_filters.append(genre_filter)

        if len(included_tags) > 0:
            tag_filter = (f'{{"field": "tag", "operator": "contains", "value": '
                          f'[{formatted_tag_list}]}}')
            include_filters.append(tag_filter)

        combined_include_filter: List[str] = []
        include_sub_query_filter: str = ''
        if len(include_filters) == 1:
            include_filters_str: str = ', '.join(include_filters)
            include_sub_query_filter = f'{include_filters[0]}'
            combined_include_filter.append(include_sub_query_filter)
        elif len(include_filters) > 1:
            include_filters_str: str = ', '.join(include_filters)
            include_sub_query_filter = f'{{"or": [{include_filters_str}]}}'
            combined_include_filter.append(include_sub_query_filter)

        if len(excluded_genres) > 0:
            excluded_genre_filter = (
                f'{{"field": "genre", "operator": "doesnotcontain", '
                f'"value": [{formatted_excluded_genre_list}]}}')
            exclude_filters.append(excluded_genre_filter)

        if len(excluded_tags) > 0:
            excluded_tag_filter = (
                'f{{"field": "tag", "operator": "doesnotcontain", '
                 f'"value": [{formatted_excluded_tag_list}]}}')
            exclude_filters.append(excluded_tag_filter)

        combined_exclude_filter = []
        exclude_sub_query_filter = ''
        if len(exclude_filters) > 1:
            exclude_filters_str = ', '.join(exclude_filters)
            exclude_sub_query_filter = f'{{"or": [{exclude_filters_str}]}}'
            combined_exclude_filter.append(exclude_sub_query_filter)
        elif len(exclude_filters) == 1:
            exclude_sub_query_filter = exclude_filters[0]
            combined_exclude_filter.append(exclude_sub_query_filter)

        combined_filter = []
        if len(combined_include_filter) > 0:
            combined_filter.append(combined_include_filter[0])
        if len(combined_exclude_filter) > 0:
            combined_filter.append(combined_exclude_filter[0])
        query_filter = ''
        if len(combined_filter) > 1:
            query_filter = f'{{"and": [{", ".join(combined_filter)}]}}'
        elif len(combined_filter) == 1:
            query_filter = combined_filter[0]

        query = f'{query_prefix}[{query_properties}]' \
                f'{query_filter_prefix}{query_filter}{query_suffix}'

        if cls._logger.isEnabledFor(LazyLogger.DISABLED):
            cls._logger.debug_verbose('query', 'genres:', included_genres,
                                      'excluded_genres:', excluded_genres, 'tags:',
                                      included_tags, 'excluded_tags:',
                                      excluded_tags, query)

        return query

    @classmethod
    def create_details_query(cls, movie_id: int) -> str:
        """
        :return:
        """

        # Getting ALL of the properties that we use and not just the ones needed for
        # Details. This is done because there are not that many that we can skip and
        # it means that we don't have to merge results.

        prefix = f'{{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovieDetails", ' \
                 f'"params": {{' \
                 f'"movieid": {movie_id}, ' \
                 f'"properties": ' \
                 f'['

        query_properties: str = ', '.join(f'"{prop}"' for prop in cls.DETAIL_PROPTIES)
        query_suffix = f']}}, "id": 1}}'

        query = f'{prefix}{query_properties}{query_suffix}'

        if cls._logger.isEnabledFor(LazyLogger.DISABLED):
            cls._logger.debug_verbose(f'query: {query}')

        return query

    @classmethod
    def get_movie_details(cls, query: str) -> List[MovieType]:
        movies: List[MovieType] = []
        try:
            if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                import simplejson as json
                # json_encoded: Dict = json.loads(query)
                cls._logger.debug_extra_verbose('JASON DUMP:',
                                               json.dumps(
                                                   query, indent=3, sort_keys=True))
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            pass

        # Depending upon the query, either a single movie is returned, or a list.
        # Always return a list

        query_result: Dict[str, Any] = {}
        try:
            query_result: Dict[str, Any] = JsonUtilsBasic.get_kodi_json(query,
                                                                        dump_results=False)
            if query_result.get('error') is not None:
                raise ValueError

            Monitor.throw_exception_if_abort_requested()
            result: Dict[str, Any] = query_result.get('result', {})
            movie: MovieType = result.get('moviedetails', None)
            if movie is None:
                movies = result.get('movies', [])
                if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                    cls._logger.error(f'Got back movies {len(movies)} '
                                     f'instead of moviedetails.')
            else:
                movies.append(movie)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            movies = []
            message: str = ''
            if query_result is not None:
                error = query_result.get('error')
                if error is not None:
                    message: str = error.get('message')
            cls._logger.exception(message)
            try:
                import simplejson as json
                # json_encoded: Dict = json.loads(query)
                cls._logger.debug_extra_verbose('JASON DUMP:',
                                               json.dumps(
                                                   query, indent=3, sort_keys=True))
            except Exception:
                movies = []

        return movies

    @classmethod
    def create_title_date_query(cls, title: str, year: str) -> str:
        """


        :return:
        """
        '''
  {"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": { "properties": [ 
  "title", "lastplayed", "studio", "cast", "plot", "writer", "director", "fanart", 
  "runtime", "mpaa", "thumbnail", "file","year", "genre", "tag", "trailer" ], "filter": 
  { "or": [ { "field": "genre", "operator": "contains", "value": [ "Film-Noir" ] }, 
  { "field": "tag", "operator": "contains", "value": [ "classic noir", "film noir", 
  "french noir", "brit noir" ] } ] } }, "id": 1 }
  
"{\"jsonrpc\": \"2.0\", \"method\": \"VideoLibrary.GetMovies\", \"params\": { 
\"properties\": [ \"title\", \"lastplayed\", \"rating\", \"mpaa\", \"year\", 
\"trailer\", \"uniqueid\" ], \"filter\": { \"and\": [ { \"field\": \"title\", 
\"operator\", \"is\", \"value\": \"Cash on Demand\" }, { \"field\": \"year\", 
\"operator\": \"is\", \"value\": \"1961\" } ] } }, \"id\": 1}"

'{
"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": { "properties": [ 
"title", "lastplayed", "rating", "mpaa", "year", "trailer", "uniqueid" ], "filter": { 
"and": [ { "field": "title", "operator", "is", "value": "Cash on Demand" }, { "field": 
"year", "operator": "is", "value": "1961" } ] } }, "id": 1}'


'''

        props: List[str]
        props = cls.MINIMAL_PROPERTIES

        query_properties: str = ', '.join(f'"{prop}"' for prop in props)
        query = f'{{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", ' \
                       f'"params": {{ "properties": [ {query_properties} ], ' \
                       f'"filter": {{ "and": [ ' \
                       f'{{ "field": "title", "operator": ' \
                       f'"is", "value": "{title}" }}, ' \
                       f'{{ "field": "year", "operator": "is", "value": "{year}" }} ' \
                       f'] }} }}, "id": 1}}'

        if cls._logger.isEnabledFor(LazyLogger.DISABLED):
            cls._logger.debug_verbose(f'title: {title} year: {year}')
            cls._logger.debug_verbose(f'query: {query}')
            try:
                x = simplejson.loads(query)
                query_str = simplejson.dumps(x, indent=4, sort_keys=True)
                cls._logger.debug_extra_verbose(f'query: {query_str}')
            except Exception:
                pass

        return query


DBAccess._class_init_()
