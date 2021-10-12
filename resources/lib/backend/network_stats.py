# -*- coding: utf-8 -*-
"""
Created on 10/6/21

@author: Frank Feuerbacher
"""
import datetime
import threading

from common.flexible_timer import FlexibleTimer
from common.imports import *
from common.playlist import Playlist
from common.logger import LazyLogger

from common.settings import Settings

THIRTY_MINUTES: Final[int] = 30

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class FailingURL:

    def __init__(self, url: str) -> None:
        self._url: str = url
        self._failing_count: int = 1
        self._last_failure: datetime.datetime = datetime.datetime.now()

    def new_failure(self) -> None:
        self._failing_count += 1
        self._last_failure: datetime.datetime = datetime.datetime.now()

    def get_failing_count(self) -> int:
        return self._failing_count

    def get_last_failure_time(self) -> datetime.datetime:
        return self._last_failure

    def get_last_failure_str(self) -> str:
        return f'{self._last_failure}'

    def get_url(self) -> str:
        return self._url


class NetworkStats:

    _logger: LazyLogger = None
    _failing_url_map: Dict[str, FailingURL] = {}
    _total_failures: int = 0
    _total_was_failing: int = 0
    _total_successes: int = 0

    @classmethod
    def class_init(cls):
        cls._logger = module_logger.getChild(cls.__class__.__name__)

    @classmethod
    def auto_report(cls, frequency_minutes: int = THIRTY_MINUTES) -> None:
        """
        Automatically run a network status report every few minutes

        :param: frequency_minutes Minutes in between reports
        """

        try:
            # Use FlexibleTimer since it will cancel if AbortException occurs

            interval: float = float(frequency_minutes * 60)
            next_report: FlexibleTimer = FlexibleTimer(interval=interval,
                                                       function=cls.do_report,
                                                       kwargs={
                                                               'frequency_minutes':
                                                               frequency_minutes
                                                           })
            next_report.start()
        except Exception:
            cls._logger.exception()

    @classmethod
    def do_report(cls, frequency_minutes: int = THIRTY_MINUTES,
                  called_early: bool = False):
        try:
            cls.report_summary()
            cls.auto_report(frequency_minutes=frequency_minutes)
        except Exception:
            cls._logger.exception()

    @classmethod
    def add_failing_url(cls, url: str):
        try:
            existing_failure: FailingURL = cls._failing_url_map.get(url)
            if existing_failure is None:
                existing_failure = FailingURL(url)
                cls._failing_url_map[url] = existing_failure
            else:
                existing_failure.new_failure()

            cls._total_failures += 1
        except Exception:
            cls._logger.exception()

    @classmethod
    def not_failing(cls, url: str):
        try:
            if url in cls._failing_url_map:
                del cls._failing_url_map[url]
                cls._total_was_failing += 1
            cls._total_successes += 1
        except Exception:
            cls._logger.exception()

    @classmethod
    def get_summary(cls) -> Tuple[int, int, float, int, str]:
        """
        Gets a summary of successful and failing remote requests for movie
        information

        :return: Number of successful downloads,
                 Number of failing urls,
                 Average number of times a failing url fails
                 Maximum number of times a url failed
                 URL that failed the most
        """
        try:
            number_of_failing_urls: int = len(cls._failing_url_map)
            total_failures: int = 0
            max_failures: int = 0
            most_failing_url: str = ''
            url: str
            failing_url: FailingURL
            for failing_url in cls._failing_url_map.values():
                fail_count: int = failing_url.get_failing_count()
                if fail_count > max_failures:
                    max_failures = fail_count
                    most_failing_url = failing_url.get_url()
                total_failures += fail_count

            average_failures: float
            if number_of_failing_urls == 0:
                average_failures: float = total_failures
            else:
                average_failures: float = total_failures / number_of_failing_urls

            return (
                    cls._total_successes,
                    number_of_failing_urls,
                    average_failures,
                    max_failures,
                    most_failing_url)
        except Exception:
            cls._logger.exception()

    @classmethod
    def report_summary(cls) -> None:
        try:
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(f'Failing URLs')
                total_successes: int
                number_of_failures: int
                average_failures: float
                max_failures: int
                most_failing_url: str
                (total_successes,
                 number_of_failures,
                 average_failures,
                 max_failures,
                 most_failing_url) = cls.get_summary()
                cls._logger.debug_extra_verbose(f'Successful downloads: '
                                                f'{total_successes}')
                cls._logger.debug_extra_verbose(f'Number of failing URLs: '
                                                f'{number_of_failures}')
                cls._logger.debug_extra_verbose(f'Average failures: {average_failures}')
                cls._logger.debug_extra_verbose(f'Max failures: {max_failures}')
                cls._logger.debug_extra_verbose(f'Most failing URL: {most_failing_url}')
                cls._logger.debug_extra_verbose(f'Reported failures:'
                                                f' {cls._total_failures}')
                cls._logger.debug_extra_verbose(f'No longer failing: '
                                                f'{cls._total_was_failing}')
        except Exception:
            cls._logger.exception()

    @classmethod
    def full_report(cls, min_failures: int = 0, include_timestamps: bool = False) -> None:
        try:
            failing_url: FailingURL

            playlist = Playlist.get_playlist(
                'URL_Failure.report', append=False)

            number_of_failures: int
            average_failures: float
            max_failures: int
            most_failing_url: str

            (total_successes,
             number_of_failures,
             average_failures,
             max_failures,
             most_failing_url) = cls.get_summary()

            playlist.writeLine(f'Successful downloads: {total_successes}')
            playlist.writeLine(f'Number of failing URLs: {number_of_failures}')
            playlist.writeLine(f'Average failures: {average_failures}')
            playlist.writeLine(f'Max failures: {max_failures}')
            playlist.writeLine(f'Most failing URL: {most_failing_url}')
            playlist.writeLine(f'Reported failures: {cls._total_failures}')
            playlist.writeLine(f'No longer failing: {cls._total_was_failing}')
            playlist.writeLine('')

            a = sorted(cls._failing_url_map, key=lambda key:
                       cls._failing_url_map[key].get_failing_count(), reverse=True)

            line: str = f'URL       #failures '
            playlist.writeLine(line)
            for failing_url in a:
                fail_count: int = failing_url.get_failing_count()
                if fail_count >= min_failures:
                    if include_timestamps:
                        line = f'{failing_url.get_url()}  ' \
                               f'{failing_url.get_failing_count()}'
                    else:
                        line = f'{failing_url.get_url()}  ' \
                               f'{failing_url.get_failing_count()}' \
                               f' {failing_url.get_last_failure_time()}'
                    playlist.writeLine(line)

            playlist.close()
        except Exception:
            cls._logger.exception()


NetworkStats.class_init()
