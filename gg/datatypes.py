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

import os
import time
import json
import pyexiv2

from gettext import gettext as _
from gi.repository import Gio, GdkPixbuf

from gps import *

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

class Photograph(ReadableDictionary):
    """Represents a single photograph and it's location in space and time."""
    
    def __init__(self, filename, cache, callback, thumb_size=200):
        """Initialize new Photograph object's attributes with default values."""
        gps = 'Exif.GPSInfo.GPS'
        self.filename = filename
        self.cache    = cache
        self.callback = callback
        self.manual   = False
        for key in [ 'timestamp', 'altitude', 'latitude', 'longitude',
        'marker', 'iter', 'timezone' ] + geonames_of_interest.values():
            self[key] = None
        try:
            self.exif = pyexiv2.ImageMetadata(filename)
            self.exif.read()
            self.thumb = GdkPixbuf.Pixbuf.new_from_file_at_size(
                filename, thumb_size, thumb_size)
        except:
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
        except:
            pass
        for iptc in geonames_of_interest.values():
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
            self.timestamp = int(time.mktime(
                self.exif['Exif.Photo.DateTimeOriginal'].value.timetuple()))
        except:
            self.timestamp = int(os.stat(self.filename).st_mtime)
    
    def set_location(self, lat, lon, ele=None):
        """Alter the coordinates of this photo."""
        if ele is not None:
            self.altitude = ele
        self.latitude  = lat
        self.longitude = lon
        self.position_marker()
        self.cache.request_geoname(self)
        self.callback(self)
    
    def set_geoname(self, geoname):
        """Insert geonames into the photo."""
        for geocode, iptc in geonames_of_interest.items():
            self[iptc] = geoname.get(geocode)
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
        return maps_link(self.latitude, self.longitude) if self.valid_coords() else ""
    
    def pretty_time(self):
        """Convert epoch seconds to a human-readable date."""
        return _("No timestamp") if type(self.timestamp) is not int else \
            time.strftime("%Y-%m-%d %X", time.localtime(self.timestamp))
    
    def pretty_coords(self):
        """Add cardinal directions to decimal coordinates."""
        return _("Not geotagged") if not self.valid_coords() else \
            format_coords(self.latitude, self.longitude)
    
    def pretty_geoname(self):
        """Display city, state, and country, if present."""
        names, length = [], 0
        for value in [self.City, self.ProvinceState, self.CountryName]:
            if type(value) in (str, unicode) and len(value) > 0:
                names.append(value)
                length += len(value)
        return (",\n" if length > 35 else ", ").join(names)
    
    def pretty_elevation(self):
        """Convert elevation into a human readable format."""
        return "" if type(self.altitude) not in (float, int) else "%.1f%s" % (
            abs(self.altitude),
            _("m above sea level")
            if self.altitude >= 0 else
            _("m below sea level")
        )
    
    def short_summary(self):
        """Plaintext summary of photo metadata."""
        strings = []
        for value in [self.pretty_time(), self.pretty_coords(),
        self.pretty_geoname(), self.pretty_elevation()]:
            if type(value) in (str, unicode) and len(value) > 0:
                strings.append(value)
        return "\n".join(strings)
    
    def long_summary(self):
        """Longer summary with Pango markup."""
        return ('<span size="larger">%s</span>\n<span style="italic" size="smaller">%s</span>' % (
            os.path.basename(self.filename),
            self.short_summary()
        )).encode('utf-8')

class GeoCache:
    """This class serves as a data store for caching geonames.org data."""
    
    def __init__(self):
        self.stash = {}
        self.queue = {}
    
    def request_geoname(self, photo):
        """Use the GeoNames.org webservice to name coordinates."""
        if not photo.valid_coords():
            return
        key = "%.2f,%.2f" % (photo.latitude, photo.longitude)
        if key in self.stash:
            if self.stash[key] is None:
                self.queue[key].append(photo)
            else:
                photo.set_geoname(self.stash[key])
        else:
            self.queue[key] = [photo]
            self.stash[key] = None
            gfile = Gio.file_new_for_uri(
                'http://ws.geonames.org/findNearbyJSON?lat=%s&lng=%s'
                % (photo.latitude, photo.longitude) +
                '&fclass=P&fcode=PPLA&fcode=PPL&fcode=PPLC&style=full')
            gfile.load_contents_async(None, self.receive_geoname, key)
    
    def receive_geoname(self, gfile, result, key):
        """This callback method is executed when geoname download completes."""
        try:
            obj = json.loads(gfile.load_contents_finish(result)[1])
        except Exception as inst:
            del self.queue[key]
            del self.stash[key]
            print inst
        else:
            if "status" in obj:
                print obj["status"]
                del self.queue[key]
                del self.stash[key]
            elif "geonames" in obj:
                self.stash[key] = obj['geonames'][0]
                print self.stash[key]
                while len(self.queue[key]) > 0:
                    self.queue[key].pop().set_geoname(self.stash[key])

# This dictionary maps geonames.org jargon (keys) into IPTC jargon (values).
geonames_of_interest = {
    'countryCode': 'CountryCode',
    'countryName': 'CountryName',
    'adminName1':  'ProvinceState',
    'name':        'City'
}
