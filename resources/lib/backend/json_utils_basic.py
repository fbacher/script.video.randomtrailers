# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import sys
import datetime
from email.utils import parsedate_tz
from enum import Enum, auto

from common.debug_utils import Debug
from requests import Response

import simplejson as json
import random
import requests
from requests.exceptions import ConnectionError, ConnectTimeout, ReadTimeout

import threading
import calendar

import xbmc

from backend.backend_constants import TMDbConstants
from backend.network_stats import NetworkStats
from common.imports import *

from common.logger import LazyLogger, Trace
from common.exceptions import AbortException
from common.messages import Messages
from common.monitor import Monitor
from backend import backend_constants

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class JsonReturnCode(Enum):
    OK = auto()
    RETRY = auto()
    FAILURE_NO_RETRY = auto()
    UNKNOWN_ERROR = auto()


class Result:
    def __init__(self, rc: JsonReturnCode, status: int = None, msg: str = None,
                 data: MovieType = None) -> None:
        self._rc: JsonReturnCode = rc
        self._status: int = status
        self._msg: str = msg
        self._data: MovieType = data

    def get_api_success(self) -> str:
        api_success: str = None
        if self._data is not None and isinstance(self._data, dict):
            api_success = self._data.get('success')

        return api_success

    def get_api_status_code(self) -> str:
        api_status_code = None
        if self._data is not None and isinstance(self._data, dict):
            api_status_code = self._data.get('status_code')

        return api_status_code

    def get_api_status_msg(self) -> str:
        api_status_msg: str = None
        if self._data is not None and isinstance(self._data, dict):
            api_status_msg = self._data.get('status_message')

        return api_status_msg

    def get_rc(self) -> JsonReturnCode:
        return self._rc

    def set_rc(self, rc: JsonReturnCode) -> None:
        self._rc = rc

    def get_status(self) -> int:
        return self._status

    def set_status(self, status: int) -> None:
        self._status = status

    def get_msg(self) -> str:
        return self._msg

    def set_msg(self, msg: str) -> None:
        self._msg = msg

    def get_data(self) -> MovieType:
        return self._data

    def set_data(self, data: MovieType) -> None:
        self._data = data


class JsonUtilsBasic:
    RandomGenerator = random.Random()
    RandomGenerator.seed()

    _exit_requested = False
    """
        Tunes and TMDB each have rate limiting:
            TMDB is limited over a period of 10 seconds
            iTunes is limited to 20 requests/minute and 200
            results per search.
            
            For iTunes see:
         https://affiliate.itunes.apple.com/resources/documentation/itunes-store-web
         -service-search-api/#overview
             All iTunes results are JSON UTF-8

        In order to track the rate of requests over a minute, we have to
        track the timestamp of each request made in the last minute.
    
        Keep in mind for both TMDB and iTunes, that other plugins may be
        making requests
    """

    # In 2019 TMDb turned off rate limiting. Bumped limits up a bit

    TMDB_NAME = 'tmdb'
    TMDB_REQUEST_INDEX = 0
    TMDB_WINDOW_TIME_PERIOD = datetime.timedelta(seconds=100)
    TMDB_WINDOW_MAX_REQUESTS = 120

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

    _logger: LazyLogger = None
    _instance = None

    @classmethod
    def class_init(cls) -> None:
        """

        """
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    # Each entry in the above _request_window* lists is
    # a list with the timestamp and running request count:

    @classmethod
    def get_delay_time(cls, destination: int) -> int:
        """
            Calculates if and how much delay is required by the site
            to prevent rejection of the request.

            We track the timestamp of each request made as well as the running
            request count for each destination (TMDB or ITUNES).
            Here we need to determine what, if any delay is needed so that we
            don't cause rate-limit errors. (Yeah, we could ignore them, until
            we get the error and the and then we would still need to calculate
            a delay).

            The last request is at the end of the list. Starting from the
            front of the list (the oldest entry), toss out every entry that
            is older than our wait window.

        :param destination:
        :return:
        """

        thread_name = threading.currentThread().getName()
        destination_data = JsonUtilsBasic.DestinationDataContainer.get_data(
            destination)
        destination_name = destination_data.name

        request_window = destination_data.get_request_window()
        last_request_count = 0
        if len(request_window) > 0:
            newest_request = request_window[len(request_window) - 1]
            last_request_count = newest_request.get_request_count()
            newest_response_time_stamp = newest_request.get_time_stamp()
        else:
            # Create a dummy timestamp
            newest_response_time_stamp = datetime.datetime.now()

        # Remove any entry that has expired. The window_time_period has how
        # many seconds ago we have to retain entries.

        window_expiration_time = newest_response_time_stamp - \
                                 destination_data.window_time_period

        if (cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                and Trace.is_enabled(Trace.TRACE_NETWORK)):
            cls._logger.debug_extra_verbose('destination', destination_name,
                                            'expiration:', window_expiration_time,
                                            '#request_window:',
                                            len(request_window), 'last_request_count:',
                                            last_request_count, 'transaction timestamp:',
                                            newest_response_time_stamp,
                                            trace=[Trace.TRACE_JSON, Trace.TRACE_NETWORK])
        index = 0
        oldest_entry = None
        while index < len(request_window):
            oldest_entry = request_window[0]
            was = oldest_entry.get_time_stamp()
            #
            # Purge expired entries
            #
            # cls._logger.debug(
            #    'was: ', was, 'request_window length:', len(request_window))
            if was < window_expiration_time:
                # Purge
                del request_window[0]
            else:
                break

        if (cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                and Trace.is_enabled(Trace.TRACE_NETWORK)):
            cls._logger.debug_extra_verbose('request_window length:', len(request_window),
                                            'destination_data.request_window length:',
                                            len(destination_data.get_request_window()),
                                            trace=Trace.TRACE_NETWORK)

            # At this point, request_window[0] should be the oldest, un-expired
            # entry

            if oldest_entry is None:
                cls._logger.debug_extra_verbose('oldest_entry: None',
                                                'expiration:',
                                                window_expiration_time,
                                                'hardCodedRequestsPerTimePeriod:',
                                                destination_data.
                                                    hard_coded_requests_per_time_period,
                                                trace=[Trace.TRACE_JSON,
                                                       Trace.TRACE_NETWORK])
            else:
                cls._logger.debug_extra_verbose(
                    'oldest_entry:',
                    oldest_entry.get_time_stamp(),
                    'expiration:', window_expiration_time,
                    'oldest RequestCount:',
                    oldest_entry.get_request_count(),
                    'hardCodedRequestsPerTimePeriod:',
                    destination_data.hard_coded_requests_per_time_period,
                    trace=[Trace.TRACE_JSON,
                           Trace.TRACE_NETWORK])
        #
        # Have we hit the maximum number of requests over this
        # time period? If we have, then how long do we have to wait before the
        # next request.
        #
        # This calculation is based soley on counts
        # and ignores what the server may be telling us from the last response
        # hard_coded_requests_per_time_period and
        # actual_oldest_request_in_window_expiration_time

        delay = datetime.timedelta(0)
        calculated_number_of_requests_pending = 0
        if len(request_window) > 0:
            starting_request_count = oldest_entry.get_request_count()

            # How many additional requests can be made before we are blocked?

            calculated_number_of_requests_pending = last_request_count - \
                                                    starting_request_count + 1
            if (cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                    and Trace.is_enabled(Trace.TRACE_NETWORK)):
                cls._logger.debug_extra_verbose(
                    'calculated_number_of_requests_pending:',
                    calculated_number_of_requests_pending,
                    'length of request_window:',
                    len(request_window),
                    'numberOfAdditionalRequetsAllowedByServer from server:',
                    destination_data.number_of_additional_requests_allowed_by_server,
                    'starting_request_count',
                    starting_request_count, 'limit:',
                    destination_data.hard_coded_requests_per_time_period,
                    trace=[Trace.TRACE_JSON,
                           Trace.TRACE_NETWORK])

        # If the server gives us this info directly, then replace
        # our calculated value with the server value.

        # If server does not give us actual number of remaining requests, then
        # see if server specifies the number in a time period

        max_requests_in_time_period = destination_data.hard_coded_requests_per_time_period
        if destination_data.actual_max_requests_per_time_period > 0:
            max_requests_in_time_period = \
                destination_data.actual_max_requests_per_time_period
            if (cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                    and Trace.is_enabled(Trace.TRACE_NETWORK)):
                cls._logger.debug_extra_verbose(
                    'Setting max_requests_in_time_period to value from server:',
                    max_requests_in_time_period,
                    trace=[Trace.TRACE_JSON, Trace.TRACE_NETWORK])

        number_of_requests_that_can_still_be_made = max_requests_in_time_period - \
                                                    calculated_number_of_requests_pending

        # If server gives us actual number of remaining requests, then
        # use that instead of what we calculated above.

        if destination_data.number_of_additional_requests_allowed_by_server >= 0:
            number_of_requests_that_can_still_be_made = \
                destination_data.number_of_additional_requests_allowed_by_server
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(
                    'Using number_of_additional_requests_allowed_by_server:',
                    number_of_requests_that_can_still_be_made,
                    trace=Trace.TRACE_JSON)

        # Based on the above, calculate any delay time required before making
        # next request

        if number_of_requests_that_can_still_be_made > 0:
            delay = datetime.timedelta(0)  # Now, we should be ok
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose('delay:', delay,
                                                '#requests:', len(request_window),
                                                'requests_that_can_still_be_made:',
                                                number_of_requests_that_can_still_be_made,
                                                trace=Trace.TRACE_JSON)
        elif len(request_window) > 0:
            already_waited = newest_response_time_stamp - oldest_entry.get_time_stamp()
            delay = destination_data.window_time_period - already_waited

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose('already_waited:', already_waited,
                                                'delay:', delay,
                                                trace=Trace.TRACE_JSON)
            if delay.total_seconds() <= 0:
                cls._logger.error(
                    'Logic error: timer delay should be > 0')

        # If the server gave us information about how long to delay before
        # making a request, then use that instead of the calcualted value
        #
        # The server can give delay information in two ways:
        # 1) the timestamp for the oldest request. Waiting until expires will
        #    guarantee that at least one more request can be made.
        #
        # 2) After a request failure, the server may give how much time
        #    must elapse before trying again.
        #
        corrected_delay = 0
        if number_of_requests_that_can_still_be_made <= 0:
            if destination_data.actual_oldest_request_in_window_expiration_time is not \
                    None:
                reset_time_from_server: datetime.datetime = (
                            destination_data.actual_oldest_request_in_window_expiration_time
                            + datetime.timedelta(0, 1))
                corrected_delay = reset_time_from_server - datetime.datetime.now()
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    cls._logger.debug_extra_verbose(
                        'correctedDelay:',
                        corrected_delay.total_seconds(),
                        trace=Trace.TRACE_JSON)

            # Second method:
        #
        # Not all requests provide an X-RateLimit-Reset value in the header
        # but when a limit failure the header contains
        # 'Retry-After' which tells you when you can retry again.

        corrected_delay2 = 0
        if destination_data.server_blocking_request_until is not None:
            corrected_delay2 = destination_data.server_blocking_request_until - \
                               datetime.datetime.now()
            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose('corrected_delay2:',
                                          corrected_delay2.total_seconds(),
                                          trace=Trace.TRACE_JSON)

            # If server's calculated expirationTime disagrees significantly than ours,
        # then use it.

        if corrected_delay != 0:
            delay = corrected_delay

        # If server is rejecting requests, then use it's delay time.

        if corrected_delay2 != 0:
            delay = corrected_delay2

        delay_seconds = delay.total_seconds()

        if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            cls._logger.debug_extra_verbose('delay_seconds:', delay_seconds,
                                      trace=Trace.TRACE_JSON)

        if delay_seconds < 0:
            delay_seconds = 0

        return delay_seconds

    class RequestTimestamp:
        """
            A running history of request transactions is kept to
            track when a transaction was made as well as the transaction
            number. Used to prevent exceeding limits to a site over a
            period of time.

        """

        def __init__(self,
                     time_stamp: datetime.datetime,
                     request_count: int) -> None:
            """

            :param time_stamp:
            :param request_count:
            """
            self._time_stamp = time_stamp
            self._request_count = request_count

        def get_time_stamp(self) -> datetime.datetime:
            """
                Gets the timestamp of this request entry to the associated
                site.

            :return:
            """
            return self._time_stamp

        def get_request_count(self) -> int:
            """
                Gets the running count of requests to the associated site
                and request history.
                Used to keep track if too many requests have occurred over
                a given period of time.

            :return:
            """
            return self._request_count

    @classmethod
    def record_request_timestamp(cls,
                                 destination: int,
                                 response_time_stamp: datetime.datetime,
                                 failed: bool = False) -> None:
        """
            Records the fact that a request to the given site occurred at a
            specific time. Done for traffic management.

        """
        destination_data = JsonUtilsBasic.DestinationDataContainer.get_data(
            destination)
        request_window = destination_data.get_request_window()
        if cls._logger.isEnabledFor(LazyLogger.DISABLED):
            cls._logger.debug_extra_verbose('JSON destination:',
                                            destination, 'timestamp:',
                                            response_time_stamp,
                                            trace=Trace.TRACE_JSON)
            JsonUtilsBasic.dump_delay_info(destination)

        last_index = -1
        last_request_count = 0
        if len(request_window) > 0:
            last_index = len(request_window) - 1
            last_request_count = request_window[last_index].get_request_count()

        if failed:
            last_request_count += destination_data.hard_coded_requests_per_time_period
        else:
            last_request_count += 1

        new_entry = JsonUtilsBasic.RequestTimestamp(
            response_time_stamp, last_request_count)
        request_window.append(new_entry)

        if cls._logger.isEnabledFor(LazyLogger.DISABLED):
            cls._logger.debug_verbose('last_request_count:', last_request_count,
                                      'last_index:', last_index,
                                      'length:', len(request_window),
                                      'failed:', failed,
                                      trace=Trace.TRACE_JSON)
            JsonUtilsBasic.dump_delay_info(destination,
                                           msg='Exiting record_request_timestamp')

    @classmethod
    def dump_delay_info(cls,
                        destination: int,
                        msg: str = '') -> None:
        """
            Dumps debug information about recent requests to the given
            site.

        :param destination:
        :param msg:
        :return:
        """
        if not cls._logger.isEnabledFor(LazyLogger.DISABLED):
            return

        destination_data = cls.DestinationDataContainer.get_data(
            destination)
        request_window = destination_data.get_request_window()
        request_count = None
        time_stamp = None
        for request in request_window:
            time_stamp = request.get_time_stamp()
            request_count = request.get_request_count()

        try:

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                if len(request_window) != 0:
                    cls._logger.debug_verbose(msg, '\n', 'timestamp:', str(time_stamp),
                                              'count:', request_count, '\n')
                else:
                    cls._logger.debug_verbose('no requests',
                                              trace=Trace.TRACE_JSON)
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception('')

    class DestinationData:
        """

        """

        _destination_data = []

        def __init__(self,
                     name: str,
                     max_requests: int,
                     window_time_period: datetime.timedelta) -> None:
            """

            """
            self.name = name
            self.total_requests = 0  # Total requests made

            # Reported in header from every request response to tmdb
            # header.get('X-RateLimit-Remaining')
            self.number_of_additional_requests_allowed_by_server = -1

            # Number of requests that can be made over a period of time
            # For TMDB, most APIs return this value in the header:
            # header.get('X-RateLimit-Limit')  # Was 40
            self.actual_max_requests_per_time_period = -1

            # When X-RateLimt-Limit is not available,
            # then hard_coded_requests_per_time_period
            # contains the maximum number of requests that can occur over
            # a period of time. This is a constant per site.

            self.hard_coded_requests_per_time_period = max_requests

            # For TMDB, the header contains when the running rate limit
            # will expire.  header.get('X-RateLimit-Reset')
            # Limit will be lifted at this time, in epoch seconds

            self.actual_oldest_request_in_window_expiration_time:\
                Union[datetime.datetime, None] = None

            # Not all requests utilize the above, but when a limit failure occurs,
            # use 'Retry-After' header value which tells you when you can retry
            # again.

            self.server_blocking_request_until = None
            self.window_time_period = window_time_period
            self.response_time_stamp = None

            self._request_window = []
            self._lock = threading.RLock()

        def get_lock(self) -> threading.RLock:
            """
            Gets a handle to a lock for the download site (TMDB, iTunes).

            :return:
            """
            return self._lock

        def get_request_window(self) -> List['JsonUtilsBasic.RequestTimestamp']:
            """

            :return:
            """
            return self._request_window

    class DestinationDataContainer:
        """

        """
        data_for_destination: List['JsonUtilsBasic.DestinationData'] = []

        @classmethod
        def get_data_for_destination(cls,
                    destination: int) -> ForwardRef('JsonUtilsBasic.DestinationData'):
            """
            """
            return JsonUtilsBasic.DestinationDataContainer.data_for_destination[
                destination]

        @staticmethod
        def initialize() -> None:
            """
                staticmethod to create instances for each type of
                destination (TMDB & ITUNES)

            :return:
            """
            tmdb_data = JsonUtilsBasic.DestinationData(
                                        JsonUtilsBasic.TMDB_NAME,
                                        JsonUtilsBasic.TMDB_WINDOW_MAX_REQUESTS,
                                        JsonUtilsBasic.TMDB_WINDOW_TIME_PERIOD)
            JsonUtilsBasic.DestinationDataContainer.data_for_destination.append(
                tmdb_data)

            itunes_data = JsonUtilsBasic.DestinationData(
                                        JsonUtilsBasic.ITUNES_NAME,
                                        JsonUtilsBasic.ITUNES_WINDOW_MAX_REQUESTS,
                                        JsonUtilsBasic.ITUNES_WINDOW_TIME_PERIOD)
            JsonUtilsBasic.DestinationDataContainer.data_for_destination.append(
                itunes_data)

            # TODO: supply correct info

            rotten_tomatoes_data = JsonUtilsBasic.DestinationData(
                                    JsonUtilsBasic.ROTTEN_TOMATOES_NAME,
                                    JsonUtilsBasic.ROTTEN_TOMATOES_WINDOW_MAX_REQUESTS,
                                    JsonUtilsBasic.ROTTEN_TOMATOES_WINDOW_TIME_PERIOD)
            JsonUtilsBasic.DestinationDataContainer.data_for_destination.append(
                rotten_tomatoes_data)

        @staticmethod
        def get_data(destination: int) -> ForwardRef('JsonUtilsBasic.DestinationData'):
            """
                Gets data about recent requests to the given site so that
                appropriate delays between requests can occur.

            :param destination:
            :return:
            """
            if len(JsonUtilsBasic.DestinationDataContainer.data_for_destination) == 0:
                JsonUtilsBasic.DestinationDataContainer.initialize()

            return JsonUtilsBasic.DestinationDataContainer.data_for_destination[
                destination]

    @classmethod
    def get_json(cls, url: str,
                 second_attempt: bool = False,
                 dump_results: bool = False,
                 dump_msg: str = '',
                 error_msg: Union[str, int, None] = None,
                 headers: Union[dict, None] = None,
                 params: Union[Dict[str, Any], None] = None,
                 timeout: float = 3.0
                 ) -> Result:
        """
            Queries external site for movie/trailer information.

            Returns JSON result.

            Retries once on failure. Uses hints from response to adjust
            delay between requests.

        :param url:
        :param second_attempt:
        :param dump_results:
        :param dump_msg:
        :param error_msg:
        :param headers:
        :param params:
        :param timeout:
        :return:
        """

        result: Result
        result = Result(rc=JsonReturnCode.UNKNOWN_ERROR, status=-1,
                        msg='Result not returned', data=None)
        if headers is None:
            headers = {}

        if params is None:
            params = {}

        destination_string = ''
        request_index = None
        site = None
        if 'themoviedb' in url:
            destination_string = 'TMDB'
            request_index = JsonUtilsBasic.TMDB_REQUEST_INDEX
            site = 'TMDB'
        elif backend_constants.APPLE_URL_PREFIX in url:
            destination_string = 'iTunes'
            request_index = JsonUtilsBasic.ITUNES_REQUEST_INDEX
            site = 'iTunes'
        elif backend_constants.ROTTEN_TOMATOES_URL_PREFIX in url:
            destination_string = 'RottenTomatoes'
            request_index = JsonUtilsBasic.ROTTEN_TOMATOES_REQUEST_INDEX
            site = 'Tomatoes'

        destination_data = JsonUtilsBasic.DestinationDataContainer.get_data(
            request_index)
        Monitor.throw_exception_if_abort_requested()
        rc: JsonReturnCode

        with destination_data.get_lock():
            time_delay = JsonUtilsBasic.get_delay_time(request_index)
            movie_data: MovieType = None

            # TMDb no longer rate limits, but still, add 10 seconds for retries

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(
                    'requestCount:',
                    destination_data.total_requests,
                    'serverBlockingRequestUntil:',
                    destination_data.server_blocking_request_until,
                    'numberOfAdditionalRequestsAllowedByServer:',
                    destination_data.number_of_additional_requests_allowed_by_server,
                    'hardCodedRequestsPerTimePeriod:',
                    destination_data.hard_coded_requests_per_time_period,
                    'requestLimitFromServer:',
                    destination_data.actual_max_requests_per_time_period,
                    'actualOldestRequestInWindowExpirationTime:',
                    destination_data.actual_oldest_request_in_window_expiration_time,
                    trace=Trace.TRACE_JSON)
            if time_delay > 0:
                if cls._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    cls._logger.debug_verbose('Waiting for JSON request to',
                                      destination_string, 'for', time_delay,
                                      'seconds',
                                      trace=[Trace.STATS, Trace.TRACE_JSON])
            Monitor.throw_exception_if_abort_requested(timeout=time_delay)
            destination_data.total_requests += 1
            requests_to_url = destination_data.total_requests

            now = datetime.datetime.now()
            response_time_stamp = now

            try:
                response = requests.get(
                    url.encode('utf-8'), headers=headers, params=params,
                    timeout=timeout)
                now = datetime.datetime.now()
                rc = cls.response_checker(response, msg=error_msg, url=url)
                response_time_stamp = now
                status_code = response.status_code  # ex. 200
                reason: str = response.reason  # ex: 'OK'
                movie_data = response.json()
                # Debug.dump_json(text='Dumping downloaded data', data=movie_data,
                #                 log_level=LazyLogger.DEBUG_EXTRA_VERBOSE)

                result = Result(rc, status=status_code, msg=reason, data=movie_data )
                if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                    cls._logger.debug(
                        f'generated url: {response.url} status_code: {status_code}')
                    # cls._logger.debug(f'{json.dumps(movie_data, indent=3,
                    # sort_keys=True)}')
                    # cls._logger.debug(f'response: {response}')
                    cls._logger.debug(f'reason: {response.reason}')
                    # cls._logger.debug(f'headers: {response.headers}')
                    cls._logger.debug(f'api_success: {result.get_api_success()} '
                                      f'api_status_code: {result.get_api_status_code()} '
                                      f'api_status_message: '
                                      f'{result.get_api_status_msg()}')

                returned_header = response.headers
            except AbortException:
                reraise(*sys.exc_info())
            #
            # Possible Exceptions:
            #     RequestException, Timeout, URLRequired,
            #     TooManyRedirects, HTTPError, ConnectionError,
            #     FileModeWarning, ConnectTimeout, ReadTimeout
            except (ReadTimeout, ConnectTimeout, ConnectionError) as e:
                if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                    cls._logger.debug(
                        'Timeout occurred. Will retry.', error_msg)
                result.set_rc(JsonReturnCode.RETRY)
                result.set_status(-1)
                result.set_data(None)
                result.set_msg('Timeout')
                returned_header = {
                    'Retry-After': str(
                        destination_data.window_time_period.total_seconds())}

            except Exception as e:
                try:
                    # TODO: Move this after full analysis, not nested

                    if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                        cls._logger.debug('Exception getting movie:', error_msg,
                                          'url:', url)
                        cls._logger.exception('')

                    result.set_rc(JsonReturnCode.FAILURE_NO_RETRY) # Not sure
                    result.set_status(-1)
                    result.set_data(None)
                    result.set_msg('Exception caught')
                    returned_header = {}

                    if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                        # The exception frequently doesn't have a complete stack
                        # trace

                        LazyLogger.dump_stack()
                        cls._logger.debug('request to', destination_string,
                                          'FAILED.', 'url', url, 'headers:',
                                          headers,
                                          'params', params, 'timeout', timeout,
                                          trace=[Trace.STATS, Trace.TRACE_JSON])
                        cls._logger.debug('request to', destination_string,
                                          'FAILED total requests:',
                                          requests_to_url,
                                          trace=[Trace.STATS, Trace.TRACE_JSON])
                        JsonUtilsBasic.dump_delay_info(request_index)

                    if second_attempt:
                        if result.get_rc() != JsonReturnCode.OK:
                            NetworkStats.add_failing_url(url=url)
                        else:
                            NetworkStats.not_failing(url=url)
                        return result

                    if cls._logger.isEnabledFor(LazyLogger.DEBUG):
                        JsonUtilsBasic.dump_delay_info(request_index)

                except AbortException:
                    reraise(*sys.exc_info())
                except Exception as e:
                    cls._logger.exception('')

            if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                cls._logger.debug_extra_verbose(
                    'Headers from:', site, returned_header)

            # TODO- delete or control by setting or config_logger

            destination_data.number_of_additional_requests_allowed_by_server = -1
            destination_data.actual_max_requests_per_time_period = -1
            destination_data.actual_oldest_request_in_window_expiration_time = None
            destination_data.server_blocking_request_until = None

            tmp = returned_header.get('X-RateLimit-Remaining')
            if tmp is not None:
                destination_data.number_of_additional_requests_allowed_by_server = int(
                    tmp)

            tmp = returned_header.get('X-RateLimit-Limit')
            if tmp is not None:
                destination_data.actual_max_requests_per_time_period = int(tmp)

            # Limit will be lifted at this time, in epoch seconds
            tmp = returned_header.get('X-RateLimit-Reset')
            if tmp is not None:
                destination_data.actual_oldest_request_in_window_expiration_time = (
                    datetime.datetime.fromtimestamp(int(tmp)))
            else:
                # Some calls don't return X-RateLimit-Reset, in those cases there
                # should be Retry-After indicating how many more seconds to wait
                # before traffic can resume

                server_blocking_request_until_value = 0
                tmp = returned_header.get('Retry-After')
                msg = ''
                if tmp is not None:
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        cls._logger.debug_extra_verbose(
                            'Retry-After:', tmp)
                    seconds = float(tmp) + 1
                    server_blocking_request_until_value = response_time_stamp + \
                                                          datetime.timedelta(0, seconds)
                    destination_data.server_blocking_request_until = \
                        server_blocking_request_until_value

                # TODO: This is messy. The Date string returned is probably dependent
                # upon the locale of the user, which means the format will be different
                # Note also that the time zone GMT, or any timezone, is not recognized
                # on input and it is assumed that you are in the same timezone (yeesh)
                # Have to manually clobber the TZ field and reset to UTC.

                tmp = returned_header.get('Date')
                if tmp is not None:
                    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        parsed_date = parsedate_tz(tmp)
                        unix_time_stamp = calendar.timegm(parsed_date)
                        time_stamp = datetime.datetime.fromtimestamp(
                            unix_time_stamp)

                        delta = time_stamp - response_time_stamp
                        # cls._logger.debug_extra_verbose(
                        #     'Date: ', tmp)

                        if cls._logger.isEnabledFor(LazyLogger.DISABLED):
                            cls._logger.debug_extra_verbose('Timestamp from server:',
                                                            time_stamp,
                                                            'difference from client:',
                                                            delta.total_seconds())
                # In 2019 TMDb turned off rate limiting.

                # if request_index == JsonUtilsBasic.TMDB_REQUEST_INDEX:
                #    if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                #        cls._logger.debug_extra_verbose(
                #            'TMDB response header missing X-RateLimit info.', msg)

            # Debug.myLog('get_json movie_data: ' + movie_data.__class__.__name__ +
            #            ' ' + json.dumps(movie_data), xbmc.LOGDEBUG)

            '''
            if ((status_code == Constants.TOO_MANY_TMDB_REQUESTS)
                    and (
                            request_index == JsonUtilsBasic.TMDB_REQUEST_INDEX)):  #
                # Too many requests,
                if cls._logger.isEnabledFor(LazyLogger.INFO):
                    cls._logger.info(
                        'JSON Request rate to TMDB exceeds limits ('
                        + str(destination_data.hard_coded_requests_per_time_period) +
                        ' every', destination_data.window_time_period.total_seconds(),
                        ' seconds). Consider getting API Key. This session\'s requests: '
                        + str(destination_data.total_requests),
                        trace=Trace.TRACE_JSON)

                if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    JsonUtilsBasic.dump_delay_info(request_index)
            '''

            if cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                cls._logger.debug_extra_verbose(
                    'JSON request source:',
                    destination_string, 'total requests:',
                    requests_to_url,
                    'serverBlockingRequestUntil:',
                    destination_data.server_blocking_request_until,
                    'numberOfAdditionalRequetsAllowedByServer:',
                    destination_data.number_of_additional_requests_allowed_by_server,
                    'hardCodedRequestsPerTimePeriod:',
                    destination_data.hard_coded_requests_per_time_period,
                    'actualMaxRequestsPerTimePeriod:',
                    destination_data.actual_max_requests_per_time_period,
                    'actualOldestRequestInWindowExpirationTime:',
                    destination_data.actual_oldest_request_in_window_expiration_time,
                    trace=[Trace.STATS, Trace.TRACE_JSON])
            request_failed: bool = result.get_rc() != JsonReturnCode.OK
            JsonUtilsBasic.record_request_timestamp(
                request_index, response_time_stamp, failed=request_failed)
            if result.get_status() != JsonReturnCode.OK:
                #
                # Retry only once
                #

                if not second_attempt:
                    try:
                        result = \
                            JsonUtilsBasic.get_json(url,
                                                    second_attempt=True,
                                                    headers=headers,
                                                    params=params,
                                                    timeout=0.50)
                    except AbortException:
                        reraise(*sys.exc_info())
                    except Exception as e:
                        result.set_rc(JsonReturnCode.FAILURE_NO_RETRY)
                        result.set_data(None)
                        result.set_msg('Exception caught')
                    finally:
                        request_failed: bool = result.get_rc() != JsonReturnCode.OK
                        JsonUtilsBasic.record_request_timestamp(
                            request_index, response_time_stamp, failed=request_failed)

        # if dump_results and cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
        #    cls._logger.debug_extra_verbose('JSON DUMP:', dump_msg)
        #    cls._logger.debug_extra_verbose(json.dumps(
        #        movie_data, indent=3, sort_keys=True))

        if result.get_rc() != JsonReturnCode.OK:
            NetworkStats.add_failing_url(url=url)
        else:
            NetworkStats.not_failing(url=url)

        return result

    @classmethod
    def get_kodi_json(cls,
                      query: str,
                      dump_results: bool = False) -> Dict[str, Any]:
        """
            Queries Kodi database and returns JSON result

        :param query:
        :param dump_results:
        :return:
        """
        json_text = xbmc.executeJSONRPC(query)
        Monitor.throw_exception_if_abort_requested()
        movie_results = json.loads(json_text, encoding='utf-8',
                                   object_hook=JsonUtilsBasic.abort_checker)
        if dump_results and cls._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            Monitor.throw_exception_if_abort_requested()
            cls._logger.debug_extra_verbose('JASON DUMP:',
                                            json.dumps(
                                                json_text, indent=3, sort_keys=True))
        return movie_results

    @classmethod
    def response_checker(cls, response: Response, msg: str = '',
                         url: str = '') -> JsonReturnCode:
        '''

                    200's OK
                    400's LOG, don't retry
                    500's LOG, Server error
                    502-504 retry
               Code 	HTTP Status 	Message
               OK, unless additional data available
            1 	200 	Success.
            13 	200 	The item/record was deleted successfully.
            21 	200 	Entry not found: The item you are trying to edit cannot be found.
            40 	200 	Nothing to update.
            12 	201 	The item/record was updated successfully.

            Application error  LOG, don't retry
            18 	400 	Validation failed.
            22 	400 	Invalid page: Pages start at 1 and max at 1000. They are expected to be an integer.
            23 	400 	Invalid date: Format needs to be YYYY-MM-DD.
            26 	400 	You must provide a username and password.
            27 	400 	Too many append to response objects: The maximum number of remote calls is 20.
            28 	400 	Invalid timezone: Please consult the documentation for a valid timezone.
            29 	400 	You must confirm this action: Please provide a confirm=true parameter.
            47 	400 	The input is not valid.
            3 	401 	Authentication failed: You do not have permissions to access the service.
            7 	401 	Invalid API key: You must be granted a valid key.
            10 	401 	Suspended API key: Access to your account has been suspended, contact TMDb.
            14 	401 	Authentication failed.
            16 	401 	Device denied.
            17 	401 	Session denied.
            30 	401 	Invalid username and/or password: You did not provide a valid login.
            31 	401 	Account disabled: Your account is no longer active. Contact TMDb if this is an error.
            32 	401 	Email not verified: Your email address has not been verified.
            33 	401 	Invalid request token: The request token is either expired or invalid.
            35 	401 	Invalid token.
            36 	401 	This token hasn't been granted write permission by the user.
            37 	404 	The requested session could not be found.
            38 	401 	You don't have permission to edit this resource.
            39 	401 	This resource is private.
             8 	403 	Duplicate entry: The data you tried to submit already exists.
            45 	403 	This user has been suspended.
            6 	404 	Invalid id: The pre-requisite id is invalid or not found.
            34 	404 	The resource you requested could not be found.
            4 	405 	Invalid format: This service doesn't exist in that format.
            42 	405 	This request method is not supported for this resource.
            19 	406 	Invalid accept header.
            5 	422 	Invalid parameters: Your request parameters are incorrect.
            20 	422 	Invalid date range: Should be a range no longer than 14 days.
            41 	422 	This request token hasn't been approved by the user.
            25 	429 	Your request count (#) is over the allowed limit of (40).

            Server error, try again?
   LOG         11 	500 	Internal error: Something went wrong, contact TMDb.
            15 	500 	Failed.
            44 	500 	The ID is invalid.
            2 	501 	Invalid service: this service does not exist.
            43 	502 	Couldn't connect to the backend server.
    RETRY         9 	503 	Service offline: This service is temporarily offline, try again later.
            46 	503 	The API is undergoing maintenance. Try again later.
    RETRY        24 	504 	Your request to the backend server timed out. Try again.
        '''

        status_code = response.status_code  # ex. 200
        reason: str = response.reason  # ex: 'OK'
        # action: ok, retry, error
        if status_code in range(200, 300):
            return JsonReturnCode.OK

        elif status_code in range(400, 500):
            cls._logger.info(f'Failure getting information: {msg} '
                             f'status: {status_code} reason: {reason} '
                             f'url: {url}')
            return JsonReturnCode.FAILURE_NO_RETRY

        elif status_code in range(500, 502):
            cls._logger.warning(f'RandomTrailers error getting: {msg} '
                                f'status: {status_code} reason: {reason} '
                                f'url: {url}')
            return JsonReturnCode.FAILURE_NO_RETRY

        elif status_code in range(502, 505):
            cls._logger.debug(f'Temporary problem getting {msg} '
                              f'status: {status_code} reason: {reason}. Retry Later')
            return JsonReturnCode.FAILURE_RETRY

        elif status_code in range(505, 600):
            cls._logger.warning(f'RandomTrailers error getting: {msg} '
                                f'status: {status_code} reason: {reason} '
                                f'url: {url}')
            return JsonReturnCode.FAILURE_NO_RETRY

        else:
            cls._logger.info(f'Unknown error getting: {msg} '
                             f'status: {status_code} reason: {reason} '
                             f'url: {url}')
            return JsonReturnCode.FAILURE_NO_RETRY

    @staticmethod
    def abort_checker(dct: Dict[str, Any]) -> Dict[str, Any]:
        """

        :param dct:
        :return:
        """
        Monitor.throw_exception_if_abort_requested()
        return dct


# Force initialization of config_logger
JsonUtilsBasic.class_init()
