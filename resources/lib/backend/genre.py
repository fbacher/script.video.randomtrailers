'''
Created on Feb 10, 2019

@author: fbacher
'''

from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from builtins import unicode
from multiprocessing.pool import ThreadPool


from common.rt_constants import Constants, Movie, iTunes, GenreConstants
from common.rt_utils import Utils, Playlist
from common.debug_utils import Debug
from common.exceptions import AbortException, ShutdownException
from common.messages import Messages
from common.rt_utils import WatchDog
from common.logger import Trace, Logger

from backend.rating import Rating
from backend import backend_constants
from settings import Settings

import sys
import datetime
import io
import json
import os
import queue
import random
import re
import requests
import resource
import threading
import time
import traceback
#from kodi_six import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin
import xbmcaddon
#import xbmcwsgi
from kodi65 import addon
from kodi65 import utils
import xbmcdrm
import xml.dom.minidom
import string


class GenreEntry(object):
    def __init__(self, genreSearchIds=[], tags=[]):
        if not isinstance(genreSearchIds, list):
            self.genreSearchIds = []
            if genreSearchIds is not None:
                self.genreSearchIds.append(genreSearchIds)
        else:
            self.genreSearchIds = genreSearchIds

        if not isinstance(tags, list):
            self.tags = []
            if tags is not None:
                self.tags.append(tags)
        else:
            self.tags = tags

    def getGenres(self):
        return self.genreSearchIds

    def getTags(self):
        return self.tags


class TMDBGenre(GenreEntry):

    def __init__(self, tmdbSearchId=None, tmdbTags=None):
        super(TMDBGenre, self).__init__(tmdbSearchId, tmdbTags)

    @classmethod
    def _initClass(cls):
        cls.TMDB_Action = TMDBGenre(tmdbSearchId=u'Action')
        cls.TMDB_Adventure = TMDBGenre(u'Adventure)')
        cls.TMDB_Animation = TMDBGenre(u'Animation')
        cls.TMDB_Antholgy = TMDBGenre(tmdbTags=u'anthology')
        cls.TMDB_Biograpy = TMDBGenre(tmdbSearchId=None,
                                      tmdbTags=u'biography')
        cls.TMDB_Comedy = TMDBGenre(u'Comedy')
        cls.TMDB_Crime = TMDBGenre(u'Crime')
        cls.TMDB_Dark_Comedy = TMDBGenre(u'dark comedy')
        cls.TMDB_DOCUMENTARY = TMDBGenre(u'Documentary')
        cls.TMDB_Drama = TMDBGenre(u'Drama')
        cls.TMDB_Epic = TMDBGenre(tmdbSearchId=None,
                                  tmdbTags=u'epic')
        cls.TMDB_Family = TMDBGenre(u'Family')
        cls.TMDB_Fantasy = TMDBGenre(u'Fantasy')
        cls.TMDB_Film_Noir = TMDBGenre(tmdbSearchId=None,
                                       tmdbTags=[u'classic noir',
                                                 u'film noir',
                                                 u'french noir',
                                                 u'brit noir'])
        cls.TMDB_History = TMDBGenre(u'History')
        cls.TMDB_Horror = TMDBGenre(u'Horror')
        cls.TMDB_Melodrama = TMDBGenre(tmdbSearchId=None,
                                       tmdbTags=u'melodrama')
        cls.TMDB_Music = TMDBGenre(u'Music')
        cls.TMDB_Musical = TMDBGenre(tmdbSearchId=None,
                                     tmdbTags=u'musical')
        cls.TMDB_Mystery = TMDBGenre(u'Mystery')
        cls.TMDB_Pre_Code = TMDBGenre(tmdbTags=u'pre-code')

        cls.TMDB_Romance = TMDBGenre(u'Romance')
        cls.TMDB_Romantic_Comedy = TMDBGenre(tmdbSearchId=None,
                                             tmdbTags=u'romantic comedy')
        cls.TMDB_Satire = TMDBGenre(tmdbSearchId=None,
                                    tmdbTags=u'satire')
        cls.TMDB_Science_Fiction = TMDBGenre(u'Science Fiction')
        cls.TMDB_Screwball_Comedy = TMDBGenre(tmdbSearchId=None,
                                              tmdbTags=[u'screwball',
                                                        u'screwball comedy'])
        cls.TMDB_Swashbuckler = TMDBGenre(tmdbSearchId=None,
                                          tmdbTags=u'swashbuckler')
        cls.TMDB_Thriller = TMDBGenre(u'Thriller')
        cls.TMDB_TV_Movie = TMDBGenre(u'TV Movie')
        cls.TMDB_War = TMDBGenre(u'War')
        cls.TMDB_Western = TMDBGenre(u'Western')


TMDBGenre._initClass()

# iTunes has a number of Foreign films that are not english. I don't
# see any language indication, but perhaps we are not doing the
# query correctly.

# TMDB has movies with original_language != English and no
# apparent english tag. Note that details gives spoken_languages


class iTunesGenre(GenreEntry):
    def __init__(self,  iTunesSearchId=None, iTunesKeyword=None):
        super(iTunesGenre, self).__init__(
            iTunesSearchId, iTunesKeyword)

    @classmethod
    def _initClass(cls):
        # Probably incomplete
        cls.iTunes_Action_And_Adventure = iTunesGenre(u'Action and Adventure')
        cls.iTunes_Comedy = iTunesGenre(u'Comedy')
        cls.iTunes_Documentary = iTunesGenre(u'Documentary')
        cls.iTunes_Drama = iTunesGenre(u'Drama')
        cls.iTunes_Family = iTunesGenre(u'Family')
        cls.iTunes_History = iTunesGenre(u'Foreign')
        cls.iTunes_Horror = iTunesGenre(u'Horror')
        cls.iTunes_Romance = iTunesGenre(u'Romance')
        cls.iTunes_Science_Fiction = iTunesGenre(u'Science Fiction')
        cls.iTunes_Thriller = iTunesGenre(u'Thriller')


iTunesGenre._initClass()


class IMDBGenre(GenreEntry):
    def __init__(self,  imdbSearchId=None, imdbKeywords=None):
        super(IMDBGenre, self).__init__(
            imdbSearchId, imdbKeywords)

    @classmethod
    def _initClass(cls):
        '''
        Action     Adventure     Animation     Biography
        Comedy     Crime     Documentary     Drama
        Family     Fantasy     Film-Noir     Game-Show
        History     Horror     Music     Musical
        Mystery     News     Reality-TV     Romance
        Sci-Fi     Sport     Talk-Show     Thriller
        War     Western
        '''

        cls.IMDB_Action = IMDBGenre(u'Action')
        cls.IMDB_Adventure = IMDBGenre(u'Adventure)')
        cls.IMDB_Animation = IMDBGenre(u'Animation')
        cls.IMDB_Biography = IMDBGenre(u'Biography')
        cls.IMDB_Comedy = IMDBGenre(u'Comedy')
        cls.IMDB_Crime = IMDBGenre(u'Crime')
        cls.IMDB_Documentary = IMDBGenre(u'Documentary')
        cls.IMDB_Drama = IMDBGenre(u'Drama')
        cls.IMDB_Family = IMDBGenre(u'Family')
        cls.IMDB_Fantasy = IMDBGenre(u'Fantasy')
        cls.IMDB_Film_Noir = IMDBGenre(u'Film-Noir')
        cls.IMDB_Game_Show = IMDBGenre(u'Game-Show')
        cls.IMDB_History = IMDBGenre(u'History')
        cls.IMDB_Horror = IMDBGenre(u'Horror')
        cls.IMDB_Music = IMDBGenre(u'Music')
        cls.IMDB_Musical = IMDBGenre(u'Musical')
        cls.IMDB_Mystery = IMDBGenre(u'Mystery')
        cls.IMDB_News = IMDBGenre(u'News')
        cls.IMDB_Reality_TV = IMDBGenre(u'Reality-TV')
        cls.IMDB_Romance = IMDBGenre(u'Romance')
        cls.IMDB_Science_Fiction = IMDBGenre(u'Sci-Fi')
        cls.IMDB_Short = IMDBGenre(u'Short')
        cls.IMDB_Sport = IMDBGenre(u'Sport')
        cls.IMDB_Talk_Show = IMDBGenre(u'Talk-Show')
        cls.IMDB_Thriller = IMDBGenre(u'Thriller')
        cls.IMDB_War = IMDBGenre(u'War')
        cls.IMDB_Western = IMDBGenre(u'Western')


IMDBGenre._initClass()


class RandomTrailersGenre:
    def __init__(self, genreId, translatableLabelId, tmdbGenre, iTunesGenre, imdbGenre):
        self._genreId = genreId
        self._translatableLableId = translatableLabelId
        self._tmdbGenre = tmdbGenre
        self._iTunesGenre = iTunesGenre
        self._imdbGenre = imdbGenre
        self._isPreselected = False
        self._isUISelected = False

        '''
            Kodi Genres are created from the scraping process. The genres depend
            upon which site the scraper uses (imdb, tmdb, Rotten Tomatoes, among
            others.
                Action, Adventure, Animation, Biography, Comedy, Crime, Documentary, 
                Drama, Family, Fantasy, Film-Noir, History, Horror, Music, Musical,
                Mystery, Romance, Sci-Fi, Science Fiction, Short, Sport, TV Movie

            Kodi Tags are also created from the scraping process. Some sites 
            may have a specific genre (say, imdb Film-Noir) while others use a tag
            (tmdb film noir). There can be a very large number of tags, many 
            which are rarely used. In addition, tag use is very subjective. At 
            least on TMDB any user who can edit can define new tags. This results
            in misspellings, ('corean war') or language variations (lobor vs labour).
            Further, it is clumsy to see what is
            already defined, so you end up with different users using different
            words for the same thing. Sigh.
            
            TMDB tags of note: classic noir, film noir, french noir, brit noir,
            pre-code, short, anthology, biography, all black cast, epic,
            melodrama, musical,romantic comedy, satire, screwball, screwball comedy,
            swashbuckler, gangster, b movie, world war II, murder, suspense, 
            prison, detective, world war i, love triangle, romance, spy, 
            newspaper, ship, train, nightclub, gambling, hospital, blackmail,
            nurse, boston blackie, broadway, historical figure, nazi, 
            private detetive, amnesia, the falcon, navy, ghost, bulldog drummond,
            philo vance, prostitute, korean war, gold digger, scotland yard,
            cult film, lone wolf, epic, the saint, nazis, the whistler, 
            corruption, organized crime, golddigger, espionage, bootlegger,
            sherlock holmes, 
        '''
    @classmethod
    def _initClass(cls):
        allowedGenres = []
        cls.RANDOM_ACTION = RandomTrailersGenre(GenreConstants.ACTION,
                                                Messages.GENRE_ACTION,
                                                TMDBGenre.TMDB_Action,
                                                iTunesGenre.iTunes_Action_And_Adventure,
                                                IMDBGenre.IMDB_Action)
        allowedGenres.append(cls.RANDOM_ACTION)
        '''
        cls.RANDOM_ALEGORY = RandomTrailersGenre(GenreConstants.ALEGORY,
                                                 Messages.GENRE_ALEGORY,
                                                 None,
                                                 None,
                                                 None)
        allowedGenres.append(cls.RANDOM_ALEGORY)
        '''
        '''
        cls.RANDOM_ANTHOLOGY = RandomTrailersGenre(GenreConstants.ANTHOLOGY,
                                                   Messages.GENRE_ANTHOLOGY,
                                                   None,
                                                   None,
                                                   None)
        allowedGenres.append(cls.RANDOM_ANTHOLOGY)
        '''
        cls.RANDOM_ADVENTURE = RandomTrailersGenre(GenreConstants.ADVENTURE,
                                                   Messages.GENRE_ADVENTURE,
                                                   TMDBGenre.TMDB_Adventure,
                                                   iTunesGenre.iTunes_Action_And_Adventure,
                                                   IMDBGenre.IMDB_Adventure)
        allowedGenres.append(cls.RANDOM_ADVENTURE)
        cls.RANDOM_ANIMATION = RandomTrailersGenre(GenreConstants.ANIMATION,
                                                   Messages.GENRE_ANIMATION,
                                                   TMDBGenre.TMDB_Animation,
                                                   None,
                                                   IMDBGenre.IMDB_Animation)
        allowedGenres.append(cls.RANDOM_ANIMATION)
        cls.RANDOM_BIOGRAPHY = RandomTrailersGenre(GenreConstants.BIOGRAPHY,
                                                   Messages.GENRE_BIOGRAPHY,
                                                   TMDBGenre.TMDB_Biograpy,
                                                   None,
                                                   IMDBGenre.IMDB_Biography)
        allowedGenres.append(cls.RANDOM_BIOGRAPHY)
        cls.RANDOM_BLACK_COMEDY = RandomTrailersGenre(GenreConstants.DARK_COMEDY,
                                                      Messages.GENRE_BLACK_COMEDY,
                                                      TMDBGenre.TMDB_Dark_Comedy,
                                                      None,
                                                      None)
        allowedGenres.append(cls.RANDOM_BLACK_COMEDY)
        '''
        cls.RANDOM_CHILDRENS = RandomTrailersGenre(GenreConstants.CHILDRENS,
                                                   Messages.GENRE_CHILDRENS,
                                                   None,
                                                   None,
                                                   None)
        allowedGenres.append(cls.RANDOM_CHILDRENS)
        '''
        cls.RANDOM_COMEDY = RandomTrailersGenre(GenreConstants.COMEDY,
                                                Messages.GENRE_COMEDY,
                                                TMDBGenre.TMDB_Comedy,
                                                iTunesGenre.iTunes_Comedy,
                                                IMDBGenre.IMDB_Comedy)
        allowedGenres.append(cls.RANDOM_COMEDY)
        cls.RANDOM_CRIME = RandomTrailersGenre(GenreConstants.CRIME,
                                               Messages.GENRE_CRIME,
                                               TMDBGenre.TMDB_Crime,
                                               None,
                                               IMDBGenre.IMDB_Crime)
        allowedGenres.append(cls.RANDOM_CRIME)
        cls.RANDOM_DOCUMENTARY = RandomTrailersGenre(GenreConstants.DOCUMENTARY,
                                                     Messages.GENRE_DOCUMENTARY,
                                                     TMDBGenre.TMDB_DOCUMENTARY,
                                                     iTunesGenre.iTunes_Documentary,
                                                     IMDBGenre.IMDB_Documentary)
        allowedGenres.append(cls.RANDOM_DOCUMENTARY)
        cls.RANDOM_DRAMA = RandomTrailersGenre(GenreConstants.DRAMA,
                                               Messages.GENRE_DRAMA,
                                               TMDBGenre.TMDB_Drama,
                                               iTunesGenre.iTunes_Drama,
                                               IMDBGenre.IMDB_Drama)
        allowedGenres.append(cls.RANDOM_DRAMA)
        cls.RANDOM_EPIC = RandomTrailersGenre(GenreConstants.EPIC,
                                              Messages.GENRE_EPIC,
                                              TMDBGenre.TMDB_Epic,
                                              None,
                                              None)
        allowedGenres.append(cls.RANDOM_EPIC)
        '''
        cls.RANDOM_EXPERIMENTAL = RandomTrailersGenre(GenreConstants.EXPERIMENTAL,
                                                      Messages.GENRE_EXPERIMENTAL,
                                                      None,
                                                      None,
                                                      None)
        allowedGenres.append(cls.RANDOM_EXPERIMENTAL)
        '''
        cls.RANDOM_FAMILY = RandomTrailersGenre(GenreConstants.FAMILY,
                                                Messages.GENRE_FAMILY,
                                                TMDBGenre.TMDB_Family,
                                                iTunesGenre.iTunes_Family,
                                                IMDBGenre.IMDB_Family)
        allowedGenres.append(cls.RANDOM_FAMILY)
        cls.RANDOM_FANTASY = RandomTrailersGenre(GenreConstants.FANTASY,
                                                 Messages.GENRE_FANTASY,
                                                 TMDBGenre.TMDB_Fantasy,
                                                 None,
                                                 IMDBGenre.IMDB_Fantasy)
        allowedGenres.append(cls.RANDOM_FANTASY)
        cls.RANDOM_FILM_NOIR = RandomTrailersGenre(GenreConstants.FILM_NOIR,
                                                   Messages.GENRE_FILM_NOIR,
                                                   TMDBGenre.TMDB_Film_Noir,
                                                   None,
                                                   IMDBGenre.IMDB_Film_Noir)
        allowedGenres.append(cls.RANDOM_FILM_NOIR)
        '''
        cls.RANDOM_GAME_SHOW = RandomTrailersGenre(GenreConstants.GAME_SHOW,
                                                   Messages.GENRE_GAME_SHOW,
                                                   None,
                                                   None,
                                                   IMDBGenre.IMDB_Game_Show)
        allowedGenres.append(cls.RANDOM_GAME_SHOW)
        '''
        cls.RANDOM_HISTORY = RandomTrailersGenre(GenreConstants.HISTORY,
                                                 Messages.GENRE_HISTORY,
                                                 TMDBGenre.TMDB_History,
                                                 iTunesGenre.iTunes_History,
                                                 IMDBGenre.IMDB_History)
        allowedGenres.append(cls.RANDOM_HISTORY)
        cls.RANDOM_HORROR = RandomTrailersGenre(GenreConstants.HORROR,
                                                Messages.GENRE_HORROR,
                                                TMDBGenre.TMDB_Horror,
                                                iTunesGenre.iTunes_Horror,
                                                IMDBGenre.IMDB_Horror)
        allowedGenres.append(cls.RANDOM_HORROR)
        cls.RANDOM_MELODRAMA = RandomTrailersGenre(GenreConstants.MELODRAMA,
                                                   Messages.GENRE_MELODRAMA,
                                                   TMDBGenre.TMDB_Melodrama,
                                                   None,
                                                   None)
        allowedGenres.append(cls.RANDOM_MELODRAMA)
        cls.RANDOM_MUSIC = RandomTrailersGenre(GenreConstants.MUSIC,
                                               Messages.GENRE_MUSIC,
                                               TMDBGenre.TMDB_Music,
                                               None,
                                               IMDBGenre.IMDB_Music)
        allowedGenres.append(cls.RANDOM_MUSIC)
        cls.RANDOM_MUSICAL = RandomTrailersGenre(GenreConstants.MUSICAL,
                                                 Messages.GENRE_MUSICAL,
                                                 TMDBGenre.TMDB_Musical,
                                                 None,
                                                 IMDBGenre.IMDB_Musical)
        allowedGenres.append(cls.RANDOM_MUSICAL)
        '''
        cls.RANDOM_MUSICAL_COMEDY = RandomTrailersGenre(GenreConstants.MUSICAL_COMEDY,
                                                        Messages.GENRE_MUSICAL_COMEDY,
                                                        None,
                                                        None,
                                                        None)
        allowedGenres.append(cls.RANDOM_MUSICAL_COMEDY)
        '''
        cls.RANDOM_MYSTERY = RandomTrailersGenre(GenreConstants.MYSTERY,
                                                 Messages.GENRE_MYSTERY,
                                                 TMDBGenre.TMDB_Mystery,
                                                 None,
                                                 IMDBGenre.IMDB_Mystery)
        allowedGenres.append(cls.RANDOM_MYSTERY)
        # Defined only in AFI
        '''
        cls.RANDOM_PERFORMANCE = RandomTrailersGenre(GenreConstants.PERFORMANCE,
                                                     Messages.GENRE_PERFORMANCE,
                                                     None,
                                                     None,
                                                     None)
        allowedGenres.append(cls.RANDOM_PERFORMANCE)
        '''

        cls.PRE_CODE = RandomTrailersGenre(GenreConstants.PRE_CODE,
                                           Messages.GENRE_PRE_CODE,
                                           TMDBGenre.TMDB_Pre_Code,
                                           None,
                                           None)
        cls.RANDOM_ROMANCE = RandomTrailersGenre(GenreConstants.ROMANCE,
                                                 Messages.GENRE_ROMANCE,
                                                 TMDBGenre.TMDB_Romance,
                                                 iTunesGenre.iTunes_Romance,
                                                 IMDBGenre.IMDB_Romance)
        allowedGenres.append(cls.RANDOM_ROMANCE)
        '''
        cls.RANDOM_ROMANTIC_COMEDY = RandomTrailersGenre(GenreConstants.ROMANTIC_COMEDY,
                                                         Messages.GENRE_ROMANCE_COMEDY,
                                                         TMDBGenre.TMDB_Romantic_Comedy,
                                                         None,
                                                         None)
                                                         
        allowedGenres.append(cls.RANDOM_ROMANTIC_COMEDY)
        '''
        cls.RANDOM_SATIRE = RandomTrailersGenre(GenreConstants.SATIRE,
                                                Messages.GENRE_SATIRE,
                                                TMDBGenre.TMDB_Satire,
                                                None,
                                                None)
        allowedGenres.append(cls.RANDOM_SATIRE)
        cls.RANDOM_SCIENCE_FICTION = RandomTrailersGenre(GenreConstants.SCI_FI,
                                                         Messages.GENRE_SCIENCE_FICTION,
                                                         TMDBGenre.TMDB_Science_Fiction,
                                                         iTunesGenre.iTunes_Science_Fiction,
                                                         IMDBGenre.IMDB_Science_Fiction)
        allowedGenres.append(cls.RANDOM_SCIENCE_FICTION)
        cls.RANDOM_SCREWBALL_COMEDY = RandomTrailersGenre(GenreConstants.SCREWBALL_COMEDY,
                                                          Messages.GENRE_SCREWBALL_COMEDY,
                                                          TMDBGenre.TMDB_Screwball_Comedy,
                                                          None,
                                                          None)
        allowedGenres.append(cls.RANDOM_SCREWBALL_COMEDY)
        cls.RANDOM_SWASHBUCKLER = RandomTrailersGenre(GenreConstants.SWASHBUCKLER,
                                                      Messages.GENRE_SWASHBUCKLER,
                                                      TMDBGenre.TMDB_Swashbuckler,
                                                      None,
                                                      None)
        allowedGenres.append(cls.RANDOM_SWASHBUCKLER)
        cls.RANDOM_THRILLER = RandomTrailersGenre(GenreConstants.THRILLER,
                                                  Messages.GENRE_THRILLER,
                                                  TMDBGenre.TMDB_Thriller,
                                                  iTunesGenre.iTunes_Thriller,
                                                  IMDBGenre.IMDB_Thriller)
        allowedGenres.append(cls.RANDOM_THRILLER)
        cls.RANDOM_TV_MOVIE = RandomTrailersGenre(GenreConstants.TV_MOVIE,
                                                  Messages.GENRE_TV_MOVIE,
                                                  TMDBGenre.TMDB_TV_Movie,
                                                  None,
                                                  None)
        allowedGenres.append(cls.RANDOM_TV_MOVIE)
        # more for TV
        '''
        cls.RANDOM_VARIETY = RandomTrailersGenre(GenreConstants.VARIETY,
                                                 Messages.GENRE_VARIETY,
                                                 None,
                                                 None,
                                                 None)
        allowedGenres.append(cls.RANDOM_VARIETY)
        '''
        cls.RANDOM_WAR = RandomTrailersGenre(GenreConstants.WAR,
                                             Messages.GENRE_WAR,
                                             TMDBGenre.TMDB_War,
                                             None,
                                             IMDBGenre.IMDB_War)
        allowedGenres.append(cls.RANDOM_WAR)
        cls.RANDOM_WAR_DOCUMENTARY = RandomTrailersGenre(GenreConstants.WAR_DOCUMENTARY,
                                                         Messages.GENRE_WAR_DOCUMENTARY,
                                                         None,
                                                         None,
                                                         None)
        allowedGenres.append(cls.RANDOM_WAR_DOCUMENTARY)
        cls.RANDOM_WESTERN = RandomTrailersGenre(GenreConstants.WESTERN,
                                                 Messages.GENRE_WESTERN,
                                                 TMDBGenre.TMDB_Western,
                                                 None,
                                                 IMDBGenre.IMDB_Western)
        allowedGenres.append(cls.RANDOM_WESTERN)

        RandomTrailersGenre.ALLOWED_GENRES = allowedGenres

    def getGenreId(self):
        return self._genreId

    def getLabel(self):
        return Messages.getInstance().getMsg(self._translatableLableId)

    def getTmdbGenre(self):
        return self._tmdbGenre

    def getItunesGenre(self):
        return self._iTunesGenre

    def getImdbGenre(self):
        return self._imdbGenre

    def isPreSelected(self):
        return self._isPreselected

    def isUISelected(self):
        return self._isUISelected

    def isSelected(self):
        return self.isUISelected()

    def uiSelect(self, selection):
        self._isUISelected = selection

    def preSelect(self, selection):
        self.isPreselected = selection

    def resetUISelection(self):
        self._isUISelected = self._isPreSelected

    def appendToQuery(self, query, newQuerySegment):
        separator = u''
        if len(query) > 0 and len(newQuerySegment) > 0:
            separator = u', '

        return query + separator + newQuerySegment

    def getGenres(self, destination):
        #
        # Since Kodi imports from multiple sources, the
        # tags & genres from all of these sources may
        # appear in the database. Take the union of
        # tags/genres.

        genres = []

        if destination == Genre.TMDB_DATABASE or destination == Genre.LOCAL_DATABASE:
            if self.getTmdbGenre() is not None:
                genres.extend(self.getTmdbGenre().getGenres())
        if destination == Genre.ITUNES_DATABASE or destination == Genre.LOCAL_DATABASE:
            if self.getItunesGenre() is not None:
                genres.extend(self.getItunesGenre().getGenres())
        if destination == Genre.IMDB_DATABASE or destination == Genre.LOCAL_DATABASE:
            if self.getImdbGenre() is not None:
                genres.extend(self.getImdbGenre().getGenres())
        # if destination == Genre.ROTTEN_TOMATOES_DATABASE or destination == Genre.LOCAL_DATABASE:
        #    if self.getTomatoesGenre() is not None:
        #        genres.extend(self.getTomatoesGenre().getGenres())

        return genres

    def getTags(self, destination):
        #
        # Since Kodi imports from multiple sources, the
        # tags & genres from all of these sources may
        # appear in the database. Take the union of
        # tags/genres.

        tags = []

        if destination == Genre.TMDB_DATABASE or destination == Genre.LOCAL_DATABASE:
            if self.getTmdbGenre() is not None:
                tags.extend(self.getTmdbGenre().getTags())
        if destination == Genre.ITUNES_DATABASE or destination == Genre.LOCAL_DATABASE:
            if self.getItunesGenre() is not None:
                tags.extend(self.getItunesGenre().getTags())
        if destination == Genre.IMDB_DATABASE or destination == Genre.LOCAL_DATABASE:
            if self.getImdbGenre() is not None:
                tags.extend(self.getImdbGenre().getTags())
        # if destination == Genre.ROTTEN_TOMATOES_DATABASE or destination == Genre.LOCAL_DATABASE:
        #    tags.extend(self.getTomatoesGenre().getTags())

        return tags


RandomTrailersGenre._initClass()


class Genre:

    LOCAL_DATABASE = 0
    TMDB_DATABASE = 1
    ITUNES_DATABASE = 2
    IMDB_DATABASE = 3
    ROTTEN_TOMATOES_DATABASE = 4

    GENRE_ACTION = u'Action and Adventure'
    GENRE_COMEDY = u'Comedy'
    GENRE_DOCUMENTARY = u'Documentary'
    GENRE_DRAMA = u'Drama'
    GENRE_FAMILY = u'Family'
    GENRE_FANTASY = u'Fantasy'
    GENRE_FOREIGN = u'Foreign'
    GENRE_HORROR = u'Horror'
    GENRE_MUSICAL = u'Musical'
    GENRE_ROMANCE = u'Romance'
    GENRE_SCIFI = u'Science Fiction'
    GENRE_THRILLER = u'Thriller'

    '''
         For local Kodi library search, need: TMDB & IMDB genres/keywords
         For TMDB, Apple (RottenTomatoes?)
         lookup, need those genres/keywords as well

        For reference. American Film Institute is not used (TCM uses it)

        AFI
            AFI_Adventure, 
            AFI_Allegory, 
            AFI_Anthology, 
            AFI_Biography, 
            AFI_Black comedy, 
            AFI_Children's works, 
            AFI_Comedy 
            AFI_Comedy-drama, 
            AFI_Documentary, 
            AFI_Drama, 
            AFI_Epic, 
            AFI_Experimental, 
            AFI_Fantasy, 
            AFI_film noir, 
            AFI_Horror, 
            AFI_Melodrama,
            AFI_Musical, 
            AFI_Musical Comedy
            AFI_Mystery, 
            AFI_Performance, 
            AFI_Romance, 
            AFI_Romantic Comedy,
            AFI_Satire, 
            AFI_Science fiction, 
            AFI_Screwball comedy, 
            AFI_Swashbuckler, 
            AFI_Variety, 
            AFI_War documentary,
            AFI_Western

        Rotten Tomatoes: (probably not exhaustive)
            ROTTEN_Action
            ROTTEN_Comedy
            ROTTEN_Comic_Book_Movies
            ROTTEN_Drama
            ROTTEN_Kids/Family
            ROTTEN_Foreign
            ROTTEN_Musical
            ROTTEN_Thriller
            ROTTEN_Animated
            ROTTEN_Documentary
            ROTTEN_Horror
            ROTTEN_Romance
            ROTTEN_Sci-Fi/Fantasy
    '''

    _instance = None

    def __init__(self):
        pass

# TMDB Genres:
# Action, Adventure, Animation, Comedy, Crime, Documentary, Drama, Family, Fantasy,
# History, Horror, Music, Mystery, Romance, Science Fiction, Thriller, TV Movie,
# War, Western
#
# Keywords of interest:
#    pre-code, film noir

# IMDB Genres:
#    Action, Adult, Adventure, Animation, Biography, Comedy, Crime, Documentary,
#    Drama, Family, Fantasy, Film Noir, Game-Show, History, Horror, Musical,
#    Music, Mystery, News, Reality-TV, Romance, Sci-Fi, Short, Sport,
#    Talk-Show, Thriller, War, Western

# AFI Genres:
# Adventure, Allegory, Anthology, Biography, Black comedy, Children's works, Comedy
# Comedy-drama, Documentary, Drama, Epic, Experimental, Fantasy, film noir, Horror, Melodrama,
# Musical, Musical Comedy, Mystery, Performance, Romance, Romantic Comedy,
# Satire, Science fiction, Screwball comedy, Swashbuckler, Variety, War documentary,
# Western

    @staticmethod
    def getInstance():
        if Genre._instance is None:
            Genre._instance = Genre()
        return Genre._instance

    def getAllowedGenres(self):
        allowedGenres = RandomTrailersGenre.ALLOWED_GENRES
        genres = sorted(
            allowedGenres, key=lambda element: element.getLabel())
        return genres

    def resetSelection(self):
        self.selectedGenres = self.getAllGenres()

    def getAllGenres(self):
        pass

    def isFiltered(self):
        for genre in self.getAllowedGenres():
            if genre.isSelected():
                return True

        return False

    def getGenres(self, destination):
        '''
            Return a JSON type query segment appropriate for the
            particular destination (LOCAL_DATABASE, TMDB_DATABASE,
            etc.). Different destinations use different ids for 
            genres. In some cases, tags are used instead of genres,
            so both getGenres and getTags must be done.
        '''
        genres = []
        for genre in self.getAllowedGenres():
            if genre.isSelected():
                genres.extend(genre.getGenres(destination))
        return genres

    def getTags(self, destination):
        '''
            Return a JSON type query segment appropriate for the
            particular destination (LOCAL_DATABASE, TMDB_DATABASE,
            etc.). Different destinations use different ids for 
            genres. In some cases, tags are used instead of genres,
            so both getGenres and getTags must be done.
        '''
        tags = []
        for genre in self.getAllowedGenres():
            if genre.isSelected():
                tags.extend(genre.getTags(destination))
        return tags

    def getEnabledGenres(self):
        enabledGenres = []
        genres = Genre.getInstance().getAllowedGenres()

        for genre in genres:
            if Settings.getGenre(genre.getGenreId()):
                enabledGenres.append(genre)
                genre.uiSelect(True)
                genre.preSelect(True)
            else:
                genre.uiSelect(False)
                genre.preSelect(True)

        return enabledGenres
