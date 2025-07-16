# -*- coding: utf-8 -*-
import datetime
import threading
from abc import ABC

import xbmc
import xbmcgui
from xbmc import PlayList, InfoTagVideo, InfoTagMusic, InfoTagRadioRDS

from common.imports import *
from common.logger import *
from common.monitor import Monitor
from player.abstract_player import AbstractPlayer
from .__init__ import *

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)
DEBUG_PLAYER: int = DEBUG

class AdvancedPlayer(xbmc.Player, AbstractPlayer, ABC):
    """

    """
    DEBUG_MONITOR: Final[bool] = True
    _logger: BasicLogger = None

    def __init__(self):
        super().__init__()

        if AdvancedPlayer._logger is None:
            AdvancedPlayer._logger = module_logger.getChild(type(self).__name__)

        self._is_playing: bool = False
        self._play_started: bool = False
        self._is_paused: bool = False

        # Last known playing file path.
        # Set by onAVStarted
        # Cleared by onPlayBackStopped, onPlayBackError
        self._playing_path: str = ''
        self._is_finished: bool = False
        self._monitor_thread: threading.Thread = None
        self._closed: bool = True
        self._has_osd: bool = False
        self._has_seek_osd: bool = False
        self._has_show_info: bool = False
        self._player_window_open: bool = False
        self._call_back_on_show_info: Callable[[Any], Any] = None
        self.started: bool = False

    def set_callbacks(self,
                      on_video_window_opened: Callable[[Any], Any] = None,
                      on_video_window_closed: Callable[[Any], Any] = None,
                      on_show_osd: Callable[[Any], Any] = None,
                      on_show_info: Callable[[Any], Any] = None) -> None:
        #  self._call_back_on_show_info = on_show_info
        pass

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
        clz = AdvancedPlayer
        if clz._logger.isEnabledFor(DEBUG):
            clz._logger.debug('reset')
        self.started = False

    '''
    def control(self, cmd: str) -> None:
        clz = AdvancedPlayer

        if cmd == 'play':
            if clz._logger.isEnabledFor(DEBUG_PLAYER):
                clz._logger.debug_extra_verbose('Command=Play')
            if xbmc.getCondVisibility('Player.Paused | !Player.Playing'):
                if clz._logger.isEnabledFor(DEBUG_PLAYER):
                    clz._logger.debug_extra_verbose('Playing')
                xbmc.executebuiltin('PlayerControl(Play)')
        elif cmd == 'pause':
            if clz._logger.isEnabledFor(DEBUG_PLAYER):
                clz._logger.debug_extra_verbose('Command=Pause')
            if not xbmc.getCondVisibility('Player.Paused'):
                if clz._logger.isEnabledFor(DEBUG_PLAYER):
                    clz._logger.debug_extra_verbose(' Pausing')
                xbmc.executebuiltin('PlayerControl(Play)')
    '''

    '''
    @property
    def play_state(self) -> str:
        clz = AdvancedPlayer

        return self.play_state

        
        if xbmc.getCondVisibility('Player.Playing'):
            play_state = PlayerState.STATE_PLAYING
        elif xbmc.getCondVisibility('Player.Paused'):
            play_state = PlayerState.STATE_PAUSED
        else:
            play_state = PlayerState.STATE_STOPPED
        if clz._logger.isEnabledFor(DEBUG_PLAYER):
            clz._logger.debug_extra_verbose('play_state: ' + play_state)
        # self._dump_state()  # TODO: remove
        return play_state
    '''

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
        clz = AdvancedPlayer

        Monitor.throw_exception_if_abort_requested()

        if type(self).DEBUG_MONITOR:
            clz._logger.debug('enter')
        super().play(item, listitem, windowed, startpos)
        self.enable_advanced_monitoring()
        self._play_started = True

    # Defined in xbmc.Player
    def stop(self) -> None:
        """
        Stop playing.
        """
        clz = AdvancedPlayer

        if (type(self).DEBUG_MONITOR and
                clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
            clz._logger.debug_extra_verbose('enter')
        self._is_playing = False
        self._play_started = False
        self._is_paused = False
        super().stop()

    # Defined in xbmc.Player
    def pause(self) -> None:
        """
        Toggle play/pause state
        Assumes this is just a pass-through to super.
        Does NOT update _is_paused state
        """

        clz = AdvancedPlayer

        if (type(self).DEBUG_MONITOR and
                clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
            clz._logger.debug_extra_verbose(f'is_playing: {self._is_playing} '
                                            f'is_paused: {self._is_paused}')
        super().pause()

    def pause_play(self) -> None:
        clz = AdvancedPlayer

        if (clz._logger.isEnabledFor(DEBUG_PLAYER)
                and clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
            clz._logger.debug_extra_verbose(f'is_playing: {self._is_playing} '
                                            f'is_paused: {self._is_paused}')
        if not self._is_playing:
            self._is_paused = False
            return

        if not self._is_paused:
            self.pause() # Toggle
            self._is_paused = True

    def resume_play(self) -> None:
        clz = AdvancedPlayer

        if (clz._logger.isEnabledFor(DEBUG_PLAYER)
                and clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
            clz._logger.debug_extra_verbose(f'is_playing: {self._is_playing} '
                                            f'is_paused: {self._is_paused}')
        if not self._is_playing:
            self._is_paused = False
            return

        if self._is_paused:
            self.pause() # Toggle
            self._is_paused = False

    # Defined in xbmc.Player
    def playnext(self) -> None:
        """
        Play next item in playlist.
        """
        clz = AdvancedPlayer

        if clz._logger.isEnabledFor(DEBUG_PLAYER):
            clz._logger.debug('enter')

        # Don't set playing state until we get onAVStarted
        # self._is_playing = True
        # self._paused = False
        super().playnext()

    # Defined in xbmc.Player
    def playprevious(self) -> None:
        """
        Play previous item in playlist.
        """
        clz = AdvancedPlayer

        if clz._logger.isEnabledFor(DEBUG_PLAYER):
            clz._logger.debug('enter')

        # Don't set playing state until we get onAVStarted
        # self._is_playing = True
        # self._is_paused = False
        super().playprevious()

    # Defined in xbmc.Player
    def playselected(self, selected: int) -> None:
        """
        Play a certain item from the current playlist.

        :param selected: Integer - Item to select
        """
        clz = AdvancedPlayer

        if clz._logger.isEnabledFor(DEBUG_PLAYER):
            clz._logger.debug('enter')

        # Don't set playing state until we get onAVStarted
        # self._is_playing = True
        # self._is_paused = False
        super().playselected(selected)

    # Defined in xbmc.Player
    def isPlaying(self) -> bool:
        """
        Is Kodi is playing something.

        :return: True if Kodi is playing a file.
        """
        clz = AdvancedPlayer

        is_playing = bool(super().isPlaying())
        return is_playing

    # Defined in xbmc.Player
    def isPlayingAudio(self) -> bool:
        """
        Is Kodi playing audio.

        :return: True if Kodi is playing an audio file.
        """
        clz = AdvancedPlayer

        playing_audio = bool(super().isPlayingAudio())
        # clz._logger.debug(str(playing_audio))
        return playing_audio

    # Defined in xbmc.Player
    def isPlayingVideo(self) -> bool:
        """
        Is Kodi playing video.

        :return: True if Kodi is playing a video.
        """
        clz = AdvancedPlayer

        # return xbmc.getCondVisibility('Player.Playing') and xbmc.getCondVisibility('Player.HasVideo')

        is_playing_video: bool = super().isPlayingVideo()
        if self._is_playing != is_playing_video:
            clz._logger.error(f'internal play state != xbmc play state')
            self._is_playing = is_playing_video

        #  Does not take pause into account!

        return self._is_playing

    # Defined in xbmc.Player
    def isPlayingRDS(self) -> bool:
        """
        Check for playing radio data system (RDS).

        :return: True if kodi is playing a radio data system (RDS).
        """
        clz = AdvancedPlayer

        playing_rds = bool(super().isPlayingRDS())
        return playing_rds

    def is_paused(self) -> bool:
        clz = AdvancedPlayer
        return self._is_paused

    '''
    def is_player_window_open(self) -> bool:
        return self._player_window_open
    '''

    # Defined in xbmc.Player
    def isExternalPlayer(self) -> bool:
        """
        Is Kodi using an external player.

        :return: True if kodi is playing using an external player.

        New function added.
        """
        clz = AdvancedPlayer
        external_player = bool(super().isExternalPlayer())
        return external_player

    def is_finished(self) -> bool:
        clz = AdvancedPlayer
        if clz._logger.isEnabledFor(DEBUG_PLAYER):
            clz._logger.debug_extra_verbose('value:', self._is_finished)
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
        clz = AdvancedPlayer
        playing_file = ''
        try:
            # Exception thrown if Kodi has not played any file

            playing_file = super().getPlayingFile()
            self._is_playing = True

            if clz._logger.isEnabledFor(DISABLED):
                clz._logger.debug_extra_verbose('playing_file: ' + playing_file)
        except Exception as e:
            # clz._logger.exception(msg='')
            self._is_playing = False
        finally:
            return playing_file

    def _dump_state(self) -> None:
        clz = AdvancedPlayer
        if clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            self.is_video_fullscreen()
            self.isPlaying()
            self.isPlayingAudio()
            self.isPlayingVideo()
            self.isPlayingRDS()
            self.isExternalPlayer()
            self.is_finished()
            clz._logger.debug_extra_verbose(f'is_paused: {self._is_paused} '
                                            f'is_playing: {self._is_playing}')

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
        clz = AdvancedPlayer
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
        clz = AdvancedPlayer
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
        clz = AdvancedPlayer
        return super().setSubtitles(subtitle_file)

    # Defined in xbmc.Player
    def showSubtitles(self, b_visible: bool) -> None:
        """
        Enable / disable subtitles.

        :param b_visible: [boolean] True for visible subtitles.

        Example::

            xbmc.Player().showSubtitles(True)
        """
        clz = AdvancedPlayer
        return super().showSubtitles(b_visible)

    # Defined in xbmc.Player
    def getSubtitles(self) -> str:
        """
        Get subtitle stream name.

        :return: Stream name
        """
        clz = AdvancedPlayer
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
        clz = AdvancedPlayer
        title = None
        #try:
        #    playing_file = super().getPlayingFile()
        #except Exception as e:
        #    playing_file = 'unknown'
        try:
            info_tag = self.getVideoInfoTag()
            title = info_tag.getTitle()
        except Exception as e:
            clz._logger.exception(msg='')
            title = "Exception- Nothing Playing?"
            self._is_finished = True

        return title

    def is_playing_file(self, file_path) -> bool:
        """
        :param file_path: Path of the file to verify is playing (may be paused)
        :returns: True if playing (may be paused) the current file
                  else False
        """
        clz = AdvancedPlayer
        playing_the_file: bool = False
        playing_path: str = ''
        try:
            # getPlayingFile throws exception when not playing a file

            playing_path: str = self.getPlayingFile()
            playing_the_file = playing_path == file_path
        except Exception:
            playing_the_file = False
            # clz._logger.debug(f'given path: {file_path}')

        clz._logger.debug(f'paths_same: {playing_the_file} given path: {file_path} '
                          f'playing_path: {playing_path}')
        return playing_the_file

    def kill_player(self) -> None:
        clz = AdvancedPlayer
        if clz._logger.isEnabledFor(DEBUG_PLAYER):
            clz._logger.debug('enter')
        if not self._is_finished:
            xbmc.executebuiltin('PlayerControl(Stop)')

        self._is_playing = False
        self._is_paused = False
        self._is_finished = True
        self._play_started = False
    '''
    def on_preplay_started(self) -> None:
        pass
    '''

    '''
    # Defined in xbmc.Player
    def onPlayBackStarted(self):
        """
        onPlayBackStarted method.

        Will be called when Kodi player starts. Video or audio might not be available at
        this point.

        v18 Python API changes:
        Use onAVStarted() instead if you need to detect if Kodi is actually playing
        a media file (i.e, if a stream is available)
        """

        if clz._logger.isEnabledFor(DEBUG_VERBOSE):
            clz._logger.debug_verbose('You probably want to use onAVStarted instead')
        # self._dump_state()  # TODO: remove

    '''

    # Defined in xbmc.Player
    def onAVStarted(self) -> None:
        """
        Will be called when Kodi has a video or audiostream.

        v18 Python API changes:
            New function added.
        """
        clz = AdvancedPlayer
        if clz._logger.isEnabledFor(DEBUG_VERBOSE):
            try:
                clz._logger.debug_verbose(
                    f'{self.get_playing_title()} path: {self.getPlayingFile()}',
                    trace=Trace.TRACE)
            except RuntimeError:
                clz._logger.debug_verbose('Movie info not yet available')

        self._is_playing = True
        self._is_paused = False
        self._play_started = True
        self._playing_path = self.getPlayingFile()

        # self._dump_state()  # TODO: remove

    def wait_for_is_playing_video(self, path:str = None,
                                  timeout: float = None) -> bool:
        """
            Waits until a video is playing (or paused).

        :param: timeout: Maximum amount of time to wait, in seconds.
                Defaults to an hour if None or <= 0
        :return: True if playing a video
                 False if no video was played within timeout seconds

        """
        '''
              This is a mess.

              The preferred way to deal with this is to monitor onPlayBackStarted/
              onPlayBackEnded events, but onPlayBackEnded is not reliably sent.
              So, poll isPlayingVideo, which is True prior to the video actually
              being played, so some method calls can throw exceptions until
              onPlayBackStarted is issued. Sigh

              Perhaps rely on onVidowWindowOpened/Closed, but that depends upon
              the actual dialog opening/closing. Not good

              :param: timeout: Maximum amount of time to wait, in seconds
              '''
        clz = AdvancedPlayer
        if timeout is None or timeout <= 0.0:
            timeout = 3600.0  # An hour, insane

        timeout_ms: int = int(timeout * 1000.0)

        # TODO: Add check for failures: onPlabackFailed/Ended/Error
        while not Monitor.wait_for_abort(0.250):
            playing_path = self.getPlayingFile()
            if clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(f'is_playing: {path} '
                                                f'playing path: '
                                                f'{playing_path} '
                                                f'paused: {self._is_paused} '
                                                f'playing: '
                                                f'{self._is_playing} '
                                                f'play_started: '
                                                f'{self._play_started}')
            if playing_path == path:
                break

            # if self.getPlayingFile() == path and self._is_playing:
                # Success!
            #     break
            # If no attempt has been made to even start playing, we may as well
            # give up.

            if not self._play_started:
                return False

            timeout_ms -= 250

        '''
        while (not Monitor.wait_for_abort(0.250)
               and not self._player_window_open
               and timeout_ms > 0):
            if self.is_paused():
                break
            timeout_ms -= 250

        if timeout_ms <= 0:
            return False
        '''

        if timeout_ms <= 0:
            return False
        return True

    def wait_for_is_not_playing_video(self,
                                      path: str = None,
                                      timeout: float = None,
                                      trace: str = None) -> bool:
        """
          Waits until a video is NOT playing (or paused).

          :param: path: Wait until the given video path is no longer playing.
          :param: timeout: Maximum amount of time to wait, in seconds.
                  Defaults to an hour if None or <= 0
          :return: True if video is not playing (or paused)
                   False if a video was playing (or paused) for
                   entire timeout period of seconds

        """
        #  This is a mess. See wait_for_is_playing_video

        clz = AdvancedPlayer
        if path is None:
            path = ''

        if timeout is None or timeout <= 0:
            timeout = 3600.0

        timeout_ms: int = int(timeout * 1000.0)
        while not Monitor.wait_for_abort(0.250) and timeout_ms > 0:
            playing_path = self.getPlayingFile()
            # We are finished when not playing anything or when not playing
            # the given path
            if playing_path == '' or (path != playing_path):
                break
            timeout_ms -= 250

        if timeout_ms > 0:
            return True

        return False

    # Defined in xbmc.Player
    def onAVChange(self) -> None:
        """
            Will be called when Kodi has a video, audio or subtitle stream. Also
            happens when the stream changes.

            v18 Python API changes:
            New function added.
        """
        clz = AdvancedPlayer
        try:
            if clz._logger.isEnabledFor(DISABLED):
                clz._logger.debug(f'onAVChange path: {self.getPlayingFile()}')
        except Exception:
            clz._logger.exception(msg='')

        if clz._logger.isEnabledFor(DISABLED):
            if (type(self).DEBUG_MONITOR and
                    clz._logger.isEnabledFor(DEBUG)):
                clz._logger.debug_extra_verbose(f'{self.get_playing_title()} '
                                                f'playing: {self._is_playing} '
                                                f'paused: {self._is_paused} '
                                                f'play_started: '
                                                f'{self._play_started}',
                                                trace=Trace.TRACE)

    # Defined in xbmc.Player
    def onPlayBackEnded(self)  -> None:
        """
            Will be called when Kodi stops playing a file.
        """
        clz = AdvancedPlayer
        self._is_playing = False
        self._is_paused = False
        self._play_started = False
        self._playing_path = ''

        try:
            clz._logger.debug(f'onPlayBackEnded path: {self.getPlayingFile()}')
        except Exception:
            clz._logger.exception(msg='')


    # Defined in xbmc.Player
    def onPlayBackStopped(self) -> None:
        """
        Will be called when user stops Kodi playing a file.
        """
        clz = AdvancedPlayer
        self._is_playing = False
        self._is_paused = False
        self._play_started = False
        self._playing_path = ''
        # self._dump_state()  # TODO: remove
        try:
            clz._logger.debug(f'onPlayBackStopped path: {self.getPlayingFile()}')
        except Exception:
            clz._logger.exception(msg='')

    # Defined in xbmc.Player
    def onPlayBackError(self) -> None:
        """
            Will be called when playback stops due to an error.
        """
        clz = AdvancedPlayer
        self._is_playing = False
        self._is_paused = False
        self._play_started = False
        self._playing_path = ''
        try:
            clz._logger.debug(f'onPlayBackError path: {self.getPlayingFile()}')
        except Exception:
            clz._logger.exception(msg='')

    # Defined in xbmc.Player
    def onPlayBackPaused(self) -> None:
        """
            Will be called when user pauses a playing file.
        """

        clz = AdvancedPlayer
        self._is_paused = True
        if not self._is_playing:
            clz._logger.error(f'Paused and not Playing!')

        try:
            if clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(self.getPlayingFile(),
                                                trace=Trace.TRACE)
        except Exception:
            clz._logger.exception(msg='')

        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackResumed(self) -> None:
        """
            Will be called when user resumes a paused file.
        """

        clz = AdvancedPlayer
        if clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose(self.get_playing_title(),
                                            trace=Trace.TRACE)
        self._is_paused = False
        if not self._is_playing:
            clz._logger.error(f'Not Paused and not Playing!')

        try:
            clz._logger.debug(f'onPlayBackResumed path: {self.getPlayingFile()}')
        except Exception:
            clz._logger.exception(msg='')

    # Defined in xbmc.Player
    def onPlayBackSeek(self, time: int, seekOffset: int) -> None:
        """
        Will be called when user seeks to a time.
        """

    # Defined in xbmc.Player
    def onPlayBackSeekChapter(self, chapter: int) -> None:
        """
        Will be called when user performs a chapter seek.
        """

    # Defined in xmbc.Player
    def onPlayBackSpeedChanged(self, speed: int) -> None:
        """
        Will be called when players speed changes (eg. user FF/RW).

        Note:  Negative speed means player is rewinding, 1 is normal playback speed.
        """

    # Defined in xbmc.Player
    def onQueueNextItem(self) -> None:
        """
        Will be called when user queues the next item.
        """
        clz = AdvancedPlayer
        if (type(self).DEBUG_MONITOR and
                clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
            clz._logger.debug_extra_verbose(self.get_playing_title(),
                                            trace=Trace.TRACE)

    '''
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
        clz = AdvancedPlayer
        if (type(self).DEBUG_MONITOR and
                clz._logger.isEnabledFor(DEBUG_VERBOSE)):
            clz._logger.debug('enter')
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
        clz = AdvancedPlayer
        if (type(self).DEBUG_MONITOR and
                clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
            clz._logger.debug('enter')
        # self._dump_state()  # TODO: remove

    def kill_playing_trailer(self) -> None:
        clz = AdvancedPlayer
        if clz._logger.isEnabledFor(DEBUG_PLAYER):
            clz._logger.debug('enter')

    def monitor(self) -> None:
        Monitor.throw_exception_if_abort_requested()
        if not self._monitor_thread or not self._monitor_thread.isAlive():
            if self._monitor_thread:
                self._monitor_thread.join()

            self._monitor_thread = threading.Thread(
                target=self._monitor, name='AdvancedPlayer:MONITOR')
            self._monitor_thread.start()

    def _monitor(self) -> None:
        clz = AdvancedPlayer
        clz = AdvancedPlayer
        try:
            if clz.DEBUG_MONITOR:
                clz._logger.debug('enter')

            while not Monitor.wait_for_abort(0.1) and not self._closed:
                if (clz.DEBUG_MONITOR and
                        clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
                    if not self.isPlaying():
                        clz._logger.debug_extra_verbose('Player: Idling...')

                while not self.isPlaying() and not self._closed:
                    Monitor.throw_exception_if_abort_requested(timeout=0.1)

                if self.isPlayingVideo():
                    if (clz.DEBUG_MONITOR and
                            clz._logger.isEnabledFor(DEBUG_VERBOSE)):
                        clz._logger.debug_verbose('Monitoring video...')
                    self._video_monitor()
                elif self.isPlayingAudio():
                    if (clz.DEBUG_MONITOR and
                            clz._logger.isEnabledFor(DEBUG_VERBOSE)):
                        clz._logger.debug_verbose('Monitoring audio...')
                    # self._audio_monitor()
                elif self.isPlaying():
                    if (clz.DEBUG_MONITOR and
                            clz._logger.isEnabledFor(DEBUG_VERBOSE)):
                        clz._logger.debug_verbose('Monitoring pre-play...')
                    self._preplay_monitor()

            if (clz.DEBUG_MONITOR and
                    clz._logger.isEnabledFor(DEBUG_VERBOSE)):
                clz._logger.debug_verbose('Player: Closed')
        except AbortException:
            pass  # Just exit thread
        except Exception as e:
            clz._logger.exception('')
        finally:
            pass

    def _preplay_monitor(self) -> None:
        clz = AdvancedPlayer
        clz = AdvancedPlayer
        try:
            if (clz.DEBUG_MONITOR and
                    clz._logger.isEnabledFor(DEBUG_VERBOSE)):
                clz._logger.debug('enter')
            self.on_preplay_started()
            while (self.isPlaying() and not self.isPlayingVideo()
                   and not self.isPlayingAudio()
                   and not self._closed):
                Monitor.throw_exception_if_abort_requested(timeout=0.1)

            if not self.isPlayingVideo() and not self.isPlayingAudio():
                self.on_playback_failed()

            if (clz.DEBUG_MONITOR and
                    clz._logger.isEnabledFor(DEBUG_VERBOSE)):
                clz._logger.debug()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception('')

    def _video_monitor(self) -> None:
        clz = AdvancedPlayer
        clz = AdvancedPlayer
        try:
            if (clz.DEBUG_MONITOR and
                    clz._logger.isEnabledFor(DEBUG_VERBOSE)):
                clz._logger.debug('enter')
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
                    clz._logger.isEnabledFor(DEBUG_VERBOSE)):
                clz._logger.debug()
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception('')

    """
    def _audio_monitor(self):
        clz = AdvancedPlayer
        try:
            if (type(self).DEBUG_MONITOR and
                    clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
                clz._logger.debug('enter')
            ct = 0
            while (self.isPlayingAudio() and not Monitor.is_abort_requested() 
                   and not self._closed):
                Monitor.wait_for_abort(0.1)

                ct += 1
                if ct > 9:
                    ct = 0
                    self.tick()

            if (type(self).DEBUG_MONITOR and
                    clz._logger.isEnabledFor(DEBUG_EXTRA_VERBOSE)):
                clz._logger.debug()
        except AbortException:
            raise AbortException
        except Exception as e:
            clz._logger.exception('')
    """
    '''
