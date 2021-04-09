
# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: Frank Feuerbacher
"""

import threading


class TrailerFetcherInterface(threading.Thread):
    """

    """

    def __init__(self, thread_name: str) -> None:
        """

                 :param thread_name
        """

        super().__init__(name=thread_name)
