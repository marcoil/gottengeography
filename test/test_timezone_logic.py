
"""Timezones are tricky business."""

from gg.camera import Camera
from gg.common import GSettings
from gg.photos import Photograph

from test import GPXFILES, IMGFILES
from test import gui, setup, teardown

def test_timezone_lookups():
    """Ensure that the timezone can be discovered from the map"""
    # Be very careful to reset everything so that we're sure that
    # we're not just finding the timezone from gsettings.
    teardown()
    gst = GSettings('camera', 'canon_canon_powershot_a590_is')
    gst.reset('found-timezone')
    gst.reset('offset')
    gst.set_string('timezone-method', 'lookup')
    Camera.cache.clear()
    
    # Open just the GPX
    gui.open_files(GPXFILES)
    
    # At this point the camera hasn't been informed of the timezone
    assert gst.get_string('found-timezone') == ''
    
    # Opening a photo should place it on the map.
    gui.open_files([IMGFILES[0]])
    print Camera.instances
    print gst.get_string('found-timezone')
    assert gst.get_string('found-timezone') == 'America/Edmonton'
    assert Photograph.instances
    assert Camera.instances
    
    photo = list(Photograph.instances).pop()
    assert photo.latitude == 53.530476
    assert photo.longitude == -113.450635

def test_manual_timezone():
    """The wrong timezone will clamp the photo to the end of the track"""
    assert Camera.instances
    assert Photograph.instances
    photo = list(Photograph.instances).pop()
    camera = photo.camera
    
    camera.gst.set_string('timezone-method', 'offset')
    camera.gst.set_int('utc-offset', -6)
    assert photo.latitude == 53.530476
    assert photo.longitude == -113.450635
    
    camera.gst.set_int('utc-offset', 3)
    assert photo.latitude == 53.52263
    assert photo.longitude == -113.448979
    
    camera.gst.set_int('utc-offset', -10)
    assert photo.latitude == 53.522496
    assert photo.longitude == -113.450537
    
    camera.gst.set_string('timezone-method', 'custom')
    camera.gst.set_string('timezone-region', 'America')
    camera.gst.set_string('timezone-city', 'Vancouver')
    assert photo.latitude == 53.522496
    assert photo.longitude == -113.450537
    
    camera.gst.set_string('timezone-city', 'Winnipeg')
    assert photo.latitude == 53.52263
    assert photo.longitude == -113.448979
    
    camera.gst.set_string('timezone-city', 'Edmonton')
    assert photo.latitude == 53.530476
    assert photo.longitude == -113.450635

