
"""Pretty strings should match what's given here.'"""

from gg.common import Struct
from gg.camera import Camera
from gg.photos import Photograph

from test import DEMOFILES, teardown, setup

def test_string_functions():
    """Ensure that strings print properly."""
    teardown()
    
    photo = Photograph(DEMOFILES[5])
    photo.read()
    
    photo._latitude  = 200
    photo._longitude = 200
    assert photo.pretty_coords() == 'Not geotagged'
    
    photo.positioned = 0
    photo.latitude  = 10.0
    photo.longitude = 10.0
    assert photo.pretty_coords() == 'N 10.00000, E 10.00000'
    
    photo.latitude  = -10.0
    photo.longitude = -10.0
    assert photo.pretty_coords() == 'S 10.00000, W 10.00000'
    
    camera = Camera.instances.values()[0]
    camera.gst.set_string('timezone-method', 'lookup')
    photo.timestamp = 999999999
    assert photo.pretty_time() == '2001-09-08 07:46:39 PM'
    
    photo.altitude = -10.20005
    assert photo.pretty_altitude() == '10.2m below sea level'
    
    photo.altitude = 600.71
    assert photo.pretty_altitude() == '600.7m above sea level'
    
    assert photo.plain_summary() == \
"""Georgetown, Ascension, Saint Helena
2001-09-08 07:46:39 PM
S 10.00000, W 10.00000
600.7m above sea level"""
    
    assert photo.markup_summary() == \
"""<span size="larger">IMG_2411.JPG</span>
<span style="italic" size="smaller">Georgetown, Ascension, Saint Helena
2001-09-08 07:46:39 PM
S 10.00000, W 10.00000
600.7m above sea level</span>"""

