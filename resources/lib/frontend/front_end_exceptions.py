# -*- coding: utf-8 -*-

"""
Created on July, 25, 2021

@author: Frank Feuerbacher
"""


class SkipMovieException(Exception):
    def __init__(self):
        super().__init__()


class UserExitException(Exception):
    def __init__(self):
        super().__init__()


class StopPlayingGroup(Exception):
    def __init__(self):
        super().__init__()