"""
Created on Apr 5, 2019

@author: Frank Feuerbacher
"""

from common.imports import *

import datetime
import glob
import simplejson as json
import os
import random
import re
import sys

import youtube_dl

from common.constants import Constants, Movie, MovieType
from common.logger import (LazyLogger, Trace)
from common.monitor import Monitor
from common.exceptions import AbortException
from common.rating import WorldCertifications
from common.settings import Settings

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)

#  Intentional delay (seconds) to help prevent TOO_MANY_REQUESTS
YOUTUBE_DOWNLOAD_INFO_DELAY = (5.0, 10.0)
ITUNES_DOWNLOAD_INFO_DELAY = (1.0, 3.0)
TFH_INFO_DELAY = (1.0, 4.1)
DOWNLOAD_INFO_DELAY_BY_SOURCE = {Movie.ITUNES_SOURCE: ITUNES_DOWNLOAD_INFO_DELAY,
                                 Movie.TMDB_SOURCE: YOUTUBE_DOWNLOAD_INFO_DELAY,
                                 Movie.TFH_SOURCE: TFH_INFO_DELAY,
                                 Movie.LIBRARY_SOURCE: YOUTUBE_DOWNLOAD_INFO_DELAY,
                                 Movie.FOLDER_SOURCE: YOUTUBE_DOWNLOAD_INFO_DELAY}
#  Intentional delay (seconds) to help prevent TOO_MANY_REQUESTS
YOUTUBE_DOWNLOAD_VIDEO_DELAY = (30.0, 120.0)
ITUNES_DOWNLOAD_VIDEO_DELAY = (10.0, 60.0)
DOWNLOAD_VIDEO_DELAY_BY_SOURCE = {Movie.ITUNES_SOURCE: ITUNES_DOWNLOAD_VIDEO_DELAY,
                                  Movie.TMDB_SOURCE: YOUTUBE_DOWNLOAD_VIDEO_DELAY,
                                  Movie.TFH_SOURCE: YOUTUBE_DOWNLOAD_VIDEO_DELAY,
                                  Movie.LIBRARY_SOURCE: YOUTUBE_DOWNLOAD_VIDEO_DELAY,
                                  Movie.FOLDER_SOURCE: YOUTUBE_DOWNLOAD_VIDEO_DELAY}

PYTHON_PATH = Constants.YOUTUBE_DL_ADDON_LIB_PATH
PYTHON_EXEC = sys.executable
YOUTUBE_DL_PATH = os.path.join(Constants.BACKEND_ADDON_UTIL.PATH,
                               'resources', 'lib', 'shell', 'youtube_dl_main.py')
# Delay two hours after encountering 429 (too many requests)
RETRY_DELAY = datetime.timedelta(0, float(60 * 2))


class VideoDownloader:
    """
    Downloads Videos, or video information for individual or playlists. Uses
    embedded youtube-dl to accomplish this.

    """
    DOWNLOAD_ERROR = 10
    BLOCKED_ERROR = 11

    # Initialize to a year ago
    # Is an estimate of when the Too Many Requests will expire
    _too_many_requests_timestamp = datetime.datetime.now() - datetime.timedelta(365)
    #
    # Records when Too Many Requests began. Reset to None once successful.
    # Used to help improve estimate of how long to quarantine.
    #
    # For each use an instance must be created. Then one of
    # get_video
    # get_info
    # or get_tfh_index
    # is called.
    # In addition, check_too_many_requests checks to see if any recent '429'
    # errors have been returned indicating that there have been TOO MANY REQUESTS
    # to the site. The site is not recorded here, but at this point it is either
    # youtube or iTunes and I have yet to see iTunes return it.
    # The amount of time that you must wait after a TOO_MANY_REQUESTS error is not
    # specified, but probably measured in one or more days.
    #
    # If you search for youtube-dl 429 you will get to a workaround that involves
    # you playing a youtube video from your browser, then exporting your youtube
    # cookies and using that as input youtube-dl. There is a hidden option in
    # settings.xml, youtube_dl_cookie_path, that you can set to point to your
    # cookie file. Hopefully this is not needed. In my experience it is only
    # with repeated testing, clearing caches and, in particular, clearing the
    # TFH cache that would cause the 429 error.

    _initial_tmr_timestamp = None
    _last_youtube_request_timestamp: datetime.datetime = datetime.datetime(
        1990, 1, 1)
    _last_itunes_request_timestamp: datetime.datetime = datetime.datetime(
        1990, 1, 1)
    _logger = module_logger.getChild('VideoDownloader')

    def __init__(self) -> None:
        """

        """
        clz = VideoDownloader

        self._command_process = None
        self._stderr_thread = None
        self._stdout_thread = None
        self._error = 0
        self._stdout_text = None
        self.debug_lines: List[str] = []
        self.warning_lines: List[str] = []
        self.error_lines: List[str] = []
        self._download_eta = None
        self._download_finished = False

    @staticmethod
    def get_youtube_wait_seconds() -> ClassVar[datetime.timedelta]:
        """
          Returns how many seconds should be waited (after a 429 error) before
          trying another download.
        """
        clz = VideoDownloader

        seconds_to_wait = (clz._too_many_requests_timestamp
                           - datetime.datetime.now()).total_seconds()
        if seconds_to_wait < 0:
            seconds_to_wait = 0
        return seconds_to_wait

    @classmethod
    def check_too_many_requests(cls, url: str, source: str) -> int:
        """
          Returns 429 if a 429 error has occurred within RETRY_DELAY seconds.
          Otherwise, returns 0.
        """
        if source == Movie.ITUNES_SOURCE:
            return 0

        if cls._too_many_requests_timestamp > datetime.datetime.now():
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                expiration_time = datetime.datetime.strftime(
                    cls._too_many_requests_timestamp,
                    '%a, %d %b %Y %H:%M:%S')
                cls._logger.debug_extra_verbose(
                    f'Blocking download of {url} due to TOO MANY REQUESTS (429)'
                    f' since: {expiration_time}')
                return 429
        return 0

    @classmethod
    def wait_if_too_busy(cls, source: str, video: bool):
        if video:
            delay_range = DOWNLOAD_VIDEO_DELAY_BY_SOURCE[source]
        else:
            delay_range = DOWNLOAD_INFO_DELAY_BY_SOURCE[source]
        delay = cls.get_delay(delay_range)
        # min_time_between_requests = datetime.timedelta(seconds=10.0)
        if source == Movie.ITUNES_SOURCE:
            waited: datetime.timedelta = (
                datetime.datetime.now() - cls._last_itunes_request_timestamp)
        else:
            waited: datetime.timedelta = (
                datetime.datetime.now() - cls._last_youtube_request_timestamp)
        time_to_wait = delay - waited.total_seconds()
        if time_to_wait > 0.0:
            Monitor.throw_exception_if_abort_requested(time_to_wait)
        if source == Movie.ITUNES_SOURCE:
            cls._last_itunes_request_timestamp = datetime.datetime.now()
        else:
            cls._last_youtube_request_timestamp = datetime.datetime.now()

    @classmethod
    def get_delay(cls, delay_range: Tuple[float, float]) -> float:
        lower = int(13 * delay_range[0])
        upper = int(13 * delay_range[1])
        return float(random.randint(lower, upper)) / 13.0

    def get_video(self, url: str, folder: str, movie_id: Union[int, str],
                  title: str, source: str) -> Tuple[int, Optional[MovieType]]:
        """
             Downloads a video from the given url into the given folder.

        :param url:      To download from
        :param folder:   To download to
        :param movie_id: To pass to youtube-dl to embed in the created file name
        :param title:    For logging
        :param source:   Movie source used to determine delay
        :return:
        """
        clz = VideoDownloader

        too_many_requests = clz.check_too_many_requests(url, source)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            clz._logger.debug_verbose(
                f'url: {url} Too Many Requests: {too_many_requests}')

        if too_many_requests != 0:
            return too_many_requests, None

        clz.wait_if_too_busy(source, True)
        # The embedded % fields are for youtube_dl to fill  in.

        template = os.path.join(folder, f'_rt_{movie_id}_%(title)s.%(ext)s')
        movie = None

        # Collect and respond to output from youtube-dl
        if source == Movie.ITUNES_SOURCE:
            parse_json_as_youtube = False
        else:
            parse_json_as_youtube = True
        video_logger = VideoLogger(self, url,
                                   parse_json_as_youtube=parse_json_as_youtube)
        try:
            ydl_opts = {
                'forcejson': 'true',
                'outtmpl': template,
                'updatetime': 'false',
                'logger': video_logger,
                'progress_hooks': [VideoDownloadProgressHook(self).status_hook]
            }
            # Optional cookie-file used to avoid youtube 429 errors (see
            # above).

            cookie_path = Settings.get_youtube_dl_cookie_path()
            if len(cookie_path) > 0 and os.path.exists(cookie_path):
                ydl_opts['cookiefile'] = cookie_path

            # Start download
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            while (video_logger.data is None and self._error == 0 and not
                    self._download_finished):
                Monitor.throw_exception_if_abort_requested(timeout=0.5)

            movie = video_logger.data
            if self._error == 0:
                trailer_file = os.path.join(folder, f'_rt_{movie_id}*')
                trailer_file = glob.glob(trailer_file)
                if trailer_file is not None:
                    if len(trailer_file) > 0:
                        trailer_file = trailer_file[0]
                    #
                    # Don't know why, but sometimes youtube_dl returns incorrect
                    # file extension

                    movie.setdefault(Movie.TRAILER, trailer_file)
                    if trailer_file != movie[Movie.TRAILER]:
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz._logger.debug_extra_verbose(
                                'youtube_dl gave incorrect file name:',
                                movie[Movie.TRAILER], 'changing to:',
                                trailer_file)

                        movie[Movie.TRAILER] = trailer_file

        except AbortException:
            self._error = 99
            movie = None
            to_delete = os.path.join(folder, f'_rt_{movie_id}*')
            to_delete = glob.glob(to_delete)
            for aFile in to_delete:
                try:
                    os.remove(aFile)
                except Exception as e:
                    pass
            reraise(*sys.exc_info())
        except Exception as e:
            if self._error == 0:
                self._error = 3
                clz._logger.exception(e)

        if self._error == 0 and movie is None:
            self._error = 1

        if self._error != 0:
            clz._logger.debug(
                f'Results for {title} url:{url} error: {self._error}')
            video_logger.log_debug()
            video_logger.log_warning()
            video_logger.log_error()
            movie = None
            to_delete = os.path.join(folder, f'_rt_{movie_id}*')
            to_delete = glob.glob(to_delete)
            for aFile in to_delete:
                try:
                    os.remove(aFile)
                except Exception as e:
                    pass

        Monitor.throw_exception_if_abort_requested()
        return self._error, movie

    def get_info(self, url: str, movie_source: str) -> Tuple[
            int, Optional[List[MovieType]]]:
        """
        Instead of downloading a video, get basic information about the video

        :param url: To get information from
        :param movie_source: Used to determine delay between requests
        :return: a dictionary (MovieType) from the json returned by site
        """
        clz = VideoDownloader
        trailer_info: Optional[List[MovieType]] = None

        clz.wait_if_too_busy(movie_source, False)
        too_many_requests = clz.check_too_many_requests(url, movie_source)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            clz._logger.debug_verbose(
                f'url: {url} Too Many Requests: {too_many_requests}')

        if too_many_requests != 0:
            return 429, None

        info_logger = TfhInfoLogger(self, url, parse_json_as_youtube=False)
        try:
            ydl_opts = {
                'forcejson': 'true',
                'skip_download': 'true',
                'logger': info_logger,
                'progress_hooks': [TrailerInfoProgressHook(self).status_hook]
            }
            cookie_path = Settings.get_youtube_dl_cookie_path()
            if len(cookie_path) > 0 and os.path.exists(cookie_path):
                ydl_opts['cookiefile'] = cookie_path

            Monitor.throw_exception_if_abort_requested()

            # Start Download

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Wait for download

            while info_logger.is_finished is None and self._error == 0:
                Monitor.throw_exception_if_abort_requested(timeout=0.5)

            if self._error == 0:
                trailer_info: List[MovieType] = info_logger.get_trailer_info()

        except AbortException:
            reraise(*sys.exc_info())

        except Exception as e:
            if self._error == 0:
                clz._logger.exception(e)
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    clz._logger.debug_verbose(
                        'Failed to download site info for:', url)
            trailer_info = None

        if self._error not in (0, 99):
            clz._logger.debug('Results for url:', url, 'error:', self._error)
            info_logger.log_debug()
            info_logger.log_warning()
            info_logger.log_error()

        Monitor.throw_exception_if_abort_requested()
        return 0, trailer_info

    def get_tfh_index(self, url: str, trailers_to_download: str,
                      trailer_handler) -> int:
        """
        Fetches all of the urls in the Trailers From Hell playlist. Note that
        the entire list is well over a thousand and that indiscriminate
        downloading can get the dreaded "429" code from Youtube (Too Many
        Requests) which will cause downloads to be denied for an extended
        period of time and potentially banned. To help prevent this
        reducing how many trailers are requested at a time, caching and
        throttling of requests should be used.

        :param url: points to playlist
        :param trailers_to_download: Specifies the index of which trailers to get
                                     url of. An empty list means get all urls.
        :param trailer_handler: Call back to DiscoverTFHMovies to process each
                returned entry as it occurs.
        :return:
        """

        clz = VideoDownloader

        clz.wait_if_too_busy(Movie.TFH_SOURCE, False)
        too_many_requests = clz.check_too_many_requests(url, Movie.TFH_SOURCE)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            clz._logger.debug_verbose(
                f'url: {url} Too Many Requests: {too_many_requests}')

        if too_many_requests != 0:
            return too_many_requests

        # Would prefer to specify a list of playlist_items in order
        # to control rate of fetches (and hopefully avoid TOO_MANY REQUESTS)
        # But.. when you use playlist_items you do NOT get the total number
        # of items in the playlist as part of the results. Further, if you
        # try to get a playlist item out of range, there is no error, nothing.
        #
        # Therefore, reluctantly not using playlist_items and getting everything
        # at once (although no downloaded trailers).

        tfh_index_logger = TfhIndexLogger(self, trailer_handler, url)
        ydl_opts = {
            'forcejson': True,
            'noplaylist': False,
            # 'extract_flat': 'in_playlist',
            'skip_download': True,
            'logger': tfh_index_logger,
            'sleep_interval': 10,
            'max_sleep_interval': 240,
            #  'playlist_items': trailers_to_download,
            'playlistrandom': True,
            'progress_hooks': [TFHIndexProgressHook(self).status_hook],
            # 'debug_printtraffic': True
        }
        cookie_path = Settings.get_youtube_dl_cookie_path()
        if len(cookie_path) > 0 and os.path.exists(cookie_path):
            ydl_opts['cookiefile'] = cookie_path

        cache_dir = Settings.get_youtube_dl_cache_path()
        if len(cache_dir) > 0 and os.path.exists(cache_dir):
            ydl_opts['cachedir'] = cache_dir

        if len(trailers_to_download) > 10:
            ydl_opts['playlist_items'] = trailers_to_download

        Monitor.throw_exception_if_abort_requested()
        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        except AbortException:
            reraise(*sys.exc_info())

        except Exception as e:
            if self._error == 0:
                clz._logger.exception(e)

        if self._error not in (0, 99):
            clz._logger.debug('Results for url:', url, 'error:', self._error)
            tfh_index_logger.log_error()
            tfh_index_logger.log_debug()
            tfh_index_logger.log_warning()

        Monitor.throw_exception_if_abort_requested()
        return self._error


class BaseYDLogger:
    """
    Intercepts the output from YouTubeDL
      - to log
      - to scan and respond to events, such as json-text or diagnostic msgs
    """

    logger = None

    def __init__(self, downloader: VideoDownloader, url: str,
                 parse_json_as_youtube: bool = True):
        clz = BaseYDLogger
        clz.logger = module_logger.getChild(clz.__name__)
        self.debug_lines: List[str] = []
        self.warning_lines: List[str] = []
        self.error_lines: List[str] = []
        self._downloader: VideoDownloader = downloader
        self.index = 0
        self.total = 0
        self.url = url
        self._parse_json_as_youtube = parse_json_as_youtube
        self._parsed_movie = None
        self.raw_data: Optional[MovieType] = None

    def debug(self, line: str) -> None:
        """
        {"_type": "url", "url": "vYALYAuD5Fw", "ie_key": "Youtube",
        "id": "vYALYAuD5Fw", "title": "Larry Karaszewski on ROAD TO SALINA"}
                                                   [download] Downloading video 14 of 1448
                                                   {"_type": "url", "url":
                                                   "dZzFqtlamV4", "ie_key": "Youtube",
                                                   "id": "dZzFqtlamV4", "title": "Joe
                                                   Dante on HALF HUMAN"}
        [download] Downloading video 15 of 1448

        {"id": "nrExo_KJROc", "uploader": "Trailers From Hell",
            "uploader_id": "trailersfromhell",
            "uploader_url": "http://www.youtube.com/user/trailersfromhell",
            "channel_id": "UCg7Mllu8AnTjlZ4Vu1FNdjQ",
            "channel_url": "http://www.youtube.com/channel/UCg7Mllu8AnTjlZ4Vu1FNdjQ"
           "upload_date": "20200908", "license": null, "creator": null,
          "title": "Brian Trenchard-Smith on ONCE UPON A TIME IN HOLLYWOOD",
           "alt_title": null,
            "thumbnails": [{"url":
            "https://i.ytimg.com/vi/nrExo_KJROc/hqdefault.jpg?sqp
            =-oaymwEYCKgBEF5IVfKriqkDCwgBFQAAiEIYAXAB&rs
            =AOn4CLCPHEof66nqx4GxE04sOUocr9WywA",
             "width": 168, "height": 94, "resolution": "168x94", "id": "0"},
             {"url": "https://i.ytimg.com/vi/nrExo_KJROc/hqdefault.jpg?sqp
             =-oaymwEYCMQBEG5IVfKriqkDCwgBFQAAiEIYAXAB&rs=AOn4CLAm
             -CXcCCu0LATG_R347wBxBQj4BQ",
               "width": 196, "height": 110, "resolution": "196x110", "id": "1"},
             {"url": "https://i.ytimg.com/vi/nrExo_KJROc/hqdefault.jpg?sqp
             =-oaymwEZCPYBEIoBSFXyq4qpAwsIARUAAIhCGAFwAQ==&rs
             =AOn4CLAhW2AcVqdWYiPMZuKENgiCO0gykQ",...
        :return:
        """
        clz = BaseYDLogger
        if Monitor.is_abort_requested():
            self._downloader._error = 99
            # Kill YoutubeDL
            Monitor.throw_exception_if_abort_requested()

        self.debug_lines.append(line)
        if line.startswith('[download] Downloading video'):
            try:
                _, index_str, total_str = re.split(r'[^0-9]+', line)
                self.index = int(index_str)
                self.total = int(total_str)
            except Exception as e:
                clz.logger.exception()
                self._downloader._error = 1

        # if line.startswith('{"_type":'):
        #     try:
        #         data = json.loads(line)
        #         self._trailer_handler(data)
        #     except Exception as e:
        #         clz.logger.exception()
        if line.startswith('{"id":'):
            try:
                self.raw_data = json.loads(line)
                if self._parse_json_as_youtube:
                    self._parsed_movie = populate_youtube_movie_info(self.raw_data,
                                                                     self.url)
                # self._trailer_handler(movie_data)
            except Exception as e:
                clz.logger.exception()
                self._downloader._error = 2

    def warning(self, line: str) -> None:
        if Monitor.is_abort_requested():
            self._downloader._error = 99
            # Kill YoutubeDL
            Monitor.throw_exception_if_abort_requested()

        if 'merged' in line:
            # str: Requested formats are incompatible for merge and will be merged into
            # mkv.
            pass
        else:
            self.warning_lines.append(line)

    def error(self, line: str) -> None:
        if Monitor.is_abort_requested():
            self._downloader._error = 99
            # Kill YoutubeDL
            Monitor.throw_exception_if_abort_requested()

        clz = BaseYDLogger
        if 'Error 429' in line:
            self._downloader._error = 429
            self._downloader._initial_tmr_timestamp = datetime.datetime.now()
            self._downloader._too_many_requests_timestamp = (
                datetime.datetime.now() + RETRY_DELAY)

            clz.logger.info(
                'Abandoning download. Too Many Requests')
        # str: ERROR: (ExtractorError(...), 'wySw1lhMt1s: YouTube said: Unable
        # to extract video data')
        elif 'Unable to extract' in line:
            self._downloader._error = VideoDownloader.DOWNLOAD_ERROR
        elif 'blocked' in line:
            self._downloader._error = VideoDownloader.BLOCKED_ERROR
        else:
            self.error_lines.append(line)

    def get_debug(self) -> List[str]:
        """
        {"_type": "url", "url": "vYALYAuD5Fw", "ie_key": "Youtube",
        "id": "vYALYAuD5Fw", "title": "Larry Karaszewski on ROAD TO SALINA"}
                                                   [download] Downloading video 14 of 1448
                                                   {"_type": "url", "url":
                                                   "dZzFqtlamV4", "ie_key": "Youtube",
                                                   "id": "dZzFqtlamV4", "title": "Joe
                                                   Dante on HALF HUMAN"}
                                                   [download] Downloading video 15 of 1448

        :return:
        """
        return self.debug_lines

    def get_warning(self) -> List[str]:
        return self.warning_lines

    def get_error(self) -> List[str]:
        return self.error_lines

    def log_lines(self, lines: List[str], label: str) -> None:
        if self._downloader._error == 99:
            return

        clz = BaseYDLogger
        text = '\n'.join(lines)
        if clz.logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz.logger.debug_extra_verbose(label, text)

    def log_debug(self) -> None:
        self.log_lines(self.debug_lines, 'DEBUG:')

    def log_error(self) -> None:
        self.log_lines(self.error_lines, 'ERROR:')

    def log_warning(self) -> None:
        self.log_lines(self.warning_lines, 'WARNING:')


class TfhIndexLogger(BaseYDLogger):
    logger = None

    def __init__(self, downloader: VideoDownloader,
                 trailer_handler, url: str):
        super().__init__(downloader, url, parse_json_as_youtube=True)
        clz = TfhIndexLogger
        clz.logger = module_logger.getChild(clz.__name__)
        self._trailer_handler = trailer_handler

    def debug(self, line: str) -> None:
        """
             :return:
        """
        super().debug(line)
        clz = TfhIndexLogger
        if self._parsed_movie is not None and self._downloader._error != 0:
            try:
                if self._parsed_movie.get(Movie.YOUTUBE_ID) is None:
                    clz.logger.debug('Missing YOUTUBE_ID\n',
                                     json.dumps(self._parsed_movie,
                                                encoding='utf-8',
                                                ensure_ascii=False,
                                                indent=3, sort_keys=True))
                self._trailer_handler(self._parsed_movie)
                VideoDownloader.wait_if_too_busy(Movie.TFH_SOURCE, False)
            except Exception as e:
                clz.logger.exception()


class VideoLogger(BaseYDLogger):
    logger = None

    def __init__(self, downloader: VideoDownloader, url: str,
                 parse_json_as_youtube: bool):
        super().__init__(downloader, url,
                         parse_json_as_youtube=parse_json_as_youtube)
        clz = TfhIndexLogger
        clz.logger = module_logger.getChild(clz.__name__)
        self.data = None

    def debug(self, line: str) -> None:
        """
        :return:
        """
        super().debug(line)
        clz = VideoLogger

        if self._parse_json_as_youtube:
            self.data = self._parsed_movie
        else:
            self.data = self.raw_data


class TfhInfoLogger(BaseYDLogger):
    logger = None

    def __init__(self, downloader: VideoDownloader, url: str,
                 parse_json_as_youtube: bool = False):
        super().__init__(downloader, url, parse_json_as_youtube=parse_json_as_youtube)
        clz = TfhIndexLogger
        clz.logger = module_logger.getChild(clz.__name__)
        self._trailer_info: List[MovieType] = []
        self.is_finished = False

    def get_trailer_info(self) -> List[MovieType]:
        return self._trailer_info

    def debug(self, line: str) -> None:
        """
             :return:
        """
        super().debug(line)
        clz = TfhIndexLogger

        if self.raw_data is not None:
            self._trailer_info.append(self.raw_data)

        # How do we know when finished?


def populate_youtube_movie_info(movie_data: MovieType, url: str) -> MovieType:
    """
        Creates a Kodi MovieType from the data returned from Youtube.
        Currently only used for TFH movies.

        Not used for iTunes movies. Rely on DiscoverItunesMovies for that.

        TFH trailers are titled: <reviewer> on <MOVIE_TITLE_ALL_CAPS>
        Here we can try to get just the movie title and then look up
        a likely match in TMDB (with date, and other info).
        TFH may not like us changing/guessing the movie title, however.
    """

    movie: Union[MovieType, None] = None
    dump_json = False
    missing_keywords = []
    try:
        trailer_id = movie_data.get('id')
        if trailer_id is None:
            missing_keywords.append('id')
            dump_json = True
        if movie_data.get('title') is None:
            missing_keywords.append('title')
            dump_json = True
        title = movie_data.get('title', 'missing title')
        # title_segments = title.split(' on ')
        # real_title_index = len(title_segments) - 1
        # movie_title = title_segments[real_title_index]
        movie_title = title
        trailer_url = 'https://youtu.be/' + trailer_id
        if movie_data.get('upload_date') is None:
            missing_keywords.append('upload_date')
            dump_json = True
            movie_data['upload_date'] = datetime.datetime.now(
            ).strftime('%Y%m%d')
        upload_date = movie_data.get('upload_date', '19000101')  # 20120910
        year = upload_date[0:4]
        year = int(year)
        if movie_data.get('thumbnail') is None:
            missing_keywords.append('thumbnail')
            dump_json = True
        thumbnail = movie_data.get('thumbnail', '')

        original_language = ''
        if movie_data.get('description') is None:
            missing_keywords.append('description')
            dump_json = True
        description = movie_data.get('description', '')
        country_id = Settings.get_country_iso_3166_1().lower()
        certifications = WorldCertifications.get_certifications(country_id)
        unrated_id = certifications.get_unrated_certification().get_preferred_id()
        trailers_in_playlist = movie_data.get('n_entries', 1)
        playlist_index = movie_data.get('playlist_index', 0)
        # Tags might have some good stuff, but very unorganized and full of junk
        # tags: Dict[str, str] = movie_data.get('tags', {})
        if movie_data.get('average_rating') is None:
            missing_keywords.append('average_rating')
            dump_json = True
        if movie_data.get('duration') is None:
            missing_keywords.append('duration')
            dump_json = True
        movie = {Movie.SOURCE: 'unknown',
                 Movie.YOUTUBE_ID: trailer_id,
                 Movie.TITLE: movie_title,
                 Movie.YEAR: year,
                 Movie.ORIGINAL_LANGUAGE: original_language,
                 Movie.TRAILER: trailer_url,
                 Movie.PLOT: description,
                 Movie.THUMBNAIL: thumbnail,
                 Movie.DISCOVERY_STATE: Movie.NOT_FULLY_DISCOVERED,
                 Movie.MPAA: unrated_id,
                 Movie.ADULT: False,
                 Movie.RATING: movie_data.get('average_rating', 0.0),
                 # Kodi measures in seconds
                 Movie.RUNTIME: movie_data.get('duration', 1.0) * 60
                 }
        if playlist_index is not None:
            movie[Movie.YOUTUBE_PLAYLIST_INDEX] = playlist_index
            movie[Movie.YOUTUBE_TRAILERS_IN_PLAYLIST] = trailers_in_playlist
    except Exception as e:
        dump_json = True
        module_logger.exception(e)
    if dump_json:
        if module_logger.isEnabledFor(LazyLogger.DEBUG):
            module_logger.debug('Missing json data. Missing keywords:',
                                ', '.join(missing_keywords), 'URL:', url,
                                '\njson:',
                                json.dumps(movie_data,
                                           encoding='utf-8',
                                           ensure_ascii=False,
                                           indent=3, sort_keys=True))
    return movie


class BaseInfoHook:
    _logger = module_logger.getChild('BaseInfoHook')

    def __init__(self, downloader: VideoDownloader):
        self.error_lines: List[str] = []
        self.warning_lines: List[str] = []
        self.debug_lines: List[str] = []
        self._download_eta: Optional[int] = None
        self._error: int = 0
        self._downloader = downloader

    def status_hook(self, status: Dict[str, str]) -> None:
        clz = BaseInfoHook
        if Monitor.is_abort_requested():
            self._downloader._error = 99
            # Kill YoutubeDL
            Monitor.throw_exception_if_abort_requested()

        status_str = status.get('status', 'missing status')
        if status_str is None:
            clz._logger.debug('Missing status indication')
        elif status_str == 'downloading':
            self._download_eta = status.get('eta', 0)  # In seconds
            self._downloader._download_eta = self._download_eta
        elif status_str == 'error':
            clz._logger.error('Status:', str(status))
            self.error_lines.append('Error downloading')
            self._error = VideoDownloader.DOWNLOAD_ERROR
            self._downloader._error = self._error
        elif status_str == 'finished':
            filename = status.get('filename')
            tmpfilename = status.get('tmpfilename')
            downloaded_bytes = status.get('downloaded_bytes')
            total_bytes = status.get('total_bytes')
            total_bytes_estimate = status.get('total_bytes_estimate')
            elapsed = status.get('elapsed')
            eta = status.get('eta')
            speed = status.get('speed')
            fragment_index = status.get('fragment_index')
            fragment_count = status.get('fragment_count')
            self._downloader._download_finished = True

            clz._logger.debug('Finished')


class TrailerInfoProgressHook(BaseInfoHook):
    _logger = module_logger.getChild('TrailerInfoProgressHook')

    def __init__(self, downloader: VideoDownloader):
        super().__init__(downloader)

    def status_hook(self, status: Dict[str, str]) -> None:
        clz = TrailerInfoProgressHook
        super().status_hook(status)


class TFHIndexProgressHook(BaseInfoHook):
    _logger = module_logger.getChild('TFHIndexProgressHook')

    def __init__(self, downloader: VideoDownloader):
        super().__init__(downloader)

    def status_hook(self, status: Dict[str, str]) -> None:
        clz = TFHIndexProgressHook
        super().status_hook(status)


class VideoDownloadProgressHook(BaseInfoHook):
    _logger = module_logger.getChild('VideoDownloadProgressHook')

    def __init__(self, downloader: VideoDownloader):
        super().__init__(downloader)

    def status_hook(self, status: Dict[str, str]) -> None:
        clz = VideoDownloadProgressHook
        super().status_hook(status)
