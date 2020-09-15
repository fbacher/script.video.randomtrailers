# -*- coding: utf-8 -*-

'''
Created on Feb 12, 2019

@author: Frank Feuerbacher
'''

from common.imports import *

import threading
from logging import *
import queue
import sys

import xbmc
import xbmcgui

from common.monitor import Monitor
from common.constants import Constants
from common.exceptions import AbortException
from common.settings import Settings
from frontend.front_end_bridge import FrontendBridge
from common.logger import (LazyLogger, Trace)

from frontend import random_trailers_ui

REMOTE_DBG = True

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        xbmc.log('Trying to attach to debugger', xbmc.LOGDEBUG)
        # os.environ["DEBUG_CLIENT_SERVER_TRANSLATION"] = "True"
        # os.environ['PATHS_FROM_ECLIPSE_TO_PYTHON'] =\
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
            raise sys.exc_info()
        except Exception as e:
            xbmc.log(
                ' Looks like remote debugger was not started prior to plugin start', xbmc.LOGDEBUG)

    except ImportError:
        msg = 'Error:  You must add org.python.pydev.debug.pysrc to your PYTHONPATH.'
        xbmc.log(msg, xbmc.LOGDEBUG)
        sys.stderr.write(msg)
        sys.exit(1)
    except BaseException:
        xbmc.log('Waiting on Debug connection', xbmc.LOGDEBUG)

RECEIVER = None
xbmc.log('__file__:' + __file__ + 'module:' + __name__ , xbmc.LOGDEBUG)

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class MainThreadLoop(object):
    """
        Kodi's Monitor class has some quirks in it that strongly favor creating
        it from the main thread as well as callng xbmc.sleep/xbmc.wait_for_abort.
        The main issue is that a Monitor event can not be received until
        xbmc.sleep/xbmc.wait_for_abort is called FROM THE SAME THREAD THAT THE
        MONITOR WAS INSTANTIATED FROM. Further, it may be the case that
        other plugins may be blocked as well. For this reason, the main thread
        should not be blocked for too long.
    """
    _advanced_player = None
    _callableTasks = None
    _is_screensaver = None
    _logger = None
    _start_ui = None

    def __init__(self, is_screensaver: bool) -> None:
        """

        :param is_screensaver:
        """
        pass

    @classmethod
    def class_init(cls, is_screensaver: bool) -> None:
        cls._logger = module_logger.getChild(cls.__name__)
        if cls._logger.isEnabledFor(LazyLogger.DEBUG):
            cls._logger.enter()
        Trace.enable_all()
        Settings.save_settings()
        cls._advanced_player = None
        cls._is_screensaver = is_screensaver
        cls._start_ui = None
        cls._callableTasks = queue.Queue(maxsize=0)

    # Calls that need to be performed on the main thread

    @classmethod
    def startup(cls) -> None:
        """

        :return:
        """

        FrontendBridge()  # Initialize
        if not cls._is_screensaver and Settings.prompt_for_settings():
            cls.configure_settings()
        try:
            thread = threading.Thread(target=cls.ui_thread_runner,
                                      name='ui_thread')
            thread.start()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            module_logger.exception('')

        Monitor.set_startup_complete()
        cls.event_processing_loop()

    @classmethod
    def event_processing_loop(cls) -> None:
        """

        :return:
        """
        cls._logger.enter()

        try:
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
                    task = cls._callableTasks.get(block=False)
                    cls.run_task(task)
                except queue.Empty:
                    pass

            Monitor.throw_exception_if_abort_requested(timeout=timeout)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            cls._logger.exception(e)

    @classmethod
    def ui_thread_runner(cls):
        try:
            cls._start_ui = random_trailers_ui.StartUI(cls._is_screensaver)
            cls._start_ui.start()
        except AbortException:
            pass  # Thread to die
        except Exception:
            cls._logger.exception('')

    @classmethod
    def run_on_main_thread(cls, callable_class: Callable) -> None:
        """

        :param callable_class:
        :return:
        """
        cls._callableTasks.put(callable_class)

    @classmethod
    def run_task(cls, callable_class: Callable) -> None:
        """

        :param callable_class:
        :return:
        """
        if cls._logger.isEnabledFor(LazyLogger.DEBUG):
            cls._logger.enter()
        try:
            callable_class()
        except AbortException:
            pass
        except Exception:
            cls._logger.exception('')

    @classmethod
    def configure_settings(cls) -> None:
        """
            Allow Settings to be modified inside of addon
        """

        if cls._logger.isEnabledFor(LazyLogger.DEBUG):
            cls._logger.enter()
        Constants.FRONTEND_ADDON.openSettings()

        return


def bootstrap_random_trailers(is_screensaver: bool) -> None:
    """
    :param is_screensaver: True when launched as a screensaver
    :return:
    """
    try:
        Monitor.register_settings_changed_listener(
            Settings.on_settings_changed)
        Monitor.register_settings_changed_listener(
            LazyLogger.on_settings_changed)

        MainThreadLoop.class_init(is_screensaver)
        MainThreadLoop.startup()

        # LazyLogger can be unusable during shutdown

        if module_logger.isEnabledFor(LazyLogger.DEBUG):
            module_logger.exit('Exiting plugin')

    except AbortException:
        pass
    except Exception:
        module_logger.exception('')
    finally:
        if REMOTE_DBG:
            try:
                pydevd.stoptrace()
            except Exception:
                pass
        exit(0)


def bootstrap_unit_test():
    pass


if __name__ == '__main__':  # TODO: need quick exit if backend is not running
    if xbmc.Player().isPlaying():
        exit(0)
    run_random_trailers = True
    argc = len(sys.argv) - 1
    is_screensaver = False
    is_unit_test = False
    for arg in sys.argv[1:]:
        if arg == 'screensaver':
            is_screensaver = True
        if arg == 'unittest':
            is_unit_test = True

    if run_random_trailers:
        bootstrap_random_trailers(is_screensaver)
    elif is_unit_test:
        bootstrap_unit_test()
