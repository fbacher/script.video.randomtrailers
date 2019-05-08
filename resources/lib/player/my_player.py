# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from typing import Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence
from kodi_six import xbmcgui, utils

from player.advanced_player import AdvancedPlayer
from common.logger import Logger
from common.constants import Movie
from common.utils import Utils
from common.monitor import Monitor
import os


class MyPlayer(AdvancedPlayer):

    def __init__(self):
        super().__init__()
        self._logger = Logger(self.__class__.__name__)
        self._expectedTitle = None
        self._expectedFilePath = None
        self._isURL = False
        self._isActivated = True

    def playTrailer(self, path, trailer):
        localLogger = self._logger.getMethodLogger(u'playTrailer')

        title = trailer[Movie.TITLE]
        filePath = trailer.get(Movie.NORMALIZED_TRAILER, None)
        if filePath is None:
            filePath = trailer[Movie.TRAILER]
        filePath = utils.py2_decode(filePath)
        fileName = os.path.basename(filePath)
        passedFileName = utils.py2_decode(os.path.basename(path))
        if fileName != passedFileName:
            localLogger.debug(u'passed file name:', passedFileName,
                              u'trailer fileName:', fileName,)

        listitem = xbmcgui.ListItem(title)
        listitem.setInfo(
            u'video', {u'title': title, u'genre': u'randomtrailers',
            u'Genre': u'randomtrailers',
                       u'trailer': passedFileName, u'path': utils.py2_decode(path),
                       u'mediatype': u'video', u'tag': u'randomtrailers'})
        listitem.setPath(filePath)

        self.setPlayingTitle(title)
        self.setPlayingFilePath(filePath)
        localLogger.debug(u'path:', fileName, u'title:', title)

        self.play(item=path, listitem=listitem)

    def play(self, item="", listitem=None, windowed=False, startpos=-1):
        super().play(item, listitem, windowed, startpos)

    def setPlayingTitle(self, title):
        self._expectedTitle = title

    def setPlayingFilePath(self, filePath):
        filePath = utils.py2_decode(filePath)
        self._isURL = Utils.isURL(filePath)
        self._expectedFilePath = filePath

    def onAVStarted(self):
        localLogger = self._logger.getMethodLogger(u'onAVStarted')

        self.dumpData(u'onAVStarted')

        try:
            genre = utils.py2_decode(self.getVideoInfoTag().getGenre())
            if genre != u'randomtrailers':
                playingFile = super().getPlayingFile()
                playingFile = utils.py2_decode(playingFile)
                if self._isURL and Utils.isURL(playingFile):
                    localLogger.debug(u'URLs used. Consider pass')
                else:
                    # Do not use this player anymore until
                    self._isActivated = False
                    localLogger.debug(u'Genre and URL test failed.',
                                      u'Genre:', genre,
                                      u'playingFile:', playingFile,
                                      u'expectedPlayingFile:',
                                      self._expectedFilePath)
                    Monitor.getInstance().onScreensaverDeactivated()
            else:
                localLogger.debug(u'Genre passed')
        except (Exception) as e:
            pass


    def isPlayingExpectedTitle(self):
        localLogger = self._logger.getMethodLogger(u'isPlayingExpectedTitle')

        playingTitle = super().getPlayingTitle()
        videoInfo = super().getVideoInfoTag()
        if videoInfo is not None:
            title2 = utils.py2_decode(videoInfo.getTitle())
            localLogger.debug(u'title2:', title2, u'title:',
                              self._expectedTitle)
        if playingTitle != self._expectedTitle:
            localLogger.debug(u'Expected to play:', self._expectedTitle, u'Playing:',
                              playingTitle)
            return False
        else:
            return True

    def isPlayingExpectedFile(self):
        localLogger = self._logger.getMethodLogger(
            u'isPlayingExpectedFile')
        playingFile = super().getPlayingFile()
        playingFile = utils.py2_decode(playingFile)
        playingFile = os.path.basename(playingFile)
        videoInfo = super().getVideoInfoTag()
        if videoInfo is not None:
            playingFile2 = videoInfo.getFile()
            playingFile2 = utils.py2_decode(playingFile2)
            playingFile2 = os.path.dirname(playingFile2)
            localLogger.debug(u'expected:', self._expectedFilePath, u'file2:',
                              playingFile2)
        if playingFile != os.path.dirname(self._expectedFilePath):
            localLogger.debug(u'Expected to play:', self._expectedFilePath, u'Playing:',
                              playingFile)
            return False
        else:
            return True


    def dumpData(self, context):
        localLogger = self._logger.getMethodLogger(
            u'dumpData')

        infoTagVideo = self.getVideoInfoTag()
        localLogger.debug(u'context:', context, u'title:', infoTagVideo.getTitle(),
                          u'genre:', infoTagVideo.getGenre(),
                          u'trailer:', infoTagVideo.getTrailer())

    def isActivated(self):
        return self._isActivated
