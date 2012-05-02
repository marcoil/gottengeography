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

from xml.parsers.expat import ParserCreate, ExpatError
from gi.repository import GdkPixbuf, Gio, GObject
from re import compile as re_compile
from pyexiv2 import ImageMetadata
from time import mktime, clock
from calendar import timegm
from os import stat

from utils import Coordinates, format_list
from utils import decimal_to_dms, dms_to_decimal, float_to_rational
from territories import get_state, get_country

# Prefixes for common EXIF keys.
gps  = 'Exif.GPSInfo.GPS'
iptc = 'Iptc.Application2.'

def pixbuf_from_data(data, size):
    input_str = Gio.MemoryInputStream.new_from_data(data, None)
    pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
        input_str, size, size, True, None)
    return pixbuf

class Photograph(Coordinates):
    """Represents a single photograph and it's location in space and time."""
    
    def __init__(self, filename, callback, thumb_size=200):
        """Initialize new Photograph object's attributes with default values."""
        self.filename = filename
        self.callback = callback
        self.thm_size = thumb_size
        self.label    = None
        self.iter     = None
    
    def read(self):
        """Load exif data from disk."""
        self.exif      = ImageMetadata(self.filename)
        self.timestamp = None
        self.altitude  = None
        self.latitude  = None
        self.longitude = None
        self.timezone  = None
        self.manual    = False
        """Load the metadata."""
        try:
            self.exif.read()
        except TypeError:
            raise IOError
        
        """Try to get a thumbnail."""
        try:
            self.thumb = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    self.filename, self.thm_size, self.thm_size)
        except GObject.GError:
            if len(self.exif.previews) > 0:
                self.thumb = pixbuf_from_data(self.exif.previews[-1].data,
                    self.thm_size)
            elif len(self.exif.exif_thumbnail.data) > 0:
                self.thumb = pixbuf_from_data(self.exif.exif_thumbnail.data,
                    self.thm_size)
            else:
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
            self.altitude = float(self.exif[gps + 'Altitude'].value)
            if int(self.exif[gps + 'AltitudeRef'].value) > 0:
                self.altitude *= -1
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
        self.exif.write()
    
    def set_location(self, lat, lon, ele=None):
        """Alter the coordinates of this photo."""
        if ele is not None:
            self.altitude = ele
        self.latitude  = lat
        self.longitude = lon
        self.position_label()
        self.lookup_geoname()
        self.callback(self)
    
    def position_label(self):
        """Maintain correct position and visibility of ChamplainLabel."""
        if self.valid_coords():
            self.label.set_location(self.latitude, self.longitude)
            self.label.show()
            if self.label.get_selected():
                self.label.raise_top()
        else:
            self.label.hide()
    
    def set_label_highlight(self, highlight, transparent):
        """Set the highlightedness of the given photo's ChamplainLabel."""
        if self.label.get_property('visible'):
            self.label.set_scale(*[1.1 if highlight else 1] * 2)
            self.label.set_selected(highlight)
            self.label.set_opacity(64 if transparent and not highlight else 255)
            if highlight:
                self.label.raise_top()
    
    def set_geodata(self, data):
        """Override Coordinates.set_geodata to apply directly into IPTC."""
        city, state, countrycode, tz      = data
        self.exif[iptc + 'City']          = [city or ""]
        self.exif[iptc + 'ProvinceState'] = [get_state(countrycode, state) or ""]
        self.exif[iptc + 'CountryName']   = [get_country(countrycode) or ""]
        self.exif[iptc + 'CountryCode']   = [countrycode or ""]
        self.timezone                     = tz.strip()
    
    def pretty_geoname(self):
        """Override Coordinates.pretty_geoname to read from IPTC."""
        names = []
        for key in [ 'City', 'ProvinceState', 'CountryName' ]:
            try: names.extend(self.exif[iptc + key].values)
            except KeyError: pass
        length = sum(map(len, names))
        return format_list(names, ',\n' if length > 35 else ', ')

# GPX files use ISO 8601 dates, which look like 2010-10-16T20:09:13Z.
# This regex splits that up into a list like 2010, 10, 16, 20, 09, 13.
split = re_compile(r'[:TZ-]').split

class GPXLoader(Coordinates):
    """Use expat to parse GPX data quickly."""
    
    def __init__(self, filename, callback, add_polygon):
        """Create the parser and begin parsing."""
        self.add_poly = add_polygon
        self.filename = filename
        self.pulse    = callback
        self.clock    = clock()
        self.append   = None
        self.tracks   = {}
        self.state    = {}
        
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
    
    def element_root(self, name, attributes):
        """Expat StartElementHandler.
        
        This is only called on the top level element in the given XML file.
        """
        if name != 'gpx':
            raise IOError
        self.parser.StartElementHandler = self.element_start
    
    def element_start(self, name, attributes):
        """Expat StartElementHandler.
        
        This method creates new ChamplainMarkerLayers when necessary and initializes
        variables for the CharacterDataHandler. It also extracts latitude and
        longitude from GPX element attributes. For example:
        
        <trkpt lat="45.147445" lon="-81.469507">
        """
        self.element     = name
        self.state[name] = ""
        self.state.update(attributes)
        if name == "trkseg":
            self.append = self.add_poly()
    
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
        strings into UTC epoch seconds, appending to the ChamplainMarkerLayers,
        keeping track of the first and last points loaded, and occaisionally
        redrawing the screen so that the user can see what's going on while
        stuff is loading.
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
        
        self.tracks[timestamp] = self.append(lat, lon, float(self.state.get('ele', 0.0)))
        
        self.state.clear()
        if clock() - self.clock > .2:
            self.pulse(self)
            self.clock = clock()

