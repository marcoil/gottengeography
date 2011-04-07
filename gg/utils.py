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

from cPickle import dumps as pickle
from cPickle import loads as unpickle
from os.path import join, dirname, basename
from gi.repository import GConf, Clutter, Champlain
from math import acos, sin, cos, radians
from time import strftime, localtime
from math import modf as split_float
from gettext import gettext as _
from fractions import Fraction
from pyexiv2 import Rational

from territories import get_state, get_country

def get_file(filename):
    """Find a file that's in the same directory as this program."""
    return join(dirname(__file__), filename)

def make_clutter_color(color):
    """Generate a Clutter.Color from the currently chosen color."""
    return Clutter.Color.new(
        *[x / 256 for x in [color.red, color.green, color.blue, 32768]])

################################################################################
# GConf methods. These methods interact with GConf.
################################################################################

gconf = GConf.Client.get_default()

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

################################################################################
# GPS math functions. These methods convert numbers into other numbers.
################################################################################

def dms_to_decimal(degrees, minutes, seconds, sign=" "):
    """Convert degrees, minutes, seconds into decimal degrees."""
    return (-1 if sign[0] in 'SWsw' else 1) * (
        float(degrees)        +
        float(minutes) / 60   +
        float(seconds) / 3600
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

################################################################################
# String formatting methods. These methods manipulate strings.
################################################################################

def format_list(strings, joiner=", "):
    """Join geonames with a comma, ignoring missing names."""
    return joiner.join([name for name in strings if name])

def maps_link(lat, lon, anchor=_("View in Google Maps")):
    """Create a Pango link to Google Maps."""
    return '<a title="%s" href="http://maps.google.com/maps?q=%s,%s">Google</a>' % (anchor, lat, lon)

def format_coords(lat, lon):
    """Add cardinal directions to decimal coordinates."""
    return "%s %.5f, %s %.5f" % (
        _("N") if lat >= 0 else _("S"), abs(lat),
        _("E") if lon >= 0 else _("W"), abs(lon)
    )


class Polygon(Champlain.PathLayer):
    def __init__(self):
        super(Champlain.PathLayer, self).__init__()
        self.set_stroke_width(4)
    
    def append_point(self, latitude, longitude, elevation):
        """Simplify appending a point onto a polygon."""
        coord = Champlain.Coordinate.new_full(latitude, longitude)
        coord.lat = latitude
        coord.lon = longitude
        coord.ele = elevation
        self.add_node(coord)
        return coord


class Coordinates():
    """A generic object containing latitude and longitude coordinates.
    
    This class is inherited by Photograph and GPXLoader and contains methods
    required by both of those classes.
    
    The geodata attribute of this class is shared across all instances of
    all subclasses of this class. When it is modified by any instance, the
    changes are immediately available to all other instances. It serves as
    a cache for data read from cities.txt, which contains geocoding data
    provided by geonames.org. All subclasses of this class can call
    self.lookup_geoname() and receive cached data if it was already
    looked up by another instance of any subclass.
    """
    
    provincestate = None
    countrycode   = None
    countryname   = None
    city          = None
    
    filename  = ""
    altitude  = None
    latitude  = None
    longitude = None
    timestamp = None
    timezone  = None
    geodata   = {}
    
    def valid_coords(self):
        """Check if this object contains valid coordinates."""
        return valid_coords(self.latitude, self.longitude)
    
    def maps_link(self):
        """Return a link to Google Maps if this object has valid coordinates."""
        if self.valid_coords():
            return maps_link(self.latitude, self.longitude)
    
    def lookup_geoname(self):
        """Search cities.txt for nearest city."""
        if not self.valid_coords():
            return
        assert self.geodata is Coordinates.geodata
        key = "%.2f,%.2f" % (self.latitude, self.longitude)
        if key in self.geodata:
            return self.set_geodata(self.geodata[key])
        near, dist = None, float('inf')
        lat1, lon1 = radians(self.latitude), radians(self.longitude)
        with open(get_file("cities.txt")) as cities:
            for city in cities:
                name, lat, lon, country, state, tz = city.split("\t")
                lat2, lon2 = radians(float(lat)), radians(float(lon))
                delta = acos(sin(lat1) * sin(lat2) +
                             cos(lat1) * cos(lat2) *
                             cos(lon2  - lon1))    * 6371 # earth's radius in km
                if delta < dist:
                    dist = delta
                    near = [name, state, country, tz]
        self.geodata[key] = near
        return self.set_geodata(near)
    
    def set_geodata(self, data):
        """Apply geodata to internal attributes."""
        self.city, state, self.countrycode, tz = data
        self.provincestate = get_state(self.countrycode, state)
        self.countryname   = get_country(self.countrycode)
        self.timezone      = tz.strip()
        return self.timezone
    
    def pretty_time(self):
        """Convert epoch seconds to a human-readable date."""
        if type(self.timestamp) is int:
            return strftime("%Y-%m-%d %X", localtime(self.timestamp))
    
    def pretty_coords(self):
        """Add cardinal directions to decimal coordinates."""
        return format_coords(self.latitude, self.longitude) \
            if self.valid_coords() else _("Not geotagged")
    
    def pretty_geoname(self):
        """Display city, state, and country, if present."""
        names = [self.city, self.provincestate, self.countryname]
        length = sum(map(len, names))
        return format_list(names, ',\n' if length > 35 else ', ')
    
    def pretty_elevation(self):
        """Convert elevation into a human readable format."""
        if type(self.altitude) in (float, int):
            return "%.1f%s" % (abs(self.altitude), _("m above sea level")
                        if self.altitude >= 0 else _("m below sea level"))
    
    def short_summary(self):
        """Plaintext summary of photo metadata."""
        return format_list([self.pretty_time(), self.pretty_coords(),
            self.pretty_geoname(), self.pretty_elevation()], "\n")
    
    def long_summary(self):
        """Longer summary with Pango markup."""
        return '<span %s>%s</span>\n<span %s>%s</span>' % (
            'size="larger"', basename(self.filename),
            'style="italic" size="smaller"', self.short_summary()
        )


class Struct:
    """This is a generic object which can be assigned arbitrary attributes."""
    def __init__(self, attributes={}):
        self.__dict__.update(attributes)

