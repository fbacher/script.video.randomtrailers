# -*- coding: utf-8 -*-

"""
Created on Feb 10, 2019

@author: fbacher
"""
import io
import os
import logging
import sys
from typing import List, ForwardRef, Dict, Any, Union, Set

import json
import xmltodict
from .__init__ import *


class Requirement:
    """
    Records an addon which another addon referenced_addons (depends upon)

    Addons._all_addons keeps a list of all addons that are required by another
    addon

    """
    def __init__(self, addon: str, version: str, optional: bool):
        # Simply record info from "referenced_addons" section of addon.xmls,
        # namely, the addon info that is required by some addon.
        # The other addon requiring this one is tracked in
        # Addons._all_addons

        self.addon_id: str = addon
        self.version: str = version
        self.optional: bool = optional

    def get_addon_id(self) -> str:
        return self.addon_id

    def get_version(self) -> str:
        return self.version

    def is_optional(self) -> bool:
        return self.optional


'''
class DependsUpon:
    """
    Records all of the addons that require another addon (inverse of Requirement).

    Addons.all_dependencies keeps a list of all addons that require
    another addon

    """

    def __init__(self, requirement: Requirement, addon: ForwardRef('Addon')):
        """
        To find all of the addons that require another addon, get a list
        of dependant addons from Addons._dependent_addons[addon_which_others_depend_upon]

        These entries simply list the info for the addon requiring it

        @param: requirement: The addon which is required
        @param: addon: An addon which referenced_addons another addon
        """
        clz = type(self)
        self.addon_id: str = requirement.get_addon_id()
        self.version: str = requirement.get_version()
        self.optional: bool = requirement.is_optional()
        self._depending_addon_id: str = addon.get_addon_id()

        # For each addon, keep a list of all of the addons which
        # depend upon it.

        # Could be improved by making it take into account indirect
        # dependencies A -> B -> C, therefore A -> C

        dependencies: List[ForwardRef('DependsUpon')]
        dependencies = Addons.all_dependencies.get(self.addon_id)
        if dependencies is None:
            dependencies = []
            Addons.all_dependencies[self.addon_id] = dependencies
        dependencies.append(self)

    def get_addon_id(self) -> str:
        return self._depending_addon_id

    def get_version(self) -> str:
        return self.version

    def is_optional(self) -> bool:
        return self.optional

    def get_referenced_addon_id(self):
        return self.addon_id

    def __lt__(self, obj):
        other: DependsUpon = obj
        return self._depending_addon_id < other._depending_addon_id

    def __eq__(self, obj):
        other: DependsUpon = obj
        return self._depending_addon_id == other._depending_addon_id

    def __gt__(self, obj):
        other: DependsUpon = obj
        return self._depending_addon_id > other._depending_addon_id

    def __ge__(self, obj):
        other: DependsUpon = obj
        return self._depending_addon_id >= other._depending_addon_id

    def __le__(self, obj):
        other: DependsUpon = obj
        return self._depending_addon_id <= other._depending_addon_id

    def __repr__(self):
        return self._depending_addon_id
'''


class Addon:
    all_addons: Dict[str, ForwardRef('Addon')] = {}

    def __init__(self, addon_id: str,
                 version: str) -> None:
        self.addon_id: str = addon_id
        self.version: str = version

    @classmethod
    def create(cls, addon_id: str, version: str) -> ForwardRef('Addon'):
        addon: Addon = cls.all_addons.get(addon_id)
        if addon is None:
            addon = Addon(addon_id, version)
            cls.all_addons[addon_id] = addon
        return addon

    def get_addon_id(self) -> str:
        return self.addon_id

    def get_version(self) -> str:
        return self.version


class Addons:
    ADDONS_PATH: str = "/home/fbacher/Source/addons.xml"

    #  For a given addon, keep a list of addons which it depends

    all_dependencies: Dict[str, Set[str]] = {}

    # For a given addon, keep a list of addons which depend upon it

    inverse_addons: Dict[str, Set[str]] = {}

    @classmethod
    def add_referenced_addon(cls, addon: Addon, requires: Addon) -> None:
        if addon.get_addon_id() == requires.get_addon_id():
            return

        required_ids: Set[str] = cls.all_dependencies.get(addon.get_addon_id())
        if required_ids is None:
            required_ids = set()
            cls.all_dependencies[addon.get_addon_id()] = required_ids

        required_ids.add(requires.get_addon_id())

        inverse_ids: Set[str] = cls.inverse_addons.get(requires.get_addon_id())
        if inverse_ids is None:
            inverse_ids = set()
            cls.inverse_addons[requires.get_addon_id()] = inverse_ids

        inverse_ids.add(addon.get_addon_id())
        return

    def __init__(self) -> None:
        pass

    @classmethod
    def load_addons(cls):

        # Load several special addons in

        addon_id = 'xbmc.python_3.0.0'
        addon: Addon = Addon(addon_id, '3.0.0')

        raw_addons: Dict[str, Any]
        raw_addons = Addons.read_cache_json()
        raw_addon: Dict[str, str]
        for raw_addon in raw_addons["addons"]["addon"]:
            addon_name: str = raw_addon['@id']
            version: str = raw_addon['@version']
            addon_id: str = f'{addon_name}_{version}'
            logging.debug(f'Creating addon: {addon_id}')
            addon: Addon = Addon.create(addon_id, version)
            req: Dict[str, str]
            references: [Dict[str, str]] = raw_addon.get('requires')
            logging.debug(f'About to parse references for {addon_id}')

            if references is None:
                logging.debug(f'References are None")')
                continue

            # logging.debug(f'referenced_addons: {addon_id} {type(references)} {references}')
            imports = references["import"]
            # logging.debug(f'imports type: {type(imports)}')
            if not isinstance(imports, list):
                logging.debug(f'imports is not a list')
                import_list = list()
                import_list.append(imports)
                imports = import_list
            for req in imports:
                #
                # The Addon that we are parsing (with addon_id) referenced_addons
                # each of these other addons.
                #
                req_name: str = req['@addon']
                req_version: str = req.get('@version', '*')
                req_id: str = f'{req_name}_{req_version}'
                req_optional: bool = bool(req.get('optional', 'false'))

                logging.debug(f'req_id: {req_id} {req_version} {req_optional} '
                              f'for addon_id: {addon_id} ')

                requirement_addon: Addon = Addon.create(req_id, req_version)
                Addons.add_referenced_addon(addon, requirement_addon)

        return

    @classmethod
    def read_cache_json(cls
                        ) -> Dict[str, Any]:

        try:
            addon_index = Dict[str, Any]
            addon_index = {}
            # Keep cached files from the source the data/trailer comes from
            path: str = cls.ADDONS_PATH
            if path is None or not os.path.exists(path):
                logging.debug(f'cache file not found for: path: {path}')
                return None

            if not os.access(path, os.R_OK):
                logging.warning(f'Can not read file: {path}')
                return None

            with io.open(path.encode('utf-8'), mode='rt', newline=None,
                         encoding='utf-8') as addon_file:
                try:
                    addon_index = xmltodict.parse(addon_file.read())
                except Exception as e:
                    logging.exception(e)
                    logging.debug(
                        f'Failing xmltodict: {path}')
                    exception_occurred = True
            with io.open("/tmp/addons.xml", mode='wt', newline=None,
                         encoding="utf-8") as json_file:
                json_file.write(json.dumps(addon_index,
                                           ensure_ascii=False,
                                           indent=3, sort_keys=True)
                                )
        except IOError as e:
            logging.exception('')
            exception_occurred = True
        except Exception as e:
            logging.exception('')
            exception_occurred = True

        return addon_index

    @classmethod
    def print_dependencies(cls):

        cls.print_addons_require()

        addon_id: str
        all_addon_keys = list(Addon.all_addons.keys())
        all_addon_keys.sort()

        print("")
        print('For every addon, list addons that require it')
        print("")
        for addon_id in all_addon_keys:
            print("")
            print(f'Addon: {addon_id}')
            requiring_addon_id: str
            requiring_addon_ids: Set[str] = Addons.inverse_addons.get(addon_id)
            if requiring_addon_ids is None:
                print(f'    No addons require this addon')
                continue

            sorted_requiring_addons = list(requiring_addon_ids)
            sorted_requiring_addons.sort()
            if len(sorted_requiring_addons) == 0:
                logging.debug(f'    No addons require this addon:')
            for requiring_addon_id in sorted_requiring_addons:
                print(f'    {requiring_addon_id}')

        print('fine\n')
        sys.exit(0)

    @classmethod
    def print_addons_require(cls):

        print("")
        print("")
        print(f'Addon\'s requirements on other addons')
        print("")
        addon_id: str
        #  logging.debug(f'all_addons: {Addons.all_addons}')
        for addon_id in sorted(Addon.all_addons.keys()):
            print("")
            print(f'Addon: {addon_id}')

            #  Get addons required by this addon

            required_addon_ids: Set[str]
            required_addon_ids = Addons.all_dependencies.get(addon_id)
            if required_addon_ids is None or len(required_addon_ids) == 0:
                print(f'   No addons require this addon')
                continue

            required_addon_id_list = list(required_addon_ids)
            required_addon_id_list.sort()
            required_addon_id: str
            for required_addon_id in required_addon_id_list:
                print(f'    Is Required by: {required_addon_id}')


        print("")



if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    Addons.load_addons()
    Addons.print_dependencies()
