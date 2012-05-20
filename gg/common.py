# GottenGeography - Common things used throughout the app.
# Copyright (C) 2010 Robert Park <rbpark@exolucere.ca>
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

from __future__ import division

from gi.repository import Gtk, Gio, GLib
from gi.repository import GtkChamplain, Champlain
from os.path import join

from build_info import PKG_DATA_DIR
from version import PACKAGE

class metadata:
    """Records clock offset and times of first/last gps track points"""
    delta = 0
    omega = float('-inf')
    alpha = float('inf')

# This function is the embodiment of my applications core logic.
# Everything else is just implementation details.
def auto_timestamp_comparison(photo, points):
    """Use GPX data to calculate photo coordinates and elevation.
    
    photo:    A Photograph object.
    points:   A dictionary mapping epoch seconds to ChamplainCoordinates.
    """
    if photo.manual or len(points) < 2:
        return
        
    # Add the user-specified clock offset (metadata.delta) to the photo
    # timestamp, and then keep it within the range of available GPX points.
    # The result is in epoch seconds, just like the keys of the 'points' dict.
    stamp = min(max(
        metadata.delta + photo.timestamp,
        metadata.alpha),
        metadata.omega)
    
    try:
        point = points[stamp] # Try to use an exact match,
        lat   = point.lat     # if such a thing were to exist.
        lon   = point.lon     # It's more likely than you think. 50%
        ele   = point.ele     # of the included demo data matches here.
    
    except KeyError:
        # Find the two points that are nearest (in time) to the photo.
        hi = min([point for point in points if point > stamp])
        lo = max([point for point in points if point < stamp])
        hi_point = points[hi]
        lo_point = points[lo]
        hi_ratio = (stamp - lo) / (hi - lo)  # Proportional amount of time
        lo_ratio = (hi - stamp) / (hi - lo)  # between each point & the photo.
        
        # Find intermediate values using the proportional ratios.
        lat = ((lo_point.lat * lo_ratio)  +
               (hi_point.lat * hi_ratio))
        lon = ((lo_point.lon * lo_ratio)  +
               (hi_point.lon * hi_ratio))
        ele = ((lo_point.ele * lo_ratio)  +
               (hi_point.ele * hi_ratio))
    
    photo.set_location(lat, lon, ele)


class Builder(Gtk.Builder):
    """Load GottenGeography's UI definitions."""
    def __init__(self):
        Gtk.Builder.__init__(self)
        
        self.set_translation_domain(PACKAGE)
        self.add_from_file(join(PKG_DATA_DIR, PACKAGE + '.ui'))


class GSettings(Gio.Settings):
    """Override GSettings to be more useful to me."""
    get = Gio.Settings.get_value
    
    def __init__(self):
        Gio.Settings.__init__(self, 'ca.exolucere.' + PACKAGE)
        
        # These are used to avoid infinite looping.
        self._ignore_key_changed = False
        self._ignore_prop_changed = True
    
    def bind(self, key, widget, prop, flags=Gio.SettingsBindFlags.DEFAULT):
        """Don't make me specify the default flags every time."""
        Gio.Settings.bind(self, key, widget, prop, flags)
    
    def set(self, key, value):
        """Convert arrays to GVariants.
        
        This makes it easier to set the back button history and the window size.
        """
        use_matrix = type(value) is list
        do_override = type(value) is tuple or use_matrix
        Gio.Settings.set_value(self, key, value if not do_override else
            GLib.Variant('aad' if use_matrix else '(ii)', value))
    
    def bind_with_convert(self, key, widget, prop, key_to_prop, prop_to_key):
        """Recreate g_settings_bind_with_mapping from scratch.
        
        This method was shamelessly stolen from John Stowers'
        gnome-tweak-tool on May 14, 2012.
        """
        def key_changed(settings, key):
            if self._ignore_key_changed: return
            orig_value = self[key]
            converted_value = key_to_prop(orig_value)
            self._ignore_prop_changed = True
            try:
                widget.set_property(prop, converted_value)
            except TypeError:
                print "TypeError: %s not a valid %s." % (converted_value, prop)
            self._ignore_prop_changed = False
        
        def prop_changed(widget, param):
            if self._ignore_prop_changed: return
            orig_value = widget.get_property(prop)
            converted_value = prop_to_key(orig_value)
            self._ignore_key_changed = True
            try:
                self[key] = converted_value
            except TypeError:
                print "TypeError: %s not a valid %s." % (converted_value, key)
            self._ignore_key_changed = False
        
        self.connect("changed::" + key, key_changed)
        widget.connect("notify::" + prop, prop_changed)
        key_changed(self,key) # init default state


class ChamplainEmbedder(GtkChamplain.Embed):
    """Put the map view onto the main window."""
    
    def __init__(self):
        GtkChamplain.Embed.__init__(self)
        get_obj("map_container").add_with_viewport(self)


class Polygon(Champlain.PathLayer):
    """Extend a Champlain.PathLayer to do things more the way I like them."""
    
    def __init__(self):
        Champlain.PathLayer.__init__(self)
        self.set_stroke_width(4)
    
    def append_point(self, latitude, longitude, elevation):
        """Simplify appending a point onto a polygon."""
        coord = Champlain.Coordinate.new_full(latitude, longitude)
        coord.lat = latitude
        coord.lon = longitude
        coord.ele = elevation
        self.add_node(coord)
        return coord


class Struct:
    """This is a generic object which can be assigned arbitrary attributes."""
    
    def __init__(self, attributes={}):
        self.__dict__.update(attributes)


class CommonAttributes:
    """Define attributes required by all Controller classes.
    
    This class is never instantiated, it is only inherited by classes that
    need to manipulate the map, or the loaded photos.
    """
    tracks    = {}
    photo     = {}


# Initialize GtkBuilder, Champlain, and GSettings
get_obj  = Builder().get_object
map_view = ChamplainEmbedder().get_view()
gst      = GSettings()

# These variables are used for sharing data between classes
selected = set()
modified = set()
polygons = []

