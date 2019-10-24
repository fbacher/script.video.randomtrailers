"""
Created on Apr 5, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import six
import glob
import subprocess
from subprocess import CalledProcessError
import json
import os
import sys
import threading

from kodi_six import utils

from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                      TextType, MovieType, DEVELOPMENT, RESOURCE_LIB)
from common.constants import Constants
from common.logger import (Logger, LazyLogger, Trace)
from common.monitor import Monitor
from common.exceptions import AbortException, ShutdownException

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger(
    ).getChild('backend.yd_stream_extractor_proxy')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class YDStreamExtractorProxy(object):
    """

    """
    _instance = None

    def __init__(self):
        # type: () -> None
        """

        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        pass

    @staticmethod
    def get_instance():
        # type: () -> YDStreamExtractorProxy
        """

        :return:
        """
        if YDStreamExtractorProxy._instance is None:
            YDStreamExtractorProxy._instance = YDStreamExtractorProxy()
        return YDStreamExtractorProxy._instance

    def get_video(self, url, folder, movie_id):
        # type: (TextType, TextType, Union[int, TextType]) -> MovieType
        """

        :param url:
        :param folder:
        :param movie_id:
        :return:
        """
        python_exec = sys.executable
        PYTHONPATH = Constants.YOUTUBE_DL_ADDON_LIB_PATH
        template = os.path.join(
            folder, '_rt_' + str(movie_id) + '_%(title)s.%(ext)s')

        cmdPath = os.path.join(Constants.BACKEND_ADDON_UTIL.PATH,
                               'resources', 'lib', 'shell', 'youtube_dl_main.py')

        env = os.environ.copy()
        env['PYTHONPATH'] = PYTHONPATH
        args = [python_exec, cmdPath, '--print-json',
                '--no-mtime', url, '-o', template]
        trailer = None
        try:
            output = subprocess.check_output(
                args, stdin=None, stderr=None, shell=False, env=env)
            output = utils.py2_decode(output)
            trailer = json.loads(output)
            trailer_file = os.path.join(folder, '_rt_' + str(movie_id) + '*')
            trailer_file = glob.glob(trailer_file)
            if trailer_file is not None:
                if len(trailer_file) > 0:
                    trailer_file = trailer_file[0]
            #
            # Don't know why, but sometimes youtube_dl returns incorrect
            # file extension

            if trailer_file != trailer['_filename']:
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('youtube_dl gave incorrect file name:',
                                       trailer['_filename'], 'changing to:',
                                       trailer_file)

                trailer['_filename'] = trailer_file

        except (AbortException, ShutdownException) as e:
            trailer = None
            to_delete = os.path.join(folder, '_rt_' + str(movie_id) + '*')
            to_delete = glob.glob(to_delete)
            for aFile in to_delete:
                os.remove(aFile)
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            trailer = None
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Failed to download trailer for:', url,
                                   'to folder:', folder)
            to_delete = os.path.join(folder, '_rt_' + str(movie_id) + '*')
            to_delete = glob.glob(to_delete)
            for aFile in to_delete:
                os.remove(aFile)
        finally:
            return trailer

    def get_info(self, url):
        # type: (TextType) -> MovieType
        """

        :param url:
        :return:
        """
        python_exec = sys.executable
        PYTHONPATH = Constants.YOUTUBE_DL_ADDON_LIB_PATH

        cmdPath = os.path.join(Constants.BACKEND_ADDON_UTIL.PATH,
                               'resources', 'lib', 'shell', 'youtube_dl_main.py')

        env = os.environ.copy()
        env['PYTHONPATH'] = PYTHONPATH
        args = [python_exec, cmdPath, '--print-json', '--skip-download', url]

        remaining_attempts = 10
        trailer_info = None
        while remaining_attempts > 0:
            try:
                commmand_process = subprocess.Popen(
                    args, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    shell=False, env=env, close_fds=True, universal_newlines=True)
                commmand_process.wait()

                stderr = commmand_process.stderr.read()
                #output = commmand_process.stdout.read()
                lines = []
                finished = False
                while not finished:
                    line = commmand_process.stdout.readline()
                    if not line:
                        break
                    lines.append(utils.py2_decode(line))

                trailer_info = []
                # json_text = []
                for line in lines:
                    single_trailer_info = json.loads(line)

                    # json_text.append(json.dumps(
                    # single_trailer_info, indent=3, sort_keys=True))
                    trailer_info.append(single_trailer_info)

                # if self._logger.isEnabledFor(Logger.DEBUG):
                #   json_text_buffer = '\n\n'.join(json_text)
                #   self._logger.debug('itunes trailer info:', json_text_buffer)
                break
            except (CalledProcessError) as e:
                remaining_attempts -= 1
                output = e.output
                stderr = e.stderror
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Failed to download site info for:', url,
                                       'remaining_attempts:', remaining_attempts)
                    self._logger.debug('output:', output)
                    self._logger.debug('stderr:', stderr)
                trailer_info = None
                Monitor.get_instance().throw_exception_if_shutdown_requested(delay=70.0)
            except (Exception) as e:
                remaining_attempts -= 1
                self._logger.exception('')
                # output = e.output
                # stderr = e.stderror
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Failed to download site info for:', url,
                                       'remaining_attempts:', remaining_attempts)
                    self._logger.debug('output:', output)
                    self._logger.debug('stderr:', stderr)
                trailer_info = None

        return trailer_info

    def get_tfh_index(self, url, trailer_handler):
        # type: (TextType) -> bool
        """

        :param url:
        :return:
        """
        python_exec = sys.executable
        PYTHONPATH = Constants.YOUTUBE_DL_ADDON_LIB_PATH

        cmd_path = os.path.join(Constants.BACKEND_ADDON_UTIL.PATH,
                                'resources', 'lib', 'shell', 'youtube_dl_main.py')

        env = os.environ.copy()
        env['PYTHONPATH'] = PYTHONPATH
        args = [python_exec, cmd_path, '--playlist-random', '--yes-playlist',
                '--dump-json', url]

        remaining_attempts = 10
        line = None
        lines_read = 0
        self._tfh_success = True
        while remaining_attempts > 0:
            try:
                # It can take 20 minutes to dump entire TFH index. Read
                # as it is produced

                self._tfh_command_process = subprocess.Popen(
                    args, bufsize=1, stdin=None, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False, env=env, close_fds=True, universal_newlines=True)

                self._thread = threading.Thread(
                    target=self.stderr_reader, name='Stderr Reader')
                self._thread.start()

                finished = False
                while not finished:
                    line = self._tfh_command_process.stdout.readline()
                    if not line or not self._tfh_success:
                        break
                    #
                    # Returns True when no more trailers are wanted

                    finished = trailer_handler(line)
                    lines_read += 1

                break
            except (CalledProcessError) as e:
                remaining_attempts -= 1
                if remaining_attempts == 0:
                    self._tfh_success = False
                output = e.output
                stderr = e.stderror
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Failed to download site info for:', url,
                                       'remaining_attempts:', remaining_attempts)
                    self._logger.debug('output:', output)
                    self._logger.debug('stderr:', stderr)
                trailer_info = None
                Monitor.get_instance().throw_exception_if_shutdown_requested(delay=70.0)
            except (Exception) as e:
                remaining_attempts -= 1
                if remaining_attempts == 0:
                    self._tfh_success = False
                self._logger.exception('')
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Failed to download site info for:', url,
                                       'remaining_attempts:', remaining_attempts)
                    if line:
                        self._logger.debug('current response:', line)

        if lines_read == 0:
            self._tfh_success = False

        return self._tfh_success

    def stderr_reader(self):
        #  type: () -> None
        """
        """
        finished = False
        while not finished:
            line = self._tfh_command_process.stderr.readline()
            if not line:
                break
            self._logger.info('stderr:', line)
            if 'Error 429' in line:
                self._logger.error(
                    'Abandoning download from TFH. Too Many Requests')
                self._tfh_success = False
                self._tfh_command_process.terminate()
