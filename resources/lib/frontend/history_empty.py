# -*- coding: utf-8 -*-

'''
Created on May 25, 2019

@author: Frank Feuerbacher
'''

from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                      TextType, MovieType, DEVELOPMENT, RESOURCE_LIB)
import sys
import threading
from collections import deque

from common.front_end_bridge import FrontendBridge
from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger, Trace, log_entry_exit
from common.messages import Messages
from common.monitor import Monitor

class HistoryEmpty(BaseException):
    def __init__(self):
        # type: () -> None
        """

        """