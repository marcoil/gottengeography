
"""Initialize the GottenGeography Nose test suite."""

from os import listdir, system, environ
from os.path import abspath, join
from random import random
from time import tzset

from gg.app import GottenGeography, get_obj, gst
from gg.camera import known_cameras
from gg.common import photos, modified, selected, map_view
from gg.xmlfiles import clear_all_gpx
from gg.build_info import PKG_DATA_DIR

DEMOFILES = [abspath(join(PKG_DATA_DIR, '..', 'demo', f))
             for f in listdir('./demo/')]

gui = GottenGeography()

# Disable animation for speed.
gst.set_int('animation-steps', 15)
gui.search.slide_to = map_view.center_on

def random_coord(maximum=180):
    """Generate a random number -maximum <= x <= maximum."""
    return (random() * maximum * 2) - maximum

def setup():
    """Start from a clean slate."""
    system('git checkout demo')
    environ['TZ'] = 'America/Edmonton'
    tzset()
    gui.open_files(DEMOFILES)

def teardown():
    """Clean it all up."""
    clear_all_gpx()
    for camera in known_cameras.values():
        camera.photos.clear()
    for photo in photos.values():
        gui.labels.layer.remove_marker(photo.label)
    photos.clear()
    modified.clear()
    selected.clear()
    gui.liststore.clear()
    system('git checkout demo')
    for key in gst.list_keys():
        gst.reset(key)

