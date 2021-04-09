# -*- coding: utf-8 -*-
import xbmcgui
from xbmc import InfoTagMusic, InfoTagRadioRDS, InfoTagVideo, PlayList

from common.imports import *

from common.monitor import Monitor


class PlayerState:
    STATE_STOPPED = 'stopped'
    STATE_PLAYING = 'playing'
    STATE_PAUSED = 'paused'


class DummyPlayer:

    def __init__(self) -> None:
        return

    def register_exit_on_movie_playing(self, listener) -> None:
        pass

    def set_callbacks(self,
                      on_video_window_opened: Callable[[Any], Any] = None,
                      on_video_window_closed: Callable[[Any], Any] = None,
                      on_show_osd: Callable[[Any], Any] = None,
                      on_show_info: Callable[[Any], Any] = None) -> None:
        return

    def enable_advanced_monitoring(self) -> None:
        return

    def disable_advanced_monitoring(self, shutdown: bool = False) -> None:
        return

    def reset(self) -> None:
        return

    def control(self, cmd: str) -> None:
        return

    @property
    def play_state(self) -> str:
        return 'dummyState'

    def is_video_fullscreen(self) -> bool:
        return True

    def play_trailer(self, path, trailer):
        return

    def play(self,
             item: Union[PlayList, str] = "",
             listitem: xbmcgui.ListItem = None,
             windowed: bool = False,
             startpos: int = -1) -> None:
        return

    def stop(self) -> None:
        return

    def pause(self) -> None:
        return

    def pause_play(self) -> None:
        return

    def resume_play(self) -> None:
        return

    def playnext(self) -> None:
        return

    def playprevious(self) -> None:
        return

    def playselected(self, selected: int) -> None:
        return

    def isPlaying(self) -> bool:
        return False

    def myIsPlayingVideo(self):
        return False

    def isPlayingAudio(self) -> bool:
        return False

    def isPlayingVideo(self) -> bool:
        return False

    def isPlayingRDS(self) -> bool:
        return False

    def is_paused(self) -> bool:
        return False

    def isExternalPlayer(self) -> bool:
        return False

    def is_finished(self) -> bool:
        return True

    def getPlayingFile(self) -> str:
        return ''

    def _dumpState(self):
        return

    def getTime(self) -> float:
        return 0

    def seekTime(self, seek_time) -> None:
        return 0

    def setSubtitles(self, subtitle_file: Any) -> None:
        return

    def showSubtitles(self, b_visible: bool) -> None:
        return

    def getSubtitles(self) -> str:
        return ''

    def getAvailableSubtitleStreams(self) -> List[str]:
        return []

    def setSubtitleStream(self, i_stream: int) -> None:
        return

    def updateInfoTag(self, item: xbmcgui.ListItem) -> None:
        return

    def getVideoInfoTag(self) -> InfoTagVideo:
        return None

    def getMusicInfoTag(self) -> InfoTagMusic:
        return None

    def getRadioRDSInfoTag(self) -> InfoTagRadioRDS:
        return None

    def getTotalTime(self) -> float:
        return 0.0

    def getAvailableAudioStreams(self) -> List[str]:
        return []

    def setAudioStream(self, i_stream: int) -> None:
        return

    def getAvailableVideoStreams(self) -> List[str]:
        return []

    def setVideoStream(self, i_stream: int) -> None:
        return

    def get_playing_title(self) -> str:
        return ''

    def kill_player(self) -> None:
        return

    def on_preplay_started(self) -> None:
        return

    def onPlayBackStarted(self) -> None:
        return

    def onAVStarted(self) -> None:
        return

    def wait_for_is_playing_video(self, timeout: float = None) -> bool:

        Monitor.throw_exception_if_abort_requested()
        return False

    def wait_for_is_not_playing_video(self,
                                  timeout: float = None,
                                  trace: str = None) -> bool:
        Monitor.throw_exception_if_abort_requested()
        return True

    def onAVChange(self) -> None:
        return

    def onPlayBackEnded(self)  -> None:
        return

    def on_playback_failed(self) -> None:
        return

    def onPlayBackStopped(self) -> None:
        return

    def onPlayBackError(self) -> None:
        return

    def onPlayBackPaused(self):
        return

    def onPlayBackPaused(self) -> None:
        return

    def onPlayBackResumed(self) -> None:
        return

    def onPlayBackSeek(self, time: int, seekOffset: int) -> None:
        return

    def onPlayBackSeekChapter(self, chapter: int) -> None:
        return

    def onPlayBackSpeedChanged(self, speed: int) -> None:
        return

    def onQueueNextItem(self) -> None:
        return

    def on_video_window_opened(self) -> None:
        return

    def on_video_window_closed(self) -> None:
        return

    def show_osd(self, from_seek: bool = False) -> None:
        return

    def hide_osd(self, delete=False) -> None:
        return

    def on_video_osd(self) -> None:
        return

    def on_show_info(self) -> None:
        return

    def tick(self):
        pass

    def on_seek_osd(self) -> None:
        return

    def kill_playing_trailer(self) -> None:
        return

    def monitor(self) -> None:
        return

    def is_activated(self) -> bool:
        return False
