
"""Camera objects should be able to independantly remember settings."""

from gg.camera import Camera
from gg.photos import Photograph

def test_camera_offsets():
    """Make sure that camera offsets function correctly"""
    assert Photograph.instances
    assert Camera.instances
    
    camera = Camera.instances.values()[0]
    photo = Photograph.instances.values()[0]
    
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

def test_memoization():
    """Memoization shouldn't get in the way of things"""
    assert Camera.instances is Camera.cls.instances
    assert Camera.generate_id({}) == ('unknown_camera', 'Unknown Camera')
    assert Camera.generate_id({'Make': 'Nikon'}) == ('nikon', 'Nikon')
    
    foo = Camera('unknown_camera')
    assert Camera('unknown_camera') is Camera('unknown_camera')
    assert id(foo) == id(Camera('unknown_camera'))

