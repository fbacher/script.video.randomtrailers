# -*- coding: utf-8 -*-

"""
Created on Feb 11, 2019

@author: fbacher
"""

from common.imports import *
from .__init__ import *

APPLE_URL_PREFIX = 'http://trailers.apple.com'
APPLE_REQUEST_LIMIT = 20  # Documented limit is 20 / minute
ROTTEN_TOMATOES_URL_PREFIX = 'api.rottentomatoes.com'
YOUTUBE_URL_PREFIX = 'plugin://plugin.video.youtube/play/?video_id='
# DEPRECATED plugin://plugin.video.youtube/?action=play_video&videoid=

VIMEO_URL_PREFIX: Final[str] = 'https://vimeo.com/'
YDSPROXY = None

TMDB_TRAILER_CACHE_FILE_PREFIX = 'tmdb_'

# Just use the generated apple movie id
APPLE_TRAILER_CACHE_FILE_PREFIX = 'appl_'

TFH_TRAILER_CACHE_FILE_PREFIX = 'tfh_'

YOUTUBE_URL: Final[str] = 'https://youtu.be/'


class iTunes:
    """
        Defines constants that apply to iTunes
    """
    # "Coming Soon|Just Added|Popular|Exclusive|All"
    COMING_SOON: Final[int] = 0
    JUST_ADDED: Final[int] = 1
    POPULAR: Final[int] = 2
    EXCLUSIVE: Final[int] = 3
    ALL: Final[int] = 4

    COMING_SOON_URL: Final[str] = '/trailers/home/feeds/studios.json'
    JUST_ADDED_URL: Final[str] = '/trailers/home/feeds/just_added.json'
    POPULAR_URL: Final[str] = '/trailers/home/feeds/most_pop.json'
    EXCLUSIVE_URL: Final[str] = '/trailers/home/feeds/exclusive.json'
    ALL_URL: Final[str] = '/trailers/home/feeds/studios.json'

    TRAILER_BASE_URL: Final[str] = 'https://trailers.apple.com'
    BASE_IMAGE_URL: Final[str] = 'http://image.tmdb.org/t/p/'

    _trailerForTypeMap: Final[Dict[int, str]] =\
        {COMING_SOON: COMING_SOON_URL,
         JUST_ADDED: JUST_ADDED_URL,
         POPULAR: POPULAR_URL,
         EXCLUSIVE: EXCLUSIVE_URL,
         ALL: ALL_URL}

    @staticmethod
    def get_url_for_trailer_type(trailer_type: int) -> str:
        url: str = iTunes._trailerForTypeMap.get(trailer_type, None)
        return url


class TMDbConstants:

    URL_PREFIX: Final[str] = 'http://api.themoviedb.org'
    # Works for all ids: TMDb, IMDb, etc. Works because ids have different
    # formats: tt<imdb>
    FIND_URL: Final[str] = 'http://api.themoviedb.org/3/find/'
    SEARCH_URL: Final[str] = 'https://api.themoviedb.org/3/search/movie'
    DISCOVER_ALL_URL: Final[str] = 'http://api.themoviedb.org/3/discover/movie'
    DISCOVER_TRAILER_URL: Final[str] = 'https://api.themoviedb.org/3/movie/'
    IMAGE_BASE_URL: Final[str] = 'http://image.tmdb.org/t/p/'


class TFHConstants:
    TFH_TRAILER_PLAYLIST_URL: Final[str] = \
        'https://www.youtube.com/user/trailersfromhell/videos'