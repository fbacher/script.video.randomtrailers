# -*- coding: utf-8 -*-

'''
Created on Jan 22, 2021

@author: Frank Feuerbacher
'''

import threading

import xbmcgui
from xbmcgui import (Control, ControlImage, ControlButton, ControlEdit,
                     ControlGroup, ControlLabel, ControlList, ControlTextBox,
                     ControlSpin, ControlSlider, ControlProgress, ControlFadeLabel,
                     ControlRadioButton)

from common.constants import Constants
from common.imports import *
from common.logger import *
from common.messages import Messages
from common.monitor import Monitor
from frontend.text_to_speech import TTS
from action_map import Action


module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class LegalInfo(xbmcgui.WindowXMLDialog):
    """
        Page shown at startup displaying legal information, such as logos, etc.
    """

    _instance: ForwardRef('LegalInfo') = None
    _destroyed: bool = False
    _window_id: str = None

    @staticmethod
    def get_instance() -> ForwardRef('LegalInfo'):
        """

        :return:
        """
        if LegalInfo._instance is None and not LegalInfo._destroyed:
            LegalInfo._instance = LegalInfo('legal.xml',
                                            Constants.ADDON_PATH, 'Default')
        return LegalInfo._instance

    def __init__(self, *args: Any, **kwargs: int) -> None:
        """

        :param args:
        :param kwargs:
        """
        super().__init__(*args, **kwargs)
        self._logger = module_logger.getChild(type(self).__name__)
        LegalInfo._instance = self
        type(self)._window_id = xbmcgui.getCurrentWindowId()
        self._wait_or_interrupt_event = threading.Event()
        self._license_display_seconds = kwargs['license_display_seconds']
        Monitor.register_abort_listener(self.on_abort_event)
        self._exit_dialog_timer = threading.Timer(
            interval=float(self._license_display_seconds), function=self.exit_dialog)
        self._exit_dialog_timer.setName('LegalInfoTimer')
        self._update_dialog_thread = None

    def on_abort_event(self) -> None:
        # self._logger.debug_extra_verbose('In on_abort_event')
        self._wait_or_interrupt_event.set()

    def exit_dialog(self) -> None:
        # self._logger.debug_extra_verbose('In exit_dialog')
        self._wait_or_interrupt_event.set()

    def onInit(self) -> None:
        """

        :return:
        """
        self._update_dialog_thread = threading.Thread(
            target=self.update_dialog, name='LegalInfo.update_dialog')
        self._update_dialog_thread.start()
        self._exit_dialog_timer.start()

    def update_dialog(self) -> None:
        label: Union[ControlLabel, Control] = self.getControl(38021)
        label_text = Messages.get_msg(Messages.LICENSE_LABEL)
        label.setLabel(f'[B]{label_text}[/B]')
        TTS.say_text(label_text, interrupt=True)

        tmdb_license = Messages.get_msg(Messages.TMDB_LICENSE)

        text_control: Union[Control, ControlTextBox] = self.getControl(38022)
        text_control.setText(tmdb_license)
        TTS.say_text(tmdb_license, interrupt=False)

        tfh_license = Messages.get_msg(Messages.TFH_LICENSE)

        text_control: Union[Control, ControlTextBox] = self.getControl(38023)
        text_control.setText(tfh_license)
        TTS.say_text(tfh_license, interrupt=False)

        while not self._wait_or_interrupt_event.is_set():
            Monitor.wait_for_abort(0.1)

        # self._logger.debug_extra_verbose(
        #     f'_wait_or_interrupt_event: {self._wait_or_interrupt_event.is_set()}')
        # self._logger.debug_extra_verbose(f'abort: {Monitor.wait_for_abort(0.0)}')
        self.close()

    def close(self) -> None:
        """

        :return:
        """
        # self._logger.debug_extra_verbose('In close')
        super().close()

    def destroy(self) -> None:
        """

        :return:
        """
        # self._logger.debug_extra_verbose('In destroy')
        Monitor.unregister_abort_listener(self.on_abort_event)
        del LegalInfo._instance
        LegalInfo._instance = None
        LegalInfo._destroyed = True
        try:
            self._update_dialog_thread.join(timeout=0.1)
        except Exception:
            pass
        del self._update_dialog_thread

    def show(self) -> None:
        # self._logger.debug_extra_verbose('In show')
        super().show()

    def doModal(self) -> bool:
        """

        :return:
        """
        super().doModal()
        return True

    def onAction(self, action: xbmcgui.Action) -> None:
        """

        :param action:
        :return:

            ACTION_MOVE_RIGHT -> Skip to next movie

            PREVIOUS_MENU | NAV_BACK | ACTION_BUILT_IN_FUNCTION ->
                                                 Exit Random Trailer script
                or stop Screensaver
        """
        action_id = action.getId()

        if self._logger.isEnabledFor(DISABLED):
            self._logger.debug_extra_verbose(f'In onAction id: {action_id}')

        if action_id != 107:  # Mouse Move
            if self._logger.isEnabledFor(DISABLED):
                self._logger.debug_extra_verbose(f'Action.id: {action_id}'
                                                 f'{hex(action_id)} '
                                                 f'Action.button_code: '
                                                 f'{action.getButtonCode()} '
                                                 f'{hex(action.getButtonCode())}',
                                                 trace=Trace.TRACE)

        action_mapper = Action.get_instance()
        matches = action_mapper.getKeyIDInfo(action)

        # Mouse Move
        if action_id != 107 and self._logger.isEnabledFor(
                DISABLED):
            for line in matches:
                self._logger.debug_extra_verbose(line)

        key = ''
        if self._logger.isEnabledFor(DISABLED):
            button_code = action.getButtonCode()

            # These return empty string if not found
            action_key = action_mapper.getActionIDInfo(action)
            remote_button = action_mapper.getRemoteKeyButtonInfo(action)
            remote_key_id = action_mapper.getRemoteKeyIDInfo(action)

            # Returns found button_code, or 'key_' +  action_button
            action_button = action_mapper.getButtonCodeId(action)

            separator = ''
            if action_key != '':
                key = action_key
                separator = ', '
            if remote_button != '':
                key = key + separator + remote_button
                separator = ', '
            if remote_key_id != '':
                key = key + separator + remote_key_id
            if key == '':
                key = action_button
            # Mouse Move
            if action_id != 107:
                self._logger.debug_extra_verbose(f'Key found: {key}')

        #################################################################
        #   ACTIONS
        ##################################################################
        #    DEBUG thread dump
        #################################################################

        if (self._logger.isEnabledFor(DEBUG_VERBOSE)
                and (action_id == xbmcgui.ACTION_PAGE_UP
                     or action_id == xbmcgui.ACTION_MOVE_UP)):

            from common.debug_utils import Debug
            Debug.dump_all_threads()

        ##################################################################
        elif (action_id == xbmcgui.ACTION_STOP
              or action_id == xbmcgui.ACTION_MOVE_RIGHT):
            if self._logger.isEnabledFor(DISABLED):
                self._logger.debug_extra_verbose(
                    f'{key} Exit display license at user\'s request')
            self.exit_dialog()
            # self._logger.debug_extra_verbose(
            #    f'just set: {self._wait_or_interrupt_event.is_set()}')

        ##################################################################

        elif (action_id == xbmcgui.ACTION_PREVIOUS_MENU
              or action_id == xbmcgui.ACTION_NAV_BACK):
            if self._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                self._logger.debug_extra_verbose(
                    f'{key} Exiting RandomTrailers at user request')

            Monitor.abort_requested()
            self.on_abort_event()

        ##################################################################

        # TODO: Need proper handling of this (and other inputs that we don't
        # handle. Sigh

        elif action_id == xbmcgui.ACTION_BUILT_IN_FUNCTION:
            if self._logger.isEnabledFor(DEBUG_VERBOSE):
                self._logger.debug_verbose(f'{key} Exiting RandomTrailers due to '
                                           'ACTION_BUILT_IN_FUNCTION',
                                           trace=Trace.TRACE_SCREENSAVER)
            Monitor.abort_requested()
            self.on_abort_event()
