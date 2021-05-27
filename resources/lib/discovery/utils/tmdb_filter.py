# -*- coding: utf-8 -*-
"""
Created on 4/13/21

@author: Frank Feuerbacher
"""

import sys

from backend.genreutils import GenreUtils
from common.constants import RemoteTrailerPreference
from common.imports import *
from common.logger import LazyLogger
from common.movie import TMDbMovie, TMDbMoviePageData
from common.movie_constants import MovieField
from common.rating import Certification, WorldCertifications
from common.settings import Settings

from common.exceptions import AbortException, reraise
from discovery.restart_discovery_exception import RestartDiscoveryException

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TMDbFilter:

    logger: LazyLogger = None

    @classmethod
    def class_init(cls,) -> None:

        if cls.logger is None:
            cls.logger: LazyLogger = module_logger.getChild(cls.__name__)

    @classmethod
    def pre_filter_movie(cls,
                         movie: Union[TMDbMoviePageData, TMDbMovie]) -> bool:
        """
        Filter the given movie information to determine if it passes the current
        filter settings.

        The movie information can be either complete or partial information.

        Complete information is from TrailerFetcher.get_tmdb_trailer,
        by way of the cache Cache.read_tmdb_cache_json.

        Partial information is from the initial TMDb page discovery via
        CacheIndex.get_unprocessed_movies.

        For the most part, the fields are the same for both types of entries.

        :param movie:
                Movie to filter
                TMDbMovie objects are fully populated with enough information to
                do a complete filter
                TMDbMoviePageData objects are partially populated from summary
                information and only a pre-filter can be performed to weed out
                movies which no additional queries from TMDb are needed.
        :return:
        """

        minimum_year: int = Settings.get_tmdb_minimum_year()
        maximum_year: int = Settings.get_tmdb_maximum_year()
        vote_comparison, vote_value = Settings.get_tmdb_avg_vote_preference()

        filter_passes = True
        try:
            movie_title = movie.get_title()

            if minimum_year is not None \
                    and movie.get_year() < minimum_year:
                filter_passes = False
                if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls.logger.debug_extra_verbose(
                        'Omitting movie_entry older than minimum Year:',
                        minimum_year, 'movie_entry:',
                        movie_title,
                        'release:', movie.get_year())
            elif maximum_year is not None \
                    and movie.get_year() > maximum_year:
                filter_passes = False
                if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls.logger.debug_extra_verbose(
                        'Omitting movie_entry newer than maximum Year:',
                        minimum_year, 'movie_entry:',
                        movie_title,
                        'release:', movie.get_year())

            # Trailer Type is unknown for TMDbMoviePageData objects, so '' is
            # returned instead, which filter ignores.
            #
            #  TODO: Consider moving trailer choice from parse_basic_trailer_information to here
            #  and enable it to be dynamic, persisting best of each video type
            #  so that decision can be remade when settings change without
            #  refetching from TMDb.

            movie_type = movie.get_trailer_type()
            if (movie_type == MovieField.TRAILER_TYPE_FEATURETTE
                    and not Settings.get_include_featurettes()):
                filter_passes = False
            elif (movie_type == MovieField.TRAILER_TYPE_CLIP
                  and not Settings.get_include_clips()):
                filter_passes = False
            elif (movie_type == MovieField.TRAILER_TYPE_TRAILER
                  and not Settings.get_include_tmdb_trailers()):
                filter_passes = False

            elif movie.get_certification_id() is not None:
                cert_passes: bool = WorldCertifications.filter(
                    certification_id=movie.get_certification_id())
                if not cert_passes:
                    filter_passes = False
            elif not Settings.is_allow_foreign_languages() \
                    and movie.get_original_language().lower() != \
                    Settings.get_lang_iso_639_1().lower():
                filter_passes = False

            # plot = movie.get('overview', '')
            # popularity = movie.get('popularity', '0.0')
            #  original_title = movie.get('original_title', '')
            #  backdrop_path = movie.get('backdrop_path', '')
            # vote_count = movie.get('vote_count', '-1')
            # is_video = movie.is_video()
            vote_average: float = movie.get_rating()
            genre_ids: [int] = movie.get_genre_ids()
            original_language: str = movie.get_original_language()

            # We know the genres for this movie, but not the keywords.

            if not GenreUtils.include_movie(genre_names=genre_ids, tag_names=None):
                filter_passes = False
                if cls.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    cls.logger.debug_verbose('Rejected due to Genre')

            if vote_comparison == \
                    RemoteTrailerPreference.AVERAGE_VOTE_GREATER_OR_EQUAL:
                if vote_average < vote_value:
                    filter_passes = False
                    if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls.logger.debug_extra_verbose(
                            f'Rejected due to vote_average < {movie_title}')
            elif vote_comparison == \
                    RemoteTrailerPreference.AVERAGE_VOTE_LESS_OR_EQUAL:
                if vote_average > vote_value:
                    filter_passes = False
                    if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls.logger.debug_extra_verbose(
                            f'Rejected due to vote_average > {movie_title}')

            """
            original_title = tmdb_result['original_title']
            if original_title is not None:
                dict_info[MovieField.ORIGINAL_TITLE] = original_title

            adult_movie = tmdb_result['adult'] == 'true'
            if adult_movie and not include_adult:
                add_movie = False
                if cls.logger.isEnabledFor(LazyLogger.DEBUG):
                    cls.logger.debug('Rejected due to adult')

            dict_info[MovieField.ADULT] = adult_movie
            dict_info[MovieField.SOURCE] = MovieField.TMDB_SOURCE

            # Normalize rating

            mpaa = Rating.get_certification_id(mpaa_rating=mpaa, adult_rating=None)
            if not Rating.filter(mpaa):
                add_movie = False
                if cls.logger.isEnabledFor(LazyLogger.DEBUG):
                    cls.logger.debug('Rejected due to rating')
                    # Debug.dump_json(text='get_tmdb_trailer exit:', data=dict_info)

            current_parameters = CacheParameters({
                'excluded_tags': cls._excluded_keywords,
                'remote_trailer_preference': cls._remote_trailer_preference,
                'vote_comparison': vote_comparison,  # type: int
                'vote_value': vote_value,  # type: int
                'rating_limit_string': cls._rating_limit_string,  # type: str
                'language': cls._language,  # type str
                'country': cls._country,  # type: str
            })
            """

        except (AbortException, RestartDiscoveryException):
            reraise(*sys.exc_info())
        except Exception as e:
            cls.logger.exception('')

        return filter_passes

    @classmethod
    def filter_movie(cls, movie: TMDbMovie) -> List[int]:
        rejection_reasons: List[int] = []
        minimum_year: int = Settings.get_tmdb_minimum_year()
        maximum_year: int = Settings.get_tmdb_maximum_year()
        vote_comparison, vote_value = Settings.get_tmdb_avg_vote_preference()

        filter_passes = True
        try:
            movie_title = movie.get_title()

            if movie.get_trailer_path() == '':
                rejection_reasons.append(MovieField.REJECTED_NO_TRAILER)
                if cls.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    cls.logger.debug_verbose('No trailer found for movie:',
                                             movie_title,
                                             'Continuing to process other data')

            # Year check not needed for movies downloaded by tmdb_id, but is used
            # for those downloaded by a search (page data).

            date_passes = True
            if minimum_year is not None \
                    and movie.get_year() < minimum_year:
                date_passes = False
            elif maximum_year is not None \
                    and movie.get_year() > maximum_year:
                date_passes = False
            if not date_passes:
                rejection_reasons.append(MovieField.REJECTED_FILTER_DATE)
                add_movie = False

            if not GenreUtils.include_movie(genre_names=movie.get_genre_ids(),
                                            tag_names=movie.get_tag_ids()):
                if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls.logger.debug_extra_verbose(
                        f'Rejected due to Genre or Keyword: {movie_title}')
                add_movie = False
                rejection_reasons.append(MovieField.REJECTED_FILTER_GENRE)

            is_original_language_found: bool = movie.is_original_language_found()
            if not (is_original_language_found or Settings.is_allow_foreign_languages()):
                if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls.logger.debug_extra_verbose(
                        f'Rejected due to foreign language: {movie_title}')
                add_movie = False
                rejection_reasons.append(MovieField.REJECTED_LANGUAGE)

            vote_comparison, vote_value = Settings.get_tmdb_avg_vote_preference()
            if vote_comparison != RemoteTrailerPreference.AVERAGE_VOTE_DONT_CARE:
                if vote_comparison == \
                        RemoteTrailerPreference.AVERAGE_VOTE_GREATER_OR_EQUAL:
                    if movie.get_rating() < vote_value:
                        add_movie = False
                        rejection_reasons.append(MovieField.REJECTED_VOTE)
                        if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls.logger.debug_extra_verbose(
                                f'Rejected due to vote_average < {movie_title}')
                elif vote_comparison == \
                        RemoteTrailerPreference.AVERAGE_VOTE_LESS_OR_EQUAL:
                    if movie.get_rating() > vote_value:
                        add_movie = False
                        rejection_reasons.append(MovieField.REJECTED_VOTE)
                        if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            cls.logger.debug_extra_verbose(
                                f'Rejected due to vote_average > {movie_title}')

            # Normalize certification

            country_id = Settings.get_country_iso_3166_1().lower()
            certifications = WorldCertifications.get_certifications(country_id)
            certification: Certification = certifications.get_certification(
                movie.get_certification_id())

            if not certifications.filter(certification):
                add_movie = False
                rejection_reasons.append(MovieField.REJECTED_CERTIFICATION)
                if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls.logger.debug_extra_verbose(
                        f'Rejected due to rating: {movie_title} cert: {str(certification)}'
                        f' mpaa: {movie.get_certification_id()}')
                    # Debug.dump_json(text='get_tmdb_trailer exit:', data=dict_info)

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            cls.logger.exception(
                f'Error filtering tmdb movie: {movie.get_title()}')
            
        cls.logger.exit(f'Finished processing movie: {movie.get_title()} year: '
                        f'{movie.get_year()} rejection_reason count:  '
                        f'{len(rejection_reasons)}')

        return rejection_reasons


TMDbFilter.class_init()
