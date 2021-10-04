# -*- coding: utf-8 -*-
"""
Created on 9/30/21

@author: Frank Feuerbacher
"""
import datetime
import threading

from common.imports import *

from common.logger import LazyLogger
from cache.base_reverse_index_cache import BaseReverseIndexCache

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TMDbJsonCache(BaseReverseIndexCache):
    """
    Provides a cache index of all of the json files for TMDb movies.

    When a movie database (Itunes, TFH, local library) is missing a trailer
    or some other info, we use TMDb to supply the missing information.

    All of the TMDb json files are kept in TMDb directories and shared
    among the users of it. This cache provides:
       * A map of the TMDb id for a given source id (source can be TFH,
         Library, Itunes, TMDb)
       * A reverse mapping from TMDb id to source_id. This is accomplished
         by prefixing the source id with an underscore '_'. Since TMDb ids
         are integers, we can distinguish between the two.

    """

    CACHE_PATH: str
    _lock = threading.RLock()
    _last_saved = datetime.datetime.now()
    _unsaved_changes: int = 0
    _logger = None

    _cache: Dict[str, str] = {}
    _reverse_cache: Dict[str, str] = {}

    @classmethod
    def class_init(cls, cache_name: str = None) -> None:
        """
        :return:
        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(type(cls).__name__)

        super().class_init('tmdb_json_cache')


TMDbJsonCache.class_init()
