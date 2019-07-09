# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

import sys
import os
import threading
from xml.dom import minidom

from kodi_six import xbmc, xbmcgui, utils

from common.constants import Constants, Movie
from common.playlist import Playlist
from common.exceptions import AbortException, ShutdownException
from common.logger import Logger
from common.monitor import Monitor
from player.player_container import PlayerContainer
from common.settings import Settings
from common.watchdog import WatchDog
from frontend.trailer_dialog import TrailerDialog, DialogState
from frontend.black_background import BlackBackground

'''
    Rough outline:
        Start separate threads to discover basic information about all selected
        video sources:
            1- library
            2- trailer folders
            3- iTunes
            4- TMDB
            5- (future) IMDB
        Each of the above store the discovered info into separate queues.
        The main function here is to discover the identity of all candidates
        for playing so that a balanced mix of trailers is available for playing
        and random selection. It is important to do this quickly. Additional
        information discovery is performed later, in background threads or
        just before playing the video.

        Immediately after starting the discovery threads, the player
        thread is started. The player thread:
            * Loops playing videos until stopped
            * On each iteration it gets movie a to play from
              TrailerManager's ReadyToPlay queue
            * Listens for events:stop & exit, pause, play, queue_movie, showInfo,
              Skip to next trailer, etc.

        TrailerManager holds various queues and lists:
            * Queues for each video source (library, iTunes, etc.) for
                the initial discovery from above
            * Queues for discovering additional information
            * DiscoveredTrailers, a list of all videos after filtering (genre,
                rating, etc). This list grows during initial discovery
            * A small queue (about 5 elements) for each video source so that
                required additional information can be discovered just before
                playing the video. The queues provide enough of a buffer so
                that playing will not be interrupted waiting on discovery
            * The ReadyToPlayQueue which is a small queue containing fully
                discovered trailers and awaiting play. WAs trailers are played
                it is refilled from the small final discovery queues above


'''

# TODO: Move to ui_utils

logger = Logger('random_trailer_ui')


def getTitleFont():
    # type: () -> TextType
    """

    :return:
    """
    local_monitor = logger.get_method_logger('getTitleFont')
    local_monitor.debug('In randomtrailer.getTitleFont')
    title_font = 'font13'
    base_size = 20
    multiplier = 1
    skin_dir = xbmc.translatePath("special://skin/")
    list_dir = os.listdir(skin_dir)
    fonts = []
    fontxml_path = ''
    font_xml = ''
    for item in list_dir:
        item = os.path.join(skin_dir, item)
        if os.path.isdir(item):
            font_xml = os.path.join(item, "Font.xml")
        if os.path.exists(font_xml):
            fontxml_path = font_xml
            break
    the_dom = minidom.parse(fontxml_path)
    fontlist = the_dom.getElementsByTagName('font')
    for font in fontlist:
        name = font.getElementsByTagName('name')[0].childNodes[0].nodeValue
        size = font.getElementsByTagName('size')[0].childNodes[0].nodeValue
        fonts.append({'name': name, 'size': float(size)})
    fonts = sorted(fonts, key=lambda k: k['size'])
    for f in fonts:
        if f['name'] == 'font13':
            multiplier = f['size'] / base_size
            break
    for f in fonts:
        if f['size'] >= 38 * multiplier:
            title_font = f['name']
            break
    return title_font


def play_trailers():
    # type: () -> None
    """

    :return:
    """
    my_trailer_dialog = None
    local_monitor = logger.get_method_logger('play_trailers')
    black_background = None
    try:
        black_background = BlackBackground.get_instance()
        black_background.show()
        my_trailer_dialog = TrailerDialog('script-trailerwindow.xml',
                                          Constants.ADDON_PATH, 'Default')
        my_trailer_dialog.doModal()
    finally:
        if my_trailer_dialog is not None:
            del my_trailer_dialog
            my_trailer_dialog = None
        if black_background is not None:
            black_background.destroy()
            del black_background
            black_background = None
        local_logger = Logger('play_trailers')
        local_logger.debug('ReplaceWindow(12005)')
        xbmc.executebuiltin('ReplaceWindow(12005)')
        local_logger.debug('Action(FullScreen,12005)')
        # xbmc.executebuiltin('ActivateWindow(12005)')
        # xbmc.executebuiltin('Action(FullScreen,12005)')
        local_logger.debug('About to local_monitor.exit()')
        local_monitor.exit()


# noinspection Annotator
class StartUI(threading.Thread):
    """

    """

    def __init__(self, started_as_screesaver):
        # type: () -> None
        """

        """
        super().__init__(name='startUI')
        self._logger = Logger(self.__class__.__name__)
        local_monitor = self._logger.get_method_logger('__init__')
        local_monitor.enter()

        self._player_container = None
        self._started_as_screensaver = started_as_screesaver
        WatchDog.register_thread(self)

    # Don't start if Kodi is busy playing something

    def run(self):
        # type: () -> None
        """

        :return:
        """
        local_monitor = self._logger.get_method_logger('run')
        try:
            local_monitor.debug('ADDON_PATH: ' + Constants.ADDON_PATH)

            finished = False
            while not finished:
                self.start_playing_trailers()
                break
                Monitor.get_instance().throw_exception_if_shutdown_requested(delay=60)

        except (AbortException):
            local_monitor.error(
                'Exiting Random Trailers Screen Saver due to Kodi Abort!')
        except (ShutdownException):
            local_monitor.error(
                'Exiting Random Trailers Screen Saver at addon\'s request')
        except (Exception) as e:
            local_monitor.log_exception(e)

        finally:
            local_monitor.debug('Stopping xbmc.Player')

            Monitor.get_instance().shutdown_requested()
            local_monitor.exit()

    def start_playing_trailers(self):
        # type: () -> None
        """

        :return:
        """
        local_monitor = self._logger.get_method_logger(
            'start_playing_trailers')
        # black_background = None
        try:
            local_monitor.debug('ADDON_PATH: ' + Constants.ADDON_PATH)

            if not xbmc.Player().isPlaying() and not self.check_for_xsqueeze():
                local_monitor.debug('Python path:', utils.py2_decode(sys.path))

                if (self._started_as_screensaver and Settings.is_set_fullscreen_when_screensaver()):
                    if not xbmc.getCondVisibility("System.IsFullscreen"):
                        xbmc.executebuiltin('xbmc.Action(togglefullscreen)')

                # TODO: Use settings

                current_dialog_id = xbmcgui.getCurrentWindowDialogId()
                current_window_id = xbmcgui.getCurrentWindowId()
                local_monitor.debug('CurrentDialogId, CurrentWindowId: ' + str(current_dialog_id) +
                                    ' ' + str(current_window_id))

                volume_was_adjusted = False
                if Settings.get_adjust_volume():
                    muted = xbmc.getCondVisibility(u"Player.Muted")
                    if not muted and Settings.get_volume() == 0:
                        xbmc.executebuiltin('xbmc.Mute()')
                    else:
                        volume = Settings.get_volume()
                        if volume != 100:
                            volume_was_adjusted = True
                            xbmc.executebuiltin(
                                'XBMC.SetVolume(' + str(volume) + ')')

                self._player_container = PlayerContainer.get_instance()
                # if Settings.get_show_curtains():
                #    self._player_container.get_player().play_trailer(Settings.get_open_curtain_path(),
                #                                                  {Movie.TITLE: 'openCurtain',
                # Movie.TRAILER: Settings.get_open_curtain_path()})

                # Finish curtain playing before proceeding

                #    self._player_container.get_player().waitForIsPlayingVideo(3)
                #    self._player_container.get_player().waitForIsNotPlayingVideo()
                play_trailers()

                # TODO: Need to adjust whenever settings changes

                if volume_was_adjusted:
                    muted = xbmc.getCondVisibility('Player.Muted')

                    if muted and Settings.get_volume() == 0:
                        xbmc.executebuiltin('xbmc.Mute()')
                    else:
                        # TODO: Looks fishy, why not set to what it was?

                        current_volume = xbmc.getInfoLabel('Player.Volume')
                        current_volume = int(
                            (float(current_volume.split(' ')[0]) + 60.0) / 60.0 * 100.0)
                        xbmc.executebuiltin(
                            'XBMC.SetVolume(' + str(current_volume) + ')')

                local_monitor.debug('Shutting down')
                Playlist.shutdown()
            else:
                local_monitor.notice(
                    'Exiting Random Trailers Screen Saver Something is playing!!!!!!')
        except (AbortException):
            local_monitor.error(
                'Exiting Random Trailers Screen Saver due to Kodi Abort!')
        except (ShutdownException):
            local_monitor.error(
                'Exiting Random Trailers Screen Saver at addon\'s request')
        except (Exception) as e:
            local_monitor.log_exception(e)

        finally:
            local_monitor.debug('Stopping xbmc.Player')
            #
            # Player is set to a dummy in the event that it is no longer in
            # Random Trailers control

            if (self._player_container is not None
                    and self._player_container.get_player() is not None):
                self._player_container.get_player().stop()

            local_monitor.debug('Deleting black screen')

            black_background = BlackBackground.get_instance()
            if black_background is not None:
                black_background.close()
                black_background.destroy()
                del black_background
            black_background = None
            local_monitor.exit()

    def check_for_xsqueeze(self):
        # type: () -> bool
        """

        :return:
        """
        local_monitor = self._logger.get_method_logger('check_for_xsqueeze')
        local_monitor.enter()
        key_map_dest_file = os.path.join(xbmc.translatePath(
            'special://userdata/keymaps'), "xsqueeze.xml")
        if os.path.isfile(key_map_dest_file):
            return True
        else:
            return False

    def shutdown_thread(self):
        # type: () -> None
        """

        :return:
        """
        pass
