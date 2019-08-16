# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

from kodi_six import xbmc

from common.constants import (Constants)
from common.exceptions import AbortException, ShutdownException
from common.logger import (Logger, LazyLogger, Trace)
from common.monitor import Monitor
import sys
import threading

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild('player.advanced_player')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class PlayerState(object):
    STATE_STOPPED = 'stopped'
    STATE_PLAYING = 'playing'
    STATE_PAUSED = 'paused'


# noinspection Annotator,Annotator
class AdvancedPlayer(xbmc.Player):
    """

    """

    def __init__(self):
        self._is_playing = False
        self._is_finished = False
        self._kill_trailer_timer = None
        self._previous_info_tag = None
        self._info_dialog_initialized = False
        self._logger = module_logger.getChild(self.__class__.__name__)
        self._monitor_thread = None
        self._closed = True
        self._has_osd = False
        self._has_seek_osd = False
        self._has_show_info = False
        self._player_window_open = False
        self._call_back_on_show_info = None
        self._player_state = PlayerState.STATE_STOPPED
        self.video = None
        self.started = False
        self.player_object = None

    def setCallBacks(self, on_video_window_opened=None, on_video_window_closed=None,
                     on_show_osd=None, on_show_info=None):
        self._call_back_on_show_info = on_show_info

    def enableAdvancedMonitoring(self):
        self._logger.enter()
        self._closed = False
        self.monitor()

    def disableAdvancedMonitoring(self, shutdown=False):
        self._closed = True
        try:
            if self._monitor_thread is not None and self._monitor_thread.isAlive():
                self._monitor_thread.join(0.1)
        finally:
            self._monitor_thread = None

    def reset(self):
        self._logger.enter()
        self.video = None
        self.started = False
        self.player_object = None
        self.current_time = 0

    def control(self, cmd):
        if cmd == 'play':
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Command=Play')
            if xbmc.getCondVisibility('Player.Paused | !Player.Playing'):
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug('Playing')
                xbmc.executebuiltin('PlayerControl(Play)')
        elif cmd == 'pause':
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Command=Pause')
            if not xbmc.getCondVisibility('Player.Paused'):
                if self._logger.isEnabledFor(Logger.DEBUG):
                    self._logger.debug(' Pausing')
                xbmc.executebuiltin('PlayerControl(Play)')

    @property
    def play_state(self):
        self._logger.enter()
        if xbmc.getCondVisibility('Player.Playing'):
            play_state = PlayerState.STATE_PLAYING
        elif xbmc.getCondVisibility('Player.Paused'):
            play_state = PlayerState.STATE_PAUSED
        else:
            play_state = PlayerState.STATE_STOPPED
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('play_state: ' + play_state)
        # self._dump_state()  # TODO: remove
        return play_state

    def isVideoFullscreen(self):

        isFullScreen = bool(xbmc.getCondVisibility('VideoPlayer.IsFullscreen'))
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('isFullScreen', isFullScreen)
        return isFullScreen

    '''
    def currentTrack(self):
        if self.handler.media and self.handler.media.type == 'track':
            return self.handler.media
        return None
    '''

    # Defined in xbmc.Player
    def play(self, item="", listitem=None, windowed=False, startpos=-1):
        # type: (Union[str_type, PlayList], 'xbmcgui.ListItem', bool, int) ->None
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

        Monitor.get_instance().throw_exception_if_shutdown_requested()

        self._logger.enter()
        super().play(item, listitem, windowed, startpos)
        self.enableAdvancedMonitoring()
        # self._dump_state()  # TODO: remove
        self._logger.exit()

    # Defined in xbmc.Player
    def stop(self):
        """
        Stop playing.
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter()
        super().stop()
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def pause(self):
        """
        Toggle play/pause state
        """

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter()
        super().pause()
        self._dump_state()  # TODO: remove

    def pausePlay(self):
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter()
        if self.play_state == PlayerState.STATE_PLAYING:
            self._dump_state()  # TODO: remove
            self.pause()

    def resumePlay(self):
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter()
        if self.play_state == PlayerState.STATE_PAUSED:
            self._dump_state()  # TODO: remove
            self.pause()

    # Defined in xbmc.Player
    def playnext(self):
        """
        Play next item in playlist.
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter()
        super().playnext()
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def playprevious(self):
        """
        Play previous item in playlist.
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter()
        super().playprevious()
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def playselected(self, selected):
        # type: (int) -> None
        """
        Play a certain item from the current playlist.

        :param selected: Integer - Item to select
        """
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter()
        super().playselected(selected)
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def isPlaying(self):
        """
        Is Kodi is playing something.

        :return: True if Kodi is playing a file.
        """
        self._is_playing = bool(super().isPlaying())
        #   if self._logger.isEnabledFor(Logger.DEBUG):
        #       self._logger.debug(':', self._is_playing)

        return self._is_playing

    def myIsPlayingVideo(self):
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter()

            self._logger.debug('isPlayingVideo:',
                                self.isPlayingVideo())
            """
            Returns True if the player is playing video.
            """

            self._logger.debug("Player.Playing: " +
                              str(bool(xbmc.getCondVisibility('Player.Playing'))))
            self._logger.debug('Player.HasVideo: ' +
                              str(bool(xbmc.getCondVisibility('Player.HasVideo'))))
        is_playing = bool(xbmc.getCondVisibility('Player.Playing')
                         and xbmc.getCondVisibility('Player.HasVideo'))
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug('is really playing:', is_playing)
        return is_playing

    # Defined in xbmc.Player
    def isPlayingAudio(self):
        """
        Is Kodi playing audio.

        :return: True if Kodi is playing an audio file.
        """
        playing_audio = bool(super().isPlayingAudio())
        # self._logger.debug(str(playing_audio))
        return playing_audio

    # Defined in xbmc.Player
    def isPlayingVideo(self):
        """
        Is Kodi playing video.

        :return: True if Kodi is playing a video.
        """
        isPlaying = bool(super().isPlayingVideo())
        #self._logger.debug(': ' + str(isPlaying))

        return isPlaying

    # Defined in xbmc.Player
    def isPlayingRDS(self):
        """
        Check for playing radio data system (RDS).

        :return: True if kodi is playing a radio data system (RDS).
        """
        playing_rds = bool(super().isPlayingRDS())
        # self._logger.debug(str(playing_rds))
        return playing_rds

    def isPaused(self):
        paused = False
        if self._player_state == PlayerState.STATE_PAUSED:
            paused = True
        return True

    # Defined in xbmc.Player
    def isExternalPlayer(self):
        """
        Is Kodi using an external player.

        :return: True if kodi is playing using an external player.

        New function added.
        """
        external_player = bool(super().isExternalPlayer())
        # self._logger.debug(str(external_player))
        return external_player

    def isFinished(self):
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter()
            self._logger.debug('value:', self._is_finished)
        return self._is_finished

    # Defined in xbmc.Player
    def getPlayingFile(self):
        """
        Returns the current playing file as a string.

        For LiveTV, returns a ``pvr://`` url which is not translatable to
        an OS specific file or external url.

        :return: Playing filename
        :raises Exception: If player is not playing a file.
        """
        playing_file = ''
        try:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.enter()

            playing_file = super().getPlayingFile()

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('playing_file: ' + playing_file)
        except (Exception) as e:
            pass
        finally:
            return playing_file

    def _dump_state(self):
        if self._logger.isEnabledFor(Logger.DEBUG):
            self.isVideoFullscreen()
            self.isPlaying()
            self.isPlayingAudio()
            self.isPlayingVideo()
            self.isPlayingRDS()
            self.isExternalPlayer()
            self.isFinished()
            self._logger.debug('play_state: ', self._player_state)

            # self.getPlayingFile()
            # self.getTime()
            # self.getSubtitles()
            # self.getAvailableSubtitleStreams()
            # self.getVideoInfoTag()
            # self.getMusicInfoTag()
            # self.getRadioRDSInfoTag()
            # self.getTotalTime()
            # self.getAvailableAudioStreams()
            # self.getPlayingTitle()

    # Defined in xbmc.Player
    def getTime(self):
        """
        Get playing time.

        Returns the current time of the current playing media as fractional seconds.

        :return: Current time as fractional seconds
        :raises Exception: If player is not playing a file.
        """
        time = 0
        try:
            # self._logger.enter()
            time = super().getTime()
            #self._logger.debug('time: ' + str(time))
        except (Exception):
            pass

        return time

    # Defined in xbmc.Player
    def seekTime(self, seek_time):
        """
        Seek time.

        Seeks the specified amount of time as fractional seconds. The time
        specified is relative to the beginning of the currently
        playing media file.

        :param seek_time: Time to seek as fractional seconds
        :raises Exception: If player is not playing a file.
        """
        seek_time = 0
        try:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.enter()

            seek_time = super().seekTime(seek_time)

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('seek_time: ' + str(seek_time))
        except (Exception):
            pass
        finally:
            return seek_time

    # Defined in xbmc.Player
    def setSubtitles(self, subtitle_file):
        """
        Set subtitle file and enable subtitles.

        :param subtitle_file: File to use as source of subtitles
        """
        return super().setSubtitles(subtitle_file)

    # Defined in xbmc.Player
    def showSubtitles(self, b_visible):
        # type: (bool) -> None
        """
        Enable / disable subtitles.

        :param b_visible: [boolean] True for visible subtitles.

        Example::

            xbmc.Player().showSubtitles(True)
        """
        return super().showSubtitles(b_visible)

    # Defined in xbmc.Player
    def getSubtitles(self):
        # type: () -> str
        """
        Get subtitle stream name.

        :return: Stream name
        """
        return super().getSubtitles()

    # Defined in xbmc.Player
    def getAvailableSubtitleStreams(self):
        # type: () -> List[str]
        """
        Get Subtitle stream names.

        :return: List of subtitle streams as name
        """
        return super().getAvailableSubtitleStreams()

    # Defined in xbmc.Player
    def setSubtitleStream(self, i_stream):
        # type: (int) -> None
        """
        Set Subtitle Stream.

        :param i_stream: [int] Subtitle stream to select for play

        Example::

            xbmc.Player().setSubtitleStream(1)
        """
        return super().setSubtitleStream(i_stream)

    # Defined in xbmc.Player
    def updateInfoTag(self, item):
        # type: ('xbmcgui.ListItem') -> None
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
    def getVideoInfoTag(self):
        # type: () -> InfoTagVideo
        """
        To get video info tag.

        Returns the VideoInfoTag of the current playing Movie.

        :return: Video info tag
        :raises Exception: If player is not playing a file or current file
            is not a movie file.
        """
        return super().getVideoInfoTag()

    # Defined in xbmc.Player
    def getMusicInfoTag(self):
        # type: () -> InfoTagMusic
        """
        To get music info tag.

        Returns the MusicInfoTag of the current playing 'Song'.

        :return: Music info tag
        :raises Exception: If player is not playing a file or current file
            is not a music file.
        """
        return super().getMusicInfoTag()

    # Defined in xbmc.Player
    def getRadioRDSInfoTag(self):
        # type: () -> Union[InfoTagRadioRDS, None]
        """
        To get Radio RDS info tag

        Returns the RadioRDSInfoTag of the current playing 'Radio Song if. present'.

        :return: Radio RDS info tag
        :raises Exception: If player is not playing a file or current file
            is not a rds file.
        """
        try:
            return super().getRadioRDSInfoTag()
        except (Exception):
            return None

    # Defined in xbmc.Player
    def getTotalTime(self):
        # type: () -> float
        """
        To get total playing time.

        Returns the total time of the current playing media in seconds.
        This is only accurate to the full second.

        :return: Total time of the current playing media
        :raises Exception: If player is not playing a file.
        """
        try:
            return super().getTotalTime()
        except (Exception):
            return 0

    # Defined in xbmc.Player
    def getAvailableAudioStreams(self):
        # type: () -> List[str]
        """
        Get Audio stream names

        :return: List of audio streams as name
        """
        return super().getAvailableAudioStreams()

    # Defined in xbmc.Player
    def setAudioStream(self, i_stream):
        # type: (int) -> None
        """
        Set Audio Stream.

        :param i_stream: [int] Audio stream to select for play

        Example::

            xbmc.Player().setAudioStream(1)
        """
        return super().setAudioStream(i_stream)

    # Defined in xbmc.Player
    def getAvailableVideoStreams(self):
        # type: () -> List[str]
        """
        Get Video stream names

        :return: List of video streams as name
        """
        return super().getAvailableVideoStreams()

    # Defined in xbmc.Player
    def setVideoStream(self, i_stream):
        # type: (int) -> None
        """
        Set Video Stream.

        :param i_stream: [int] Video stream to select for play

        Example::

            xbmc.Player().setVideoStream(1)
        """
        return super().setVideoStream(i_stream)

    def getPlayingTitle(self):
        # type: () -> TextType
        title = None
        try:
            playing_file = super().getPlayingFile()
        except (Exception) as e:
            playing_file = 'unknown'
        try:
            info_tag = self.getVideoInfoTag()
            title = info_tag.getTitle()
        except (Exception) as e:
            title = "Exception- Nothing Playing?"

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('title:', title, 'file:', playing_file)

        except (Exception) as e:
            self._logger.exception('')
            self._is_finished = True

        return title

    def killPlayer(self):
        self._logger.enter()
        if not self._is_finished:
            xbmc.executebuiltin('xbmc.PlayerControl(Stop)')

        self._is_finished = True

    def onPrePlayStarted(self):
        if self._logger.isEnabledFor(Logger.DEBUG_EXTRA_VERBOSE):
            self._logger.enter()
        # self._dump_state()  # TODO: remove

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

        if self._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
            self._logger.debug_verbose('You probably want to use onAVStarted instead')
        # self._dump_state()  # TODO: remove

    """

    # Defined in xbmc.Player
    def onAVStarted(self):

        '''
        Will be called when Kodi has a video or audiostream.

        v18 Python API changes:
            New function added.
        '''
        if self._logger.isEnabledFor(Logger.DEBUG_VERBOSE):
            self._logger.debug_verbose(self.getPlayingTitle(), trace=Trace.TRACE)

        # self._dump_state()  # TODO: remove
        '''
        infoTag = self.getVideoInfoTag()
        newMovieStarted = False
        if (infoTag != self._previous_info_tag):
            self._previous_info_tag = infoTag
            newMovieStarted = True

        xbmc.log("AdvancedPlayer.onAVStarted-Video: " + str(bool(self.isPlayingVideo())) +
                 " New Movie: " + str(newMovieStarted) + " " + self.getPlayingTitle(), xbmc.LOGNOTICE)
        if (newMovieStarted):
            if (self._kill_trailer_timer != None):
                self._kill_trailer_timer.cancel()
                del self._kill_trailer_timer
                self._kill_trailer_timer = None

            previewTime = getPreviewTime
            if (previewTime() > 0):
                self._kill_trailer_timer = threading.Timer(
                    previewTime(), self.kill_playing_trailer)
                self._kill_trailer_timer.start()
                xbmc.log("Started timer", xbmc.LOGNOTICE)
            else:
                self._kill_trailer_timer = None

            self.displayInfo()
        '''

    def waitForIsPlayingVideo(self, timeout=None):
        # type: (Optional[float) -> bool
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
        self._logger.enter()
        if timeout is None:
            timeout = 3600  # An hour, insane

        timeout = timeout * 1000  # Convert to ms
        kodi_monitor = Monitor.get_instance()

        # TODO: Add check for failures: onPlabackFailed/Ended/Error
        while not self._player_window_open and timeout > 0 and not kodi_monitor.wait_for_shutdown(0.250):
            timeout -= 250

        if timeout <= 0:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Timed out waiting')
            return False

        self._logger.exit()
        return True

    def wait_for_is_not_playing_video(self, timeout=None, trace=None):
        # type: (float, TextType) -> Union[bool, None]
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
        self._logger.enter(trace=trace)

        try:
            if timeout is None:
                timeout = 0
                if self._player_window_open:
                    timeout = self.getTime()
                    timeout = self.getTotalTime() - timeout + 2
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Setting timeout to:', timeout)
        except:
            # Player must be finished

            timeout = 0

        timeout = timeout * 1000  # Convert to ms
        kodi_monitor = Monitor.get_instance()
        while self._player_window_open and timeout > 0 and not kodi_monitor.wait_for_shutdown(0.250):
            timeout -= 250

        if timeout > 0:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Timed out waiting')
            return False

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.exit()
        return True

    # Defined in xbmc.Player
    def onAVChange(self):
        '''
            Will be called when Kodi has a video, audio or subtitle stream. Also
            happens when the stream changes.

            v18 Python API changes:
            New function added.
        '''
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(self.getPlayingTitle(), trace=Trace.TRACE)
        # self._dump_state()  # TODO: remove

        # self.displayInfo()

    # Defined in xbmc.Player
    def onPlayBackEnded(self):
        '''
            Will be called when Kodi stops playing a file.
        '''
        self._player_state = PlayerState.STATE_STOPPED

        # self._dump_state()  # TODO: remove

    def onPlayBackFailed(self):
        self._player_state = PlayerState.STATE_STOPPED

        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackStopped(self):
        '''
        Will be called when user stops Kodi playing a file.
        '''
        self._player_state = PlayerState.STATE_STOPPED
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackError(self):
        '''
            Will be called when playback stops due to an error.
        '''
        self._player_state = PlayerState.STATE_STOPPED
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Playser
    def onPlayBackPaused(self):
        '''
            Will be called when user pauses a playing file.
        '''

        self._player_state = PlayerState.STATE_PAUSED
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(self.getPlayingTitle(), trace=Trace.TRACE)
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Playser
    def onPlayBackResumed(self):
        '''
            Will be called when user resumes a paused file.
        '''

        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(self.getPlayingTitle(), trace=Trace.TRACE)
        self._player_state = PlayerState.STATE_PLAYING

        # self._dump_state()  # TODO: remove

        # self.displayInfo()

    # Defined in xbmc.Player
    def onPlayBackSeek(self, time, seekOffset):
        '''
        Will be called when user seeks to a time.
        '''
        # self._dump_state()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackSeekChapter(self, chapter):
        '''
        Will be called when user performs a chapter seek.
        '''

    # Defined in xmbc.Player
    def onPlayBackSpeedChanged(self, speed):
        '''
        Will be called when players speed changes (eg. user FF/RW).

        Note:  Negative speed means player is rewinding, 1 is normal playback speed.
        '''

    # Defined in xbmc.Player
    def onQueueNextItem(self):
        '''
        Will be called when user queues the next item.
        '''
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.debug(self.getPlayingTitle(), trace=Trace.TRACE)
        # self._dump_state()  # TODO: remove

    def onVideoWindowOpened(self):
        # type: () -> None
        """
            Event indicating that the Video Window has been opened.

            Note: This event is NOT sent if the Player is started in non-windowed
            mode.

        :return: None
        """
        # self._dump_state()  # TODO: remove
        self._player_window_open = True
        # self.getDialog().show()

    def onVideoWindowClosed(self):
        # type: () ->None
        """
            Event indicating that the Video Window has been closed.

            Note: This event is NOT sent if the Player is started in non-windowed
            mode.
        :return: None
        """
        self._logger.enter()
        self._player_window_open = False
        self.hideOSD()
        # self._dump_state()  # TODO: remove

    def showOSD(self, from_seek=False):
        self._logger.enter()
        # self._dump_state()  # TODO: remove

        # if self.dialog:
        #    self.updateOffset()
        #    self.dialog.update(self.offset, from_seek)
        #    self.dialog.showOSD()

    def hideOSD(self, delete=False):
        self._logger.enter()
        # self._dump_state()  # TODO: remove

        # if self.dialog:
        #    self.dialog.hideOSD()
        #    if delete:
        #        d = self.dialog
        #        self.dialog = None
        #        d.doClose()
        #        del d

    def onVideoOSD(self):
        # self._dump_state()  # TODO: remove
        pass

    def onShowInfo(self):
        # self._dump_state()  # TODO: remove

        if self._call_back_on_show_info is not None:
            self._call_back_on_show_info()

    def tick(self):
        pass

    def onSeekOSD(self):
        self._logger.enter()
        # self._dump_state()  # TODO: remove

    def kill_playing_trailer(self):
        self._logger.enter()

    def monitor(self):
        Monitor.get_instance().throw_exception_if_shutdown_requested()
        if not self._monitor_thread or not self._monitor_thread.isAlive():
            if self._monitor_thread:
                self._monitor_thread.join()

            self._monitor_thread = threading.Thread(
                target=self._monitor, name='AdvancedPlayer:MONITOR')
            self._monitor_thread.start()

    def _monitor(self):
        kodi_monitor = Monitor.get_instance()
        try:
            self._logger.enter()

            while not kodi_monitor.wait_for_shutdown(0.1) and not self._closed:
                if not self.isPlaying():
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Player: Idling...')

                while not self.isPlaying() and not self._closed:
                    kodi_monitor.throw_exception_if_shutdown_requested(0.1)

                if self.isPlayingVideo():
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Monitoring video...')
                    self._video_monitor()
                elif self.isPlayingAudio():
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Monitoring audio...')
                    self._audio_monitor()
                elif self.isPlaying():
                    if self._logger.isEnabledFor(Logger.DEBUG):
                        self._logger.debug('Monitoring pre-play...')
                    self._preplay_monitor()

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.debug('Player: Closed')
        except (AbortException, ShutdownException):
            pass # Just exit thread
        except (Exception) as e:
            self._logger.exception('')
        finally:
            pass

    def _preplay_monitor(self):
        try:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.enter()
            kodi_monitor = Monitor.get_instance()
            self.onPrePlayStarted()
            while (self.isPlaying() and not self.isPlayingVideo()
                   and not self.isPlayingAudio()
                   and not self._closed):
                kodi_monitor.throw_exception_if_shutdown_requested(0.1)

            if not self.isPlayingVideo() and not self.isPlayingAudio():
                self.onPlayBackFailed()

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.exit()
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except (Exception) as e:
            self._logger.exception('')

    def _video_monitor(self):
        try:
            kodi_monitor = Monitor.get_instance()
            self._logger.enter()
            has_full_screened = False

            ct = 0
            while self.isPlayingVideo() and not self._closed:
                kodi_monitor.throw_exception_if_shutdown_requested(0.1)
                if xbmc.getCondVisibility('Window.IsActive(videoosd)'):
                    if not self._has_osd:
                        self._has_osd = True
                        self.onVideoOSD()
                else:
                    self._has_osd = False

                if self._closed:
                    break

                if xbmc.getCondVisibility('Player.ShowInfo'):
                    if not self._has_show_info:
                        self.onShowInfo()
                        self._has_show_info = True
                else:
                    self._has_show_info = False

                if self._closed:
                    break

                if xbmc.getCondVisibility('Window.IsActive(seekbar)'):
                    if not self._has_seek_osd:
                        self._has_seek_osd = True
                        self.onSeekOSD()
                else:
                    self._has_seek_osd = False

                if self._closed:
                    break

                if xbmc.getCondVisibility('VideoPlayer.IsFullscreen'):
                    if not has_full_screened:
                        has_full_screened = True
                        self.onVideoWindowOpened()
                elif has_full_screened and not xbmc.getCondVisibility('Window.IsVisible(busydialog)'):
                    has_full_screened = False
                    self.onVideoWindowClosed()

                if self._closed:
                    break

                ct += 1
                if ct > 9:
                    ct = 0
                    self.tick()

            if has_full_screened:
                self.onVideoWindowClosed()

            self._logger.exit()
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except (Exception) as e:
            self._logger.exception('')

    def _audio_monitor(self):
        try:
            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.enter()
            kodi_monitor = Monitor.get_instance()
            ct = 0
            while self.isPlayingAudio() and not kodi_monitor.is_shutdown_requested() and not self._closed:
                kodi_monitor.wait_for_shutdown(0.1)

                ct += 1
                if ct > 9:
                    ct = 0
                    self.tick()

            if self._logger.isEnabledFor(Logger.DEBUG):
                self._logger.exit()
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except (Exception) as e:
            self._logger.exception('')

    def shutdown_thread(self):
        if self._logger.isEnabledFor(Logger.DEBUG):
            self._logger.enter()
