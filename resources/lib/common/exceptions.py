# -*- coding: utf-8 -*-

"""
Created on Feb 19, 2019

@author: Frank Feuerbacher
"""


# From six
def reraise(tp, value, tb=None):
    try:
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value
    finally:
        value = None
        tb = None


class AbortException(Exception):
    def __init__(self):
        super().__init__


class LaunchException(Exception):
    def __init__(self):
        super().__init__


class TrailerIdException(Exception):
    def __init__(self):
        super().__init__


class LogicError(Exception):
    def __init__(self):
        super().__init__


class DuplicateException(Exception):
    def __init__(self):
        super().__init__

# Something went wrong trying to communicate. Could be network failure
# or could be api failure, perhaps even failure in RandomTrailers


class CommunicationException(Exception):
    def __init__(self):
        super().__init__
