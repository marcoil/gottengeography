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

import os, re, time, calendar, math, gettext, json, pyexiv2
from gi.repository import Clutter, GtkChamplain, Champlain
from gi.repository import Gio, Gtk, GObject, Gdk, GdkPixbuf, GConf
from gettext import gettext as _
from xml.parsers import expat
from fractions import Fraction

# "If I have seen a little further it is by standing on the shoulders of Giants."
#                                    --- Isaac Newton

APPNAME = "GottenGeography"
VERSION = "0.4"

gettext.bindtextdomain(APPNAME.lower())
gettext.textdomain(APPNAME.lower())

class GottenGeography:
    """Provides a graphical interface to automagically geotag photos.
    
    Just load your photos, and load a GPX file, and GottenGeography will
    automatically cross-reference the timestamps on the photos to the timestamps
    in the GPX to determine the three-dimensional coordinates of each photo.
    """
    
################################################################################
# GPS math. These methods convert numbers into other numbers.
################################################################################
    
    def dms_to_decimal(self, degrees, minutes, seconds, sign=""):
        """Convert degrees, minutes, seconds into decimal degrees."""
        return (-1 if re.match(r'[SWsw]', sign) else 1) * (
            degrees.to_float()        +
            minutes.to_float() / 60   +
            seconds.to_float() / 3600
        )
    
    def decimal_to_dms(self, decimal):
        """Convert decimal degrees into degrees, minutes, seconds."""
        remainder, degrees = math.modf(abs(decimal))
        remainder, minutes = math.modf(remainder * 60)
        seconds            =           remainder * 60
        return [
            pyexiv2.Rational(degrees, 1),
            pyexiv2.Rational(minutes, 1),
            self.float_to_rational(seconds)
        ]
    
    def float_to_rational(self, value):
        """Create a pyexiv2.Rational with help from fractions.Fraction."""
        frac = Fraction(abs(value)).limit_denominator(99999)
        return pyexiv2.Rational(frac.numerator, frac.denominator)
    
    def valid_coords(self, lat, lon):
        """Determine the validity of coordinates."""
        if type(lat) not in (float, int): return False
        if type(lon) not in (float, int): return False
        return abs(lat) <= 90 and abs(lon) <= 180
    
################################################################################
# Champlain. This section contains methods that manipulate the map.
################################################################################
    
    def remember_location_with_gconf(self):
        """Use GConf for persistent storage of the currently viewed location."""
        self.gconf_set('last_latitude',   self.map_view.get_property('latitude'))
        self.gconf_set('last_longitude',  self.map_view.get_property('longitude'))
        self.gconf_set('last_zoom_level', self.map_view.get_zoom_level())
    
    def remember_location(self):
        """Add the current location to the history stack."""
        self.history.append( [
            self.map_view.get_property('latitude'),
            self.map_view.get_property('longitude'),
            self.map_view.get_zoom_level()
        ] )
    
    def return_to_last(self, button=None):
        """Return the map view to where the user last set it."""
        try: lat, lon, zoom = self.history.pop()
        except IndexError:
            lat  = self.gconf_get('last_latitude',   float)
            lon  = self.gconf_get('last_longitude',  float)
            zoom = self.gconf_get('last_zoom_level', int)
            if button is not None:
                self.status_message(_("That's as far back as she goes, kiddo!"))
        self.map_view.center_on(lat, lon)
        self.map_view.set_zoom_level(zoom)
        self.zoom_button_sensitivity()
    
    def zoom_in(self, button=None):
        """Zoom the map in by one level."""
        self.map_view.zoom_in()
        self.zoom_button_sensitivity()
    
    def zoom_out(self, button=None):
        """Zoom the map out by one level."""
        self.map_view.zoom_out()
        self.zoom_button_sensitivity()
    
    def move_map_view_by_arrow_keys(self, accel_group, acceleratable, keyval, modifier):
        """Move the map view in discrete steps."""
        x = self.map_view.get_width()  / 2
        y = self.map_view.get_height() / 2
        
        # moves by 1/5 (40% of half) screen length in the given direction
        if   keyval == Gdk.keyval_from_name("Left"):  x *= 0.6
        elif keyval == Gdk.keyval_from_name("Up"):    y *= 0.6
        elif keyval == Gdk.keyval_from_name("Right"): x *= 1.4
        elif keyval == Gdk.keyval_from_name("Down"):  y *= 1.4
        
        lat, lon = self.map_view.get_coords_at(int(x), int(y))[1:3]
        if self.valid_coords(lat, lon): self.map_view.center_on(lat, lon)
    
    def maps_link(self, lat, lon):
        """Create a Pango link to Google Maps."""
        return '<a href="http://maps.google.com/maps?q=%s,%s">%s</a>' % (
            lat, lon, _("View in Google Maps"))
    
    def display_actors(self, stage=None, parameter=None):
        """Position and update all my custom ClutterActors."""
        stage_width  = self.stage.get_width()
        stage_height = self.stage.get_height()
        self.crosshair.set_position(
            (stage_width  - self.crosshair.get_width())  / 2,
            (stage_height - self.crosshair.get_height()) / 2
        )
        
        if stage is None: return
        lat = self.map_view.get_property('latitude')
        lon = self.map_view.get_property('longitude')
        self.coords.set_markup("%.5f, %.5f" % (lat, lon))
        self.coords_label.set_markup(self.maps_link(lat, lon))
        
        self.coords_background.set_size(stage_width, self.coords.get_height() + 10)
        self.coords.set_position((stage_width - self.coords.get_width()) / 2, 5)
    
    def marker_clicked(self, marker, event):
        """When a ChamplainMarker is clicked, select it in the GtkListStore.
        
        The interface defined by this method is consistent with the behavior of
        the GtkListStore itself in the sense that a normal click will select
        just one item, but Ctrl+clicking allows you to select multiple.
        """
        try: iter = self.photo[marker.get_name()].iter
        except KeyError: return
        
        if (Clutter.ModifierType.CONTROL_MASK |
            Clutter.ModifierType.MOD2_MASK      == event.get_state()):
            if marker.get_highlighted(): self.photo_selection.unselect_iter(iter)
            else:                        self.photo_selection.select_iter(iter)
        else:
            self.button.gtk_select_all.set_active(False)
            self.photo_selection.unselect_all()
            self.photo_selection.select_iter(iter)
    
    def marker_mouse_in(self, marker, event):
        """Enlarge a hovered-over ChamplainMarker by 5%."""
        marker.set_scale(*[marker.get_scale()[0] * 1.05] * 2)
    
    def marker_mouse_out(self, marker, event):
        """Reduce a no-longer-hovered ChamplainMarker to it's original size."""
        marker.set_scale(*[marker.get_scale()[0] / 1.05] * 2)
    
    def set_marker_highlight(self, marker, area, transparent):
        """Set the highlightedness of the given photo's ChamplainMarker."""
        try:
            if not marker.get_property('visible'): return
        except AttributeError:                     return
        
        highlight = area is not None
        marker.set_property('opacity', 64 if transparent else 255)
        marker.set_scale(*[1.1 if highlight else 1] * 2)
        marker.set_highlighted(highlight)
        
        if highlight:
            marker.raise_top()
            lat = marker.get_latitude()
            lon = marker.get_longitude()
            area[0] = min(area[0], lat)
            area[1] = min(area[1], lon)
            area[2] = max(area[2], lat)
            area[3] = max(area[3], lon)
    
    def update_all_marker_highlights(self, selection):
        """Ensure only the selected markers are highlighted."""
        selection_exists = selection.count_selected_rows() > 0
        for photo in self.photo.values():
            # Maintain self.selected for easy iterating.
            if selection.iter_is_selected(photo.iter):
                self.selected.add(photo)
            else:
                self.selected.discard(photo)
            self.set_marker_highlight(photo.marker, None, selection_exists)
        
        if selection_exists:
            area = [ float('inf') ] * 2 + [ float('-inf') ] * 2
            for photo in self.selected:
                self.set_marker_highlight(photo.marker, area, False)
            if self.valid_coords(area[0], area[1]):
                self.remember_location()
                self.map_view.ensure_visible(*area + [False])
    
    def add_marker(self, label):
        """Create a new ChamplainMarker and add it to the map."""
        marker = Champlain.Marker()
        marker.set_name(label)
        marker.set_text(os.path.basename(label))
        marker.set_property('reactive', True)
        marker.connect("button-press-event", self.marker_clicked)
        marker.connect("enter-event", self.marker_mouse_in)
        marker.connect("leave-event", self.marker_mouse_out)
        
        self.map_photo_layer.add_marker(marker)
        return marker
    
    def clear_all_gpx(self, widget=None):
        """Forget all GPX data, start over with a clean slate."""
        for polygon in self.polygons:
            polygon.hide()
            # Why doesn't this work? Why do these always cause segfaults?
            # Who are you? Where are my pants?
            #self.map_view.remove_polygon(polygon)
            #polygon.clear_points()
        
        self.polygons  = []
        self.tracks    = {}
        self.gpx_state = {}
        self.metadata  = {
            'delta': 0,                  # Time offset
            'omega': float('-inf'),      # Final GPX track point
            'alpha': float('inf'),       # Initial GPX track point
            'tau':   time.clock(),       # Most recent time screen was updated
            'area':  [ float('inf') ] * 2 + [ float('-inf') ] * 2
        }
        
        self.update_sensitivity()
    
################################################################################
# File data handling. These methods interact with files (loading, saving, etc)
################################################################################
    
    def save_all_files(self, widget=None):
        """Ensure all loaded files are saved."""
        self.progressbar.show()
        total = len(self.modified)
        for photo in self.modified.copy():
            self.redraw_interface(
                (1 + total - len(self.modified)) / total,
                os.path.basename(photo.filename)
            )
            
            key = 'Exif.GPSInfo.GPS'
            
            exif = pyexiv2.ImageMetadata(photo.filename)
            exif.read()
            
            if photo.altitude is not None:
                exif[key + 'Altitude']    = self.float_to_rational(photo.altitude)
                exif[key + 'AltitudeRef'] = '0' if photo.altitude >= 0 else '1'
            exif[key + 'Latitude']     = self.decimal_to_dms(photo.latitude)
            exif[key + 'LatitudeRef']  = "N" if photo.latitude >= 0 else "S"
            exif[key + 'Longitude']    = self.decimal_to_dms(photo.longitude)
            exif[key + 'LongitudeRef'] = "E" if photo.longitude >= 0 else "W"
            exif[key + 'MapDatum']     = 'WGS-84'
            
            for iptc in self.geonames_of_interest.values():
                if photo[iptc.lower()] is not None:
                    exif['Iptc.Application2.' + iptc] = [photo[iptc.lower()]]
            
            try:
                exif.write()
            except Exception as inst:
                self.status_message(", ".join(inst.args))
            else:
                self.modified.discard(photo)
                self.loaded_photos.set_value(photo.iter, self.SUMMARY,
                    photo.long_summary())
        
        self.update_sensitivity()
        self.progressbar.hide()
    
    def load_exif_from_file(self, filename, thumb_size=200):
        """Read photo metadata from disk using the pyexiv2 module.
        
        Raises IOError if the specified file is not an image
        format supported by both pyexiv2 and GdkPixbuf.
        """
        try:
            exif = pyexiv2.ImageMetadata(filename)
            exif.read()
            
            # I have tested this successfully on JPG, PNG, DNG, and NEF.
            photo = Photograph(
                filename, GdkPixbuf.Pixbuf.new_from_file_at_size(
                filename, thumb_size, thumb_size))
        except:
            # If GdkPixbuf can't open it, it's most likely not a photo. However,
            # if there exists an image format that is supported by pyexiv2 but
            # not GdkPixbuf, then this is a bug.
            raise IOError
        
        try:
            # This assumes that the camera and computer have the same timezone.
            timestamp = exif['Exif.Photo.DateTimeOriginal'].value
            photo.timestamp = int(time.mktime(timestamp.timetuple()))
        except:
            photo.timestamp = int(os.stat(filename).st_mtime)
        
        gps  = 'Exif.GPSInfo.GPS'
        try:
            photo.latitude = self.dms_to_decimal(
                *exif[gps + 'Latitude'].value +
                [exif[gps + 'LatitudeRef'].value]
            )
            photo.longitude = self.dms_to_decimal(
                *exif[gps + 'Longitude'].value +
                [exif[gps + 'LongitudeRef'].value]
            )
        except KeyError: pass
        
        try:
            photo.altitude = exif[gps + 'Altitude'].value.to_float()
            if int(exif[gps + 'AltitudeRef'].value) > 0:
                photo.altitude *= -1
        except: pass
        
        for key in self.geonames_of_interest.values():
            try: photo[key.lower()] = exif['Iptc.Application2.' + key].values[0]
            except KeyError: pass
        
        return photo
    
    def gpx_element_root(self, name, attributes):
        """Expat StartElementHandler.
        
        This is only called on the top level element in the given XML file.
        """
        if name <> 'gpx': raise expat.ExpatError
        self.gpx_parser.StartElementHandler = self.gpx_element_start
    
    def gpx_element_start(self, name, attributes):
        """Expat StartElementHandler.
        
        This method creates new ChamplainPolygons when necessary and initializes
        variables for the CharacterDataHandler. It also extracts latitude and
        longitude from GPX element attributes. For example:
        
        <trkpt lat="45.147445" lon="-81.469507">
        """
        self.metadata['element-name'] = name
        self.gpx_state[name]          = ""
        self.gpx_state.update(attributes)
        
        if name == "trkseg":
            self.polygons.append(Champlain.Polygon())
            self.polygons[-1].set_stroke_width(5)
            self.polygons[-1].set_stroke_color(self.track_color)
            self.polygons[-1].show()
            self.map_view.add_polygon(self.polygons[-1])
    
    def gpx_element_data(self, data):
        """Expat CharacterDataHandler.
        
        This method extracts elevation and time data from GPX elements.
        For example:
        
        <ele>671.092</ele>
        <time>2010-10-16T20:09:13Z</time>
        """
        data = data.strip()
        if not data: return
        
        # Sometimes expat calls this handler multiple times each with just
        # a chunk of the whole data, so += is necessary to collect all of it.
        self.gpx_state[self.metadata['element-name']] += data
    
    def gpx_element_end(self, name):
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
        if name <> "trkpt": return
        
        try:
            timestamp = calendar.timegm(
                # Sadly, time.strptime() was too slow and had to be replaced.
                map(int, self.delimiters.split(self.gpx_state['time'])[0:6])
            )
            lat = float(self.gpx_state['lat'])
            lon = float(self.gpx_state['lon'])
        except:
            # If any of lat, lon, or time is missing, we cannot continue.
            # Better to just give up on this track point and go to the next.
            return
        
        self.tracks[timestamp] = {
            'elevation': float(self.gpx_state.get('ele', 0.0)),
            'point':     self.polygons[-1].append_point(lat, lon)
        }
        
        self.gpx_state.clear()
        
        self.metadata['omega']   = max(self.metadata['omega'], timestamp)
        self.metadata['alpha']   = min(self.metadata['alpha'], timestamp)
        self.metadata['area'][0] = min(self.metadata['area'][0], lat)
        self.metadata['area'][1] = min(self.metadata['area'][1], lon)
        self.metadata['area'][2] = max(self.metadata['area'][2], lat)
        self.metadata['area'][3] = max(self.metadata['area'][3], lon)
        
        if time.clock() - self.metadata['tau'] > .2:
            self.progressbar.pulse()
            self.map_view.ensure_visible(*self.metadata['area'] + [False])
            self.redraw_interface()
            self.metadata['tau'] = time.clock()
    
    def load_gpx_from_file(self, filename):
        """Parse GPX data, drawing each GPS track segment on the map."""
        self.remember_location()
        start_points = len(self.tracks)
        start_time   = time.clock()
        
        self.gpx_parser = expat.ParserCreate()
        self.gpx_parser.StartElementHandler  = self.gpx_element_root
        self.gpx_parser.CharacterDataHandler = self.gpx_element_data
        self.gpx_parser.EndElementHandler    = self.gpx_element_end
        
        with open(filename) as gpx:
            status = self.gpx_parser.ParseFile(gpx)
        
        self.update_sensitivity()
        self.status_message(
            _("%d points loaded in %.2fs.") %
            (len(self.tracks) - start_points,
             time.clock()     - start_time)
        )
        
        if len(self.tracks) > 0:
            self.map_view.ensure_visible(*self.metadata['area'] + [False])
        
        for filename in self.photo:
            self.auto_timestamp_comparison(filename)
        
        # Cleanup leftover data from parser
        self.gpx_state.clear()
        if 'element-name' in self.metadata: del self.metadata['element-name']
    
################################################################################
# GtkListStore. These methods modify the liststore data in some way.
################################################################################
    
    def auto_timestamp_comparison(self, filename):
        """Use GPX data to calculate photo coordinates and elevation."""
        if len(self.tracks) < 2:        return
        if self.photo[filename].manual: return
        
        photo  = self.photo[filename].timestamp # this is in epoch seconds
        photo += self.metadata['delta']
        
        # Chronological first and last timestamp created by the GPX device.
        hi = self.metadata['omega']
        lo = self.metadata['alpha']
        
        # If the photo is out of range, simply peg it to the end of the range.
        photo = min(max(photo, lo), hi)
        
        try:
            lat = self.tracks[photo]['point'].lat
            lon = self.tracks[photo]['point'].lon
            ele = self.tracks[photo]['elevation']
        except KeyError:
            # Iterate over the available gpx points, find the two that are
            # nearest (in time) to the photo timestamp.
            for point in self.tracks:
                if point > photo: hi = min(point, hi)
                if point < photo: lo = max(point, lo)
            
            delta = hi - lo    # in seconds
            
            # lo_perc and hi_perc are ratios (between 0 and 1) representing the
            # proportional amount of time between the photo and the points.
            hi_perc = (photo - lo) / delta
            lo_perc = (hi - photo) / delta
            
            # Find intermediate values using the proportional ratios.
            lat = ((self.tracks[lo]['point'].lat * lo_perc)  +
                   (self.tracks[hi]['point'].lat * hi_perc))
            lon = ((self.tracks[lo]['point'].lon * lo_perc)  +
                   (self.tracks[hi]['point'].lon * hi_perc))
            ele = ((self.tracks[lo]['elevation'] * lo_perc)  +
                   (self.tracks[hi]['elevation'] * hi_perc))
        
        self.modify_coordinates(filename, lat, lon, ele)
    
    def time_offset_changed(self, widget):
        """Update all photos each time the camera's clock is corrected."""
        for spinbutton in self.offset.values():
            # Suppress extraneous invocations of this method.
            spinbutton.handler_block_by_func(self.time_offset_changed)
        
        seconds = self.offset.seconds.get_value()
        minutes = self.offset.minutes.get_value()
        hours   = self.offset.hours.get_value()
        offset  = int((hours * 3600) + (minutes * 60) + seconds)
        
        if abs(seconds) == 60:
            minutes += seconds/60
            self.offset.seconds.set_value(0)
            self.offset.minutes.set_value(minutes)
        
        if abs(minutes) == 60:
            hours += minutes/60
            self.offset.minutes.set_value(0)
            self.offset.hours.set_value(hours)
        
        if offset <> self.metadata['delta']:
            self.metadata['delta'] = offset
            
            for filename in self.photo:
                self.auto_timestamp_comparison(filename)
        
        for spinbutton in self.offset.values():
            spinbutton.handler_unblock_by_func(self.time_offset_changed)
    
    def apply_selected_photos(self, button=None):
        """Manually apply map center coordinates to all selected photos."""
        for photo in self.selected:
            photo.manual = True
            self.modify_coordinates(photo.filename,
                self.map_view.get_property('latitude'),
                self.map_view.get_property('longitude'))
            photo.marker.raise_top()
        self.update_sensitivity()
    
    def revert_selected_photos(self, button=None):
        """Discard any modifications to all selected photos."""
        self.progressbar.show()
        
        mod_in_sel = self.modified & self.selected
        
        total = len(mod_in_sel)
        while len(mod_in_sel) > 0:
            photo = mod_in_sel.pop()
            self.redraw_interface(
                (total - len(mod_in_sel)) / total,
                os.path.basename(photo.filename)
            )
            self.add_or_reload_photo(photo.filename)
            photo.marker.raise_top()
        
        self.progressbar.hide()
        self.update_sensitivity()
    
    def close_selected_photos(self, button=None):
        """Discard all selected photos."""
        for photo in self.selected.copy():
            photo.marker.destroy()
            self.loaded_photos.remove(photo.iter)
            self.selected.discard(photo)
            self.modified.discard(photo)
            del self.photo[photo.filename]
        
        self.button.gtk_select_all.set_active(False)
        self.update_sensitivity()
    
    def modify_coordinates(self, filename, lat, lon, ele=None):
        """Alter the coordinates of a loaded photo."""
        self.photo[filename].update( {
            'altitude':  ele,
            'latitude':  lat,
            'longitude': lon
        } )
        self.photo[filename].position_marker()
        self.photo[filename].request_geoname(self)
        self.modify_summary(filename)
    
    def modify_summary(self, filename):
        """Insert the current photo summary into the liststore."""
        photo = self.photo[filename]
        self.modified.add(photo)
        self.loaded_photos.set_value(photo.iter, self.SUMMARY,
            ('<b>%s</b>' % photo.long_summary()))
    
    def add_or_reload_photo(self, filename):
        """Create or update a row in the ListStore.
        
        Checks if the file has already been loaded, and if not, creates a new
        row in the ListStore. Either way, it then populates that row with
        photo metadata as read from disk. Effectively, this is used both for
        loading new photos, and reverting old photos, discarding any changes.
        
        Raises IOError if filename refers to a file that is not a photograph.
        """
        photo = self.load_exif_from_file(filename)
        
        photo.update( {
            'iter':   self.loaded_photos.append([None] * 4),
            'marker': self.add_marker(filename)
        } if filename not in self.photo else {
            'iter':   self.photo[filename].iter,
            'marker': self.photo[filename].marker
        } )
        
        photo.position_marker()
        self.modified.discard(photo)
        self.photo[filename] = photo
        
        self.loaded_photos.set_value(photo.iter, self.PATH,      filename)
        self.loaded_photos.set_value(photo.iter, self.THUMB,     photo.thumb)
        self.loaded_photos.set_value(photo.iter, self.TIMESTAMP, photo.timestamp)
        self.loaded_photos.set_value(photo.iter, self.SUMMARY,   photo.long_summary())
        
        self.auto_timestamp_comparison(filename)
        self.update_sensitivity()
    
################################################################################
# Dialogs. Various dialog-related methods for user interaction.
################################################################################
    
    def update_preview(self, chooser):
        """Display photo thumbnail and geotag data in file chooser."""
        filename = chooser.get_preview_filename()
        self.preview_label.set_label(_("No preview available"))
        self.preview_image.set_from_stock(Gtk.STOCK_FILE,
            Gtk.IconSize.LARGE_TOOLBAR
        )
        
        try: photo = self.load_exif_from_file(filename, 300)
        except IOError: return
        
        lat, lon = photo.latitude, photo.longitude
        self.preview_image.set_from_pixbuf(photo.thumb)
        self.preview_label.set_label("%s\n%s" % (photo.short_summary(),
            self.maps_link(lat, lon) if self.valid_coords(lat, lon) else ""))
    
    def add_files_dialog(self, widget=None, data=None):
        """Display a file chooser, and attempt to load chosen files."""
        chooser = Gtk.FileChooserDialog(
            title=_("Open Files"),
            buttons=(
                Gtk.STOCK_CANCEL,  Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OPEN,    Gtk.ResponseType.OK
            )
        )
        chooser.set_action(Gtk.FileChooserAction.OPEN)
        chooser.set_default_response(Gtk.ResponseType.OK)
        chooser.set_select_multiple(True)
        
        self.preview_image = Gtk.Image()
        self.preview_label = Gtk.Label()
        self.preview_label.set_justify(Gtk.Justification.CENTER)
        self.preview_label.set_selectable(True)
        self.preview_label.set_use_markup(True)
        self.preview_widget = Gtk.VBox(spacing=6)
        self.preview_widget.set_size_request(310, -1)
        self.preview_widget.pack_start(self.preview_image, False, False, 0)
        self.preview_widget.pack_start(self.preview_label, False, False, 0)
        self.preview_widget.show_all()
        
        chooser.set_preview_widget(self.preview_widget)
        chooser.set_preview_widget_active(True)
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
        
        invalid_files, count = [], 0
        for filename in files:
            count += 1
            self.redraw_interface(
                count / len(files),
                os.path.basename(filename)
            )
            
            # Assume the file is an image; if that fails, assume it's GPX;
            # if that fails, show an error
            try:
                try:            self.add_or_reload_photo(filename)
                except IOError: self.load_gpx_from_file(filename)
            except expat.ExpatError:
                invalid_files.append(os.path.basename(filename))
        
        if len(invalid_files) > 0:
            self.status_message(
                _("Could not open: %s") % ", ".join(invalid_files)
            )
        
        self.progressbar.hide()
        self.update_sensitivity()
        self.update_all_marker_highlights(self.photo_selection)
    
    def confirm_quit_dialog(self, widget=None, event=None):
        """Teardown method, inform user of unsaved files, if any."""
        self.remember_location_with_gconf()
        
        # If there's no unsaved data, just close without confirmation.
        if len(self.modified) == 0:
            Gtk.main_quit()
            return True
        
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
        self.redraw_interface()
        
        # Save and/or quit as necessary
        if response == Gtk.ResponseType.ACCEPT: self.save_all_files()
        if response <> Gtk.ResponseType.CANCEL: Gtk.main_quit()
        
        # Prevents GTK from trying to call a non-existant destroy method.
        return True
    
    def about_dialog(self, widget=None, data=None):
        """Describe this application to the user."""
        dialog = Gtk.AboutDialog()
        dialog.set_program_name(APPNAME)
        dialog.set_version(VERSION)
        dialog.set_copyright("(c) Robert Park, 2010")
        dialog.set_license(LICENSE)
        dialog.set_comments(COMMENTS)
        dialog.set_website("http://github.com/robru/GottenGeography/wiki")
        dialog.set_website_label("%s Wiki" % APPNAME)
        dialog.set_authors(["Robert Park <rbpark@exolucere.ca>"])
        dialog.set_documenters(["Robert Park <rbpark@exolucere.ca>"])
        #dialog.set_artists(["Robert Park <rbpark@exolucere.ca>"])
        #dialog.set_translator_credits("Nobody!")
        dialog.run()
        dialog.destroy()
    
################################################################################
# Initialization and Gtk boilerplate/housekeeping type stuff and such.
################################################################################
    
    def __init__(self, animate_crosshair=True):
        self.photo    = {}
        self.selected = set()
        self.modified = set()
        self.history  = []
        self.polygons = []
        
        # GPX files use ISO 8601 dates, which look like 2010-10-16T20:09:13Z.
        # This regex splits that up into a list like 2010, 10, 16, 20, 09, 13.
        self.delimiters = re.compile(r'[:TZ-]')
        
        # Maps geonames.org jargon into IPTC jargon. Expanding this will result
        # in more data being extracted from the geonames.org data
        self.geonames_cache = {}
        self.geonames_queue = {}
        self.geonames_of_interest = {
            'countryCode': 'CountryCode',
            'countryName': 'CountryName',
            'adminName1':  'ProvinceState',
            'name':        'City'
        }
        
        self.toolbar = Gtk.Toolbar()
        self.button  = ReadableDictionary()
        self.create_tool_button(Gtk.STOCK_OPEN, self.add_files_dialog,
            _("Load photos or GPS data (Ctrl+O)"), _("Open"))
        self.create_tool_button(Gtk.STOCK_SAVE, self.save_all_files,
            _("Save all photos (Ctrl+S)"), _("Save All"))
        self.toolbar.add(Gtk.SeparatorToolItem())
        self.create_tool_button(Gtk.STOCK_CLEAR, self.clear_all_gpx,
            _("Unload all GPS data (Ctrl+X)"), _("Clear GPX"))
        self.create_tool_button(Gtk.STOCK_CLOSE, self.close_selected_photos,
            _("Close selected photos (Ctrl+W)"), _("Close Photo"))
        self.toolbar.add(Gtk.SeparatorToolItem())
        self.create_tool_button(Gtk.STOCK_REVERT_TO_SAVED,
            self.revert_selected_photos,
            _("Reload selected photos, losing all changes (Ctrl+Z)"))
        self.toolbar_spacer = Gtk.SeparatorToolItem()
        self.toolbar_spacer.set_expand(True)
        self.toolbar_spacer.set_draw(False)
        self.toolbar.add(self.toolbar_spacer)
        self.create_tool_button(Gtk.STOCK_ZOOM_OUT, self.zoom_out,
            _("Zoom the map out one step."))
        self.create_tool_button(Gtk.STOCK_ZOOM_IN, self.zoom_in, _("Enhance!"))
        self.toolbar.add(Gtk.SeparatorToolItem())
        self.create_tool_button(Gtk.STOCK_GO_BACK, self.return_to_last,
            _("Return to previous location in map view."))
        self.toolbar.add(Gtk.SeparatorToolItem())
        self.create_tool_button(Gtk.STOCK_ABOUT, self.about_dialog,
            _("About %s") % APPNAME)
        
        self.loaded_photos = Gtk.ListStore(
            GObject.TYPE_STRING,  # 0 Path to image file
            GObject.TYPE_STRING,  # 1 Pango-formatted summary
            GdkPixbuf.Pixbuf,     # 2 Thumbnail
            GObject.TYPE_INT,     # 3 Timestamp in Epoch seconds
        )
        
        # Handy names for the above GtkListStore column numbers.
        self.PATH, self.SUMMARY, self.THUMB, self.TIMESTAMP = \
            range(self.loaded_photos.get_n_columns())
        
        self.loaded_photos.set_sort_column_id(
            self.TIMESTAMP,
            Gtk.SortType.ASCENDING
        )
        
        self.cell_string = Gtk.CellRendererText()
        self.cell_thumb  = Gtk.CellRendererPixbuf()
        self.cell_thumb.set_property('stock-id', Gtk.STOCK_MISSING_IMAGE)
        self.cell_thumb.set_property('ypad', 6)
        self.cell_thumb.set_property('xpad', 6)
        
        self.column = Gtk.TreeViewColumn('Photos')
        self.column.pack_start(self.cell_thumb, False)
        self.column.add_attribute(self.cell_thumb, 'pixbuf', self.THUMB)
        self.column.pack_start(self.cell_string, False)
        self.column.add_attribute(self.cell_string, 'markup', self.SUMMARY)
        self.column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        
        self.photos_view = Gtk.TreeView(model=self.loaded_photos)
        self.photos_view.set_enable_search(False)
        self.photos_view.set_reorderable(False)
        self.photos_view.set_headers_visible(False)
        self.photos_view.set_rubber_banding(True)
        self.photos_view.append_column(self.column)
        
        self.photo_selection = self.photos_view.get_selection()
        self.photo_selection.set_mode(Gtk.SelectionMode.MULTIPLE)
        self.photo_selection.connect("changed", self.update_all_marker_highlights)
        self.photo_selection.connect("changed", self.update_sensitivity)
        
        self.photo_scroller = Gtk.ScrolledWindow()
        self.photo_scroller.add(self.photos_view)
        self.photo_scroller.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC
        )
        
        self.button.gtk_apply = Gtk.Button.new_from_stock(Gtk.STOCK_APPLY)
        self.button.gtk_apply.set_tooltip_text(
            _("Place selected photos onto center of map (Ctrl+Return)"))
        self.button.gtk_apply.connect("clicked", self.apply_selected_photos)
        
        self.button.gtk_select_all = Gtk.ToggleButton(label=Gtk.STOCK_SELECT_ALL)
        self.button.gtk_select_all.set_use_stock(True)
        self.button.gtk_select_all.set_tooltip_text(
            _("Toggle whether all photos are selected (Ctrl+A)"))
        self.button.gtk_select_all.connect("clicked", self.toggle_selected_photos)
        
        self.photo_button_bar = Gtk.HBox(spacing=12)
        self.photo_button_bar.set_border_width(3)
        for button in [ 'gtk_select_all', 'gtk_apply' ]:
            self.photo_button_bar.pack_start(
                self.button[button], True, True, 0
            )
        
        self.photos_with_buttons = Gtk.VBox()
        self.photos_with_buttons.pack_start(self.photo_scroller, True, True, 0)
        self.photos_with_buttons.pack_start(self.photo_button_bar, False, False, 0)
        
        # Initialize all the clutter/champlain stuff
        Clutter.init([])
        self.champlain = GtkChamplain.Embed()
        self.map_view = self.champlain.get_view()
        self.map_view.set_property('show-scale', True)
        self.map_view.set_scroll_mode(Champlain.ScrollMode.KINETIC)
        self.map_photo_layer = Champlain.Layer()
        self.map_view.add_layer(self.map_photo_layer)
        
        self.photos_and_map_container = Gtk.HPaned()
        self.photos_and_map_container.add(self.photos_with_buttons)
        self.photos_and_map_container.add(self.champlain)
        
        self.progressbar = Gtk.ProgressBar()
        self.progressbar.set_size_request(0, -1) # Stops it from flailing.
        
        self.offset_label = Gtk.Label(label=_("Clock Offset: "))
        self.coords_label = Gtk.Label()
        
        self.statusbar = Gtk.Statusbar(spacing=12)
        self.statusbar.set_border_width(3)
        self.statusbar.pack_start(self.progressbar, True, True, 0)
        self.statusbar.pack_start(self.coords_label, False, False, 0)
        self.statusbar.pack_start(self.offset_label, False, False, 0)
        
        self.offset = ReadableDictionary( {
            'seconds': self.create_spin_button(60, _("seconds")),
            'minutes': self.create_spin_button(60, _("minutes")),
            'hours':   self.create_spin_button(24, _("hours"))
        } )
        
        self.app_container = Gtk.VBox(spacing=0)
        self.app_container.pack_start(self.toolbar, False, True, 0)
        self.app_container.pack_start(self.photos_and_map_container, True, True, 0)
        self.app_container.pack_end(self.statusbar, False, True, 0)
        
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_title(APPNAME)
        self.window.set_default_icon_name('gtk-new')
        self.window.set_default_size(800,600)
        self.window.set_size_request(620,400)
        self.window.connect("delete_event", self.confirm_quit_dialog)
        self.window.add(self.app_container)
        
        self.track_color = Clutter.Color.new(255, 0, 0, 128)
        
        self.gconf_client = GConf.Client.get_default()
        self.return_to_last()
        
        # Key bindings
        self.accel = Gtk.AccelGroup()
        self.window.add_accel_group(self.accel)
        for key in [ 'q', 'w', 'x', 'o', 's', 'z', 'a', 'Return', 'slash',
        'question', 'equal', 'minus', 'Left' ]:
            self.accel.connect(
                Gdk.keyval_from_name(key),
                Gdk.ModifierType.CONTROL_MASK,
                0, self.key_accel
            )
        
        for key in [ 'Left', 'Right', 'Up', 'Down' ]:
            self.accel.connect(
                Gdk.keyval_from_name(key),
                Gdk.ModifierType.MOD1_MASK,
                0, self.move_map_view_by_arrow_keys
            )
        
        self.window.show_all()
        self.progressbar.hide()
        
        self.clear_all_gpx()
        self.redraw_interface()
        
        self.stage = self.map_view.get_stage()
        
        self.coords_background = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(255, 255, 255, 164)
        )
        self.prep_actor(self.coords_background)
        self.coords_background.set_position(0, 0)
        
        self.coords = Clutter.Text()
        self.coords.set_single_line_mode(True)
        self.prep_actor(self.coords)
        
        self.crosshair = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(0, 0, 0, 32)
        )
        self.crosshair.set_property('has-border', True)
        self.crosshair.set_border_color(Clutter.Color.new(0, 0, 0, 128))
        self.crosshair.set_border_width(1)
        self.prep_actor(self.crosshair)
        
        self.zoom_button_sensitivity()
        self.display_actors(self.stage)
        
        if not animate_crosshair: return
        
        # This causes the crosshair to start off huge and invisible, and it
        # quickly shrinks, spins, and fades into existence. The last value for
        # i before it stops will be 8, so: 53-i ends at 45 degrees, and
        # 260-(0.51*i) ends at 255 or full opacity. The numbers come from
        # simplifying the formula ((508-i)/500) * 255.
        for i in range(500, 7, -1):
            self.crosshair.set_size(i, i)
            self.crosshair.set_z_rotation_from_gravity(53-i,
                Clutter.Gravity.CENTER)
            self.crosshair.set_property('opacity', int(260-(0.51*i)))
            self.display_actors()
            self.redraw_interface()
            time.sleep(0.002)
        
        for signal in [ 'height', 'width', 'latitude', 'longitude' ]:
            self.map_view.connect('notify::%s' % signal, self.display_actors)
    
    def create_spin_button(self, value, label):
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
            _("Add or subtract %s from your camera's clock.") % label)
        
        button.connect("value-changed", self.time_offset_changed)
        self.statusbar.pack_end(button, False, False, 0)
        return button
    
    def create_tool_button(self, stock_id, action, tooltip, label=None):
        """Create a ToolButton for use on the toolbar."""
        button = Gtk.ToolButton(stock_id=stock_id)
        button.set_is_important(label is not None)
        button.set_tooltip_text(tooltip)
        button.connect("clicked", action)
        
        if label is not None: button.set_label(label)
        
        self.toolbar.add(button)
        self.button[re.sub(r'-', '_', stock_id)] = button
    
    def prep_actor(self, actor):
        """Do some standard things to a ClutterActor."""
        actor.set_parent(self.stage)
        actor.raise_top()
        actor.show()
    
    def toggle_selected_photos(self, button=None):
        """Toggle the selection of photos."""
        if button is None:
            # User typed Ctrl+a, so select all!
            button = self.button.gtk_select_all
            button.set_active(True)
        
        if button.get_active(): self.photo_selection.select_all()
        else:                   self.photo_selection.unselect_all()
    
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
        elif keyval == Gdk.keyval_from_name("Left"):   self.return_to_last(True)
        elif keyval == Gdk.keyval_from_name("x"):      self.clear_all_gpx()
        elif keyval == Gdk.keyval_from_name("o"):      self.add_files_dialog()
        elif keyval == Gdk.keyval_from_name("q"):      self.confirm_quit_dialog()
        elif keyval == Gdk.keyval_from_name("/"):      self.about_dialog()
        elif keyval == Gdk.keyval_from_name("?"):      self.about_dialog()
        elif keyval == Gdk.keyval_from_name("a"):      self.toggle_selected_photos()
        
        # Prevent the following keybindings from executing if there are no unsaved files
        if len(self.modified) == 0: return
        
        if   keyval == Gdk.keyval_from_name("s"):      self.save_all_files()
        elif keyval == Gdk.keyval_from_name("z"):      self.revert_selected_photos()
    
    def gconf_key(self, key):
        """Determine appropriate GConf key that is unique to this application.
        
        Returns /apps/gottengeography/key.
        """
        return "/".join(['', 'apps', APPNAME.lower(), key])
    
    def gconf_set(self, key, value):
        """Sets the given GConf key to the given value."""
        key = self.gconf_key(key)
        
        if   type(value) is float: self.gconf_client.set_float(key, value)
        elif type(value) is int:   self.gconf_client.set_int(key, value)
    
    def gconf_get(self, key, type):
        """Gets the given GConf key as the requested type."""
        key = self.gconf_key(key)
        
        if   type is float: return self.gconf_client.get_float(key)
        elif type is int:   return self.gconf_client.get_int(key)
    
    def status_message(self, message):
        """Display a message on the GtkStatusBar."""
        self.statusbar.push(self.statusbar.get_context_id("msg"), message)
    
    def redraw_interface(self, fraction=None, text=None):
        """Tell Gtk to redraw the user interface, so it doesn't look hung.
        
        Primarily used to update the progressbar, but also for disappearing
        some dialogs while things are processing in the background. Won't
        modify the progressbar if called with no arguments.
        """
        if fraction is not None: self.progressbar.set_fraction(fraction)
        if text is not None:     self.progressbar.set_text(str(text))
        while Gtk.events_pending(): Gtk.main_iteration()
    
    def zoom_button_sensitivity(self):
        """Ensure zoom buttons are only sensitive when they need to be."""
        zoom_level = self.map_view.get_zoom_level()
        self.button.gtk_zoom_out.set_sensitive(
            self.map_view.get_min_zoom_level() is not zoom_level)
        self.button.gtk_zoom_in.set_sensitive(
            self.map_view.get_max_zoom_level() is not zoom_level)
    
    def update_sensitivity(self, selection=None):
        """Ensure widgets are sensitive only when they need to be.
        
        This method should be called every time any program state changes,
        eg, when modifying a photo in any way, and when the selection changes.
        """
        self.button.gtk_apply.set_sensitive(len(self.selected) > 0)
        self.button.gtk_close.set_sensitive(len(self.selected) > 0)
        self.button.gtk_save.set_sensitive( len(self.modified) > 0)
        self.button.gtk_revert_to_saved.set_sensitive(
            len(self.modified & self.selected) > 0
        )
        
        gpx_sensitive = len(self.tracks) > 0
        for widget in self.offset.values() + [
            self.offset_label, self.button.gtk_clear ]:
            widget.set_sensitive(gpx_sensitive)
        
        if len(self.photo) > 0: self.photos_with_buttons.show()
        else:                   self.photos_with_buttons.hide()
    
    def main(self):
        """Go!"""
        Gtk.main()

################################################################################
# These data structures are used throughout GottenGeography
################################################################################

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
    
    def __init__(self, filename, thumb):
        """Initialize new Photograph object's attributes with default values."""
        self.filename = filename
        self.thumb    = thumb
        self.manual   = False
        for key in [ 'timestamp', 'altitude', 'latitude', 'longitude',
        'countryname', 'countrycode', 'provincestate', 'city',
        'marker', 'iter' ]:
            self[key] = None
    
    def position_marker(self):
        """Maintain correct position and visibility of ChamplainMarker."""
        if self.valid_coords():
            self.marker.set_position(self.latitude, self.longitude)
            self.marker.show()
        else:
            self.marker.hide()
    
    def cache_key(self):
        """Returns a string representing coarsely the area the photo is in."""
        return "%.2f,%.2f" % (self.latitude, self.longitude)
    
    def request_geoname(self, gui):
        """Use the GeoNames.org webservice to name coordinates."""
        if not self.valid_coords():
            return
        key = self.cache_key()
        if key in gui.geonames_cache:
            if gui.geonames_cache[key] is None:
                gui.geonames_queue[key].append(self)
            else:
                self.process_geoname(gui.geonames_cache[key], gui)
        else:
            gui.geonames_queue[key] = [self]
            gui.geonames_cache[key] = None
            gfile = Gio.file_new_for_uri(
                'http://ws.geonames.org/findNearbyJSON?lat=%s&lng=%s'
                % (self.latitude, self.longitude) +
                '&fclass=P&fcode=PPLA&fcode=PPL&fcode=PPLC&style=full')
            gfile.load_contents_async(None, self.receive_geoname, gui)
    
    def receive_geoname(self, gfile, result, gui):
        """This callback method is executed when geoname download completes."""
        key = self.cache_key()
        try:
            obj = json.loads(gfile.load_contents_finish(result)[1])['geonames']
        except:
            if key in gui.geonames_queue: del gui.geonames_queue[key]
            if key in gui.geonames_cache: del gui.geonames_cache[key]
            return
        geoname = {}
        for data in obj:
            geoname.update(data)
        gui.geonames_cache[key] = geoname
        while len(gui.geonames_queue[key]) > 0:
            photo = gui.geonames_queue[key].pop()
            photo.process_geoname(geoname, gui)
    
    def process_geoname(self, geoname, gui):
        """Insert geonames into the photo and update the GtkListStore."""
        for geocode, iptc in gui.geonames_of_interest.items():
            self[iptc.lower()] = geoname.get(geocode)
        self.timezone = geoname['timezone']['timeZoneId']
        gui.modify_summary(self.filename)
    
    def valid_coords(self):
        """Check if this photograph contains valid coordinates."""
        if type(self.latitude)  not in (float, int): return False
        if type(self.longitude) not in (float, int): return False
        return abs(self.latitude) <= 90 and abs(self.longitude) <= 180
    
################################################################################
# Pretty string methods display internal data in a human-readable way.
################################################################################
    
    def pretty_time(self):
        """Convert epoch seconds to a human-readable date."""
        return _("No timestamp") if type(self.timestamp) is not int else \
            time.strftime("%Y-%m-%d %X", time.localtime(self.timestamp))
    
    def pretty_coords(self):
        """Add cardinal directions to decimal coordinates."""
        return _("Not geotagged") if not self.valid_coords() \
            else '%s %.5f, %s %.5f' % (
                _("N") if self.latitude  >= 0 else _("S"), abs(self.latitude),
                _("E") if self.longitude >= 0 else _("W"), abs(self.longitude)
            )
    
    def pretty_geoname(self):
        """Display city, state, and country, if present."""
        names, length = [], 0
        for value in [ self.city, self.provincestate, self.countryname ]:
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
        return (LONG_SUMMARY % (
            os.path.basename(self.filename),
            self.short_summary()
        )).encode('utf-8')

################################################################################
# Strings section. Various strings that were too obnoxiously large to fit
# nicely into the actual code above, so they've been extracted here.
################################################################################

LONG_SUMMARY = """<span size="larger">%s</span>
<span style="italic" size="smaller">%s</span>"""

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

if __name__ == "__main__": GottenGeography().main()
