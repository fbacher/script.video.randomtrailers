
# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

from common.imports import *
import threading
from .__init__ import *


class TrailerFetcherInterface(threading.Thread):
    """

    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """

                 :param thread_name
        """

        kwargs['daemon'] = False
        super().__init__(*args, **kwargs)

    def start_fetchers(self):
        pass

    def stop_fetchers(self):
        pass

    def destroy(self):
        pass
