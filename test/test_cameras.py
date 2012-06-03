
"""Camera objects should be able to independantly remember settings."""

from gg.camera import known_cameras
from gg.common import photos

def test_camera_offsets():
    """Make sure that camera offsets function correctly"""
    assert photos
    assert known_cameras
    
    camera = known_cameras.values()[0]
    photo = photos.values()[0]
    
    for delta in (1, 10, 100, 600, -711):
        start = [photo.timestamp, camera.offset,
                 camera.gst.get_int('offset')]
        camera.offset += delta
        end = [photo.timestamp, camera.offset,
               photo.camera.gst.get_int('offset')]
        
        # Check that the photo timestamp, spinbutton value, and gsettings
        # key have all changed by precisely the same amount.
        for i, num in enumerate(start):
            assert end[i] - num == delta

