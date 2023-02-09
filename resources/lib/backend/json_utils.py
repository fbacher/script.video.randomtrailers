# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

from common.imports import *
from backend.json_utils_basic import JsonUtilsBasic
from common.logger import *
from .__init__ import *

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class JsonUtils(JsonUtilsBasic):

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

    _logger: BasicLogger = None

    @classmethod
    def class_init(cls) -> None:
        """

        """
        super().class_init()
        cls._logger = module_logger.getChild(cls.__name__)

'''
    @staticmethod
    def get_cached_tmdb_movie(url: str,
                        tmdb_id: Union[str, int] = None,
                        error_msg: Union[str, int] = None,
                        source: str = None,
                        dump_results: bool = False,
                        dump_msg: str = '',
                        headers: Dict[str, Any] = None,
                        params: Dict[str, Any] = None,
                        timeout: float = 3.0
                        ) -> (int, str):
        """
            Attempt to get cached JSON movie information before using the JSON calls
            to get it remotely.

            Any information not in the cache will be placed into it after successfully
            reading it.
        :param url:
        :param tmdb_id:
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
                tmdb_id, source, error_msg=error_msg)
            status = 0
            stop = datetime.datetime.now()
            read_time = stop - start
            Statistics.add_json_read_time(int(read_time.microseconds / 10000))
            # if JsonUtils._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            #    JsonUtils._logger.debug_extra_verbose(f'json cache read time: '
            #                                          f'{read_time.microseconds / 10000}'
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
                Cache.write_tmdb_cache_json(tmdb_id, source, trailer_data)

        if trailer_data is None and status == 0:
            status = -1
        return status, trailer_data
'''


# Force initialization of config_logger
JsonUtils.class_init()
