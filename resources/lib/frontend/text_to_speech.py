# -*- coding: utf-8 -*-

import re
import threading
from re import Pattern

import xbmc
import simplejson as json
from common.imports import *
from common.logger import LazyLogger

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TTS:

    stop_listeners: List[Callable[[], None]] = []
    _tts_stopped: bool = False

    @staticmethod
    def say_text(text, interrupt=False) -> str:

        # {"method": "JSONRPC.NotifyAll",
        #  "params": {"sender": "service.xbmc.tts",
        #             "message": "SAY",
        #             "data": {"text": "Flamingo Road (1949) - library"}
        #             },
        #   "id": 1,
        #   "jsonrpc": "2.0"}

        # Remove excess whitespace from text

        _RE_COMBINE_WHITESPACE: Pattern = re.compile(r"\s+")

        text = _RE_COMBINE_WHITESPACE.sub(" ", text).strip()

        params = dict(method='JSONRPC.NotifyAll',
                      params=dict(sender='service.kodi.tts',
                                  message='SAY',
                                  data=dict(text=text,
                                            interrupt=interrupt),
                                  ),
                      id=1,
                      jsonrpc='2.0')

        json_args = json.dumps(params)
        result: str = xbmc.executeJSONRPC(json_args)
        return result

    @staticmethod
    def add_stop_listener(listener: Callable[[], None]) -> None:
        TTS.stop_listeners.append(listener)

    @staticmethod
    def stop() -> None:
        #
        # Run in separate thread because it adds about 1/2 second to switching
        # visibility of trailer/details view

        stop_tts_thread: threading.Thread
        stop_tts_thread = threading.Thread(name='start tts', target = TTS._stop)

        stop_tts_thread.start()

    @staticmethod
    def _stop() -> None:
        try:
            xbmc.executebuiltin('NotifyAll(service.kodi.tts,STOP)')

            for listener in TTS.stop_listeners:
                listener()
        except Exception:
            module_logger.exception()

    @staticmethod
    def tts_stopped() -> None:
        """
        Primative flag to indicate that the text_to_speech engine was told
        to stop. Currently it is cleared as soon as it is queried. Mostly useful
        for stopping voicing everything on the ShowDetails page.
        :return:
        """
        TTS._tts_stopped = True

    @staticmethod
    def is_tts_stopped() -> bool:
        is_stopped: bool = TTS._tts_stopped
        TTS._tts_stopped = False
        return is_stopped
