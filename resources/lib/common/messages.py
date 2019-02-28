'''
Created on Feb 28, 2019

@author: fbacher
'''


class Messages:

    TRAILER_EXCEEDS_MAX_PLAY_TIME = u'This trailer exceeds the maximum play time. Terminating'
    TMDB_LABEL = u'TMDb'  # Offical name
    _instance = None

    def __init__(self):
        pass

    @staticmethod
    def getInstance():
        if Messages._instance is None:
            Messages._instance = Messages()
        return Messages._instance

    def getMsg(self, msgKey):
        return msgKey
