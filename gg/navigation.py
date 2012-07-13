# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Control how the map is navigated."""

from __future__ import division

from gi.repository import GtkClutter
GtkClutter.init([])

from gi.repository import Gdk

from common import Gst
from gpsmath import valid_coords
from widgets import Widgets, MapView

def move_by_arrow_keys(accel_group, acceleratable, keyval, modifier):
    """Move the map view by 5% of its length in the given direction."""
    key = Gdk.keyval_name(keyval)
    factor = 0.45 if key in ('Up', 'Left') else 0.55
    if key in ('Up', 'Down'):
        lat = MapView.y_to_latitude(MapView.get_height() * factor)
        lon = MapView.get_center_longitude()
    else:
        lat = MapView.get_center_latitude()
        lon = MapView.x_to_longitude(MapView.get_width() * factor)
    if valid_coords(lat, lon):
        MapView.center_on(lat, lon)

def remember_location(view):
    """Add current location to history stack."""
    history = list(Gst.get('history'))
    location = tuple([view.get_property(x) for x in
        ('latitude', 'longitude', 'zoom-level')])
    if history[-1] != location:
        history.append(location)
    Gst.set_history(history[-30:])

def go_back(*ignore):
    """Return the map view to where the user last set it."""
    history = list(Gst.get('history'))
    lat, lon, zoom = history.pop()
    if valid_coords(lat, lon):
        MapView.set_zoom_level(zoom)
        MapView.center_on(lat, lon)
    if len(history) > 1:
        Gst.set_history(history)
    else:
        Gst.reset('history')

def zoom_button_sensitivity(view, signal, in_sensitive, out_sensitive):
    """Ensure zoom buttons are only sensitive when they need to be."""
    zoom = view.get_zoom_level()
    out_sensitive(view.get_min_zoom_level() != zoom)
    in_sensitive( view.get_max_zoom_level() != zoom)

for prop in ('latitude', 'longitude', 'zoom-level'):
    Gst.bind(prop, MapView, prop)

MapView.connect('notify::zoom-level', zoom_button_sensitivity,
    Widgets.zoom_in_button.set_sensitive, Widgets.zoom_out_button.set_sensitive)
MapView.connect('realize', remember_location)

