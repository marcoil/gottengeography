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
from re import compile as re_compile
from pyexiv2 import ImageMetadata
from time import mktime, clock
from calendar import timegm
from datetime import datetime
import dateutil.parser
from os import stat

from utils import Coordinates, format_list
from utils import decimal_to_dms, dms_to_decimal, float_to_rational
from utils import XMLSimpleParser
from territories import get_state, get_country

# Prefixes for common EXIF keys.
gps  = 'Exif.GPSInfo.GPS'
iptc = 'Iptc.Application2.'

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

class TrackFile(Coordinates):
    """Parent class for all track files.
    Subclasses must implement element_start and element_end, and call them in
    the base class."""
    def __init__(self, filename, callback, add_polygon):
        self.add_poly = add_polygon
        self.pulse    = callback
        self.clock    = clock()
        self.append   = None
        self.tracks   = {}
        
        self.__class__.parser.parse(filename, self.element_start, self.element_end)
        
        keys = self.tracks.keys()
        self.alpha = min(keys)
        self.omega = max(keys)
    
    def element_start(self, name, attributes):
        return False
    
    def element_end(self, name, state):
        """Occasionally redraw the screen so that the user can see what's going
        on while stuff is loading."""
        if clock() - self.clock > .2:
            self.pulse(self)
            self.clock = clock()

# GPX files use ISO 8601 dates, which look like 2010-10-16T20:09:13Z.
# This regex splits that up into a list like 2010, 10, 16, 20, 09, 13.
split = re_compile(r'[:TZ-]').split

class GPXFile(TrackFile):
    parser = XMLSimpleParser('gpx', ['trkseg', 'trkpt'])
    
    def __init__(self, filename, callback, add_polygon):
        """Parse a GPX file."""
        
        TrackFile.__init__(self, filename, callback, add_polygon)
    
    def element_start(self, name, attributes):
        """If the element is the start of a new track segment, create a new
        polygon to keep its points. If it's a track point, start accumulating
        its data."""
        TrackFile.element_start(self, name, attributes)
        
        if name == "trkseg":
            self.append = self.add_poly()
        if name == 'trkpt':
            return True
        return False
    
    def element_end(self, name, state):
        """This method does most of the heavy lifting, including parsing time
        strings into UTC epoch seconds, appending to the ChamplainMarkerLayers,
        keeping track of the first and last points loaded.
        """
        # We only care about the trkpt element closing, because that means
        # there is a new, fully-loaded GPX point to play with.
        if name != "trkpt":
            return
        try:
            timestamp = timegm(map(int, split(state['time'])[0:6]))
            lat = float(state['lat'])
            lon = float(state['lon'])
        except Exception as error:
            print error
            # If any of lat, lon, or time is missing, we cannot continue.
            # Better to just give up on this track point and go to the next.
            return
        
        self.tracks[timestamp] = self.append(lat, lon, float(state.get('ele', 0.0)))
        
        TrackFile.element_end(self, name, state)

class KMLFile(TrackFile):
    parser = XMLSimpleParser('kml', ['gx:Track', 'when', 'gx:coord'])
    
    def __init__(self, filename, callback, add_polygon):
        """Parse a KML file."""
        self.whens    = []
        self.coords   = []
        
        TrackFile.__init__(self, filename, callback, add_polygon)
    
    def element_start(self, name, attributes):
        """Create new ChamplainMarkerLayers for each gx:Track element.
        If it's another element, start keeping its data."""
        TrackFile.element_start(self, name, attributes)
        
        if name == 'gx:Track':
            self.append = self.add_poly()
            return False
        return True
    
    def element_end(self, name, state):
        """Keep parallel arrays of whens and gx:coords. When we have a complete
        pair, add it to out tracks.
        """
        if name == "when":
            try:
                timestamp = dateutil.parser.parse(state['when'])
            except Exception as error:
                print error
                return
            self.whens.append(mktime(timestamp.timetuple()))
        if name == "gx:coord":
            self.coords.append(state['gx:coord'].split())
        
        complete = min(len(self.whens), len(self.coords))
        if complete > 0:
            for i in range(0, complete):
                self.tracks[self.whens[i]] = \
                    self.append(float(self.coords[i][1]), \
                                float(self.coords[i][0]), \
                                float(self.coords[i][2]))
            self.whens = self.whens[complete:]
            self.coords = self.coords[complete:]
        
        TrackFile.element_end(self, name, state)

