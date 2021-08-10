# coding=utf-8
"""
Created on Jul 23, 2021

@author: Frank Feuerbacher
"""

from threading import Event, RLock, Thread
from common.logger import LazyLogger

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class FlexibleTimer(Thread):
    """
    Modified version of Timer.

    Call a function after a specified number of seconds, with the ability to
    run the function early by direct call:

            t = Timer(30.0, f, args=None, kwargs=None)
            t.start()
            t.cancel()     # stop the timer's action if it's still waiting
            t.run_now()    # Calls function with the additional argument
                           # called_early=True

    """
    _logger: LazyLogger = None

    def __init__(self, interval, function, args=None, kwargs=None):
        super().__init__(self)
        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(self.__class__.__name__)
        self.interval = interval
        self.function = function
        self.args = args if args is not None else []
        self.kwargs = kwargs if kwargs is not None else {}
        self.lock = RLock()
        self.finished = Event()

    def cancel(self):
        """Stop the timer if it hasn't finished yet."""
        self.finished.set()

    def run(self):
        self.finished.wait(self.interval)
        with self.lock:
            if not self.finished.is_set():
                self.function(*self.args, **self.kwargs)
            self.finished.set()

    def run_now(self, kwargs=None):
        clz = type(self)
        with self.lock:
            if not self.finished.is_set():
                # Prevent from running again
                self.finished.set()
                if kwargs is not None:
                    for key, value in kwargs.items():
                        clz._logger.debug(f'key: {key} value: {value}')
                        self.kwargs[key] = value

                self.kwargs['called_early'] = True
                self.function(*self.args, **self.kwargs)
