# -*- coding: utf-8 -*-
"""
Created on Feb 28, 2019

@author: fbacher
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from .imports import *
from .constants import Movie

class Messages(object):
    """
    Provides methods, message tags and default messages for accessing translated messages.
    """

    TRAILER_EXCEEDS_MAX_PLAY_TIME = 'This trailer exceeds the maximum play time. Terminating'
    TMDB_LABEL = 'TMDb'  # Offical name
    ITUNES_LABEL = 'iTunes'  # VERIFY
    MISSING_TITLE = 'Missing movie title'
    MISSING_DETAIL = 'Unavailable'
    CAN_NOT_READ_FILE = 'Can not read file: %s'
    CAN_NOT_WRITE_FILE = 'Can not write file: %s'
    NO_TRAILERS_TO_PLAY = 'There are no trailers to play'
    HEADING_INFO = 'Info'
    NO_MOVIE_TO_PLAY = 'There is no movie associated with this trailer to play'
    HEADER_IDLE = 'Idle'
    PLAYER_IDLE = 'Waiting to play next group of trailers'
    UNLIMITED = 'unlimited'
    NO_MORE_MOVIE_HISTORY = 'No previous movie to play'
    PLAYING_PREVIOUS_MOVIE = 'Playing: %s'
    GENRE_LABEL = 'Genre: '
    MINUTES_DETAIL = '{} [B]Minutes[/B] - '
    RUNTIME_GENRE = '{} [B]Genre:[/B] {}'

    GENRE_ACTION = 'Action'
    GENRE_ALEGORY = 'Allegory'
    GENRE_ANTHOLOGY = 'Anthology'
    GENRE_ADVENTURE = 'Adventure'
    GENRE_ANIMATION = 'Animation'
    GENRE_BIOGRAPHY = 'Biography'
    GENRE_BLACK_COMEDY = 'Black Comedy'
    GENRE_CHILDRENS = 'Children\'s'
    GENRE_COMEDY = 'Comedy'
    GENRE_COMEDY_DRAMA = 'Comedy Drama'
    GENRE_CRIME = 'Crime'
    GENRE_DOCUMENTARY = 'Documentary'
    GENRE_DRAMA = 'Drama'
    GENRE_EPIC = 'Epic'
    GENRE_EXPERIMENTAL = 'Experimental'
    GENRE_FAMILY = 'Family'
    GENRE_FANTASY = 'Fantasy'
    GENRE_FILM_NOIR = 'Film Noir'
    GENRE_GAME_SHOW = 'Game Show'
    GENRE_HISTORY = 'History'
    GENRE_HORROR = 'Horror'
    GENRE_MELODRAMA = 'Melodrama'
    GENRE_MUSIC = 'Music'
    GENRE_MUSICAL = 'Musical'
    GENRE_MUSICAL_COMEDY = 'Musical Comedy'
    GENRE_MYSTERY = 'Mystery'
    GENRE_PERFORMANCE = 'Performance'
    GENRE_PRE_CODE = 'Pre-Code'
    GENRE_ROMANCE = 'Romance'
    GENRE_ROMANCE_COMEDY = 'Romance Comedy'
    GENRE_SATIRE = 'Satire'
    GENRE_SCIENCE_FICTION = 'Science Fiction'
    GENRE_SCREWBALL_COMEDY = 'Screwball Comedy'
    GENRE_SWASHBUCKLER = 'Schwashbuckler'
    GENRE_THRILLER = 'Thriller'
    GENRE_TV_MOVIE = 'TV Movie'
    GENRE_VARIETY = 'Variety'
    GENRE_WAR = 'War'
    GENRE_WAR_DOCUMENTARY = 'War Documentary'
    GENRE_WESTERN = 'Western'
    _instance = None

    def __init__(self):
        # type: () -> None
        """

        """
        pass

    @staticmethod
    def get_instance():
        # type: () -> Messages
        """

        :return:
        """
        if Messages._instance is None:
            Messages._instance = Messages()
        return Messages._instance

    def get_msg(self, msg_key):
        # type: (TextType) -> TextType
        """

        :param msg_key:
        :return:
        """
        return msg_key

    def get_formatted_msg(self, msg_key, *args):
        # type: (TextType, Optional[List[TextType]]) -> TextType
        """

        :param msg_key:
        :param args
        :return:
        """
        return msg_key.format(*args)

    def get_formated_title(self, movie):
        # type: (Dict[TextType, TextType]) -> TextType
        """

        :param movie:
        :return:
        """
        trailer_type = movie.get(Movie.TYPE, '')

        year = str(movie.get(Movie.YEAR), '')
        if year != '':
            year = '(' + year + ')'

        # A movie from a remote source (tmdb) may also be in local library.

        sources = movie[Movie.SOURCE]
        if movie[Movie.SOURCE] != Movie.LIBRARY_SOURCE and movie.get(Movie.MOVIEID, None):
            sources += ' / ' + Movie.LIBRARY_SOURCE

        title_string = (movie[Movie.TITLE] + ' ' + year + ' - ' +
                        sources + ' ' + trailer_type)
        return title_string
