# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Class for loading and saving photographs."""

from __future__ import division

from gi.repository import Gio, GObject, GdkPixbuf
from pyexiv2 import ImageMetadata
from time import mktime
from os import stat

from label import Label
from widgets import Widgets
from xmlfiles import TrackFile
from camera import Camera, CameraView
from gpsmath import Coordinates, float_to_rational
from gpsmath import dms_to_decimal, decimal_to_dms
from common import Gst, memoize, points, modified

# Prefixes for common EXIF keys.
GPS  = 'Exif.GPSInfo.GPS'
IPTC = 'Iptc.Application2.'


# This function is the embodiment of my applications core logic.
# Everything else is just implementation details.
def auto_timestamp_comparison(photo):
    """Use GPX data to calculate photo coordinates and elevation."""
    if photo.manual or len(TrackFile.range) < 2:
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

def fetch_thumbnail(filename, size=Gst.get_int('thumbnail-size')):
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
    files = instances.viewvalues()
    camera_info = None
    manual = False
    camera = None
    label = None
    exif = None
    iter = None
    
    @staticmethod
    def resize_all_photos(gst, key):
        """Reload all the thumbnails when the GSetting changes."""
        # TODO: There's probably a more GObjecty way to do this with properties
        # TODO: Is it necessary to reload every time? Probably could just load
        # the max size to start and then scale it down to the requested size on
        # the fly. But this works for now.
        size = gst.get_int(key)
        for photo in Photograph.files:
            photo.thumb = fetch_thumbnail(photo.filename, size)
            Widgets.loaded_photos.set_value(photo.iter, 2, photo.thumb)
    
    @staticmethod
    def load_from_file(uri):
        """Coordinates instantiation of various classes.
        
        Ensures that related Photograph, Camera, CameraView, and Label are all
        instantiated together.
        """
        photo = Photograph(uri)
        photo.read()
        
        Widgets.empty_camera_list.hide()
        
        camera_id, camera_name = Camera.generate_id(photo.camera_info)
        camera = Camera(camera_id)
        camera.add_photo(photo)
        
        CameraView(camera, camera_name)
        Label(photo)
        
        # If the user has selected the lookup method, then the timestamp
        # was probably calculated incorrectly the first time (before the
        # timezone was discovered). So call it again to get the correct value.
        if camera.timezone_method == 'lookup':
            photo.calculate_timestamp(camera.offset)
        
        Widgets.photos_selection.emit('changed')
        
        return photo
    
    def __init__(self, filename):
        """Raises IOError for invalid file types.
        
        This MUST be the case in order to avoid the @memoize cache getting
        filled up with invalid Photograph instances.
        """
        Coordinates.__init__(self)
        self.thumb = fetch_thumbnail(filename)
        self.filename = filename
        
        self.connect('notify::geoname', self.update_liststore_summary)
        self.connect('notify::positioned', self.respond_positioned)
    
    def read(self):
        """Discard all state and (re)initialize from disk."""
        self.exif = fetch_exif(self.filename)
        self.manual = False
        self.modified_timeout = None
        self.latitude = 0.0
        self.longitude = 0.0
        self.altitude = 0.0
        self.timestamp = 0
        
        self.city = ''
        self.provincestate = ''
        self.countryname = ''
        self.geotimezone = ''
        
        modified.discard(self)
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
                                                  self.markup_summary(),
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
    
    def calculate_timestamp(self, offset=0):
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
        self.exif[IPTC + 'City']          = [self.city or '']
        self.exif[IPTC + 'ProvinceState'] = [self.provincestate or '']
        self.exif[IPTC + 'CountryName']   = [self.countryname or '']
        self.exif.write()
        modified.discard(self)
        Widgets.loaded_photos.set_value(self.iter, 1, self.markup_summary())
    
    def disable_auto_position(self):
        """Indicate that the user has manually positioned the photo.
        
        This prevents it from snapping to any available GPS data automatically.
        """
        self.manual = True
    
    def set_location(self, lat, lon, ele=None):
        """Alter the coordinates of this photo."""
        if ele is not None:
            self.altitude = ele
        self.latitude  = lat
        self.longitude = lon
    
    def respond_positioned(self, *ignore):
        """If a photo has been placed on the map, make it saveable."""
        if self.positioned:
            modified.add(self)
            Widgets.photos_selection.emit('changed')
    
    def update_liststore_summary(self, *ignore):
        """Update the text displayed in the GtkListStore."""
        modified.add(self)
        if self.iter is not None:
            Widgets.loaded_photos.set_value(self.iter, 1, self.markup_summary())
        if self.camera and self.camera.found_timezone is not self.geotimezone:
            self.camera.found_timezone = self.geotimezone
    
    def destroy(self):
        """Agony!"""
        self.update_derived_properties() # To clear any callback...
        # TODO: Disconnect this from here
        if self in Label.instances:
            Label(self).destroy()
        if self.camera is not None:
            self.camera.remove_photo(self)
        modified.discard(self)
        if self.iter:
            Widgets.loaded_photos.remove(self.iter)
        del Photograph.instances[self.filename]

