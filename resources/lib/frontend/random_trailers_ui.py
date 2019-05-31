# -*- coding: utf-8 -*-
"""
Created on Feb 12, 2019

@author: Frank Feuerbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from future.builtins import (
    bytes, dict, int, list, object, range, str,
    ascii, chr, hex, input, next, oct, open,
    pow, round, super, filter, map, zip)

from common.development_tools import (Any, Callable, Optional, Iterable, List, Dict, Tuple, Sequence, Union,
                                      TextType, DEVELOPMENT, RESOURCE_LIB)
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

logger = Logger(u'random_trailer_ui')


def getTitleFont():
    # type: () -> TextType
    """

    :return:
    """
    local_monitor = logger.get_method_logger(u'getTitleFont')
    local_monitor.debug(u'In randomtrailer.getTitleFont')
    title_font = 'font13'
    base_size = 20
    multiplier = 1
    skin_dir = xbmc.translatePath("special://skin/")
    list_dir = os.listdir(skin_dir)
    fonts = []
    fontxml_path = u''
    font_xml = u''
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
    fonts = sorted(fonts, key=lambda k: k[u'size'])
    for f in fonts:
        if f[u'name'] == 'font13':
            multiplier = f[u'size'] / base_size
            break
    for f in fonts:
        if f[u'size'] >= 38 * multiplier:
            title_font = f[u'name']
            break
    return title_font


def play_trailers():
    # type: () -> None
    """

    :return:
    """
    my_trailer_dialog = None
    local_monitor = logger.get_method_logger(u'play_trailers')
    try:
        black_background = BlackBackground.get_instance()
        black_background.show()
        my_trailer_dialog = TrailerDialog(u'script-trailerwindow.xml',
                                        Constants.ADDON_PATH, u'Default')
        _exit = my_trailer_dialog.doModal()

        """
            currentWindow = xbmcgui.getCurrentWindowId()
            # fullscreenvideo 		12005
            # ReplaceWindow(u'fullscreenvideo')
            black_background.set_visibility(opaque=False)
            windowId = black_background.get_window_id()

            black_background.close()
            xbmc.executebuiltin(u'ReplaceWindow(' + str(currentWindow) + u')')
            del black_background
            xbmc.executebuiltin(u'ReplaceWindow(' + str(currentWindow) + u')')
         """
    finally:
        if my_trailer_dialog is not None:
            del my_trailer_dialog
            my_trailer_dialog = None
            local_monitor.exit()


# noinspection Annotator
class StartUI(threading.Thread):
    """

    """
    def __init__(self):
        # type: () -> None
        """

        """
        super().__init__(name=u'startUI')
        self._logger = Logger(self.__class__.__name__)
        local_monitor = self._logger.get_method_logger(u'__init__')
        local_monitor.enter()

        self._player_container = None
        WatchDog.register_thread(self)

    # Don't start if Kodi is busy playing something

    def run(self):
        # type: () -> None
        """

        :return:
        """
        local_monitor = self._logger.get_method_logger(u'run')
        try:
            local_monitor.debug(u'ADDON_PATH: ' + Constants.ADDON_PATH)

            finished = False
            while not finished:
                self.start_playing_trailers()
                break
                Monitor.get_instance().throw_exception_if_shutdown_requested(delay=60)

        except AbortException:
            local_monitor.error(
                'Exiting Random Trailers Screen Saver due to Kodi Abort!')
        except ShutdownException:
            local_monitor.error(
                u'Exiting Random Trailers Screen Saver at addon\'s request')
        except Exception as e:
            local_monitor.log_exception(e)

        finally:
            local_monitor.debug(u'Stopping xbmc.Player')

            Monitor.get_instance().shutdown_requested()
            local_monitor.exit()

    def start_playing_trailers(self):
        # type: () -> None
        """

        :return:
        """
        local_monitor = self._logger.get_method_logger(u'start_playing_trailers')
        # black_background = None
        try:
            local_monitor.debug(u'ADDON_PATH: ' + Constants.ADDON_PATH)

            if not xbmc.Player().isPlaying() and not self.check_for_xsqueeze():
                local_monitor.debug(u'Python path:', utils.py2_decode(sys.path))

                # TODO: Use settings

                current_dialog_id = xbmcgui.getCurrentWindowDialogId()
                current_window_id = xbmcgui.getCurrentWindowId()
                local_monitor.debug(u'CurrentDialogId, CurrentWindowId: ' + str(current_dialog_id) +
                                  u' ' + str(current_window_id))

                if Settings.get_adjust_volume():
                    muted = xbmc.getCondVisibility(u"Player.Muted")
                    if not muted and Settings.get_volume() == 0:
                        xbmc.executebuiltin(u'xbmc.Mute()')
                    else:
                        xbmc.executebuiltin(
                            u'XBMC.SetVolume(' + str(Settings.get_volume()) + ')')

                self._player_container = PlayerContainer.get_instance()
                # if Settings.get_show_curtains():
                #    self._player_container.get_player().play_trailer(Settings.get_open_curtain_path(),
                #                                                  {Movie.TITLE: u'openCurtain',
                # Movie.TRAILER: Settings.get_open_curtain_path()})

                # Finish curtain playing before proceeding

                #    self._player_container.get_player().waitForIsPlayingVideo(3)
                #    self._player_container.get_player().waitForIsNotPlayingVideo()
                play_trailers()
                # del self._player_container
                # self._player_container = None
                # del black_background
                # black_background = None
                if Settings.get_adjust_volume():
                    muted = xbmc.getCondVisibility(u'Player.Muted')

                    if muted and Settings.get_volume() == 0:
                        xbmc.executebuiltin('xbmc.Mute()')
                    else:
                        current_volume = xbmc.getInfoLabel(u'Player.Volume')
                        current_volume = int(
                            (float(current_volume.split(u' ')[0]) + 60.0) / 60.0 * 100.0)
                        xbmc.executebuiltin(
                            'XBMC.SetVolume(' + str(current_volume) + ')')

                local_monitor.debug(u'Shutting down')
                Playlist.shutdown()
            else:
                local_monitor.notice(
                    'Exiting Random Trailers Screen Saver Something is playing!!!!!!')
        except AbortException:
            local_monitor.error(
                'Exiting Random Trailers Screen Saver due to Kodi Abort!')
        except ShutdownException:
            local_monitor.error(
                u'Exiting Random Trailers Screen Saver at addon\'s request')
        except Exception as e:
            local_monitor.log_exception(e)

        finally:
            local_monitor.debug(u'Stopping xbmc.Player')
            #
            # Player is set to a dummy in the event that it is no longer in
            # Random Trailers control

            if (self._player_container is not None
                    and self._player_container.get_player() is not None):
                self._player_container.get_player().stop()

            local_monitor.debug(u'Deleting black screen')

            black_background = BlackBackground.get_instance()
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
        local_monitor = self._logger.get_method_logger(u'check_for_xsqueeze')
        local_monitor.enter()
        key_map_dest_file = os.path.join(xbmc.translatePath(
            u'special://userdata/keymaps'), "xsqueeze.xml")
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
