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

import os, time, json
from gettext import gettext as _
from gi.repository import Gio

from gps import valid_coords

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
    
    def __init__(self, filename, thumb, cache, callback):
        """Initialize new Photograph object's attributes with default values."""
        self.filename = filename
        self.thumb    = thumb
        self.cache    = cache
        self.callback = callback
        self.manual   = False
        for key in [ 'timestamp', 'altitude', 'latitude', 'longitude',
        'CountryName', 'CountryCode', 'ProvinceState', 'City',
        'marker', 'iter', 'timezone' ]:
            self[key] = None
    
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
    
    def pretty_time(self):
        """Convert epoch seconds to a human-readable date."""
        return _("No timestamp") if type(self.timestamp) is not int else \
            time.strftime("%Y-%m-%d %X", time.localtime(self.timestamp))
    
    def pretty_coords(self):
        """Add cardinal directions to decimal coordinates."""
        return _("Not geotagged") if not self.valid_coords() else \
            '%s %.5f, %s %.5f' % (
                _("N") if self.latitude  >= 0 else _("S"), abs(self.latitude),
                _("E") if self.longitude >= 0 else _("W"), abs(self.longitude)
            )
    
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
            obj = json.loads(gfile.load_contents_finish(result)[1])['geonames']
        except:
            if key in self.queue: del self.queue[key]
            if key in self.stash: del self.stash[key]
            return
        geoname = {}
        for data in obj:
            geoname.update(data)
        self.stash[key] = geoname
        while len(self.queue[key]) > 0:
            photo = self.queue[key].pop()
            photo.set_geoname(geoname)

# This dictionary maps geonames.org jargon (keys) into IPTC jargon (values).
geonames_of_interest = {
    'countryCode': 'CountryCode',
    'countryName': 'CountryName',
    'adminName1':  'ProvinceState',
    'name':        'City'
}
