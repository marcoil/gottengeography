
"""Test various forms of mathemagics."""

from __future__ import division

from math import floor

from fractions import Fraction
from gg.gpsmath import Coordinates, valid_coords
from gg.gpsmath import dms_to_decimal, decimal_to_dms

from test import random_coord

def test_valid_coords():
    """valid_coords() needs to be bulletproof"""
    assert not valid_coords(None, None)
    assert not valid_coords('', '')
    assert not valid_coords(True, True)
    assert not valid_coords(False, False)
    assert not valid_coords(45, 270)
    assert not valid_coords(100, 50)
    assert not valid_coords([], 50)
    assert not valid_coords(45, {'grunt':42})
    assert not valid_coords(set(), 50)
    assert not valid_coords(45, valid_coords)
    assert not valid_coords('ya', 'dun goofed')
    assert valid_coords(0, 0)
    assert valid_coords(53.67, -113.589)

def test_st_johns():
    """Don't let St John's break the map"""
    # Seriously. Revert commit 362dd6eb and watch this explode.
    stjohns = Coordinates()
    stjohns.latitude = 47.56494
    stjohns.longitude = -52.70931
    stjohns.lookup_geodata()
    assert stjohns.names[0] == "St. John's"

def test_math():
    """Test coordinate conversion functions"""
    to_float = lambda rats: (
        Fraction(rats[0].to_float()),
        Fraction(rats[1].to_float()),
                 rats[2])
    
    # Pick 100 random coordinates on the globe, convert them from decimal
    # to sexagesimal and then back, and ensure that they are always equal-ish.
    for i in range(100):
        decimal_lat = random_coord(80)
        decimal_lon = random_coord(180)
        assert valid_coords(decimal_lat, decimal_lon)
        
        dms_lat = decimal_to_dms(decimal_lat)
        dms_lon = decimal_to_dms(decimal_lon)
        
        assert len(dms_lat) == 3
        assert dms_lat[0].numerator == floor(abs(decimal_lat))
        
        assert len(dms_lon) == 3
        assert dms_lon[0].numerator == floor(abs(decimal_lon))
        
        assert decimal_lat - dms_to_decimal(*to_float(dms_lat) \
            + ('N' if decimal_lat >= 0 else 'S',)) < 1e-6
        assert decimal_lon - dms_to_decimal(*to_float(dms_lon) \
            + ('E' if decimal_lon >= 0 else 'W',)) < 1e-6

