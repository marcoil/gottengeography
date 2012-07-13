
"""Ensure that it's possible to navigate the map."""

from gi.repository import Gdk

from gg.widgets import Widgets, MapView
from gg.navigation import move_by_arrow_keys

from test import Gst, random_coord

def test_history():
    """The history should keep track of where we go"""
    coords = [[
        MapView.get_center_latitude(),
        MapView.get_center_longitude()
    ]]
    MapView.emit('realize')
    assert len(Widgets.main.get_title()) > 5
    assert Widgets.main.get_title().index(',') > 0
    
    lat = random_coord(90)
    lon = random_coord(180)
    MapView.center_on(lat, lon)
    coords.append([lat, lon])
    
    assert coords[0][0] - Gst.get('history')[-1][0] < 1e-6
    assert coords[0][1] - Gst.get('history')[-1][1] < 1e-6

def test_zoom_buttons():
    """Zoom buttons function correctly"""
    lat = random_coord(80)
    lon = random_coord(170)
    MapView.center_on(lat, lon)
    
    zoom_in  = Widgets.zoom_in_button
    zoom_out = Widgets.zoom_out_button
    MapView.set_zoom_level(0)
    assert not zoom_out.get_sensitive()
    assert zoom_in.get_sensitive()
    
    zoom_in.emit('clicked')
    assert zoom_out.get_sensitive()
    assert zoom_in.get_sensitive()
    assert 1 == MapView.get_zoom_level()
    
    zoom_in.emit('clicked')
    assert 2 == MapView.get_zoom_level()
    
    zoom_in.emit('clicked')
    assert 3 == MapView.get_zoom_level()
    
    zoom_out.emit('clicked')
    assert 2 == MapView.get_zoom_level()
    
    MapView.set_zoom_level(MapView.get_max_zoom_level() - 1)
    assert zoom_out.get_sensitive()
    assert zoom_in.get_sensitive()
    
    zoom_in.emit('clicked')
    assert zoom_out.get_sensitive()
    assert not zoom_in.get_sensitive()
    assert MapView.get_max_zoom_level() == MapView.get_zoom_level()

def test_arrow_keys():
    """The user can navigate by arrow keys"""
    Widgets.back_button.emit('clicked')
    
    MapView.set_zoom_level(10)
    
    lat = MapView.get_center_latitude()
    lon = MapView.get_center_longitude()
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Left'), None)
    assert lat - MapView.get_center_latitude() < 1e-6
    assert lon > MapView.get_center_longitude()
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Right'), None)
    assert lat - MapView.get_center_latitude() < 1e-6
    assert lon - MapView.get_center_longitude() < 1e-2
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Right'), None)
    assert lon < MapView.get_center_longitude()
    assert lat - MapView.get_center_latitude() < 1e-6
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Left'), None)
    assert lon - MapView.get_center_longitude() < 1e-2
    assert lat - MapView.get_center_latitude() < 1e-6
    
    lon = MapView.get_center_longitude()
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Up'), None)
    assert lon - MapView.get_center_longitude() < 1e-6
    assert lat < MapView.get_center_latitude()
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Down'), None)
    assert lon - MapView.get_center_longitude() < 1e-6
    assert lat - MapView.get_center_latitude() < 1e-6
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Down'), None)
    assert lon - MapView.get_center_longitude() < 1e-6
    assert lat > MapView.get_center_latitude()
    
    move_by_arrow_keys(None, None, Gdk.keyval_from_name('Up'), None)
    assert lon - MapView.get_center_longitude() < 1e-6
    assert lat - MapView.get_center_latitude() < 1e-6


