
"""Test the KML parser for accuracy."""

from os.path import abspath, join
from glob import glob

from gg.xmlfiles import TrackFile, KMLFile
from gg.common import points

from test import gui, setup, teardown

KMLFILES = [abspath(f) for f in glob(join('test', 'data', '*.kml'))]

def test_ordered():
    """Test that we can read a KML with ordered pairs"""
    teardown()
    assert not TrackFile.instances
    assert not points
    
    gui.open_files([KMLFILES[1]])
    assert len(TrackFile.instances) == 1
    assert len(points) == 84
    
    alpha = points[min(points)]
    omega = points[max(points)]
    
    assert alpha.lat == 39.6012887
    assert alpha.lon == 3.2617136
    assert alpha.ele == 185.0
    
    assert omega.lat == 39.6012402
    assert omega.lon == 3.2617779
    assert omega.ele == 0.0

def test_stupid_ordering():
    """Somebody at Google thought this was a good idea"""
    teardown()
    assert not TrackFile.instances
    assert not points
    
    gui.open_files([KMLFILES[0]])
    assert len(TrackFile.instances) == 1
    assert len(points) == 84
    
    alpha = points[min(points)]
    omega = points[max(points)]
    
    assert alpha.lat == 39.6012887
    assert alpha.lon == 3.2617136
    assert alpha.ele == 185.0
    
    assert omega.lat == 39.6012402
    assert omega.lon == 3.2617779
    assert omega.ele == 0.0
    
    gui.open_files([KMLFILES[1]])
    assert len(TrackFile.instances) == 2
    assert len(points) == 84
    
    one = KMLFile(KMLFILES[0]).tracks
    two = KMLFile(KMLFILES[1]).tracks
    
    # Both traces are identical, only the ordering in the XML differs
    for point in points:
        assert one[point].lat == two[point].lat
        assert one[point].lon == two[point].lon
        assert one[point].ele == two[point].ele
    
    # Test that points is valid even when destroying overlapping traces
    assert len(points) == 84
    KMLFile(KMLFILES[0]).destroy()
    assert len(points) == 84
    KMLFile(KMLFILES[1]).destroy()
    assert not points

