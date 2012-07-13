
"""Test the CSV parser for accuracy."""

from os.path import abspath, join

from gg.xmlfiles import TrackFile, CSVFile
from gg.common import points

from test import gui, setup, teardown

def test_mytracks():
    """Test that we can read the output from Google's MyTracks app"""
    teardown()
    assert not TrackFile.instances
    assert not points
    
    csv = abspath(join('test', 'data', 'mytracks.csv'))
    gui.open_files([csv])
    assert len(TrackFile.instances) == 1
    assert len(points) == 100
    assert len(CSVFile(csv).polygons) == 2
    
    alpha = points[min(points)]
    omega = points[max(points)]
    
    assert alpha.lat == 49.887554
    assert alpha.lon == -97.131041
    assert alpha.ele == 217.1999969482422
    
    assert omega.lat == 49.885108
    assert omega.lon == -97.136677
    assert omega.ele == 195.6999969482422

def test_invalid_altitude():
    """Ensure that we can still read CSVs if the altitude data is corrupted"""
    teardown()
    assert not TrackFile.instances
    assert not points
    
    csv = abspath(join('test', 'data', 'missing_alt.csv'))
    gui.open_files([csv])
    assert len(TrackFile.instances) == 1
    assert len(points) == 10
    assert len(CSVFile(csv).polygons) == 1
    
    for point in points.values():
        assert type(point.ele) is float
        assert point.ele == 0.0

def test_minimal():
    """The minimal amount of CSV data should be valid"""
    teardown()
    assert not TrackFile.instances
    assert not points
    
    csv = abspath(join('test', 'data', 'minimal.csv'))
    gui.open_files([csv])
    assert len(TrackFile.instances) == 1
    assert len(points) == 3
    assert len(CSVFile(csv).polygons) == 1
    
    for point in points.values():
        assert type(point.ele) is float
        assert point.ele == 0.0
    
    alpha = points[min(points)]
    omega = points[max(points)]
    
    assert alpha.lat == 49.885583
    assert alpha.lon == -97.151421
    assert alpha.ele == 0.0
    
    assert omega.lat == 49.885576
    assert omega.lon == -97.151397
    assert omega.ele == 0.0

