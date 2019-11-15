# -*- coding: utf-8 -*-

"""
Created on Mar 21, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from .imports import *

import sys
import threading
import six

import xbmc
from kodi65 import addon
# from kodi_six import xbmc
import AddonSignals as AddonSignals

from .constants import Constants, Movie
from .exceptions import AbortException, ShutdownException
from .logger import (Logger, LazyLogger, Trace)
from .monitor import Monitor

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'common.plugin_bridge')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class PluginBridgeStatus(object):
    """

    """
    IDLE = 'idle'
    TIMED_OUT = 'Timed Out'
    BUSY = 'Busy'
    OK = 'OK'


class PluginBridge(object):
    """
        PluginBridge provides support for the random trailers plugins to
        communicate with one another. Communication is accomplished using
        the AddonSignals service.
    """
    _instance = None

    def __init__(self):
        # type: () -> None
        """

        """
        self._logger = module_logger.getChild(self.__class__.__name__)
        # super().__init__()
        try:
            self._monitor = Monitor.get_instance()
            self._monitor.register_shutdown_listener(self.on_shutdown_event)
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception) as e:
            self._logger.exception('')

    def register_listeners(self):
        # type: () -> None
        """
            Register listeners (callbacks) with service. Note that
            communication is asynchronous

            :return: None
        """

        self._logger.enter()

        if self._context == Constants.FRONTEND_SERVICE:
            self.register_slot(
                addon.ID, 'nextTrailer', self.returned_trailer)
            self.register_slot(
                addon.ID, 'activate_screensaver', self.activate_screensaver)

        elif self._context == Constants.SCREENSAVER_SERVICE:
            self.register_slot(addon.ID, 'ack', self.receiveAck)

    ###########################################################
    #
    #    Plumbing
    #
    ###########################################################

    def notify_settings_changed(self):
        # type: () -> None
        """
            Front-end informs others (back-end) that settings may have changed.

        :return:
        """
        self._logger.enter('Override me')

    def send_data(self, data):
        # type: (Any) -> None
        """
        Send arbitrary data to remove service

        :param data:
        :return:
        """

        # Uses xbmc.notifyAll
        self.send_signal(self._signalName, data=data,
                         source_id=None)  # default is plugin id

    def send_signal(self, signal, data=None, source_id=None):
        # type: (str, Any, str) -> None
        """

        :param signal:
        :param data:
        :param source_id:
        :return:
        """
        try:
            thread = threading.Thread(
                target=self.send_signal_worker,
                args=(signal,),
                kwargs={'data': data, 'source_id': source_id},
                name='BackendBridge.on_settings_changed')

            thread.start()
        except (AbortException, ShutdownException):
            six.reraise(*sys.exc_info())
        except (Exception):
            self._logger.exception('')

    def send_signal_worker(self, signal, data=None, source_id=None):
        # type: (str, Any, str) -> None
        """

        :param signal:
        :param data:
        :param source_id:
        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('context:', self._context, 'signal:', signal,
                               'source_id:', source_id)
        self._monitor.throw_exception_if_shutdown_requested()

        AddonSignals.sendSignal(signal, data=data,
                                source_id=source_id)

    def register_slot(self, signaler_id, signal, callback):
        # type: (str, str, Callable[[Any], None]) -> None
        """

        :param signaler_id:
        :param signal:
        :param callback:
        :return:
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('signaler_id:', signaler_id,
                               'signal:', signal, 'callback:', callback.__name__)
        self._monitor.throw_exception_if_shutdown_requested()
        AddonSignals.registerSlot(signaler_id, signal, callback)

    @staticmethod
    def un_register_slot(signaler_id, signal):
        # type: (str, str) -> None
        """

        :param signaler_id:
        :param signal:
        :return:
        """

        Monitor.get_instance().throw_exception_if_shutdown_requested()
        AddonSignals.unRegisterSlot(signaler_id, signal)

    def return_call(self, signal, data=None, source_id=None):
        # type: (str, Any, str) -> None
        """

        :param signal:
        :param data:
        :param source_id:
        :return:
        """

        pass
        # send_signal('_return.{0}'.format(signal), data, source_id)

    def on_shutdown_event(self):
        # type: () -> None
        """

        :return:
        """
        self.delete_instance()

    def delete_instance(self):
        # type: () -> None
        """

        :return:
        """
        try:
            PluginBridge.un_register_slot(addon.ID, 'get_next_trailer')
            PluginBridge.un_register_slot(addon.ID, 'nextTrailer')
            PluginBridge.un_register_slot(addon.ID, 'settings_changed')
            PluginBridge.un_register_slot(addon.ID, 'ack')
            monitor = Monitor.get_instance()
            if monitor is not None:
                monitor.unregister_shutdown_listener(self)

            del AddonSignals.RECEIVER
            AddonSignals.RECEIVER = None
            PluginBridge._instance = None
        except (Exception) as e:
            pass
