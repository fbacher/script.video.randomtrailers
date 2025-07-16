# -*- coding: utf-8 -*-

import re
import threading

import xbmc
import json
from common.logger import *
from json import JSONEncoder
from .__init__ import *
from .phrases import Phrase

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class MyEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, Phrase):
            value: Dict[str, Dict[str, Any]] = {'phrase': o.__dict__}
            return value
        return json.JSONEncoder.default(self, o)


class TTS:

    stop_listeners: List[Callable[[], None]] = []
    _tts_stopped: bool = False
    _is_tts_running: bool = True

    @staticmethod
    def is_tts_running() -> bool:
        return TTS._is_tts_running

    @staticmethod
    def say_text(phrases: List[Phrase]) -> str:
        if not TTS._is_tts_running:
            return ''

        params = dict(method='JSONRPC.NotifyAll',
                      params=dict(sender='service.kodi.tts',
                                  message='SAY',
                                  data=dict(phrases=phrases),
                                  ),
                      id=1,
                      jsonrpc='2.0')

        json_args: str = MyEncoder().encode(params)
        result: str = xbmc.executeJSONRPC(json_args)
        module_logger.debug(f'Sending JSONRPC: '
                            f'{json_args}')
        module_logger.debug(f'result: {result}')
        return result

    @staticmethod
    def add_stop_listener(listener: Callable[[], None]) -> None:
        if not TTS._is_tts_running:
            return

        TTS.stop_listeners.append(listener)

    @staticmethod
    def stop() -> None:
        if not TTS._is_tts_running:
            return

        #
        # Run in separate thread because it adds about 1/2 second to switching
        # visibility of trailer/details view

        stop_tts_thread: threading.Thread
        stop_tts_thread = threading.Thread(name='start tts', target = TTS._stop)

        stop_tts_thread.start()

    @staticmethod
    def _stop() -> None:
        if not TTS._is_tts_running:
            return

        try:
            xbmc.executebuiltin('NotifyAll(service.kodi.tts,STOP)')

            for listener in TTS.stop_listeners:
                listener()
        except Exception:
            module_logger.exception(msg='')

    @staticmethod
    def tts_stopped() -> None:
        if not TTS._is_tts_running:
            return

        """
        Primative flag to indicate that the text_to_speech engine was told
        to stop. Currently it is cleared as soon as it is queried. Mostly useful
        for stopping voicing everything on the ShowDetails page.
        :return:
        """
        TTS._tts_stopped = True

    @staticmethod
    def is_tts_stopped() -> bool:
        if not TTS._is_tts_running:
            return True

        is_stopped: bool = TTS._tts_stopped
        TTS._tts_stopped = False
        return is_stopped
