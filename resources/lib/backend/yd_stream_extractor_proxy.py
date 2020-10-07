"""
Created on Apr 5, 2019

@author: Frank Feuerbacher
"""

from common.imports import *

import datetime
import glob
import subprocess
from subprocess import CalledProcessError
import simplejson as json
import os
import sys
import re
import threading

import youtube_dl

from common.constants import Constants, Movie, MovieType
from common.logger import (LazyLogger, Trace)
from common.monitor import Monitor
from common.exceptions import AbortException
from common.rating import WorldCertifications
from common.settings import Settings

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)

#  Intentional delay (seconds) to help prevent TOO_MANY_REQUESTS
DELAY = 5.0
PYTHON_PATH = Constants.YOUTUBE_DL_ADDON_LIB_PATH
PYTHON_EXEC = sys.executable
YOUTUBE_DL_PATH = os.path.join(Constants.BACKEND_ADDON_UTIL.PATH,
                               'resources', 'lib', 'shell', 'youtube_dl_main.py')
# Delay one hour after encountering 429 (too many requests)
RETRY_DELAY = datetime.timedelta(0, float(60 * 2))


class YDStreamExtractorProxy:
    """

    """
    DOWNLOAD_ERROR = 10
    BLOCKED_ERROR = 11

    # Initialize to a year ago
    # Is an estimate of when the Too Many Requests will expire
    _too_many_requests_timestamp = datetime.datetime.now() - datetime.timedelta(365)
    #
    # Records when Too Many Requests began. Reset to None once successful.
    # Used to help improve estimate of how long to quarantine.

    _initial_tmr_timestamp = None
    _logger = module_logger.getChild('YDStreamExtractorProxy')

    def __init__(self) -> None:
        """

        """
        clz = YDStreamExtractorProxy

        self._command_process = None
        self._stderr_thread = None
        self._stdout_thread = None
        self._error = 0
        self._stdout_text = None
        self.debug_lines: List[str] = []
        self.warning_lines: List[str] = []
        self.error_lines: List[str] = []
        self._download_eta = None

    @staticmethod
    def get_youtube_wait_seconds() -> ClassVar[datetime.timedelta]:
        clz = YDStreamExtractorProxy

        seconds_to_wait = (clz._too_many_requests_timestamp
                           - datetime.datetime.now()).total_seconds()
        if seconds_to_wait < 0:
            seconds_to_wait = 0
        return seconds_to_wait

    @classmethod
    def check_too_many_requests(cls, url: str) -> int:
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

    def get_video(self, url, folder, movie_id):
        # type: (str, str, Union[int, str]) -> Tuple[int, Optional[MovieType]]
        """

        :param url:
        :param folder:
        :param movie_id:
        :return:
        """
        clz = YDStreamExtractorProxy

        if clz.check_too_many_requests(url) != 0:
            return 429, None

        # The embedded % fields are for youtube_dl to fill  in.

        template = os.path.join(folder, f'_rt_{movie_id}_%(title)s.%(ext)s')
        movie = None
        video_logger = TfhVideoLogger(self, url)
        try:
            ydl_opts = {
                'forcejson': 'true',
                'outtmpl': template,
                'updatetime': 'false',
                'logger': video_logger,
                'progress_hooks': [VideoDownloadProgressHook(self).status_hook],
                'cookiefile': '/home/fbacher/youtube.cookies'
            }

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            while video_logger.data is None and self._error == 0:
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

                    if trailer_file != movie[Movie.TRAILER]:
                        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                            clz._logger.debug_extra_verbose(
                                'youtube_dl gave incorrect file name:',
                                movie[Movie.TRAILER], 'changing to:',
                                trailer_file)

                        movie[Movie.TRAILER] = trailer_file

        except AbortException:
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
            clz._logger.debug('Results for url:', url, 'error:', self._error)
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

        Monitor.throw_exception_if_abort_requested(timeout=DELAY)
        return self._error, movie

    def get_info(self, url: str) -> Tuple[int, Optional[List[MovieType]]]:
        """

        :param url:
        :return:
        """
        clz = YDStreamExtractorProxy
        trailer_info: Optional[List[MovieType]] = None

        if clz.check_too_many_requests(url) != 0:
            return 429, None

        info_logger = TfhInfoLogger(self, url, parse_json_as_youtube=False)
        try:
            ydl_opts = {
                'forcejson': 'true',
                'skip_download': 'true',
                'logger': info_logger,
                'progress_hooks': [TrailerInfoProgressHook(self).status_hook],
                'cookiefile': '/home/fbacher/youtube.cookies'
            }

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            while info_logger.is_finished is None and self._error == 0:
                Monitor.throw_exception_if_abort_requested(timeout=0.5)

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

        if self._error != 0:
            clz._logger.debug('Results for url:', url, 'error:', self._error)
            info_logger.log_debug()
            info_logger.log_warning()
            info_logger.log_error()

        Monitor.throw_exception_if_abort_requested(timeout=DELAY)
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

        :param url:
        :param trailers_to_download: Specifies the index of which trailers to get
                                     url of. An empty list means get all urls.
        :param trailer_handler:
        :return:
        """

        clz = YDStreamExtractorProxy

        rc = self.check_too_many_requests(url)
        if rc != 0:
            return rc

        # Would prefer to get a list of playlist_items in order
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
            'cookiefile': '/home/fbacher/youtube.cookies',
            'cachedir': '/home/fbacher/youtube-dl.cache'
            #'debug_printtraffic': True
        }

        if len(trailers_to_download) > 10:
            ydl_opts['playlist_items'] = trailers_to_download

        clz._logger.debug('Start download')
        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            clz._logger.debug('End download. RC:', self._error)

        except AbortException:
            reraise(*sys.exc_info())

        except Exception as e:
            if self._error == 0:
                clz._logger.exception(e)

        if self._error != 0:
            clz._logger.debug('Results for url:', url, 'error:', self._error)
            tfh_index_logger.log_error()
            tfh_index_logger.log_debug()
            tfh_index_logger.log_warning()

        Monitor.throw_exception_if_abort_requested(timeout=DELAY)
        return self._error


class BaseYDLogger:
    logger = None

    def __init__(self, callback, url: str, parse_json_as_youtube: bool = True):
        clz = BaseYDLogger
        clz.logger = module_logger.getChild(clz.__name__)
        self.debug_lines: List[str] = []
        self.warning_lines: List[str] = []
        self.error_lines: List[str] = []
        self._callback = callback
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
            "thumbnails": [{"url": "https://i.ytimg.com/vi/nrExo_KJROc/hqdefault.jpg?sqp=-oaymwEYCKgBEF5IVfKriqkDCwgBFQAAiEIYAXAB&rs=AOn4CLCPHEof66nqx4GxE04sOUocr9WywA",
             "width": 168, "height": 94, "resolution": "168x94", "id": "0"},
             {"url": "https://i.ytimg.com/vi/nrExo_KJROc/hqdefault.jpg?sqp=-oaymwEYCMQBEG5IVfKriqkDCwgBFQAAiEIYAXAB&rs=AOn4CLAm-CXcCCu0LATG_R347wBxBQj4BQ",
               "width": 196, "height": 110, "resolution": "196x110", "id": "1"},
             {"url": "https://i.ytimg.com/vi/nrExo_KJROc/hqdefault.jpg?sqp=-oaymwEZCPYBEIoBSFXyq4qpAwsIARUAAIhCGAFwAQ==&rs=AOn4CLAhW2AcVqdWYiPMZuKENgiCO0gykQ",...
        :return:
        """
        clz = BaseYDLogger
        self.debug_lines.append(line)
        if line.startswith('[download] Downloading video'):
            try:
                _, index_str, total_str = re.split(r'[^0-9]+', line)
                self.index = int(index_str)
                self.total = int(total_str)
            except Exception as e:
                clz.logger.exception()
                self._callback._error = 1

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
                    self._parsed_movie = populate_movie(self.raw_data, self.url)
                # self._trailer_handler(movie_data)
            except Exception as e:
                clz.logger.exception()
                self._callback._error = 2

    def warning(self, line: str) -> None:
        if 'merged' in line:
            # str: Requested formats are incompatible for merge and will be merged into
            # mkv.
            pass
        else:
            self.warning_lines.append(line)

    def error(self, line: str) -> None:
        clz = BaseYDLogger
        if 'Error 429' in line:
            self._callback._error = 429
            clz._initial_tmr_timestamp = datetime.datetime.now()
            clz._too_many_requests_timestamp = (
                datetime.datetime.now() + RETRY_DELAY)

            clz.logger.info(
                'Abandoning download. Too Many Requests')
        # str: ERROR: (ExtractorError(...), 'wySw1lhMt1s: YouTube said: Unable
        # to extract video data')
        elif 'Unable to extract' in line:
            self._callback._error = YDStreamExtractorProxy.DOWNLOAD_ERROR
        elif 'blocked' in line:
            self._callback._error = YDStreamExtractorProxy.BLOCKED_ERROR
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

    def __init__(self, callback, trailer_handler, url: str):
        super().__init__(callback, url, parse_json_as_youtube=True)
        clz = TfhIndexLogger
        clz.logger = module_logger.getChild(clz.__name__)
        self._trailer_handler = trailer_handler

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
            "thumbnails": [{"url": "https://i.ytimg.com/vi/nrExo_KJROc/hqdefault.jpg?sqp=-oaymwEYCKgBEF5IVfKriqkDCwgBFQAAiEIYAXAB&rs=AOn4CLCPHEof66nqx4GxE04sOUocr9WywA",
             "width": 168, "height": 94, "resolution": "168x94", "id": "0"},
             {"url": "https://i.ytimg.com/vi/nrExo_KJROc/hqdefault.jpg?sqp=-oaymwEYCMQBEG5IVfKriqkDCwgBFQAAiEIYAXAB&rs=AOn4CLAm-CXcCCu0LATG_R347wBxBQj4BQ",
               "width": 196, "height": 110, "resolution": "196x110", "id": "1"},
             {"url": "https://i.ytimg.com/vi/nrExo_KJROc/hqdefault.jpg?sqp=-oaymwEZCPYBEIoBSFXyq4qpAwsIARUAAIhCGAFwAQ==&rs=AOn4CLAhW2AcVqdWYiPMZuKENgiCO0gykQ",...
        :return:
        """
        super().debug(line)
        clz = TfhIndexLogger
        if self._parsed_movie is not None:
            try:
                self._trailer_handler(self._parsed_movie)
            except Exception as e:
                clz.logger.exception()


class TfhVideoLogger(BaseYDLogger):
    logger = None

    def __init__(self, callback, url: str):
        super().__init__(callback, url, parse_json_as_youtube=False)
        clz = TfhIndexLogger
        clz.logger = module_logger.getChild(clz.__name__)
        self.data = None

    def debug(self, line: str) -> None:
        """
        :return:
        """
        super().debug(line)
        clz = TfhVideoLogger

        self.data = self._parsed_movie


class TfhInfoLogger(BaseYDLogger):
    logger = None

    def __init__(self, callback, url: str, parse_json_as_youtube: bool = False):
        super().__init__(callback, url, parse_json_as_youtube=parse_json_as_youtube)
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


def populate_movie(movie_data: MovieType, url: str) -> MovieType:

    # TFH trailers are titled: <reviewer> on <MOVIE_TITLE_ALL_CAPS>
    # Here we can try to get just the movie title and then look up
    # a likely match in TMDB (with date, and other info).

    # TFH may not like changing the title, however.
    movie: MovieType = {}
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
            movie_data['upload_date'] = datetime.datetime.now().strftime('%Y%m%d')
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
                 # 'tags': tags,
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

    def __init__(self, callback):
        self.error_lines: List[str] = []
        self.warning_lines: List[str] = []
        self.debug_lines: List[str] = []
        self._download_eta: Optional[int] = None
        self._error: int = 0
        self._callback = callback

    def status_hook(self, status: Dict[str, str]) -> None:
        clz = BaseInfoHook

        status_str = status.get('status', 'missing status')
        if status_str is None:
            clz._logger.debug('Missing status indication')
        elif status_str == 'downloading':
            self._download_eta = status.get('eta', 0)  # In seconds
        elif status_str == 'error':
            clz._logger.error('Status:', str(status))
            self.error_lines.append('Error downloading')
            self._error = YDStreamExtractorProxy.DOWNLOAD_ERROR
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

            clz._logger.debug('Finished')


class TrailerInfoProgressHook(BaseInfoHook):
    _logger = module_logger.getChild('TrailerInfoProgressHook')

    def __init__(self, callback):
        super().__init__(callback)

    def status_hook(self, status: Dict[str, str]) -> None:
        clz = TrailerInfoProgressHook
        super().status_hook(status)


class TFHIndexProgressHook(BaseInfoHook):
    _logger = module_logger.getChild('TFHIndexProgressHook')

    def __init__(self, callback):
        super().__init__(callback)

    def status_hook(self, status: Dict[str, str]) -> None:
        clz = TFHIndexProgressHook
        super().status_hook(status)


class VideoDownloadProgressHook(BaseInfoHook):
    _logger = module_logger.getChild('VideoDownloadProgressHook')

    def __init__(self, callback):
        super().__init__(callback)

    def status_hook(self, status: Dict[str, str]) -> None:
        clz = VideoDownloadProgressHook
        super().status_hook(status)
