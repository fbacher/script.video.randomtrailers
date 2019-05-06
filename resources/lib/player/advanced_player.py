# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from future import standard_library
standard_library.install_aliases()  # noqa: E402

from builtins import str
from kodi_six import xbmc

from common.exceptions import AbortException, ShutdownException
from common.logger import Logger, Trace
from common.monitor import Monitor
import sys
import threading


class PlayerState:
    STATE_STOPPED = u'stopped'
    STATE_PLAYING = u'playing'
    STATE_PAUSED = u'paused'


class AdvancedPlayer(xbmc.Player):

    '''
    isPlaying | onAVStarted, 
    isPlaying- False
    play Entering
    isFullScreen- False
    isPlayingAudio False
    isPlayingVideo False
    isPlayingRDS False
    isExternalPlayer False
    isFinished False
    play Exiting
    isPlaying False
    monitor Player: Idling
    isPlaying- False
    ...
    isPlaying- True
    monitor pre-play
    onPrePlayStarted
    isFullScreen False
    isPlaying True
    isPlayingVideo- False
    ...
    isPlayingVideo- True
    onSeekOSD
    isFullScreen True
    onVideoWindowOpened
    isPlaying True
    play Entering
    onPlayBackStarted
    onAVChange
    onAVChange
    onAVChange
    onSeekOSD
    onAVChange
    onAVStarted
    onPlayBackResumed
    onPlayBackStarted
    onAVChange
    onAVChange
    onAVChange
    onAVStarted
    -- Sometimes onPlayBackFailed, onPlayBackEnded, isFulllscreen: false, onPlayBackStarted, onAVChange, onAVStarted, -> isFullScreen True, onVideoWindowOpened, onAVChange

    onVideoWindowClosed
    hideOSD
    isFullScreen True
    isPlaying False
    isPlayingVideo False
    isFinished False   BUG
    onVideoWindowClosed
    idling

    Observe that we don't always get onPlayBackEnded & friends, but isPlaying goes to False


    '''

    def __init__(self):
        self._isPlaying = False
        self._isFinished = False
        self._killTrailerTimer = None
        self._previousInfoTag = None
        self._InfoDialogInitialized = False
        self._logger = Logger(self.__class__.__name__)
        self._monitorThread = None
        self._started = False
        self._closed = True
        self._hasOSD = False
        self._hasSeekOSD = False
        self._hasShowInfo = False
        self._currentTime = None
        self._playerWindowOpen = False
        self._callBackOnShowInfo = None
        self._playerState = PlayerState.STATE_STOPPED

    def setCallBacks(self, onVideoWindowOpened=None, onVideoWindowClosed=None,
                     onShowOSD=None, onShowInfo=None):
        self._callBackOnShowInfo = onShowInfo

    def enableAdvancedMonitoring(self):
        localLogger = self._logger.getMethodLogger(u'enableAdvancedMonitoring')
        localLogger.enter()
        self._closed = False
        self.monitor()

    def disableAdvancedMonitoring(self, shutdown=False):
        self._closed = True
        try:
            if self._monitorThread is not None and self._monitorThread.isAlive():
                self._monitorThread.join(0.1)
        finally:
            self._monitorThread = None

    def reset(self):
        localLogger = self._logger.getMethodLogger(u'reset')
        localLogger.enter()
        self.video = None
        self.started = False
        self.playerObject = None
        self.currentTime = 0

    def control(self, cmd):
        localLogger = self._logger.getMethodLogger(u'control')
        if cmd == 'play':
            localLogger.debug(u'Command=Play')
            if xbmc.getCondVisibility('Player.Paused | !Player.Playing'):
                localLogger.debug(u'Playing')
                xbmc.executebuiltin('PlayerControl(Play)')
        elif cmd == 'pause':
            localLogger.debug(u'Command=Pause')
            if not xbmc.getCondVisibility('Player.Paused'):
                localLogger.debug(u' Pausing')
                xbmc.executebuiltin('PlayerControl(Play)')

    @property
    def playState(self):
        localLogger = self._logger.getMethodLogger(u'playState')
        localLogger.enter()
        if xbmc.getCondVisibility('Player.Playing'):
            playState = PlayerState.STATE_PLAYING
        elif xbmc.getCondVisibility('Player.Paused'):
            playState = PlayerState.STATE_PAUSED
        else:
            playState = PlayerState.STATE_STOPPED
        localLogger.debug(u'playState: ' + playState)
        # self._dumpState()  # TODO: remove
        return playState

    def isVideoFullscreen(self):
        localLogger = self._logger.getMethodLogger(u'videoIsFullscreen')

        isFullScreen = bool(xbmc.getCondVisibility('VideoPlayer.IsFullscreen'))
        localLogger.debug(u'isFullScreen', isFullScreen)
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

        Monitor.getInstance().throwExceptionIfShutdownRequested()

        localLogger = self._logger.getMethodLogger(u'play')
        localLogger.enter()
        super(AdvancedPlayer, self).play(item, listitem, windowed, startpos)
        self.enableAdvancedMonitoring()
        # self._dumpState()  # TODO: remove
        localLogger.exit()

    # Defined in xbmc.Player
    def stop(self):
        """
        Stop playing. 
        """
        localLogger = self._logger.getMethodLogger(u'stop')
        localLogger.enter()
        super(AdvancedPlayer, self).stop()
        # self._dumpState()  # TODO: remove

    # Defined in xbmc.Player
    def pause(self):
        """ 
        Toggle play/pause state
        """

        localLogger = self._logger.getMethodLogger(u'pause')
        localLogger.enter()
        super(AdvancedPlayer, self).pause()
        self._dumpState()  # TODO: remove

    def pausePlay(self):
        localLogger = self._logger.getMethodLogger(u'pausePlay')
        localLogger.enter()
        if self.playState == PlayerState.STATE_PLAYING:
            self._dumpState()  # TODO: remove
            self.pause()

    def resumePlay(self):
        localLogger = self._logger.getMethodLogger(u'resumePlay')
        localLogger.enter()
        if self.playState == PlayerState.STATE_PAUSED:
            self._dumpState()  # TODO: remove
            self.pause()

    # Defined in xbmc.Player
    def playnext(self):
        """
        Play next item in playlist. 
        """
        localLogger = self._logger.getMethodLogger(u'playnext')
        localLogger.enter()
        super(AdvancedPlayer, self).playnext()
        # self._dumpState()  # TODO: remove

    # Defined in xbmc.Player
    def playprevious(self):
        """
        Play previous item in playlist. 
        """
        localLogger = self._logger.getMethodLogger(u'playprevious')
        localLogger.enter()
        super(AdvancedPlayer, self).playprevious()
        # self._dumpState()  # TODO: remove

    # Defined in xbmc.Player
    def playselected(self, selected):
        # type: (int) -> None
        """
        Play a certain item from the current playlist. 

        :param selected: Integer - Item to select 
        """
        localLogger = self._logger.getMethodLogger(u'playselected')
        localLogger.enter()
        super(AdvancedPlayer, self).playselected(selected)
        # self._dumpState()  # TODO: remove

    # Defined in xbmc.Player
    def isPlaying(self):
        """
        Is Kodi is playing something. 

        :return: True if Kodi is playing a file. 
        """
        #localLogger = self._logger.getMethodLogger(u'isPlaying')
        self._isPlaying = bool(super(AdvancedPlayer, self).isPlaying())
        #localLogger.debug(u': ' + str(self._isPlaying))

        return self._isPlaying

    def myIsPlayingVideo(self):
        localLogger = self._logger.getMethodLogger(u'myIsPlayingVideo')
        localLogger.enter()

        localLogger.debug(u' isPlayingVideo: ' +
                          str(self.isPlayingVideo()))
        """
        Returns True if the player is playing video.
        """
        localLogger.debug("Player.Playing: " +
                          str(bool(xbmc.getCondVisibility('Player.Playing'))))
        localLogger.debug(u'Player.HasVideo: ' +
                          str(bool(xbmc.getCondVisibility('Player.HasVideo'))))
        isPlaying = bool(xbmc.getCondVisibility('Player.Playing')
                         and xbmc.getCondVisibility('Player.HasVideo'))
        localLogger.debug(u' is really playing: ' +
                          str(isPlaying))
        return isPlaying

    # Defined in xbmc.Player
    def isPlayingAudio(self):
        """
        Is Kodi playing audio. 

        :return: True if Kodi is playing an audio file. 
        """
        #localLogger = self._logger.getMethodLogger(u'isPlayingAudio')
        playingAudio = bool(super(AdvancedPlayer, self).isPlayingAudio())
        # localLogger.debug(str(playingAudio))
        return playingAudio

    # Defined in xbmc.Player
    def isPlayingVideo(self):
        """
        Is Kodi playing video. 

        :return: True if Kodi is playing a video. 
        """
        #localLogger = self._logger.getMethodLogger(u'isPlayingVideo')
        isPlaying = bool(super(AdvancedPlayer, self).isPlayingVideo())
        #localLogger.debug(u': ' + str(isPlaying))

        return isPlaying

    # Defined in xbmc.Player
    def isPlayingRDS(self):
        """
        Check for playing radio data system (RDS). 

        :return: True if kodi is playing a radio data system (RDS). 
        """
        #localLogger = self._logger.getMethodLogger(u'isPlayingRDS')
        playingRDS = bool(super(AdvancedPlayer, self).isPlayingRDS())
        # localLogger.debug(str(playingRDS))
        return playingRDS

    def isPaused(self):
        paused = False
        if self._playerState == PlayerState.STATE_PAUSED:
            paused = True
        return True

    # Defined in xbmc.Player
    def isExternalPlayer(self):
        """
        Is Kodi using an external player. 

        :return: True if kodi is playing using an external player.

        New function added. 
        """
        #localLogger = self._logger.getMethodLogger(u'isExternalPlayer')
        externalPlayer = bool(super(AdvancedPlayer, self).isExternalPlayer())
        # localLogger.debug(str(externalPlayer))
        return externalPlayer

    def isFinished(self):
        localLogger = self._logger.getMethodLogger(u'isFinished')
        localLogger.enter()
        localLogger.debug(u'value: ' + str(self._isFinished))
        return self._isFinished

    # Defined in xbmc.Player
    def getPlayingFile(self):
        """
        Returns the current playing file as a string. 

        For LiveTV, returns a ``pvr://`` url which is not translatable to
        an OS specific file or external url.

        :return: Playing filename
        :raises Exception: If player is not playing a file. 
        """
        playingFile = u''
        try:
            localLogger = self._logger.getMethodLogger(u'getPlayingFile')
            localLogger.enter()
            playingFile = super(AdvancedPlayer, self).getPlayingFile()
            localLogger.debug(u'playingFile: ' + playingFile)
        except Exception as e:
            pass
        finally:
            return playingFile

    def _dumpState(self):
        localLogger = self._logger.getMethodLogger(u'_dumpState')
        self.isVideoFullscreen()
        self.isPlaying()
        self.isPlayingAudio()
        self.isPlayingVideo()
        self.isPlayingRDS()
        self.isExternalPlayer()
        self.isFinished()
        localLogger.debug(u'playState: ', self._playerState)

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
            #localLogger = self._logger.getMethodLogger(u'getTime')
            # localLogger.enter()
            time = super(AdvancedPlayer, self).getTime()
            #localLogger.debug(u'time: ' + str(time))
        except:
            pass

        return time

    # Defined in xbmc.Player
    def seekTime(self, seekTime):
        """
        Seek time. 

        Seeks the specified amount of time as fractional seconds. The time
        specified is relative to the beginning of the currently
        playing media file.

        :param seekTime: Time to seek as fractional seconds 
        :raises Exception: If player is not playing a file. 
        """
        seekTime = 0
        try:
            localLogger = self._logger.getMethodLogger(u'seekTime')
            localLogger.enter()
            seekTime = super(AdvancedPlayer, self).seekTime(seekTime)
            localLogger.debug(u'seekTime: ' + str(seekTime))
        except:
            pass
        finally:
            return seekTime

    # Defined in xbmc.Player
    def setSubtitles(self, subtitleFile):
        """
        Set subtitle file and enable subtitles. 

        :param subtitleFile: File to use as source of subtitles
        """
        return super(AdvancedPlayer, self).setSubtitles(subtitleFile)

    # Defined in xbmc.Player
    def showSubtitles(self, bVisible):
        # type: (bool) -> None
        """
        Enable / disable subtitles. 

        :param visible: [boolean] True for visible subtitles.

        Example::

            xbmc.Player().showSubtitles(True)
        """
        return super(AdvancedPlayer, self).showSubtitles(bVisible)

    # Defined in xbmc.Player
    def getSubtitles(self):
        # type: () -> str
        """
        Get subtitle stream name. 

        :return: Stream name 
        """
        return super(AdvancedPlayer, self).getSubtitles()

    # Defined in xbmc.Player
    def getAvailableSubtitleStreams(self):
        # type: () -> List[str]
        """
        Get Subtitle stream names. 

        :return: List of subtitle streams as name 
        """
        return super(AdvancedPlayer, self).getAvailableSubtitleStreams()

    # Defined in xbmc.Player
    def setSubtitleStream(self, iStream):
        # type: (int) -> None
        """
        Set Subtitle Stream. 

        :param iStream: [int] Subtitle stream to select for play

        Example::

            xbmc.Player().setSubtitleStream(1)
        """
        return super(AdvancedPlayer, self).setSubtitleStream(iStream)

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
        super(AdvancedPlayer, self).updateInfoTag(item)

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
        return super(AdvancedPlayer, self).getVideoInfoTag()

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
        return super(AdvancedPlayer, self).getMusicInfoTag()

    # Defined in xbmc.Player
    def getRadioRDSInfoTag(self):
        # type: () -> InfoTagRadioRDS
        """
        To get Radio RDS info tag 

        Returns the RadioRDSInfoTag of the current playing 'Radio Song if. present'.

        :return: Radio RDS info tag
        :raises Exception: If player is not playing a file or current file
            is not a rds file.
        """
        try:
            return super(AdvancedPlayer, self).getRadioRDSInfoTag()
        except:
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
            return super(AdvancedPlayer, self).getTotalTime()
        except:
            return 0

    # Defined in xbmc.Player
    def getAvailableAudioStreams(self):
        # type: () -> List[str]
        """
        Get Audio stream names 

        :return: List of audio streams as name 
        """
        return super(AdvancedPlayer, self).getAvailableAudioStreams()

    # Defined in xbmc.Player
    def setAudioStream(self, iStream):
        # type: (int) -> None
        """
        Set Audio Stream. 

        :param iStream: [int] Audio stream to select for play

        Example::

            xbmc.Player().setAudioStream(1)
        """
        return super(AdvancedPlayer, self).setAudioStream(iStream)

    # Defined in xbmc.Player
    def getAvailableVideoStreams(self):
        # type: () -> List[str]
        """
        Get Video stream names 

        :return: List of video streams as name 
        """
        return super(AdvancedPlayer, self).getAvailableVideoStreams()

    # Defined in xbmc.Player
    def setVideoStream(self, iStream):
        # type: (int) -> None
        """
        Set Video Stream. 

        :param iStream: [int] Video stream to select for play

        Example::

            xbmc.Player().setVideoStream(1)
        """
        return super(AdvancedPlayer, self).setVideoStream(iStream)

    def getPlayingTitle(self):
        localLogger = self._logger.getMethodLogger(u'getPlayingTitle')
        try:
            playingFile = super(AdvancedPlayer, self).getPlayingFile()
        except (Exception) as e:
            playingFile = u'unknown'
        try:
            infoTag = self.getVideoInfoTag()
            title = infoTag.getTitle()
        except (Exception) as e:
            title = "Exception- Nothing Playing?"

            localLogger.debug(u'title:', title, u'file:', playingFile)

        except Exception as e:
            localLogger.logException(e)
            self._isFinished = True

        return title

    def killPlayer(self):
        localLogger = self._logger.getMethodLogger(u'killPlayer')
        localLogger.enter()
        if not self._isFinished:
            xbmc.executebuiltin('xbmc.PlayerControl(Stop)')

        self._isFinished = True

    def onPrePlayStarted(self):
        localLogger = self._logger.getMethodLogger(u'onPrePlayStarted')
        localLogger.enter()
        localLogger.trace(trace=Trace.TRACE)
        # self._dumpState()  # TODO: remove

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

        localLogger = self._logger.getMethodLogger(u'onPlayBackStarted')
        localLogger.debug(u'You probably want to use onAVStarted instead')
        # self._dumpState()  # TODO: remove

    # Defined in xbmc.Playesr
    def onAVStarted(self):
        '''
        Will be called when Kodi has a video or audiostream.

        v18 Python API changes:
            New function added. 
        '''
        localLogger = self._logger.getMethodLogger(u'onAVStarted')
        localLogger.trace(self.getPlayingTitle(), trace=Trace.TRACE)

        # self._dumpState()  # TODO: remove
        self._onAVStarted = True
        '''
        infoTag = self.getVideoInfoTag()
        newMovieStarted = False
        if (infoTag != self._previousInfoTag):
            self._previousInfoTag = infoTag
            newMovieStarted = True

        xbmc.log("AdvancedPlayer.onAVStarted-Video: " + str(bool(self.isPlayingVideo())) +
                 " New Movie: " + str(newMovieStarted) + " " + self.getPlayingTitle(), xbmc.LOGNOTICE)
        if (newMovieStarted):
            if (self._killTrailerTimer != None):
                self._killTrailerTimer.cancel()
                del self._killTrailerTimer
                self._killTrailerTimer = None

            previewTime = getPreviewTime
            if (previewTime() > 0):
                self._killTrailerTimer = threading.Timer(
                    previewTime(), self.killPlayingTrailer)
                self._killTrailerTimer.start()
                xbmc.log("Started timer", xbmc.LOGNOTICE)
            else:
                self._killTrailerTimer = None

            self.displayInfo()
        '''

    def waitForIsPlayingVideo(self, timeout=None):
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
        localLogger = self._logger.getMethodLogger(u'waitForIsPlayingVideo')
        localLogger.enter()
        if timeout is None:
            timeout = 3600  # An hour, insane

        timeout = timeout * 1000  # Convert to ms
        kodiMonitor = Monitor.getInstance()

        # TODO: Add check for failures: onPlabackFailed/Ended/Error
        while not self._playerWindowOpen and timeout > 0 and not kodiMonitor.waitForShutdown(0.250):
            timeout -= 250

        if timeout <= 0:
            localLogger.debug(u'Timed out waiting')
            return False

        localLogger.exit()
        return True

    def waitForIsNotPlayingVideo(self, timeout=None, trace=None):
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
        localLogger = self._logger.getMethodLogger(u'waitForIsNotPlayingVideo')
        localLogger.enter(trace=trace)

        try:
            if timeout is None:
                timeout = 0
                if self._playerWindowOpen:
                    timeout = self.getTime()
                    timeout = self.getTotalTime() - timeout + 2
                    localLogger.debug(u'Setting timeout to: ' + str(timeout))
        except:
            # Player must be finished

            timeout = 0

        timeout = timeout * 1000  # Convert to ms
        kodiMonitor = Monitor.getInstance()
        while self._playerWindowOpen and timeout > 0 and not kodiMonitor.waitForShutdown(0.250):
            timeout -= 250

        if timeout > 0:
            localLogger.debug(u'Timed out waiting')
            return False

        localLogger.exit()
        return True

    # Defined in xbmc.Player
    def onAVChange(self):
        '''
            Will be called when Kodi has a video, audio or subtitle stream. Also
            happens when the stream changes.

            v18 Python API changes:
            New function added. 
        '''
        localLogger = self._logger.getMethodLogger(u'onAVChange')
        self._onAVChange = True
        localLogger.trace(self.getPlayingTitle(), trace=Trace.TRACE)
        # self._dumpState()  # TODO: remove

        # self.displayInfo()

    # Defined in xbmc.Player
    def onPlayBackEnded(self):
        '''
            Will be called when Kodi stops playing a file. 
        '''
        localLogger = self._logger.getMethodLogger(u'onPlayBackEnded')
        self._onPlayBackEnded = True
        self._playerState = PlayerState.STATE_STOPPED

        localLogger.trace(trace=Trace.TRACE)
        # self._dumpState()  # TODO: remove
        if not self._started:
            self.onPlayBackFailed()

    def onPlayBackFailed(self):
        localLogger = self._logger.getMethodLogger(u'onPlayBackFailed')
        localLogger.trace(trace=Trace.TRACE)
        self._playerState = PlayerState.STATE_STOPPED

        # self._dumpState()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackStopped(self):
        '''
        Will be called when user stops Kodi playing a file. 
        '''
        localLogger = self._logger.getMethodLogger(u'onPlayBackStopped')
        self._playBackStopped = True
        localLogger.trace(trace=Trace.TRACE)
        self._playerState = PlayerState.STATE_STOPPED
        # self._dumpState()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackError(self):
        '''
            Will be called when playback stops due to an error.
        '''
        localLogger = self._logger.getMethodLogger(u'onPlayBackError')
        self._onPlayBackError = True
        localLogger.trace(trace=Trace.TRACE)
        self._playerState = PlayerState.STATE_STOPPED
        # self._dumpState()  # TODO: remove

    # Defined in xbmc.Playser
    def onPlayBackPaused(self):
        '''
            Will be called when user pauses a playing file. 
        '''
        localLogger = self._logger.getMethodLogger(u'onPlayBackPaused')

        self._playerState = PlayerState.STATE_PAUSED
        localLogger.trace(self.getPlayingTitle(), trace=Trace.TRACE)
        # self._dumpState()  # TODO: remove

    # Defined in xbmc.Playser
    def onPlayBackResumed(self):
        '''
            Will be called when user resumes a paused file. 
        '''
        localLogger = self._logger.getMethodLogger(u'onPlayBackResumed')

        localLogger.trace(self.getPlayingTitle(), trace=Trace.TRACE)
        self._playerState = PlayerState.STATE_PLAYING

        # self._dumpState()  # TODO: remove

        # self.displayInfo()

    # Defined in xbmc.Player
    def onPlayBackSeek(self, time, seekOffset):
        '''
        Will be called when user seeks to a time.
        '''
        localLogger = self._logger.getMethodLogger(u'onPlayBackSeek')
        localLogger.trace(trace=Trace.TRACE)
        # self._dumpState()  # TODO: remove

    # Defined in xbmc.Player
    def onPlayBackSeekChapter(self, chapter):
        '''
        Will be called when user performs a chapter seek.
        '''
        localLogger = self._logger.getMethodLogger(u'onPlayBackSeekChapter')
        localLogger.trace(trace=Trace.TRACE)

    # Defined in xmbc.Player
    def onPlayBackSpeedChanged(self, speed):
        '''
        Will be called when players speed changes (eg. user FF/RW).

        Note:  Negative speed means player is rewinding, 1 is normal playback speed. 
        '''
        localLogger = self._logger.getMethodLogger(u'onPlayBackSpeedChanged')
        localLogger.trace(trace=Trace.TRACE)

    # Defined in xbmc.Player
    def onQueueNextItem(self):
        '''
        Will be called when user queues the next item. 
        '''
        localLogger = self._logger.getMethodLogger(u'onQueueNextItem')
        localLogger.trace(self.getPlayingTitle(), trace=Trace.TRACE)
        # self._dumpState()  # TODO: remove

    def onVideoWindowOpened(self):
        localLogger = self._logger.getMethodLogger(u'onVideoWindowOpened')
        localLogger.trace(trace=Trace.TRACE)
        # self._dumpState()  # TODO: remove
        self._playerWindowOpen = True
        # self.getDialog().show()

    def onVideoWindowClosed(self):
        localLogger = self._logger.getMethodLogger(u'onVideoWindowClosed')
        localLogger.enter()
        self._playerWindowOpen = False
        self.hideOSD()
        # self._dumpState()  # TODO: remove

    def showOSD(self, from_seek=False):
        localLogger = self._logger.getMethodLogger(u'showOSD')
        localLogger.enter()
        # self._dumpState()  # TODO: remove

        # if self.dialog:
        #    self.updateOffset()
        #    self.dialog.update(self.offset, from_seek)
        #    self.dialog.showOSD()

    def hideOSD(self, delete=False):
        localLogger = self._logger.getMethodLogger(u'hideOSD')
        localLogger.enter()
        # self._dumpState()  # TODO: remove

        # if self.dialog:
        #    self.dialog.hideOSD()
        #    if delete:
        #        d = self.dialog
        #        self.dialog = None
        #        d.doClose()
        #        del d

    def onVideoOSD(self):
        localLogger = self._logger.getMethodLogger(u'onVideoOSD')
        localLogger.trace(trace=Trace.TRACE)
        # self._dumpState()  # TODO: remove

    def onShowInfo(self):
        localLogger = self._logger.getMethodLogger(u'onShowInfo')
        localLogger.trace(trace=Trace.TRACE)
        # self._dumpState()  # TODO: remove

        if self._callBackOnShowInfo is not None:
            self._callBackOnShowInfo.onShowInfo()

    def tick(self):
        pass

    def onSeekOSD(self):
        localLogger = self._logger.getMethodLogger(u'onSeekOSD')
        localLogger.enter()
        # self._dumpState()  # TODO: remove

    def killPlayingTrailer(self):
        localLogger = self._logger.getMethodLogger(u'killPlayingTrailer')
        localLogger.enter()
        # self._dumpState()  # TODO: remove

        '''
        if (not self._isFinished):
            try:
                super(AdvancedPlayer, self).playnext()
            except Exception as e:
                xbmc.log("AdvancedPlayer.killPlayingTrailer Exception caught: " + str(e))
        '''

    def monitor(self):
        Monitor.getInstance().throwExceptionIfShutdownRequested()
        if not self._monitorThread or not self._monitorThread.isAlive():
            if self._monitorThread:
                self._monitorThread.join()

            self._monitorThread = threading.Thread(
                target=self._monitor, name='AdvancedPlayer:MONITOR')
            self._monitorThread.start()

    def _monitor(self):
        try:
            kodiMonitor = Monitor.getInstance()
            localLogger = self._logger.getMethodLogger(u'_monitor')
            localLogger.enter()

            while not kodiMonitor.waitForShutdown(0.1) and not self._closed:
                if not self.isPlaying():
                    localLogger.debug('Player: Idling...')

                while (not self.isPlaying() and not kodiMonitor.isShutdownRequested()
                        and not self._closed):
                    kodiMonitor.waitForShutdown(0.1)

                if self.isPlayingVideo():
                    localLogger.debug('Monitoring video...')
                    self._videoMonitor()
                elif self.isPlayingAudio():
                    localLogger.debug('Monitoring audio...')
                    self._audioMonitor()
                elif self.isPlaying():
                    localLogger.debug('Monitoring pre-play...')
                    self._preplayMonitor()

            localLogger.debug('Player: Closed')
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)
        finally:
            pass

    def _preplayMonitor(self):
        try:
            localLogger = self._logger.getMethodLogger(u'_preplayMonitor')
            localLogger.enter()
            kodiMonitor = Monitor.getInstance()
            self.onPrePlayStarted()
            while (self.isPlaying() and not self.isPlayingVideo()
                   and not self.isPlayingAudio()
                    and not kodiMonitor.isShutdownRequested() and not self._closed):
                kodiMonitor.waitForShutdown(0.1)

            if not self.isPlayingVideo() and not self.isPlayingAudio():
                self.onPlayBackFailed()

            localLogger.exit()
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)

    def _videoMonitor(self):
        try:
            kodiMonitor = Monitor.getInstance()
            localLogger = self._logger.getMethodLogger(u'_videoMonitor')
            localLogger.enter()
            hasFullScreened = False

            ct = 0
            while self.isPlayingVideo() and not kodiMonitor.isShutdownRequested() and not self._closed:
                self.currentTime = self.getTime()
                kodiMonitor.waitForShutdown(0.1)
                if xbmc.getCondVisibility('Window.IsActive(videoosd)'):
                    if not self._hasOSD:
                        self._hasOSD = True
                        self.onVideoOSD()
                else:
                    self._hasOSD = False

                if xbmc.getCondVisibility('Player.ShowInfo'):
                    if not self._hasShowInfo:
                        self.onShowInfo()
                        self._hasShowInfo = True
                else:
                    self._hasShowInfo = False
                if xbmc.getCondVisibility('Window.IsActive(seekbar)'):
                    if not self._hasSeekOSD:
                        self._hasSeekOSD = True
                        self.onSeekOSD()
                else:
                    self._hasSeekOSD = False

                if xbmc.getCondVisibility('VideoPlayer.IsFullscreen'):
                    if not hasFullScreened:
                        hasFullScreened = True
                        self.onVideoWindowOpened()
                elif hasFullScreened and not xbmc.getCondVisibility('Window.IsVisible(busydialog)'):
                    hasFullScreened = False
                    self.onVideoWindowClosed()

                ct += 1
                if ct > 9:
                    ct = 0
                    self.tick()

            if hasFullScreened:
                self.onVideoWindowClosed()

            localLogger.exit()
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)

    def _audioMonitor(self):
        try:
            localLogger = self._logger.getMethodLogger(u'_audioMonitor')
            localLogger.enter()
            kodiMonitor = Monitor.getInstance()
            self._started = True
            ct = 0
            while self.isPlayingAudio() and not kodiMonitor.isShutdownRequested() and not self._closed:
                self.currentTime = self.getTime()
                kodiMonitor.waitForShutdown(0.1)

                ct += 1
                if ct > 9:
                    ct = 0
                    self.tick()

            localLogger.exit()
        except (AbortException, ShutdownException):
            raise sys.exc_info()
        except Exception as e:
            localLogger.logException(e)

    def shutdownThread(self):
        localLogger = self._logger.getMethodLogger(u'shutdownThread')
        localLogger.enter()
