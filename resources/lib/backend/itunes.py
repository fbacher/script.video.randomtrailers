# -*- coding: utf-8 -*-

'''
Created on Mar 4, 2019

@author: fbacher
'''

from common.imports import *
from common.settings import Settings
from common.logger import *

module_logger: BasicLogger = BasicLogger.get_module_logger(module_path=__file__)


class ITunes:
    '''
    On first blush, iTunes appears to use 2-letter country codes (ISO-3166-1 alpha-2
    as well as ISO -639 language names). It is more likely that they use standardized
    sound/subtitle track language codes.

     _languageCodes = { 'japanese' : 'JP',
                       }
    '''

    _logger: BasicLogger = None

    def __init__(self) -> None:
        cls = type(self)
        if cls._logger is None:
            cls._logger = module_logger.getChild(cls.__name__)

    @classmethod
    def get_excluded_types(cls) -> {str}:
        '''

        :return:
        '''
        iso_639_2_name = Settings.get_lang_iso_639_2()
        iso_639_1_name = Settings.get_lang_iso_639_1()

        return {'- JP Sub', 'Interview', '- UK', '- BR Sub', '- FR', '- IT',
                '- AU', '- MX', '- MX Sub', '- BR', '- RU', '- DE',
                '- ES', '- FR Sub', '- KR Sub', '- Russian', '- French',
                '- Spanish', '- German', '- Latin American Spanish', '- Italian'}


# Initialize logger
ITunes()
