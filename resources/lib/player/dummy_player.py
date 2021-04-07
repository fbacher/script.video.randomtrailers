# -*- coding: utf-8 -*-

from common.imports import *

from common.monitor import Monitor


class PlayerState:
    STATE_STOPPED = 'stopped'
    STATE_PLAYING = 'playing'
    STATE_PAUSED = 'paused'


class DummyPlayer:

    def __init__(self):
        return

    def register_exit_on_movie_playing(self, listener):
        pass

    def setCallBacks(self, on_video_window_opened=None, on_video_window_closed=None,
                     on_show_osd=None, on_show_info=None):
        return

    def enableAdvancedMonitoring(self):
        return

    def disableAdvancedMonitoring(self, shutdown=False):
        return

    def reset(self):
        return

    def control(self, cmd):
        return

    @property
    def playState(self):
        return 'dummyState'

    def isVideoFullscreen(self):
        return True

    def play_trailer(self, path, trailer):
        return

    def play(self, item="", listitem=None, windowed=False, startpos=-1):
        return

    def stop(self):
        return

    def pause(self):
        return

    def pausePlay(self):
        return

    def resumePlay(self):
        return

    def playnext(self):
        return

    def playprevious(self):
        return

    def playselected(self, selected):
        # type: (int) -> None
        return

    def isPlaying(self):
        return False

    def myIsPlayingVideo(self):
        return False

    def isPlayingAudio(self):
        return False

    def isPlayingVideo(self):
        return False

    def isPlayingRDS(self):
        return False

    def isPaused(self):
        return False

    def isExternalPlayer(self):
        return False

    def isFinished(self):
        return True

    def getPlayingFile(self):
        return ''

    def _dumpState(self):
        return

    def getTime(self):
        return 0

    def seekTime(self, seekTime):
        return 0

    def setSubtitles(self, subtitleFile):
        return

    def showSubtitles(self, bVisible):
        return

    def getSubtitles(self):
        return ''

    def getAvailableSubtitleStreams(self):
        return []

    def setSubtitleStream(self, iStream):
        return

    def updateInfoTag(self, item):
        return

    def getVideoInfoTag(self):
        return None

    def getMusicInfoTag(self):
        return None

    def getRadioRDSInfoTag(self):
        return None

    def getTotalTime(self):
        return 0

    def getAvailableAudioStreams(self):
        return []

    def setAudioStream(self, iStream):
        return

    def getAvailableVideoStreams(self):
        return []

    def setVideoStream(self, iStream):
        return

    def getPlayingTitle(self):
        return ''

    def killPlayer(self):
        return

    def onPrePlayStarted(self):
        return

    def onPlayBackStarted(self):
        return

    def onAVStarted(self):
        return

    def waitForIsPlayingVideo(self, timeout=None):

        Monitor.throw_exception_if_abort_requested()
        return False

    def waitForIsNotPlayingVideo(self, timeout=None, trace=None):
        Monitor.throw_exception_if_abort_requested()
        return True

    def onAVChange(self):
        return

    def onPlayBackEnded(self):
        return

    def onPlayBackFailed(self):
        return

    def onPlayBackStopped(self):
        return

    def onPlayBackError(self):
        return

    def onPlayBackPaused(self):
        return

    def onPlayBackResumed(self):
        return

    def onPlayBackSeek(self, time, seekOffset):
        return

    def onPlayBackSeekChapter(self, chapter):
        return

    def onPlayBackSpeedChanged(self, speed):
        return

    def onQueueNextItem(self):
        return

    def onVideoWindowOpened(self):
        return

    def onVideoWindowClosed(self):
        return

    def showOSD(self, from_seek=False):
        return

    def hideOSD(self, delete=False):
        return

    def onVideoOSD(self):
        return

    def onShowInfo(self):
        return

    def tick(self):
        pass

    def onSeekOSD(self):
        return

    def killPlayingTrailer(self):
        return

    def monitor(self):
        return

    def is_activated(self):
        return False
