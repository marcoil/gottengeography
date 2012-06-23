
"""Test all manner of drag & drop actions."""

from gi.repository import Clutter

from gg.common import Struct, points, selected
from gg.photos import Photograph
from gg.label import Label

from test import setup, teardown
from test import gui, DEMOFILES, random_coord

def test_drags_from_external_source():
    """Make sure that we can load photos dragged in"""
    data = Struct({'get_text': lambda: '\n'.join(DEMOFILES)})
    assert len(Photograph.instances) == 0
    assert len(points) == 0
    
    gui.drag.photo_drag_end(None, None, 20, 20, data,
                            None, None, True)
    assert len(Photograph.instances) == 6
    assert len(points) == 374

def test_drags_on_map():
    """Drag the ChamplainLabels around the map"""
    gui.open_files(DEMOFILES)
    assert Photograph.instances
    assert Label.instances
    for label in Label.instances:
        label.set_location(random_coord(80), random_coord(180))
        label.emit('drag-finish', Clutter.Event())
        assert label.get_latitude() == label.photo.latitude
        assert label.get_longitude() == label.photo.longitude
        label.photo.lookup_geodata()
        assert len(label.photo.geoname) > 5

def test_drags_from_liststore():
    """Drag from the GtkListStore to the map"""
    gui.open_files(DEMOFILES)
    assert Photograph.instances
    assert Label.instances
    for photo in Photograph.instances:
        old = [photo.latitude, photo.longitude]
        selected.add(photo)
        data = Struct({'get_text': lambda: photo.filename})
        gui.drag.photo_drag_end(None, None, 20, 20, data,
                                None, None, True)
        assert Label(photo).get_latitude() == photo.latitude
        assert Label(photo).get_longitude() == photo.longitude
        photo.lookup_geodata()
        assert len(photo.geoname) > 5
        assert photo.latitude != old[0]
        assert photo.longitude != old[1]

