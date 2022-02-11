# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""

import queue

from common.imports import *
from common.logger import *
from common.movie import AbstractMovie

from discovery.abstract_movie_data import AbstractMovieData

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class PlayableTrailersContainerInterface:
    """
        Interface with common code for all Trailer Managers

        The common code is primarily responsible for containing the
        various manager's discovered movie/trailer information as
        well as supplying trailers to be played.

        It would probably be better to better to have explicit
        Discovery classes for the various TrailerManager subclasses. The
        interfaces would be largely the same.
    """

    def __init__(self,
                 source: str
                 ) -> None:
        """

        :return:
        """

    @staticmethod
    def get_container(source: str):
        from discovery.playable_trailers_container import PlayableTrailersContainer
        return PlayableTrailersContainer(source)

    def set_movie_data(self, movie_data: AbstractMovieData) -> None:
        """

        :return:
        """
        pass

    def get_movie_data(self) -> AbstractMovieData:
        """

        :return:
        """

        pass

    def stop_thread(self) -> None:
        """
        Stop using this instance

        :return:
        """
        pass

    def destroy(self) -> None:
        """

        Thread clean-up after it has stopped

        :return:
        """
        pass

    def add_to_ready_to_play_queue(self, movie: AbstractMovie) -> None:
        """

        :param movie:
        :return:
        """
        pass

    def get_ready_to_play_queue(self) -> queue.Queue:
        """

        :return:
        """
        pass

    def get_number_of_playable_movies(self) -> int:
        """

        :return:
        """
        pass

    def get_number_of_added_trailers(self) -> int:
        """

        :return:
        """
        pass

    def get_next_movie(self) -> AbstractMovie:
        """

        :return:
        """
        pass

    @classmethod
    def is_any_trailers_available_to_play(cls) -> bool:
        """

        :return:
        """

        return cls._any_trailers_available_to_play.isSet()

    def is_playable_trailers(self) -> bool:
        """

        :return:
        """
        pass

    def get_projected_number_of_trailers(self) -> int:
        """

        :return:
        """
        pass

    #
    #
    def set_starving(self, is_starving) -> None:
        """

        :return:
        """
        #
        # Inform the fetching code that at least one of the queues is out of
        # playable trailers.
        #
        # Since TrailerDialog pre-fetches the next movie to play and because
        # we don't want to force replaying the currently running movie when if
        # we just waited a few seconds we would have more options, we put a delay
        # before passing along the starving message.

        pass

    def starving_check(self) -> None:
        pass

    def is_starving(self) -> bool:
        """

        :return:
        """
        pass

    def set_shuffled(self) -> None:
        pass

    def is_shuffled(self) -> bool:
        pass

    def clear_shuffled(self) -> None:
        pass

    @staticmethod
    def get_instances() -> Dict[str, Any]:
        """

        :return:
        """
        pass

    @staticmethod
    def remove_instance(source: str) -> None:
        """

        :param source:
        :return:
        """
        pass

    def clear(self) -> None:
        pass
