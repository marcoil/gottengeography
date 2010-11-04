#!/usr/bin/env python
# coding=utf-8

# GottenGeography - Automagically geotags photos by comparing timestamps to GPX data
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

from __future__ import division
#from __future__ import calculus # too advanced for us cavemen

import pyexiv2, os, re, time, calendar, math, gettext
from gi.repository import Gtk, GObject, Gdk, GdkPixbuf, GConf
from gi.repository import Clutter, Champlain, GtkChamplain
from xml.parsers import expat
from fractions import Fraction

# "If I have seen a little further it is by standing on the shoulders of Giants."
#                                    --- Isaac Newton

VERSION = "0.1.3"

class GottenGeography:
    
    t = gettext.translation("gottengeography", "/usr/share/locale/")
    _ = t.ugettext
    t.install()
    
################################################################################
# Pretty string methods. These methods take numbers as input and return strings
# that are suitable for displaying to the user.
################################################################################
    
    def _pretty_coords(self, lat, lon):
        """Add cardinal directions to decimal coordinates."""
        
        if lat > 0: lat_sign = _("N")
        else:       lat_sign = _("S")
        if lon > 0: lon_sign = _("E")
        else:       lon_sign = _("W")
        
        # Eg, "N nn.nnnnn, W nnn.nnnnn"
        return ("%s %.5f, %s %.5f" % 
            (lat_sign, abs(lat), lon_sign, abs(lon)))
    
    def _pretty_time(self, timestamp):
        """Print time in a human readable way.
        
        Takes either a datetime.datetime or epoch seconds in int/float."""
        
        if timestamp is None: return "No timestamp"
        
        try:    return timestamp.strftime("%Y-%m-%d %X")
        except: return time.strftime("%Y-%m-%d %X", time.localtime(timestamp))
    
    def _create_summary(self, file, timestamp, lat=None, lon=None, ele=None, modified=False):
        """Describe photo metadata with Pango formatting."""
        
        if self.valid_coords(lat, lon): 
            summary = self._pretty_coords(lat, lon)
        else:
            summary = _("Not geotagged")
        
        summary = "%s\n%s" % (self._pretty_time(timestamp), summary)
        
        if ele: summary += "\n%.1f%s" % (ele, _("m above sea level"))
        
        # Eg:
        # filename.jpg
        # N nn.nnnnn, W nnn.nnnnn
        # 540.6m above sea level
        summary = (
            '<span size="larger">%s</span>\n<span style="italic" size="smaller">%s</span>' % 
            (os.path.basename(file), summary)
        )
        
        # Embolden text if this image has unsaved data
        if modified: summary = '<b>%s</b>' % summary
        
        return summary
    
################################################################################
# GPS math. These methods convert numbers into other numbers.
################################################################################
    
    def dms_to_decimal(self, (degrees, minutes, seconds), sign=""):
        """Convert degrees, minutes, seconds into decimal degrees."""
        
        # The south and the west hemispheres are considered "negative"
        if re.match("[SWsw]", sign): sign = -1
        else:                        sign =  1
        
        return ((degrees.numerator / degrees.denominator)         + 
                (minutes.numerator / minutes.denominator) / 60    + 
                (seconds.numerator / seconds.denominator) / 3600) * sign
    
    def decimal_to_dms(self, decimal, is_latitude):
        """Convert decimal degrees into degrees, minutes, seconds."""
        
        # Don't translate these strings as they're stored in EXIF, which
        # defines them in English only.
        if is_latitude:
            if decimal > 0: sign = "N"
            else:           sign = "S"
        else:
            if decimal > 0: sign = "E"
            else:           sign = "W"
        
        # math.modf splits a float into it's remainder and largest whole number
        (remainder, degrees) = math.modf(abs(decimal))
        (remainder, minutes) = math.modf(remainder * 60)
        seconds              = remainder * 60
        
        return [ pyexiv2.Rational(degrees, 1),
                 pyexiv2.Rational(minutes, 1),
                 self.float_to_rational(seconds) ], sign
    
    def float_to_rational(self, decimal):
        """Converts a float to a pyexiv2.Rational using fractions.Fraction()."""
        
        # fractions.Fraction() method claims to be able to convert a 
        # float to a fraction, but it seems to be broken. Fortunately, 
        # if I cast the float to a string first, that seems to work. 
        # limit_denominator() causes some rounding to occur which 
        # could reduce precision, but it's mostly just rounding out
        # the imprecision inherent to a float. 
        fraction = Fraction(str(decimal)).limit_denominator(10000)
        return pyexiv2.Rational(fraction.numerator, fraction.denominator)
    
    def valid_coords(self, lat, lon):
        """Determine the validity of coordinates."""
        
        if type(lat) is not float: return False
        if type(lon) is not float: return False
        
        return lat >= -90 and lat <= 90 and lon >= -180 and lon <= 180
    
################################################################################
# Champlain. This section contains methods that manipulate the map.
################################################################################
    
    def remember_location(self):
        """Add the current location to the history stack."""
        
        self.history.append( [
            self.map_view.get_property('latitude'),
            self.map_view.get_property('longitude'),
            self.map_view.get_zoom_level()
        ] )
    
    def return_to_last(self, button=None):
        """Return the map view to where the user last set it."""
        
        try:
            last = self.history.pop()
        except IndexError:
            self.back_button.set_sensitive(False)
        else:
            self.map_view.center_on(last[0], last[1])
            self.map_view.set_zoom_level(last[2])
        
        self.update_sensitivity()
    
    def zoom_in(self, button=None):
        """Zoom the map in by one level."""
        
        self.map_view.zoom_in()
        self.update_sensitivity()
    
    def zoom_out(self, button=None):
        """Zoom the map out by one level."""
        
        self.map_view.zoom_out()
        self.update_sensitivity()
    
    def move_map_view_by_arrow_keys(self, accel_group, acceleratable, keyval, modifier):
        """Move the map view, taking into account the current zoom."""
        
        lat = self.map_view.get_property('latitude')
        lon = self.map_view.get_property('longitude')
        
        # 10 / (1 + 4zoom^3) where zoom is the map zoom level from 0 to 20)
        # This makes the map move by 10 degrees at zoom level 0, but only
        # 0.0003125 degrees at maximum zoom (which is roughly one quarter of
        # a city block in my neighborhood)
        move_by = 10 / (1 + (4 * (self.map_view.get_zoom_level() ** 3)))
        
        if   keyval == Gdk.keyval_from_name("Left"):  lon += move_by * -1
        elif keyval == Gdk.keyval_from_name("Up"):    lat += move_by
        elif keyval == Gdk.keyval_from_name("Right"): lon += move_by
        elif keyval == Gdk.keyval_from_name("Down"):  lat += move_by * -1
        
        if self.valid_coords(lat, lon):
            self.map_view.center_on(lat, lon)
    
    def create_polygon(self):
        """Prepare a new ChamplainPolygon for display on the map."""
        
        polygon = Champlain.Polygon()
        polygon.set_property('closed-path', False)
        polygon.set_property('mark-points', False)
        polygon.set_stroke(True)
        polygon.set_stroke_width(5)
        polygon.set_stroke_color(self.track_color)
        polygon.set_fill(False)
        self.map_view.add_polygon(polygon)
        polygon.show()
        return polygon
    
    def position_crosshair(self, stage=None):
        """Ensure that the crosshair is precisely in the center of the map."""
        
        self.crosshair.set_position(
            (self.stage.get_width()  - self.crosshair.get_width())  / 2,
            (self.stage.get_height() - self.crosshair.get_height()) / 2
        )
    
    def set_marker_highlight(self, photos, path, iter, (area, transparent)):
        """Set the highlightedness of the given photo's ChamplainMarker."""
        
        marker = photos.get_value(iter, self.PHOTO_MARKER)
        
        if marker is None:          return
        if not marker.get_parent(): return
        
        highlighted = area is not None
        
        if transparent: marker.set_property('opacity', 64)
        else:           marker.set_property('opacity', 255)
        
        marker.set_highlighted(highlighted)
        
        if highlighted:
            marker.set_scale(1.2, 1.2)
            marker.raise_top()
        else:
            marker.set_scale(1, 1)
            return
        
        lat = marker.get_property('latitude')
        lon = marker.get_property('longitude')
        
        # Keep track of (min, max) of (lat, lon) for use with ensure_visible()
        if lat < area[0]: area[0] = lat
        if lon < area[1]: area[1] = lon
        if lat > area[2]: area[2] = lat
        if lon > area[3]: area[3] = lon
    
    def update_all_marker_highlights(self, selection=None):
        """Ensure only the selected markers are highlighted."""
        
        if selection is None: selection = self.photo_selection
        
        # The first two values are minimums, and the second two are maximums.
        # 'float < ""' is always true, and 'float > None' is always true, so
        # these are sensible default values that get immediately clobbered
        # whenever compared against a real value.
        area = [ "", "", None, None, False ]
        
        if selection.count_selected_rows() > 0:
            self.loaded_photos.foreach(self.set_marker_highlight, (None, True))
            selection.selected_foreach(self.set_marker_highlight, (area, False))
            if (self.valid_coords(*area[0:2]) and 
                self.valid_coords(*area[2:4])):
                self.remember_location()
                self.map_view.ensure_visible(*area)
        else:
            self.loaded_photos.foreach(self.set_marker_highlight, (None, False))
    
    def add_marker(self, label, lat, lon):
        """Create a new ChamplainMarker and add it to the map."""
        
        marker = Champlain.Marker()
        marker.set_text(os.path.basename(label))
        marker.set_position(lat, lon)
        self.map_photo_layer.add_marker(marker)
        marker.show()
        marker.raise_top()
        return marker
    
    def remove_marker(self, photos, iter):
        """Remove any marker associated with the given photo from the map."""
        
        old_marker = photos.get_value(iter, self.PHOTO_MARKER)
        if old_marker: old_marker.destroy()
    
    def clear_all_gpx(self, widget=None):
        """Forget all GPX data, start over with a clean slate."""
        
        for polygon in self.polygons:
            polygon.hide()
            
            # Why doesn't this work? Why do these always cause segfaults?
            # Who are you? Where are my pants?
            #self.map_view.remove_polygon(polygon)
            #polygon.clear_points()
        
        self.polygons = []
        
        self.tracks = {}
        
        self.current = { 
            'count':   0.0, 
            # 'float < ""' is always true, and 'float > None' is always true,
            # so these make sensible default values that we can easily clobber
            'area':    [ "", "", None, None, False ], 
            'highest': None, 
            'lowest':  "" 
        }
        
        self.update_sensitivity()
    
################################################################################
# File data handling. These methods interact with files (loading, saving, etc)
################################################################################
    
    def save_one_file(self, photos, path, iter, (current, total)):
        """Save the specified file, if necessary."""
        
        filename = photos.get_value(iter, self.PHOTO_PATH)
        
        if filename not in self.modified: return
        
        current.append(path)
        
        altitude  = photos.get_value(iter, self.PHOTO_ALTITUDE)
        latitude  = photos.get_value(iter, self.PHOTO_LATITUDE)
        longitude = photos.get_value(iter, self.PHOTO_LONGITUDE)
        
        self._redraw_interface(len(current) / total, 
            _("Saving %s...") % os.path.basename(filename))
        
        exif = pyexiv2.Image(filename)
        exif.readMetadata()
        
        exif['Exif.GPSInfo.GPSMapDatum'] = 'WGS-84'
        
        exif['Exif.GPSInfo.GPSAltitudeRef'] = 0
        exif['Exif.GPSInfo.GPSAltitude'] = self.float_to_rational(altitude)
        
        (exif['Exif.GPSInfo.GPSLatitude'], exif['Exif.GPSInfo.GPSLatitudeRef']
            ) = self.decimal_to_dms(latitude, True)
        
        (exif['Exif.GPSInfo.GPSLongitude'], exif['Exif.GPSInfo.GPSLongitudeRef']
            ) = self.decimal_to_dms(longitude, False)
        
        try:
            exif.writeMetadata()
        except Exception as inst:
            self._status_message(", ".join(inst.args))
        else:
            del self.modified[filename]
            photos.set_value(
                iter, self.PHOTO_SUMMARY, 
                re.sub(
                    r'</?b>', '', 
                    photos.get_value(iter, self.PHOTO_SUMMARY)
                )
            )
    
    def save_all_files(self, widget=None):
        """Call self.save_one_file() once for each loaded file."""
        
        self.progressbar.show()
        
        self.loaded_photos.foreach(self.save_one_file, [[], len(self.modified)])
        
        self.update_sensitivity()
        self.progressbar.hide()
    
    def load_exif_from_file(self, filename, thumb_size=200):
        """Read photo metadata from disk using the pyexiv2 module."""
        
        try: 
            thumb = GdkPixbuf.Pixbuf.new_from_file_at_size(
                filename, 
                thumb_size, 
                thumb_size
            )
        except RuntimeError:
            # IOErrror is what I'm using to indicate "invalid filetype"
            # because that's what pyexiv2 raises for certain invalid files.
            # This means my program will refuse to open files that GdkPixbuf
            # can't create a thumbnail for, which might pose a problem in the 
            # event that there's some image format that is supported by
            # pyexiv2 but not GdkPixbuf. Works with JPG and DNG at least.
            raise IOError
        
        exif = pyexiv2.Image(filename)
        exif.readMetadata()
        
        try:
            timestamp = exif['Exif.Photo.DateTimeOriginal']
        except KeyError: 
            timestamp = None
        
        # pyexiv2 provides a string when it can't parse invalid data
        # So I just discard it here.
        if type(timestamp) == str:
            timestamp = None
        
        try:
            lat = self.dms_to_decimal(
                exif['Exif.GPSInfo.GPSLatitude'], 
                exif['Exif.GPSInfo.GPSLatitudeRef']
            )
            lon = self.dms_to_decimal(
                exif['Exif.GPSInfo.GPSLongitude'], 
                exif['Exif.GPSInfo.GPSLongitudeRef']
            )
        except KeyError:
            lat = lon = None
        
        try:
            ele = exif['Exif.GPSInfo.GPSAltitude']
            ele = ele.numerator / ele.denominator
        except:
            ele = None
        
        return timestamp, lat, lon, ele, thumb
    
    def gpx_element_start(self, name, attributes):
        """Callback function for Expat StartElementHandler."""
        
        # If the root element is not GPX, don't even bother with it, just
        # barf right away and get it over with.
        if 'element-name' not in self.current and name <> 'gpx':
            raise expat.ExpatError
        
        # This is how the data handler knows what element it's in
        self.current['element-name'] = name
        
        # give us a blank string to append to from the data handler
        self.current[name] = ""
        
        # New track segment, create a new polygon for it
        if name == "trkseg":
            self.polygons.append(self.create_polygon())
        
        # Eg, <trkpt lat="45.147445" lon="-81.469507">
        if 'lat' in attributes:
            self.current.update(attributes)
    
    def gpx_element_data(self, data):
        """Callback function for Expat CharacterDataHandler."""
        
        data = data.strip()
        if not data: return
        
        # This is where we collect elevation and time data
        # Sometimes expat calls this handler multiple times each with just
        # a chunk of the whole data, so += is necessary to collect all of it.
        self.current[self.current['element-name']] += data
    
    def gpx_element_end(self, name):
        """Callback function for Expat EndElementHandler."""
        
        # We only care about the trkpt element closing, because that means
        # there is a new, fully-loaded GPX point to play with.
        if name <> "trkpt": return
        
        self.current['count'] += 1.0
        
        # GPX is only UTC, as far as I'm aware
        timestamp = calendar.timegm(
            time.strptime(self.current['time'], '%Y-%m-%dT%H:%M:%SZ')
        )
        
        lat = float(self.current['lat'])
        lon = float(self.current['lon'])
        
        if not self.valid_coords(lat, lon): return
        
        self.tracks[timestamp] = {
            'elevation': float(self.current['ele']),
            'point':     self.polygons[-1].append_point(lat, lon)
        }
        
        if timestamp > self.current['highest']: 
            self.current['highest'] = timestamp
        if timestamp < self.current['lowest']: 
            self.current['lowest'] = timestamp
        
        if lat < self.current['area'][0]: self.current['area'][0] = lat
        if lon < self.current['area'][1]: self.current['area'][1] = lon
        if lat > self.current['area'][2]: self.current['area'][2] = lat
        if lon > self.current['area'][3]: self.current['area'][3] = lon
        
        # Refreshing the screen for every single track point seems to be
        # the slowest part of this whole operation, so I'm only going to do
        # it every 200th point.
        if self.current['count'] % 200 == 0:
            self.progressbar.pulse()
            self.map_view.ensure_visible(*self.current['area'])
            self._redraw_interface()
        
        # Clear all four coordinates of our four-dimensional location
        # so that it can't accidentally be re-used for the next point
        try:
            del self.current['lat']
            del self.current['lon']
            del self.current['ele']
            del self.current['time']
        except KeyError:
            pass
    
    def load_gpx_from_file(self, filename):
        """Parse GPX data, drawing each GPS track segment on the map."""
        
        self._redraw_interface(0, _("Parsing GPX data..."))
        
        self.remember_location()
        
        start_time = time.clock()
        
        gpx_parser = expat.ParserCreate()
        
        # Callback functions which do all of the parsing.
        gpx_parser.StartElementHandler = self.gpx_element_start
        gpx_parser.CharacterDataHandler = self.gpx_element_data
        gpx_parser.EndElementHandler = self.gpx_element_end
        
        with open(filename) as gpx:
            status = gpx_parser.ParseFile(gpx)
        
        self.update_sensitivity()
        
        self._status_message(
            _("%d points loaded in %.2fs.") % 
            (self.current['count'], time.clock()-start_time),
            False
        )
        
        if len(self.tracks) > 0:
            self.map_view.ensure_visible(*self.current['area'])
        
        self.loaded_photos.foreach(self.auto_timestamp_comparison, None)
        
        # Cleanup leftover data from parser
        self.current['count'] = 0.0
        for key in self.current.keys():
            if key not in [ 'count', 'area', 'highest', 'lowest' ]:
                del self.current[key]
    
################################################################################
# GtkListStore. These methods modify the liststore data in some way.
################################################################################
    
    def auto_timestamp_comparison(self, photos, path, iter, data=None):
        """Use GPX data to calculate photo coordinates and elevation."""
        
        # There must be at least two GPX points loaded for this to work
        if len(self.tracks) < 2: return
        
        # User has manually tagged a photo, we should respect that
        if photos.get_value(iter, self.PHOTO_PATH) in self.has_manual: return
        
        # photo is the timestamp in epoch seconds,
        photo = photos.get_value(iter, self.PHOTO_TIMESTAMP)
        photo += self.offset_hours.get_value() * 3600
        photo += self.offset_minutes.get_value() * 60
        photo += self.offset_seconds.get_value()
        
        # hi and lo begin by referring to the chronological first
        # and last timestamp created by the GPX device. We later
        # iterate over the list, searching for the two timestamps
        # that are nearest to the photo
        hi = self.current['highest']
        lo = self.current['lowest']
        
        # If the photo is out of range, simply peg it to the end of the range.
        # I think this makes sense. If it doesn't, the user isn't obligated to
        # save the result. They can always override with the 'apply' button, 
        # or load in a different GPX file with correct data.
        if photo < lo: photo = lo
        if photo > hi: photo = hi
        
        # Check for GPX point with exact timestamp as photo. This is more likely
        # than you might think. Three out of the six supplied demo images match
        # this criteria, which I didn't notice until *after* I selected them.
        try:
            lat = self.tracks[photo]['point'].lat
            lon = self.tracks[photo]['point'].lon
            ele = self.tracks[photo]['elevation']
        
        # Failing that, however, we have to find the two track points that
        # are nearest to the photo timestamp, and then proportionally calculate
        # the location in between. 
        except KeyError: 
            # Iterate over the available gpx points, find the two that are
            # nearest (in time) to the photo timestamp.
            for point in self.tracks:
                if (point > photo) and (point < hi): hi = point
                if (point < photo) and (point > lo): lo = point
            
            # delta is the number of seconds between 
            # the two points we're averaging
            delta = hi - lo
            
            # low_perc and high_perc are percentages (between 0 and 1)
            # representing the proportional amount of time from the 
            # lower point to the photo, and the higher point to the photo
            hi_perc = (photo - lo) / delta
            lo_perc = (hi - photo) / delta
            
            # Multiply the coordinates of the gpx points by the proportional
            # distance between the gpx point and the photo timestamp, and then
            # add the two proportions. This results in finding the correct
            # coordinates for the photo.
            lat = ((self.tracks[lo]['point'].lat * lo_perc)   + 
                   (self.tracks[hi]['point'].lat * hi_perc))
            lon = ((self.tracks[lo]['point'].lon * lo_perc)   + 
                   (self.tracks[hi]['point'].lon * hi_perc))
            ele = ((self.tracks[lo]['elevation'] * lo_perc)   +
                   (self.tracks[hi]['elevation'] * hi_perc))
        
        self._insert_coordinates(photos, iter, lat, lon, ele)
    
    def time_offset_value_changed(self, widget):
        """Update all photos each time the camera's clock is corrected."""
        
        # Some magic to let minutes and seconds settings wrap around.
        seconds = self.offset_seconds.get_value()
        minutes = self.offset_minutes.get_value()
        
        if seconds == -60 or seconds == 60:
            self.offset_seconds.set_value(0)
            self.offset_minutes.set_value(
                self.offset_minutes.get_value() + (seconds/60)
            )
        
        if minutes == -60 or minutes == 60:
            self.offset_minutes.set_value(0)
            self.offset_hours.set_value(
                self.offset_hours.get_value() + (minutes/60)
            )
        
        self.loaded_photos.foreach(self.auto_timestamp_comparison, None)
        self.update_all_marker_highlights()
    
    def apply_single_photo(self, photos, path, iter, data=None):
        """Manually apply map center coordinates to given photo."""
        
        self._insert_coordinates(photos, iter, 
            self.map_view.get_property('latitude'), 
            self.map_view.get_property('longitude')
        )
        
        self.has_manual[photos.get_value(iter, self.PHOTO_PATH)] = True
    
    # {apply,revert,close}_selected_photos are signal handlers that are called
    # in response to both keyboard shortcuts and button clicking. button will
    # be the ToolButton that invoked it, or None for a keyboard invocation.
    def apply_selected_photos(self, button=None):
        """Manually apply map center coordinates to all selected photos."""
        
        self.photo_selection.selected_foreach(self.apply_single_photo, None)
        self.update_sensitivity()
        self.update_all_marker_highlights()
    
    def revert_selected_photos(self, button=None):
        """Discard any modifications to all selected photos."""
        
        self.progressbar.show()
        
        self.photo_selection.selected_foreach(
            self.add_or_reload_photo, 
            [[], len(self.modified)]
        )
        
        self.progressbar.hide()
        
        self.update_sensitivity()
        self.update_all_marker_highlights()
    
    def close_selected_photos(self, button=None):
        """Discard all selected photos."""
        
        (pathlist, photos) = self.photo_selection.get_selected_rows()
        if pathlist == []: return
        
        pathlist.reverse()
        
        for path in pathlist:
            iter = photos.get_iter(path)[1]
            filename = photos.get_value(iter, self.PHOTO_PATH)
            if filename in self.modified:   del self.modified[filename]
            if filename in self.has_manual: del self.has_manual[filename]
            self.remove_marker(photos, iter)
            photos.remove(iter)
        
        self.update_sensitivity()
    
    def _insert_coordinates(self, photos, iter, lat=None, lon=None, ele=None, modified=True):
        """Create map marker and assign 3D coordinates to specified photo."""
        
        self.remove_marker(photos, iter)
        
        filename = photos.get_value(iter, self.PHOTO_PATH)
        timestamp = photos.get_value(iter, self.PHOTO_TIMESTAMP)
        
        if modified: self.modified[filename] = True
        
        if ele:
            photos.set_value(iter, self.PHOTO_ALTITUDE,  ele)
        
        if self.valid_coords(lat, lon):
            photos.set_value(iter, self.PHOTO_LATITUDE,  lat)
            photos.set_value(iter, self.PHOTO_LONGITUDE, lon)
            photos.set_value(iter, self.PHOTO_SUMMARY,
                self._create_summary(filename, timestamp, lat, lon, ele, modified))
            photos.set_value(iter, self.PHOTO_MARKER,
                self.add_marker(filename, lat, lon))
    
    def _find_existing_photo(self, photos, path, iter, (loaded, filename)):
        """Determine if a photo has already been loaded or not."""
        
        if filename == photos.get_value(iter, self.PHOTO_PATH):
            loaded.append(iter.copy())
            return True
    
    def add_or_reload_photo(self, photos=None, path=None, iter=None, data=None, filename=None):
        """Create or update a row in the ListStore.
        
        Checks if the file has already been loaded, and if not, creates a new
        row in the ListStore. Either way, it then populates that row with
        photo metadata as read from disk. Effectively, this is used both for 
        loading new photos, and reverting old photos, discarding any changes.
        
        Must be passed either an iter or filename, or both. Raises IOError if 
        filename refers to a file that is not a photograph.
        """
        
        if iter is None and filename is None: return
        
        if photos is None:   photos   = self.loaded_photos
        if filename is None: filename = photos.get_value(iter, self.PHOTO_PATH)
        
        (timestamp, lat, lon, ele, thumb
            ) = self.load_exif_from_file(filename, 200)
        
        # Update the progressbar
        (current, total) = data
        current.append(filename)
        self._redraw_interface(
            len(current) / total,
            _("Loading %s...") % os.path.basename(filename)
        )
        
        if timestamp:
            # This code requires the computer's timezone to be set to the same 
            # timezone as your camera. TODO add an option for the user
            # to override the system timezone.
            timestamp = int(time.mktime(timestamp.timetuple()))
        else:
            # This number won't be especially useful, but more useful
            # than absolutely nothing.
            timestamp = int(os.stat(filename).st_mtime)
        
        # Make sure we're not loading a file that's already loaded.
        if iter is None:
            files = []
            photos.foreach(self._find_existing_photo, [files, filename])
            
            # The user is loading a NEW file! Yay!
            if files == []: 
                iter = photos.append([None] * photos.get_n_columns())
            
            # The user is trying to open a file that already was loaded
            # so reload the file into the already-existing iter
            else: 
                iter = files[0]
        
        photos.set_value(iter, self.PHOTO_PATH,      filename)
        photos.set_value(iter, self.PHOTO_THUMB,     thumb)
        photos.set_value(iter, self.PHOTO_TIMESTAMP, timestamp)
        photos.set_value(iter, self.PHOTO_SUMMARY, 
            self._create_summary(filename, timestamp, lat, lon, ele))
        
        self._insert_coordinates(photos, iter, lat, lon, ele, False)
        
        if filename in self.modified:   del self.modified[filename]
        if filename in self.has_manual: del self.has_manual[filename]
        
        self.auto_timestamp_comparison(photos, None, iter)
        self.update_sensitivity()
    
################################################################################
# Dialogs. Various dialog-related methods for user interaction.
################################################################################
    
    def update_preview(self, chooser):
        """Display photo thumbnail and geotag data in file chooser."""
        
        filename = chooser.get_preview_filename()
        
        if not os.path.isfile(str(filename)): 
            chooser.set_preview_widget_active(False)
            return
        
        try:
            (timestamp, lat, lon, ele, thumb
                ) = self.load_exif_from_file(filename, 400)
        except IOError:
            chooser.set_preview_widget_active(False)
            return
        
        image = Gtk.Image()
        image.set_from_pixbuf(thumb)
        
        label = self._pretty_time(timestamp)
        
        if self.valid_coords(lat, lon): 
            label = "%s\n%s" % (label, self._pretty_coords(lat, lon))
        else:
            label = "%s\n%s" % (label, _("Not geotagged"))
        
        if ele: label = "%s\n%.1f%s" % (label, ele, _("m above sea level"))
        
        # Is this a label? This should be a label.
        label = Gtk.Label(label=label)
        
        label.set_justify(Gtk.Justification.CENTER)
        
        preview_widget = Gtk.VBox(spacing=6)
        preview_widget.pack_start(image, False, False, 0)
        preview_widget.pack_start(label, False, False, 0)
        preview_widget.show_all()
        
        chooser.set_preview_widget(preview_widget)
        chooser.set_preview_widget_active(True)
    
    # TODO Need to be able to load files with drag & drop, not just this thing
    def add_files_dialog(self, widget=None, data=None):
        """Display a file chooser, and attempt to load chosen files."""
        
        chooser = Gtk.FileChooserDialog(
            title=_("Open files..."),
            buttons=(
                Gtk.STOCK_CANCEL,  Gtk.ResponseType.CANCEL, 
                Gtk.STOCK_OPEN,    Gtk.ResponseType.OK
            )
        )
        chooser.set_action(Gtk.FileChooserAction.OPEN)
        chooser.set_default_response(Gtk.ResponseType.OK)
        chooser.set_select_multiple(True)
        
        # make a file preview thingo
        chooser.connect("selection-changed", self.update_preview)
        
        # Exit if the user clicked anything other than "OK"
        if chooser.run() <> Gtk.ResponseType.OK:
            chooser.destroy()
            return
        
        self.progressbar.show()
        
        # Make the chooser disappear immediately after clicking a button,
        # anything else feels unresponsive
        files = chooser.get_filenames()
        chooser.destroy()
        
        # This is used to count loaded files
        loaded_files = []
        
        invalid_files = []
        
        # Iterate over files and attempt to load them.
        for filename in files:
            # Assume the file is an image; if that fails, assume it's GPX; 
            # if that fails, show an error
            try:
                try:
                    self.add_or_reload_photo(
                        filename=filename, 
                        data=[loaded_files, len(files)]
                    )
                except IOError: 
                    self.load_gpx_from_file(filename)
            except expat.ExpatError:
                invalid_files.append(os.path.basename(filename))
                self._status_message(_("Could not open: %s") % 
                    ", ".join(invalid_files))
        
        self.progressbar.hide()
        self.update_sensitivity()
    
    def confirm_quit_dialog(self, widget=None, event=None):
        """Teardown method, inform user of unsaved files, if any."""
        
        # Remember the last viewed location so we can return to it next run
        self.gconf_client.set_float(self.gconf_keys['lat'], 
            self.map_view.get_property('latitude')) 
        self.gconf_client.set_float(self.gconf_keys['lon'], 
            self.map_view.get_property('longitude'))
        self.gconf_client.set_int(self.gconf_keys['zoom'], 
            self.map_view.get_zoom_level())
        
        # If there's no unsaved data, just close without confirmation.
        if len(self.modified) == 0: Gtk.main_quit(); return True
        
        dialog = Gtk.MessageDialog(
            parent=self.window, 
            flags=Gtk.DialogFlags.MODAL,
            title=" "            
        )
        dialog.set_property('message-type', Gtk.MessageType.WARNING)
        dialog.set_markup(SAVE_WARNING % len(self.modified))
        dialog.add_button(_("Close _without Saving"), Gtk.ResponseType.CLOSE)
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dialog.add_button(Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        
        # If we don't dialog.destroy() here, and the user chooses to save files, 
        # the dialog stays open during the save, which looks very unresponsive 
        # and makes the application feel sluggish.
        response = dialog.run()
        dialog.destroy()
        self._redraw_interface()
        
        # Save and/or quit as necessary
        if response == Gtk.ResponseType.ACCEPT: self.save_all_files()
        if response <> Gtk.ResponseType.CANCEL: Gtk.main_quit()
        
        # Prevents GTK from trying to call a non-existant destroy method
        return True 
    
    # TODO needs logo
    def about_dialog(self, widget=None, data=None):
        """Describe this application to the user."""
        
        dialog = Gtk.AboutDialog()
        dialog.set_program_name("GottenGeography")
        dialog.set_name("GottenGeography")
        dialog.set_version(VERSION)
        dialog.set_copyright("(c) Robert Park, 2010")
        dialog.set_license(LICENSE)
        dialog.set_comments(COMMENTS)
        dialog.set_website("http://github.com/robru/GottenGeography/wiki")
        dialog.set_website_label("GottenGeography Wiki")
        dialog.set_authors(["Robert Park <rbpark@exolucere.ca>"])
        dialog.set_documenters(["Robert Park <rbpark@exolucere.ca>"])
        #dialog.set_artists(["Robert Park <rbpark@exolucere.ca>"])
        #dialog.set_translator_credits("Nobody!")
        dialog.run()
        dialog.destroy()
    
################################################################################
# Initialization and Gtk boilerplate/housekeeping type stuff and such.
################################################################################
    
    def __init__(self):
        """Initialize all necessary state."""
        
        # Keeps track of which files have been modified, mostly for counting
        # purposes. Keys are absolute paths to files, values are True.
        self.modified = {}
        
        # Keeps track of which files have manually-applied tags, so that the
        # auto-tagger doesn't discard the users hard work.
        self.has_manual = {}
        
        # Stores a list of locations that the user was viewing immediately
        # prior to any point at which the view was changed programmatically.
        # Allows the user to go "back", eg, after GPX load has changed the view.
        self.history = []
        
        # GConf is used to store the last viewed location
        self.gconf_client = GConf.Client.get_default()
        self.gconf_keys = { 
            'lat':  '/apps/gottengeography/last_latitude',
            'lon':  '/apps/gottengeography/last_longitude',
            'zoom': '/apps/gottengeography/last_zoom_level'
        }
        
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_title("GottenGeography")
        self.window.set_size_request(900,700)
        
        self.app_container = Gtk.VBox(spacing=0)
        
        # Create the toolbar with standard buttons and some tooltips
        self.toolbar = Gtk.Toolbar()
        self.open_button = Gtk.ToolButton(stock_id=Gtk.STOCK_OPEN)
        self.open_button.set_tooltip_text(
            _("Load photos or GPS data (Ctrl+O)"))
        
        self.save_button = Gtk.ToolButton(stock_id=Gtk.STOCK_SAVE)
        self.save_button.set_tooltip_text(
            _("Save all modified GPS data into your photos (Ctrl+S)"))
        self.save_button.set_label(_("Save All"))
        
        self.toolbar_first_spacer = Gtk.SeparatorToolItem()
        
        self.clear_gpx_button = Gtk.ToolButton(stock_id=Gtk.STOCK_CLEAR) 
        self.clear_gpx_button.set_tooltip_text(
            _("Unload all GPS data (Ctrl+X)"))
        self.clear_gpx_button.set_label(_("Clear GPX"))
        
        self.close_button = Gtk.ToolButton(stock_id=Gtk.STOCK_CLOSE) 
        self.close_button.set_tooltip_text(
            _("Close selected photos (Ctrl+W)"))
        self.close_button.set_label(_("Close Photo"))
        
        self.toolbar_second_spacer = Gtk.SeparatorToolItem()
        
        self.revert_button = Gtk.ToolButton(stock_id=Gtk.STOCK_REVERT_TO_SAVED)
        self.revert_button.set_tooltip_text(
            _("Reload selected photos, losing all changes (Ctrl+Z)"))
        
        self.toolbar_third_spacer = Gtk.SeparatorToolItem()
        self.toolbar_third_spacer.set_expand(True)
        self.toolbar_third_spacer.set_draw(False)
        
        self.zoom_out_button = Gtk.ToolButton(stock_id=Gtk.STOCK_ZOOM_OUT)
        self.zoom_out_button.set_tooltip_text(
            _("Zoom the map out one step."))
        
        self.zoom_in_button = Gtk.ToolButton(stock_id=Gtk.STOCK_ZOOM_IN)
        self.zoom_in_button.set_tooltip_text(
            _("Enhance!"))
        
        self.toolbar_fourth_spacer = Gtk.SeparatorToolItem()
        
        self.back_button = Gtk.ToolButton(stock_id=Gtk.STOCK_GO_BACK)
        self.back_button.set_tooltip_text(
            _("Return to previous location in map view."))
        
        self.toolbar_fifth_spacer = Gtk.SeparatorToolItem()
        
        self.about_button = Gtk.ToolButton(stock_id=Gtk.STOCK_ABOUT)
        
        self.photos_and_map_container = Gtk.HPaned()
        
        # This code defines how the photo list will appear
        self.loaded_photos = Gtk.ListStore(
            GObject.TYPE_STRING,  # 0 Path to image file
            GObject.TYPE_STRING,  # 1 "Nice" name for display purposes
            GdkPixbuf.Pixbuf,     # 2 Thumbnail
            GObject.TYPE_INT,     # 3 Timestamp in Epoch seconds
            GObject.TYPE_DOUBLE,  # 4 Latitude
            GObject.TYPE_DOUBLE,  # 5 Longitude
            GObject.TYPE_DOUBLE,  # 6 Altitude
            GObject.TYPE_OBJECT   # 7 ChamplainMarker representing photo on map
        )
        
        # These constants will make referencing the above columns much easier
        (self.PHOTO_PATH, self.PHOTO_SUMMARY, self.PHOTO_THUMB, 
        self.PHOTO_TIMESTAMP, self.PHOTO_LATITUDE, self.PHOTO_LONGITUDE, 
        self.PHOTO_ALTITUDE, self.PHOTO_MARKER
        ) = range(self.loaded_photos.get_n_columns())
        
        self.loaded_photos.set_sort_column_id(
            self.PHOTO_TIMESTAMP, 
            Gtk.SortType.ASCENDING
        )
        
        self.photos_view = Gtk.TreeView(model=self.loaded_photos)
        self.photos_view.set_enable_search(False)
        self.photos_view.set_reorderable(False)
        self.photos_view.set_headers_visible(False)
        self.photos_view.set_rubber_banding(True)
        
        self.photo_selection = self.photos_view.get_selection()
        self.photo_selection.set_mode(Gtk.SelectionMode.MULTIPLE)
        
        self.cell_string = Gtk.CellRendererText()
        self.cell_thumb = Gtk.CellRendererPixbuf()
        self.cell_thumb.set_property('stock-id', Gtk.STOCK_MISSING_IMAGE)
        self.cell_thumb.set_property('ypad', 6)
        self.cell_thumb.set_property('xpad', 6)
        
        self.column = Gtk.TreeViewColumn('Photos')
        self.column.pack_start(self.cell_thumb, False)
        self.column.add_attribute(self.cell_thumb, 'pixbuf', self.PHOTO_THUMB)
        self.column.pack_start(self.cell_string, False)
        self.column.add_attribute(self.cell_string, 'markup', self.PHOTO_SUMMARY)
        self.column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        self.photos_view.append_column(self.column)
        
        self.photo_scroller = Gtk.ScrolledWindow()
        self.photo_scroller.set_policy(
            Gtk.PolicyType.NEVER, 
            Gtk.PolicyType.AUTOMATIC
        )
        
        self.apply_button = Gtk.Button.new_from_stock(Gtk.STOCK_APPLY)
        self.apply_button.set_tooltip_text(
            _("Place selected photos onto center of map (Ctrl+Return)"))
        
        self.select_all_button = Gtk.ToggleButton(label=Gtk.STOCK_SELECT_ALL)
        self.select_all_button.set_use_stock(True)
        self.select_all_button.set_tooltip_text(
            _("Toggle whether all photos are selected (Ctrl+A)"))
        
        self.photo_button_bar = Gtk.HBox(spacing=12)
        self.photo_button_bar.pack_start(self.select_all_button, True, True, 0)
        self.photo_button_bar.pack_start(self.apply_button, True, True, 0)
        self.photo_button_bar.set_border_width(3)
        
        self.photos_with_buttons = Gtk.VBox()
        self.photos_with_buttons.pack_start(self.photo_scroller, True, True, 0)
        self.photos_with_buttons.pack_start(self.photo_button_bar, False, False, 0)
        
        # Initialize all the clutter/champlain stuff
        Clutter.init([])
        self.champlain = GtkChamplain.Embed()
        self.map_view = self.champlain.get_view()
        self.map_view.set_property('show-scale', True)
        self.map_photo_layer = Champlain.Layer()
        self.map_view.add_layer(self.map_photo_layer)
        self.map_photo_layer.show()
        
        # color to use for GPX tracks
        self.track_color = Clutter.Color.new(255, 0, 0, 128)
        
        # Load last used location from GConf
        self.map_view.center_on(
            self.gconf_client.get_float(self.gconf_keys['lat']), 
            self.gconf_client.get_float(self.gconf_keys['lon'])
        ) 
        self.map_view.set_zoom_level(
            self.gconf_client.get_int(self.gconf_keys['zoom'])
        )
        
        self.stage = self.map_view.get_stage()
        
        self.crosshair = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(0, 0, 0, 128)
        )
        self.crosshair.set_property('has-border', False)
        self.crosshair.set_size(6, 6)
        self.crosshair.set_parent(self.stage)
        self.crosshair.set_rotation(
            Clutter.RotateAxis.Z_AXIS, 
            45, # Degrees
            self.crosshair.get_width()/2, 
            self.crosshair.get_height()/2, 
            0
        )
        self.crosshair.raise_top()
        self.position_crosshair()
        self.crosshair.show()
        
        self.progressbar = Gtk.ProgressBar()
        self.progressbar.set_size_request(550, -1)
        self.progressbar.set_pulse_step(0.02)
        
        self.offset_label = Gtk.Label(label=_("Clock Offset: "))
        self.offset_hours_label = Gtk.Label(label=_("h "))
        self.offset_minutes_label = Gtk.Label(label=_("m "))
        self.offset_seconds_label = Gtk.Label(label=_("s "))
        
        self.offset_hours   = self.create_spin_button(24)
        self.offset_minutes = self.create_spin_button(60)
        self.offset_seconds = self.create_spin_button(60)
        
        self.statusbar = Gtk.Statusbar()
        self.statusbar.pack_start(self.progressbar, True, True, 6)
        self.statusbar.pack_end(self.offset_seconds_label, False, False, 0)
        self.statusbar.pack_end(self.offset_seconds, False, False, 0)
        self.statusbar.pack_end(self.offset_minutes_label, False, False, 0)
        self.statusbar.pack_end(self.offset_minutes, False, False, 0)
        self.statusbar.pack_end(self.offset_hours_label, False, False, 0)
        self.statusbar.pack_end(self.offset_hours, False, False, 0)
        self.statusbar.pack_end(self.offset_label, False, False, 0)
        
        # This adds each widget into it's place in the window.
        self.photo_scroller.add(self.photos_view)
        self.photos_and_map_container.add(self.photos_with_buttons)
        self.photos_and_map_container.add(self.champlain)
        self.toolbar.add(self.open_button)
        self.toolbar.add(self.save_button)
        self.toolbar.add(self.toolbar_first_spacer)
        self.toolbar.add(self.clear_gpx_button)
        self.toolbar.add(self.close_button)
        self.toolbar.add(self.toolbar_second_spacer)
        self.toolbar.add(self.revert_button)
        self.toolbar.add(self.toolbar_third_spacer)
        self.toolbar.add(self.zoom_out_button)
        self.toolbar.add(self.zoom_in_button)
        self.toolbar.add(self.toolbar_fourth_spacer)
        self.toolbar.add(self.back_button)
        self.toolbar.add(self.toolbar_fifth_spacer)
        self.toolbar.add(self.about_button)
        self.app_container.pack_start(self.toolbar, False, True, 0)
        self.app_container.pack_start(self.photos_and_map_container, True, True, 0)
        self.app_container.pack_end(self.statusbar, False, True, 0)
        self.window.add(self.app_container)
        
        # Connect all my precious signal handlers
        self.window.connect("delete_event", self.confirm_quit_dialog)
        self.open_button.connect("clicked", self.add_files_dialog)
        self.save_button.connect("clicked", self.save_all_files)
        self.apply_button.connect("clicked", self.apply_selected_photos)
        self.revert_button.connect("clicked", self.revert_selected_photos)
        self.close_button.connect("clicked", self.close_selected_photos)
        self.clear_gpx_button.connect("clicked", self.clear_all_gpx)
        self.zoom_out_button.connect("clicked", self.zoom_out)
        self.zoom_in_button.connect("clicked", self.zoom_in)
        self.back_button.connect("clicked", self.return_to_last)
        self.about_button.connect("clicked", self.about_dialog)
        self.select_all_button.connect("released", self.toggle_selected_photos)
        self.photo_selection.connect("changed", self.update_sensitivity)
        self.photo_selection.connect("changed", self.update_all_marker_highlights)
        self.offset_seconds.connect("value-changed", self.time_offset_value_changed)
        self.offset_minutes.connect("value-changed", self.time_offset_value_changed)
        self.offset_hours.connect("value-changed", self.time_offset_value_changed)
        self.stage.connect("paint", self.position_crosshair)
        
        # Key bindings
        self.accel = Gtk.AccelGroup()
        self.window.add_accel_group(self.accel)
        for key in [ 'q', 'w', 'x', 'o', 's', 'z', 'Return', 'slash', 
        'question', 'equal', 'minus', 'Left' ]: 
            self.accel.connect(
                Gdk.keyval_from_name(key), 
                Gdk.ModifierType.CONTROL_MASK, 
                0, 
                self.key_accel
            )
        
        for key in [ 'Left', 'Right', 'Up', 'Down' ]:
            self.accel.connect(
                Gdk.keyval_from_name(key), 
                Gdk.ModifierType.MOD1_MASK, 
                0, 
                self.move_map_view_by_arrow_keys
            )
        
        # Ensure all widgets are displayed properly
        self.window.show_all()
        self.progressbar.hide()
        
        # Various bits of state for the GPX parser
        self.polygons = []
        self.clear_all_gpx()
    
    def create_spin_button(self, value):
        """Create a SpinButton for use as a clock offset setting."""
        
        button = Gtk.SpinButton()
        button.set_digits(0)
        button.set_value(0)
        button.set_increments(1, 4)
        button.set_range(-1*value, value)
        button.set_update_policy(Gtk.SpinButtonUpdatePolicy.IF_VALID)
        button.set_numeric(True)
        button.set_snap_to_ticks(True)
        button.set_tooltip_text(
            _("Is the clock on your camera wrong? Correct it here."))
        
        return button
    
    def toggle_selected_photos(self, button):
        """Toggle the selection of photos."""
        
        if button.get_active():
            self.photo_selection.select_all()
        else:
            self.photo_selection.unselect_all()
    
    # TODO make sure these key choices actually make sense 
    # and are consistent with other apps
    def key_accel(self, accel_group, acceleratable, keyval, modifier):
        """Respond to keyboard shortcuts as typed by user."""
        
        # It would make more sense to store Gdk.keyval_name(keyval) in a
        # variable and compare that rather than calling Gdk.keyval_from_name() 
        # a million times, but that seems to just crash and this way actually
        # works, so it looks like this is what we're going with. 
        # Update 2010-10-29: J5 says he's just fixed this in Gtk3. Maybe one day
        # I'll get to use it!
        if   keyval == Gdk.keyval_from_name("Return"): self.apply_selected_photos()
        elif keyval == Gdk.keyval_from_name("w"):      self.close_selected_photos()
        elif keyval == Gdk.keyval_from_name("equal"):  self.zoom_in()
        elif keyval == Gdk.keyval_from_name("minus"):  self.zoom_out()
        elif keyval == Gdk.keyval_from_name("Left"):   self.return_to_last()
        elif keyval == Gdk.keyval_from_name("x"):      self.clear_all_gpx()
        elif keyval == Gdk.keyval_from_name("o"):      self.add_files_dialog()
        elif keyval == Gdk.keyval_from_name("q"):      self.confirm_quit_dialog()
        elif keyval == Gdk.keyval_from_name("/"):      self.about_dialog()
        elif keyval == Gdk.keyval_from_name("?"):      self.about_dialog()
        
        # Prevent the following keybindings from executing if there are no unsaved files
        if len(self.modified) == 0: return
        
        if   keyval == Gdk.keyval_from_name("s"):      self.save_all_files()
        elif keyval == Gdk.keyval_from_name("z"):      self.revert_selected_photos()
    
    def _status_message(self, message, error=True):
        """Display a message on the GtkStatusBar."""
        
        if error: context_id = "error"
        else:     context_id = "message"
        
        self.statusbar.push(self.statusbar.get_context_id(context_id), message)
    
    def _redraw_interface(self, fraction=None, text=None):
        """Tell Gtk to redraw the user interface, so it doesn't look hung.
        
        Primarily used to update the progressbar, but also for disappearing
        some dialogs while things are processing in the background. Won't 
        modify the progressbar if called with no arguments.
        """
        
        if fraction is not None: self.progressbar.set_fraction(fraction)
        if text is not None:     self.progressbar.set_text(str(text))
        while Gtk.events_pending(): Gtk.main_iteration()
    
    def _append_if_modified(self, photos, path, iter, pathlist):
        """Append the given photo to the pathlist if it's been modified."""
        
        if photos.get_value(iter, self.PHOTO_PATH) in self.modified: 
            pathlist.append(path)
            return True
    
    def update_sensitivity(self, selection=None):
        """Ensure all widgets are sensitive only when they need to be.
        
        This method should be called every time any program state changes,
        eg, when modifying a photo in any way, and when the selection changes.
        """
        
        if selection is None: selection = self.photo_selection
        sensitivity = selection.count_selected_rows() > 0
        
        # Apply and Close buttons get activated if any photo is selected
        self.apply_button.set_sensitive(sensitivity)
        self.close_button.set_sensitive(sensitivity)
        
        # Select button needs to show as toggled if there is any selection
        self.select_all_button.set_property('active', sensitivity)
        
        # Revert button is only activated if the selection has unsaved files.
        modified_in_selection = []
        self.photo_selection.selected_foreach(
            self._append_if_modified, 
            modified_in_selection
        )
        self.revert_button.set_sensitive(len(modified_in_selection) > 0)
        
        # Save button is only activated if there are modified files.
        self.save_button.set_sensitive(len(self.modified) > 0)
        
        # Clear button and time fudge are only sensitive if there's any GPX.
        gpx_sensitive = len(self.tracks) > 0
        for widget in [self.clear_gpx_button, self.offset_hours, 
        self.offset_minutes, self.offset_seconds, self.offset_hours_label, 
        self.offset_minutes_label, self.offset_seconds_label, 
        self.offset_label]:
            widget.set_sensitive(gpx_sensitive)
        
        # Zoom buttons should not be able to zoom beyond their ability
        zoom_level = self.map_view.get_zoom_level()
        self.zoom_in_button.set_sensitive(
            self.map_view.get_max_zoom_level() is not zoom_level)
        self.zoom_out_button.set_sensitive(
            self.map_view.get_min_zoom_level() is not zoom_level)
        
        # Back button should not be sensitive if there's no history yet.
        self.back_button.set_sensitive(len(self.history) > 0)
        
        # GtkListStore needs to be hidden if it is empty.
        if self.loaded_photos.get_iter_first()[0]: self.photos_with_buttons.show()
        else:                                      self.photos_with_buttons.hide()
    
    def main(self):
        """Go!"""
        
        Gtk.main()

################################################################################
# Strings section. Various strings that were too obnoxiously large to fit
# nicely into the actual code above, so they've been extracted here.
################################################################################

SAVE_WARNING = """<span weight="bold" size="larger">""" + _("""Save changes to \
your photos before closing?""") + """</span>

""" + _("""The changes you've made to %d of your photos will be permanently \
lost if you do not save.""")

COMMENTS = _("""GottenGeography is written in the Python programming language, \
and allows you to geotag your photos. The name is an anagram of "Python \
Geotagger".""")

LICENSE = """
                    GNU GENERAL PUBLIC LICENSE
                       Version 3, 29 June 2007

 Copyright (C) 2007 Free Software Foundation, Inc. <http://fsf.org/>
 Everyone is permitted to copy and distribute verbatim copies
 of this license document, but changing it is not allowed.

                            Preamble

  The GNU General Public License is a free, copyleft license for
software and other kinds of works.

  The licenses for most software and other practical works are designed
to take away your freedom to share and change the works.  By contrast,
the GNU General Public License is intended to guarantee your freedom to
share and change all versions of a program--to make sure it remains free
software for all its users.  We, the Free Software Foundation, use the
GNU General Public License for most of our software; it applies also to
any other work released this way by its authors.  You can apply it to
your programs, too.

  When we speak of free software, we are referring to freedom, not
price.  Our General Public Licenses are designed to make sure that you
have the freedom to distribute copies of free software (and charge for
them if you wish), that you receive source code or can get it if you
want it, that you can change the software or use pieces of it in new
free programs, and that you know you can do these things.

  To protect your rights, we need to prevent others from denying you
these rights or asking you to surrender the rights.  Therefore, you have
certain responsibilities if you distribute copies of the software, or if
you modify it: responsibilities to respect the freedom of others.

  For example, if you distribute copies of such a program, whether
gratis or for a fee, you must pass on to the recipients the same
freedoms that you received.  You must make sure that they, too, receive
or can get the source code.  And you must show them these terms so they
know their rights.

  Developers that use the GNU GPL protect your rights with two steps:
(1) assert copyright on the software, and (2) offer you this License
giving you legal permission to copy, distribute and/or modify it.

  For the developers' and authors' protection, the GPL clearly explains
that there is no warranty for this free software.  For both users' and
authors' sake, the GPL requires that modified versions be marked as
changed, so that their problems will not be attributed erroneously to
authors of previous versions.

  Some devices are designed to deny users access to install or run
modified versions of the software inside them, although the manufacturer
can do so.  This is fundamentally incompatible with the aim of
protecting users' freedom to change the software.  The systematic
pattern of such abuse occurs in the area of products for individuals to
use, which is precisely where it is most unacceptable.  Therefore, we
have designed this version of the GPL to prohibit the practice for those
products.  If such problems arise substantially in other domains, we
stand ready to extend this provision to those domains in future versions
of the GPL, as needed to protect the freedom of users.

  Finally, every program is threatened constantly by software patents.
States should not allow patents to restrict development and use of
software on general-purpose computers, but in those that do, we wish to
avoid the special danger that patents applied to a free program could
make it effectively proprietary.  To prevent this, the GPL assures that
patents cannot be used to render the program non-free.

  The precise terms and conditions for copying, distribution and
modification follow.

                       TERMS AND CONDITIONS

  0. Definitions.

  "This License" refers to version 3 of the GNU General Public License.

  "Copyright" also means copyright-like laws that apply to other kinds of
works, such as semiconductor masks.

  "The Program" refers to any copyrightable work licensed under this
License.  Each licensee is addressed as "you".  "Licensees" and
"recipients" may be individuals or organizations.

  To "modify" a work means to copy from or adapt all or part of the work
in a fashion requiring copyright permission, other than the making of an
exact copy.  The resulting work is called a "modified version" of the
earlier work or a work "based on" the earlier work.

  A "covered work" means either the unmodified Program or a work based
on the Program.

  To "propagate" a work means to do anything with it that, without
permission, would make you directly or secondarily liable for
infringement under applicable copyright law, except executing it on a
computer or modifying a private copy.  Propagation includes copying,
distribution (with or without modification), making available to the
public, and in some countries other activities as well.

  To "convey" a work means any kind of propagation that enables other
parties to make or receive copies.  Mere interaction with a user through
a computer network, with no transfer of a copy, is not conveying.

  An interactive user interface displays "Appropriate Legal Notices"
to the extent that it includes a convenient and prominently visible
feature that (1) displays an appropriate copyright notice, and (2)
tells the user that there is no warranty for the work (except to the
extent that warranties are provided), that licensees may convey the
work under this License, and how to view a copy of this License.  If
the interface presents a list of user commands or options, such as a
menu, a prominent item in the list meets this criterion.

  1. Source Code.

  The "source code" for a work means the preferred form of the work
for making modifications to it.  "Object code" means any non-source
form of a work.

  A "Standard Interface" means an interface that either is an official
standard defined by a recognized standards body, or, in the case of
interfaces specified for a particular programming language, one that
is widely used among developers working in that language.

  The "System Libraries" of an executable work include anything, other
than the work as a whole, that (a) is included in the normal form of
packaging a Major Component, but which is not part of that Major
Component, and (b) serves only to enable use of the work with that
Major Component, or to implement a Standard Interface for which an
implementation is available to the public in source code form.  A
"Major Component", in this context, means a major essential component
(kernel, window system, and so on) of the specific operating system
(if any) on which the executable work runs, or a compiler used to
produce the work, or an object code interpreter used to run it.

  The "Corresponding Source" for a work in object code form means all
the source code needed to generate, install, and (for an executable
work) run the object code and to modify the work, including scripts to
control those activities.  However, it does not include the work's
System Libraries, or general-purpose tools or generally available free
programs which are used unmodified in performing those activities but
which are not part of the work.  For example, Corresponding Source
includes interface definition files associated with source files for
the work, and the source code for shared libraries and dynamically
linked subprograms that the work is specifically designed to require,
such as by intimate data communication or control flow between those
subprograms and other parts of the work.

  The Corresponding Source need not include anything that users
can regenerate automatically from other parts of the Corresponding
Source.

  The Corresponding Source for a work in source code form is that
same work.

  2. Basic Permissions.

  All rights granted under this License are granted for the term of
copyright on the Program, and are irrevocable provided the stated
conditions are met.  This License explicitly affirms your unlimited
permission to run the unmodified Program.  The output from running a
covered work is covered by this License only if the output, given its
content, constitutes a covered work.  This License acknowledges your
rights of fair use or other equivalent, as provided by copyright law.

  You may make, run and propagate covered works that you do not
convey, without conditions so long as your license otherwise remains
in force.  You may convey covered works to others for the sole purpose
of having them make modifications exclusively for you, or provide you
with facilities for running those works, provided that you comply with
the terms of this License in conveying all material for which you do
not control copyright.  Those thus making or running the covered works
for you must do so exclusively on your behalf, under your direction
and control, on terms that prohibit them from making any copies of
your copyrighted material outside their relationship with you.

  Conveying under any other circumstances is permitted solely under
the conditions stated below.  Sublicensing is not allowed; section 10
makes it unnecessary.

  3. Protecting Users' Legal Rights From Anti-Circumvention Law.

  No covered work shall be deemed part of an effective technological
measure under any applicable law fulfilling obligations under article
11 of the WIPO copyright treaty adopted on 20 December 1996, or
similar laws prohibiting or restricting circumvention of such
measures.

  When you convey a covered work, you waive any legal power to forbid
circumvention of technological measures to the extent such circumvention
is effected by exercising rights under this License with respect to
the covered work, and you disclaim any intention to limit operation or
modification of the work as a means of enforcing, against the work's
users, your or third parties' legal rights to forbid circumvention of
technological measures.

  4. Conveying Verbatim Copies.

  You may convey verbatim copies of the Program's source code as you
receive it, in any medium, provided that you conspicuously and
appropriately publish on each copy an appropriate copyright notice;
keep intact all notices stating that this License and any
non-permissive terms added in accord with section 7 apply to the code;
keep intact all notices of the absence of any warranty; and give all
recipients a copy of this License along with the Program.

  You may charge any price or no price for each copy that you convey,
and you may offer support or warranty protection for a fee.

  5. Conveying Modified Source Versions.

  You may convey a work based on the Program, or the modifications to
produce it from the Program, in the form of source code under the
terms of section 4, provided that you also meet all of these conditions:

    a) The work must carry prominent notices stating that you modified
    it, and giving a relevant date.

    b) The work must carry prominent notices stating that it is
    released under this License and any conditions added under section
    7.  This requirement modifies the requirement in section 4 to
    "keep intact all notices".

    c) You must license the entire work, as a whole, under this
    License to anyone who comes into possession of a copy.  This
    License will therefore apply, along with any applicable section 7
    additional terms, to the whole of the work, and all its parts,
    regardless of how they are packaged.  This License gives no
    permission to license the work in any other way, but it does not
    invalidate such permission if you have separately received it.

    d) If the work has interactive user interfaces, each must display
    Appropriate Legal Notices; however, if the Program has interactive
    interfaces that do not display Appropriate Legal Notices, your
    work need not make them do so.

  A compilation of a covered work with other separate and independent
works, which are not by their nature extensions of the covered work,
and which are not combined with it such as to form a larger program,
in or on a volume of a storage or distribution medium, is called an
"aggregate" if the compilation and its resulting copyright are not
used to limit the access or legal rights of the compilation's users
beyond what the individual works permit.  Inclusion of a covered work
in an aggregate does not cause this License to apply to the other
parts of the aggregate.

  6. Conveying Non-Source Forms.

  You may convey a covered work in object code form under the terms
of sections 4 and 5, provided that you also convey the
machine-readable Corresponding Source under the terms of this License,
in one of these ways:

    a) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by the
    Corresponding Source fixed on a durable physical medium
    customarily used for software interchange.

    b) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by a
    written offer, valid for at least three years and valid for as
    long as you offer spare parts or customer support for that product
    model, to give anyone who possesses the object code either (1) a
    copy of the Corresponding Source for all the software in the
    product that is covered by this License, on a durable physical
    medium customarily used for software interchange, for a price no
    more than your reasonable cost of physically performing this
    conveying of source, or (2) access to copy the
    Corresponding Source from a network server at no charge.

    c) Convey individual copies of the object code with a copy of the
    written offer to provide the Corresponding Source.  This
    alternative is allowed only occasionally and noncommercially, and
    only if you received the object code with such an offer, in accord
    with subsection 6b.

    d) Convey the object code by offering access from a designated
    place (gratis or for a charge), and offer equivalent access to the
    Corresponding Source in the same way through the same place at no
    further charge.  You need not require recipients to copy the
    Corresponding Source along with the object code.  If the place to
    copy the object code is a network server, the Corresponding Source
    may be on a different server (operated by you or a third party)
    that supports equivalent copying facilities, provided you maintain
    clear directions next to the object code saying where to find the
    Corresponding Source.  Regardless of what server hosts the
    Corresponding Source, you remain obligated to ensure that it is
    available for as long as needed to satisfy these requirements.

    e) Convey the object code using peer-to-peer transmission, provided
    you inform other peers where the object code and Corresponding
    Source of the work are being offered to the general public at no
    charge under subsection 6d.

  A separable portion of the object code, whose source code is excluded
from the Corresponding Source as a System Library, need not be
included in conveying the object code work.

  A "User Product" is either (1) a "consumer product", which means any
tangible personal property which is normally used for personal, family,
or household purposes, or (2) anything designed or sold for incorporation
into a dwelling.  In determining whether a product is a consumer product,
doubtful cases shall be resolved in favor of coverage.  For a particular
product received by a particular user, "normally used" refers to a
typical or common use of that class of product, regardless of the status
of the particular user or of the way in which the particular user
actually uses, or expects or is expected to use, the product.  A product
is a consumer product regardless of whether the product has substantial
commercial, industrial or non-consumer uses, unless such uses represent
the only significant mode of use of the product.

  "Installation Information" for a User Product means any methods,
procedures, authorization keys, or other information required to install
and execute modified versions of a covered work in that User Product from
a modified version of its Corresponding Source.  The information must
suffice to ensure that the continued functioning of the modified object
code is in no case prevented or interfered with solely because
modification has been made.

  If you convey an object code work under this section in, or with, or
specifically for use in, a User Product, and the conveying occurs as
part of a transaction in which the right of possession and use of the
User Product is transferred to the recipient in perpetuity or for a
fixed term (regardless of how the transaction is characterized), the
Corresponding Source conveyed under this section must be accompanied
by the Installation Information.  But this requirement does not apply
if neither you nor any third party retains the ability to install
modified object code on the User Product (for example, the work has
been installed in ROM).

  The requirement to provide Installation Information does not include a
requirement to continue to provide support service, warranty, or updates
for a work that has been modified or installed by the recipient, or for
the User Product in which it has been modified or installed.  Access to a
network may be denied when the modification itself materially and
adversely affects the operation of the network or violates the rules and
protocols for communication across the network.

  Corresponding Source conveyed, and Installation Information provided,
in accord with this section must be in a format that is publicly
documented (and with an implementation available to the public in
source code form), and must require no special password or key for
unpacking, reading or copying.

  7. Additional Terms.

  "Additional permissions" are terms that supplement the terms of this
License by making exceptions from one or more of its conditions.
Additional permissions that are applicable to the entire Program shall
be treated as though they were included in this License, to the extent
that they are valid under applicable law.  If additional permissions
apply only to part of the Program, that part may be used separately
under those permissions, but the entire Program remains governed by
this License without regard to the additional permissions.

  When you convey a copy of a covered work, you may at your option
remove any additional permissions from that copy, or from any part of
it.  (Additional permissions may be written to require their own
removal in certain cases when you modify the work.)  You may place
additional permissions on material, added by you to a covered work,
for which you have or can give appropriate copyright permission.

  Notwithstanding any other provision of this License, for material you
add to a covered work, you may (if authorized by the copyright holders of
that material) supplement the terms of this License with terms:

    a) Disclaiming warranty or limiting liability differently from the
    terms of sections 15 and 16 of this License; or

    b) Requiring preservation of specified reasonable legal notices or
    author attributions in that material or in the Appropriate Legal
    Notices displayed by works containing it; or

    c) Prohibiting misrepresentation of the origin of that material, or
    requiring that modified versions of such material be marked in
    reasonable ways as different from the original version; or

    d) Limiting the use for publicity purposes of names of licensors or
    authors of the material; or

    e) Declining to grant rights under trademark law for use of some
    trade names, trademarks, or service marks; or

    f) Requiring indemnification of licensors and authors of that
    material by anyone who conveys the material (or modified versions of
    it) with contractual assumptions of liability to the recipient, for
    any liability that these contractual assumptions directly impose on
    those licensors and authors.

  All other non-permissive additional terms are considered "further
restrictions" within the meaning of section 10.  If the Program as you
received it, or any part of it, contains a notice stating that it is
governed by this License along with a term that is a further
restriction, you may remove that term.  If a license document contains
a further restriction but permits relicensing or conveying under this
License, you may add to a covered work material governed by the terms
of that license document, provided that the further restriction does
not survive such relicensing or conveying.

  If you add terms to a covered work in accord with this section, you
must place, in the relevant source files, a statement of the
additional terms that apply to those files, or a notice indicating
where to find the applicable terms.

  Additional terms, permissive or non-permissive, may be stated in the
form of a separately written license, or stated as exceptions;
the above requirements apply either way.

  8. Termination.

  You may not propagate or modify a covered work except as expressly
provided under this License.  Any attempt otherwise to propagate or
modify it is void, and will automatically terminate your rights under
this License (including any patent licenses granted under the third
paragraph of section 11).

  However, if you cease all violation of this License, then your
license from a particular copyright holder is reinstated (a)
provisionally, unless and until the copyright holder explicitly and
finally terminates your license, and (b) permanently, if the copyright
holder fails to notify you of the violation by some reasonable means
prior to 60 days after the cessation.

  Moreover, your license from a particular copyright holder is
reinstated permanently if the copyright holder notifies you of the
violation by some reasonable means, this is the first time you have
received notice of violation of this License (for any work) from that
copyright holder, and you cure the violation prior to 30 days after
your receipt of the notice.

  Termination of your rights under this section does not terminate the
licenses of parties who have received copies or rights from you under
this License.  If your rights have been terminated and not permanently
reinstated, you do not qualify to receive new licenses for the same
material under section 10.

  9. Acceptance Not Required for Having Copies.

  You are not required to accept this License in order to receive or
run a copy of the Program.  Ancillary propagation of a covered work
occurring solely as a consequence of using peer-to-peer transmission
to receive a copy likewise does not require acceptance.  However,
nothing other than this License grants you permission to propagate or
modify any covered work.  These actions infringe copyright if you do
not accept this License.  Therefore, by modifying or propagating a
covered work, you indicate your acceptance of this License to do so.

  10. Automatic Licensing of Downstream Recipients.

  Each time you convey a covered work, the recipient automatically
receives a license from the original licensors, to run, modify and
propagate that work, subject to this License.  You are not responsible
for enforcing compliance by third parties with this License.

  An "entity transaction" is a transaction transferring control of an
organization, or substantially all assets of one, or subdividing an
organization, or merging organizations.  If propagation of a covered
work results from an entity transaction, each party to that
transaction who receives a copy of the work also receives whatever
licenses to the work the party's predecessor in interest had or could
give under the previous paragraph, plus a right to possession of the
Corresponding Source of the work from the predecessor in interest, if
the predecessor has it or can get it with reasonable efforts.

  You may not impose any further restrictions on the exercise of the
rights granted or affirmed under this License.  For example, you may
not impose a license fee, royalty, or other charge for exercise of
rights granted under this License, and you may not initiate litigation
(including a cross-claim or counterclaim in a lawsuit) alleging that
any patent claim is infringed by making, using, selling, offering for
sale, or importing the Program or any portion of it.

  11. Patents.

  A "contributor" is a copyright holder who authorizes use under this
License of the Program or a work on which the Program is based.  The
work thus licensed is called the contributor's "contributor version".

  A contributor's "essential patent claims" are all patent claims
owned or controlled by the contributor, whether already acquired or
hereafter acquired, that would be infringed by some manner, permitted
by this License, of making, using, or selling its contributor version,
but do not include claims that would be infringed only as a
consequence of further modification of the contributor version.  For
purposes of this definition, "control" includes the right to grant
patent sublicenses in a manner consistent with the requirements of
this License.

  Each contributor grants you a non-exclusive, worldwide, royalty-free
patent license under the contributor's essential patent claims, to
make, use, sell, offer for sale, import and otherwise run, modify and
propagate the contents of its contributor version.

  In the following three paragraphs, a "patent license" is any express
agreement or commitment, however denominated, not to enforce a patent
(such as an express permission to practice a patent or covenant not to
sue for patent infringement).  To "grant" such a patent license to a
party means to make such an agreement or commitment not to enforce a
patent against the party.

  If you convey a covered work, knowingly relying on a patent license,
and the Corresponding Source of the work is not available for anyone
to copy, free of charge and under the terms of this License, through a
publicly available network server or other readily accessible means,
then you must either (1) cause the Corresponding Source to be so
available, or (2) arrange to deprive yourself of the benefit of the
patent license for this particular work, or (3) arrange, in a manner
consistent with the requirements of this License, to extend the patent
license to downstream recipients.  "Knowingly relying" means you have
actual knowledge that, but for the patent license, your conveying the
covered work in a country, or your recipient's use of the covered work
in a country, would infringe one or more identifiable patents in that
country that you have reason to believe are valid.

  If, pursuant to or in connection with a single transaction or
arrangement, you convey, or propagate by procuring conveyance of, a
covered work, and grant a patent license to some of the parties
receiving the covered work authorizing them to use, propagate, modify
or convey a specific copy of the covered work, then the patent license
you grant is automatically extended to all recipients of the covered
work and works based on it.

  A patent license is "discriminatory" if it does not include within
the scope of its coverage, prohibits the exercise of, or is
conditioned on the non-exercise of one or more of the rights that are
specifically granted under this License.  You may not convey a covered
work if you are a party to an arrangement with a third party that is
in the business of distributing software, under which you make payment
to the third party based on the extent of your activity of conveying
the work, and under which the third party grants, to any of the
parties who would receive the covered work from you, a discriminatory
patent license (a) in connection with copies of the covered work
conveyed by you (or copies made from those copies), or (b) primarily
for and in connection with specific products or compilations that
contain the covered work, unless you entered into that arrangement,
or that patent license was granted, prior to 28 March 2007.

  Nothing in this License shall be construed as excluding or limiting
any implied license or other defenses to infringement that may
otherwise be available to you under applicable patent law.

  12. No Surrender of Others' Freedom.

  If conditions are imposed on you (whether by court order, agreement or
otherwise) that contradict the conditions of this License, they do not
excuse you from the conditions of this License.  If you cannot convey a
covered work so as to satisfy simultaneously your obligations under this
License and any other pertinent obligations, then as a consequence you may
not convey it at all.  For example, if you agree to terms that obligate you
to collect a royalty for further conveying from those to whom you convey
the Program, the only way you could satisfy both those terms and this
License would be to refrain entirely from conveying the Program.

  13. Use with the GNU Affero General Public License.

  Notwithstanding any other provision of this License, you have
permission to link or combine any covered work with a work licensed
under version 3 of the GNU Affero General Public License into a single
combined work, and to convey the resulting work.  The terms of this
License will continue to apply to the part which is the covered work,
but the special requirements of the GNU Affero General Public License,
section 13, concerning interaction through a network will apply to the
combination as such.

  14. Revised Versions of this License.

  The Free Software Foundation may publish revised and/or new versions of
the GNU General Public License from time to time.  Such new versions will
be similar in spirit to the present version, but may differ in detail to
address new problems or concerns.

  Each version is given a distinguishing version number.  If the
Program specifies that a certain numbered version of the GNU General
Public License "or any later version" applies to it, you have the
option of following the terms and conditions either of that numbered
version or of any later version published by the Free Software
Foundation.  If the Program does not specify a version number of the
GNU General Public License, you may choose any version ever published
by the Free Software Foundation.

  If the Program specifies that a proxy can decide which future
versions of the GNU General Public License can be used, that proxy's
public statement of acceptance of a version permanently authorizes you
to choose that version for the Program.

  Later license versions may give you additional or different
permissions.  However, no additional obligations are imposed on any
author or copyright holder as a result of your choosing to follow a
later version.

  15. Disclaimer of Warranty.

  THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY
APPLICABLE LAW.  EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT
HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY
OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO,
THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE.  THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM
IS WITH YOU.  SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF
ALL NECESSARY SERVICING, REPAIR OR CORRECTION.

  16. Limitation of Liability.

  IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING
WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS
THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY
GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE
USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF
DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD
PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS),
EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF
SUCH DAMAGES.

  17. Interpretation of Sections 15 and 16.

  If the disclaimer of warranty and limitation of liability provided
above cannot be given local legal effect according to their terms,
reviewing courts shall apply local law that most closely approximates
an absolute waiver of all civil liability in connection with the
Program, unless a warranty or assumption of liability accompanies a
copy of the Program in return for a fee.

                     END OF TERMS AND CONDITIONS
"""

if __name__ == "__main__":
    gui = GottenGeography()
    gui.main()
