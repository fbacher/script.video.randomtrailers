# -*- coding: utf-8 -*-
''' 
Created on Feb 6, 2019

@author: fbacher
'''
from __future__ import print_function, division, absolute_import, unicode_literals

from future import standard_library
standard_library.install_aliases()  # noqa: E402

from builtins import str
from kodi_six import xbmc


class Action:
    # Values came from xbmcgui

    def __init__(self):
        actionMap = {u'ACTION_ANALOG_FORWARD': 113,
                     u'ACTION_ANALOG_MOVE': 49,
                     u'ACTION_ANALOG_MOVE_X_LEFT': 601,
                     u'ACTION_ANALOG_MOVE_X_RIGHT': 602,
                     u'ACTION_ANALOG_MOVE_Y_DOWN': 604,
                     u'ACTION_ANALOG_MOVE_Y_UP': 603,
                     u'ACTION_ANALOG_REWIND': 114,
                     u'ACTION_ANALOG_SEEK_BACK': 125,
                     u'ACTION_ANALOG_SEEK_FORWARD': 124,
                     u'ACTION_ASPECT_RATIO': 19,
                     u'ACTION_AUDIO_DELAY': 161,
                     u'ACTION_AUDIO_DELAY_MIN': 54,
                     u'ACTION_AUDIO_DELAY_PLUS': 55,
                     u'ACTION_AUDIO_NEXT_LANGUAGE': 56,
                     u'ACTION_BACKSPACE': 110,
                     u'ACTION_BIG_STEP_BACK': 23,
                     u'ACTION_BIG_STEP_FORWARD': 22,
                     u'ACTION_BROWSE_SUBTITLE': 247,
                     u'ACTION_BUILT_IN_FUNCTION': 122,
                     u'ACTION_CALIBRATE_RESET': 48,
                     u'ACTION_CALIBRATE_SWAP_ARROWS': 47,
                     u'ACTION_CHANGE_RESOLUTION': 57,
                     u'ACTION_CHANNEL_DOWN': 185,
                     u'ACTION_CHANNEL_NUMBER_SEP': 192,
                     u'ACTION_CHANNEL_SWITCH': 183,
                     u'ACTION_CHANNEL_UP': 184,
                     u'ACTION_CHAPTER_OR_BIG_STEP_BACK': 98,
                     u'ACTION_CHAPTER_OR_BIG_STEP_FORWARD': 97,
                     u'ACTION_CONTEXT_MENU': 117,
                     u'ACTION_COPY_ITEM': 81,
                     u'ACTION_CREATE_BOOKMARK': 96,
                     u'ACTION_CREATE_EPISODE_BOOKMARK': 95,
                     u'ACTION_CURSOR_LEFT': 120,
                     u'ACTION_CURSOR_RIGHT': 121,
                     u'ACTION_CYCLE_SUBTITLE': 99,
                     u'ACTION_DECREASE_PAR': 220,
                     u'ACTION_DECREASE_RATING': 137,
                     u'ACTION_DELETE_ITEM': 80,
                     u'ACTION_ENTER': 135,
                     u'ACTION_ERROR': 998,
                     u'ACTION_FILTER': 233,
                     u'ACTION_FILTER_CLEAR': 150,
                     u'ACTION_FILTER_SMS2': 151,
                     u'ACTION_FILTER_SMS3': 152,
                     u'ACTION_FILTER_SMS4': 153,
                     u'ACTION_FILTER_SMS5': 154,
                     u'ACTION_FILTER_SMS6': 155,
                     u'ACTION_FILTER_SMS7': 156,
                     u'ACTION_FILTER_SMS8': 157,
                     u'ACTION_FILTER_SMS9': 158,
                     u'ACTION_FIRST_PAGE': 159,
                     u'ACTION_FORWARD': 16,
                     u'ACTION_GESTURE_ABORT': 505,
                     u'ACTION_GESTURE_BEGIN': 501,
                     u'ACTION_GESTURE_END': 599,
                     u'ACTION_GESTURE_NOTIFY': 500,
                     u'ACTION_GESTURE_PAN': 504,
                     u'ACTION_GESTURE_ROTATE': 503,
                     u'ACTION_GESTURE_SWIPE_DOWN': 541,
                     u'ACTION_GESTURE_SWIPE_DOWN_TEN': 550,
                     u'ACTION_GESTURE_SWIPE_LEFT': 511,
                     u'ACTION_GESTURE_SWIPE_LEFT_TEN': 520,
                     u'ACTION_GESTURE_SWIPE_RIGHT': 521,
                     u'ACTION_GESTURE_SWIPE_RIGHT_TEN': 530,
                     u'ACTION_GESTURE_SWIPE_UP': 531,
                     u'ACTION_GESTURE_SWIPE_UP_TEN': 540,
                     u'ACTION_GESTURE_ZOOM': 502,
                     u'ACTION_GUIPROFILE_BEGIN': 204,
                     u'ACTION_HIGHLIGHT_ITEM': 8,
                     u'ACTION_INCREASE_PAR': 219,
                     u'ACTION_INCREASE_RATING': 136,
                     u'ACTION_INPUT_TEXT': 244,
                     u'ACTION_JUMP_SMS2': 142,
                     u'ACTION_JUMP_SMS3': 143,
                     u'ACTION_JUMP_SMS4': 144,
                     u'ACTION_JUMP_SMS5': 145,
                     u'ACTION_JUMP_SMS6': 146,
                     u'ACTION_JUMP_SMS7': 147,
                     u'ACTION_JUMP_SMS8': 148,
                     u'ACTION_JUMP_SMS9': 149,
                     u'ACTION_LAST_PAGE': 160,
                     u'ACTION_MENU': 163,
                     u'ACTION_MOUSE_DOUBLE_CLICK': 103,
                     u'ACTION_MOUSE_DRAG': 106,
                     u'ACTION_MOUSE_END': 109,
                     u'ACTION_MOUSE_LEFT_CLICK': 100,
                     u'ACTION_MOUSE_LONG_CLICK': 108,
                     u'ACTION_MOUSE_MIDDLE_CLICK': 102,
                     u'ACTION_MOUSE_MOVE': 107,
                     u'ACTION_MOUSE_RIGHT_CLICK': 101,
                     u'ACTION_MOUSE_START': 100,
                     u'ACTION_MOUSE_WHEEL_DOWN': 105,
                     u'ACTION_MOUSE_WHEEL_UP': 104,
                     u'ACTION_MOVE_DOWN': 4,
                     u'ACTION_MOVE_ITEM': 82,
                     u'ACTION_MOVE_ITEM_DOWN': 116,
                     u'ACTION_MOVE_ITEM_UP': 115,
                     u'ACTION_MOVE_LEFT': 1,
                     u'ACTION_MOVE_RIGHT': 2,
                     u'ACTION_MOVE_UP': 3,
                     u'ACTION_MUTE': 91,
                     u'ACTION_NAV_BACK': 92,
                     u'ACTION_NEXT_CHANNELGROUP': 186,
                     u'ACTION_NEXT_CONTROL': 181,
                     u'ACTION_NEXT_ITEM': 14,
                     u'ACTION_NEXT_LETTER': 140,
                     u'ACTION_NEXT_PICTURE': 28,
                     u'ACTION_NEXT_SCENE': 138,
                     u'ACTION_NEXT_SUBTITLE': 26,
                     u'ACTION_NONE': 0,
                     u'ACTION_NOOP': 999,
                     u'ACTION_PAGE_DOWN': 6,
                     u'ACTION_PAGE_UP': 5,
                     u'ACTION_PARENT_DIR': 9,
                     u'ACTION_PASTE': 180,
                     u'ACTION_PAUSE': 12,
                     u'ACTION_PLAYER_DEBUG': 27,
                     u'ACTION_PLAYER_FORWARD': 77,
                     u'ACTION_PLAYER_PLAY': 79,
                     u'ACTION_PLAYER_PLAYPAUSE': 229,
                     u'ACTION_PLAYER_PROCESS_INFO': 69,
                     u'ACTION_PLAYER_PROGRAM_SELECT': 70,
                     u'ACTION_PLAYER_RESET': 248,
                     u'ACTION_PLAYER_RESOLUTION_SELECT': 71,
                     u'ACTION_PLAYER_REWIND': 78,
                     u'ACTION_PREVIOUS_CHANNELGROUP': 187,
                     u'ACTION_PREVIOUS_MENU': 10,
                     u'ACTION_PREV_CONTROL': 182,
                     u'ACTION_PREV_ITEM': 15,
                     u'ACTION_PREV_LETTER': 141,
                     u'ACTION_PREV_PICTURE': 29,
                     u'ACTION_PREV_SCENE': 139,
                     u'ACTION_PVR_PLAY': 188,
                     u'ACTION_PVR_PLAY_RADIO': 190,
                     u'ACTION_PVR_PLAY_TV': 189,
                     u'ACTION_PVR_SHOW_TIMER_RULE': 191,
                     u'ACTION_QUEUE_ITEM': 34,
                     u'ACTION_QUEUE_ITEM_NEXT': 251,
                     u'ACTION_RECORD': 170,
                     u'ACTION_RELOAD_KEYMAPS': 203,
                     u'ACTION_REMOVE_ITEM': 35,
                     u'ACTION_RENAME_ITEM': 87,
                     u'ACTION_REWIND': 17,
                     u'ACTION_ROTATE_PICTURE_CCW': 51,
                     u'ACTION_ROTATE_PICTURE_CW': 50,
                     u'ACTION_SCAN_ITEM': 201,
                     u'ACTION_SCROLL_DOWN': 112,
                     u'ACTION_SCROLL_UP': 111,
                     u'ACTION_SELECT_ITEM': 7,
                     u'ACTION_SETTINGS_LEVEL_CHANGE': 242,
                     u'ACTION_SETTINGS_RESET': 241,
                     u'ACTION_SET_RATING': 164,
                     u'ACTION_SHIFT': 118,
                     u'ACTION_SHOW_FULLSCREEN': 36,
                     u'ACTION_SHOW_GUI': 18,
                     u'ACTION_SHOW_INFO': 11,
                     u'ACTION_SHOW_OSD': 24,
                     u'ACTION_SHOW_OSD_TIME': 123,
                     u'ACTION_SHOW_PLAYLIST': 33,
                     u'ACTION_SHOW_SUBTITLES': 25,
                     u'ACTION_SHOW_VIDEOMENU': 134,
                     u'ACTION_SMALL_STEP_BACK': 76,
                     u'ACTION_STEP_BACK': 21,
                     u'ACTION_STEP_FORWARD': 20,
                     u'ACTION_STEREOMODE_NEXT': 235,
                     u'ACTION_STEREOMODE_PREVIOUS': 236,
                     u'ACTION_STEREOMODE_SELECT': 238,
                     u'ACTION_STEREOMODE_SET': 240,
                     u'ACTION_STEREOMODE_TOGGLE': 237,
                     u'ACTION_STEREOMODE_TOMONO': 239,
                     u'ACTION_STOP': 13,
                     u'ACTION_SUBTITLE_ALIGN': 232,
                     u'ACTION_SUBTITLE_DELAY': 162,
                     u'ACTION_SUBTITLE_DELAY_MIN': 52,
                     u'ACTION_SUBTITLE_DELAY_PLUS': 53,
                     u'ACTION_SUBTITLE_VSHIFT_DOWN': 231,
                     u'ACTION_SUBTITLE_VSHIFT_UP': 230,
                     u'ACTION_SWITCH_PLAYER': 234,
                     u'ACTION_SYMBOLS': 119,
                     u'ACTION_TAKE_SCREENSHOT': 85,
                     u'ACTION_TELETEXT_BLUE': 218,
                     u'ACTION_TELETEXT_GREEN': 216,
                     u'ACTION_TELETEXT_RED': 215,
                     u'ACTION_TELETEXT_YELLOW': 217,
                     u'ACTION_TOGGLE_COMMSKIP': 246,
                     u'ACTION_TOGGLE_DIGITAL_ANALOG': 202,
                     u'ACTION_TOGGLE_FONT': 249,
                     u'ACTION_TOGGLE_FULLSCREEN': 199,
                     u'ACTION_TOGGLE_SOURCE_DEST': 32,
                     u'ACTION_TOGGLE_WATCHED': 200,
                     u'ACTION_TOUCH_LONGPRESS': 411,
                     u'ACTION_TOUCH_LONGPRESS_TEN': 420,
                     u'ACTION_TOUCH_TAP': 401,
                     u'ACTION_TOUCH_TAP_TEN': 410,
                     u'ACTION_TRIGGER_OSD': 243,
                     u'ACTION_VIDEO_NEXT_STREAM': 250,
                     u'ACTION_VIS_PRESET_LOCK': 130,
                     u'ACTION_VIS_PRESET_NEXT': 128,
                     u'ACTION_VIS_PRESET_PREV': 129,
                     u'ACTION_VIS_PRESET_RANDOM': 131,
                     u'ACTION_VIS_PRESET_SHOW': 126,
                     u'ACTION_VIS_RATE_PRESET_MINUS': 133,
                     u'ACTION_VIS_RATE_PRESET_PLUS': 132,
                     u'ACTION_VOICE_RECOGNIZE': 300,
                     u'ACTION_VOLAMP': 90,
                     u'ACTION_VOLAMP_DOWN': 94,
                     u'ACTION_VOLAMP_UP': 93,
                     u'ACTION_VOLUME_DOWN': 89,
                     u'ACTION_VOLUME_SET': 245,
                     u'ACTION_VOLUME_UP': 88,
                     u'ACTION_VSHIFT_DOWN': 228,
                     u'ACTION_VSHIFT_UP': 227,
                     u'ACTION_ZOOM_IN': 31,
                     u'ACTION_ZOOM_LEVEL_1': 38,
                     u'ACTION_ZOOM_LEVEL_2': 39,
                     u'ACTION_ZOOM_LEVEL_3': 40,
                     u'ACTION_ZOOM_LEVEL_4': 41,
                     u'ACTION_ZOOM_LEVEL_5': 42,
                     u'ACTION_ZOOM_LEVEL_6': 43,
                     u'ACTION_ZOOM_LEVEL_7': 44,
                     u'ACTION_ZOOM_LEVEL_8': 45,
                     u'ACTION_ZOOM_LEVEL_9': 46,
                     u'ACTION_ZOOM_LEVEL_NORMAL': 37,
                     u'ACTION_ZOOM_OUT': 30}

        '''
            u'ALPHANUM_HIDE_INPUT' : 2,
            u'CONTROL_TEXT_OFFSET_X' : 10,
            u'CONTROL_TEXT_OFFSET_Y' : 2,
            u'HORIZONTAL' : 0,
            u'ICON_OVERLAY_HD' : 6,
            u'ICON_OVERLAY_LOCKED' : 3,
            u'ICON_OVERLAY_NONE' : 0,
            u'ICON_OVERLAY_RAR' : 1,
            u'ICON_OVERLAY_UNWATCHED' : 4,
            u'ICON_OVERLAY_WATCHED' : 5,
            u'ICON_OVERLAY_ZIP' : 2,
            u'ICON_TYPE_FILES' : 106,
            u'ICON_TYPE_MUSIC' : 103,
            u'ICON_TYPE_NONE' : 101,
            u'ICON_TYPE_PICTURES' : 104,
            u'ICON_TYPE_PROGRAMS' : 102,
            u'ICON_TYPE_SETTINGS' : 109,
            u'ICON_TYPE_VIDEOS' : 105,
            u'ICON_TYPE_WEATHER' : 107
        '''

        '''
            u'INPUT_ALPHANUM' : 0,
            u'INPUT_DATE' : 2,
            u'INPUT_IPADDRESS' : 4,
            u'INPUT_NUMERIC' : 1,
            u'INPUT_PASSWORD' : 5,
                u'INPUT_TIME' : 3,
                u'INPUT_TYPE_DATE' : 4,
                u'INPUT_TYPE_IPADDRESS' : 5,
                u'INPUT_TYPE_NUMBER' : 1,
                u'INPUT_TYPE_PASSWORD' : 6,
                u'INPUT_TYPE_PASSWORD_MD5' : 7,
                u'INPUT_TYPE_SECONDS' : 2,
                u'INPUT_TYPE_TEXT' : 0,
            u'INPUT_TYPE_TIME' : 3
        '''

        '''
                u'KEY_APPCOMMAND' : 53248,
                u'KEY_ASCII' : 61696,
        '''

        keyButtonMap = {
            u'KEY_BUTTON_A': 256,
            u'KEY_BUTTON_B': 257,
            u'KEY_BUTTON_BACK': 275,
            u'KEY_BUTTON_BLACK': 260,
            u'KEY_BUTTON_DPAD_DOWN': 271,
            u'KEY_BUTTON_DPAD_LEFT': 272,
            u'KEY_BUTTON_DPAD_RIGHT': 273,
            u'KEY_BUTTON_DPAD_UP': 270,
            u'KEY_BUTTON_LEFT_ANALOG_TRIGGER': 278,
            u'KEY_BUTTON_LEFT_THUMB_BUTTON': 276,
            u'KEY_BUTTON_LEFT_THUMB_STICK': 264,
            u'KEY_BUTTON_LEFT_THUMB_STICK_DOWN': 281,
            u'KEY_BUTTON_LEFT_THUMB_STICK_LEFT': 282,
            u'KEY_BUTTON_LEFT_THUMB_STICK_RIGHT': 283,
            u'KEY_BUTTON_LEFT_THUMB_STICK_UP': 280,
            u'KEY_BUTTON_LEFT_TRIGGER': 262,
            u'KEY_BUTTON_RIGHT_ANALOG_TRIGGER': 279,
            u'KEY_BUTTON_RIGHT_THUMB_BUTTON': 277,
            u'KEY_BUTTON_RIGHT_THUMB_STICK': 265,
            u'KEY_BUTTON_RIGHT_THUMB_STICK_DOWN': 267,
            u'KEY_BUTTON_RIGHT_THUMB_STICK_LEFT': 268,
            u'KEY_BUTTON_RIGHT_THUMB_STICK_RIGHT': 269,
            u'KEY_BUTTON_RIGHT_THUMB_STICK_UP': 266,
            u'KEY_BUTTON_RIGHT_TRIGGER': 263,
            u'KEY_BUTTON_START': 274,
            u'KEY_BUTTON_WHITE': 261,
            u'KEY_BUTTON_X': 258,
            u'KEY_BUTTON_Y': 259,
            u'KEY_INVALID': 65535,
            u'KEY_MOUSE_CLICK': 57344,
            u'KEY_MOUSE_DOUBLE_CLICK': 57360,
            u'KEY_MOUSE_DRAG': 57604,
            u'KEY_MOUSE_DRAG_END': 57606,
            u'KEY_MOUSE_DRAG_START': 57605,
            u'KEY_MOUSE_END': 61439,
            u'KEY_MOUSE_LONG_CLICK': 57376,
            u'KEY_MOUSE_MIDDLECLICK': 57346,
            u'KEY_MOUSE_MOVE': 57603,
            u'KEY_MOUSE_NOOP': 61439,
            u'KEY_MOUSE_RDRAG': 57607,
            u'KEY_MOUSE_RDRAG_END': 57609,
            u'KEY_MOUSE_RDRAG_START': 57608,
            u'KEY_MOUSE_RIGHTCLICK': 57345,
            u'KEY_MOUSE_START': 57344,
            u'KEY_MOUSE_WHEEL_DOWN': 57602,
            u'KEY_MOUSE_WHEEL_UP': 57601,
            u'KEY_UNICODE': 61952,
            u'KEY_VKEY': 61440,
            u'KEY_VMOUSE': 61439}

        '''
            u'NOTIFICATION_ERROR' : ,'error'
            u'NOTIFICATION_INFO' : ,'info'
            u'NOTIFICATION_WARNING' : ,'warning'
            u'PASSWORD_VERIFY' : 1
        '''

        remoteMap = {
            u'REMOTE_0': 58,
            u'REMOTE_1': 59,
            u'REMOTE_2': 60,
            u'REMOTE_3': 61,
            u'REMOTE_4': 62,
            u'REMOTE_5': 63,
            u'REMOTE_6': 64,
            u'REMOTE_7': 65,
            u'REMOTE_8': 66,
            u'REMOTE_9': 67,
            u'VERTICAL': 1}

        self.byNameMap = {u'actionMap': actionMap,
                          u'keyButtonMap': keyButtonMap,
                          u'remoteMap': remoteMap
                          }
        self.reverseActionMap = dict()
        for key in actionMap:
            value = actionMap.get(key)
            if value in self.reverseActionMap:
                xbmc.log(u'duplicate value in actionMap: ' +
                         str(value), xbmc.LOGDEBUG)
            self.reverseActionMap[value] = key

        self.reverseKeyButtonMap = dict()
        for key in keyButtonMap:
            value = keyButtonMap.get(key)
            if value in self.reverseKeyButtonMap:
                xbmc.log(u'duplicate value in keyButtonMap: ' +
                         str(value), xbmc.LOGDEBUG)
            self.reverseKeyButtonMap[value] = key

        self.buttonNameForCode = dict()
        self.buttonNameForCode[61513] = u'key_I'

        self.reverseRemoteMap = dict()
        for key in remoteMap:
            value = remoteMap.get(key)
            if value in self.reverseRemoteMap:
                xbmc.log(u'duplicate value in remoteMap: ' +
                         str(value) + u' ' + self.reverseRemoteMap.get(value), xbmc.LOGDEBUG)
            self.reverseRemoteMap[value] = key

        self.reverseMapsByNameMap = {u'actionMap': self.reverseActionMap,
                                     u'keyButtonMap': self.reverseKeyButtonMap,
                                     u'remoteMap':  self.reverseRemoteMap}
        self.mapNames = [u'actionMap', u'keyButtonMap', u'remoteMap']

    _singletonInstance = None

    @staticmethod
    def getInstance():
        if Action._singletonInstance is None:
            Action._singletonInstance = Action()
        return Action._singletonInstance

    def getKeyIDInfo(self, action):
        actionId = action.getId()

        result = []
        for mapName in self.mapNames:
            reverseMap = self.reverseMapsByNameMap.get(mapName)
            keyName = reverseMap.get(actionId)
            if keyName is not None:
                result.append(str(actionId) + u' Map: ' +
                              mapName + u' : ' + keyName)

        if len(result) == 0:
            result.append(u'Keyname for ' + str(actionId) + u' not Found')

        return result

    def getRemoteKeyIDInfo(self, action):
        actionId = action.getId()
        return self.reverseRemoteMap.get(actionId, u'')

    def getRemoteKeyButtonInfo(self, action):
        actionId = action.getId()
        return self.reverseKeyButtonMap.get(actionId, u'')

    def getActionIDInfo(self, action):
        actionId = action.getId()
        return self.reverseActionMap.get(actionId, u'')

    def getButtonCodeId(self, action):
        buttonCode = action.getButtonCode()
        buttonName = self.buttonNameForCode.get(
            buttonCode, u'key_' + str(buttonCode))
        return buttonName
