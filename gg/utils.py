# GottenGeography - Utility functions used by GottenGeography
# Copyright (C) 2010 Robert Park <rbpark@exolucere.ca>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import division

from gi.repository import GConf
from cPickle import dumps as pickle
from cPickle import loads as unpickle
from os.path import join, basename, dirname
from math import modf as split_float
from gettext import gettext as _
from fractions import Fraction
from pyexiv2 import Rational
from re import match

# Don't export everything, that's too sloppy.
__all__ = [ 'gconf_set', 'gconf_get', 'get_file', 'format_list',
    'dms_to_decimal', 'decimal_to_dms', 'float_to_rational',
    'valid_coords', 'maps_link', 'format_coords', 'iptc_keys',
    'Coordinates', 'ReadableDictionary' ]

iptc_keys = ['CountryCode', 'CountryName', 'ProvinceState', 'City']
gconf     = GConf.Client.get_default()

def gconf_key(key):
    """Determine appropriate GConf key that is unique to this application."""
    return "/apps/gottengeography/" + key

def gconf_set(key, value):
    """Sets the given GConf key to the given value."""
    gconf.set_string(gconf_key(key), pickle(value))

def gconf_get(key, default=None):
    """Gets the given GConf key as the requested type."""
    try:
        return unpickle(gconf.get_string(gconf_key(key)))
    except TypeError:
        return default

def get_file(filename):
    """Find a file that's in the same directory as this program."""
    return join(dirname(__file__), filename)

def format_list(strings, joiner=", "):
    """Join geonames with a comma, ignoring missing names."""
    return joiner.join([name for name in strings if name])

def dms_to_decimal(degrees, minutes, seconds, sign=""):
    """Convert degrees, minutes, seconds into decimal degrees."""
    return (-1 if match(r'[SWsw]', sign) else 1) * (
        degrees.to_float()        +
        minutes.to_float() / 60   +
        seconds.to_float() / 3600
    )

def decimal_to_dms(decimal):
    """Convert decimal degrees into degrees, minutes, seconds."""
    remainder, degrees = split_float(abs(decimal))
    remainder, minutes = split_float(remainder * 60)
    return [
        Rational(degrees, 1),
        Rational(minutes, 1),
        float_to_rational(remainder * 60)
    ]

def float_to_rational(value):
    """Create a pyexiv2.Rational with help from fractions.Fraction."""
    frac = Fraction(abs(value)).limit_denominator(99999)
    return Rational(frac.numerator, frac.denominator)

def valid_coords(lat, lon):
    """Determine the validity of coordinates."""
    if type(lat) not in (float, int): return False
    if type(lon) not in (float, int): return False
    return abs(lat) <= 90 and abs(lon) <= 180

def maps_link(lat, lon, anchor=_("View in Google Maps")):
    """Create a Pango link to Google Maps."""
    return '<a href="http://maps.google.com/maps?q=%s,%s">%s</a>' % (lat, lon, anchor)

def format_coords(lat, lon):
    """Add cardinal directions to decimal coordinates."""
    return "%s %.5f, %s %.5f" % (
        _("N") if lat >= 0 else _("S"), abs(lat),
        _("E") if lon >= 0 else _("W"), abs(lon)
    )

class Coordinates():
    """A generic object containing latitude and longitude coordinates.
    
    This class is inherited by Photograph and GPXLoader and contains methods
    required by both of those classes.
    """
    
    latitude  = None
    longitude = None
    
    def valid_coords(self):
        """Check if this object contains valid coordinates."""
        return valid_coords(self.latitude, self.longitude)
    
    def maps_link(self):
        """Return a link to Google Maps if this object has valid coordinates."""
        if self.valid_coords():
            return maps_link(self.latitude, self.longitude)

class ReadableDictionary:
    """Object that exposes it's internal namespace as a dictionary.
    
    This can for the most part be used just like a normal dictionary, except
    you can access it's keys with readable.key as well as readable['key'].
    """
    def values(self):
        return self.__dict__.values()
    
    def update(self, attributes):
        self.__dict__.update(attributes)
    
    def __init__(self, attributes={}):
        self.update(attributes)
    
    def __len__(self):
        return len(self.__dict__)
    
    def __getitem__(self, key):
        return self.__dict__[key]
    
    def __setitem__(self, key, value):
        self.__dict__[key] = value
    
    def __delitem__(self, key):
        del self.__dict__[key]

