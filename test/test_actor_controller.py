
"""Test various ClutterActors related to the map."""

from gi.repository import Clutter, Champlain

from gg.xmlfiles import Polygon
from gg.widgets import Widgets, MapView
from gg.actor import MAP_SOURCES, Box, Crosshair, animate_in

from test import Gst, gui

def test_map_sources():
    """The map should have multiple sources"""
    MapView.set_map_source(MAP_SOURCES['osm-cyclemap'])
    assert Gst.get_string('map-source-id') == 'osm-cyclemap'
    
    Gst.set_string('map-source-id', 'mff-relief')
    assert MapView.get_map_source().get_id() == 'mff-relief'
    
    menu = Widgets.map_source_menu.get_active().get_group()
    assert menu
    for menu_item in menu:
        menu_item.set_active(True)
        assert MapView.get_map_source().get_name() == menu_item.get_label()

def test_polygons():
    """Polygons should behave"""
    polygon = Polygon()
    assert isinstance(polygon, Champlain.PathLayer)
    
    point = polygon.append_point(0, 0, 0)
    assert isinstance(point, Champlain.Coordinate)
    assert point.lat == 0
    assert point.lon == 0
    assert point.ele == 0
    
    point = polygon.append_point(45, 90, 1000)
    assert isinstance(point, Champlain.Coordinate)
    assert point.lat == 45
    assert point.lon == 90
    assert point.ele == 1000
    
    assert len(polygon.get_nodes()) == 2

