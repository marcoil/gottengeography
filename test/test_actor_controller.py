
"""Test various ClutterActors related to the map."""

from gi.repository import Clutter, Champlain

from gg.common import Widgets, map_view
from gg.xmlfiles import Polygon
from gg.actor import MAP_SOURCES

from test import gui, gst

def test_strings():
    """Coordinate and Google Maps links should be accurate"""
    link = Widgets.maps_link
    
    map_view.center_on(50, 50)
    assert gui.actors.label.get_text() == 'N 50.00000, E 50.00000'
    assert link.get_uri().startswith(
        'http://maps.google.com/maps?ll=50.0,50.0&amp;spn=')
    
    map_view.center_on(-10, -30)
    assert gui.actors.label.get_text() == 'S 10.00000, W 30.00000'
    assert link.get_uri().startswith(
        'http://maps.google.com/maps?ll=-10.0,-30.0&amp;spn=')

def test_crosshair_rotation():
    """Ensure crosshair is properly rotated"""
    for rot in gui.actors.xhair.get_rotation(Clutter.RotateAxis.Z_AXIS):
        assert rot == 0
    
    gui.actors.animate_in(20)
    assert gui.actors.black.get_width() == map_view.get_width()
    assert gui.actors.xhair.get_rotation(Clutter.RotateAxis.Z_AXIS)[0] == 45

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

