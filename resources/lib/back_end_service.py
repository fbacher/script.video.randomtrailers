# -*- coding: utf-8 -*-

"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
#  from time import sleep
import sys
import xbmc
from common.python_debugger import PythonDebugger
# from common.critical_settings import CriticalSettings
# from common.minimal_monitor import MinimalMonitor

#  from common import *

# CriticalSettings.set_plugin_name('rt_backend')
addon_id: str = 'rt_backend'  # CriticalSettings.ADDON_ID
REMOTE_DEBUG: bool = False

'''
import faulthandler
import signal
import io
debug_file = io.open("/home/fbacher/.kodi/temp/kodi.crash", mode='w', buffering=1,
                     newline=None,
                     encoding='ASCII')

faulthandler.register(signal.SIGUSR1, file=debug_file, all_threads=True)
'''
if REMOTE_DEBUG:
    xbmc.log('About to call PythonDebugger.enable randomtrailers.backend', xbmc.LOGINFO)
    PythonDebugger.enable(addon_id)
    xbmc.sleep(500)
    # if MinimalMonitor.abort_requested():
    #     PythonDebugger.disable()
    #     sys.exit()
try:
    pass
    # import web_pdb;

    # web_pdb.set_trace()
except Exception as e:
    pass

from common.minimal_monitor import MinimalMonitor
from common.critical_settings import CriticalSettings
addon_id: str = CriticalSettings.ADDON_ID
from common.logger import *

module_logger = BasicLogger.get_module_logger(module_path=__file__)

import locale
module_logger.debug(f'preferredencoding: {locale.getpreferredencoding()}')
language_code: str
encoding: str
language_code, encoding = locale.getlocale(locale.LC_CTYPE)
module_logger.debug(f'getdefaultlocale(LC_CTYPE)')
module_logger.debug(f'language_code default: {language_code} '
                    f'encoding: {encoding}')

LOCALE_LANGUAGE_ISO_639_1 = "language_iso_639_1"
LOCALE_LANGUAGE_ISO_639_2T = "language_iso_639_2T"
LOCALE_LANGUAGE_ISO_639_2B = "language_iso_639_2B"
LOCALE_COUNTRY_ISO_3166_1_ALPHA_2 = "country_iso_3166_1_alpha_2"
LOCALE_COUNTRY_ISO_3166_1_ALPHA_3 = "country_iso_3166_1_alpha_3"
LOCALE_CODESET = "codeset"
LOCALE_ENGLISH_LANGUAGE_NAME = "english_language_name"
LOCALE_AUDIO_LANGUAGE = "audio_language"
LOCALE_SUBTITLE_LANGUAGE = "subtitle_language"
LOCALE_NAME = "locale_name"

args: list[str] = [
    LOCALE_LANGUAGE_ISO_639_1,
    LOCALE_LANGUAGE_ISO_639_2T,
    LOCALE_LANGUAGE_ISO_639_2B,
    LOCALE_COUNTRY_ISO_3166_1_ALPHA_2,
    LOCALE_COUNTRY_ISO_3166_1_ALPHA_3,
    LOCALE_CODESET,
    LOCALE_ENGLISH_LANGUAGE_NAME,
    LOCALE_AUDIO_LANGUAGE,
    LOCALE_SUBTITLE_LANGUAGE,
    LOCALE_NAME]

name = xbmc.getLanguage(format=xbmc.ENGLISH_NAME, region=False)
xbmc.log(f'xbmc.getLanguage ENGLISH_NAME region-false: {name}', xbmc.LOGINFO)

name = xbmc.getLanguage(format=xbmc.ENGLISH_NAME, region=True)
xbmc.log(f'xbmc.getLanguage ENGLISH_NAME region-true: {name}', xbmc.LOGINFO)

name = xbmc.getLanguage(format=xbmc.ISO_639_1, region=False)
xbmc.log(f'xbmc.getLanguage ISO_639_1 region-false: {name}', xbmc.LOGINFO)

name = xbmc.getLanguage(format=xbmc.ISO_639_1, region=True)
xbmc.log(f'xbmc.getLanguage ISO_639_1 region-true: {name}', xbmc.LOGINFO)

name = xbmc.getLanguage(format=xbmc.ISO_639_2, region=False)
xbmc.log(f'xbmc.getLanguage ISO_639_2 region-false: {name}', xbmc.LOGINFO)

name = xbmc.getLanguage(format=xbmc.ISO_639_2, region=True)
xbmc.log(f'xbmc.getLanguage ISO_639_2 region-true: {name}', xbmc.LOGINFO)

'''
# getLocaleProperties only in xbmc patch
try:
    xbmc.log("Calling getLocaleProperties", xbmc.LOGINFO)
    result: list[tuple[str,str]] = xbmc.getLocaleProperties(args)
    xbmc.log("Returned from getLocalProperties", xbmc.LOGINFO)
    if len(args) != len(result):
        xbmc.log(f'Unexpected lengths args: {len(args)} result: {len(result)}', xbmc.LOGINFO)

    xbmc.log(f'result.len: {len(result)}', xbmc.LOGINFO)

    item: tuple[str, str]
    for item in result:
        xbmc.log(f'prop: {item[0]} value: {item[1]}', xbmc.LOGINFO)

    xbmc.log('Finished display of getLocalProperties', xbmc.LOGINFO)
except Exception:
    xbmc.log(f'Could not run GetLocalProperties')
'''

def exit_randomtrailers():
    if PythonDebugger.is_enabled():
        PythonDebugger.disable()
    sys.exit(0)


import threading
from common.exceptions import AbortException
from common.imports import *

class MainThreadLoop:
    """
        Kodi's Monitor class has some quirks in it that strongly favors creating
        it from the main thread as well as calling xbmc.sleep/xbmc.wait_for_abort.
        The main issue is that a Monitor event can not be received until
        xbmc.sleep/xbmc.wait_for_abort is called FROM THE SAME THREAD THAT THE
        MONITOR WAS INSTANTIATED FROM. Further, it may be the case that
        other plugins may be blocked as well. For this reason, the main thread
        should not be blocked for too long.
    """

    profiler = None

    @classmethod
    def event_processing_loop(cls) -> None:
        """

        :return:
        """
        try:
            # Cheat and start the back_end_bridge here, although this method
            # should just be a loop.

            worker_thread_initialized = False
            bridge_initialized = False

            # For the first 10 seconds use a short timeout so that initialization
            # stuff is handled quickly. Then revert to less frequent checks

            initial_timeout = 0.05
            switch_timeouts_count = 10 * 20

            # Don't start backend for about one second after start if
            # debugging is enabled in order for it to start.

            if REMOTE_DEBUG:
                start_backend_count_down = 2.0 / initial_timeout
            else:
                start_backend_count_down = 0.0

            i: int = 0
            timeout = initial_timeout

            # Using real_waitForAbort to
            # cause Monitor to query Kodi for Abort on the main thread.
            # If this is not done, then Kodi will get constipated
            # sending/receiving events to plugins.

            while not MinimalMonitor.real_waitForAbort(timeout=timeout):
                i += 1
                if i == switch_timeouts_count:
                    timeout = CriticalSettings.LONG_POLL_DELAY

                if start_backend_count_down > 0:
                    start_backend_count_down -= 1.0
                else:
                    if not worker_thread_initialized:
                        worker_thread_initialized = True
                        cls.start_backend_worker_thread()

                    if not bridge_initialized:
                        bridge_initialized = True
                        cls.start_back_end_bridge()

            MinimalMonitor.throw_exception_if_abort_requested(timeout=timeout)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            # xbmc.log('xbmc.log Exception: ' + str(e), xbmc.LOGERROR)
            module_logger.exception(e)

    @classmethod
    def start_back_end_bridge(cls) -> None:
        module_logger.debug_verbose(f'starting BackendBridge')
        from backend.back_end_bridge import BackendBridge
        from discovery.playable_trailer_service import PlayableTrailerService
        BackendBridge(PlayableTrailerService())

    @classmethod
    def start_backend_worker_thread(cls) -> None:
        try:
            import backend_service_worker
            thread = threading.Thread(
                target=backend_service_worker.startup_non_main_thread,
                name='back_end_service.startup_non_main_thread',
                daemon=False)
            thread.start()
        except Exception as e:
            xbmc.log('Exception: ' + str(e), xbmc.LOGERROR)
            # module_logger# .exception('')


def bootstrap_random_trailers() -> None:
    """
    First function called at startup.

    Note this means that this is running on the main thread

    :return:
    """

    try:
        # xbmc.log('Starting event processing loop', xbmc.LOGDEBUG)

        MainThreadLoop.event_processing_loop()
    except AbortException as e:
        pass
    except Exception as e:
        xbmc.log('Exception: ' + str(e), xbmc.LOGERROR)
        # module_logger.exception('')
    finally:
        exit_randomtrailers()


def bootstrap_unit_test() -> None:
    from test.backend_test_suite import (BackendTestSuite)
    # module_logger.enter()
    suite = BackendTestSuite()
    suite.run_suite()


if __name__ == '__main__':
    try:
        MinimalMonitor.real_waitForAbort(0.1)  # Sometimes thread name is not set
        threading.current_thread().name = 'RandomTrailers backend'
        run_random_trailers = True
        argc = len(sys.argv) - 1
        is_unit_test = False
        for arg in sys.argv[1:]:
            if arg == 'unittest':
                is_unit_test = True
                run_random_trailers = False
        if run_random_trailers:

            # This will NOT return until exiting plugin

            bootstrap_random_trailers()
            profile = False
            if profile:
                import cProfile

                # MainThreadLoop.profiler = cProfile.Profile()
                # MainThreadLoop.profiler.runcall(bootstrap_random_trailers)
        elif is_unit_test:
            bootstrap_unit_test()
    except AbortException:
        pass  # Die, Die, Die
    finally:
        exit
