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

"""Class for loading and saving photographs."""

from __future__ import division

from gi.repository import Gio, GObject, GdkPixbuf
from pyexiv2 import ImageMetadata
from time import mktime
from os import stat

from gpsmath import Coordinates, format_list
from gpsmath import dms_to_decimal, decimal_to_dms, float_to_rational
from territories import get_state, get_country

# Prefixes for common EXIF keys.
GPS  = 'Exif.GPSInfo.GPS'
IPTC = 'Iptc.Application2.'


class Photograph(Coordinates):
    """Represents a single photograph and it's location in space and time."""
    
    def __init__(self, filename, callback, thumb_size=200):
        """Initialize new Photograph object's attributes with default values."""
        self.filename = filename
        self.callback = callback
        self.thm_size = thumb_size
        self.label    = None
        self.iter     = None
        self.exif     = None
        self.thumb    = None
        self.manual   = None
    
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
        except TypeError:
            raise IOError
        
        # Try to get a thumbnail.
        try:
            self.thumb = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    self.filename, self.thm_size, self.thm_size)
        except GObject.GError:
            if len(self.exif.previews) > 0:
                data = self.exif.previews[-1].data
            elif len(self.exif.exif_thumbnail.data) > 0:
                data = self.exif.exif_thumbnail.data
            else:
                raise IOError
            
            self.thumb = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                Gio.MemoryInputStream.new_from_data(data, None),
                self.thm_size, self.thm_size, True, None)
        
        self.calculate_timestamp()
        try:
            self.latitude = dms_to_decimal(
                *self.exif[GPS + 'Latitude'].value +
                [self.exif[GPS + 'LatitudeRef'].value]
            )
            self.longitude = dms_to_decimal(
                *self.exif[GPS + 'Longitude'].value +
                [self.exif[GPS + 'LongitudeRef'].value]
            )
        except KeyError:
            pass
        try:
            self.altitude = float(self.exif[GPS + 'Altitude'].value)
            if int(self.exif[GPS + 'AltitudeRef'].value) > 0:
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
            self.exif[GPS + 'Altitude']    = float_to_rational(self.altitude)
            self.exif[GPS + 'AltitudeRef'] = '0' if self.altitude >= 0 else '1'
        self.exif[GPS + 'Latitude']     = decimal_to_dms(self.latitude)
        self.exif[GPS + 'LatitudeRef']  = 'N' if self.latitude >= 0 else 'S'
        self.exif[GPS + 'Longitude']    = decimal_to_dms(self.longitude)
        self.exif[GPS + 'LongitudeRef'] = 'E' if self.longitude >= 0 else 'W'
        self.exif[GPS + 'MapDatum']     = 'WGS-84'
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
        city, state, country, tz          = data
        self.exif[IPTC + 'City']          = [city or '']
        self.exif[IPTC + 'ProvinceState'] = [get_state(country, state) or '']
        self.exif[IPTC + 'CountryName']   = [get_country(country) or '']
        self.exif[IPTC + 'CountryCode']   = [country or '']
        self.timezone                     = tz.strip()
    
    def pretty_geoname(self):
        """Override Coordinates.pretty_geoname to read from IPTC."""
        names = []
        for key in [ 'City', 'ProvinceState', 'CountryName' ]:
            try: names.extend(self.exif[IPTC + key].values)
            except KeyError: pass
        length = sum(map(len, names))
        return format_list(names, ',\n' if length > 35 else ', ')

