# -*- coding: utf-8 -*-

"""
Created on Mar 21, 2019

@author: Frank Feuerbacher
"""

import sys
import threading

from .imports import *
from kodi65 import addon
import AddonSignals as AddonSignals

from common.constants import Constants, Movie
from common.exceptions import AbortException
from common.logger import (LazyLogger, Trace)
from common.monitor import Monitor

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class PluginBridgeStatus:
    """

    """
    IDLE = 'idle'
    TIMED_OUT = 'Timed Out'
    BUSY = 'Busy'
    OK = 'OK'
    DELETED = 'Deleted'  # When cached trailer (or even non-cached) is deleted


class PluginBridge:
    """
        PluginBridge provides support for the random trailers plugins to
        communicate with one another. Communication is accomplished using
        the AddonSignals service.
    """
    _logger = None
    _registered_slots = None

    def __init__(self):
        # type: () -> None
        """

        """
        if PluginBridge._logger is not None:
            return

        PluginBridge._logger = module_logger.getChild(type(self).__name__)
        try:
            PluginBridge._registered_slots = []
            Monitor.register_abort_listener(type(self).on_abort_event)
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            PluginBridge._logger.exception('')

    ###########################################################
    #
    #    Plumbing
    #
    ###########################################################

    @classmethod
    def notify_settings_changed(cls):
        # type: () -> None
        """
            Front-end informs others (back-end) that settings may have changed.

        :return:
        """
        PluginBridge._logger.enter('Override me')

    @classmethod
    def send_signal(cls, signal, data=None, source_id=None):
        # type: (str, Any, Union[str, None]) -> None
        """

        :param signal:
        :param data:
        :param source_id:
        :return:
        """
        try:
            thread = threading.Thread(
                target=PluginBridge.send_signal_worker,
                args=(signal,),
                kwargs={'data': data, 'source_id': source_id},
                name='BackendBridge.' + signal)

            thread.start()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            PluginBridge._logger.exception('')

    @classmethod
    def send_signal_worker(cls, signal, data=None, source_id=None):
        # type: (str, Any, str) -> None
        """

        :param signal:
        :param data:
        :param source_id:
        :return:
        """
        if PluginBridge._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            PluginBridge._logger.debug_extra_verbose('signal:', signal,
                                                     'source_id:', source_id)
        Monitor.throw_exception_if_abort_requested()

        try:
            AddonSignals.sendSignal(signal, data=data,
                                    source_id=source_id)
        except Exception as e:
            cls._logger.exception(e)

    @classmethod
    def register_slot(cls, signaler_id, signal, callback):
        # type: (str, str, Callable[[Any], None]) -> None
        """

        :param signaler_id:
        :param signal:
        :param callback:
        :return:
        """
        if PluginBridge._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            PluginBridge._logger.debug_extra_verbose('signaler_id:', signaler_id,
                                       'signal:', signal, 'callback:', callback.__name__)
        Monitor.throw_exception_if_abort_requested()
        AddonSignals.registerSlot(signaler_id, signal, callback)
        PluginBridge._registered_slots.append((signaler_id, signal))

    @classmethod
    def unregister_slot(cls, signaler_id, signal):
        # type: (str, str) -> None
        """

        :param signaler_id:
        :param signal:
        :return:
        """

        Monitor.throw_exception_if_abort_requested()
        try:
            AddonSignals.unRegisterSlot(signaler_id, signal)
        except Exception:
            pass

    @classmethod
    def return_call(cls, signal, data=None, source_id=None):
        # type: (str, Any, str) -> None
        """

        :param signal:
        :param data:
        :param source_id:
        :return:
        """

        pass
        # send_signal('_return.{0}'.format(signal), data, source_id)

    @classmethod
    def on_abort_event(cls):
        # type: () -> None
        """

        :return:
        """
        PluginBridge.delete_instance()

    @classmethod
    def delete_instance(cls):
        # type: () -> None
        """

        :return:
        """
        try:
            PluginBridge.unregister_slots()
            try:
                Monitor.unregister_abort_listener(PluginBridge.on_abort_event)
            except Exception:
                pass

            del AddonSignals.RECEIVER
            AddonSignals.RECEIVER = None
        except Exception as e:
            pass

    @classmethod
    def unregister_slots(cls):
        for signaler_id, signal in PluginBridge._registered_slots:
            PluginBridge.unregister_slot(signaler_id, signal)

        del PluginBridge._registered_slots[:]
