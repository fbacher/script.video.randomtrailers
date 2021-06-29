# -*- coding: utf-8 -*-
"""
Created on 4/13/21

@author: Frank Feuerbacher
"""

from cache.cache import Cache
from common.imports import *
from common.movie import MovieField, TMDbMovie, TMDbMovieId
from common.utils import Delay
from discovery.utils.tmdb_filter import TMDbFilter


class TMDbUtils:

    @classmethod
    def load_from_cache(cls, tmdb_movie_ids: Iterable[TMDbMovieId],
                        additional_movies_to_get: int,
                        delay: Delay = None) -> List[TMDbMovie]:
        movies: List[TMDbMovie] = []
        for tmdb_id in tmdb_movie_ids:
            if Delay is not None:
                Delay.delay()
            cached_movie: TMDbMovie = Cache.read_tmdb_cache_json(
                tmdb_id.get_id(),
                error_msg='TMDb movie '
                          'not found')
            if cached_movie is not None:
                if TMDbFilter.pre_filter_movie(cached_movie):
                    if additional_movies_to_get <= 0:
                        break
                    movies.append(cached_movie)
                    additional_movies_to_get -= 1
                else:
                    Cache.delete_cache_json(tmdb_id.get_id(), MovieField.TMDB_SOURCE)
        return movies
