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

from common import modified, get_obj
from common import auto_timestamp_comparison
from gpsmath import Coordinates, float_to_rational
from gpsmath import dms_to_decimal, decimal_to_dms
from territories import get_state, get_country
from label import Label

# Prefixes for common EXIF keys.
GPS  = 'Exif.GPSInfo.GPS'
IPTC = 'Iptc.Application2.'


class Photograph(Coordinates):
    """Represents a single photograph and it's location in space and time."""
    liststore = get_obj('loaded_photos')
    instances = {}
    camera_info = None
    manual = None
    camera = None
    label = None
    exif = None
    iter = None
    
    @staticmethod
    def get(filename):
        """Find an existing Photograph instance, or create a new one."""
        photo = Photograph.instances.get(filename) or Photograph(filename)
        photo.read()
        Photograph.instances[filename] = photo
        return photo
    
    def __init__(self, filename):
        self.filename = filename
    
    def fetch_exif(self):
        """Read the EXIF data from the file."""
        if self.exif is not None:
            return
        self.exif = ImageMetadata(self.filename)
        try:
            self.exif.read()
        except TypeError:
            raise IOError
    
    def fetch_thumbnail(self, size=200):
        """Return the file's thumbnail as best as possible.
        
        This is used in the preview widget without fully loading the file. It
        can potentially cause EXIF data to be read, but only if GdkPixbuf
        fails at generating a thumbnail by itself.
        """
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_size(
                self.filename, size, size)
        except GObject.GError:
            self.fetch_exif()
            if len(self.exif.previews) > 0:
                data = self.exif.previews[-1].data
            elif len(self.exif.exif_thumbnail.data) > 0:
                data = self.exif.exif_thumbnail.data
            else:
                raise IOError
            
            return GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                Gio.MemoryInputStream.new_from_data(data, None),
                size, size, True, None)
    
    def read(self):
        """Discard all state and (re)initialize from disk."""
        self.exif      = None
        self.timestamp = None
        self.altitude  = None
        self.latitude  = None
        self.longitude = None
        self.timezone  = None
        self.manual    = False
        
        self.fetch_exif()
        
        # If we're re-loading, we'll have to hide the old label
        if self.label is None:
            self.label = Label(self)
        else:
            self.label.hide()
        
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
        
        if self.iter is None:
            self.iter = self.liststore.append()
        self.liststore.set_row(self.iter, [self.filename,
                                           self.long_summary(),
                                           self.fetch_thumbnail(),
                                           self.timestamp])
        
        # Get the camera info
        self.camera_info = {'Make': '', 'Model': ''}
        keys = ['Exif.Image.' + key for key in self.camera_info.keys()
                    + ['CameraSerialNumber']] + ['Exif.Photo.BodySerialNumber']
        for key in keys:
            try:
                self.camera_info.update(
                    {key.split('.')[-1]: self.exif[key].value})
            except KeyError:
                pass
    
    def calculate_timestamp(self, offset = 0):
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
        self.timestamp += offset
        if self.label is not None:
            auto_timestamp_comparison(self)
    
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
        modified.discard(self)
        self.liststore.set_value(self.iter, 1, self.long_summary())
    
    def set_location(self, lat, lon, ele=None):
        """Alter the coordinates of this photo."""
        if ele is not None:
            self.altitude = ele
        self.latitude  = lat
        self.longitude = lon
        self.position_label()
        self.lookup_geoname()
        self.modify_summary()
    
    def modify_summary(self):
        """Update the text displayed in the GtkListStore."""
        modified.add(self)
        if self.iter is not None:
            self.liststore.set_value(self.iter, 1,
                ('<b>%s</b>' % self.long_summary()))
    
    def position_label(self):
        """Maintain correct position and visibility of ChamplainLabel."""
        if self.label.get_parent() is None:
            return
        if self.valid_coords():
            self.label.set_location(self.latitude, self.longitude)
            self.label.show()
            if self.label.get_selected():
                self.label.raise_top()
        else:
            self.label.hide()
    
    def set_geodata(self, data):
        """Override Coordinates.set_geodata to apply directly into IPTC."""
        city, state, country, tz          = data
        self.exif[IPTC + 'City']          = [city or '']
        self.exif[IPTC + 'ProvinceState'] = [get_state(country, state) or '']
        self.exif[IPTC + 'CountryName']   = [get_country(country) or '']
        self.exif[IPTC + 'CountryCode']   = [country or '']
        self.timezone                     = tz.strip()
        if self.camera is not None:
            self.camera.set_found_timezone(self.timezone)
    
    def pretty_geoname(self):
        """Override Coordinates.pretty_geoname to read from IPTC."""
        names = []
        for key in [ 'City', 'ProvinceState', 'CountryName' ]:
            try:
                names.extend(self.exif[IPTC + key].values)
            except KeyError:
                pass
        return ', '.join([name for name in names if name])
    
    def destroy(self):
        """Agony!"""
        if self.label:
            self.label.unmap()
            self.label.destroy()
        if self.camera is not None:
            self.camera.remove_photo(self)
        del Photograph.instances[self.filename]
        modified.discard(self)
        if self.iter:
            self.liststore.remove(self.iter)

