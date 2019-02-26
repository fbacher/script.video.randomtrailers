'''
Created on Feb 12, 2019

@author: fbacher
'''

from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import unicode
from multiprocessing.pool import ThreadPool
from xml.dom import minidom
from kodi65 import addon
from kodi65 import utils
from common.rt_constants import Constants
from common.rt_constants import Movie
from common.rt_utils import Utils
from common.debug_utils import Debug
from common.rt_utils import Playlist
from common.rt_utils import WatchDog
from common.rt_utils import Trace
from action_map import Action
from settings import Settings
from backend.api import *
import sys
import random_trailers_ui

random_trailers_ui.myMain()
