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
from os.path import join
from time import tzset
from os import environ

from territories import tz_regions, get_timezone
from common import get_obj, GSettings
from build_info import PKG_DATA_DIR
from version import PACKAGE

BOTTOM = Gtk.PositionType.BOTTOM
RIGHT = Gtk.PositionType.RIGHT

known_cameras = {}

def get_camera(photo):
    """This method caches Camera instances."""
    names = {'Make': 'Unknown Make', 'Model': 'Unknown Camera'}
    keys = ['Exif.Image.' + key for key in names.keys()
        + ['CameraSerialNumber']] + ['Exif.Photo.BodySerialNumber']
    
    for key in keys:
        try:
            names.update({key.split('.')[-1]: photo.exif[key].value})
        except KeyError:
            pass
    
    # Turn a Nikon Wonder Cam with serial# 12345 into '12345_nikon_wonder_cam'
    camera_id = '_'.join(sorted(names.values())).lower().replace(' ', '_')
    
    if camera_id not in known_cameras:
        known_cameras[camera_id] = Camera(
            camera_id, names['Make'], names['Model'])
    
    camera = known_cameras[camera_id]
    camera.photos.add(photo)
    return camera

def display_offset(offset, value, add, subtract):
    """Display the offset spinbutton as M:SS."""
    seconds, minutes = split_float(abs(value) / 60)
    return (subtract if value < 0 else add) % (minutes, int(seconds * 60))


class Camera():
    """Store per-camera configuration in GSettings."""
    
    def __init__(self, camera_id, make, model):
        """Generate Gtk widgets and bind their properties to GSettings."""
        self.photos = set()
        
        # TODO find some kind of parent widget that can group these together
        # to make it easier to get them and insert them into places.
        builder = Gtk.Builder()
        builder.add_from_file(join(PKG_DATA_DIR, 'camera.ui'))
        
        camera_label = builder.get_object('camera_label')
        camera_label.set_text(model)
        
        # GtkScale allows the user to correct the camera's clock.
        offset = builder.get_object('offset')
        offset.connect('value-changed', self.offset_handler)
        offset.connect('format-value', display_offset,
            _('Add %dm, %ds to clock.'),
            _('Subtract %dm, %ds from clock.'))
        
        # These two ComboBoxTexts are used for choosing the timezone manually.
        # They're hidden to reduce clutter when not needed.
        tz_region = builder.get_object('timezone_region')
        tz_cities = builder.get_object('timezone_cities')
        for name in tz_regions:
            tz_region.append(name, name)
        tz_region.connect('changed', self.region_handler, tz_cities)
        tz_cities.connect('changed', self.cities_handler)
        
        # TODO we're gonna need some on screen help to explain what it even
        # means to select the method of determining the timezone.
        # Back when this was radio button in a preferences window we had more
        # room for verbosity, but this combobox is *so terse* that I don't
        # really expect anybody to understand it at all.
        timezone = builder.get_object('timezone_method')
        timezone.connect('changed', self.method_handler, tz_region, tz_cities)
        
        # Push all the widgets into the UI and display them to the user.
        grid = get_obj('cameras_view')
        grid.attach_next_to(camera_label, None, BOTTOM, 2, 1)
        grid.attach_next_to(timezone, None, BOTTOM, 2, 1)
        grid.attach_next_to(tz_region, None, BOTTOM, 1, 1)
        grid.attach_next_to(tz_cities, tz_region, RIGHT, 1, 1)
        grid.attach_next_to(offset, None, BOTTOM, 2, 1)
        grid.show_all()
        
        self.offset    = offset
        self.tz_method = timezone
        self.tz_region = tz_region
        self.tz_cities = tz_cities
        self.camera_id = camera_id
        self.make      = make
        self.model     = model
        
        self.gst = GSettings('camera', camera_id)
        
        self.gst.set_string('make', make)
        self.gst.set_string('model', model)
        
        self.gst.bind('offset', offset.get_adjustment(), 'value')
        self.gst.bind('timezone-method', timezone, 'active-id')
        self.gst.bind('timezone-region', tz_region, 'active')
        self.gst.bind('timezone-cities', tz_cities, 'active')
    
    def method_handler(self, method, region, cities):
        """Only show manual tz selectors when necessary."""
        visible = method.get_active_id() == 'custom'
        region.set_visible(visible)
        cities.set_visible(visible)
        self.set_timezone()
    
    def region_handler(self, region, cities):
        """Populate the list of cities when a continent is selected."""
        cities.remove_all()
        for city in get_timezone(region.get_active_id(), []):
            cities.append(city, city)
    
    def cities_handler(self, cities):
        """When a city is selected, update the chosen timezone."""
        if cities.get_active_id() is not None:
            self.set_timezone()
    
    def set_found_timezone(self, found):
        """Store discovered timezone in GSettings."""
        self.gst.set_string('found-timezone', found)
    
    def set_timezone(self):
        """Set the timezone to the chosen zone and update all photos."""
        environ['TZ'] = ''
        case = lambda x, y=self.tz_method.get_active_id(): x == y
        if case('lookup'):
            # Note that this will gracefully fallback on system timezone
            # if no timezone has actually been found yet.
            environ['TZ'] = self.gst.get_string('found-timezone')
        elif case('custom'):
            region = self.tz_region.get_active_id()
            city   = self.tz_cities.get_active_id()
            if region is not None and city is not None:
                environ['TZ'] = '/'.join([region, city])
        tzset()
        self.offset_handler()
    
    def offset_handler(self, offset=None):
        """When the offset is changed, update the loaded photos."""
        for photo in self.photos:
            photo.calculate_timestamp()
    
    def get_offset(self):
        """Return the currently selected clock offset value."""
        return int(self.offset.get_value())

