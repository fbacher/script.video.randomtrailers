# -*- coding: utf-8 -*-
import sys
import threading

import xbmc
import xbmcgui
from xbmc import PlayList, InfoTagVideo, InfoTagMusic, InfoTagRadioRDS

from common.imports import *
from common.exceptions import AbortException
from common.logger import LazyLogger, Trace
from common.monitor import Monitor

module_logger: LazyLogger = LazyLogger.get_addon_module_logger(file_path=__file__)
DEBUG_PLAYER: int = LazyLogger.DISABLED


class PlayerState:
    STATE_STOPPED: Final[str] = 'stopped'
    STATE_PLAYING: Final[str] = 'playing'
    STATE_PAUSED: Final[str] = 'paused'


class AdvancedPlayer(xbmc.Player):
    """

    """
    DEBUG_MONITOR: Final[bool] = False
    _logger: LazyLogger = None

    def __init__(self):
        super().__init__()

        if AdvancedPlayer._logger is None:
            AdvancedPlayer._logger = module_logger.getChild(type(self).__name__)

        self._is_playing: bool = False
        self._is_finished: bool = False
        self._monitor_thread: threading.Thread = None
        self._closed: bool = True
        self._has_osd: bool = False
        self._has_seek_osd: bool = False
        self._has_show_info: bool = False
        self._player_window_open: bool = False
        self._call_back_on_show_info: Callable[[Any], Any] = None
        self._player_state: str = PlayerState.STATE_STOPPED
        self.started: bool = False

    def set_callbacks(self,
                      on_video_window_opened: Callable[[Any], Any] = None,
                      on_video_window_closed: Callable[[Any], Any] = None,
                      on_show_osd: Callable[[Any], Any] = None,
                      on_show_info: Callable[[Any], Any] = None) -> None:
        self._call_back_on_show_info = on_show_info

    def enable_advanced_monitoring(self) -> None:
        self._closed = False
        self.monitor()

    def disable_advanced_monitoring(self, shutdown: bool = False) -> None:
        self._closed = True
        try:
            if self._monitor_thread is not None and self._monitor_thread.isAlive():
                self._monitor_thread.join(0.1)
        finally:
            self._monitor_thread = None

    def reset(self) -> None:
        local_class = AdvancedPlayer
        if local_class._logger.isEnabledFor(DEBUG_PLAYER):
            local_class._logger.enter()
        self.started = False

    def control(self, cmd: str) -> None:
        local_class = AdvancedPlayer

        if cmd == 'play':
            if local_class._logger.isEnabledFor(DEBUG_PLAYER):
                local_class._logger.debug_extra_verbose('Command=Play')
            if xbmc.getCondVisibility('Player.Paused | !Player.Playing'):
                if local_class._logger.isEnabledFor(DEBUG_PLAYER):
                    local_class._logger.debug_extra_verbose('Playing')
                xbmc.executebuiltin('PlayerControl(Play)')
        elif cmd == 'pause':
            if local_class._logger.isEnabledFor(DEBUG_PLAYER):
                local_class._logger.debug_extra_verbose('Command=Pause')
            if not xbmc.getCondVisibility('Player.Paused'):
                if local_class._logger.isEnabledFor(DEBUG_PLAYER):
                    local_class._logger.debug_extra_verbose(' Pausing')
                xbmc.executebuiltin('PlayerControl(Play)')

    @property
    def play_state(self) -> str:
        local_class = AdvancedPlayer

        if xbmc.getCondVisibility('Player.Playing'):
            play_state = PlayerState.STATE_PLAYING
        elif xbmc.getCondVisibility('Player.Paused'):
            play_state = PlayerState.STATE_PAUSED
        else:
            play_state = PlayerState.STATE_STOPPED
        if local_class._logger.isEnabledFor(DEBUG_PLAYER):
            local_class._logger.debug_extra_verbose('play_state: ' + play_state)
        # self._dump_state()  # TODO: remove
        return play_state

    def is_video_fullscreen(self) -> bool:
        is_fullscreen = bool(xbmc.getCondVisibility('VideoPlayer.IsFullscreen'))
        return is_fullscreen

    # Defined in xbmc.Player
    def play(self,
             item: Union[PlayList, str] = "",
             listitem: xbmcgui.ListItem = None,
             windowed: bool = False,
             startpos: int = -1) -> None:
        """
        Play a item.

        :param item: [opt] string - filename, url or playlist
        :param listitem: [opt] listitem - used with setInfo() to set different
            infolabels.
        :param windowed: [opt] bool - true=play video windowed,
            false=play users preference.(default)
        :param startpos: [opt] int - starting position when playing a playlist.
            Default = -1

        If item is not given then the Player will try to play the current item
        in the current playlist. You can use the above as keywords for arguments
        and skip certain optional arguments. Once you use a keyword,
        all following arguments require the keyword.

        Example::

            listitem = xbmcgui.ListItem('Ironman')
            listitem.setInfo('video', {'Title': 'Ironman', 'Genre': 'Science Fiction'})
            xbmc.Player().play(url, listitem, windowed)
            xbmc.Player().play(playlist, listitem, windowed, startpos)
        """
        local_class = AdvancedPlayer

        Monitor.throw_exception_if_abort_requested()

        if type(self).DEBUG_MONITOR:
            local_class._logger.enter()
        super().play(item, listitem, windowed, startpos)
        self.enable_advanced_monitoring()

    # Defined in xbmc.Player
    def stop(self) -> None:
        """
        Stop playing.
        """
        local_class = AdvancedPlayer

        if (type(self).DEBUG_MONITOR and
                local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
            local_class._logger.enter()
        super().stop()

    # Defined in xbmc.Player
    def pause(self) -> None:
        """
        Toggle play/pause state
        """
        local_class = AdvancedPlayer

        if (type(self).DEBUG_MONITOR and
                local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
            local_class._logger.enter()
        super().pause()
        #self._dump_state()  # TODO: remove

    def pause_play(self) -> None:
        local_class = AdvancedPlayer

        if (local_class._logger.isEnabledFor(DEBUG_PLAYER)
                and local_class._logger.isEnabled(LazyLogger.DEBUG_EXTRA_VERBOSE)):
            local_class._logger.enter()
        if self.play_state == PlayerState.STATE_PLAYING:
            # self._dump_state()  # TODO: remove
            self.pause()

    def resume_play(self) -> None:
        local_class = AdvancedPlayer

        if local_class._logger.isEnabledFor(DEBUG_PLAYER):
            local_class._logger.enter()
        if self.play_state == PlayerState.STATE_PAUSED:
            # self._dump_state()  # TODO: remove
            self.pause()

    # Defined in xbmc.Player
    def playnext(self) -> None:
        """
        Play next item in playlist.
        """
        local_class = AdvancedPlayer

        if local_class._logger.isEnabledFor(DEBUG_PLAYER):
            local_class._logger.enter()
        super().playnext()
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def playprevious(self) -> None:
        """
        Play previous item in playlist.
        """
        local_class = AdvancedPlayer

        if local_class._logger.isEnabledFor(DEBUG_PLAYER):
            local_class._logger.enter()
        super().playprevious()
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def playselected(self, selected: int) -> None:
        """
        Play a certain item from the current playlist.

        :param selected: Integer - Item to select
        """
        local_class = AdvancedPlayer

        if local_class._logger.isEnabledFor(DEBUG_PLAYER):
            local_class._logger.enter()
        super().playselected(selected)
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def isPlaying(self) -> bool:
        """
        Is Kodi is playing something.

        :return: True if Kodi is playing a file.
        """
        local_class = AdvancedPlayer

        self._is_playing = bool(super().isPlaying())
        return self._is_playing

    # Defined in xbmc.Player
    def isPlayingAudio(self) -> bool:
        """
        Is Kodi playing audio.

        :return: True if Kodi is playing an audio file.
        """
        local_class = AdvancedPlayer

        playing_audio = bool(super().isPlayingAudio())
        # local_class._logger.debug(str(playing_audio))
        return playing_audio

    # Defined in xbmc.Player
    def isPlayingVideo(self) -> bool:
        """
        Is Kodi playing video.

        :return: True if Kodi is playing a video.
        """
        local_class = AdvancedPlayer

        isPlaying = bool(super().isPlayingVideo())

        return isPlaying

    # Defined in xbmc.Player
    def isPlayingRDS(self) -> bool:
        """
        Check for playing radio data system (RDS).

        :return: True if kodi is playing a radio data system (RDS).
        """
        local_class = AdvancedPlayer

        playing_rds = bool(super().isPlayingRDS())
        return playing_rds

    def is_paused(self) -> bool:
        local_class = AdvancedPlayer
        paused = False
        if self._player_state == PlayerState.STATE_PAUSED:
            paused = True
        return True

    # Defined in xbmc.Player
    def isExternalPlayer(self) -> bool:
        """
        Is Kodi using an external player.

        :return: True if kodi is playing using an external player.

        New function added.
        """
        local_class = AdvancedPlayer
        external_player = bool(super().isExternalPlayer())
        return external_player

    def is_finished(self) -> bool:
        local_class = AdvancedPlayer
        if local_class._logger.isEnabledFor(DEBUG_PLAYER):
            local_class._logger.debug_extra_verbose('value:', self._is_finished)
        return self._is_finished

    # Defined in xbmc.Player
    def getPlayingFile(self) -> str:
        """
        Returns the current playing file as a string.

        For LiveTV, returns a ``pvr://`` url which is not translatable to
        an OS specific file or external url.

        :return: Playing filename
        :raises Exception: If player is not playing a file.
        """
        local_class = AdvancedPlayer
        playing_file = ''
        try:
            playing_file = super().getPlayingFile()

            if local_class._logger.isEnabledFor(DEBUG_PLAYER):
                local_class._logger.debug_extra_verbose('playing_file: ' + playing_file)
        except Exception as e:
            pass
        finally:
            return playing_file

    def _dump_state(self) -> None:
        local_class = AdvancedPlayer
        if local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            self.is_video_fullscreen()
            self.isPlaying()
            self.isPlayingAudio()
            self.isPlayingVideo()
            self.isPlayingRDS()
            self.isExternalPlayer()
            self.isFinished()
            local_class._logger.debug_extra_verbose('play_state: ', self._player_state)

            # self.getPlayingFile()
            # self.getTime()
            # self.getSubtitles()
            # self.getAvailableSubtitleStreams()
            # self.getVideoInfoTag()
            # self.getMusicInfoTag()
            # self.getRadioRDSInfoTag()
            # self.getTotalTime()
            # self.getAvailableAudioStreams()
            # self.get_playing_title()

    # Defined in xbmc.Player
    def getTime(self) -> float:
        """
        Get playing time.

        Returns the current time of the current playing media as fractional seconds.

        :return: Current time as fractional seconds
        :raises Exception: If player is not playing a file.
        """
        local_class = AdvancedPlayer
        time: float = 0.0
        try:
            time = super().getTime()
        except Exception:
            pass

        return time

    # Defined in xbmc.Player
    def seekTime(self, seek_time) -> None:
        """
        Seek time.

        Seeks the specified amount of time as fractional seconds. The time
        specified is relative to the beginning of the currently
        playing media file.

        :param seek_time: Time to seek as fractional seconds
        :raises Exception: If player is not playing a file.
        """
        local_class = AdvancedPlayer
        seek_time = 0
        try:
            super().seekTime(seek_time)
        except Exception:
            pass
        finally:
            return

    # Defined in xbmc.Player
    def setSubtitles(self, subtitle_file: Any) -> None:
        """
        Set subtitle file and enable subtitles.

        :param subtitle_file: File to use as source of subtitles
        """
        local_class = AdvancedPlayer
        return super().setSubtitles(subtitle_file)

    # Defined in xbmc.Player
    def showSubtitles(self, b_visible: bool) -> None:
        """
        Enable / disable subtitles.

        :param b_visible: [boolean] True for visible subtitles.

        Example::

            xbmc.Player().showSubtitles(True)
        """
        local_class = AdvancedPlayer
        return super().showSubtitles(b_visible)

    # Defined in xbmc.Player
    def getSubtitles(self) -> str:
        """
        Get subtitle stream name.

        :return: Stream name
        """
        local_class = AdvancedPlayer
        return super().getSubtitles()

    # Defined in xbmc.Player
    def getAvailableSubtitleStreams(self) -> List[str]:
        """
        Get Subtitle stream names.

        :return: List of subtitle streams as name
        """
        return super().getAvailableSubtitleStreams()

    # Defined in xbmc.Player
    def setSubtitleStream(self, i_stream: int) -> None:
        """
        Set Subtitle Stream.

        :param i_stream: [int] Subtitle stream to select for play

        Example::

            xbmc.Player().setSubtitleStream(1)
        """
        return super().setSubtitleStream(i_stream)

    # Defined in xbmc.Player
    def updateInfoTag(self, item: xbmcgui.ListItem) -> None:
        """
        Update info labels for currently playing item.

        :param item: ListItem with new info
        :raises Exception: If player is not playing a file

        New function added.

        Example::

            item = xbmcgui.ListItem()
            item.setPath(xbmc.Player().getPlayingFile())
            item.setInfo('music', {'title' : 'foo', 'artist' : 'bar'})
            xbmc.Player().updateInfoTag(item)
        """
        super().updateInfoTag(item)

    # Defined in xbmc.Player
    def getVideoInfoTag(self) -> InfoTagVideo:
        """
        To get video info tag.

        Returns the VideoInfoTag of the current playing Movie.

        :return: Video info tag
        :raises Exception: If player is not playing a file or current file
            is not a movie file.
        """
        return super().getVideoInfoTag()

    # Defined in xbmc.Player
    def getMusicInfoTag(self) -> InfoTagMusic:
        """
        To get music info tag.

        Returns the MusicInfoTag of the current playing 'Song'.

        :return: Music info tag
        :raises Exception: If player is not playing a file or current file
            is not a music file.
        """
        return super().getMusicInfoTag()

    # Defined in xbmc.Player
    def getRadioRDSInfoTag(self) -> InfoTagRadioRDS:
        """
        To get Radio RDS info tag

        Returns the RadioRDSInfoTag of the current playing 'Radio Song if. present'.

        :return: Radio RDS info tag
        :raises Exception: If player is not playing a file or current file
            is not a rds file.
        """
        try:
            return super().getRadioRDSInfoTag()
        except Exception:
            return None

    # Defined in xbmc.Player
    def getTotalTime(self) -> float:
        """
        To get total playing time.

        Returns the total time of the current playing media in seconds.
        This is only accurate to the full second.

        :return: Total time of the current playing media
        :raises Exception: If player is not playing a file.
        """
        try:
            return super().getTotalTime()
        except Exception:
            return 0

    # Defined in xbmc.Player
    def getAvailableAudioStreams(self) -> List[str]:
        """
        Get Audio stream names

        :return: List of audio streams as name
        """
        return super().getAvailableAudioStreams()

    # Defined in xbmc.Player
    def setAudioStream(self, i_stream: int) -> None:
        """
        Set Audio Stream.

        :param i_stream: [int] Audio stream to select for play

        Example::

            xbmc.Player().setAudioStream(1)
        """
        return super().setAudioStream(i_stream)

    # Defined in xbmc.Player
    def getAvailableVideoStreams(self) -> List[str]:
        """
        Get Video stream names

        :return: List of video streams as name
        """
        return super().getAvailableVideoStreams()

    # Defined in xbmc.Player
    def setVideoStream(self, i_stream: int) -> None:
        """
        Set Video Stream.

        :param i_stream: [int] Video stream to select for play

        Example::

            xbmc.Player().setVideoStream(1)
        """
        return super().setVideoStream(i_stream)

    def get_playing_title(self) -> str:
        local_class = AdvancedPlayer
        title = None
        try:
            playing_file = super().getPlayingFile()
        except Exception as e:
            playing_file = 'unknown'
        try:
            info_tag = self.getVideoInfoTag()
            title = info_tag.getTitle()
        except Exception as e:
            title = "Exception- Nothing Playing?"
            self._is_finished = True

        return title

    def kill_player(self) -> None:
        local_class = AdvancedPlayer
        if local_class._logger.isEnabledFor(DEBUG_PLAYER):
            local_class._logger.enter()
        if not self._is_finished:
            xbmc.executebuiltin('xbmc.PlayerControl(Stop)')

        self._is_finished = True

    def on_preplay_started(self) -> None:
        pass

    """
    # Defined in xbmc.Player
    def onPlayBackStarted(self):
        '''
        onPlayBackStarted method.

        Will be called when Kodi player starts. Video or audio might not be available at
        this point.

        v18 Python API changes:
        Use onAVStarted() instead if you need to detect if Kodi is actually playing
        a media file (i.e, if a stream is available)
        '''

        if local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            local_class._logger.debug_verbose('You probably want to use onAVStarted instead')
        # self._dump_state()  # TODO: remove

    """

    # Defined in xbmc.Player
    def onAVStarted(self) -> None:
        '''
        Will be called when Kodi has a video or audiostream.

        v18 Python API changes:
            New function added.
        '''
        local_class = AdvancedPlayer
        if local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
            local_class._logger.debug_verbose(
                self.get_playing_title(), trace=Trace.TRACE)

        # self._dump_state()  # TODO: remove

    def wait_for_is_playing_video(self, timeout: float = None) -> bool:
        '''
        This is a mess.

        The preferred way to deal with this is to monitor onPlayBackStarted/
        onPlayBackEnded events, but onPlayBackEnded is not reliably sent.
        So, poll isPlayingVideo, which is True prior to the video actually
        being played, so some method calls can throw exceptions until
        onPlayBackStarted is issued. Sigh

        Perhaps rely on onVidowWindowOpened/Closed, but that depends upon
        the actual dialog opening/closing. Not good
        '''
        local_class = AdvancedPlayer
        if timeout is None:
            timeout = 3600  # An hour, insane

        timeout = timeout * 1000  # Convert to ms

        # TODO: Add check for failures: onPlabackFailed/Ended/Error
        while not self._player_window_open and timeout > 0 and not Monitor.wait_for_abort(0.250):
            timeout -= 250

        if timeout <= 0:
            return False

        return True

    def wait_for_is_not_playing_video(self,
                                      timeout: float = None,
                                      trace: str = None) -> bool:
        '''
        This is a mess.

        The preferred way to deal with this is to monitor onPlayBackStarted/
        onPlayBackEnded events, but onPlayBackEnded is not reliably sent.
        So, poll isPlayingVideo, which is True prior to the video actually
        being played, so some method calls can throw exceptions until
        onPlayBackStarted is issued. Sigh

        Perhaps rely on onVidowWindowOpened/Closed, but that depends upon
        the actual dialog opening/closing. Not good
        '''

        local_class = AdvancedPlayer
        try:
            if timeout is None:
                timeout = 0
                if self._player_window_open:
                    timeout = self.getTime()
                    timeout = self.getTotalTime() - timeout + 2
        except Exception:
            # Player must be finished
            timeout = 0

        timeout = timeout * 1000  # Convert to ms
        while (self._player_window_open
               and timeout > 0 and not Monitor.wait_for_abort(0.250)):
            timeout -= 250

        if timeout > 0:
            return False
        return True

    # Defined in xbmc.Player
    def onAVChange(self) -> None:
        '''
            Will be called when Kodi has a video, audio or subtitle stream. Also
            happens when the stream changes.

            v18 Python API changes:
            New function added.
        '''
        local_class = AdvancedPlayer
        if (type(self).DEBUG_MONITOR and
                local_class._logger.isEnabledFor(LazyLogger.DEBUG)):
            local_class._logger.debug_extra_verbose(self.get_playing_title(), trace=Trace.TRACE)
        # self._dump_state()  # TODO: remove

        # self.displayInfo()

    # Defined in xbmc.Player
    def onPlayBackEnded(self)  -> None:
        '''
            Will be called when Kodi stops playing a file.
        '''
        self._player_state = PlayerState.STATE_STOPPED

        # self._dump_state()  # TODO: remove

    def on_playback_failed(self) -> None:
        self._player_state = PlayerState.STATE_STOPPED

        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackStopped(self) -> None:
        '''
        Will be called when user stops Kodi playing a file.
        '''
        self._player_state = PlayerState.STATE_STOPPED
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackError(self) -> None:
        '''
            Will be called when playback stops due to an error.
        '''
        self._player_state = PlayerState.STATE_STOPPED
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackPaused(self) -> None:
        '''
            Will be called when user pauses a playing file.
        '''

        local_class = AdvancedPlayer
        self._player_state = PlayerState.STATE_PAUSED
        if local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            local_class._logger.debug_extra_verbose(self.get_playing_title(),
                                                    trace=Trace.TRACE)
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackResumed(self) -> None:
        '''
            Will be called when user resumes a paused file.
        '''

        local_class = AdvancedPlayer
        if local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            local_class._logger.debug_extra_verbose(self.get_playing_title(),
                                                    trace=Trace.TRACE)
        self._player_state = PlayerState.STATE_PLAYING

    # Defined in xbmc.Player
    def onPlayBackSeek(self, time: int, seekOffset: int) -> None:
        '''
        Will be called when user seeks to a time.
        '''
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackSeekChapter(self, chapter: int) -> None:
        '''
        Will be called when user performs a chapter seek.
        '''

    # Defined in xmbc.Player
    def onPlayBackSpeedChanged(self, speed: int) -> None:
        '''
        Will be called when players speed changes (eg. user FF/RW).

        Note:  Negative speed means player is rewinding, 1 is normal playback speed.
        '''

    # Defined in xbmc.Player
    def onQueueNextItem(self) -> None:
        '''
        Will be called when user queues the next item.
        '''
        local_class = AdvancedPlayer
        if (type(self).DEBUG_MONITOR and
                local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
            local_class._logger.debug_extra_verbose(self.get_playing_title(),
                                                    trace=Trace.TRACE)
        # self._dump_state()  # TODO: remove

    def on_video_window_opened(self) -> None:
        """
            Event indicating that the Video Window has been opened.

            Note: This event is NOT sent if the Player is started in non-windowed
            mode.

        :return: None
        """
        # self._dump_state()  # TODO: remove
        self._player_window_open = True
        # self.getDialog().show()

    def on_video_window_closed(self) -> None:
        """
            Event indicating that the Video Window has been closed.

            Note: This event is NOT sent if the Player is started in non-windowed
            mode.
        :return: None
        """
        local_class = AdvancedPlayer
        if (type(self).DEBUG_MONITOR and
                local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)):
            local_class._logger.enter()
        self._player_window_open = False
        # self.hide_osd()
        # self._dump_state()  # TODO: remove

    def show_osd(self, from_seek=False) -> None:
        pass

    def hide_osd(self, delete=False) -> None:
        pass

    def on_video_osd(self) -> None:
        # self._dump_state()  # TODO: remove
        pass

    def on_show_info(self) -> None:
        # self._dump_state()  # TODO: remove

        if self._call_back_on_show_info is not None:
            self._call_back_on_show_info()

    def tick(self) -> None:
        pass

    def on_seek_osd(self) -> None:
        local_class = AdvancedPlayer
        if (type(self).DEBUG_MONITOR and
                local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
            local_class._logger.enter()
        # self._dump_state()  # TODO: remove

    def kill_playing_trailer(self) -> None:
        local_class = AdvancedPlayer
        if local_class._logger.isEnabledFor(DEBUG_PLAYER):
            local_class._logger.enter()

    def monitor(self) -> None:
        Monitor.throw_exception_if_abort_requested()
        if not self._monitor_thread or not self._monitor_thread.isAlive():
            if self._monitor_thread:
                self._monitor_thread.join()

            self._monitor_thread = threading.Thread(
                target=self._monitor, name='AdvancedPlayer:MONITOR')
            self._monitor_thread.start()

    def _monitor(self) -> None:
        local_class = AdvancedPlayer
        clz = type(self)
        try:
            if clz.DEBUG_MONITOR:
                local_class._logger.enter()

            while not Monitor.wait_for_abort(0.1) and not self._closed:
                if (clz.DEBUG_MONITOR and
                        local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
                    if not self.isPlaying():
                        local_class._logger.debug_extra_verbose('Player: Idling...')

                while not self.isPlaying() and not self._closed:
                    Monitor.throw_exception_if_abort_requested(timeout=0.1)

                if self.isPlayingVideo():
                    if (clz.DEBUG_MONITOR and
                            local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)):
                        local_class._logger.debug_verbose('Monitoring video...')
                    self._video_monitor()
                elif self.isPlayingAudio():
                    if (clz.DEBUG_MONITOR and
                            local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)):
                        local_class._logger.debug_verbose('Monitoring audio...')
                    # self._audio_monitor()
                elif self.isPlaying():
                    if (clz.DEBUG_MONITOR and
                            local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)):
                        local_class._logger.debug_verbose('Monitoring pre-play...')
                    self._preplay_monitor()

            if (clz.DEBUG_MONITOR and
                    local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)):
                local_class._logger.debug_verbose('Player: Closed')
        except AbortException:
            pass  # Just exit thread
        except Exception as e:
            local_class._logger.exception('')
        finally:
            pass

    def _preplay_monitor(self) -> None:
        local_class = AdvancedPlayer
        clz = type(self)
        try:
            if (clz.DEBUG_MONITOR and
                    local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)):
                local_class._logger.enter()
            self.on_preplay_started()
            while (self.isPlaying() and not self.isPlayingVideo()
                   and not self.isPlayingAudio()
                   and not self._closed):
                Monitor.throw_exception_if_abort_requested(timeout=0.1)

            if not self.isPlayingVideo() and not self.isPlayingAudio():
                self.on_playback_failed()

            if (clz.DEBUG_MONITOR and
                    local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)):
                local_class._logger.exit()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            local_class._logger.exception('')

    def _video_monitor(self) -> None:
        local_class = AdvancedPlayer
        clz = type(self)
        try:
            if (clz.DEBUG_MONITOR and
                    local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)):
                local_class._logger.enter()
            has_full_screened = False

            ct = 0
            while self.isPlayingVideo() and not self._closed:
                Monitor.throw_exception_if_abort_requested(timeout=0.1)
                if xbmc.getCondVisibility('Window.IsActive(videoosd)'):
                    if not self._has_osd:
                        self._has_osd = True
                        self.on_video_osd()
                else:
                    self._has_osd = False

                if self._closed:
                    break

                if xbmc.getCondVisibility('Player.ShowInfo'):
                    if not self._has_show_info:
                        self.on_show_info()
                        self._has_show_info = True
                else:
                    self._has_show_info = False

                if self._closed:
                    break

                if xbmc.getCondVisibility('Window.IsActive(seekbar)'):
                    if not self._has_seek_osd:
                        self._has_seek_osd = True
                        self.on_seek_osd()
                else:
                    self._has_seek_osd = False

                if self._closed:
                    break

                if xbmc.getCondVisibility('VideoPlayer.IsFullscreen'):
                    if not has_full_screened:
                        has_full_screened = True
                        self.on_video_window_opened()
                elif has_full_screened and not xbmc.getCondVisibility('Window.IsVisible(busydialog)'):
                    has_full_screened = False
                    self.on_video_window_closed()

                if self._closed:
                    break

            if has_full_screened:
                self.on_video_window_closed()

            if (clz.DEBUG_MONITOR and
                    local_class._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)):
                local_class._logger.exit()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            local_class._logger.exception('')

    """
    def _audio_monitor(self):
        local_class = AdvancedPlayer
        try:
            if (type(self).DEBUG_MONITOR and
                    local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
                local_class._logger.enter()
            ct = 0
            while self.isPlayingAudio() and not Monitor.is_abort_requested() and not self._closed:
                Monitor.wait_for_abort(0.1)

                ct += 1
                if ct > 9:
                    ct = 0
                    self.tick()

            if (type(self).DEBUG_MONITOR and
                    local_class._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
                local_class._logger.exit()
        except AbortException:
            raise AbortException
        except Exception as e:
            local_class._logger.exception('')
    """
