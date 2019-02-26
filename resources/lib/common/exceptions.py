'''
Created on Feb 19, 2019

@author: fbacher
'''


class ShutdownException(Exception):
    pass


class AbortException(ShutdownException):
    pass
