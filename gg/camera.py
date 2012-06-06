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

from gi.repository import GObject, Gtk
from math import modf as split_float
from gettext import gettext as _
from time import tzset
from os import environ

from territories import tz_regions, get_timezone
from common import GSettings, Builder, Widgets, memoize, bind_properties

gproperty = GObject.property
cameras_view = Widgets.cameras_view

@memoize
class Camera(GObject.GObject):
    """Store per-camera configuration in GSettings."""
    instances = {}
    
    # Properties definitions
    name = gproperty(type = str,
                     default = '')
    offset = gproperty(type = int,
                       default = 0,
                       minimum = -3600,
                       maximum = 3600)
    timezone_method = gproperty(type = str,
                                default = 'system')
    found_timezone = gproperty(type = str,
                               default = '')
    timezone_region = gproperty(type = str,
                                default = '')
    timezone_city = gproperty(type = str,
                                default = '')
    num_photos = gproperty(type = int,
                           default = 0)
    
    @staticmethod
    def generate_id(info):
        """Identifies a camera by serial number, make, and model.
        
        The ids look like: 12345_nikon_wonder_cam
        """
        return '_'.join(sorted(info.values())).lower().replace(' ', '_')  \
            or 'unknown_camera'
    
    @staticmethod
    def build_name(info):
        """Pretty prints the make and model of the camera."""
        maker = info.get('Make', '').capitalize()
        model = info.get('Model', '')
        if not maker + model:
            return _('Unknown Camera')
        
        # Some makers put their name twice
        return model if model.startswith(maker) else maker + ' ' + model
    
    @staticmethod
    def set_all_found_timezone(timezone):
        """"Set all cameras to the given timezone."""
        for camera in Camera.instances.values():
            camera.set_found_timezone(timezone)
    
    @staticmethod
    def timezone_handler_all():
        """Update all of the photos from all of the cameras."""
        for camera in Camera.instances.values():
            camera.timezone_handler()
    
    def __init__(self, camera_id, info):
        """Bind self's properties to GSettings."""
        GObject.GObject.__init__(self)
        self.id = camera_id
        self.photos = set()
        
        # Bind properties to settings
        self.gst = GSettings('camera', camera_id)
        self.gst.bind('name', self)
        self.gst.bind('offset', self)
        self.gst.bind('timezone-method', self)
        self.gst.bind('timezone-region', self)
        self.gst.bind('timezone-city', self)
        self.gst.bind('found-timezone', self)
        
        # If we don't have a proper name, build it from the info
        if not self.name:
            self.name = Camera.build_name(info)
        
        # Get notifications when properties are changed
        self.connect('notify::offset', self.offset_handler)
        self.connect('notify::timezone-method', self.timezone_handler)
        self.connect('notify::timezone-city', self.timezone_handler)
        
        CameraView(self)
    
    def set_found_timezone(self, found):
        """Store discovered timezone in GSettings."""
        self.found_timezone = found
    
    def timezone_handler(self, *ignore):
        """Set the timezone to the chosen zone and update all photos."""
        environ['TZ'] = ''
        if self.timezone_method == 'lookup':
            # Note that this will gracefully fallback on system timezone
            # if no timezone has actually been found yet.
            environ['TZ'] = self.found_timezone
        elif self.timezone_method == 'custom' and \
             self.timezone_region and self.timezone_city:
            environ['TZ'] = '/'.join(
                [self.timezone_region, self.timezone_city])
        
        tzset()
        self.offset_handler()
    
    def offset_handler(self, *ignore):
        """When the offset is changed, update the loaded photos."""
        for photo in self.photos:
            photo.calculate_timestamp(self.offset)
    
    def add_photo(self, photo):
        """Adds photo to the list of photos taken by this camera."""
        if photo.camera is not None:
            photo.camera.remove_photo(photo)
        photo.camera = self
        self.photos.add(photo)
        self.num_photos += 1
    
    def remove_photo(self, photo):
        """Removes photo from the list of photos taken by this camera."""
        photo.camera = None
        self.photos.discard(photo)
        self.num_photos -= 1

def display_offset(offset, value, add, subtract):
    """Display minutes and seconds in the offset GtkScale."""
    seconds, minutes = split_float(abs(value) / 60)
    return (subtract if value < 0 else add) % (minutes, int(seconds * 60))

class CameraView(Gtk.Box):
    """A widget to show a camera data."""
    
    def __init__(self, camera):
        Gtk.Box.__init__(self)
        self.camera = camera
        
        builder = Builder('camera')
        self.add(builder.camera_settings)
        
        label = builder.camera_label
        label.set_text(camera.name)
        
        self.counter = builder.count_label
        self.set_counter_text(camera, None)
        
        # GtkScale allows the user to correct the camera's clock.
        scale = builder.offset
        scale.connect('format-value', display_offset,
                           _('Add %dm, %ds to clock.'),
                           _('Subtract %dm, %ds from clock.'))
        
        # NOTE: This has to be so verbose because of
        # https://bugzilla.gnome.org/show_bug.cgi?id=675582
        # Also, it seems SYNC_CREATE doesn't really work.
        scale.set_value(camera.offset)
        self.scale_binding = bind_properties(scale.get_adjustment(),
                                             'value',
                                             camera,
                                             'offset')
        
        # These two ComboBoxTexts are used for choosing the timezone manually.
        # They're hidden to reduce clutter when not needed.
        self.region_combo = builder.timezone_region
        self.cities_combo = builder.timezone_cities
        for name in tz_regions:
            self.region_combo.append(name, name)
        
        self.region_binding = bind_properties(self.region_combo, 'active-id',
                                              camera, 'timezone-region')
        self.region_combo.connect('changed', self.region_handler,
                                  self.cities_combo)
        self.region_combo.set_active_id(camera.timezone_region)
        
        self.cities_binding = bind_properties(self.cities_combo, 'active-id',
                                              camera, 'timezone-city')
        self.cities_combo.set_active_id(camera.timezone_city)
        
        self.method_combo = builder.timezone_method
        self.method_binding = bind_properties(self.method_combo, 'active-id',
                                              camera, 'timezone-method')
        self.method_combo.connect('changed', self.method_handler)
        self.method_combo.set_active_id(camera.timezone_method)
        
        Widgets.timezone_regions_group.add_widget(self.region_combo)
        Widgets.timezone_cities_group.add_widget(self.cities_combo)
        Widgets.cameras_group.add_widget(self.get_children()[0])
        
        camera.connect('notify::num-photos', self.set_counter_text)
        
        cameras_view.attach_next_to(self, None, Gtk.PositionType.BOTTOM, 1, 1)
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
    
    def set_counter_text(self, *ignore):
        """Display to the user how many photos are loaded."""
        num = self.camera.num_photos
        text = _('No photos loaded.')
        if num is 1:
            text = _('One photo loaded.')
        elif num > 1:
            text = _('%d photos loaded.') % num 
        self.counter.set_text(text)

