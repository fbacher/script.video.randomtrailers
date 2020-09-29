"""
Created on Apr 5, 2019

@author: Frank Feuerbacher
"""

from common.imports import *

import datetime
import glob
import subprocess
from subprocess import CalledProcessError
import json
import os
import sys
import threading

from common.constants import Constants
from common.logger import (LazyLogger, Trace)
from common.monitor import Monitor
from common.exceptions import AbortException

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)
PYTHON_PATH = Constants.YOUTUBE_DL_ADDON_LIB_PATH
PYTHON_EXEC = sys.executable
YOUTUBE_DL_PATH = os.path.join(Constants.BACKEND_ADDON_UTIL.PATH,
                               'resources', 'lib', 'shell', 'youtube_dl_main.py')
# Delay one hour after encountering 429 (too many requests)
RETRY_DELAY = datetime.timedelta(0, float(60 * 2))


class YDStreamExtractorProxy(object):
    """

    """
    # Initialize to a year ago
    _too_many_requests_timestamp = datetime.datetime.now() - datetime.timedelta(365)
    _initial_tmr_timestamp = None
    _logger = module_logger.getChild('YDStreamExtractorProxy')

    def __init__(self) -> None:
        """

        """
        clz = YDStreamExtractorProxy

        self._success = None
        self._command_process = None
        self._thread = None
        self._error = 0
        pass

    @staticmethod
    def get_youtube_wait_seconds() ->  ClassVar[datetime.timedelta]:
        clz = YDStreamExtractorProxy

        seconds_to_wait = (clz._too_many_requests_timestamp
                           - datetime.datetime.now()).total_seconds()
        if seconds_to_wait < 0:
            seconds_to_wait = 0
        return seconds_to_wait

    def get_video(self, url, folder, movie_id):
        # type: (str, str, Union[int, str]) -> Tuple[int, Optional[MovieType]]
        """

        :param url:
        :param folder:
        :param movie_id:
        :return:
        """
        clz = YDStreamExtractorProxy

        if clz._too_many_requests_timestamp > datetime.datetime.now():
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                expiration_time =  datetime.datetime.strftime(
                    clz._too_many_requests_timestamp,
                    '%a, %d %b %Y %H:%M:%S')
                clz._logger.debug_extra_verbose(
                    f'Blocking download of {url} due to TOO MANY REQUESTS (429)'
                    f' until: {expiration_time}')
            return 429, None

        env = os.environ.copy()
        env['PYTHONPATH'] = PYTHON_PATH

        # The embedded % fields are for youtube_dl to fill  in.

        template = os.path.join(folder, f'_rt_{movie_id}_%(title)s.%(ext)s')
        args = [PYTHON_EXEC, YOUTUBE_DL_PATH, '--print-json', '--no-mtime', url,
                '-o', template]

        trailer = None
        try:
            self._command_process = subprocess.Popen(
                args, stdin=None, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False, env=env, close_fds=True, universal_newlines=True)

            self._thread = threading.Thread(
                target=self.stderr_reader, name='Stderr Reader')
            self._thread.start()

            # while not Monitor.wait_for_abort(timeout=0.1):
            #    try:
            #        rc = self._command_process.wait(0.0)
            #        break  # Complete
            #    except subprocess.TimeoutExpired:
            #        pass

            Monitor.throw_exception_if_abort_requested()
            json_output = self._command_process.stdout.read()
            Monitor.throw_exception_if_abort_requested()
            self._thread.join(timeout=0.1)
            if json_output is not None and len(json_output) != 0 and self._error == 0:
                trailer = None
                try:
                    trailer = json.loads(json_output)
                except Exception as e:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                        clz._logger.exception(f'json: {json}')

                trailer_file = os.path.join(folder, f'_rt_{movie_id}*')
                trailer_file = glob.glob(trailer_file)
                if trailer_file is not None:
                    if len(trailer_file) > 0:
                        trailer_file = trailer_file[0]
                #
                # Don't know why, but sometimes youtube_dl returns incorrect
                # file extension

                if trailer_file != trailer['_filename']:
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                            'youtube_dl gave incorrect file name:',
                            trailer['_filename'], 'changing to:',
                            trailer_file)

                    trailer['_filename'] = trailer_file

        except AbortException:
            try:
                self._command_process.terminate()
            except Exception:
                pass
            trailer = None
            to_delete = os.path.join(folder, f'_rt_{movie_id}*')
            to_delete = glob.glob(to_delete)
            for aFile in to_delete:
                try:
                    os.remove(aFile)
                except Exception as e:
                    pass
            reraise(*sys.exc_info())
        except CalledProcessError as e:
            self._success = False
            trailer = None
        except Exception as e:
            self._success = False
            clz._logger.exception(e)
            try:
                self._command_process.terminate()
            except Exception:
                pass
            trailer = None
            to_delete = os.path.join(folder, f'_rt_{movie_id}*')
            to_delete = glob.glob(to_delete)
            for aFile in to_delete:
                try:
                    os.remove(aFile)
                except Exception as e:
                    pass

        if self._error == 0 and (not self._success or trailer is None):
            self._error = 1

        return self._error, trailer

    def get_info(self, url: str) -> Tuple[int, Optional[List[MovieType]]]:
        """

        :param url:
        :return:
        """
        clz = YDStreamExtractorProxy

        if clz._too_many_requests_timestamp > datetime.datetime.now():
            if clz._logger.isEnabledFor(
                    LazyLogger.DEBUG_EXTRA_VERBOSE):
                expiration_time = datetime.datetime.strftime(
                    clz._too_many_requests_timestamp,
                    '%a, %d %b %Y %H:%M:%S')
                clz._logger.debug_extra_verbose(
                    f'Blocking download of {url} due to TOO MANY REQUESTS (429)'
                    f' until: {expiration_time}')
            return 429, None

        python_exec = sys.executable

        cmdPath = os.path.join(Constants.BACKEND_ADDON_UTIL.PATH,
                               'resources', 'lib', 'shell', 'youtube_dl_main.py')

        env = os.environ.copy()
        env['PYTHONPATH'] = PYTHON_PATH
        args = [python_exec, cmdPath, '--print-json', '--skip-download', url]

        remaining_attempts = 10
        trailer_info: Optional[List[Dict[str, Any]]] = None
        while remaining_attempts > 0:
            try:
                commmand_process = subprocess.Popen(
                    args, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    shell=False, env=env, close_fds=True, universal_newlines=True)

                try:
                    while commmand_process.poll() is None:
                        Monitor.throw_exception_if_abort_requested(
                            timeout=0.10)
                except AbortException:
                    try:
                        commmand_process.terminate()
                    except Exception:
                        pass
                    finally:
                        Monitor.throw_exception_if_abort_requested()

                stderr = commmand_process.stderr.read()
                #output = commmand_process.stdout.read()
                lines = []
                finished = False
                while not finished:
                    Monitor.throw_exception_if_abort_requested()
                    line = commmand_process.stdout.readline()
                    if not line:
                        break
                    lines.append(line)

                trailer_info = []
                # json_text = []
                for line in lines:
                    single_trailer_info: Dict[str, Any] = json.loads(line)

                    # json_text.append(json.dumps(
                    # single_trailer_info, indent=3, sort_keys=True))
                    trailer_info.append(single_trailer_info)

                # if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                #   json_text_buffer = '\n\n'.join(json_text)
                #   clz._logger.debug('itunes trailer info:', json_text_buffer)
                break
            except AbortException:
                reraise(*sys.exc_info())
            except CalledProcessError as e:
                remaining_attempts -= 1
                # output = e.output
                # stderr = e.stderr
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    clz._logger.debug_verbose('Failed to download site info for:', url,
                                               'remaining_attempts:', remaining_attempts)
                    # clz._logger.debug_verbose('output:', output)
                    # clz._logger.debug_verbose('stderr:', stderr)
                trailer_info = None
                Monitor.throw_exception_if_abort_requested(timeout=70.0)
            except Exception as e:
                remaining_attempts -= 1
                clz._logger.exception('')
                # output = e.output
                # stderr = e.stderr
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    clz._logger.debug_verbose('Failed to download site info for:', url,
                                               'remaining_attempts:', remaining_attempts)
                    #clz._logger.debug('output:', output)
                    #clz._logger.debug('stderr:', stderr)
                trailer_info = None

        return 0, trailer_info

    def get_tfh_index(self, url: str, trailer_handler) -> int:
        """

        :param url:
        :param trailer_handler:
        :return:
        """
        clz = YDStreamExtractorProxy

        if clz._too_many_requests_timestamp > datetime.datetime.now():
            if clz._logger.isEnabledFor(
                    LazyLogger.DEBUG_EXTRA_VERBOSE):
                expiration_time = datetime.datetime.strftime(
                    clz._too_many_requests_timestamp,
                    '%a, %d %b %Y %H:%M:%S')
                clz._logger.debug_extra_verbose(
                    f'Blocking download of {url} due to TOO MANY REQUESTS (429)'
                    f' until: {expiration_time}')
            return 429

        python_exec = sys.executable

        cmd_path = os.path.join(Constants.BACKEND_ADDON_UTIL.PATH,
                                'resources', 'lib', 'shell', 'youtube_dl_main.py')

        env = os.environ.copy()
        env['PYTHONPATH'] = PYTHON_PATH
        args = [python_exec, cmd_path, '--playlist-random', '--yes-playlist',
                '--dump-json', url]

        remaining_attempts = 1
        line = None
        lines_read = 0
        self._success = True
        while remaining_attempts > 0:
            try:
                # It can take 20 minutes to dump entire TFH index. Read
                # as it is produced

                self._command_process = subprocess.Popen(
                    args, bufsize=1, stdin=None, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False, env=env, close_fds=True, universal_newlines=True)

                self._thread = threading.Thread(
                    target=self.stderr_reader, name='Stderr Reader')
                self._thread.start()

                finished = False
                while not finished:
                    Monitor.throw_exception_if_abort_requested()
                    line = self._command_process.stdout.readline()
                    if not line or not self._success:
                        break
                    #
                    # Returns True when no more trailers are wanted

                    finished = trailer_handler(line)
                    lines_read += 1

                break
            except AbortException:
                try:
                    self._command_process.terminate()
                except Exception:
                    pass
                reraise(*sys.exc_info())
            except CalledProcessError as e:
                remaining_attempts -= 1
                if remaining_attempts == 0:
                    self._success = False
                # output = e.output
                # stderr = e.stderr
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    clz._logger.debug_verbose('Failed to download site info for:', url,
                                               'remaining_attempts:', remaining_attempts)
                    # clz._logger.debug_verbose('output:', output)
                    # clz._logger.debug_verbose('stderr:', stderr)
                trailer_info = None
            except Exception as e:
                remaining_attempts -= 1
                if remaining_attempts == 0:
                    self._success = False
                clz._logger.exception('')
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                    clz._logger.debug_verbose('Failed to download site info for:', url,
                                               'remaining_attempts:', remaining_attempts)
                    # if line:
                    #     clz._logger.debug('current response:', line)

        if lines_read == 0:
            self._success = False

        self._thread.join(timeout=0.1)
        if self._error == 0 and not self._success:
            self._error = 1

        return self._error

    def stderr_reader(self):
        #  type: () -> None
        """
        """
        clz = YDStreamExtractorProxy

        finished = False
        log_stderr = True
        error_text = ''
        try:
            while not finished:
                Monitor.throw_exception_if_abort_requested()
                try:
                    #  TODO: need non-blocking read
                    line = self._command_process.stderr.readline()
                    if not line:
                        finished = True
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose('stderr:', line)
                    if 'Error 429' in line:
                        self._error = 429
                        clz._too_many_requests_timestamp = (
                                datetime.datetime.now() + RETRY_DELAY)

                        clz._logger.info(
                            'Abandoning download. Too Many Requests')
                        self._success = False
                        error_text = ''
                        self._command_process.terminate()
                        finished = True
                    elif 'Unable to extract video data' in line:
                        self._error = 2
                    elif 'Error' in line:
                        pass
                    if log_stderr and self._error != 0:
                        error_text = error_text + line
                except subprocess.TimeoutExpired:
                    pass
        except AbortException:
            self._command_process.terminate()
            reraise(*sys.exc_info())
        except Exception as e:
            pass  # Thread dying

        if (not self._error != 429
                and clz._initial_tmr_timestamp is not None
                and  clz._logger.isEnabledFor(
                    LazyLogger.DEBUG_EXTRA_VERBOSE)):
            initial_failure = datetime.datetime.strftime(
                clz._initial_tmr_timestamp,
                '%a, %d %b %Y %H:%M:%S')
            clz._logger.debug_extra_verbose(
                'No longer blocking due to TOO MANY REQUESTS (429)'
                f' Initial failure: {initial_failure}')
            clz._initial_tmr_timestamp = None

        pass

        # If we want to save error log, need path to log to
        # if self._error != 0 and len(error_text) > 0:
