# -*- coding: utf-8 -*-
"""
Created on 4/13/21

@author: Frank Feuerbacher
"""
import sys

from backend.genreutils import GenreUtils
from common.imports import *
from common.logger import LazyLogger
from common.movie import ITunesMovie
from common.movie_constants import MovieField
from common.certification import Certification, WorldCertifications, Certifications
from common.settings import Settings
from six import reraise

from common.exceptions import AbortException

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class ITunesFilter:

    logger: LazyLogger = None

    @classmethod
    def class_init(cls,) -> None:

        if cls.logger is None:
            cls.logger: LazyLogger = module_logger.getChild(cls.__name__)

    @classmethod
    def filter_movie(cls, movie: ITunesMovie) -> List[int]:
        rejection_reasons: List[int] = []

        filter_passes = True
        try:
            movie_title = movie.get_title()
            _selected_genres: List[str] = []
            _excluded_genres: List[str] = []

            if Settings.get_filter_genres():
                movie_genres: List[str] = movie.get_genre_names()

                _selected_genres = GenreUtils.get_external_genre_ids(
                    GenreUtils.ITUNES_DATABASE, exclude=False)
                _excluded_genres = GenreUtils.get_external_genre_ids(
                    GenreUtils.ITUNES_DATABASE, exclude=True)
                if (len(_selected_genres) > 0 and
                        (len(movie_genres) > 0) and
                        set(_selected_genres).isdisjoint(set(movie_genres))):
                    filter_passes = False
                    rejection_reasons.append(MovieField.REJECTED_FILTER_GENRE)

                    if cls.logger.isEnabledFor(LazyLogger.DISABLED):
                        cls.logger.debug_verbose(
                            f'Rejecting {movie_title} due to genre')
                if filter_passes and \
                        set(_excluded_genres).intersection(set(movie_genres)):
                    filter_passes = False
                    rejection_reasons.append(MovieField.REJECTED_FILTER_GENRE)

                    if cls.logger.isEnabledFor(LazyLogger.DISABLED):
                        cls.logger.debug_verbose(
                            f'Rejecting {movie_title} due to excluded genre')

            #  TODO: Needs to be fixed

            # if movie.get_trailer_path() != '':
            #     rejection_reasons.append(MovieField.REJECTED_NO_TRAILER)

            certification_id: str = movie.get_certification_id()
            certification: Certification =\
                WorldCertifications.get_certification_by_id(certification_id)

            certifications: Certifications = WorldCertifications.get_certifications()

            if filter_passes and not certifications.filter(certification):
                filter_passes = False
                rejection_reasons.append(MovieField.REJECTED_CERTIFICATION)

                if cls.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls.logger.debug_extra_verbose(
                        f'Rejected due to rating: {movie_title} cert: '
                        f'{str(certification)}')

        except AbortException as e:
            reraise(*sys.exc_info())
        except Exception as e:
            cls.logger.exception()

        return rejection_reasons


ITunesFilter.class_init()
