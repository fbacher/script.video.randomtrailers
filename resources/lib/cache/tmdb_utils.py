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
            cached_movie: MovieType = Cache.read_tmdb_cache_json(
                tmdb_id.get_id(),
                MovieField.TMDB_SOURCE,
                error_msg='TMDb movie '
                          'not found')
            if cached_movie is not None:
                year = cached_movie['release_date'][:-6]
                year = int(year)
                movie_entry = {MovieField.TRAILER: MovieField.TMDB_SOURCE,
                               MovieField.SOURCE: MovieField.TMDB_SOURCE,
                               MovieField.TITLE: cached_movie[MovieField.TITLE],
                               MovieField.YEAR: year,
                               MovieField.ORIGINAL_LANGUAGE:
                                   cached_movie[MovieField.ORIGINAL_LANGUAGE]}
                movie: TMDbMovie = TMDbMovie(movie_info=movie_entry)
                movie.set_tmdb_id(int(tmdb_id.get_id()))
                if TMDbFilter.pre_filter_movie(movie):
                    if additional_movies_to_get <= 0:
                        break
                    movies.append(movie)
                    additional_movies_to_get -= 1
                else:
                    Cache.delete_cache_json(tmdb_id.get_id(), MovieField.TMDB_SOURCE)
        return movies
