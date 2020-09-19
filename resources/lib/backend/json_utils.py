# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import datetime
import random

from common.imports import *

from backend.json_utils_basic import (JsonUtilsBasic)
from backend.statistics import Statistics
from cache.cache import (Cache)
from common.development_tools import (Any, List, Dict, Union)
from common.constants import Constants, Movie
from common.logger import (LazyLogger, Trace)
from common.exceptions import AbortException
from common.messages import Messages
from common.settings import Settings

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class JsonUtils(JsonUtilsBasic):
    RandomGenerator = random.Random()
    RandomGenerator.seed()

    _exit_requested = False
    """
        Tunes and TMDB each have rate limiting:
            TMDB is limited over a period of 10 seconds
            iTunes is limited to 20 requests/minute and 200
            results per search.
            
            For iTunes see:
         https://affiliate.itunes.apple.com/resources/documentation/itunes-store-web-service-search-api/#overview
             All iTunes results are JSON UTF-8

        In order to track the rate of requests over a minute, we have to
        track the timestamp of each request made in the last minute.
    
        Keep in mind for both TMDB and iTunes, that other plugins may be
        making requests
    """

    TMDB_NAME = 'tmdb'
    TMDB_REQUEST_INDEX = 0
    TMDB_WINDOW_TIME_PERIOD = datetime.timedelta(seconds=20)
    TMDB_WINDOW_MAX_REQUESTS = 40

    ITUNES_NAME = 'iTunes'
    ITUNES_REQUEST_INDEX = 1
    ITUNES_WINDOW_TIME_PERIOD = datetime.timedelta(minutes=1)
    ITUNES_WINDOW_MAX_REQUESTS = 20

    ROTTEN_TOMATOES_NAME = 'Rotten Tomatoes'
    ROTTEN_TOMATOES_REQUEST_INDEX = 2

    # Values not specified in available docs. Not using Rotten Tomatoes
    # at this time

    ROTTEN_TOMATOES_WINDOW_TIME_PERIOD = datetime.timedelta(minutes=1)
    ROTTEN_TOMATOES_WINDOW_MAX_REQUESTS = 20

    UNLIMITED = Messages.get_msg(Messages.UNLIMITED)

    _logger = None
    _instance = None

    def __init__(self):
        # type: () -> None
        """

        """
        super().__init__()
        JsonUtils._logger = module_logger.getChild(type(self).__name__)

    @staticmethod
    def get_instance():
        # type: () -> JsonUtils
        """
            Returns the singleton instance of JsonUtils

        :return:
        """
        if JsonUtils._instance is None:
            JsonUtils._instance = JsonUtils()
        return JsonUtils._instance

    @staticmethod
    def get_cached_json(url,  # type; str
                        movie_id=None,  # type: Union[str, int, None]
                        error_msg=None,  # type: Union[str, int, None]
                        source=None,  # type: Union[str, None]
                        dump_results=False,  # type: bool
                        dump_msg='',  # type: str
                        headers=None,  # type: Union[dict, None]
                        params=None,  # type: Union[dict, None]
                        timeout=3.0  # type: int
                        ):
        # type: (...) -> (int, str)
        """
            Attempt to get cached JSON movie information before using the JSON calls
            to get it remotely.

            Any information not in the cache will be placed into it after successfully
            reading it.
        :param url:
        :param movie_id:
        :param error_msg:
        :param source:
        :param dump_results:
        :param dump_msg:
        :param headers:
        :param params:
        :param timeout:
        :return:
        """

        if headers is None:
            headers = {}

        if params is None:
            params = {}

        trailer_data = None
        status = 0
        if Settings.is_use_tmdb_cache():
            start = datetime.datetime.now()
            trailer_data = Cache.read_tmdb_cache_json(
                movie_id, source, error_msg=error_msg)
            status = 0
            stop = datetime.datetime.now()
            read_time = stop - start
            Statistics.add_json_read_time(int(read_time.microseconds / 10000))
            # if JsonUtils._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            #    JsonUtils._logger.debug_extra_verbose('json cache read time:',
            #                                          read_time.microseconds / 10000,
            #                                          'ms')
            if trailer_data is not None:
                trailer_data[Movie.CACHED] = True

        if trailer_data is None:
            status, trailer_data = JsonUtils.get_json(url, dump_results=dump_results,
                                                      dump_msg=dump_msg,
                                                      headers=headers,
                                                      error_msg=error_msg,
                                                      params=params,
                                                      timeout=timeout)
            if ((status == 0 or status == 200) and trailer_data is not None
                    and Settings.is_use_tmdb_cache()):
                Cache.write_tmdb_cache_json(movie_id, source, trailer_data)

        if trailer_data is None and status == 0:
            status = -1
        return status, trailer_data


# Force initialization of config_logger
JsonUtils.get_instance()
