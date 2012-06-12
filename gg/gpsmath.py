# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

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
from common import memoize

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


class Coordinates(GObject.GObject):
    """A generic object containing latitude and longitude coordinates.
    
    Different instances of this class and it's subclass Photograph can
    call self.lookup_geodata() and receive cached geoname data.
    """
    modified_timeout = None
    timeout_seconds = 1
    
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
        if abs(value) > 90:
            return
        self._latitude = value
        self.do_modified(True)
    
    @GObject.property(type=float, default=0.0)
    def longitude(self):
        return self._longitude
    
    @longitude.setter
    def longitude(self, value):
        if abs(value) > 180:
            return
        self._longitude = value
        self.do_modified(True)
    
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
    
    # Convenience properties calculated from the other ones
    # Has it been positioned, or is it uninitialized?
    @GObject.property(type=bool, default=False)
    def positioned(self):
        return self._positioned and self.valid_coords()
    
    # The city / state / country location
    @GObject.property(type=str, default='')
    def geoname(self):
        self.update_derived_properties()
        return self._geoname
    
    def __init__(self, **props):
        self._filename = ''
        self.reset_properties()
        
        GObject.GObject.__init__(self, **props)
    
    def reset_properties(self):
        """Reset/reinitialize everything to the factory defaults."""
        self._latitude = 0.0
        self._longitude = 0.0
        self._altitude = 0.0
        self._timestamp = 0
        self._positioned = False
        self._geoname = ''
        
        self.city = ''
        self.provincestate = ''
        self.countryname = ''
        self.geotimezone = ''
    
    def valid_coords(self):
        """Check if this object contains valid coordinates."""
        return abs(self._latitude) <= 90 and abs(self._longitude) <= 180
    
    @memoize
    def do_cached_lookup(self, key):
        """Scan cities.txt for the nearest town."""
        near, dist = None, float('inf')
        lat1, lon1 = radians(self.latitude), radians(self.longitude)
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
        return near
    
    def lookup_geodata(self):
        """Check the cache for geonames, and notify of any changes."""
        if not self.positioned:
            return
        key = '%.2f,%.2f' % (self.latitude, self.longitude)
        city, state, countrycode, tz = self.do_cached_lookup(key)
        provincestate = get_state(countrycode, state)
        countryname = get_country(countrycode)
        if (city is not self.city) or \
           (provincestate is not self.provincestate) or \
           (countryname is not self.countryname):
            self.notify('geoname')
        self.city = city
        self.provincestate = provincestate
        self.countryname   = countryname
        self.geotimezone   = tz.strip()
        self._geoname = ', '.join(
            [s for s in (city, provincestate, countryname) if s])
        return self.geotimezone
    
    def pretty_time(self):
        """Convert epoch seconds to a human-readable date."""
        if type(self.timestamp) is int:
            return strftime('%Y-%m-%d %X', localtime(self.timestamp))
    
    def pretty_coords(self):
        """Add cardinal directions to decimal coordinates."""
        return format_coords(self.latitude, self.longitude) \
            if self.positioned else _('Not geotagged')
    
    def pretty_altitude(self):
        """Convert elevation into a human readable format."""
        if self.altitude != 0.0:
            return '%.1f%s' % (abs(self.altitude), _('m above sea level')
                        if self.altitude >= 0 else _('m below sea level'))
        return ''
    
    def plain_summary(self):
        """Plaintext summary of photo metadata."""
        return '\n'.join([s for s in [self.geoname,
                                      self.pretty_time(),
                                      self.pretty_coords(),
                                      self.pretty_altitude()] if s])
    
    def markup_summary(self):
        """Longer summary with Pango markup."""
        return '<span %s>%s</span>\n<span %s>%s</span>' % (
                        'size="larger"', basename(self.filename),
                        'style="italic" size="smaller"', self.plain_summary()
                        )
    
    def do_modified(self, positioned=False):
        """Notify that position has changed and set timer to update geoname."""
        if positioned and self.valid_coords():
            self._positioned = True
            self.notify('positioned')
        if not self.modified_timeout:
            self.modified_timeout = GLib.timeout_add_seconds(
                self.timeout_seconds, self.update_derived_properties)
    
    def update_derived_properties(self):
        """Do expensive geodata lookups after the timeout."""
        if self.modified_timeout:
            GLib.source_remove(self.modified_timeout)
            self.lookup_geodata()
            self.modified_timeout = None
        return False

