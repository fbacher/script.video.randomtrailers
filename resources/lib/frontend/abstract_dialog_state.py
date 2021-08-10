# -*- coding: utf-8 -*-

"""
Created on Jul 29, 2021

@author: Frank Feuerbacher

"""
from enum import Enum

from common.imports import *


class DialogState(Enum):
    """

    """
    NORMAL = 0
    SKIP_PLAYING_TRAILER = 1
    GROUP_QUOTA_REACHED = 2
    QUOTA_REACHED = 3
    NO_TRAILERS_TO_PLAY = 4
    USER_REQUESTED_EXIT = 5
    START_MOVIE_AND_EXIT = 6
    SHUTDOWN_CUSTOM_PLAYER = 7
    STARTED_PLAYING_MOVIE = 8
    SHUTDOWN = 9

    label_map: Dict[ForwardRef('DialogState'), str] = {
        NORMAL: 'NORMAL',
        SKIP_PLAYING_TRAILER: 'SKIP_PLAYING_TRAILER',
        GROUP_QUOTA_REACHED: 'GROUP_QUOTA_REACHED',
        QUOTA_REACHED: 'QUOTA_REACHED',
        NO_TRAILERS_TO_PLAY: 'NO_TRAILERS_TO_PLAY',
        USER_REQUESTED_EXIT: 'USER_REQUESTED_EXIT',
        START_MOVIE_AND_EXIT: 'START_MOVIE_AND_EXIT',
        SHUTDOWN_CUSTOM_PLAYER: 'SHUTDOWN_CUSTOM_PLAYER',
        STARTED_PLAYING_MOVIE: 'STARTED_PLAYING_MOVIE',
        SHUTDOWN: 'SHUTDOWN'}

    def __ge__(self, other):

        if self.__class__ is other.__class__:
            return self.value >= other.value

        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

    @classmethod
    def get_label(cls, dialog_state: ForwardRef('DialogState')) -> str:
        """

        :param dialog_state:
        :return:
        """
        return DialogState.label_map[dialog_state]


class BaseDialogStateMgr:

    _trailer_dialog: ForwardRef('frontend.TrailerDialog') = None
    _real_manager: ForwardRef('BaseDialogStateMgr') = None

    @classmethod
    def get_instance(cls) -> ForwardRef('BaseDialogStateMgr'):
        from frontend.dialog_controller import DialogStateMgr
        DialogStateMgr.class_init()
        return BaseDialogStateMgr._real_manager

    @classmethod
    def set_trailer_dialog(cls, trailer_dialog: ForwardRef('frontend.TrailerDialog')):
        BaseDialogStateMgr._trailer_dialog = trailer_dialog

    @classmethod
    def get_trailer_dialog(cls) -> ForwardRef('frontend.TrailerDialog'):
        return BaseDialogStateMgr._trailer_dialog

    @classmethod
    def is_random_trailers_play_state(cls,
                                      minimum_exit_state: DialogState =
                                      DialogState.GROUP_QUOTA_REACHED,
                                      exact_match: bool = False,
                                      throw_exception_on_abort: bool = True
                                      ) -> bool:
        """
            Checks the current state of random trailers plugin against default
            or passed in values.

            Note that a check for Abort state is performed on each
            call.

            A return value of True indicating whether specified state has been
            reached.

        :param minimum_exit_state: Return True if DialogState is at least this value
        :param exact_match: Only return True if DialogState is exactly this value
        :param throw_exception_on_abort: Throw AbortException
                instead, as appropriate.
        :return:
        """
        raise NotImplementedError

    @classmethod
    def set_random_trailers_play_state(cls, dialog_state: DialogState) -> None:
        """

        :param dialog_state:
        :return:
        """
        raise NotImplementedError
