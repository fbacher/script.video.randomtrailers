# -*- coding: utf-8 -*-

"""
Created on Feb 19, 2019

@author: Frank Feuerbacher
"""


class AbortException(Exception):
    pass


class LaunchException(Exception):
    pass


class TrailerIdException(Exception):
    pass


class LogicError(Exception):
    pass


class DuplicateException(Exception):
    pass

# Something went wrong trying to communicate. Could be network failure
# or could be api failure, perhaps even failure in RandomTrailers

class CommunicationException(Exception):
    pass
