
"""Ensure that it's possible to navigate the map."""

from gi.repository import Gdk

from gg.common import Widgets, map_view
from gg.navigation import move_by_arrow_keys

from test import gst, random_coord

def test_history():
    """The history should keep track of where we go"""
    coords = [[
        map_view.get_center_latitude(),
        map_view.get_center_longitude()
    ]]
    map_view.emit('realize')
    assert len(Widgets.main.get_title()) > 5
    assert Widgets.main.get_title().index(',') > 0
    
    lat = random_coord(90)
    lon = random_coord(180)
    map_view.center_on(lat, lon)
    coords.append([lat, lon])
    
    assert coords[0][0] - gst.get('history')[-1][0] < 1e-6
    assert coords[0][1] - gst.get('history')[-1][1] < 1e-6

def test_zoom_buttons():
    """Zoom buttons function correctly"""
    lat = random_coord(80)
    lon = random_coord(170)
    map_view.center_on(lat, lon)
    
    zoom_in  = Widgets.zoom_in_button
    zoom_out = Widgets.zoom_out_button
    map_view.set_zoom_level(0)
    assert not zoom_out.get_sensitive()
    assert zoom_in.get_sensitive()
    
    zoom_in.emit('clicked')
    assert zoom_out.get_sensitive()
    assert zoom_in.get_sensitive()
    assert 1 == map_view.get_zoom_level()
    
    zoom_in.emit('clicked')
    assert 2 == map_view.get_zoom_level()
    
    zoom_in.emit('clicked')
    assert 3 == map_view.get_zoom_level()
    
    zoom_out.emit('clicked')
    assert 2 == map_view.get_zoom_level()
    
    map_view.set_zoom_level(map_view.get_max_zoom_level() - 1)
    assert zoom_out.get_sensitive()
    assert zoom_in.get_sensitive()
    
    zoom_in.emit('clicked')
    assert zoom_out.get_sensitive()
    assert not zoom_in.get_sensitive()
    assert map_view.get_max_zoom_level() == map_view.get_zoom_level()

def test_arrow_keys():
    """The user can navigate by arrow keys"""
    Widgets.back_button.emit('clicked')
    
    map_view.set_zoom_level(10)
    
    lat = map_view.get_center_latitude()
    lon = map_view.get_center_longitude()
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Left'), None)
    assert lat - map_view.get_center_latitude() < 1e-6
    assert lon > map_view.get_center_longitude()
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Right'), None)
    assert lat - map_view.get_center_latitude() < 1e-6
    assert lon - map_view.get_center_longitude() < 1e-2
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Right'), None)
    assert lon < map_view.get_center_longitude()
    assert lat - map_view.get_center_latitude() < 1e-6
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Left'), None)
    assert lon - map_view.get_center_longitude() < 1e-2
    assert lat - map_view.get_center_latitude() < 1e-6
    
    lon = map_view.get_center_longitude()
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Up'), None)
    assert lon - map_view.get_center_longitude() < 1e-6
    assert lat < map_view.get_center_latitude()
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Down'), None)
    assert lon - map_view.get_center_longitude() < 1e-6
    assert lat - map_view.get_center_latitude() < 1e-6
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Down'), None)
    assert lon - map_view.get_center_longitude() < 1e-6
    assert lat > map_view.get_center_latitude()
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Up'), None)
    assert lon - map_view.get_center_longitude() < 1e-6
    assert lat - map_view.get_center_latitude() < 1e-6


