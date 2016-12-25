"""
Base classes and utilities to manage Spirent Test Center (STC).

:author: yoram@ignissoft.com
"""

import time
import re
from collections import OrderedDict

from trafficgenerator.tgn_utils import TgnError
from trafficgenerator.tgn_tcl import build_obj_ref_list
from trafficgenerator.tgn_object import TgnObject


def extract_stc_obj_type_from_obj_ref(obj_ref):
    # Extract object type from object reference. Note that there are rare cases where
    # object reference has no sequential number suffix like 'automationoptions'.
    m = re.search('(.*\D+)\d+', obj_ref)
    return m.group(1) if m else obj_ref


class StcObject(TgnObject):

    # Class level variables
    logger = None
    api = None
    project = None

    str_2_class = {}

    def __init__(self, **data):
        if 'objRef' in data:
            data['objType'] = extract_stc_obj_type_from_obj_ref(data['objRef'])
            if 'parent' not in data:
                self._data['objRef'] = data['objRef']
                data['parent'] = self.get_object_from_attribute('parent')
        if type(self) == StcObject:
            self.__class__ = self.get_obj_class(data['objType'])
        super(StcObject, self).__init__(**data)

    def get_obj_class(self, str_obj):
        return StcObject.str_2_class.get(str_obj.lower(), StcObject)

    def _create(self):
        """ Create new object on STC.

        @return: STC object reference.
        """

        # At this time objRef is not set yet so we must use direct calls to api.
        if 'name' in self._data:
            return self.api.create(self.obj_type(), self.obj_parent(), name=self.obj_name())
        else:
            stc_obj = self.api.create(self.obj_type(), self.obj_parent())
            self._data['name'] = self.api.get(stc_obj, 'name')
            return stc_obj

    def command(self, command, wait_after=0, **arguments):
        self.api.perform(command, **arguments)
        time.sleep(wait_after)

    def get_attribute(self, attribute):
        """ Get single attribute value.

        :param attribute: attribute name.
        :return: attribute value.
        """
        return self.api.get(self.obj_ref(), attribute)

    def get_list_attribute(self, attribute):
        """
        :return: attribute value as Python list.
        """
        return self.api.getList(self.obj_ref(), attribute)

    def get_objects_from_attribute(self, attribute):
        objects = []
        for handle in self.get_attribute(attribute).split():
            obj = self.project.get_object_by_ref(handle)
            if not obj:
                obj = StcObject(objRef=handle)
            objects.append(obj)
        return objects

    def get_object_from_attribute(self, attribute):
        return self.get_objects_from_attribute(attribute)[0] if self.get_objects_from_attribute(attribute) else None

    def append_attribute(self, attribute, value, apply_=False):
        cur_value = self.api.get(self.obj_ref(), attribute)
        attributes = {attribute: cur_value + ' ' + str(value)}
        self.set_attributes(apply_=apply_, **attributes)

    def get_attributes(self, *attributes):
        """ Get multiple attributes values.

        Some low level APIs (like Tcl over Telnet) supports limited output length.
        When using get_attributes() the method will use simple stc::get to read all attributes. This is efficient but
        the output might exceed the output limit and will be truncated.
        When using attributes(*attributes) the method will use stc::get -attribute to read the attributes one by one.
        This is less efficient but less likely to exceed the output length.

        :param attributes: list of attributes to retrieve. If empty (default) return all attribute values.
        :return: dictionary {attribute: value} of all requested attributes.
        """

        if not attributes:
            return self.api.get(self.obj_ref())
        values = {}
        for attribute in attributes:
            values[attribute] = self.get_attribute(attribute)
        return values

    def get_children(self, *types):
        children_objs = OrderedDict()
        if not types:
            types = self.get_all_child_types()
        for child_type in types:
            output = self.get_attribute('children' + '-' + child_type)
            children_objs.update(self._build_children_objs(child_type, output.split(' ')))
        return children_objs.values()

    def get_all_child_types(self):
        children = self.get_attribute('children').split()
        return list(set([m.group(1) for c in children for m in [re.search('(.*\D+)\d+', c)]]))

    def set_attributes(self, apply_=False, **attributes):
        self.api.config(self.obj_ref(), **attributes)
        if apply_:
            self.api.apply()

    def set_active(self, active):
        self.set_attributes(Active=active)

    def set_targets(self, apply_=False, **attributes):
        attributes_targets = {}
        for attribute, value in attributes.items():
            attributes_targets[attribute + '-targets'] = value
        self.set_attributes(apply_, **attributes_targets)

    def set_sources(self, apply_=False, **attributes):
        attributes_targets = {}
        for attribute, value in attributes.items():
            attributes_targets[attribute + '-sources'] = value
        self.set_attributes(apply_, **attributes_targets)

    def get_name(self):
        return self.get_attribute('Name')

    def get_active(self):
        return self.get_attribute('Active')

    def test_command_rc(self, attribute):
        status = self.api.command_rc[attribute].lower()
        if status and 'passed' not in status and 'successful' not in status:
            raise TgnError('{} = {}'.format(attribute, status))

    @classmethod
    def send_arp_ns(cls, *objects):
        """ Send ARP and NS for ports, devices or stream blocks. """
        StcObject.api.perform('ArpNdStart', HandleList=build_obj_ref_list(objects))

    @classmethod
    def get_arp_cache(self, *objects):
        arp_table = []
        for obj in objects:
            obj.command('ArpNdUpdateArpCache', HandleList=obj.obj_ref())
            arp_cache = obj.get_child('ArpCache')
            arp_table += arp_cache.get_list_attribute('ArpCacheData')
        return arp_table