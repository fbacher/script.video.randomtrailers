# -*- coding: utf-8 -*-

import re
from re import Pattern

import xbmc
import simplejson as json
from common.imports import *


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
                  params=dict(sender='service.xbmc.tts',
                              message='SAY',
                              data=dict(text=text,
                                        interrupt=interrupt),
                              ),
                  id=1,
                  jsonrpc='2.0')

    json_args = json.dumps(params)
    result = xbmc.executeJSONRPC(json_args)

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


def stop() -> None:
    xbmc.executebuiltin('XBMC.NotifyAll(service.xbmc.tts,STOP)')
