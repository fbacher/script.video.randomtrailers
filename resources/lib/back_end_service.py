# -*- coding: utf-8 -*-

"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""

import os
import io
import sys
import stat
import threading
from queue import Queue, Empty

import xbmc

from common.imports import *
from backend.back_end_bridge import BackendBridge
from common.constants import Constants
from common.monitor import Monitor
from common.exceptions import AbortException
from common.settings import Settings
from common.critical_settings import CriticalSettings
from backend.api import load_trailers
from common.logger import (LazyLogger)

from discovery.playable_trailer_service import PlayableTrailerService
from cache.cache_manager import CacheManager


REMOTE_DBG = True

if REMOTE_DBG:
    # Make pydev debugger work for auto reload.
    # Note pydevd module needs to be copied in XBMC\system\python\Lib\pysrc
    try:
        # if config_logger.isEnabledFor((LazyLogger.DEBUG)):
        #     config_logger.debug('%s', 'Trying to attach to debugger',
        #                  kwargs={'lazy_logger': False})
        #     config_logger.debug('%s %s', 'Python path:', str(
        #         sys.path), kwargs={'lazy_logger': False})

        # os.environ["DEBUG_CLIENT_SERVER_TRANSLATION"] = "True"
        # os.environ['PATHS_FROM_ECLIPSE_TO_PYTON'] =\
        #    '/home/fbacher/.kodi/addons/script.video/randomtrailers/resources/lib/random_trailers_ui.py:' +\
        #    '/home/fbacher/.kodi/addons/script.video/randomtrailers/resources/lib/random_trailers_ui.py'

        '''
            If the server (your python process) has the structure
                /user/projects/my_project/src/package/module1.py

            and the client has:
                c:\my_project\src\package\module1.py

            the PATHS_FROM_ECLIPSE_TO_PYTHON would have to be:
                PATHS_FROM_ECLIPSE_TO_PYTHON = [(r'c:\my_project\src', r'/user/projects/my_project/src')
            # with the addon script.module.pydevd, only use `import pydevd`
            # import pysrc.pydevd as pydevd
        '''
        sys.path.append('/home/fbacher/.kodi/addons/script.module.pydevd/lib/pydevd.py'
                        )
        import pydevd
        # stdoutToServer and stderrToServer redirect stdout and stderr to eclipse
        # console
        try:
            pydevd.settrace('localhost', stdoutToServer=True,
                            stderrToServer=True)
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            xbmc.log(
                ' Looks like remote debugger was not started prior to plugin start',
                xbmc.LOGDEBUG)

    except ImportError:
        msg = 'Error:  You must add org.python.pydev.debug.pysrc to your PYTHONPATH.'
        xbmc.log(msg, xbmc.LOGDEBUG)
        sys.stderr.write(msg)
        sys.exit(1)
    except BaseException:
        xbmc.log('Waiting on Debug connection', xbmc.LOGERROR)

RECEIVER = None
module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class MainThreadLoop(object):
    """
        Kodi's Monitor class has some quirks in it that strongly favors creating
        it from the main thread as well as calling xbmc.sleep/xbmc.wait_for_abort.
        The main issue is that a Monitor event can not be received until
        xbmc.sleep/xbmc.wait_for_abort is called FROM THE SAME THREAD THAT THE
        MONITOR WAS INSTANTIATED FROM. Further, it may be the case that
        other plugins may be blocked as well. For this reason, the main thread
        should not be blocked for too long.
    """

    _singleton = None
    profiler = None
    _logger = None

    def __init__(self):
        # type: () -> None
        """

        """

        type(self)._logger = module_logger.getChild(
            self.__class__.__name__)
        if type(self)._logger.isEnabledFor(LazyLogger.DEBUG):
            type(self)._logger.debug('%s', 'Enter', lazy_logger=False)

        # Calls that need to be performed on the main thread

        self._callableTasks = Queue(maxsize=0)
        MainThreadLoop._singleton = self

    @staticmethod
    def get_instance():
        # type: () -> MainThreadLoop
        """

        :return:
        """

        if MainThreadLoop._singleton is None:
            MainThreadLoop()

        return MainThreadLoop._singleton

    def event_processing_loop(self):
        # type: () -> None
        """

        :return:
        """
        if type(self)._logger.isEnabledFor(LazyLogger.DEBUG):
            type(self)._logger.debug('%s', 'Enter', lazy_logger=False)

        try:
            # Cheat and start the back_end_bridge here, although this method
            # should just be a loop.

            self.start_back_end_bridge()

            # For the first 10 seconds use a short timeout so that initialization
            # stuff is handled quickly. Then revert to 1 second checks

            initial_timeout = 0.05
            switch_timeouts_count = 10 * 20

            i = 0
            timeout = initial_timeout

            # Using _wait_for_abort to
            # cause Monitor to query Kodi for Abort on the main thread.
            # If this is not done, then Kodi will get constipated
            # sending/receiving events to plugins.

            while not Monitor._wait_for_abort(timeout=timeout):
                i += 1
                if i == switch_timeouts_count:
                    timeout = 0.10

                try:
                    task = self._callableTasks.get(block=False)
                    self.run_task(task)
                except Empty as e:
                    pass

            Monitor.throw_exception_if_abort_requested(timeout=timeout)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            type(self)._logger.exception('')

    def start_back_end_bridge(self):
        BackendBridge(PlayableTrailerService())

    def run_on_main_thread(self, callable_class):
        # type: (Callable[[None], None]) -> None
        """

        :param callable_class:
        :return:
        """
        self._callableTasks.put(callable_class)

    def run_task(self, callable_class):
        # type: (Optional[Callable[[None], None]]) -> None
        """

        :param callable_class:
        :return:
        """
        if type(self)._logger.isEnabledFor(LazyLogger.DEBUG):
            type(self)._logger.debug('%s', 'Enter', lazy_logger=False)
        try:
            callable_class()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            type(self)._logger.exception('')


def profiler_thread():
    # type: () -> None

    finished = False
    try:
        num = 0
        while not finished:
            num += 1
            MainThreadLoop.profiler.enable()
            f = io.open('/tmp/profile_' + str(num), mode='wb')
            import pstats
            stats = pstats.Stats(
                MainThreadLoop.profiler, stream=f)

            Monitor.throw_exception_if_abort_requested(timeout=5 * 60)
            MainThreadLoop.profiler.create_stats()
            stats.print_stats()
            f.close()
    except AbortException:
            reraise(*sys.exc_info())
    except Exception:
        module_logger.exception('')


def startup_non_main_thread():
    # type: () -> None
    """

    :return:
    """
    if module_logger.isEnabledFor(LazyLogger.DEBUG):
        module_logger.debug('%s', 'Enter', lazy_logger=False)

    Settings.save_settings()
    Monitor.register_settings_changed_listener(
        Settings.on_settings_changed)
    Monitor.register_settings_changed_listener(
        LazyLogger.on_settings_changed)
    try:
        Settings.get_locale()
        if module_logger.isEnabledFor(LazyLogger.DEBUG):
            Settings.getLang_iso_639_1()
            Settings.getLang_iso_639_2()
            Settings.getLang_iso_3166_1()
    except AbortException:
        reraise(*sys.exc_info())
    except Exception:
        pass
    load_trailers()

    # Start the periodic garbage collector

    CacheManager.get_instance().start_cache_garbage_collection_thread()
    Monitor.register_settings_changed_listener(load_trailers)


def bootstrap_random_trailers():
    # type: () -> None
    """
    First function called at startup.

    Note this means that this is running on the main thread

    :return:
    """

    try:
        if MainThreadLoop.profiler is not None:
            MainThreadLoop.profiler.enable()
            thread = threading.Thread(
                target=profiler_thread,
                name='back_end_service.profiler_thread')
            thread.start()

        main_loop = MainThreadLoop.get_instance()
        try:
            thread = threading.Thread(
                target=startup_non_main_thread,
                name='back_end_service.startup_main_thread')
            thread.start()
        except Exception:
            module_logger.exception('')

        main_loop.event_processing_loop()

    except AbortException as e:
        pass
    except Exception as e:
        module_logger.exception('')
    finally:
        if REMOTE_DBG:
            try:
                pydevd.stoptrace()
            except Exception:
                pass
        exit(0)


def post_install():
    #
    # Ensure execute permission

    cmd_path = os.path.join(Constants.BACKEND_ADDON_UTIL.PATH,
                            'resources', 'lib', 'shell',
                            'ffmpeg_normalize.sh')

    current_permissions = stat.S_IMODE(os.lstat(cmd_path).st_mode)
    os.chmod(cmd_path, current_permissions | stat.S_IEXEC | stat.S_IREAD)


def bootstrap_unit_test():
    from test.backend_test_suite import (BackendTestSuite)
    module_logger.enter()
    suite = BackendTestSuite()
    suite.run_suite()


if __name__ == '__main__':  # TODO: need quick exit if backend is not running
    try:
        run_random_trailers = True
        argc = len(sys.argv) - 1
        is_unit_test = False
        for arg in sys.argv[1:]:
            if arg == 'unittest':
                is_unit_test = True
                run_random_trailers = False
        if run_random_trailers:
            if Constants.FRONTEND_ADDON_UTIL is None:
                module_logger.info('The plugin: ', Constants.FRONTEND_ID,
                                   'is not installed. Exiting')
                exit(0)

            post_install()
            profile = False
            if profile:
                import cProfile
                MainThreadLoop.profiler = cProfile.Profile()
                MainThreadLoop.profiler.runcall(bootstrap_random_trailers)
            else:
                bootstrap_random_trailers()
        elif is_unit_test:
            bootstrap_unit_test()
    except AbortException:
        pass  # Die, Die, Die
