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

from label import Label
from xmlfiles import TrackFile
from territories import get_state, get_country
from gpsmath import Coordinates, float_to_rational
from gpsmath import dms_to_decimal, decimal_to_dms
from common import Widgets, memoize, points, modified

# Prefixes for common EXIF keys.
GPS  = 'Exif.GPSInfo.GPS'
IPTC = 'Iptc.Application2.'


# This function is the embodiment of my applications core logic.
# Everything else is just implementation details.
def auto_timestamp_comparison(photo):
    """Use GPX data to calculate photo coordinates and elevation."""
    if photo.manual or len(points) < 2:
        return
    
    # Clamp the timestamp within the range of available GPX points.
    # The result is in epoch seconds, just like the keys of the 'points' dict.
    stamp = sorted(TrackFile.range + [photo.timestamp])[1]
    
    try:
        point = points[stamp] # Try to use an exact match,
        lat   = point.lat     # if such a thing were to exist.
        lon   = point.lon     # It's more likely than you think. 50%
        ele   = point.ele     # of the included demo data matches here.
    
    except KeyError:
        # Find the two points that are nearest (in time) to the photo.
        hi = min([point for point in points if point > stamp])
        lo = max([point for point in points if point < stamp])
        hi_point = points[hi]
        lo_point = points[lo]
        hi_ratio = (stamp - lo) / (hi - lo)  # Proportional amount of time
        lo_ratio = (hi - stamp) / (hi - lo)  # between each point & the photo.
        
        # Find intermediate values using the proportional ratios.
        lat = ((lo_point.lat * lo_ratio)  +
               (hi_point.lat * hi_ratio))
        lon = ((lo_point.lon * lo_ratio)  +
               (hi_point.lon * hi_ratio))
        ele = ((lo_point.ele * lo_ratio)  +
               (hi_point.ele * hi_ratio))
    
    photo.set_location(lat, lon, ele)

def fetch_exif(filename):
    """Load EXIF data from disk."""
    exif = ImageMetadata(filename)
    try:
        exif.read()
    except TypeError:
        raise IOError
    return exif

def fetch_thumbnail(filename, size=200):
    """Load a photo's thumbnail from disk, avoiding EXIF data if possible."""
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(filename, size, size)
    except GObject.GError:
        exif = fetch_exif(filename)
        if len(exif.previews) > 0:
            data = exif.previews[-1].data
        elif len(exif.exif_thumbnail.data) > 0:
            data = exif.exif_thumbnail.data
        else:
            raise IOError
        
        return GdkPixbuf.Pixbuf.new_from_stream_at_scale(
            Gio.MemoryInputStream.new_from_data(data, None),
            size, size, True, None)

@memoize
class Photograph(Coordinates):
    """Represents a single photograph and it's location in space and time."""
    instances = {}
    camera_info = None
    manual = None
    camera = None
    label = None
    exif = None
    iter = None
    
    def __init__(self, filename):
        """Raises IOError for invalid file types.
        
        This MUST be the case in order to avoid the @memoize cache getting
        filled up with invalid Photograph instances."""
        self.thumb = fetch_thumbnail(filename)
        self.filename = filename
    
    def read(self):
        """Discard all state and (re)initialize from disk."""
        self.exif      = fetch_exif(self.filename)
        self.timestamp = None
        self.altitude  = None
        self.latitude  = None
        self.longitude = None
        self.timezone  = None
        self.manual    = False
        
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
            self.iter = Widgets.loaded_photos.append()
        Widgets.loaded_photos.set_row(self.iter, [self.filename,
                                           self.long_summary(),
                                           self.thumb,
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
        Widgets.loaded_photos.set_value(self.iter, 1, self.long_summary())
    
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
            Widgets.loaded_photos.set_value(self.iter, 1,
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
        del Photograph().instances[self.filename]
        modified.discard(self)
        if self.iter:
            Widgets.loaded_photos.remove(self.iter)

