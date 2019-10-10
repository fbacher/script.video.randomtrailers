# -*- coding: utf-8 -*-

"""
Created on Feb 19, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals


class ShutdownException(Exception):
    pass


class AbortException(ShutdownException):
    pass


class LaunchException(Exception):
    pass


class TrailerIdException(Exception):
    pass


class LogicError(Exception):
    pass