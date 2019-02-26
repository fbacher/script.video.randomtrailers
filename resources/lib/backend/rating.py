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
from xml.dom.minidom import Node
from multiprocessing.pool import ThreadPool
from kodi65 import addon
from kodi65 import utils
from common.rt_constants import Constants
from common.rt_constants import Movie
from common.rt_utils import Utils
from common.debug_utils import Debug
from common.rt_utils import Playlist
from common.exceptions import AbortException
from common.rt_utils import WatchDog
from settings import Settings
from common.rt_utils import Trace

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
import xbmcdrm
import string


class Rating:

    RATING_G = u'G'
    RATING_PG = u'PG'
    RATING_PG_13 = u'PG-13'
    RATING_R = u'R'
    RATING_NC_17 = u'NC-17'
    RATING_NR = u'NR'

    def __init__(self, pattern, mpaaRatingLabel):
        self._pattern = pattern
        self._mpaaRatingLabel = mpaaRatingLabel

    @classmethod
    def _initClass(cls):

        Rating.ALLOWED_RATINGS = (

            # General Audience
            Rating(re.compile(u'^A$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^Approved$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^Rating Approved$'), Rating.RATING_G),
            Rating(re.compile(u'^Rated Approved$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^Passed$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^Rated Passed$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^P$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^G$'), Rating.RATING_G),  # Hays
            Rating(re.compile(u'^G .*$'), Rating.RATING_G),
            Rating(re.compile(u'^Rated G.*$'), Rating.RATING_G),
            Rating(re.compile(u'^TV-G.*$'), Rating.RATING_G),
            Rating(re.compile(u'^Rated TV-G.*$'), Rating.RATING_G),
            Rating(re.compile(u'^Rated$'), Rating.RATING_G),  # Hays

            # For young teens

            Rating(re.compile(u'^PG$'), Rating.RATING_PG),
            Rating(re.compile(u'^PG .*$'), Rating.RATING_PG),  # PG with comment
            Rating(re.compile(u'^Rated PG.*$'), Rating.RATING_PG),
            Rating(re.compile(u'^TV-PG.*$'), Rating.RATING_PG),
            Rating(re.compile(u'^Rated TV-PG.*$'), Rating.RATING_PG),

            # For older teens, more mature

            Rating(re.compile(u'^M$'), Rating.RATING_PG_13),  # Early MPAA
            Rating(re.compile(u'^GP$'), Rating.RATING_PG_13),  # Replaced M
            Rating(re.compile(u'^PG-13$'), Rating.RATING_PG_13),  # Replaced M
            # PG-13 with comment
            Rating(re.compile(u'^PG-13 .*$'), Rating.RATING_PG_13),
            Rating(re.compile(u'^Rated PG-13.*$'), Rating.RATING_PG_13),
            # Restricted
            Rating(re.compile(u'^R$'), Rating.RATING_R),
            Rating(re.compile(u'^R .*$'), Rating.RATING_R),  # R with comment
            Rating(re.compile(u'^Rated R.*$'),
                   Rating.RATING_R),  # R with comment
            # Adult
            Rating(re.compile(u'^NC17.*$'), Rating.RATING_NC_17),
            Rating(re.compile(u'^Rated NC17.*$'), Rating.RATING_NC_17),
            Rating(re.compile(u'^X.*$'), Rating.RATING_NC_17),

            Rating(re.compile(u'^NR$'), Rating.RATING_NR),
            Rating(re.compile(u'^Rated NR$'), Rating.RATING_NR),
            Rating(re.compile(u'^Not Rated$'), Rating.RATING_NR),
            Rating(re.compile(u'^Rated Not Rated$'), Rating.RATING_NR),
            Rating(re.compile(u'^Rated UR$'), Rating.RATING_NR),
            Rating(re.compile(u'^Unrated$'), Rating.RATING_NR),
            Rating(re.compile(u'^Rated Unrated$'), Rating.RATING_NR)
        )

    @classmethod
    def getMPAArating(cls, mpaaRating=None, adultRating=None):

        rating = cls.RATING_NR
        if adultRating is not None:
            if adultRating:
                rating = cls.RATING_NC_17

        Debug.myLog(u'In randomtrailers.getMPAArating rating: ' +
                    mpaaRating + u' adult: ' + str(adultRating), xbmc.LOGNOTICE)

        foundRating = False
        for ratingPattern in Rating.ALLOWED_RATINGS:
            if ratingPattern._pattern.match(ratingPattern._mpaaRatingLabel):
                foundRating = True
                rating = ratingPattern._mpaaRatingLabel
                break

        if not foundRating:
            Debug.myLog(u'mpaa rating not found for: ' +
                        mpaaRating + u' assuming Not Rated', xbmc.LOGDEBUG)

        return rating

    @classmethod
    def getImageForRating(cls, rating):
        if rating == Rating.RATING_G:
            imgRating = 'ratings/g.png'
        elif rating == Rating.RATING_PG:
            imgRating = 'ratings/pg.png'

        elif rating == Rating.RATING_PG_13:
            imgRating = 'ratings/pg13.png'

        elif rating == Rating.RATING_R:
            imgRating = 'ratings/r.png'

        elif rating == Rating.RATING_NC_17:
            imgRating = 'ratings/nc17.png'

        elif rating == Rating.RATING_NR:
            imgRating = 'ratings/notrated.png'
        return imgRating

    '''
       Does the given movie rating pass the configured limit?
    '''

    @staticmethod
    def checkRating(rating):
        passed = False
        maxRating = Settings.getRatingLimitSetting()

        Debug.myLog('In randomtrailer.checkRating rating: ' +
                    str(rating) + u' limit: ' + maxRating, xbmc.LOGNOTICE)

        if maxRating == '0':
            passed = True
        else:
            do_nr = Settings.getDoNotRatedSetting()
            nyr = u''
            nr = u''

            if Settings.getIncludeNotYetRatedTrailers():
                nyr = 'Not yet rated'

            if do_nr:
                nr = 'NR'

            if maxRating == '1':
                allowedRatings = ('G', nr, nyr)
            elif maxRating == '2':
                allowedRatings = ('G', 'PG', nr, nyr)
            elif maxRating == '3':
                allowedRatings = ('G', 'PG', 'PG-13', nr, nyr)
            elif maxRating == '4':
                allowedRatings = ('G', 'PG', 'PG-13', 'R', nr, nyr)
            elif maxRating == '5':
                allowedRatings = ('G', 'PG', 'PG-13', 'R',
                                  'NC-17', 'NC17', nr, nyr)

            if rating in allowedRatings:
                passed = True

        return passed


Rating._initClass()
