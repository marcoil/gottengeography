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

from gi.repository import GdkPixbuf, GObject
from xml.parsers.expat import ParserCreate, ExpatError
from time import strftime, mktime, localtime, clock
from re import sub, compile as re_compile
from pyexiv2 import ImageMetadata
from gettext import gettext as _
from os.path import basename
from calendar import timegm
from os import stat

from territories import get_state, get_country
from utils import decimal_to_dms, dms_to_decimal, float_to_rational
from utils import valid_coords, format_coords, iptc_keys, format_list
from utils import ReadableDictionary, Coordinates

gps = 'Exif.GPSInfo.GPS' # This is a prefix for common EXIF keys.

class Photograph(ReadableDictionary, Coordinates):
    """Represents a single photograph and it's location in space and time."""
    
    def __init__(self, filename, callback, thumb_size=200):
        """Initialize new Photograph object's attributes with default values."""
        self.exif     = ImageMetadata(filename)
        self.filename = filename
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
                self[iptc.lower()] = self.exif['Iptc.Application2.' + iptc].values[0]
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
            if self[iptc.lower()] is not None:
                self.exif['Iptc.Application2.' + iptc] = [self[iptc.lower()]]
        self.exif.write()
    
    def set_location(self, lat, lon, ele=None):
        """Alter the coordinates of this photo."""
        if ele is not None:
            self.altitude = ele
        self.latitude  = lat
        self.longitude = lon
        self.position_marker()
        self.lookup_geoname()
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

# GPX files use ISO 8601 dates, which look like 2010-10-16T20:09:13Z.
# This regex splits that up into a list like 2010, 10, 16, 20, 09, 13.
split = re_compile(r'[:TZ-]').split

class GPXLoader(Coordinates):
    """Use expat to parse GPX data quickly."""
    
    def __init__(self, filename, callback, add_polygon):
        """Create the parser and begin parsing."""
        self.polygon  = None
        self.add_poly = add_polygon
        self.pulse    = callback
        self.clock    = clock()
        self.tracks   = {}
        self.state    = {}
        self.area     = []
        
        self.parser = ParserCreate()
        self.parser.StartElementHandler  = self.element_root
        self.parser.CharacterDataHandler = self.element_data
        self.parser.EndElementHandler    = self.element_end
        
        try:
            with open(filename) as gpx:
                self.parser.ParseFile(gpx)
        except ExpatError:
            raise IOError
        
        keys = self.tracks.keys()
        self.alpha = min(keys)
        self.omega = max(keys)
        
        points = self.tracks.values()
        lats   = [p["point"].lat for p in points]
        lons   = [p["point"].lon for p in points]
        self.area.append(min(lats))
        self.area.append(min(lons))
        self.area.append(max(lats))
        self.area.append(max(lons))
        
        self.latitude  = (self.area[0] + self.area[2]) / 2
        self.longitude = (self.area[1] + self.area[3]) / 2
    
    def element_root(self, name, attributes):
        """Expat StartElementHandler.
        
        This is only called on the top level element in the given XML file.
        """
        if name != 'gpx':
            raise IOError
        self.parser.StartElementHandler = self.element_start
    
    def element_start(self, name, attributes):
        """Expat StartElementHandler.
        
        This method creates new ChamplainPolygons when necessary and initializes
        variables for the CharacterDataHandler. It also extracts latitude and
        longitude from GPX element attributes. For example:
        
        <trkpt lat="45.147445" lon="-81.469507">
        """
        self.element     = name
        self.state[name] = ""
        self.state.update(attributes)
        if name == "trkseg":
            self.polygon = self.add_poly()
    
    def element_data(self, data):
        """Expat CharacterDataHandler.
        
        This method extracts elevation and time data from GPX elements.
        For example:
        
        <ele>671.092</ele>
        <time>2010-10-16T20:09:13Z</time>
        """
        data = data.strip()
        if not data:
            return
        # Sometimes expat calls this handler multiple times each with just
        # a chunk of the whole data, so += is necessary to collect all of it.
        self.state[self.element] += data
    
    def element_end(self, name):
        """Expat EndElementHandler.
        
        This method does most of the heavy lifting, including parsing time
        strings into UTC epoch seconds, appending to the ChamplainPolygons,
        keeping track of the first and last points loaded, as well as the
        entire area covered by the polygon, and occaisionally redrawing the
        screen so that the user can see what's going on while stuff is
        loading.
        """
        # We only care about the trkpt element closing, because that means
        # there is a new, fully-loaded GPX point to play with.
        if name != "trkpt":
            return
        try:
            timestamp = timegm(map(int, split(self.state['time'])[0:6]))
            lat = float(self.state['lat'])
            lon = float(self.state['lon'])
        except Exception as error:
            print error
            # If any of lat, lon, or time is missing, we cannot continue.
            # Better to just give up on this track point and go to the next.
            return
        self.tracks[timestamp] = {
            'elevation': float(self.state.get('ele', 0.0)),
            'point':     self.polygon.append_point(lat, lon)
        }
        
        self.state.clear()
        if clock() - self.clock > .2:
            self.pulse(self)
            self.clock = clock()

