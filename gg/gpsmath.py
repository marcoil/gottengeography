# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Trigonometry and other mathematical calculations."""

from __future__ import division

from gi.repository import GLib, GObject
from time import strftime, localtime
from math import modf as split_float
from os.path import join, basename
from gettext import gettext as _
from fractions import Fraction
from math import cos, radians
from pyexiv2 import Rational

from territories import get_state, get_country
from common import memoize, modified
from build_info import PKG_DATA_DIR


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


@memoize
def do_cached_lookup(key):
    """Scan cities.txt for the nearest town.
    
    The key argument should be a GeoCacheKey instance so that we can sneak the
    precise lat,lon pair past the memoizer.
    """
    near, dist = None, float('inf')
    lat1, lon1 = radians(key.lat), radians(key.lon)
    with open(join(PKG_DATA_DIR, 'cities.txt')) as cities:
        for city in cities:
            name, lat2, lon2, country, state, tz = city.split('\t')
            lat2, lon2 = radians(float(lat2)), radians(float(lon2))
            x = (lon2 - lon1) * cos((lat1 + lat2) / 2)
            y = (lat2 - lat1)
            delta = x * x + y * y
            if delta < dist:
                dist = delta
                near = [name, state, country, tz]
    return near


class GeoCacheKey:
    """This class allows fuzzy geodata cache lookups.
    
    The magic here is that different instances of this class will compare
    equally if they have the same key (ie, if the lat,lon pair are equal to
    within 2 decimal places), and as a result of this, a dict() entry created
    by one instance of this class can be retrieved by a different instance, as
    long as self.key is equal between them.
    
    This allows me to pass in the precise lat,lon pair to the do_cached_lookup
    method above, without the memoizer caching too specifically. If we just
    cached the full lat,lon pair, there'd never be any cache hits and we'd
    be doing expensive geodata lookups way too often, so this makes the cache
    lookups 'fuzzy', allowing you to get get a cached result even if you're
    only just *nearby* a previously cached result.
    """
    
    def __init__(self, lat, lon):
        self.key = '%.2f,%.2f' % (lat, lon)
        self.lat = lat
        self.lon = lon
    
    def __str__(self):
        return self.key
    
    def __hash__(self):
        return hash(self.key)
    
    def __cmp__(self, other):
        return cmp(self.key, other.key)


class Coordinates(GObject.GObject):
    """A generic object containing latitude and longitude coordinates."""
    modified_timeout = None
    timeout_seconds = 0
    
    city = ''
    provincestate = ''
    countryname = ''
    geotimezone = ''
    
    timestamp = GObject.property(type=int)
    altitude  = GObject.property(type=float)
    latitude  = GObject.property(type=float, minimum=-90.0,  maximum=90.0)
    longitude = GObject.property(type=float, minimum=-180.0, maximum=180.0)
    
    @GObject.property(type=bool, default=False)
    def positioned(self):
        """Identify if this instance occupies a valid point on the map.
        
        Returns False at 0,0 because it's actually remarkably difficult to
        achieve that exact point in a natural way (not to mention it's in the
        middle of the Atlantic), which means the photo hasn't been placed yet.
        """
        return bool(self.latitude or self.longitude)
    
    @GObject.property(type=str)
    def geoname(self):
        """Report the city, state, and country in a pretty list."""
        return ', '.join(
            [s for s in (self.city, self.provincestate, self.countryname) if s])
    
    def __init__(self, **props):
        self.filename = ''
        
        GObject.GObject.__init__(self, **props)
        
        for prop in ('latitude', 'longitude', 'altitude', 'timestamp'):
            self.connect('notify::' + prop, self.do_modified)
    
    def lookup_geodata(self):
        """Check the cache for geonames, and notify of any changes."""
        if not self.positioned:
            return
        
        old_geoname = self.geoname
        self.city, state, countrycode, tz = do_cached_lookup(
            GeoCacheKey(self.latitude, self.longitude))
        self.provincestate = get_state(countrycode, state)
        self.countryname = get_country(countrycode)
        self.geotimezone = tz.strip()
        if self.geoname != old_geoname:
            self.notify('geoname')
        
        return self.geotimezone
    
    def pretty_time(self):
        """Convert epoch seconds to a human-readable date."""
        if self.timestamp:
            return strftime('%Y-%m-%d %X', localtime(self.timestamp))
    
    def pretty_coords(self):
        """Add cardinal directions to decimal coordinates."""
        if self.positioned:
            return format_coords(self.latitude, self.longitude)
    
    def pretty_altitude(self):
        """Convert elevation into a human readable format."""
        if self.altitude:
            return '%.1f%s' % (abs(self.altitude), _('m above sea level')
                        if self.altitude >= 0 else _('m below sea level'))
    
    def plain_summary(self):
        """Plaintext summary of photo metadata."""
        return '\n'.join([s for s in [self.geoname,
                                      self.pretty_time(),
                                      self.pretty_coords(),
                                      self.pretty_altitude()] if s])
    
    def markup_summary(self):
        """Longer summary with Pango markup."""
        summary = '<span %s>%s</span>\n<span %s>%s</span>' % (
            'size="larger"', basename(self.filename),
            'style="italic" size="smaller"', self.plain_summary())
        return '<b>%s</b>' % summary if self in modified else summary
    
    def do_modified(self, *ignore):
        """Set timer to update the geoname after all modifications are done."""
        self.notify('positioned')
        if not self.modified_timeout:
            self.modified_timeout = GLib.timeout_add_seconds(
                self.timeout_seconds, self.update_derived_properties)
    
    def update_derived_properties(self):
        """Do expensive geodata lookups after the timeout."""
        if self.modified_timeout:
            self.notify('positioned')
            GLib.source_remove(self.modified_timeout)
            self.lookup_geodata()
            self.modified_timeout = None
        return False

