# -*- coding: utf-8 -*-

'''
Created on May 25, 2019

@author: Frank Feuerbacher
'''
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import sys
import threading
from collections import deque

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