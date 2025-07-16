import sys

from common.constants import RemoteTrailerPreference
from common.imports import *
from common.logger import *
from common.movie import LibraryMovie
from common.movie_constants import MovieField
from common.certification import Certification, WorldCertifications
from common.settings import Settings
from common.exceptions import AbortException, reraise
from .__init__ import *

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class LibraryFilter:

    logger: BasicLogger = None

    @classmethod
    def class_init(cls,) -> None:

        if cls.logger is None:
            cls.logger: BasicLogger = module_logger.getChild(cls.__name__)

    @classmethod
    def filter_movie(cls, movie: LibraryMovie) -> List[int]:
        rejection_reasons: List[int] = []
        minimum_year: int = Settings.get_tmdb_minimum_year()
        maximum_year: int = Settings.get_tmdb_maximum_year()
        vote_comparison, vote_value = Settings.get_tmdb_avg_vote_preference()
        country_id = Settings.get_country_iso_3166_1().lower()
        certifications = WorldCertifications.get_certifications(country_id)
        unrated_id = certifications.get_unrated_certification().get_preferred_id()

        filter_passes = True
        try:
            movie_title = movie.get_title()

            if Settings.get_hide_watched_movies():
                if (movie.get_days_since_last_played() >
                        Settings.get_minimum_days_since_watched()):
                    filter_passes = False
                    rejection_reasons.append(MovieField.REJECTED_WATCHED)

            ''' 
            TODO:  Consider enabling for library movies.

            if filter_passes and movie.get_year() < minimum_year:
                filter_passes = False
            elif filter_passes and not movie.get_year() > maximum_year:
                filter_passes = False
            if not filter_passes:
                rejection_reasons.append(MovieField.REJECTED_FILTER_DATE)
            '''

            if filter_passes:
                filter_passes = WorldCertifications.filter(
                    certification_id=movie.get_certification_id())
                if not filter_passes:
                    rejection_reasons.append(MovieField.REJECTED_CERTIFICATION)

            '''
            Kodi library entries do not have language information
            Could get from actual movie file, but might require file to be
            cracked open and audio tracks scanned for language info. Not
            a great choice.
            
            is_original_language_found: bool = movie.is_original_language_found()
            if not (is_original_language_found or Settings.is_allow_foreign_languages()):
                if cls.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                    cls.logger.debug_extra_verbose(
                        f'Rejected due to foreign language: {movie_title}')
                add_movie = False
                rejection_reasons.append(MovieField.REJECTED_LANGUAGE)
            '''

            vote_comparison, vote_value = Settings.get_tmdb_avg_vote_preference()
            if vote_comparison != RemoteTrailerPreference.AVERAGE_VOTE_DONT_CARE:
                if vote_comparison == \
                        RemoteTrailerPreference.AVERAGE_VOTE_GREATER_OR_EQUAL:
                    if movie.get_rating() < vote_value:
                        add_movie = False
                        rejection_reasons.append(MovieField.REJECTED_VOTE)
                        if cls.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                            cls.logger.debug_extra_verbose(
                                f'Rejected due to vote_average < {movie_title}')
                elif vote_comparison == \
                        RemoteTrailerPreference.AVERAGE_VOTE_LESS_OR_EQUAL:
                    if movie.get_rating() > vote_value:
                        add_movie = False
                        rejection_reasons.append(MovieField.REJECTED_VOTE)
                        if cls.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
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
                if cls.logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                    cls.logger.debug_extra_verbose(
                        f'Rejected due to rating: {movie_title} '
                        f'cert: {str(certification)}'
                        f' mpaa: {movie.get_certification_id()}')
                    # Debug.dump_json(text='get_tmdb_trailer exit:', data=dict_info)

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            cls.logger.exception(msg='')

        return rejection_reasons


LibraryFilter.class_init()
