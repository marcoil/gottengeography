
"""Test all manner of drag & drop actions."""

from gi.repository import Clutter

from gg.common import Struct, photos, points, selected

from test import setup, teardown
from test import gui, DEMOFILES, random_coord

def test_drags_from_external_source():
    """Make sure that we can load photos dragged in"""
    data = Struct({'get_text': lambda: '\n'.join(DEMOFILES)})
    teardown()
    assert len(photos) == 0
    assert len(points) == 0
    
    gui.drag.photo_drag_end(None, None, 20, 20, data,
                            None, None, True)
    assert len(photos) == 6
    assert len(points) == 374
    
    teardown()
    assert len(photos) == 0
    assert len(points) == 0
    setup()

def test_drags_on_map():
    """Drag the ChamplainLabels around the map"""
    assert photos
    for photo in photos.values():
        photo.label.set_location(random_coord(80), random_coord(180))
        photo.label.emit('drag-finish', Clutter.Event())
        assert photo.label.get_latitude() == photo.latitude
        assert photo.label.get_longitude() == photo.longitude
        assert len(photo.pretty_geoname()) > 5

def test_drags_from_liststore():
    """Drag from the GtkListStore to the map"""
    assert photos
    for photo in photos.values():
        old = [photo.latitude, photo.longitude]
        selected.add(photo)
        data = Struct({'get_text': lambda: photo.filename})
        gui.drag.photo_drag_end(None, None, 20, 20, data,
                                None, None, True)
        assert photo.label.get_latitude() == photo.latitude
        assert photo.label.get_longitude() == photo.longitude
        assert len(photo.pretty_geoname()) > 5
        assert photo.latitude != old[0]
        assert photo.longitude != old[1]

