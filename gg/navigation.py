# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Control how the map is navigated."""

from __future__ import division

from gi.repository import Gdk

from widgets import Widgets, MapView
from common import Gst, bind_properties
from gpsmath import Coordinates, valid_coords

def move_by_arrow_keys(accel_group, acceleratable, keyval, modifier):
    """Move the map view by 5% of its length in the given direction."""
    key, view = Gdk.keyval_name(keyval), MapView
    factor    = (0.45 if key in ('Up', 'Left') else 0.55)
    lat       = view.get_center_latitude()
    lon       = view.get_center_longitude()
    if key in ('Up', 'Down'):
        lat = view.y_to_latitude(view.get_height() * factor)
    else:
        lon = view.x_to_longitude(view.get_width() * factor)
    if valid_coords(lat, lon):
        view.center_on(lat, lon)

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

for key in ['latitude', 'longitude', 'zoom-level']:
    Gst.bind(key, MapView, key)

MapView.connect('notify::zoom-level', zoom_button_sensitivity,
    Widgets.zoom_in_button.set_sensitive, Widgets.zoom_out_button.set_sensitive)
MapView.connect('realize', remember_location)

center = Coordinates()
lat_binding = bind_properties(MapView, 'latitude', center)
lon_binding = bind_properties(MapView, 'longitude', center)
center.do_modified()
center_binding = bind_properties(center, 'geoname', Widgets.main, 'title')
center.timeout_seconds = 10 # Reduces the rate that the titlebar updates

