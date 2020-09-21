# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: Frank Feuerbacher
"""

import os
import sys
import datetime
import json

from common.imports import *
from common.constants import Constants, Movie, RemoteTrailerPreference
from common.exceptions import AbortException
from common.monitor import Monitor
from common.logger import (LazyLogger, Trace)
from common.settings import Settings
from backend.json_utils_basic import JsonUtilsBasic

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class MovieEntryUtils (object):
    """

    """
    _logger = None

    @classmethod
    def _class_init(cls):
        cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def get_tmdb_id(cls, movie):
        # type: (MovieType) -> int
        """

        :param movie:
        :return:
        """
        tmdb_id: Optional[str] = None
        imdb_id = None
        title = movie[Movie.TITLE]
        unique_id = movie.get(Movie.UNIQUE_ID, None)
        if unique_id is not None:
            # if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            #     for key in unique_id:
            #         cls._logger.debug_extra_verbose(title, key, unique_id.get(key, ''))
            tmdb_id = unique_id.get(Movie.UNIQUE_ID_TMDB, None)
            if tmdb_id is not None:
                # Make sure we don't have a IMDB id in here by error
                if tmdb_id.startswith('tt'):
                    tmdb_id = None
            if tmdb_id is not None:
                tmdb_id: int = int(tmdb_id)
            else:
                imdb_id = unique_id.get(Movie.UNIQUE_ID_IMDB, None)
                if imdb_id is None:
                    imdb_id = unique_id.get(Movie.UNIQUE_ID_UNKNOWN, None)
                    if imdb_id is not None and not imdb_id.startswith('tt'):
                        imdb_id = None
                if imdb_id is not None:
                    data = {}
                    data['external_source'] = 'imdb_id'

                    # TODO: iso-639-1 gives two char lang. Prefer en-US

                    data['language'] = Settings.get_lang_iso_639_1()
                    data['api_key'] = Settings.get_tmdb_api_key()
                    url = 'http://api.themoviedb.org/3/find/' + str(imdb_id)
                    try:
                        Monitor.throw_exception_if_abort_requested()
                        status_code, tmdb_result = JsonUtilsBasic.get_json(
                            url, error_msg=title,
                            params=data, dump_results=True, dump_msg='')

                        Monitor.throw_exception_if_abort_requested()

                        if status_code == 0 and tmdb_result is not None:
                            s_code = tmdb_result.get('status_code', None)
                            if s_code is not None:
                                status_code = s_code
                        if status_code != 0:
                            pass
                        elif tmdb_result is not None:
                            movie_results = tmdb_result.get(
                                'movie_results', [])
                            if len(movie_results) == 0:
                                pass
                            elif len(movie_results) > 1:
                                pass
                            else:
                                tmdb_id = movie_results[0].get('id', None)
                                if tmdb_id is None:
                                    if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                                        cls._logger.debug('Did not find movie for',
                                                          'imdb_id:', imdb_id,
                                                          'title:', title)
                                else:
                                    cls.set_tmdb_id(movie, tmdb_id)
                                    cls.update_database_unique_id(movie)
                    except AbortException:
                        reraise(*sys.exc_info())
                    except Exception:
                        cls._logger.exception('')
        return tmdb_id

        # noinspection SyntaxError

    @classmethod
    def get_alternate_titles(cls,
                             movie_title,  # type: str
                             movie_id,  # type: Union[int, str]
                             ):
        # type: (...) -> MovieType
        """

        :param cls:
        :param movie_title:
        :param movie_id:
        :return:
        """
        if cls._logger.isEnabledFor(LazyLogger.DEBUG):
            cls._logger.debug('title:', movie_title, 'movie_id:', movie_id)

        data = {}
        # data['append_to_response'] = 'credits,releases'
        data['language'] = Settings.get_lang_iso_639_1()
        data['api_key'] = Settings.get_tmdb_api_key()
        data['append_to_response'] = 'alternative_titles'
        url = 'http://api.themoviedb.org/3/movie/' + str(movie_id)

        tmdb_result = None
        year = 0
        dump_msg = 'movie_id: ' + str(movie_id)
        try:
            Monitor.throw_exception_if_abort_requested()

            status_code, tmdb_result = JsonUtilsBasic.get_json(
                url, error_msg=movie_title,
                params=data, dump_results=False, dump_msg=dump_msg)
            Monitor.throw_exception_if_abort_requested()

            if status_code == 0:
                s_code = tmdb_result.get('status_code', None)
                if s_code is not None:
                    status_code = s_code
            if status_code != 0 and cls._logger.isEnabledFor(LazyLogger.DEBUG):
                cls._logger.debug(
                    'Error getting TMDB data for:', movie_title,
                    'status:', status_code)
                return None
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            cls._logger.exception('Error processing movie: ', movie_title)
            return None

        parsed_data = {}
        try:
            # release_date TMDB key is different from Kodi's
            try:
                year = tmdb_result['release_date'][:-6]
                year = int(year)
            except AbortException:
                reraise(*sys.exc_info())
            except Exception:
                year = 0

            parsed_data[Movie.YEAR] = year

            title = tmdb_result[Movie.TITLE]
            if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                cls._logger.debug('Processing:', title, 'type:',
                                  type(title).__name__)
            parsed_data[Movie.TITLE] = title

            studios = tmdb_result['production_companies']
            studio = []
            for s in studios:
                studio.append(s['name'])

            parsed_data[Movie.STUDIO] = studio

            tmdb_cast_members = tmdb_result['credits']['cast']
            cast = []
            for cast_member in tmdb_cast_members:
                fake_cast_entry = {}
                fake_cast_entry['name'] = cast_member['name']
                fake_cast_entry['character'] = cast_member['character']
                cast.append(fake_cast_entry)

            parsed_data[Movie.CAST] = cast

            tmdb_crew_members = tmdb_result['credits']['crew']
            director = []
            writer = []
            for crew_member in tmdb_crew_members:
                if crew_member['job'] == 'Director':
                    director.append(crew_member['name'])
                if crew_member['department'] == 'Writing':
                    writer.append(crew_member['name'])

            parsed_data[Movie.DIRECTOR] = director
            parsed_data[Movie.WRITER] = writer

            titles = tmdb_result.get('alternative_titles', {'titles': []})
            alt_titles = []
            for title in titles['titles']:
                alt_title = (title['title'], title['iso_3166_1'])
                alt_titles.append(alt_title)

            parsed_data['alt_titles'] = alt_titles
            original_title = tmdb_result['original_title']
            if original_title is not None:
                parsed_data[Movie.ORIGINAL_TITLE] = original_title

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('%s %s'.format(
                'Error getting info for movie_id:', movie_id))
            try:
                if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                    json_text = json.dumps(
                        tmdb_result, indent=3, sort_keys=True)
                    cls._logger.debug(json_text)
            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                cls._logger('failed to get Json data')

            parsed_data = None

        cls._logger.exit('Finished processing movie: ', movie_title, 'year:',
                         year)
        return parsed_data

    @classmethod
    def get_imdb_id(cls, movie):
        # type: (MovieType) -> int
        """

        :param movie:
        :return:
        """
        imdb_id = None
        unique_id = movie.get(Movie.UNIQUE_ID, None)
        if unique_id is not None:
            for key in unique_id:
                cls._logger.debug(movie[Movie.TITLE],
                                  key, unique_id.get(key, ''))
            imdb_id = unique_id.get(Movie.UNIQUE_ID_IMDB, None)
            if imdb_id is not None:
                imdb_id = int(imdb_id)

        return imdb_id

    @staticmethod
    def set_tmdb_id(movie, tmdb_id):
        # type: (MovieType, int) -> None
        """

        :param movie:
        :param tmdb_id:
        :return:
        """
        unique_id = movie.get(Movie.UNIQUE_ID, None)
        if unique_id is None:
            unique_id = {}
            movie[Movie.UNIQUE_ID] = unique_id

        unique_id[Movie.UNIQUE_ID_TMDB] = str(tmdb_id)

    @classmethod
    def update_database_unique_id(cls, trailer):
        # type: ( MovieType) -> None
        """
            Update UNIQUE_ID field in database


        :param trailer:
        :return:
        """
        try:
            update = True
            movie_id = trailer.get(Movie.MOVIEID)
            unique_id = trailer.get(Movie.UNIQUE_ID, None)

            if unique_id is None:
                cls._logger.error('Movie.UNIQUE_ID is None')
                return

            # "uniqueid":{"imdb": "tt0033517", "unknown": "tt0033517"}
            # "uniqueid": {"tmdb": 196862, "imdb": "tt0042784"}
            Monitor.throw_exception_if_abort_requested()

            json_text = json.dumps(unique_id)
            update = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", \
                    "params": {\
                        "movieid": %s, "uniqueid": %s }, "id": 1}' % (movie_id, json_text)

            query_result = JsonUtilsBasic.get_kodi_json(
                update, dump_results=True)
            Monitor.throw_exception_if_abort_requested()

            if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                cls._logger.debug('Update TMDBID for:', trailer[Movie.TITLE],
                                  'update json:', update)
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')


# Initialize logger
MovieEntryUtils._class_init()
