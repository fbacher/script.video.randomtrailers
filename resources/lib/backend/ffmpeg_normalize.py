# -*- coding: utf-8 -*-

"""
Created on Oct 7, 2020

@author: Frank Feuerbacher
"""

import os
import random
import subprocess
import tempfile
import threading

import xbmc

from common.constants import Constants, Movie
from common.imports import *
from common.exceptions import AbortException
from common.logger import (LazyLogger, Trace, log_entry_exit)
from common.messages import Messages
from common.monitor import Monitor
from common.settings import Settings

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(
    file_path=__file__)

'''
    Normalizes the volume of video using ffmpeg. Normalizing volumes is particularly
    helpful with trailers downloaded from youtube where volumes can be whispers
    or shouts.

    You may modify the parameters here to your taste.

    Note that you can not change newOutFileName, otherwise Random Trailers will not see
    the file.
'''


def normalize(in_file: str, out_file: str, use_compand: bool = False) -> int:
    """
    Normalize the audio of the given video file.

    Note that the specific normalization arguments were derived at quickly, using
    notes based on internet searches. More time should be spent on this. Further,
    it would be great to expose this to users to varying degree:
      -1) Using simple more-less slider
      -2) Expose ability to specify exact values

    :param in_file: input video file, which is not altered
    :param out_file:  output video file, with the normalized audio and copied video
    :param use_compand: If True, then normalize using ffmpeg 'compand', otherwise
                        use 'loudnorm' option.
    :return:
    """

    rc = 0
    ffmpeg_path = Settings.get_ffmpeg_path()
    if ffmpeg_path is None or ffmpeg_path == '':
        ffmpeg_path = 'ffmpeg'  # Assume on $PATH

    input_trailer_file = os.path.basename(in_file)
    input_trailer_file, input_trailer_extension = os.path.splitext(
        input_trailer_file)

    output_directory = os.path.dirname(out_file)
    output_trailer_file = os.path.basename(out_file)
    output_trailer_file, output_trailer_extension = os.path.splitext(
        output_trailer_file)

    output_file = os.path.join(output_directory,
                               f'compand_{output_trailer_file}{output_trailer_extension}')

    suffix = str(random.randint(0, 9999))
    tmp_dir = tempfile.gettempdir()
    first_pass_log_path = os.path.join(tmp_dir, f'random_trailer_{suffix}.tmp')

    compand_params = 'compand=attacks=0:points=-80/-900|-45/-15|-27/-9|0/-7|20/-7:gain=1'

    for ffmpeg_pass in (1, 2):
        if use_compand:
            if ffmpeg_pass == 1:
                args: List[str] = [ffmpeg_path,
                                   '-i',
                                   in_file,
                                   '-pass',
                                   '1',
                                   '-passlogfile',
                                   first_pass_log_path,
                                   '-c:v',
                                   'copy',
                                   '-filter_complex:a',
                                   compand_params,
                                   '-y',
                                   'NUL'
                                   ]

            else:  # Second pass
                args: List[str] = [ffmpeg_path,
                                   '-i',
                                   in_file,
                                   '-pass',
                                   '2',
                                   '-passlogfile',
                                   first_pass_log_path,
                                   '-c:v',
                                   'copy',
                                   '-filter_complex:a',
                                   compand_params,
                                   '-y',
                                   output_file
                                   ]
        else:  # Not compand
            if ffmpeg_pass == 1:
                args: List[str] = [ffmpeg_path,
                                   '-i',
                                   in_file,
                                   '-pass',
                                   '1',
                                   '-passlogfile',
                                   first_pass_log_path,
                                   '-c:v',
                                   'copy',
                                   '-filter:a',
                                   'loudnorm',
                                   '-y',
                                   output_file
                                   ]

            else:   # Second Pass
                args: List[str] = [ffmpeg_path,
                                   '-i',
                                   in_file,
                                   '-pass',
                                   '2',
                                   '-passlogfile',
                                   first_pass_log_path,
                                   '-c:v',
                                   'copy',
                                   '-filter:a',
                                   'loudnorm',
                                   '-y',
                                   output_file
                                   ]

        Monitor.throw_exception_if_abort_requested()
        runner = RunCommand(args, input_trailer_file)
        rc = runner.run_cmd()
        if os.path.exists(first_pass_log_path):
            os.remove(first_pass_log_path)
        if rc != 0:
            break

    return rc


class RunCommand:
    logger: LazyLogger = None

    def __init__(self, args: List[str], movie_name: str) -> None:
        RunCommand.logger = module_logger.getChild(RunCommand.__name__)
        self.args = args
        self.movie_name = movie_name
        self.rc = 0
        self.cmd_finished = False
        self.process: Optional[subprocess.Popen] = None
        self.run_thread: Union[None, threading.Thread] = None
        self.stdout_thread: Union[None, threading.Thread] = None
        self.stderr_thread: Union[None, threading.Thread] = None
        self.stdout_lines: List[str] = []
        self.stderr_lines: List[str] = []

    def run_cmd(self) -> int:
        self.rc = 0
        self.run_thread = threading.Thread(target=self.run_worker,
                                           name='normalize audio')
        Monitor.throw_exception_if_abort_requested()
        self.run_thread.start()

        self.cmd_finished = False
        while not Monitor.wait_for_abort(timeout=0.1):
            try:
                if self.process is not None:  # Wait to start
                    self.rc = self.process.poll()
                    if self.rc is not None:
                        self.cmd_finished = True
                        break  # Complete
            except subprocess.TimeoutExpired:
                pass

        if not self.cmd_finished:
            # Shutdown in process
            self.process: subprocess.Popen
            self.process.kill()  # SIGKILL. Should cause stderr & stdout to exit
            self.rc = 9

        if self.run_thread.is_alive():
            self.run_thread.join(timeout=1.0)
        if self.stdout_thread.is_alive():
            self.stdout_thread.join(timeout=0.2)
        if self.stderr_thread.is_alive():
            self.stderr_thread.join(timeout=0.2)
        Monitor.throw_exception_if_abort_requested(timeout=0.0)
        # If abort did not occur, then process finished

        if self.rc != 0:
            self.log_output()

        return self.rc

    def run_worker(self) -> None:
        clz = RunCommand
        rc = 0
        env = os.environ.copy()
        try:
            if xbmc.getCondVisibility('System.Platform.Windows'):
                # Prevent console for ffmpeg from opening

                self.process = subprocess.Popen(
                    self.args, stdin=None, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, shell=False, universal_newlines=True, env=env,
                    close_fds=True, creationflags=subprocess.DETACHED_PROCESS)
            else:
                self.process = subprocess.Popen(
                    self.args, stdin=None, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, shell=False, universal_newlines=True, env=env,
                    close_fds=True)
            self.stdout_thread = threading.Thread(target=self.stdout_reader,
                                                  name='normalize stdout reader')
            Monitor.throw_exception_if_abort_requested()
            self.stdout_thread.start()

            self.stderr_thread = threading.Thread(target=self.stderr_reader,
                                                  name='normalize stderr reader')
            self.stderr_thread.start()
        except AbortException as e:
            pass  # Let thread die
        except Exception as e:
            clz.logger.exception(e)

    def stderr_reader(self):
        if Monitor.is_abort_requested():
            self.process.kill()

        clz = RunCommand
        finished = False
        while not (finished or self.cmd_finished):
            try:
                line = self.process.stderr.readline()
                if len(line) > 0:
                    self.stderr_lines.append(line)
            except ValueError as e:
                if self.process.poll() is not None:
                    # Command complete
                    finished = True
                    break
                else:
                    clz.logger.exception(e)
                    finished = True
            except AbortException as e:
                finished = True
            except Exception as e:
                clz.logger.exception(e)
                finished = True

    def stdout_reader(self):
        if Monitor.is_abort_requested():
            self.process.kill()

        clz = RunCommand
        finished = False
        while not (finished or self.cmd_finished):
            try:
                line = self.process.stdout.readline()
                if len(line) > 0:
                    self.stdout_lines.append(line)
            except ValueError as e:
                if self.process.poll() is not None:
                    # Command complete
                    finished = True
                    break
                else:
                    clz.logger.exception(e)
                    finished = True
            except AbortException as e:
                finished = True
            except Exception as e:
                clz.logger.exception(e)
                finished = True

    def log_output(self):
        if Monitor.is_abort_requested():
            return

        clz = RunCommand
        if clz.logger.isEnabledFor(LazyLogger.DEBUG):
            clz.logger.debug(
                f'ffmpeg failed for {self.movie_name} rc: {self.rc}')
            if clz.logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                stdout = '\n'.join(self.stdout_lines)
                clz.logger.debug_verbose(f'STDOUT: {stdout}')
                stderr = '\n'.join(self.stderr_lines)
                clz.logger.debug_verbose(f'STDERR: {stderr}')
