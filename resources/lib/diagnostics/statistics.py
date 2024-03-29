# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import os

from common.imports import *
from common.logger import LazyLogger

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class Statistics:
    """

    """

    _library_movies_found: int = 0
    _library_movies_filtered_out: int = 0
    _library_movies_with_local_trailers: int = 0
    _library_movies_with_trailer_urls: int = 0
    _library_movies_without_trailer_info: int = 0
    _library_db_query_seconds: int = 0
    _library_trailer_url_query_successes: int = 0
    _library_trailer_url_query_failures: int = 0
    _library_trailer_not_found: int = 0
    _library_trailer_found: int = 0

    _added_missing_tmdb_trailers: int = 0
    _added_missing_library_trailers: int = 0
    _missing_library_id_not_in_cache: int = 0
    _missing_library_id_in_cache: int = 0
    _missing_tmdb_id_not_in_cache: int = 0
    _missing_tmdb_id_in_cache: int = 0
    _missing_tmdb_trailers_initial_size: int = 0
    _missing_library_trailers_initial_size: int = 0
    _missing_tmdb_trailers: int = 0
    _missing_library_trailers: int = 0

    _tmdb_movies: int = 0
    _tmdb_movies_filtered_out: int = 0
    _tmdb_movies_with_trailers: int = 0
    _tmdb_db_page_queries: int = 0
    _tmdb_db_page_query_peak_five_minute_rate: int = 0
    _tmdb_db_page_query_rate: int = 0
    _tmdb_db_page_query_failures: int = 0
    _tmdb_get_detail_queries: int = 0
    _tmdb_trailer_queries: int = 0
    _tmdb_cached_trailers: int = 0
    _tmdb_play_already_cached_trailers: int = 0
    _tmdb_normalized_trailers: int = 0
    _tmdb_play_already_normalized_trailers: int = 0
    _total_number_of_tmdb_cached_trailers: int = 0
    _total_number_of_normalized_trailers: int = 0
    _tmdb_total_number_of_unprocessed_movies: int = 0
    _tmdb_total_number_of_removed_unprocessed_movies: int = 0
    _tmdb_trailer_found: int = 0
    _tmdb_trailer_not_found: int = 0
    _next_trailer_wait_time_elapsed_seconds: int = 0
    _next_trailer_wait_time_attempts: int = 0
    _next_trailer_second_attempt_wait_time_elapsed_seconds: int = 0
    _next_trailer_second_attempt_wait_time_attempts: int = 0
    _next_trailer_third_attempt_wait_time_elapsed_seconds: int = 0
    _next_trailer_third_attempt_wait_time_attempts: int = 0
    _json_io_time: int = 0

    # For Discovery Modules

    @classmethod
    def add_library_movies_found(cls, movie_count: int = 1) -> None:
        """

        :param movie_count:
        :return:
        """
        cls._library_movies_found += movie_count

    @classmethod
    def add_library_movies_filtered_out(cls) -> None:
        """

        :return:
        """
        cls._library_movies_filtered_out += 1

    @classmethod
    def add_library_movies_with_local_trailers(cls) -> None:
        """

        :return:
        """
        cls._library_movies_with_local_trailers += 1

    @classmethod
    def add_library_movies_with_trailer_urls(cls) -> None:
        """

        :return:
        """
        cls._library_movies_with_trailer_urls += 1

    @classmethod
    def add_library_movies_without_trailer_info(cls) -> None:
        """

        :return:
        """
        cls._library_movies_filtered_out += 1

    @classmethod
    def set_library_db_query_seconds(cls, seconds: int) -> None:
        """

        :param seconds:
        :return:
        """
        cls._library_db_query_seconds = seconds

    @classmethod
    def add_library_trailer_url_query_successes(cls) -> None:
        """

        :return:
        """
        cls._library_trailer_url_query_successes += 1

    @classmethod
    def add_library_trailer_url_query_failures(cls) -> None:
        """

        :return:
        """
        cls._library_trailer_url_query_failures += 1

    @classmethod
    def add_library_trailer_found(cls) -> None:
        """

        :return:
        """
        cls._library_trailer_found += 1

    @classmethod
    def add_library_trailer_not_found(cls) -> None:
        """

        :return:
        """
        cls._library_trailer_not_found += 1

    # TMDB Trailer discovery

    @classmethod
    def add_tmdb_movies_found(cls) -> None:
        """

        :return:
        """
        cls._tmdb_movies += 1

    @classmethod
    def add_tmdb_movies_filtered_out(cls) -> None:
        """

        :return:
        """
        cls._tmdb_movies_filtered_out += 1

    @classmethod
    def add_tmdb_movies_with_trailers(cls) -> None:
        """

        :return:
        """
        cls._tmdb_movies_with_trailers += 1

    @classmethod
    def add_tmdb_db_page_queries(cls) -> None:
        """

        :return:
        """
        cls._tmdb_db_page_queries += 1

    @classmethod
    def tmdb_db_page_query_occurred(cls) -> None:
        """

        :return:
        """
        cls._tmdb_db_page_query_peak_five_minute_rate = 0
        cls._tmdb_db_page_query_rate = 0

    @classmethod
    def add_tmdb_db_page_query_failures(cls) -> None:
        """

        :return:
        """
        cls._tmdb_db_page_query_failures += 1

    @classmethod
    def add_tmdb_get_detail_queries(cls) -> None:
        """

        :return:
        """
        cls._tmdb_get_detail_queries += 1

    @classmethod
    def add_tmdb_trailer_queries(cls) -> None:
        """

        :return:
        """
        cls._tmdb_trailer_queries += 1

    @classmethod
    def tmdb_db_trailer_details_query_occurred(cls) -> None:
        """

        :return:
        """
        cls._tmdb_db_trailer_details_query_rate = 0
        cls._tmdb_db_trailer_details_query_peak_rate = 0

    @classmethod
    def add_tmdb_cached_trailers(cls) -> None:
        """

        :return:
        """
        cls._tmdb_cached_trailers += 1

    @classmethod
    def add_tmdb_play_already_cached_trailers(cls) -> None:
        """

        :return:
        """
        cls._tmdb_play_already_cached_trailers += 1

    @classmethod
    def add_tmdb_normalized_trailer(cls) -> None:
        """

        :return:
        """
        cls._tmdb_normalized_trailers += 1

    @classmethod
    def add_tmdb_play_already_normalized_trailers(cls) -> None:
        """

        :return:
        """
        cls._tmdb_play_already_normalized_trailers += 1

    @classmethod
    def add_total_number_of_tmdb_cached_trailers(cls,
                                                 number_of_trailers: int = 1) -> None:
        """

        :return:
        """
        cls._total_number_of_tmdb_cached_trailers += number_of_trailers

    @classmethod
    def add_total_number_of_normalized_trailers(cls,
                                                number_of_trailers: int = 1) -> None:
        """

        :return:
        """
        cls._total_number_of_normalized_trailers += number_of_trailers

    @classmethod
    def add_tmdb_trailer_found(cls) -> None:
        """

        :return:
        """
        cls._tmdb_trailer_found += 1

    @classmethod
    def add_tmdb_trailer_not_found(cls) -> None:
        """

        :return:
        """
        cls._tmdb_trailer_not_found += 1

    @classmethod
    def add_tmdb_total_number_of_unprocessed_movies(cls,
                                                    number: int = 1) -> None:
        """
        :param number:
        :return:
        """
        cls._tmdb_total_number_of_unprocessed_movies += number

    @classmethod
    def add_tmdb_total_number_of_removed_unprocessed_movies(cls,
                                                            number: int = 1
                                                            ) -> None:
        """
        :param number:
        :return:
        """
        cls._tmdb_total_number_of_removed_unprocessed_movies += number

    # For TrailerUnavailableCache

    @classmethod
    def missing_tmdb_trailers_initial_size(cls, size: int) -> None:
        """

        :return:
        """
        cls._missing_tmdb_trailers_initial_size = size

    @classmethod
    def missing_library_trailers_initial_size(cls, size: int) -> None:
        """

        :return:
        """
        cls._missing_library_trailers_initial_size = size

    @classmethod
    def add_missing_tmdb_trailer(cls) -> None:
        """

        :return:
        """
        cls._missing_tmdb_trailers += 1

    @classmethod
    def add_missing_library_trailer(cls) -> None:
        """

        :return:
        """
        cls._missing_library_trailers += 1

    @classmethod
    def add_missing_library_id_cache_miss(cls) -> None:
        """

        :return:
        """
        cls._missing_library_id_not_in_cache += 1

    @classmethod
    def add_missing_library_id_cache_hit(cls) -> None:
        """

        :return:
        """
        cls._missing_library_id_in_cache += 1

    @classmethod
    def add_missing_tmdb_id_cache_miss(cls) -> None:
        """

        :return:
        """
        cls._missing_tmdb_id_not_in_cache += 1

    @classmethod
    def add_missing_tmdb_cache_hit(cls) -> None:
        """

        :return:
        """
        cls._missing_tmdb_id_in_cache += 1

    @classmethod
    def add_json_read_time(cls, milliseconds: int) -> None:
        cls._json_io_time += milliseconds

    @classmethod
    def add_next_trailer_wait_time(cls, elapsed_seconds: int,
                                   attempts: int) -> None:
        cls._next_trailer_wait_time_elapsed_seconds += elapsed_seconds
        cls._next_trailer_wait_time_attempts += attempts

    @classmethod
    def add_next_trailer_second_attempt_wait_time(cls, elapsed_seconds: int,
                                                  attempts: int) -> None:
        cls._next_trailer_second_attempt_wait_time_elapsed_seconds += elapsed_seconds
        cls._next_trailer_second_attempt_wait_time_attempts += attempts

    @classmethod
    def add_next_trailer_second_attempt_wait_time(cls,
                                                  elapsed_seconds: int,
                                                  attempts: int) -> None:
        cls._next_trailer_third_attempt_wait_time_elapsed_seconds += elapsed_seconds
        cls._next_trailer_third_attempt_wait_time_attempts += attempts
