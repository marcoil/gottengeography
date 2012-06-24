
"""Camera objects should be able to independantly remember settings."""

from gg.camera import Camera
from gg.photos import Photograph

from test import DEMOFILES, gui

def test_camera_offsets():
    """Make sure that camera offsets function correctly"""
    gui.open_files(DEMOFILES)
    assert Photograph.instances
    assert Camera.instances
    
    photo = list(Photograph.instances).pop()
    camera = photo.camera
    
    camera.timezone_method = 'custom'
    camera.timezone_region = 'America'
    camera.timezone_city = 'Edmonton'
    
    for delta in (1, 10, 100, 600, -711):
        start = (photo.timestamp, camera.offset,
                 camera.gst.get_int('offset'))
        camera.offset += delta
        end = (photo.timestamp, camera.offset,
               photo.camera.gst.get_int('offset'))
        
        # Check that the photo timestamp, spinbutton value, and gsettings
        # key have all changed by precisely the same amount.
        for i, num in enumerate(start):
            assert end[i] - num == delta

