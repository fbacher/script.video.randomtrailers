# -*- coding: utf-8 -*-

"""
Created on Apr 17, 2019

@author: Frank Feuerbacher
"""

from functools import wraps
import io
import inspect
import logging
import os
import sys
import threading
import traceback
from io import StringIO

import xbmc

from common.exceptions import AbortException
from common.constants import Constants
from common.critical_settings import CriticalSettings
from common.imports import *

TOP_PACKAGE_PATH = Constants.PYTHON_ROOT_PATH

if hasattr(sys, '_getframe'):
    def current_frame(ignore_frames: int = 0) -> traceback:
        """

        : ignore_frames: By default, ignore the first frame since it is the line
                         here that captures the frame. When called by logger
                         code, it will probably set to ignore 2 or more frames.
        :return:
        """
        ignore_frames += 1
        frame = None
        try:
            raise Exception
        except:
            frame = sys._getframe(ignore_frames)

        return frame
else:
    def current_frame(ignore_frames: int = 0) -> traceback:
        """

        : ignore_frames: Specifies how many frames to ignore.
        :return:
        """
        ignore_frames += 1
        try:
            raise Exception
        except:
            return sys.exc_info()[2].tb_frame.f_back
# done filching

#
# _srcfile is used when walking the stack to check when we've got the first
# caller stack frame.
#
_srcfile = os.path.normcase(current_frame.__code__.co_filename)


class Logger(logging.Logger):
    """
        Provides logging capabilities that are more convenient than
        xbmc.log.

        Typical usage:

        class abc:
            def __init__(self):
                self._logger = LazyLogger(self.__class__.__name__)

            def method_a(self):
                local_logger = self._logger('method_a')
                local_logger.enter()
                ...
                local_logger.debug('something happened', 'value1:',
                                    value1, 'whatever', almost_any_type)
                local_logger.exit()

        In addition, there is the Trace class which provides more granularity
        for controlling what messages are logged as well as tagging of the
        messages for searching the logs.

    """
    _addon_name = None
    _logger = None
    _log_handler_added = False
    _root_logger = None
    _addon_logger = None

    @classmethod
    def _init_class(cls) -> None:
        cls.init_log_levelnames()

    def __init__(self,
                 name: str,
                 level: int = logging.NOTSET
                 ) -> None:
        """
            Creates a config_logger for (typically) a class.

        :param name: label to be printed on each logged entry
        :param level:
        """
        # noinspection PyRedundantParentheses
        try:
            super().__init__(name, level=level)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            Logger.log_exception()

    @staticmethod
    def set_addon_name(name: str) -> None:
        """
            Sets the optional addon name to be added to each log entry

        :param name: str
        :return:
        """
        Logger._addon_name = name

    @staticmethod
    def get_addon_name() -> str:
        """

        :return:
        """
        if Logger._addon_name is None:
            Logger._addon_name = Constants.CURRENT_ADDON_SHORT_NAME

        return Logger._addon_name

    @staticmethod
    def get_root_logger() -> ForwardRef('Logger'):
        """

        :return:
        """
        if Logger._root_logger is None:
            logging.setLoggerClass(LazyLogger)
            root_logger = logging.RootLogger(Logger.DEBUG)
            root_logger = logging.root
            root_logger.addHandler(MyHandler())
            logging_level = CriticalSettings.get_logging_level()
            xbmc.log('get_root_logger logging_level: ' +
                     str(logging_level), xbmc.LOGDEBUG)
            root_logger.setLevel(logging_level)
            Trace.enable_all()
            root_logger.addFilter(Trace())
            Logger._root_logger = root_logger
        return Logger._root_logger

    @staticmethod
    def get_addon_module_logger(file_path: str = None,
                                addon_name: str = None) -> ForwardRef('Logger'):
        """

        :return:
        """

        logger = None
        if Logger._addon_logger is None:
            if addon_name is None:
                addon_name = Constants.CURRENT_ADDON_SHORT_NAME
            Logger._addon_logger = Logger.get_root_logger().getChild(addon_name)
            # xbmc.log('get_addon_module_logger', xbmc.LOGDEBUG)

        logger = Logger._addon_logger
        if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
            if file_path is not None:
                file_path = file_path.replace('.py', '', 1)
                suffix = file_path.replace(TOP_PACKAGE_PATH, '', 1)
                suffix = suffix.replace('/', '.')
                if suffix.startswith('.'):
                    suffix = suffix.replace('.', '', 1)

                logger = Logger._addon_logger.getChild(suffix)
            else:
                logger.debug('Expected file_path')

        return logger

    def log(self, *args: Any, **kwargs: Any) -> None:
        """
            Creates a log entry

            *args are printed in the log, comma separated. Values are
            converted to strings.

            **Kwargs Optional Trace tags. Message is logged only if tracing
            is enabled for one or more of the tags. Further, the tag is also
            logged.

            Note, the default xbmc.log logging level is xbmc.LOGDEBUG. This can
            be overridden by including the kwarg {'log_level' : xbmc.<log_level>}

        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str Possible values:
                        'log_level'
                        'separator'
                        'exc_info'
                        'start_frame'
                        'trace'
                        'lazy_logger'
                        'test_expected_stack_top'
                        'test_expected_stack_file'
                        'test_expected_stack_method'

        :return:
        """
        # noinspection PyRedundantParentheses
        self._log(*args, **kwargs)

    def _log(self, *args: Any, **kwargs: Any) -> None:
        """
            Creates a log entry

            *args are printed in the log, comma separated. Values are
            converted to strings.

            **Kwargs Optional Trace tags. Message is logged only if tracing
            is enabled for one or more of the tags. Further, the tag is also
            logged.

            Note, the default xbmc.log logging level is xbmc.LOGDEBUG. This can
            be overridden by including the kwarg {'log_level' : xbmc.<log_level>}

        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        # noinspection PyRedundantParentheses
        start_frame = None
        try:
            kwargs.setdefault('log_level', Logger.DEBUG)
            log_level = kwargs['log_level']
            if not self.isEnabledFor(log_level):
                return

            kwargs.setdefault('ignore_frames', 0)
            ignore_frames = kwargs['ignore_frames'] + 1
            kwargs['ignore_frames'] = ignore_frames
            kwargs.setdefault('separator', ' ')

            exc_info = kwargs.get('exc_info', None)
            if exc_info is not None:
                start_frame = exc_info[2].tb_frame
                frame_info = inspect.getframeinfo(exc_info[2], context=1)
                # start_file = (pathname, lineno, func)

                start_file = (frame_info[0], frame_info[1], frame_info[2])
            else:
                start_file = tuple()
                start_frame = kwargs.get('start_frame', None)
                if start_frame is None:
                    start_frame = current_frame(ignore_frames=ignore_frames)
                # On some versions of IronPython, current_frame() returns None if
                # IronPython isn't run with -X:Frames.
                if start_frame is not None:
                    #     start_frame = start_frame.f_back
                    rv = "(unknown file)", 0, "(unknown function)"
                    while hasattr(start_frame, "f_code"):
                        co = start_frame.f_code
                        filename = os.path.normcase(co.co_filename)
                        if filename == _srcfile:
                            start_frame = start_frame.f_back
                            continue
                        start_file = (co.co_filename,
                                      start_frame.f_lineno, co.co_name)
                        break

            log_level = kwargs['log_level']
            separator = kwargs['separator']
            trace = kwargs.pop('trace', None)
            lazy_logger = kwargs.pop('lazy_logger', False)

            # The first argument is a string format, unless 'lazy_logger' is set.
            # With lazy_logger, a simple string format is generated based upon
            # the number of other args.

            format_str = ''
            if lazy_logger:
                format_proto = []  # ['[%s]']
                format_proto.extend(['%s'] * len(args))
                format_str = separator.join(format_proto)
            else:
                # Extract the format string from the first arg, then delete
                # the first arg.

                if len(args) > 0:
                    format_str = args[0]
                if len(args) > 1:
                    args = args[1:]
                else:
                    args = []

            args = tuple(args)  # MUST be a tuple

            my_trace = None
            if trace is None:
                my_trace = set()
            elif isinstance(trace, list):
                my_trace = set(trace)
            elif isinstance(trace, str):  # Single trace keyword
                my_trace = {trace, }  # comma creates set

            extra = {'trace': my_trace, 'start_file': start_file,
                     'ignore_frames': ignore_frames}

            super()._log(log_level, format_str, args, exc_info=exc_info,
                         extra=extra)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            Logger.log_exception()
        finally:
            del start_frame
            if 'start_frame' in kwargs:
                del kwargs['start_frame']

    def debug(self, format_str: str, *args: Any, **kwargs: Any) -> None:
        # TODO: Get rid of format arg
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.LOGDEBUG)
        :param format_str: Format string for args
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.DEBUG
        kwargs.setdefault('ignore_frames', 0)
        ignore_frames = kwargs['ignore_frames'] + 1
        kwargs['ignore_frames'] = ignore_frames

        self._log(format_str, *args, **kwargs)

    def debug_verbose(self, text: str, *args: Any, **kwargs: Any) -> None:
        # TODO: Get rid of text arg
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.LOGDEBUG)
        :param text: Arbitrary text to include in log
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.DEBUG_VERBOSE
        if kwargs.get('start_frame', None) is None:
            kwargs.setdefault('start_frame', current_frame())

        self._log(text, *args, **kwargs)

    def debug_extra_verbose(self, text: str, *args: Any, **kwargs: Any) -> None:
        # TODO: Get rid of text arg
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.LOGDEBUG)
        :param text: Arbitrary text to include in log
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.DEBUG_EXTRA_VERBOSE
        if kwargs.get('start_frame', None) is None:
            kwargs.setdefault('start_frame', current_frame())

        self._log(text, *args, **kwargs)

    def info(self, text: str, *args: Any, **kwargs: Any) -> None:
        # TODO: Get rid of text arg
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.LOGINFO)
        :param text: Arbitrary text
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.INFO
        if kwargs.get('start_frame', None) is None:
            kwargs.setdefault('start_frame', current_frame())

        self._log(text, *args, **kwargs)

    def warning(self, text: str, *args: Any, **kwargs: Any) -> None:
        # TODO: Get rid of text arg
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.LOGWARN)
        :param text: Arbitrary text to add to log
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.WARNING
        if kwargs.get('start_frame', None) is None:
            kwargs.setdefault('start_frame', current_frame())

        self._log(text, *args, **kwargs)

    def error(self, text: str, *args: Any, **kwargs: Any) -> None:
        # TODO: Get rid of text arg
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.ERROR)
        :param text: Arbitrary text to add to log
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.ERROR
        if kwargs.get('start_frame', None) is None:
            kwargs.setdefault('start_frame', current_frame())

        self._log(text, *args, **kwargs)

    def enter(self, *args: Any, **kwargs: str) -> None:
        """
            Convenience method to log an "Entering" method entry

        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return: None
        """
        if kwargs.get('start_frame', None) is None:
            kwargs.setdefault('start_frame', current_frame())

        self.debug('Entering', *args, **kwargs)

    def exit(self, *args: Any, **kwargs: str) -> None:
        """
               Convenience method to log an "Exiting" method entry

        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return: None
        """

        if kwargs.get('start_frame', None) is None:
            kwargs.setdefault('start_frame', current_frame())

        self.debug('Exiting', *args, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Convenience method for logging an ERROR with exception information.
        """
        kwargs.setdefault('exc_info',  sys.exc_info())
        kwargs['log_level'] = Logger.ERROR
        if kwargs.get('start_frame', None) is None:
            kwargs.setdefault('start_frame', current_frame())
        self.error(msg, *args, **kwargs)

    def fatal(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Log 'msg % args' with severity 'FATAL'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        config_logger.critical("Houston, we have a %s", "major disaster", exc_info=1)
        """
        if self.isEnabledFor(Logger.FATAL):
            kwargs['log_level'] = Logger.FATAL
            if kwargs.get('start_frame', None) is None:
                kwargs.setdefault('start_frame', current_frame())

            self._log(msg, *args, **kwargs)

    @classmethod
    def dump_stack(cls, msg: str = '', ignore_frames: int = 0) -> None:
        """
            Logs a stack dump of all Python threads

        :param msg: Optional message
        :param ignore_frames: Specifies stack frames to dump
        :return: None
        """
        ignore_frames += 1
        trace_back, thread_name, is_daemon = cls._capture_stack(
            ignore_frames=ignore_frames)
        cls.log_stack(msg, trace_back, thread_name, is_daemon)

    @classmethod
    def capture_stack(cls, ignore_frames: int = 0) -> (List[Type], str):
        """
        :param ignore_frames:
        :return:
        """
        ignore_frames += 1
        return cls._capture_stack(ignore_frames=ignore_frames)

    @classmethod
    def _capture_stack(cls, ignore_frames: int = 0) -> (List[Type], str):
        """
        :param ignore_frames: Specifies stack frames to skip
        :return:
        """
        ignore_frames += 1
        frame = current_frame(ignore_frames=int(ignore_frames))

        limit = 15
        trace_back = traceback.extract_stack(frame, limit)
        thread_name = threading.current_thread().getName()
        is_daemon: bool = threading.current_thread().isDaemon()
        return trace_back, thread_name, is_daemon

    @staticmethod
    def log_stack(msg: str, trace_back: List[Type],
                  thread_name: str = '', is_daemon: bool = None) -> None:
        """

        :param msg:
        :param trace_back:
        :param thread_name:
        :param is_daemon:
        :return:
        """

        try:
            daemon: str = 'None'
            if is_daemon is not None:
                if is_daemon:
                    daemon: 'True'
                else:
                    daemon: 'False'

            msg = f'{Constants.CURRENT_ADDON_NAME} :{msg} thread: {thread_name} '\
                  f'daemon: {daemon}'

            string_buffer = msg
            string_buffer = string_buffer + '\n' + Constants.TRACEBACK
            lines = traceback.format_list(trace_back)
            for line in lines:
                string_buffer = string_buffer + '\n' + line

            xbmc.log(string_buffer, xbmc.LOGERROR)
        except Exception as e:
            Logger.log_exception()

    DISABLED = 0
    FATAL = logging.CRITICAL  # 50
    ERROR = logging.ERROR       # 40
    WARNING = logging.WARNING   # 30
    INFO = logging.INFO         # 20
    DEBUG = logging.DEBUG       # 10
    DEBUG_VERBOSE = 8
    DEBUG_EXTRA_VERBOSE = 6
    NOTSET = logging.NOTSET     # 0

    log_level_to_label = {DISABLED: 'DISABLED',
                          FATAL: 'FATAL',
                          ERROR: 'ERROR',
                          WARNING: 'WARNING',
                          INFO: 'INFO',
                          DEBUG_EXTRA_VERBOSE: 'DEBUG_EXTRA_VERBOSE',
                          DEBUG_VERBOSE: 'DEBUG_VERBOSE',
                          DEBUG: 'DEBUG'}

    @classmethod
    def init_log_levelnames(cls) -> None:
        for level, levelname in Logger.log_level_to_label.items():
            logging.addLevelName(level, levelname)

    # XBMC levels
    LOGDEBUG = xbmc.LOGDEBUG
    LOGINFO = xbmc.LOGINFO
    LOGWARNING = xbmc.LOGWARNING
    LOGERROR = xbmc.LOGERROR
    LOGFATAL = xbmc.LOGFATAL
    LOGNONE = xbmc.LOGNONE

    logging_to_kodi_level = {DISABLED: 100,
                             FATAL: xbmc.LOGFATAL,
                             ERROR: xbmc.LOGERROR,
                             WARNING: xbmc.LOGWARNING,
                             INFO: xbmc.LOGINFO,
                             DEBUG_EXTRA_VERBOSE: xbmc.LOGDEBUG,
                             DEBUG_VERBOSE: xbmc.LOGDEBUG,
                             DEBUG: xbmc.LOGDEBUG}

    kodi_to_logging_level = {xbmc.LOGDEBUG: DEBUG,
                             xbmc.LOGINFO: INFO,
                             xbmc.LOGWARNING: WARNING,
                             xbmc.LOGERROR: ERROR,
                             xbmc.LOGFATAL: FATAL}

    @staticmethod
    def get_python_log_level(kodi_log_level: int) -> int:
        """

        :param kodi_log_level:
        :return:
        """
        return Logger.kodi_to_logging_level.get(kodi_log_level, None)

    @staticmethod
    def get_kodi_level(logging_log_level: int) -> int:
        """

        :param logging_log_level:
        :return:
        """
        return Logger.logging_to_kodi_level.get(logging_log_level, None)

    @staticmethod
    def on_settings_changed() -> None:
        """

        :return:
        """
        logging_level = CriticalSettings.get_logging_level()
        root_logger = Logger.get_root_logger()
        root_logger.setLevel(logging_level)

    @staticmethod
    def log_exception(exc_info: BaseException = None, msg: str = None) -> None:
        """
            Logs an exception.

        :param exc_info: BaseException optional Exception. Not used at this time
        :param msg: str optional msg
        :return: None
        """
        try:
            if not isinstance(exc_info, tuple):
                frame = current_frame(ignore_frames=1)
            else:
                frame = sys.exc_info()[2].tb_frame.f_back

                # stack = LazyLogger._capture_stack(ignore_frames=0)
            thread_name = threading.current_thread().getName()

            sio = StringIO()
            LazyLogger.print_full_stack(
                frame=frame, thread_name=thread_name, log_file=sio)

            s = sio.getvalue()
            sio.close()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            msg = 'Logger.log_exception raised exception during processing'
            xbmc.log(msg, xbmc.LOGERROR)

    @staticmethod
    def is_trace_enabled(trace_flags: str) -> bool:
        return Trace.is_enabled(trace_flags)

    @staticmethod
    def print_full_stack(frame: Any = None, thread_name: str = '',
                         limit: int = None,
                         log_file: io.StringIO = None) -> None:
        """

        :param frame:
        :param thread_name:
        :param limit:
        :param log_file:
        :return:
        """

        if frame is None:
            try:
                raise ZeroDivisionError
            except ZeroDivisionError:
                f = sys.exc_info()[2].tb_frame.f_back

        if log_file is None:
            log_file = sys.stderr

        lines = ['LEAK Traceback StackTrace StackDump\n']

        for item in reversed(inspect.getouterframes(frame)[1:]):
            lines.append('File "{1}", line {2}, in {3}\n'.format(*item))
            for line in item[4]:
                lines.append(' ' + line.lstrip())
        if hasattr(frame, 'tb_frame'):
            for item in inspect.getinnerframes(frame):
                lines.append(' File "{1}", line {2}, in {3}\n'.format(*item))
                for line in item[4]:
                    lines.append(' ' + line.lstrip())

        for line in lines:
            log_file.write(line)


def log_exit(func: Callable) -> None:
    """

    :param func:
    :return:
    """

    @wraps(func)
    def func_wrapper(*args: Any, **kwargs: Any) -> Callable[Any]:
        """

        :param args:
        :param kwargs:
        :return:
        """
        class_name: str = type(func).__class__.__name__
        method_name = func.__name__
        local_logger = LazyLogger.get_root_logger().getChild(class_name)
        func(*args, **kwargs)
        local_logger.exit()

    return func_wrapper


def log_entry(func: Callable) -> None:
    """

    :param func:
    :return:
    """

    @wraps(func)
    def func_wrapper(*args: Any, **kwargs: Any) -> Callable[Any]:
        """

        :param args:
        :param kwargs:
        :return:
        """
        class_name = type(func).__class__.__name__
        method_name = func.__name__

        # TODO: Does not include addon name & path
        local_logger = Logger.get_addon_module_logger().getChild(class_name)
        local_logger.enter()

        func(*args, **kwargs)

    return func_wrapper


def log_entry_exit(func: Callable) -> None:
    """

    :param func:
    :return:
    """

    @wraps(func)
    def func_wrapper(*args: Any, **kwargs: Any) -> Callable[Any]:
        """

        :param args:
        :param kwargs:
        :return:
        """
        class_name = type(func).__class__.__name__
        method_name = func.__name__

        # TODO: Does not include addon name & path

        local_logger = Logger.get_addon_module_logger().getChild(class_name)
        local_logger.enter()
        func(*args, **kwargs)
        local_logger.exit()

    return func_wrapper


class LazyLogger(Logger):
    """
        Provides logging capabilities that are more convenient than
        xbmc.log.

        Typical usage:

        class abc:
            def __init__(self):
                self._logger = LazyLogger(self.__class__.__name__)

            def method_a(self):
                local_logger = self._logger('method_a')
                local_logger.enter()
                ...
                local_logger.debug('something happened', 'value1:',
                                    value1, 'whatever', almost_any_type)
                local_logger.exit()

        In addition, there is the Trace class which provides more granularity
        for controlling what messages are logged as well as tagging of the
        messages for searching the logs.

    """
    _addon_name: str = None
    _logger: logging.Logger = None
    _log_handler_added: bool = False

    def __init__(self,
                 name: str = '',
                 class_name: str = '',
                 level: int = logging.NOTSET) -> None:

        """
            Creates a config_logger for (typically) a class.

        :param class_name: label to be printed on each logged entry
        :param level: Messages at this level and below get logged

        """
        try:
            if name == '':
                name = class_name
            super().__init__(name, level=level)

            if LazyLogger._addon_name is None:
                LazyLogger._addon_name = Constants.CURRENT_ADDON_SHORT_NAME

            self.setLevel(level)
            Trace.enable_all()
            self.addFilter(Trace())

        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            LazyLogger.log_exception()

    def log(self, *args: Any, **kwargs: Any) -> None:
        """
            Creates a log entry

            *args are printed in the log, comma separated. Values are
            converted to strings.

            **Kwargs Optional Trace tags. Message is logged only if tracing
            is enabled for one or more of the tags. Further, the tag is also
            logged.

            Note, the default xbmc.log logging level is xbmc.LOGDEBUG. This can
            be overridden by including the kwarg {'log_level' : xbmc.<log_level>}

        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        # noinspection PyRedundantParentheses
        try:
            kwargs.setdefault('lazy_logger', True)
            kwargs.setdefault('ignore_frames', 0)
            ignore_frames = kwargs['ignore_frames'] + 1
            kwargs['ignore_frames'] = ignore_frames
            super()._log(*args, **kwargs)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            LazyLogger.log_exception()

    def _log(self, *args: Any, **kwargs: Any) -> None:
        """
            Creates a log entry

            *args are printed in the log, comma separated. Values are
            converted to strings.

            **Kwargs Optional Trace tags. Message is logged only if tracing
            is enabled for one or more of the tags. Further, the tag is also
            logged.

            Note, the default xbmc.log logging level is xbmc.LOGDEBUG. This can
            be overridden by including the kwarg {'log_level' : xbmc.<log_level>}

        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        try:
            kwargs.setdefault('log_level', Logger.DEBUG)
            log_level = kwargs['log_level']
            if not self.isEnabledFor(log_level):
                return

            kwargs.setdefault('lazy_logger', True)
            kwargs.setdefault('ignore_frames', 0)
            ignore_frames = kwargs['ignore_frames'] + 1
            kwargs['ignore_frames'] = ignore_frames

            super()._log(*args, **kwargs)

        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            LazyLogger.log_exception()

    def debug(self, *args: Any, **kwargs: Any) -> None:
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.LOGDEBUG)
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.DEBUG
        kwargs.setdefault('lazy_logger', True)
        kwargs.setdefault('ignore_frames', 0)
        ignore_frames = kwargs['ignore_frames'] + 1
        kwargs['ignore_frames'] = ignore_frames

        self._log(*args, **kwargs)

    def debug_verbose(self, *args: Any, **kwargs: Any) -> None:
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.LOGDEBUG)
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.DEBUG_VERBOSE
        kwargs.setdefault('lazy_logger', True)
        kwargs.setdefault('ignore_frames', 0)
        ignore_frames = kwargs['ignore_frames'] + 1
        kwargs['ignore_frames'] = ignore_frames

        self._log(*args, **kwargs)

    def debug_extra_verbose(self, *args: Any, **kwargs: Any) -> None:
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.LOGDEBUG)
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.DEBUG_EXTRA_VERBOSE
        kwargs.setdefault('lazy_logger', True)
        kwargs.setdefault('ignore_frames', 0)
        ignore_frames = kwargs['ignore_frames'] + 1
        kwargs['ignore_frames'] = ignore_frames

        self._log(*args, **kwargs)

    def info(self, *args: Any, **kwargs: Any) -> None:
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.LOGINFO)
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.INFO
        kwargs.setdefault('lazy_logger', True)
        kwargs.setdefault('ignore_frames', 0)
        ignore_frames = kwargs['ignore_frames'] + 1
        kwargs['ignore_frames'] = ignore_frames

        self._log(*args, **kwargs)

    def warning(self, *args: Any, **kwargs: Any) -> None:
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.LOGWARN)
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.WARNING
        kwargs.setdefault('lazy_logger', True)
        kwargs.setdefault('ignore_frames', 0)
        ignore_frames = kwargs['ignore_frames'] + 1
        kwargs['ignore_frames'] = ignore_frames

        self._log(*args, **kwargs)

    def error(self, *args: Any, **kwargs: Any) -> None:
        """
            Convenience method for log(xxx kwargs['log_level' : xbmc.ERROR)
        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return:
        """
        kwargs['log_level'] = Logger.ERROR
        kwargs.setdefault('lazy_logger', True)
        kwargs.setdefault('ignore_frames', 0)
        ignore_frames = kwargs['ignore_frames'] + 1
        kwargs['ignore_frames'] = ignore_frames

        self._log(*args, **kwargs)

    def enter(self, *args: Any, **kwargs: Any) -> None:
        """
            Convenience method to log an "Entering" method entry

        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return: None
        """
        kwargs.setdefault('lazy_logger', True)
        kwargs.setdefault('ignore_frames', 0)
        ignore_frames = kwargs['ignore_frames'] + 1
        kwargs['ignore_frames'] = ignore_frames

        self.debug('Entering', *args, **kwargs)

    def exit(self, *args: Any, **kwargs: Any) -> None:
        """
               Convenience method to log an "Exiting" method entry

        :param args: Any (almost) arbitrary arguments. Typically "msg:", value
        :param kwargs: str  Meant for Trace usage:
        :return: None
        """
        kwargs.setdefault('lazy_logger', True)
        kwargs.setdefault('ignore_frames', 0)
        ignore_frames = kwargs['ignore_frames'] + 1
        kwargs['ignore_frames'] = ignore_frames

        self.debug('Exiting', *args, **kwargs)

    def exception(self, *args: Any, **kwargs: Any) -> None:
        """
        Convenience method for logging an ERROR with exception information.
        """
        kwargs.setdefault('exc_info',  sys.exc_info())
        kwargs['log_level'] = Logger.ERROR
        kwargs.setdefault('lazy_logger', True)
        kwargs.setdefault('ignore_frames', 0)
        ignore_frames = kwargs['ignore_frames'] + 1
        kwargs['ignore_frames'] = ignore_frames

        self.error(*args, **kwargs)

    def fatal(self, *args: Any, **kwargs: Any) -> None:
        """
        Log 'msg % args' with severity 'FATAL'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        config_logger.critical("Houston, we have a %s", "major disaster", exc_info=1)
        """
        if self.isEnabledFor(Logger.FATAL):
            kwargs['log_level'] = Logger.FATAL
            kwargs.setdefault('lazy_logger', True)
            kwargs.setdefault('ignore_frames', 0)
            ignore_frames = kwargs['ignore_frames'] + 1
            kwargs['ignore_frames'] = ignore_frames

            self._log(*args, **kwargs)

    @classmethod
    def dump_stack(cls, msg: str = '', ignore_frames: int = 0) -> None:
        """
            Logs a stack dump of all Python threads

        :param msg: Optional message
        :param ignore_frames: Specifies stack frames to dump
        :return: None
        """
        ignore_frames += 1
        trace_back, thread_name, is_daemon = super()._capture_stack(
            ignore_frames=ignore_frames)
        cls.log_stack(msg, trace_back, thread_name, is_daemon)

    @classmethod
    def _capture_stack(cls, ignore_frames: int = 0) -> (List[Type], str):
        """
        :param ignore_frames:
        :return:
        """
        ignore_frames += 1
        return super()._capture_stack(ignore_frames=ignore_frames)

    @staticmethod
    def log_stack(msg: str, trace_back: List[Type],
                  thread_name: str = '', is_daemon: bool = None) -> None:
        """

        :param msg:
        :param trace_back:
        :param thread_name:
        :param is_daemon:
        :return:
        """

        try:
            daemon: str = 'None'
            if is_daemon is not None:
                if is_daemon:
                    daemon = 'True'
                else:
                    daemon = 'False'

            msg = f'{Constants.CURRENT_ADDON_NAME}: {msg} thread: {thread_name} ' \
                  f'daemon: {daemon}'
            # msg = utils.py2_decode(msg)

            string_buffer = msg
            string_buffer = string_buffer + '\n' + Constants.TRACEBACK
            lines = traceback.format_list(trace_back)
            for line in lines:
                string_buffer = string_buffer + '\n' + line

            xbmc.log(string_buffer, xbmc.LOGERROR)
        except Exception as e:
            Logger.log_exception()


class Trace(logging.Filter):
    """

    """
    TRACE: Final[str] = 'TRACE'
    STATS: Final[str] = 'STATS'
    TRACE_UI: Final[str] = 'UI'
    STATS_UI: Final[str] = 'STATS_UI'
    TRACE_DISCOVERY: Final[str] = 'DISCOVERY'
    TRACE_FETCH: Final[str] = 'FETCH'
    TRACE_TRAILER_CACHE: Final[str] = 'TRAILER_CACHE'
    TRACE_TMDB_CACHE: Final[str] = 'TMDB_CACHE'
    TRACE_GENRE: Final[str] = 'GENRE'
    TRACE_CERTIFICATION: Final[str] = 'CERTIFICATION'
    TRACE_CACHE_GARBAGE_COLLECTION: Final[str] = 'CACHE_GC'
    TRACE_TFH: Final[str] = 'TFH'
    STATS_DISCOVERY: Final[str] = 'STATS_DISCOVERY'
    STATS_CACHE: Final[str] = 'STATS_CACHE'
    TRACE_MONITOR: Final[str] = 'MONITOR'
    TRACE_JSON: Final[str] = 'JSON'
    TRACE_SCREENSAVER: Final[str] = 'SCREENSAVER'
    TRACE_UI_CONTROLLER: Final[str] = 'UI_CONTROLLER'
    TRACE_CACHE_MISSING: Final[str] = 'CACHE_MISSING'
    TRACE_CACHE_UNPROCESSED: Final[str] = 'CACHE_UNPROCESSED'
    TRACE_CACHE_PAGE_DATA: Final[str] = 'CACHE_PAGE_DATA'
    TRACE_TRANSLATION: Final[str] = 'TRANSLATION'
    TRACE_SHUTDOWN: Final[str] = 'SHUTDOWN'
    TRACE_PLAY_STATS: Final[str] = 'PLAY_STATISTICS'
    TRACE_NETWORK: Final[str] = 'TRACE_NETWORK'

    TRACE_ENABLED: Final[bool] = True
    TRACE_DISABLED: Final[bool] = False

    _trace_map: Final[Dict[str, bool]] = {
        TRACE: TRACE_DISABLED,
        STATS: TRACE_DISABLED,
        TRACE_UI: TRACE_DISABLED,
        TRACE_DISCOVERY: TRACE_DISABLED,
        TRACE_FETCH: TRACE_DISABLED,
        TRACE_TRAILER_CACHE: TRACE_DISABLED,
        TRACE_TMDB_CACHE: TRACE_DISABLED,
        TRACE_GENRE: TRACE_DISABLED,
        TRACE_CERTIFICATION: TRACE_DISABLED,
        TRACE_CACHE_GARBAGE_COLLECTION: TRACE_DISABLED,
        TRACE_TFH: TRACE_DISABLED,
        STATS_DISCOVERY: TRACE_DISABLED,
        STATS_CACHE: TRACE_DISABLED,
        TRACE_MONITOR: TRACE_DISABLED,
        TRACE_JSON: TRACE_DISABLED,
        TRACE_SCREENSAVER: TRACE_DISABLED,
        TRACE_UI_CONTROLLER: TRACE_DISABLED,
        TRACE_CACHE_MISSING: TRACE_DISABLED,
        TRACE_CACHE_UNPROCESSED: TRACE_DISABLED,
        TRACE_CACHE_PAGE_DATA: TRACE_DISABLED,
        TRACE_TRANSLATION: TRACE_DISABLED,
        TRACE_SHUTDOWN: TRACE_DISABLED,
        TRACE_PLAY_STATS: TRACE_DISABLED,
        TRACE_NETWORK: TRACE_DISABLED
    }

    _trace_exclude = {
        TRACE_NETWORK: TRACE_DISABLED
    }

    _logger = None

    def __init__(self, name: str = '') -> None:
        """
        Dummy
        """
        super().__init__(name=name)

    @classmethod
    def enable(cls, *flags: str) -> None:
        """

        :param flags:
        :return:
        """
        for flag in flags:
            if flag in cls._trace_map:
                cls._trace_map[flag] = cls.TRACE_ENABLED
            else:
                cls._logger.debug(f'Invalid TRACE flag: {flag}')

    @classmethod
    def enable_all(cls) -> None:
        """

        :return:
        """
        for flag in cls._trace_map.keys():
            if flag not in cls._trace_exclude.keys():
                cls._trace_map[flag] = cls.TRACE_ENABLED

    @classmethod
    def disable(cls, *flags: str) -> None:
        """

        :param flags:
        :return:
        """
        for flag in flags:
            if flag in cls._trace_map:
                cls._trace_map[flag] = cls.TRACE_DISABLED
            else:
                cls._logger.debug(f'Invalid TRACE flag: {flag}')

    @classmethod
    def is_enabled(cls, trace_flags: Union[str, List[str]]) -> bool:
        try:
            if not isinstance(trace_flags, list):
                trace_flags = [trace_flags]

            if len(trace_flags) == 0:
                return False

            for trace in trace_flags:
                enabled = cls._trace_map.get(trace, None)
                if enabled is None:
                    cls._logger.warn(f'Invalid TRACE flag: {trace}')
                elif enabled:
                    return True

            return False
        except Exception:
            LazyLogger.log_exception()

        return False

    def filter(self, record: logging.LogRecord) -> int:
        """

        :param record:
        :return:
        """
        try:
            passed_traces = record.__dict__.get('trace', [])
            if len(passed_traces) == 0:
                return 1

            cls = type(self)
            filtered_traces = []
            for trace in passed_traces:
                is_enabled = cls._trace_map.get(trace, None)
                if is_enabled is None:
                    cls._logger.debug(f'Invalid TRACE flag: {trace}')
                elif is_enabled:
                    filtered_traces.append(trace)

            if len(filtered_traces) > 0:
                filtered_traces.sort()

                trace_string = ', '.join(filtered_traces)
                trace_string = f'[{trace_string}]'
                record.__dict__['trace_string'] = trace_string

                return 1  # Docs say 0 and non-zero
        except Exception:
            LazyLogger.log_exception()

        return 0


class MyHandler(logging.Handler):
    """

    """

    def __init__(self, level: int = logging.NOTSET,
                 trace: Set[str] = None) -> None:
        """

        :param level:
        :param trace:
        """

        self._trace = trace

        super().__init__()
        self.setFormatter(MyFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        """

        :param record:
        :return:
        """

        try:
            kodi_level = Logger.get_kodi_level(record.levelno)
            if record.exc_info is not None:
                ignore_frames = record.__dict__.get('ignore_frames', 0) + 4
                msg = self.formatter.formatException(record.exc_info,
                                                     ignore_frames)
                record.exc_text = msg
            msg = self.format(record)
            xbmc.log(msg, kodi_level)
        except Exception as e:
            pass


class MyFormatter(logging.Formatter):
    """

    """

    INCLUDE_THREAD_INFO = CriticalSettings.is_debug_include_thread_info()

    def __init__(self, fmt: str = None, datefmt: str = None) -> None:
        """

        :param fmt:
        :param datefmt:
        """
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        """

        :param record:
        :return:
        """

        """
            Attribute name 	Format 	Description
            args 	You shouldn’t need to format this yourself. 	The tuple of arguments merged into msg to produce message, or a dict whose values are used for the merge (when there is only one argument, and it is a dictionary).
            asctime 	%(asctime)s 	Human-readable time when the LogRecord was created. By default this is of the form ‘2003-07-08 16:49:45,896’ (the numbers after the comma are millisecond portion of the time).
            created 	%(created)f 	Time when the LogRecord was created (as returned by time.time()).
            exc_info 	You shouldn’t need to format this yourself. 	Exception tuple (à la sys.exc_info) or, if no exception has occurred, None.
            filename 	%(filename)s 	Filename portion of pathname.
            funcName 	%(funcName)s 	Name of function containing the logging call.
            levelname 	%(levelname)s 	Text logging level for the message ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL').
            levelno 	%(levelno)s 	Numeric logging level for the message (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            lineno 	%(lineno)d 	Source line number where the logging call was issued (if available).
            module 	%(module)s 	Module (name portion of filename).
            msecs 	%(msecs)d 	Millisecond portion of the time when the LogRecord was created.
            message 	%(message)s 	The logged message, computed as msg % args. This is set when Formatter.format() is invoked.
            msg 	You shouldn’t need to format this yourself. 	The format string passed in the original logging call. Merged with args to produce message, or an arbitrary object (see Using arbitrary objects as messages).
            name 	%(name)s 	Name of the config_logger used to log the call.
            pathname 	%(pathname)s 	Full pathname of the source file where the logging call was issued (if available).
            process 	%(process)d 	Process ID (if available).
            processName 	%(processName)s 	Process name (if available).
            relativeCreated 	%(relativeCreated)d 	Time in milliseconds when the LogRecord was created, relative to the time the logging module was loaded.
            stack_info 	You shouldn’t need to format this yourself. 	Stack frame information (where available) from the bottom of the stack in the current thread, up to and including the stack frame of the logging call which resulted in the creation of this record.
            thread 	%(thread)d 	Thread ID (if available).
            threadName 	%(threadName)s 	Thread name (if available).
            
            [service.randomtrailers.backend:DiscoverTmdbMovies:process_page] 
            [service.randomtrailers.backend:FolderMovieData:add_to_discovered_movies  TRACE_DISCOVERY]
        """
        # threadName Constants.CURRENT_ADDON_SHORT_NAME funcName:lineno
        # [threadName name funcName:lineno]

        text = ''
        try:
            start_file = record.__dict__.get('start_file', None)
            try:
                pathname, lineno, func = start_file
            except ValueError:
                pathname, lineno, func = "(unknown file)", 0, "(unknown function)"

            record.pathname = pathname
            try:
                record.filename = os.path.basename(pathname)
                record.module = os.path.splitext(record.filename)[0]
            except (TypeError, ValueError, AttributeError):
                record.filename = pathname
                record.module = "Unknown module"
            record.lineno = lineno
            record.funcName = func

            suffix = super().format(record)
            passed_traces = record.__dict__.get('trace_string', None)
            if passed_traces is None:
                if type(self).INCLUDE_THREAD_INFO:
                    prefix = '[Thread {!s} {!s}.{!s}:{!s}:{!s}]'.format(
                        record.threadName, record.name, record.funcName,
                        record.lineno, record.levelname)
                else:
                    prefix = '[{!s}.{!s}:{!s}]'.format(
                        record.name, record.funcName, record.lineno)
            else:
                if type(self).INCLUDE_THREAD_INFO:
                    prefix = '[Thread {!s} {!s}.{!s}:{!s}:{!s} Trace:{!s}]'.format(
                        record.threadName, record.name, record.funcName,
                        record.lineno, record.levelname, passed_traces)
                else:
                    prefix = '[{!s}.{!s}:{!s}:{!s} Trace:{!s}]'.format(
                        record.name, record.funcName,
                        record.lineno, record.levelname, passed_traces)
            text = '{} {}'.format(prefix, suffix)
        except Exception as e:
            pass

        return text

    def formatException(self, ei: List[Any] = None,
                        ignore_frames: int = 0) -> str:
        """

        :param ei:
        :param ignore_frames:
        :return:
        """
        ignore_frames += 1
        if ei is not None:
            thread_name = threading.current_thread().getName()

            sio = StringIO()
            self.print_exception(
                ei[0], ei[1], ei[2], thread_name='', limit=None, log_file=sio)

            s = sio.getvalue()
            sio.close()
            return s

    def print_exception(self,
                        etype: Type,
                        value: Any,
                        tb: Any,
                        thread_name: str = '',
                        limit: int = None,
                        log_file: StringIO = None) -> None:
        """
        :param etype:
        :param value:
        :param tb:
        :param thread_name:
        :param limit:
        :param log_file:
        :return:
        """

        if tb is None:
            tb = sys.exc_info()[2]

        if log_file is None:
            log_file = sys.stderr

        lines = ['LEAK Traceback StackTrace StackDump (most recent call last)\n']

        for item in reversed(inspect.getouterframes(tb.tb_frame)[1:]):
            lines.append('File "{1}", line {2}, in {3}\n'.format(*item))
            for line in item[4]:
                lines.append(' ' + line.lstrip())

        if hasattr(tb, 'tb_frame'):
            for item in inspect.getinnerframes(tb):
                lines.append(' File "{1}", line {2}, in {3}\n'.format(*item))
                for line in item[4]:
                    lines.append(' ' + line.lstrip())

        lines = lines + traceback.format_exception_only(etype, value)

        for line in lines:
            log_file.write(line)


Logger._init_class()
