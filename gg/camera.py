# Author: Robert Park <rbpark@exolucere.ca>, (C) 2012
# Copyright: See COPYING file included with this distribution.

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

from widgets import Builder, Widgets
from territories import tz_regions, get_timezone
from common import GSettings, memoize, bind_properties


@memoize
class Camera(GObject.GObject):
    """Store per-camera configuration in GSettings."""
    instances = {}
    cameras = instances.viewvalues()
    
    offset = GObject.property(
        type = int,
        default = 0,
        minimum = -3600,
        maximum = 3600)
    
    timezone_method = GObject.property(
        type = str,
        default = 'system')
    
    found_timezone = GObject.property(
        type = str,
        default = '')
    
    timezone_region = GObject.property(
        type = str,
        default = '')
    
    timezone_city = GObject.property(
        type = str,
        default = '')
    
    @GObject.property(type=int, default=0)
    def num_photos(self):
        """Read-only count of the loaded photos taken by this camera."""
        return len(self.photos)
    
    @staticmethod
    def generate_id(info):
        """Identifies a camera by serial number, make, and model.
        
        The ids look like: 12345_nikon_wonder_cam
        The names look like: 'Nikon Wonder Cam'
        """
        maker = info.get('Make', '').capitalize()
        model = info.get('Model', '')
        
        # Some makers put their name twice
        model = model if model.startswith(maker) else maker + ' ' + model
        
        camera_id = '_'.join(sorted(info.values())).lower().replace(' ', '_')
        
        return (camera_id.strip(' _') or 'unknown_camera',
                model.strip() or _('Unknown Camera'))
    
    @staticmethod
    def set_all_found_timezone(timezone):
        """"Set all cameras to the given timezone."""
        for camera in Camera.cameras:
            camera.found_timezone = timezone
    
    @staticmethod
    def timezone_handler_all():
        """Update all of the photos from all of the cameras."""
        for camera in Camera.cameras:
            camera.timezone_handler()
    
    def __init__(self, camera_id):
        """Bind self's properties to GSettings."""
        GObject.GObject.__init__(self)
        self.id = camera_id
        self.photos = set()
        
        # Bind properties to settings
        self.gst = GSettings('camera', camera_id)
        for prop in ('offset', 'timezone-method', 'timezone-region',
                     'timezone-city', 'found-timezone'):
            self.gst.bind(prop, self)
        
        # Get notifications when properties are changed
        self.connect('notify::offset', self.offset_handler)
        self.connect('notify::timezone-method', self.timezone_handler)
        self.connect('notify::timezone-city', self.timezone_handler)
    
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
        photo.camera = self
        self.photos.add(photo)
        self.notify('num_photos')
    
    def remove_photo(self, photo):
        """Removes photo from the list of photos taken by this camera."""
        photo.camera = None
        self.photos.discard(photo)
        self.notify('num_photos')


def display_offset(offset, value, add, subtract):
    """Display minutes and seconds in the offset GtkScale."""
    seconds, minutes = split_float(abs(value) / 60)
    return (subtract if value < 0 else add) % (minutes, int(seconds * 60))


@memoize
class CameraView(Gtk.Box):
    """A widget to show camera settings."""
    instances = {}
    
    def __init__(self, camera, name):
        Gtk.Box.__init__(self)
        self.camera = camera
        
        self.widgets = Builder('camera')
        self.add(self.widgets.camera_settings)
        
        self.widgets.camera_label.set_text(name)
        
        self.set_counter_text()
        
        # GtkScale allows the user to correct the camera's clock.
        scale = self.widgets.offset
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
        region_combo = self.widgets.timezone_region
        cities_combo = self.widgets.timezone_city
        for name in tz_regions:
            region_combo.append(name, name)
        
        self.bindings = {}
        for setting in ('region', 'city', 'method'):
            name = 'timezone_' + setting
            self.bindings[setting] = bind_properties(
                self.widgets[name], 'active-id', camera, name.replace('_', '-'))
        
        region_combo.connect('changed', self.region_handler, cities_combo)
        region_combo.set_active_id(camera.timezone_region)
        cities_combo.set_active_id(camera.timezone_city)
        
        method_combo = self.widgets.timezone_method
        method_combo.connect('changed', self.method_handler)
        method_combo.set_active_id(camera.timezone_method)
        
        Widgets.timezone_regions_group.add_widget(region_combo)
        Widgets.timezone_cities_group.add_widget(cities_combo)
        Widgets.cameras_group.add_widget(self.widgets.camera_settings)
        
        camera.connect('notify::num-photos', self.set_counter_text)
        
        Widgets.cameras_view.add(self)
        self.show_all()
    
    def method_handler(self, method):
        """Only show manual tz selectors when necessary."""
        visible = method.get_active_id() == 'custom'
        self.widgets.timezone_region.set_visible(visible)
        self.widgets.timezone_city.set_visible(visible)
    
    def region_handler(self, region, cities):
        """Populate the list of cities when a continent is selected."""
        cities.remove_all()
        for city in get_timezone(region.get_active_id(), []):
            cities.append(city, city)
    
    def set_counter_text(self, *ignore):
        """Display to the user how many photos are loaded."""
        num = self.camera.num_photos
        self.widgets.count_label.set_text(
            {0:   _('No photos loaded.'),
             1:   _('One photo loaded.')}.get(
             num, _('%d photos loaded.') % num))

