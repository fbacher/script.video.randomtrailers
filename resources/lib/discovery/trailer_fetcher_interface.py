
# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import sys
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import threading
import six


class TrailerFetcherInterface(threading.Thread):
    """

    """

    def __init__(self, thread_name):
        # type: (TextType)-> None
        """

                 :param thread_name
        """

        super().__init__(name=thread_name)
