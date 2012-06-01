# Copyright (C) 2012 Robert Park <rbpark@exolucere.ca>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""The Camera class handles per-camera configuration.

It uniquely identifies each camera model that the user owns and stores
settings such as what timezone to use and how wrong the camera's clock is.
A 'relocatable' GSettings schema is used to persist this data across application
launches.

Note that the Cameras tab will only display the cameras responsible for
creating the currently loaded photos. This means that it's entirely possible
for GSettings to store a camera definition that isn't displayed in the UI.
Rest assured that your camera's settings are simply gone but not forgotten,
and if you want to see the camera in the camera list, you should load a photo
taken by that camera.
"""

from __future__ import division

from gi.repository import Gio, GObject, Gtk
from math import modf as split_float
from gettext import gettext as _
from time import tzset
from os import environ

from territories import tz_regions, get_timezone
from common import get_obj, bind_properties, GSettings, Builder
from version import PACKAGE

known_cameras = {}

empty_camera_label = get_obj('empty_camera_list')

gproperty = GObject.property

class Camera(GObject.GObject):
    """Store per-camera configuration in GSettings."""
    
    # Properties definitions
    name = gproperty(type = str,
                     default = 'Unknown camera')
    offset = gproperty(type = int,
                       default = 0,
                       minimum = -3600,
                       maximum = 3600)
    timezone_method = gproperty(type = str,
                                default = 'system')
    found_timezone = gproperty(type = str,
                               default = '')
    timezone_region = gproperty(type = int,
                                default = -1)
    timezone_cities = gproperty(type = int,
                                default = -1)
    
    # Class methods
    @staticmethod
    def generate_id(info):
        # Turn a Nikon Wonder Cam with serial# 12345 into '12345_nikon_wonder_cam'
        return '_'.join(sorted(info.values())).lower().replace(' ', '_')
    
    @staticmethod
    def build_name(info):
        return info['Model'] if info['Model'] is not '' else _('Unknown camera')
    
    def __init__(self, id, info):
        print 'Creating Camera(%s, %s)' % (id, info)
        """Bind self's properties to GSettings."""
        GObject.GObject.__init__(self)
        self.id = id
        self.photos = set()
        
        # Bind properties to settings
        self.gst = GSettings('camera', id)
        self.gst.bind('name', self)
        self.gst.bind('offset', self)
        self.gst.bind('timezone-method', self, 'timezone-method')
        self.gst.bind('timezone-region', self, 'timezone-region')
        self.gst.bind('timezone-cities', self, 'timezone-cities')
        self.gst.bind('found-timezone', self, 'found-timezone')
        
        # If we don't have a proper name, build it from the info
        if self.name is '':
            self.name = Camera.build_name(info)
        
        # Get notifications when properties are changed
        self.connect('notify::offset', self.offset_handler)
        self.connect('notify::timezone-method', self.timezone_handler)
        self.connect('notify::timezone-cities', self.timezone_handler)
    
    def set_found_timezone(self, found):
        """Store discovered timezone in GSettings."""
        self.found_timezone = found
    
    def timezone_handler(self, object = None, gparamspec = None):
        """Set the timezone to the chosen zone and update all photos."""
        environ['TZ'] = ''
        if self.timezone_method == 'lookup':
            # Note that this will gracefully fallback on system timezone
            # if no timezone has actually been found yet.
            environ['TZ'] = self.gst.get_string('found-timezone')
        elif self.timezone_method == 'custom' and \
             self.timezone_region is not -1 and \
             self.timezone_cities is not -1:
                region = tz_regions[self.timezone_region]
                city   = get_timezone(region)[self.timezone_cities]
                if region is not '' and city is not '':
                    environ['TZ'] = '/'.join([region, city])
        tzset()
        self.offset_handler()
    
    def offset_handler(self, object = None, gparamstr = None):
        """When the offset is changed, update the loaded photos."""
        for photo in self.photos:
            photo.calculate_timestamp(self.offset)

def display_offset(offset, value, add, subtract):
    """Display the offset spinbutton as M:SS."""
    seconds, minutes = split_float(abs(value) / 60)
    return (subtract if value < 0 else add) % (minutes, int(seconds * 60))

class CameraView(Gtk.Box):
    """A widget to show a camera data."""
    
    def __init__(self, camera):
        Gtk.Box.__init__(self)
        self.camera = camera
        
        # TODO find some kind of parent widget that can group these together
        # to make it easier to get them and insert them into places.
        builder = Builder('camera')
        self.add(builder.get_object('camera_settings'))
        
        builder.get_object('camera_label').set_text(camera.name)
        
        # GtkScale allows the user to correct the camera's clock.
        self.scale = builder.get_object('offset')
        self.scale.connect('format-value', display_offset,
                           _('Add %dm, %ds to clock.'),
                           _('Subtract %dm, %ds from clock.'))
            # NOTE: This has to be so verbose because of
        # https://bugzilla.gnome.org/show_bug.cgi?id=675582
        # Also, it seems SYNC_CREATE doesn't really work.
        self.scale.set_value(camera.offset)
        self.scale_binding = bind_properties(self.scale.get_adjustment(), 'value',
                                             camera, 'offset')
        
        # These two ComboBoxTexts are used for choosing the timezone manually.
        # They're hidden to reduce clutter when not needed.
        self.region_combo = builder.get_object('timezone_region')
        self.cities_combo = builder.get_object('timezone_cities')
        for name in tz_regions:
            self.region_combo.append(name, name)
        self.region_binding = bind_properties(self.region_combo, 'active',
                                              camera, 'timezone-region')
        self.region_combo.connect('changed', self.region_handler, self.cities_combo)
        self.region_combo.set_active(camera.timezone_region)
        
        self.cities_binding = bind_properties(self.cities_combo, 'active',
                                              camera, 'timezone-cities')
        self.cities_combo.set_active(camera.timezone_cities)
        
        # TODO we're gonna need some on screen help to explain what it even
        # means to select the method of determining the timezone.
        # Back when this was radio button in a preferences window we had more
        # room for verbosity, but this combobox is *so terse* that I don't
        # really expect anybody to understand it at all.
        self.method_combo = builder.get_object('timezone_method')
        self.method_binding = bind_properties(self.method_combo, 'active-id',
                                              camera, 'timezone-method')
        self.method_combo.connect('changed', self.method_handler)
        self.method_combo.set_active_id(camera.timezone_method)
        
        self.show_all()
    
    def method_handler(self, method):
        """Only show manual tz selectors when necessary."""
        visible = method.get_active_id() == 'custom'
        self.region_combo.set_visible(visible)
        self.cities_combo.set_visible(visible)
    
    def region_handler(self, region, cities):
        """Populate the list of cities when a continent is selected."""
        cities.remove_all()
        for city in get_timezone(region.get_active_id(), []):
            cities.append(city, city)
