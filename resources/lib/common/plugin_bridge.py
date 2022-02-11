# -*- coding: utf-8 -*-

"""
Created on Mar 21, 2019

@author: Frank Feuerbacher
"""

import sys
import threading

from common.garbage_collector import GarbageCollector
from common.imports import *
import AddonSignals as AddonSignals

from common.exceptions import AbortException
from common.logger import *
from common.monitor import Monitor

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class PluginBridgeStatus:
    """

    """
    IDLE: Final[str] = 'idle'
    TIMED_OUT: Final[str] = 'Timed Out'
    BUSY: Final[str] = 'Busy'
    OK: Final[str] = 'OK'
    DELETED: Final[str] = 'Deleted'  # When cached movie (or even non-cached) is deleted


class PluginBridge:
    """
        PluginBridge provides support for the random trailers plugins to
        communicate with one another. Communication is accomplished using
        the AddonSignals service.
    """
    _logger: BasicLogger = None
    _registered_slots: List[Tuple[str, str]] = None

    def __init__(self) -> None:
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
    def notify_settings_changed(cls) -> None:
        """
            Front-end informs others (back-end) that settings may have changed.

        :return:
        """
        PluginBridge._logger.debug('Override me')

    @classmethod
    def send_signal(cls, signal: str, data: Any = None,
                    source_id: str = None) -> None:
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
                name='PluginBridge.' + signal)

            thread.start()
            GarbageCollector.add_thread(thread)
        except AbortException:
            reraise(*sys.exc_info())
        except Exception:
            PluginBridge._logger.exception('')

    @classmethod
    def send_signal_worker(cls, signal: str, data: Any = None,
                           source_id: str = None) -> None:
        """

        :param signal:
        :param data:
        :param source_id:
        :return:
        """
        # if PluginBridge._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            # PluginBridge._logger.debug_extra_verbose('signal:', signal,
            #                                          'source_id:', source_id)
        Monitor.throw_exception_if_abort_requested()

        try:
            AddonSignals.sendSignal(signal, data=data,
                                    source_id=source_id)
        except Exception as e:
            cls._logger.exception(e)

    @classmethod
    def register_slot(cls, signaler_id: str, signal: str,
                      callback: Callable[[Any], None]) -> None:
        """

        :param signaler_id:
        :param signal:
        :param callback:
        :return:
        """
        # if PluginBridge._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            # PluginBridge._logger.debug_extra_verbose('signaler_id:', signaler_id,
                                       # 'signal:', signal, 'callback:',
                                       # callback.__name__)
        Monitor.throw_exception_if_abort_requested()
        AddonSignals.registerSlot(signaler_id, signal, callback)
        PluginBridge._registered_slots.append((signaler_id, signal))

    @classmethod
    def unregister_slot(cls, signaler_id: str, signal: str) -> None:
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
    def return_call(cls, signal: str, data: Any = None,
                    source_id: str = None) -> None:
        """

        :param signal:
        :param data:
        :param source_id:
        :return:
        """

        pass
        # send_signal('_return.{0}'.format(signal), data, source_id)

    @classmethod
    def on_abort_event(cls) -> None:
        """

        :return:
        """
        PluginBridge.delete_instance()

    @classmethod
    def delete_instance(cls) -> None:
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
    def unregister_slots(cls) -> None:
        for signaler_id, signal in PluginBridge._registered_slots:
            PluginBridge.unregister_slot(signaler_id, signal)

        del PluginBridge._registered_slots[:]
