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

from datetime import datetime
from dateutil import tz
from gettext import gettext as _
from gi.repository import GObject, Gtk, GdkPixbuf
from math import acos, sin, cos, radians
from os.path import basename
from time import mktime

from utils import valid_coords, format_coords, format_list, get_file

class Coordinates(object):
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
    
    geodata   = {}
    
    def __init__(self):
        self.sourcename = _("Other")
        self.provincestate = None
        self.countrycode   = None
        self.countryname   = None
        self.city          = None
        
        self.filename  = ""
        self.altitude  = None
        self.latitude  = None
        self.longitude = None
        self.timestamp = None
    
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
            return ""
        assert self.geodata is Coordinates.geodata
        key = "%.2f,%.2f" % (self.latitude, self.longitude)
        if key in self.geodata:
            return self.set_geodata(self.geodata[key])
        near, dist = None, float('inf')
        lat1, lon1 = radians(self.latitude), radians(self.longitude)
        with open(get_file("cities.txt")) as cities:
            for city in cities:
                name, lat, lon, country, state, tzname = city.split("\t")
                lat2, lon2 = radians(float(lat)), radians(float(lon))
                delta = acos(sin(lat1) * sin(lat2) +
                             cos(lat1) * cos(lat2) *
                             cos(lon2  - lon1))    * 6371 # earth's radius in km
                if delta < dist:
                    dist = delta
                    near = [name, state, country, tzname]
        self.geodata[key] = near
        return self.set_geodata(near)
    
    def set_geodata(self, data):
        """Apply geodata to internal attributes, and return a timezone name"""
        self.city, state, self.countrycode, tzname = data
        self.provincestate = get_state(self.countrycode, state)
        self.countryname   = get_country(self.countrycode)
        return tzname
    
    def pretty_time(self):
        """Convert epoch seconds to a human-readable date, in local timezone."""
        return self.timestamp.astimezone(tz.gettz()).strftime("%Y-%m-%d %X")
    
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
        return '<span %s>%s</span>\n<span %s>%s</span>\n<span %s>%s</span>' % (
            'size="larger"', basename(self.filename),
            'size="smaller"', self.sourcename,
            'style="italic" size="smaller"', self.short_summary()
        )
    
    def unix_timestamp(self):
        return int(mktime(self.timestamp.utctimetuple()))

class Source(object):
    """A generic class for things that can keep Coordinates objects.
    Instances keep a map from timestamps to Polygons.
    """
    # Should we show tracks for this source?
    track = False
    
    def __init__(self, name, add_polygon):
        self.name = name
        self.timezone = tz.tzutc()
        self.add_poly = add_polygon
        self.tracks = {}
        self.alpha = datetime.max.replace(tzinfo = tz.tzutc()) # Initial GPX track point
        self.omega = datetime.min.replace(tzinfo = tz.tzutc()) # Final GPX track point
    
    def load_done(self):
        keys = self.tracks.keys()
        if len(keys) >= 2:
            self.alpha = min(keys)
            self.omega = max(keys)
    
    def set_timezone(self, tz):
        pass

class Camera(Source):
    """A source that groups photos made with the same camera."""
    
    def __init__(self, name, add_polygon):
        super(Camera, self).__init__(name, add_polygon)
        """All cameras start with system timezone."""
        self.timezone = tz.gettz()
        self.photos = []
        self.append = add_polygon()
    
    def set_timezone(self, tz):
        self.timezone = tz
        for photo in self.photos:
            photo.calculate_timestamp(tz)
    
    def add_photo(self, photo):
        photo.calculate_timestamp(self.timezone)
        if photo.has_embedded_coordinates:
            self.tracks[photo.timestamp] = self.append(photo.latitude,
                                                       photo.longitude,
                                                       photo.elevation)
        self.load_done()
