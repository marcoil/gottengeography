# GottenGeography - Custom data types used in GottenGeography application
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

from gettext import gettext as _
from gi.repository import GdkPixbuf, GObject
from time import strftime, mktime, localtime
from math import acos, sin, cos, radians
from pyexiv2 import ImageMetadata
from os.path import basename
from os import stat
from re import sub

from territories import get_state, get_country
from utils import decimal_to_dms, dms_to_decimal, float_to_rational
from utils import valid_coords, format_coords, iptc_keys, format_list
from utils import get_file, ReadableDictionary

# Don't export everything, that's too sloppy.
__all__ = [ 'Photograph', 'GeoCache' ]

earth_radius = 6371 #km
gps          = 'Exif.GPSInfo.GPS' # This is a prefix for common EXIF keys.

class Photograph(ReadableDictionary):
    """Represents a single photograph and it's location in space and time."""
    
    def __init__(self, filename, cache, callback, thumb_size=200):
        """Initialize new Photograph object's attributes with default values."""
        self.exif     = ImageMetadata(filename)
        self.filename = filename
        self.geonamer = cache
        self.callback = callback
        self.thm_size = thumb_size
        self.marker   = None
        self.iter     = None
        self.read()
    
    def read(self):
        """Load exif data from disk."""
        for key in [ 'timestamp', 'altitude', 'latitude', 'longitude',
        'timezone' ] + iptc_keys:
            self[key] = None
        self.manual = False
        try:
            self.exif.read()
            self.thumb = GdkPixbuf.Pixbuf.new_from_file_at_size(
                self.filename, self.thm_size, self.thm_size)
        except (GObject.GError, TypeError):
            raise IOError
        self.calculate_timestamp()
        try:
            self.latitude = dms_to_decimal(
                *self.exif[gps + 'Latitude'].value +
                [self.exif[gps + 'LatitudeRef'].value]
            )
            self.longitude = dms_to_decimal(
                *self.exif[gps + 'Longitude'].value +
                [self.exif[gps + 'LongitudeRef'].value]
            )
        except KeyError:
            pass
        try:
            self.altitude = self.exif[gps + 'Altitude'].value.to_float()
            if int(self.exif[gps + 'AltitudeRef'].value) > 0:
                self.altitude *= -1
        except KeyError:
            pass
        for iptc in iptc_keys:
            try:
                self[iptc] = self.exif['Iptc.Application2.' + iptc].values[0]
            except KeyError:
                pass
    
    def calculate_timestamp(self):
        """Determine the timestamp based on the currently selected timezone.
        
        This method relies on the TZ environment variable to be set before
        it is called. If you don't set TZ before calling this method, then it
        implicitely assumes that the camera and the computer are set to the
        same timezone.
        """
        try:
            self.timestamp = int(mktime(
                self.exif['Exif.Photo.DateTimeOriginal'].value.timetuple()))
        except KeyError:
            self.timestamp = int(stat(self.filename).st_mtime)
    
    def write(self):
        """Save exif data to photo file on disk."""
        if self.altitude is not None:
            self.exif[gps + 'Altitude']    = float_to_rational(self.altitude)
            self.exif[gps + 'AltitudeRef'] = '0' if self.altitude >= 0 else '1'
        self.exif[gps + 'Latitude']     = decimal_to_dms(self.latitude)
        self.exif[gps + 'LatitudeRef']  = "N" if self.latitude >= 0 else "S"
        self.exif[gps + 'Longitude']    = decimal_to_dms(self.longitude)
        self.exif[gps + 'LongitudeRef'] = "E" if self.longitude >= 0 else "W"
        self.exif[gps + 'MapDatum']     = 'WGS-84'
        for iptc in iptc_keys:
            if self[iptc] is not None:
                self.exif['Iptc.Application2.' + iptc] = [self[iptc]]
        self.exif.write()
    
    def set_location(self, lat, lon, ele=None):
        """Alter the coordinates of this photo."""
        if ele is not None:
            self.altitude = ele
        self.latitude  = lat
        self.longitude = lon
        self.position_marker()
        self.City, state, self.CountryCode, timezone = self.geonamer[self]
        self.ProvinceState = get_state(self.CountryCode, state)
        self.CountryName   = get_country(self.CountryCode)
        self.callback(self)
    
    def position_marker(self):
        """Maintain correct position and visibility of ChamplainMarker."""
        if self.valid_coords():
            self.marker.set_position(self.latitude, self.longitude)
            self.marker.show()
            if self.marker.get_highlighted():
                self.marker.raise_top()
        else:
            self.marker.hide()
    
    def set_marker_highlight(self, area, transparent):
        """Set the highlightedness of the given photo's ChamplainMarker."""
        if self.marker.get_property('visible'):
            highlight = area is not None
            self.marker.set_property('opacity', 64 if transparent else 255)
            self.marker.set_scale(*[1.1 if highlight else 1] * 2)
            self.marker.set_highlighted(highlight)
            if highlight:
                self.marker.raise_top()
                lat = self.marker.get_latitude()
                lon = self.marker.get_longitude()
                area[0] = min(area[0], lat)
                area[1] = min(area[1], lon)
                area[2] = max(area[2], lat)
                area[3] = max(area[3], lon)
    
    def valid_coords(self):
        """Check if this photograph contains valid coordinates."""
        return valid_coords(self.latitude, self.longitude)
    
    def maps_link(self):
        """Return a link to Google Maps if this photo has valid coordinates."""
        if self.valid_coords():
            return maps_link(self.latitude, self.longitude)
    
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
        name = format_list([self.City, self.ProvinceState, self.CountryName])
        return sub(", ", ",\n", name) if len(name) > 35 else name
    
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

class GeoCache:
    """Caches geonames.org lookups."""
    
    def __init__(self):
        self.stash = {}
    
    def __getitem__(self, photo):
        """Search cities.txt for nearest city."""
        if not photo.valid_coords():
            return
        key = "%.2f,%.2f" % (photo.latitude, photo.longitude)
        if key in self.stash:
            return self.stash[key]
        near, dist = None, float('inf')
        lat1, lon1 = radians(photo.latitude), radians(photo.longitude)
        with open(get_file("cities.txt")) as cities:
            for city in cities:
                name, lat, lon, country, state, tz = city.split("\t")
                lat2, lon2 = radians(float(lat)), radians(float(lon))
                # lifted from http://www.movable-type.co.uk/scripts/latlong.html
                delta = acos(sin(lat1) * sin(lat2) +
                             cos(lat1) * cos(lat2) *
                             cos(lon2  - lon1))    * earth_radius
                if delta < dist:
                    dist = delta
                    near = [name, state, country, tz]
        self.stash[key] = near
        return near

