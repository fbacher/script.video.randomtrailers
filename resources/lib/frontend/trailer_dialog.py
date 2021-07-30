# -*- coding: utf-8 -*-

"""
Created on Apr 17, 2019

@author: Frank Feuerbacher

"""

import datetime
import os
import re
import sys
import threading

import xbmc
import xbmcgui
from xbmcgui import (Control, ControlImage, ControlButton, ControlEdit,
                     ControlGroup, ControlLabel, ControlList, ControlTextBox,
                     ControlSpin, ControlSlider, ControlProgress, ControlFadeLabel,
                     ControlRadioButton)

from common.constants import Constants
from common.debug_utils import Debug
from common.imports import *
from common.movie import AbstractMovie, FolderMovie, TFHMovie
from common.movie_constants import MovieField
from common.playlist import Playlist
from common.exceptions import AbortException
from common.logger import LazyLogger, Trace
from common.messages import Messages
from common.monitor import Monitor
from common.utils import Utils
from action_map import Action
from common.settings import Settings
from frontend.dialog_controller import DialogState, BaseDialogStateMgr, Task, TaskLoop
from frontend.dialog_utils import (ControlId, Glue, MovieTimer, NotificationTimer,
                                   TrailerPlayer,
                                   TrailerStatus)
from frontend.front_end_exceptions import (SkipMovieException, StopPlayingGroup,
                                           UserExitException)
from frontend.history_list import HistoryList
from player.my_player import MyPlayer
from player.player_container import PlayerContainer
from frontend.black_background import BlackBackground
from frontend.movie_manager import MovieManager, MovieStatus
from frontend.history_empty import HistoryEmpty
from frontend.utils import ReasonEvent
from frontend import text_to_speech

module_logger = LazyLogger.get_addon_module_logger(file_path=__file__)


class TrailerDialog(xbmcgui.WindowXMLDialog):
    """
        Note that the underlying 'script-movie-window.xml' has a "videowindow"
        control. This causes the player to ignore many of the normal keymap actions.
    """

    DUMMY_TRAILER: AbstractMovie = FolderMovie({
        MovieField.TITLE: '',
        MovieField.THUMBNAIL: '',
        MovieField.FANART: '',
        MovieField.ACTORS: '',
        MovieField.PLOT: '',
    })

    _playlist_map: Dict[int, int] = {xbmcgui.REMOTE_1: 1,
                                     xbmcgui.REMOTE_2: 2,
                                     xbmcgui.REMOTE_3: 3,
                                     xbmcgui.REMOTE_4: 4,
                                     xbmcgui.REMOTE_5: 5,
                                     xbmcgui.REMOTE_6: 6,
                                     xbmcgui.REMOTE_7: 7,
                                     xbmcgui.REMOTE_8: 8,
                                     xbmcgui.REMOTE_9: 9,
                                     xbmcgui.REMOTE_0: 10,

                                     xbmcgui.ACTION_JUMP_SMS2: 2,
                                     xbmcgui.ACTION_JUMP_SMS3: 3,
                                     xbmcgui.ACTION_JUMP_SMS4: 4,
                                     xbmcgui.ACTION_JUMP_SMS5: 5,
                                     xbmcgui.ACTION_JUMP_SMS6: 6,
                                     xbmcgui.ACTION_JUMP_SMS7: 7,
                                     xbmcgui.ACTION_JUMP_SMS8: 8,
                                     xbmcgui.ACTION_JUMP_SMS9: 9}
    TFH_JUNK_PATTERN: Pattern = re.compile(r'(\n ?\n.*)|'
              r'(?:Like us on Facebook.*)|'
              r'(?:http://www.trailersfromhell.com.*)|'
              r'(?:ABOUT TRAILERS FROM HELL:.*)|'
              r'(?:As always, you can find more commentary.*)|'
              r'(?:But wait! There\'s more! TFH.*)|'
              r'(?:Want more TFH.*)|'
              r'(?:Want to know more? The TFH.*)|'
              r'(?:DID YOU KNOW: we have a podcast.*)', re.DOTALL)

    _logger: LazyLogger = None
    _trailer_dialog: ForwardRef('TrailerDialog') = None

    def __init__(self, *args: Any) -> None:
        """

        :param args:
        """
        super().__init__(*args)
        clz = type(self)
        if clz._logger is None:
            clz._logger = module_logger.getChild(clz.__name__)
        clz._logger.enter()

        clz._trailer_dialog = self
        TrailerStatus.class_init(self)
        TrailerPlayer.class_init(trailer_dialog=self)
        Glue.set_dialog(self)
        BaseDialogStateMgr.set_trailer_dialog(self)

        self._player_container: PlayerContainer = PlayerContainer.get_instance()
        self._player_container.register_exit_on_movie_playing(
            self.exit_screensaver_to_play_movie)

        self.get_player().set_callbacks(
            on_show_info=TrailerPlayer.show_details_and_play)
        self._title_control: ControlLabel = None
        self._source: str = None
        self._movie: AbstractMovie = None
        self._lock: threading.RLock = threading.RLock()
        self._thread: threading.Thread = None

        # Used mostly as a timer
        self._wait_event: ReasonEvent = ReasonEvent()
        Monitor.register_abort_listener(self.on_abort_event)

        self._movie_manager: MovieManager = MovieManager()
        self._queued_movie: AbstractMovie = None
        self._get_next_trailer_start: datetime.datetime = None
        self.trailers_per_iteration: int = None
        self.group_trailers: bool = None
        self.total_trailers_to_play: int = None
        self.delay_between_groups: int = None
        self.exiting_playing_movie: bool = False
        self._dialog_state_mgr = BaseDialogStateMgr.get_instance()

    def get_movie_manager(self) -> MovieManager:
        return self._movie_manager

    def onInit(self) -> None:
        """

        :return:
        """
        clz = type(self)
        clz._logger.enter()

        # Prevent flash of grid
        #
        # TrailerStatus.opaque()

        if self._thread is None:
            self._thread = threading.Thread(
                target=self.play_trailers, name='TrailerDialog')
            self._thread.start()

    def configure_trailer_play_parameters(self) -> None:
        """

        :return:
        """
        total_trailers_to_play: int = Settings.get_number_of_trailers_to_play()

        trailers_per_group: int = total_trailers_to_play
        group_trailers: bool = Settings.is_group_trailers()

        if group_trailers:
            trailers_per_group = Settings.get_trailers_per_group()

        trailers_per_iteration: int = total_trailers_to_play
        if trailers_per_group > 0:
            trailers_per_iteration = trailers_per_group
            if total_trailers_to_play > 0:
                trailers_per_iteration = min(
                    trailers_per_iteration, total_trailers_to_play)

        delay_between_groups: int = Settings.get_group_delay()

        self.trailers_per_iteration = trailers_per_iteration
        self.group_trailers = group_trailers
        self.total_trailers_to_play = total_trailers_to_play
        self.delay_between_groups = delay_between_groups

    def play_trailers(self) -> None:
        """

        :return:
        """
        clz = type(self)
        self.configure_trailer_play_parameters()
        trailers_played: int = 0
        try:
            self._logger.debug('In play_trailers')
            while not self._dialog_state_mgr.is_random_trailers_play_state():
                self.play_a_group_of_trailers()

                if self._dialog_state_mgr.is_random_trailers_play_state(DialogState.NO_TRAILERS_TO_PLAY):
                    break

                self._player_container.get_player().wait_for_is_not_playing_video()

                # Pre-seed all fields with empty values so that if display of
                # detailed movie text occurs prior to download of external
                # images, etc. This way default values are shown instead of
                # leftovers from previous movie.

                self._movie = TrailerDialog.DUMMY_TRAILER
                self.update_detail_view(self._movie)  # Does not display

                if self.group_trailers:
                    if self.total_trailers_to_play > 0:
                        trailers_played += self.trailers_per_iteration
                        remaining_to_play = self.total_trailers_to_play - trailers_played
                        if remaining_to_play <= 0:
                            break

                    self._wait_event.wait(self.delay_between_groups)
                    if self._dialog_state_mgr.is_random_trailers_play_state(
                            DialogState.USER_REQUESTED_EXIT):
                        break
                    if self._dialog_state_mgr.is_random_trailers_play_state(DialogState.NORMAL):
                        # Wake up and resume playing trailers early
                        pass
                    self._dialog_state_mgr.set_random_trailers_play_state(DialogState.NORMAL)

                elif self._dialog_state_mgr.is_random_trailers_play_state(DialogState.QUOTA_REACHED):
                    break

        except AbortException:
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz._logger.debug_verbose('Received abort')

        except Exception as e:
            clz._logger.exception('')
        finally:
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(
                    'About to close TrailerDialog')

            clz._logger.debug_extra_verbose(f'Canceling Trailer Dialog to exit'
                                           f' randomtrailers',
                                           trace=Trace.TRACE_UI_CONTROLLER)
            TrailerStatus.cancel_movie_timer(usage=f'Canceling Trailer Dialog to exit '
                                                   f'randomtrailers')
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose('Closed TrailerDialog')
            self.shutdown()
            return  # Exit thread

    def play_a_group_of_trailers(self) -> None:
        """
            Main Loop to get and display Trailer Information and Trailers

        :return:
        """
        clz = type(self)
        TrailerStatus.opaque()

        number_of_trailers_played = 0
        try:
            # Main movie playing loop

            self._logger.debug('In play_a_group_of_trilers')
            TaskLoop.start_playing_trailers()
            self._logger.debug('Returned from TaskLoop.start_playing_trailers')
            Monitor.throw_exception_if_abort_requested()

            ##############################################
            #
            # End of while loop. Exiting this method
            #
            ##############################################

            if self._movie is None:
                clz._logger.error('There will be no trailers to play')
                msg: str = Messages.get_msg(Messages.NO_TRAILERS_TO_PLAY)
                NotificationTimer.add_notification(msg=msg)
                self._dialog_state_mgr.set_random_trailers_play_state(DialogState.NO_TRAILERS_TO_PLAY)
            else:
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                        'out of inner play loop movie:',
                        self._movie.get_title())

            if Settings.get_show_curtains():
                self._movie_manager.queue_curtain(MovieManager.CLOSE_CURTAIN)

                _, curtain = self._movie_manager.get_next_trailer()
                TrailerStatus.set_show_curtain()

                self.get_player().play_trailer(curtain.get_trailer_path(),
                                               curtain)
                if not self.get_player().wait_for_is_playing_video(
                        path=curtain.get_trailer_path(),
                        timeout=5.0):
                    if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                        clz._logger.debug_extra_verbose(
                            'Timed out Waiting for Player.',
                            trace=Trace.TRACE_UI_CONTROLLER)
                self.get_player().wait_for_is_not_playing_video()
                TrailerStatus.opaque()

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(
                    'Completed everything except play_movie, if there is one')
        except AbortException:
            reraise(*sys.exc_info())
        except Exception as e:
            clz._logger.exception('')

        try:
            if self._movie is not None:
                if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                    clz._logger.debug_extra_verbose(
                        'Checking to see if there is a movie to play:',
                        self._movie.get_title())
            if self._dialog_state_mgr.is_random_trailers_play_state(DialogState.START_MOVIE_AND_EXIT,
                                                  exact_match=True):
                if clz._logger.isEnabledFor(LazyLogger.DEBUG):
                    clz._logger.debug_extra_verbose(
                        'about to play movie:', self._queued_movie)
                TrailerStatus.opaque()
                self.play_movie(self._queued_movie)

        except AbortException:
            clz._logger.debug('Received shutdown or abort')
        except Exception as e:
            clz._logger.exception('')

    def get_player(self) -> MyPlayer:
        return self._player_container.get_player()

    '''
    def show_movie_info(self,
                        show_detail_info: bool = False,
                        block: bool = False) -> None:
        """

        :param block:
        :param show_detail_info:
        """
        clz = type(self)
        if show_detail_info:
            self.show_detailed_info(block=block)
        else:
            MovieTimer.cancel_movie_timer(usage=f'hide_detail')
        #
        # You can have both showMovieDetails (movie details screen
        # shown prior to playing movie) as well as the
        # simple VideoOverlayTitle while the movie is playing.
        #

        MovieTimer.display_trailer()
    '''
    '''
    def show_detailed_info(self, from_user_request: bool = False,
                           block: bool = False) -> None:
        """

        :param block:
        :param from_user_request:
        """
        clz = type(self)

        if self._source != MovieField.FOLDER_SOURCE:
            if (clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)
                    and clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE)):
                clz._logger.debug(f'about to show_detailed_info: from_user_request: '
                                 f'{from_user_request}')
            display_seconds = Settings.get_time_to_display_detail_info()
            if from_user_request:
                # User must perform some action to unblock
                display_seconds = 60 * 60 * 24 * 365  # One year

            if self.get_player() is not None and self.get_player().isPlaying(): # fpf
                # Pause playing trailer
                clz._logger.debug(f'Pausing Player', trace=Trace.TRACE_UI_CONTROLLER)
                self.get_player().pause_play()

            self._show_detail_info(self._movie, display_seconds,
                                   block=block)

        #  TODO: Add msg if folder source
    
    def _show_detail_info(self, movie: AbstractMovie,
                          display_seconds: int = 0,
                          block: bool = False) -> None:
        """
        Shows the already updated detail view.

        Primarily called from the thread which plays trailers. In this case,
        after making the detail view visibile, this method blocks for display_seconds
        (or an action cancels).

        This method can also be called as the result of an action from the gui
        thread. In this case, display_seconds is 0 and no blocking occurs after
        making the detail view visible. It is up to some other action (or event)
        to change the visibility.

        :param movie:
        :param display_seconds:
        :return: unique identifier for the created movie_timer
        """
        clz = type(self)

        # TFH tend to have a LOT of boilerplate after the movie specific info

        if isinstance(movie, TFHMovie):
            scroll_plot = False
        else:
            scroll_plot = True

        TrailerStatus.set_show_details(scroll_plot=scroll_plot)

        # Wait for kodi player to say that it is paused and then the title

        # Monitor.wait_for_abort(3.0)
        self.voice_detail_view()

        Monitor.throw_exception_if_abort_requested()
        MovieTimer.display_movie_info(
            max_display_time=display_seconds, play_trailer=False,
            block=block)
        if block:
            Monitor.throw_exception_if_abort_requested()

        # Force speech to stop
        # text_to_speech.stop()
        return
    '''

    def update_detail_view(self, movie: AbstractMovie) -> None:
        """

        :return:
        """
        clz = type(self)
        self._movie = movie
        try:
            Monitor.throw_exception_if_abort_requested()
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.enter()

            control: Union[ControlImage, Control] = self.getControl(38002)
            thumbnail = self._movie.get_thumbnail()
            if thumbnail is None:
                control.setVisible(False)
            else:
                control.setImage(thumbnail)
                control.setVisible(True)

            control: Union[ControlImage, Control] = self.getControl(38004)
            image = self._movie.get_fanart()
            if image is None:
                control.setVisible(False)
            else:
                control.setVisible(True)
                control.setImage(self._movie.get_fanart())

            verbose = False
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                verbose = True
            title_string = self.get_title_string(self._movie, verbose)

            control_id: ControlId
            for control_id in (ControlId.PLAYING_TITLE, ControlId.DETAIL_TITLE):
                # control_id: int = control_id.get_control_id()
                title_control: Union[ControlLabel,
                                     Control] = control_id.get_label_control() # self.getControl(control_id)
                title_control.setLabel(title_string)

            # title.setAnimations(
            #    [('Hidden', 'effect=fade end=0 time=1000')])

            control: Union[ControlLabel, Control] = ControlId.DIRECTOR_LABEL.get_label_control()
            control.setLabel(self.bold(Messages.get_msg(Messages.DIRECTOR_LABEL)))
            control.setVisible(True)

            control: Union[ControlLabel, Control] = self.getControl(38005)
            movie_directors: List[str] = self._movie.get_directors()
            if movie_directors is None:
                control.setVisible(False)
            else:
                control.setLabel(', '.join(movie_directors))
                control.setVisible(True)

            control: Union[ControlLabel, Control] = self.getControl(38026)
            control.setLabel(self.bold(Messages.get_msg(Messages.WRITER_LABEL)))
            control.setVisible(True)

            control: Union[ControlLabel, Control] = self.getControl(38027)
            control.setLabel(self.bold(Messages.get_msg(Messages.STARS_LABEL)))
            control.setVisible(True)

            movie_actors: List[str] = self._movie.get_actors()
            control: Union[ControlLabel, Control] = self.getControl(38006)
            control.setLabel(', '.join(movie_actors))
            control.setVisible(True)

            control: Union[ControlLabel, Control] = self.getControl(38007)
            movie_writers = ', '.join(self._movie.get_writers())
            if movie_writers is None:
                control.setVisible(False)
            else:
                control.setLabel(movie_writers)
                control.setVisible(True)

            control: Union[ControlTextBox, Control] = self.getControl(38009)
            plot: str = self._movie.get_plot()
            if plot is None:
                plot = ''

            cleaned_plot = plot
            if isinstance(self._movie, TFHMovie):
                '''
                patterns = [
                    r'\n ?\n.*',
                    # r'\nA(nd, a)?s always, find more great cinematic classics at
                    # http://www.trailersfromhell.com',
                    # r'\n \nAnd, as always, find more cinematic greatness at
                    # http://www.trailersfromhell.com',
                    # r'\n \nAs always, you can find more commentary, more reviews,
                    # more podcasts, and more deep-dives into the films you don\'t know
                    # you love yet over on the Trailers From Hell mothership:',
                    r'Like us on Facebook.*',
                    r'http://www.trailersfromhell.com.*',
                    r'ABOUT TRAILERS FROM HELL:.*',
                    r'As always, you can find more commentary.*',
                    r'But wait! There\'s more! TFH.*',
                    r'Want more TFH.*',
                    r'Want to know more? The TFH.*',
                    r'DID YOU KNOW: we have a podcast.*'
                ]

                # Remove all patterns
                # for pattern in patterns:
                #     cleaned_plot = re.sub(pattern, r'', cleaned_plot)
                '''
                cleaned_plot = re.sub(TrailerDialog.TFH_JUNK_PATTERN,
                                      r'', cleaned_plot)

                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose('Plot original text:', plot)
                    clz._logger.debug_extra_verbose('Plot text:', cleaned_plot)

                    cleaned_plot += '\n=======Original Text===========\n' + plot

            if cleaned_plot is None:
                control.setVisible(False)
            else:
                control.setText(cleaned_plot)
                control.setVisible(True)

            control: Union[ControlLabel, Control] = self.getControl(38010)
            movie_studios = ', '.join(self._movie.get_studios())
            if movie_studios is None:
                control.setVisible(False)
            else:
                control.setLabel(movie_studios)
                control.setVisible(True)

            label = Messages.get_formatted_msg(Messages.RUNTIME_GENRE,
                                               self._movie.get_detail_runtime(),
                                               self._movie.get_detail_genres())
            control: Union[ControlLabel, Control] = self.getControl(38011)
            control.setLabel(label)

            image = 'stars/{:.1f}.png'.format(
                self._movie.get_rating())
            rating_control: Union[ControlImage,
                                  Control] = self.getControl(38012)
            rating_control.setImage(image)
            rating_control.setColorDiffuse('0xC0FFD700')

            control: Union[ControlImage, Control] = self.getControl(38013)
            certification_image_path = self._movie.get_certification_image_path()
            if certification_image_path is None:
                control.setVisible(False)
            else:
                certification_image_path = f'ratings/{certification_image_path}.png'
                control.setImage(certification_image_path)
                control.setVisible(True)

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.exit()

        except AbortException:
            raise sys.exc_info()
        except Exception as e:
            clz._logger.exception('')
        finally:
            pass

    def set_visibility(self, visible: bool, field: ControlId ) -> None:
        control_id: int = field.get_control_id()
        control: Union[ControlLabel, Control] = self.getControl(control_id)
        control.setVisible(visible)
        if self._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            self._logger.debug_extra_verbose(f'Setting Field: {field} visible: {visible}')

    def voice_detail_view(self) -> None:
        """

        :return:
        """
        clz = type(self)
        try:
            Monitor.throw_exception_if_abort_requested()
            if self._logger.isEnabledFor(LazyLogger.DEBUG):
                clz._logger.enter()

            title_label = Messages.get_formatted_msg(Messages.TITLE_LABEL)
            text_to_speech.say_text(title_label, interrupt=True)

            title_string = self.get_title_string(self._movie)
            text_to_speech.say_text(title_string, interrupt=False)

            rating: float = self._movie.get_rating()

            # convert to scale of 5 instead of 10, Round to nearest 0.5

            rating = int(rating * 10) / 20.0

            # "Rated 4.5 out of 5 stars"
            text_to_speech.say_text(
                Messages.get_formatted_msg(Messages.VOICED_STARS, str(rating)))

            # MPAA rating
            certification = self._movie.get_detail_certification()
            text_to_speech.say_text(
                Messages.get_formatted_msg(
                    Messages.VOICED_CERTIFICATION, certification))

            runtime_genres = Messages.get_formatted_msg(
                Messages.RUNTIME_GENRE,
                self._movie.get_detail_runtime(),
                self._movie.get_detail_genres())
            text_to_speech.say_text(runtime_genres, interrupt=False)

            director_label = \
                Messages.get_formatted_msg(Messages.DIRECTOR_LABEL)
            text_to_speech.say_text(director_label, interrupt=False)

            # When TTS uses cached speech files, say the Directors one at a time
            # to reduce cached messages

            for director in self._movie.get_voiced_directors():
                text_to_speech.say_text(director, interrupt=False)

            writer_label = \
                Messages.get_formatted_msg(Messages.WRITER_LABEL)
            text_to_speech.say_text(writer_label, interrupt=False)

            # When TTS uses cached speech files, say the writers one at a time
            # to reduce cached messages

            for writer in self._movie.get_voiced_detail_writers():
                text_to_speech.say_text(writer, interrupt=False)

            stars_label = \
                Messages.get_formatted_msg(Messages.STARS_LABEL)
            text_to_speech.say_text(stars_label, interrupt=False)

            # When TTS uses cached speech files, say the Actors one at a time
            # to reduce cached messages

            for actor in self._movie.get_voiced_actors():
                text_to_speech.say_text(actor)

            plot_label = Messages.get_formatted_msg(Messages.PLOT_LABEL)
            text_to_speech.say_text(plot_label, interrupt=False)

            plot: str = self._movie.get_plot()
            if plot is None:
                plot = ''

            cleaned_plot = plot
            if isinstance(self._movie, TFHMovie):
                patterns = [
                    r'\n ?\n.*',
                    # r'\nA(nd, a)?s always, find more great cinematic classics at
                    # http://www.trailersfromhell.com',
                    # r'\n \nAnd, as always, find more cinematic greatness at
                    # http://www.trailersfromhell.com',
                    # r'\n \nAs always, you can find more commentary, more reviews,
                    # more podcasts, and more deep-dives into the films you don\'t know
                    # you love yet over on the Trailers From Hell mothership:',
                    r'Like us on Facebook.*',
                    r'http://www.trailersfromhell.com.*',
                    r'ABOUT TRAILERS FROM HELL:.*',
                    r'As always, you can find more commentary.*',
                    r'But wait! There\'s more! TFH.*',
                    r'Want more TFH.*',
                    r'Want to know more? The TFH.*',
                    r'DID YOU KNOW: we have a podcast.*'
                ]

                # Remove all patterns
                # for pattern in patterns:
                #     cleaned_plot = re.sub(pattern, r'', cleaned_plot)
                cleaned_plot = re.sub(TrailerDialog.TFH_JUNK_PATTERN,
                                      r'', cleaned_plot)

            # self._logger.debug('Plot original text:', plot)
            # self._logger.debug('Plot text:', cleaned_plot)
            text_to_speech.say_text(cleaned_plot, interrupt=False)

            # When TTS uses cached speech files, say the Studios one at a time
            # to reduce cached messages

            for studio in self._movie.get_voiced_studios():
                text_to_speech.say_text(studio, interrupt=False)

        except AbortException:
            raise sys.exc_info()
        except Exception as e:
            clz._logger.exception('')
        finally:
            pass

    def doModal(self) -> bool:
        """

        :return:
        """
        clz = type(self)

        super().doModal()
        return self.exiting_playing_movie

    def show(self) -> None:
        """

        :return:
        """
        super().show()

    def close(self) -> None:
        """

        :return:
        """
        super().close()

    def exit_screensaver_to_play_movie(self) -> None:
        """

        :return:
        """
        clz = type(self)

        self._dialog_state_mgr.set_random_trailers_play_state(DialogState.SHUTDOWN_CUSTOM_PLAYER)

        black_background = BlackBackground.get_instance()
        if black_background is not None:
            black_background.set_visibility(opaque=True)
            black_background.close()
            del black_background
            black_background = None

        self.exiting_playing_movie = True
        self.close()
        xbmc.executebuiltin('Action(FullScreen,12005)')

    def on_abort_event(self) -> None:
        """

        :return:
        """
        clz = type(self)

        clz._logger.enter()
        # Only do this for abort, since both events should not be set at same time
        MovieTimer.cancel_movie_timer(usage='aborting')  # Unblock waits
        self._dialog_state_mgr.set_random_trailers_play_state(DialogState.SHUTDOWN)
        self._wait_event.set(ReasonEvent.SHUTDOWN)

    def do_next_movie(self) -> None:
        """
            Cause the next trailer to be played by:
                - Waking up the main "show details and trailer" loop, if
                  idle
                - Stop displaying any currently displayed movie details
                - Stop playing any currently playing trailer
            Above will allow main "show details and trailer" loop to advance
            to next trailer.
        :return:
        """
        clz = type(self)
        clz._logger.enter()

        # If idle due to wait between movie groups, then interrupt
        # and play next movie.

        if self._dialog_state_mgr.is_random_trailers_play_state(DialogState.GROUP_QUOTA_REACHED,
                                              exact_match=True):
            # Wake up wait in between groups
            self._dialog_state_mgr.set_random_trailers_play_state(DialogState.NORMAL)

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose(f'About to play next trailer: will '
                                           f'hide_detail and stop player')
        MovieTimer.cancel_movie_timer(usage=f'From do_next_movie')
        if self.get_player() is not None:
            self.get_player().stop()
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('Finished playing movie',
                                           trace=Trace.TRACE_SCREENSAVER)

    def getFocus(self) -> None:
        """

        :return:
        """
        clz = type(self)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG):
            clz._logger.debug('Do not use.')
        return

    def onAction(self, action: xbmcgui.Action) -> None:
        """

        :param action:
        :return:

            SHOW_INFO -> Toggle Display custom InfoDialog

            STOP -> Skip to next movie
            ACTION_MOVE_RIGHT -> Skip to next movie

            ACTION_MOVE_LEFT -> Play previous movie

            PREVIOUS_MENU | NAV_BACK | ACTION_BUILT_IN_FUNCTION ->
                                                 Exit Random Trailer script
                or stop Screensaver

            PAUSE -> Toggle Play/Pause playing movie
            PLAY -> Toggle Play/Pause playing movie

            ENTER -> Play movie for current movie (if available)

            REMOTE_0 .. REMOTE_9 -> Record playing movie info to
                        userdata/addon_data/script.video.randomtrailers/<playlist<n>

            ACTION_QUEUE_ITEM -> Add movie to Couch Potato
        """
        clz = type(self)
        action_id: int = action.getId()
        key: str = 'key not set'  # Debug use only

        # Grab handle to movie, it might go away.

        movie: AbstractMovie = self._movie
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            if action_id not in(100, 107):  # Mouse Move
                clz._logger.debug_extra_verbose('Action.id:', action_id,
                                               hex(action_id),
                                               'Action.button_code:',
                                               action.getButtonCode(),
                                               hex(action.getButtonCode()),
                                               trace=Trace.TRACE)

                action_mapper: Action = Action.get_instance()
                matches: List[str] = action_mapper.getKeyIDInfo(action)

                # Mouse Move
                if clz._logger.isEnabledFor(LazyLogger.DISABLED):
                    if action_id not in (100,107):
                        for line in matches:
                            clz._logger.debug_extra_verbose(line)

                button_code: int = action.getButtonCode()

                # These return empty string if not found
                action_key: str = action_mapper.getActionIDInfo(action)
                remote_button: str = action_mapper.getRemoteKeyButtonInfo(action)
                remote_key_id: str = action_mapper.getRemoteKeyIDInfo(action)

                # Returns found button_code, or 'key_' +  action_button
                action_button = action_mapper.getButtonCodeId(action)

                separator: str = ''
                key: str = ''
                if action_key != '':
                    key = action_key
                    separator = ', '
                if remote_button != '':
                    key = key + separator + remote_button
                    separator = ', '
                if remote_key_id != '':
                    key = key + separator + remote_key_id
                if key == '':
                    key = action_button
                clz._logger.debug_extra_verbose(f'Key found: {key}')

        #################################################################
        #   ACTIONS
        ##################################################################
        #    DEBUG thread dump
        #################################################################

        if (clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE)
                and (action_id == xbmcgui.ACTION_PAGE_UP
                     or action_id == xbmcgui.ACTION_MOVE_UP)):

            from common.debug_utils import Debug
            Debug.dump_all_threads()

        ################################################################
        #
        #  SHOW_INFO
        ################################################################

        if action_id == xbmcgui.ACTION_SHOW_INFO:
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose('Toggle Show_Info',
                                                trace=Trace.TRACE_UI_CONTROLLER)

            if not self._dialog_state_mgr.is_random_trailers_play_state(DialogState.NORMAL):
                message = Messages.get_msg(Messages.PLAYER_IDLE)
                TaskLoop.add_task(Task.NOTIFY, msg=message)

            elif self.getControl(ControlId.SHOW_DETAILS.get_control_id()).isVisible():
                MovieTimer.cancel_movie_timer(usage='SHOW_INFO, play trailer')
                TaskLoop.add_task(Task.RESUME_PLAY)
            else:
                clz._logger.debug(f'calling show_detailed_info',
                                  trace=Trace.TRACE_UI_CONTROLLER)
                TaskLoop.add_task(Task.SHOW_DETAILS_USER_REQUEST)

        ##################################################################
        elif (action_id == xbmcgui.ACTION_STOP
              or action_id == xbmcgui.ACTION_MOVE_RIGHT):
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(
                    key, 'Play next trailer at user\'s request',
                    trace=Trace.TRACE_UI_CONTROLLER)

            # do_play_next_thread = threading.Thread(target=self.do_play_next,
            #                                        name='do_play_next')
            # do_play_next_thread.start()

            # Tell movie manager to return next-trailer, err, next

            TaskLoop.add_task(Task.QUEUE_NEXT_TRAILER, Task.GET_TRAILER,
                              Task.SHOW_DETAILS)
            # self._movie_manager.queue_next_trailer()

            # Skip playing current trailer, if it hasn't already started playing
            # self.set_random_trailers_play_state(DialogState.SKIP_PLAYING_TRAILER)

            #
            # Cancel any: display of movie details, stop playing of any
            # playing trailer. This will allow main loop to start on next
            # trailer (which will first display details, then trailer).

            # self.do_next_movie()

        ##################################################################

        elif action_id == xbmcgui.ACTION_MOVE_LEFT:
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(key,
                                                'Play previous trailer at user\'s request',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            has_previous_trailer: bool = HistoryList.has_previous_trailer()
            if has_previous_trailer:
                TaskLoop.add_task(Task.QUEUE_PREV_TRAILER, Task.GET_TRAILER,
                                  Task.SHOW_DETAILS)
            else:
                msg = Messages.get_msg(Messages.NO_MORE_MOVIE_HISTORY)
                NotificationTimer.add_notification(msg)

            # do_play_previous_thread = threading.Thread(target=self.do_play_previous,
            #                                           name='do_play_previous')
            # do_play_previous_thread.start()

            '''
            if not HistoryList.has_previous_trailer():
                msg = Messages.get_msg(
                    Messages.NO_MORE_MOVIE_HISTORY)
                NotificationTimer.add_notification(msg=msg, block=True)
            else:
                NotificationTimer.clear()
                self._movie_manager.queue_previous_trailer()
                DialogStateMgr.set_random_trailers_play_state(
                    DialogState.SKIP_PLAYING_TRAILER)
                self.do_next_movie()
        '''
        ##################################################################
        #
        # PAUSE/PLAY is handled by native player, however, if Movie Details
        # showing due to SHOW_INFO, then switch back to player view
        #
        elif action_id == xbmcgui.ACTION_PAUSE:
            # do_pause_thread = threading.Thread(target=self.do_pause,
            #                                   name='do_pause')
            # do_pause_thread.start()
            '''
            if self.getControl(TrailerDialog.DETAIL_GROUP_CONTROL).isVisible():
                clz._logger.debug('DETAIL_GROUP_CONTROL is visible',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                MovieTimer.cancel_movie_timer(usage=f'hide_detail')
                clz._logger.debug(f'back from hide_detail_view',
                                 trace=Trace.TRACE_UI_CONTROLLER)
                TrailerStatus.set_show_trailer()
            '''
            TaskLoop.add_task(Task.PAUSE_PLAY_MOVIE)

        #################################################################
        #
        # QUEUE to Couch Potato
        #
        elif action_id == xbmcgui.ACTION_QUEUE_ITEM:

            do_couch_thread = threading.Thread(target=self.do_couch,
                                               name='do_couch')
            do_couch_thread.start()
            '''
            if Utils.is_couch_potato_installed() and movie is not None:
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(
                        key, 'Queue to couch potato',
                        trace=Trace.TRACE_UI_CONTROLLER)
                str_couch_potato = Constants.COUCH_POTATO_URL + \
                                        f'?title={movie.get_title()}'
                xbmc.executebuiltin('RunPlugin({str_couch_potato})')
                '''
        ##################################################################
        elif (action_id == xbmcgui.ACTION_PREVIOUS_MENU
              or action_id == xbmcgui.ACTION_NAV_BACK):
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose('Exit application',
                                                trace=Trace.TRACE_UI_CONTROLLER)
            TaskLoop.add_task(Task.EXIT)

            '''
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose('Exit application',
                                               trace=Trace.TRACE_SCREENSAVER)
                clz._logger.debug_extra_verbose(
                    key, 'Exiting RandomTrailers at user request')

            # Ensure we are not blocked

            self.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)
            MovieTimer.cancel_movie_timer(usage=f'hide_detail')
            '''

    ##################################################################

        # TODO: Need proper handling of this (and other inputs that we don't
        # handle). Sigh

        elif action_id == xbmcgui.ACTION_BUILT_IN_FUNCTION:

            if clz._logger.isEnabledFor(LazyLogger.DEBUG_VERBOSE):
                clz._logger.debug_verbose(key, 'Exiting RandomTrailers due to',
                                         'ACTION_BUILT_IN_FUNCTION',
                                         trace=Trace.TRACE_UI_CONTROLLER)
            do_exit_thread = threading.Thread(target=self.do_exit,
                                              name='do_exit')
            do_exit_thread.start()
            '''
            # Ensure we are not blocked

            self.set_random_trailers_play_state(
                DialogState.USER_REQUESTED_EXIT)
            MovieTimer.cancel_movie_timer(usage=f'hide_detail')
            '''

        ##################################################################
        elif (action_id == xbmcgui.ACTION_ENTER
              or action_id == xbmcgui.ACTION_SELECT_ITEM
              or action_id == xbmcgui.ACTION_SHOW_GUI) and movie is not None:

            TaskLoop.add_task(Task.PLAY_MOVIE)

            '''
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(key, 'Play Movie')
            movie_file = movie.get_movie_path()
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(
                    'Playing movie for currently playing trailer.',
                    'movie_file:', movie_file, 'source:',
                    self._movie.get_source())
            if movie_file == '':
                message = Messages.get_msg(Messages.NO_MOVIE_TO_PLAY)
                NotificationTimer.add_notification(msg=message)
            elif not self.is_random_trailers_play_state(DialogState.NORMAL):
                message = Messages.get_msg(Messages.PLAYER_IDLE)
                NotificationTimer.add_notification(msg=message)
            else:
                self.queue_movie(movie)
            '''

        ##################################################################
        # From IR remote as well as keyboard
        # Close InfoDialog and resume playing movie

        elif action_id in TrailerDialog._playlist_map and movie is not None:
            playlist_number: int = TrailerDialog._playlist_map[action_id]
            TaskLoop.add_task(Task.ADD_TO_PLAYLIST,
                              playlist_number=playlist_number)

            # do_add_to_playlist_thread = threading.Thread(target=self.do_add_to_playlist,
            #                                              name='do_add_to_playlist',
            #                                              kwargs={'playlist_number':
            #                                                      playlist_number})
            # do_add_to_playlist_thread.start()

            '''
            movie_path: str = movie.get_movie_path()
            if movie_path == '' or not os.path.exists(movie_path):
                message = Messages.get_msg(Messages.NO_MOVIE_TO_PLAY)
                NotificationTimer.add_notification(msg=message)
            else:
                if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                    clz._logger.debug_extra_verbose(key)
                self.add_to_playlist(action_id, movie)
            '''

    def is_movie_details_visible(self) -> bool:
        return self.getControl(ControlId.SHOW_DETAILS.get_control_id()).isVisible()

    def is_trailer_visible(self) -> bool:
        return self.getControl(ControlId.SHOW_TRAILER_TITLE.get_control_id()).isVisible()

    def do_pause(self):
        clz = type(self)
        if self.getControl(ControlId.SHOW_DETAILS.get_control_id()).isVisible():
            clz._logger.debug('SHOW_DETAILS is visible',
                             trace=Trace.TRACE_UI_CONTROLLER)
            MovieTimer.cancel_movie_timer(usage=f'from do_pause')
            clz._logger.debug(f'back from hide_detail_view',
                             trace=Trace.TRACE_UI_CONTROLLER)
            TrailerStatus.set_show_trailer()

    def do_couch(self):
        clz = type(self)
        if Utils.is_couch_potato_installed() and self._movie is not None:
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(
                   'Queue to couch potato',
                    trace=Trace.TRACE_UI_CONTROLLER)
            str_couch_potato = Constants.COUCH_POTATO_URL + \
                               f'?title={self._movie.get_title()}'
            xbmc.executebuiltin('RunPlugin({str_couch_potato})')

    def do_exit(self):
        clz = type(self)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('Exit application',
                                           trace=Trace.TRACE_UI_CONTROLLER)
            clz._logger.debug_extra_verbose('Exiting RandomTrailers at user request')

            # Ensure we are not blocked

        self._dialog_state_mgr.set_random_trailers_play_state(
            DialogState.USER_REQUESTED_EXIT)
        MovieTimer.cancel_movie_timer(usage=f'Exiting RandomTrailers at user request')

    def do_play_movie(self):
        clz = type(self)
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('Play Movie',
                                           trace=Trace.TRACE_UI_CONTROLLER)
        movie_file = self._movie.get_movie_path()
        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose(
                'Playing movie for currently playing trailer.',
                'movie_file:', movie_file, 'source:',
                self._movie.get_source(),
                trace=Trace.TRACE_UI_CONTROLLER)
        if movie_file == '':
            message = Messages.get_msg(Messages.NO_MOVIE_TO_PLAY)
            NotificationTimer.add_notification(msg=message)
        elif not self._dialog_state_mgr.is_random_trailers_play_state(DialogState.NORMAL):
            message = Messages.get_msg(Messages.PLAYER_IDLE)
            NotificationTimer.add_notification(msg=message)
        else:
            self.queue_movie(self._movie)

    def set_playing_trailer_title_control(self, text: str = '') -> None:
        """

        :param text:
        :return:
        """
        clz = type(self)

        title_control: xbmcgui.ControlLabel = self.getControl(38021)
        clz._logger.debug(f'Setting title of playing trailer to: {text}')
        if text != '':
            title_control.setLabel(text)
        return

    def update_notification_labels(self, text: str = None) -> None:
        """

        :param text:
        :return:
        """
        clz = type(self)

        notification_control: Union[Control,
                                    ControlLabel] = self.getControl(38023)
        notification_control_2: Union[Control,
                                      ControlLabel] = self.getControl(38024)

        if text is None:
            text = ''
        bold_text = self.bold(text)
        notification_control.setLabel(bold_text)
        notification_control_2.setLabel(bold_text)
        if text != '':
            text_to_speech.say_text(text, interrupt=True)
        return

    '''
    def add_to_playlist(self, playlist_number: int, movie: AbstractMovie) -> None:
        """

        :param action_id:
        :param movie:
        :return:
        """
        clz = type(self)
        playlist_name = Settings.get_playlist_name(playlist_number)
        if playlist_name is None or playlist_name == '':
            clz._logger.error(
                'Invalid playlistId, ignoring request to write to playlist.')
        else:
            added = Playlist.get_playlist(playlist_name, playlist_format=True).\
                add_to_smart_playlist(movie)
            if added:
                message: str = Messages.get_formatted_msg(
                    Messages.MOVIE_ADDED_TO_PLAYLIST, playlist_name)
                NotificationTimer.add_notification(msg=message)
            else:
                message: str = Messages.get_formatted_msg(
                    Messages.MOVIE_ALREADY_ON_PLAYLIST, playlist_name)
                NotificationTimer.add_notification(msg=message)
    '''
    def queue_movie(self, movie: AbstractMovie) -> None:
        """
            At user request, queue movie to be played after canceling play
            of current movie, closing curtain and closing customer Player.

        :param movie:
        :return:
        """
        clz = type(self)

        if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
            clz._logger.debug_extra_verbose('Queuing movie at user request:',
                                           movie.get_title())
        self._queued_movie = movie

    def play_movie(self, movie: AbstractMovie, already_playing: bool = False) -> None:
        """
            At user request, start playing movie on normal xbmc.player, after
            disabling the custom player that we use here.

            When already-playing is True, then the user has externally (JSON-RPC)
            started a movie and we just need to get out of the way.

        :param movie:
        :param already_playing: True when movie externally started and we need
                                to get the heck out of the way
        :return:
        """
        clz = type(self)

        black_background: BlackBackground = BlackBackground.get_instance()
        black_background.set_visibility(opaque=False)
        black_background.close()
        black_background.destroy()
        del black_background

        if not already_playing:
            movie_file = movie.get_movie_path()
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose('Playing movie at user request:',
                                               movie.get_title(),
                                               'path:', movie_file)

            self._dialog_state_mgr.set_random_trailers_play_state(
                DialogState.SHUTDOWN_CUSTOM_PLAYER)
            xbmc.Player().play(movie_file)

        if Monitor.is_abort_requested():
            if clz._logger.isEnabledFor(LazyLogger.DEBUG_EXTRA_VERBOSE):
                clz._logger.debug_extra_verbose(
                    'ABORT requested before playing movie!')
        while not Monitor.wait_for_abort(timeout=0.10):
            # Call xbmc.Player directly to avoid using DummyPlayer
            if xbmc.Player().isPlayingVideo():
                break

        self._dialog_state_mgr.set_random_trailers_play_state(DialogState.STARTED_PLAYING_MOVIE)

        # Time to exit plugin
        Monitor.abort_requested()
        clz._logger.exit('Just started player')

    @classmethod
    def get_dialog(cls) -> ForwardRef('TrailerDialog'):
        return cls._trailer_dialog

    def get_title_string(self, movie: AbstractMovie, verbose: bool = False) -> str:
        """

        :param movie:
        :param verbose:
        :return:
        """
        clz = type(self)
        title = ''
        if movie is None:
            return ''
        try:
            title = movie.get_detail_title()
            if title is None:
                title = movie.get_title()
                clz._logger.error('Missing DETAIL_TITLE:',
                                 Debug.dump_dictionary(movie.get_as_movie_type()))
            if verbose:  # for debugging
                cached = False
                normalized = False
                if movie.has_normalized_trailer():
                    normalized = True
                elif movie.has_cached_trailer():
                    cached = True

                if normalized:
                    title = title + ' Normalized'
                elif cached:
                    title = title + ' Cached'
                else:
                    pass

        except Exception as e:
            clz._logger.exception('')

        return self.bold(title)

    def bold(self, text: str) -> str:
        """

        :return:
        """
        return '[B]' + text + '[/B]'

    def shutdown(self) -> None:
        """
            Orderly stop execution of TrailerDialog.

            Note that this method can be called voluntarily, when the plugin
            decides to exit, as in the case of the configured number of trailers
            has played. OR, can be called by Monitor detecting an
            abort, in which case the shutdown still needs to be orderly, but
            since there are frequent checks for Monitor abort, the
            shutdown is less orderly, since the code is sprinkled with checks.
            In such case, some parts of the plugin can be shutting down already.

        :return:
        """
        clz = type(self)

        clz._logger.enter()
        self.close()
        delete_player = False
        try:
            # if self.is_random_trailers_play_state() >=
            # DialogState.STARTED_PLAYING_MOVIE:
            delete_player = True

        except AbortException:
            delete_player = True
        finally:
            self._player_container.use_dummy_player(delete_player)

        self._title_control = None
        self._source = None
        self._movie = None


TaskLoop.class_init()
