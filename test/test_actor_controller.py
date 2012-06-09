
"""Test various ClutterActors related to the map."""

from gi.repository import Clutter, Champlain

from gg.common import Widgets, map_view
from gg.xmlfiles import Polygon
from gg.actor import MAP_SOURCES, black, xhair, scale, animate_in

from test import gui, gst

def test_strings():
    """Coordinate and Google Maps links should be accurate"""
    link = Widgets.maps_link
    
    map_view.center_on(50, 50)
    assert link.get_uri().startswith(
        'http://maps.google.com/maps?ll=50.0,50.0&amp;spn=')
    
    map_view.center_on(-10, -30)
    assert link.get_uri().startswith(
        'http://maps.google.com/maps?ll=-10.0,-30.0&amp;spn=')

def test_configuration():
    """Reticulating splines"""
    animate_in(20)
    assert black.get_width() == map_view.get_width()
    assert isinstance(xhair, Champlain.Point)

def test_map_sources():
    """The map should have multiple sources"""
    map_view.set_map_source(MAP_SOURCES['osm-cyclemap'])
    assert gst.get_string('map-source-id') == 'osm-cyclemap'
    
    gst.set_string('map-source-id', 'mff-relief')
    assert map_view.get_map_source().get_id() == 'mff-relief'
    
    menu = Widgets.map_source_menu.get_active().get_group()
    assert menu
    for menu_item in menu:
        menu_item.set_active(True)
        assert map_view.get_map_source().get_name() == menu_item.get_label()

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

