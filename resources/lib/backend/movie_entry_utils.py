# -*- coding: utf-8 -*-
"""
Created on Apr 14, 2019

@author: Frank Feuerbacher
"""

import sys
import simplejson as json

from common.imports import *
from common.exceptions import AbortException
from common.monitor import Monitor
from common.logger import LazyLogger
from common.movie import AbstractMovie, LibraryMovie, TFHMovie
from common.movie_constants import MovieField
from common.rating import Certifications, WorldCertifications, Certification
from common.settings import Settings
from backend.json_utils_basic import JsonUtilsBasic

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class MovieEntryUtils:
    """

    """
    _logger: LazyLogger = None

    @classmethod
    def class_init(cls) -> None:
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def get_tmdb_id(cls, movie: AbstractMovie) -> Union[int, None]:
        """

        :param movie:
        :return:
        """
        tmdb_id_int: int = None
        tmdb_id_str: str = None
        title: str = movie.get_title()
        source: str = movie.get_source()
        try:
            tmdb_id_str: str = movie.get_unique_id(MovieField.UNIQUE_ID_TMDB)
            if tmdb_id_str is not None:
                # Make sure we don't have a IMDB id in here by error
                if tmdb_id_str.startswith('tt'):
                    tmdb_id_str = None
            if tmdb_id_str is not None:
                try:
                    tmdb_id_int = int(tmdb_id_str)
                except ValueError:
                    tmdb_id_str = None
            if tmdb_id_str is None:
                imdb_id = movie.get_unique_id(MovieField.UNIQUE_ID_IMDB)
                if imdb_id is None:
                    imdb_id = movie.get_unique_id(MovieField.UNIQUE_ID_UNKNOWN)
                    if imdb_id is not None and not imdb_id.startswith('tt'):
                        imdb_id = None
                if imdb_id is not None:
                    data = {'external_source': 'imdb_id',

                            # TODO: iso-639-1 gives two char lang. Prefer en-US

                            'language': Settings.get_lang_iso_639_1(),
                            'api_key': Settings.get_tmdb_api_key()
                             }
                    url = 'http://api.themoviedb.org/3/find/' + \
                        str(imdb_id)
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
                                try:
                                    tmdb_id_int = int(tmdb_id)
                                except ValueError:
                                    tmdb_id = None

                                if tmdb_id is None:
                                    if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                                        cls._logger.debug('Did not find movie for',
                                                          'imdb_id:', imdb_id,
                                                          'title:', title)
                                else:
                                    changed: bool = movie.add_tmdb_id(tmdb_id)
                                    if changed:
                                        if isinstance(movie, TFHMovie):
                                            from cache.tfh_cache import TFHCache

                                            TFHCache.update_movie(movie)

                                        if isinstance(movie, LibraryMovie):
                                            cls.update_database_unique_id(movie)
                    except AbortException:
                        reraise(*sys.exc_info())
                    except Exception:
                        cls._logger.exception(
                            f'Title: {title} source: {source}')
        except Exception as e:
            cls._logger.exception(f'Title: {title} source: {source}')
        if tmdb_id_str is not None:
            tmdb_id_int = int(tmdb_id_str)

        return tmdb_id_int

    '''
    @classmethod
    def get_alternate_titles(cls,
                             movie_title: str,
                             tmdb_id: Union[int, str],
                             ) -> TMDbMovie:
        """

        :param cls:
        :param movie_title:
        :param tmdb_id:
        :return:
        """
        if cls._logger.isEnabledFor(LazyLogger.DEBUG):
            cls._logger.debug('title:', movie_title, 'tmdb_id:', tmdb_id)

        data = {
            # 'append_to_response': 'credits,releases'
            'language': Settings.get_lang_iso_639_1(),
            'api_key': Settings.get_tmdb_api_key(),
            'append_to_response': 'alternative_titles'}

        url = 'http://api.themoviedb.org/3/movie/' + str(tmdb_id)

        tmdb_result = None
        year = 0
        dump_msg = 'tmdb_id: ' + str(tmdb_id)
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

        movie: TMDbMovie = TMDbMovie()
        try:
            # release_date TMDB key is different from Kodi's
            try:
                year = tmdb_result['release_date'][:-6]
                year = int(year)
            except AbortException:
                reraise(*sys.exc_info())
            except Exception:
                year = 0

            movie.set_year(year)

            title = tmdb_result[MovieField.TITLE]
            if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                cls._logger.debug('Processing:', title, 'type:',
                                  type(title).__name__)
            movie.set_title(title)

            studios = tmdb_result['production_companies']
            studio = []
            for s in studios:
                studio.append(s['name'])

            movie.set_studios(studio)


            tmdb_crew_members = tmdb_result['credits']['crew']
            director = []
            writer = []
            for crew_member in tmdb_crew_members:
                if crew_member['job'] == 'Director':
                    director.append(crew_member['name'])
                if crew_member['department'] == 'Writing':
                    writer.append(crew_member['name'])

            movie.set_directors(director)
            movie.set_writers(writer)

            titles = tmdb_result.get('alternative_titles', {'titles': []})
            alt_titles = []
            for title in titles['titles']:
                alt_title = (title['title'], title['iso_3166_1'])
                alt_titles.append(alt_title)

            movie.set_alt_titles(alt_titles)
            original_title = tmdb_result['original_title']
            if original_title is not None:
                movie.set_original_title(original_title)

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('%s %s'.format(
                'Error getting info for tmdb_id:', tmdb_id))
            try:
                if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                    json_text = json.dumps(
                        tmdb_result, indent=3, sort_keys=True)
                    cls._logger.debug(json_text)
            except AbortException:
                reraise(*sys.exc_info())
            except Exception as e:
                cls._logger.exception('failed to get Json data')

            movie = None

        cls._logger.exit('Finished processing movie: ', movie_title, 'year:',
                         year)
        return movie
    '''

    @classmethod
    def update_database_unique_id(cls, movie: LibraryMovie) -> None:
        """
            Update UNIQUE_ID field in database


        :param movie:
        :return:
        """
        try:
            update = True
            movie_id = movie.get_library_id()
            unique_id: Dict[str, str] = movie.get_unique_ids()

            # "uniqueid":{"imdb": "tt0033517", "unknown": "tt0033517"}
            # "uniqueid": {"tmdb": 196862, "imdb": "tt0042784"}
            Monitor.throw_exception_if_abort_requested()

            json_text = json.dumps(unique_id)

            update = f'{{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails",' \
                     f'"params": {{' \
                     f'"movieid": {movie_id}, "uniqueid": {json_text}}}, "id": 1}}'

            query_result = JsonUtilsBasic.get_kodi_json(
                update, dump_results=True)
            Monitor.throw_exception_if_abort_requested()

            if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                cls._logger.debug('Update TMDBID for:', movie.get_title(),
                                  'update json:', update)
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

    @classmethod
    def get_default_certification_id(cls) -> str:
        country_id: str = Settings.get_country_iso_3166_1().lower()
        certifications: Certifications = \
            WorldCertifications.get_certifications(country_id)

        unrated_id: str = certifications.get_unrated_certification().get_preferred_id()
        return unrated_id

    @classmethod
    def is_include_adult_certification(cls) -> bool:
        country_id: str = Settings.get_country_iso_3166_1().lower()
        certifications: Certifications = \
            WorldCertifications.get_certifications(country_id)
        adult_certification: Certification = certifications.get_adult_certification()
        include_adult: bool = certifications.filter(adult_certification)
        return include_adult


MovieEntryUtils.class_init()
