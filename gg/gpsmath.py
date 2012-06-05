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

"""Trigonometry and other mathematical calculations."""

from __future__ import division

from math import acos, sin, cos, radians
from time import strftime, localtime
from math import modf as split_float
from os.path import join, basename
from gettext import gettext as _
from fractions import Fraction
from pyexiv2 import Rational
from gi.repository import GLib, GObject

from territories import get_state, get_country
from build_info import PKG_DATA_DIR

EARTH_RADIUS = 6371 #km

def dms_to_decimal(degrees, minutes, seconds, sign=' '):
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

def format_coords(lat, lon):
    """Add cardinal directions to decimal coordinates."""
    return '%s %.5f, %s %.5f' % (
        _('N') if lat >= 0 else _('S'), abs(lat),
        _('E') if lon >= 0 else _('W'), abs(lon)
    )

gproperty = GObject.property

class Coordinates(GObject.GObject):
    """A generic object containing latitude and longitude coordinates.
    
    This class is inherited by Photograph and TrackFile and contains methods
    required by both of those classes.
    
    The geodata attribute of this class is shared across all instances of
    all subclasses of this class. When it is modified by any instance, the
    changes are immediately available to all other instances. It serves as
    a cache for data read from cities.txt, which contains geocoding data
    provided by geonames.org. All subclasses of this class can call
    self.lookup_geoname() and receive cached data if it was already
    looked up by another instance of any subclass.
    """
    
    # Class variable, keeps the geocoding cache
    geodata   = {}
    
    # GObject properties
    # Modifiable, non-derived properties
    @GObject.property(type=str, default='')
    def filename(self):
        return self._filename
    @filename.setter
    def filename(self, value):
        self._filename = value
        self.do_modified()
    @GObject.property(type=float, default=0.0)
    def latitude(self):
        return self._latitude
    @latitude.setter
    def latitude(self, value):
        self._latitude = value
        self._positioned = True
        self.do_modified()
    @GObject.property(type=float, default=0.0)
    def longitude(self):
        return self._longitude
    @longitude.setter
    def longitude(self, value):
        self._longitude = value
        self._positioned = True
        self.do_modified()
    @GObject.property(type=float, default=0.0)
    def altitude(self):
        return self._altitude
    @altitude.setter
    def altitude(self, value):
        self._altitude = value
        self.do_modified()
    @GObject.property(type=int, default=0)
    def timestamp(self):
        return self._timestamp
    @timestamp.setter
    def timestamp(self, value):
        self._timestamp = value
        self.do_modified()
    
    # Properties found from geocoding, read-only
    @GObject.property(type=str, default='')
    def provincestate(self):
        self.update_derived_properties()
        return self._provincestate
    @GObject.property(type=str, default='')
    def contrycode(self):
        self.update_derived_properties()
        return self._countrycode
    @GObject.property(type=str, default='')
    def countryname(self):
        self.update_derived_properties()
        return self._countryname
    @GObject.property(type=str, default='')
    def city(self):
        self.update_derived_properties()
        return self._city
    # The timezone at our coordinates, in 'Zone/City' format
    @GObject.property(type=str, default='')
    def geotimezone(self):
        self.update_derived_properties()
        return self._provincestate
    
    # Convenience properties calculated from the other ones
    @GObject.property(type=bool, default=False)
    def positioned(self):
        return self._positioned and self.valid_coords()
    @GObject.property(type=str, default='')
    def plain_summary(self):
        self.update_derived_properties()
        return self._plain_summary
    @GObject.property(type=str, default='')
    def markup_summary(self):
        self.update_derived_properties()
        return self._markup_summary
    
    def __init__(self, **props):
        # Initialize the 'real' values
        self._filename = ''
        self._latitude = 0.0
        self._longitude = 0.0
        self._altitude = 0.0
        self._timestamp = 0
        self._positioned = False
        for propname in ['provincestate', 'countrycode', 'countryname',
                          'city', 'geotimezone', 'plain_summary',
                          'markup_summary']:
            self.__dict__['_' + propname] = ''
        
        self.modified = False
        self.modified_timeout = None
        
        GObject.GObject.__init__(self, **props)
    
    def valid_coords(self):
        """Check if this object contains valid coordinates."""
        return abs(self._latitude) <= 90 and abs(self._longitude) <= 180
    
    def maps_link(self, link=_('View in Google Maps')):
        """Return a link to Google Maps if this object has valid coordinates."""
        return '<a href="%s?q=%s,%s">%s</a>' % ('http://maps.google.com/maps',
            self._latitude, self._longitude, link) if self.positioned else ''
    
    def lookup_geodata(self):
        """Search cities.txt for nearest city."""
        if not self.positioned:
            return
        key = '%.2f,%.2f' % (self._latitude, self._longitude)
        if key in Coordinates.geodata:
            return self.set_geodata(self.geodata[key])
        near, dist = None, float('inf')
        lat1, lon1 = radians(self._latitude), radians(self._longitude)
        with open(join(PKG_DATA_DIR, 'cities.txt')) as cities:
            for city in cities:
                name, lat, lon, country, state, tz = city.split('\t')
                lat2, lon2 = radians(float(lat)), radians(float(lon))
                try:
                    delta = acos(sin(lat1) * sin(lat2) +
                                 cos(lat1) * cos(lat2) *
                                 cos(lon2  - lon1))    * EARTH_RADIUS
                except ValueError:
                    delta = 0
                if delta < dist:
                    dist = delta
                    near = [name, state, country, tz]
        Coordinates.geodata[key] = near
        return self.set_geodata(near)
    
    def set_geodata(self, data):
        """Apply geodata to internal attributes."""
        self._city, state, self._countrycode, tz = data
        self._provincestate = get_state(self._countrycode, state)
        self._countryname   = get_country(self._countrycode)
        self._geotimezone      = tz.strip()
        return self._geotimezone
    
    def pretty_time(self):
        """Convert epoch seconds to a human-readable date."""
        if type(self._timestamp) is int:
            return strftime('%Y-%m-%d %X', localtime(self._timestamp))
    
    def pretty_coords(self):
        """Add cardinal directions to decimal coordinates."""
        return format_coords(self._latitude, self._longitude) \
            if self.positioned else _('Not geotagged')
    
    def pretty_geoname(self):
        """Display city, state, and country, if present."""
        return ', '.join(
            [s for s in (self._city, self._provincestate, self._countryname) if s])
    
    def pretty_altitude(self):
        """Convert elevation into a human readable format."""
        if self._altitude <> 0.0:
            return '%.1f%s' % (abs(self._altitude), _('m above sea level')
                        if self._altitude >= 0 else _('m below sea level'))
        return ''
    
    def build_plain_summary(self):
        """Plaintext summary of photo metadata."""
        self._plain_summary =  '\n'.join([s for s in [self.pretty_geoname(),
                                                  self.pretty_time(),
                                                  self.pretty_coords(),
                                                  self.pretty_altitude()] if s])
    
    def build_markup_summary(self):
        """Longer summary with Pango markup."""
        self._markup_summary = '<span %s>%s</span>\n<span %s>%s</span>' % (
            'size="larger"', basename(self._filename),
            'style="italic" size="smaller"', self._plain_summary
        )
    
    def do_modified(self):
        self.modified = True
        if not self.modified_timeout:
            self.modified_timeout = GLib.idle_add(self.update_derived_properties)
    
    def update_derived_properties(self):
        if not self.modified:
            return False
        if self.modified_timeout:
            GLib.source_remove(self.modified_timeout)
        self.lookup_geodata()
        self.build_plain_summary()
        self.build_markup_summary()
        
        self.modified = False
        self.modified_timeout = None
        return False
