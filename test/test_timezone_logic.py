
"""Timezones are tricky business."""

from gg.common import GSettings
from gg.photos import Photograph
from gg.camera import known_cameras
from test import gui, setup, teardown, DEMOFILES

def test_timezone_lookups():
    """Ensure that the timezone can be discovered from the map"""
    # Be very careful to reset everything so that we're sure that
    # we're not just finding the timezone from gsettings.
    teardown()
    gst = GSettings('camera', 'canon_canon_powershot_a590_is')
    gst.reset('found-timezone')
    gst.reset('offset')
    gst.set_string('timezone-method', 'lookup')
    known_cameras.clear()
    
    # Open just the GPX
    gui.open_files([DEMOFILES[3]])
    
    # At this point the camera hasn't been informed of the timezone
    assert gst.get_string('found-timezone') == ''
    
    # Opening a photo should place it on the map.
    gui.open_files([DEMOFILES[0]])
    assert gst.get_string('found-timezone') == 'America/Edmonton'
    assert Photograph.instances
    assert known_cameras
    
    photo = Photograph.instances.values()[0]
    assert photo.latitude == 53.530476
    assert photo.longitude == -113.450635

def test_manual_timezone():
    """The wrong timezone will clamp the photo to the end of the track"""
    assert known_cameras
    assert Photograph.instances
    camera = known_cameras.values()[0]
    camera.gst.set_string('timezone-method', 'custom')
    camera.gst.set_string('timezone-region', 'America')
    camera.gst.set_string('timezone-city', 'Winnipeg')
    
    photo = Photograph.instances.values()[0]
    assert photo.latitude == 53.52263
    assert photo.longitude == -113.448979

