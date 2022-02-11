# -*- coding: utf-8 -*-
from abc import ABC, abstractclassmethod, abstractmethod, abstractproperty
import xbmcgui
from xbmc import InfoTagMusic, InfoTagRadioRDS, InfoTagVideo, PlayList

from common.imports import *

from common.monitor import Monitor


class PlayerState:
    STATE_STOPPED = 'stopped'
    STATE_PLAYING = 'playing'
    STATE_PAUSED = 'paused'


class AbstractPlayer(ABC):

    def __init__(self) -> None:
        return

    @abstractmethod
    def register_exit_on_movie_playing(self, listener) -> None:
        pass

    @abstractmethod
    def set_callbacks(self,
                      on_video_window_opened: Callable[[Any], Any] = None,
                      on_video_window_closed: Callable[[Any], Any] = None,
                      on_show_osd: Callable[[Any], Any] = None,
                      on_show_info: Callable[[Any], Any] = None) -> None:
        return

    @abstractmethod
    def enable_advanced_monitoring(self) -> None:
        return

    @abstractmethod
    def disable_advanced_monitoring(self, shutdown: bool = False) -> None:
        return

    @abstractmethod
    def reset(self) -> None:
        return

    @abstractmethod
    def control(self, cmd: str) -> None:
        return

    @property
    def play_state(self) -> str:
        return 'dummyState'

    @abstractmethod
    def is_video_fullscreen(self) -> bool:
        return True

    @abstractmethod
    def play_trailer(self, path, trailer):
        return

    @abstractmethod
    def play(self,
             item: Union[PlayList, str] = "",
             listitem: xbmcgui.ListItem = None,
             windowed: bool = False,
             startpos: int = -1) -> None:
        return

    @abstractmethod
    def stop(self) -> None:
        return

    @abstractmethod
    def pause(self) -> None:
        return

    @abstractmethod
    def pause_play(self) -> None:
        return

    @abstractmethod
    def resume_play(self) -> None:
        return

    @abstractmethod
    def playnext(self) -> None:
        return

    @abstractmethod
    def playprevious(self) -> None:
        return

    @abstractmethod
    def playselected(self, selected: int) -> None:
        return

    @abstractmethod
    def isPlaying(self) -> bool:
        return False

    @abstractmethod
    def myIsPlayingVideo(self):
        return False

    @abstractmethod
    def isPlayingAudio(self) -> bool:
        return False

    @abstractmethod
    def isPlayingVideo(self) -> bool:
        return False

    @abstractmethod
    def isPlayingRDS(self) -> bool:
        return False

    @abstractmethod
    def is_paused(self) -> bool:
        return False

    @abstractmethod
    def isExternalPlayer(self) -> bool:
        return False

    @abstractmethod
    def is_finished(self) -> bool:
        return True

    @abstractmethod
    def getPlayingFile(self) -> str:
        return ''

    @abstractmethod
    def _dumpState(self):
        return

    @abstractmethod
    def getTime(self) -> float:
        return 0

    @abstractmethod
    def seekTime(self, seek_time) -> None:
        return

    @abstractmethod
    def setSubtitles(self, subtitle_file: Any) -> None:
        return

    @abstractmethod
    def showSubtitles(self, b_visible: bool) -> None:
        return

    @abstractmethod
    def getSubtitles(self) -> str:
        return ''

    @abstractmethod
    def getAvailableSubtitleStreams(self) -> List[str]:
        return []

    @abstractmethod
    def setSubtitleStream(self, i_stream: int) -> None:
        return

    @abstractmethod
    def updateInfoTag(self, item: xbmcgui.ListItem) -> None:
        return

    @abstractmethod
    def getVideoInfoTag(self) -> InfoTagVideo:
        return None

    @abstractmethod
    def getMusicInfoTag(self) -> InfoTagMusic:
        return None

    @abstractmethod
    def getRadioRDSInfoTag(self) -> InfoTagRadioRDS:
        return None

    @abstractmethod
    def getTotalTime(self) -> float:
        return 0.0

    @abstractmethod
    def getAvailableAudioStreams(self) -> List[str]:
        return []

    @abstractmethod
    def setAudioStream(self, i_stream: int) -> None:
        return

    @abstractmethod
    def getAvailableVideoStreams(self) -> List[str]:
        return []

    @abstractmethod
    def setVideoStream(self, i_stream: int) -> None:
        return

    @abstractmethod
    def get_playing_title(self) -> str:
        return ''

    @abstractmethod
    def kill_player(self) -> None:
        return

    @abstractmethod
    def on_preplay_started(self) -> None:
        return

    @abstractmethod
    def onPlayBackStarted(self) -> None:
        return

    @abstractmethod
    def onAVStarted(self) -> None:
        return

    @abstractmethod
    def wait_for_is_playing_video(self, timeout: float = None) -> bool:

        Monitor.throw_exception_if_abort_requested()
        return False

    @abstractmethod
    def wait_for_is_not_playing_video(self,
                                      timeout: float = None,
                                      trace: str = None) -> bool:
        Monitor.throw_exception_if_abort_requested()
        return True

    @abstractmethod
    def onAVChange(self) -> None:
        return

    @abstractmethod
    def onPlayBackEnded(self)  -> None:
        return

    @abstractmethod
    def on_playback_failed(self) -> None:
        return

    @abstractmethod
    def onPlayBackStopped(self) -> None:
        return

    @abstractmethod
    def onPlayBackError(self) -> None:
        return

    @abstractmethod
    def onPlayBackPaused(self):
        return

    @abstractmethod
    def onPlayBackResumed(self) -> None:
        return

    @abstractmethod
    def onPlayBackSeek(self, time: int, seekOffset: int) -> None:
        return

    @abstractmethod
    def onPlayBackSeekChapter(self, chapter: int) -> None:
        return

    @abstractmethod
    def onPlayBackSpeedChanged(self, speed: int) -> None:
        return

    @abstractmethod
    def onQueueNextItem(self) -> None:
        return

    @abstractmethod
    def on_video_window_opened(self) -> None:
        return

    @abstractmethod
    def on_video_window_closed(self) -> None:
        return

    @abstractmethod
    def show_osd(self, from_seek: bool = False) -> None:
        return

    @abstractmethod
    def hide_osd(self, delete=False) -> None:
        return

    @abstractmethod
    def on_video_osd(self) -> None:
        return

    @abstractmethod
    def on_show_info(self) -> None:
        return

    @abstractmethod
    def tick(self):
        pass

    @abstractmethod
    def on_seek_osd(self) -> None:
        return

    @abstractmethod
    def kill_playing_trailer(self) -> None:
        return

    @abstractmethod
    def monitor(self) -> None:
        return

    @abstractmethod
    def is_activated(self) -> bool:
        return False

