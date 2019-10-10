# -*- coding: utf-8 -*-

'''
Created on Mar 4, 2019

@author: fbacher
'''
from __future__ import absolute_import, division, print_function, unicode_literals

from common.imports import *

from common.constants import (Constants)
from common.settings import Settings
from common.logger import (Logger, LazyLogger, Trace)

if Constants.INCLUDE_MODULE_PATH_IN_LOGGER:
    module_logger = LazyLogger.get_addon_module_logger().getChild(
        'backend.itunes')
else:
    module_logger = LazyLogger.get_addon_module_logger()


class ITunes(object):
    '''
    On first blush, iTunes appears to use 2-letter country codes (ISO-3166-1 alpha-2
    as well as ISO -639 language names). It is more likely that they use standardized
    sound/subtitle track language codes.

     _languageCodes = { 'japanese' : 'JP',
                       }
    '''

    @staticmethod
    def get_excluded_types():
        # type: () -> {str}
        '''

        :return:
        '''
        iso_639_2_name = Settings.getLang_iso_639_2()
        iso_639_1_name = Settings.getLang_iso_639_1()
        if module_logger.isEnabledFor(Logger.DEBUG):
            module_logger.getChild('ITunes').debug('iso_639_2:', iso_639_2_name,
                                                   'iso_639_1:', iso_639_1_name)

        return {'- JP Sub', 'Interview', '- UK', '- BR Sub', '- FR', '- IT', '- AU', '- MX', '- MX Sub', '- BR', '- RU', '- DE',
                '- ES', '- FR Sub', '- KR Sub', '- Russian', '- French', '- Spanish', '- German', '- Latin American Spanish', '- Italian'}
