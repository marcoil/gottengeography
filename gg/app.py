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

APPNAME = "GottenGeography"
VERSION = "0.5a"

import os
import re
import time
import gettext

gettext.bindtextdomain(APPNAME.lower())
gettext.textdomain(APPNAME.lower())

from gi.repository import GtkClutter, Clutter, GtkChamplain, Champlain
from gi.repository import Gtk, GObject, Gdk, GdkPixbuf, GConf
from gettext import gettext as _

# "If I have seen a little further it is by standing on the shoulders of Giants."
#                                    --- Isaac Newton

from datatypes import *
from gps import *

PACKAGE_DIR = os.path.dirname(__file__)

class GottenGeography:
    """Provides a graphical interface to automagically geotag photos.
    
    Just load your photos, and load a GPX file, and GottenGeography will
    automatically cross-reference the timestamps on the photos to the timestamps
    in the GPX to determine the three-dimensional coordinates of each photo.
    """
    
################################################################################
# Map navigation section. These methods move and zoom the map around.
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
            if button is not False:
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
        """Move the map view by 5% of its length in the given direction."""
        x = self.map_view.get_width()  / 2
        y = self.map_view.get_height() / 2
        key = Gdk.keyval_name(keyval)
        if   key == "Left":  x *= 0.9
        elif key == "Up":    y *= 0.9
        elif key == "Right": x *= 1.1
        elif key == "Down":  y *= 1.1
        status, lat, lon = self.map_view.get_coords_at(int(x), int(y))
        if valid_coords(lat, lon):
            self.map_view.center_on(lat, lon)
    
################################################################################
# Map features section. These methods control map objects.
################################################################################
    
    def display_actors(self, stage=None, parameter=None):
        """Position and update my custom ClutterActors.
        
        self.actors.coords:       Map center coordinates at top of map view.
        self.actors.coords_bg:    Translucent white bar at top of map view.
        self.actors.crosshair:    Black diamond at map center.
        
        This method is called whenever the size of the map view changes, and
        whenever the map center coordinates change, so that everything is
        always positioned and sized correctly, and displaying the correct
        coordinates.
        """
        stage_width  = self.stage.get_width()
        stage_height = self.stage.get_height()
        self.actors.crosshair.set_position(
            (stage_width  - self.actors.crosshair.get_width())  / 2,
            (stage_height - self.actors.crosshair.get_height()) / 2
        )
        
        if stage is not None:
            lat   = self.map_view.get_property('latitude')
            lon   = self.map_view.get_property('longitude')
            label = self.actors.coords
            white = self.actors.coords_bg
            label.set_markup(format_coords(lat, lon))
            white.set_size(stage_width, label.get_height() + 10)
            label.set_position((stage_width - label.get_width()) / 2, 5)
            self.builder.get_object("maps_link").set_markup(maps_link(lat, lon))
    
    def marker_clicked(self, marker, event):
        """When a ChamplainMarker is clicked, select it in the GtkListStore.
        
        The interface defined by this method is consistent with the behavior of
        the GtkListStore itself in the sense that a normal click will select
        just one item, but Ctrl+clicking allows you to select multiple.
        """
        photo = self.photo[marker.get_name()]
        if (Clutter.ModifierType.CONTROL_MASK |
            Clutter.ModifierType.MOD2_MASK      == event.get_state()):
            if marker.get_highlighted(): self.listsel.unselect_iter(photo.iter)
            else:                        self.listsel.select_iter(photo.iter)
        else:
            self.builder.get_object("select_all_button").set_active(False)
            self.listsel.unselect_all()
            self.listsel.select_iter(photo.iter)
    
    def marker_mouse_in(self, marker, event):
        """Enlarge a hovered-over ChamplainMarker by 5%."""
        marker.set_scale(*[marker.get_scale()[0] * 1.05] * 2)
    
    def marker_mouse_out(self, marker, event):
        """Reduce a no-longer-hovered ChamplainMarker to it's original size."""
        marker.set_scale(*[marker.get_scale()[0] / 1.05] * 2)
    
    def update_all_marker_highlights(self, sel):
        """Ensure only the selected markers are highlighted."""
        selection_exists = sel.count_selected_rows() > 0
        self.selected = set()
        for photo in self.photo.values():
            photo.set_marker_highlight(None, selection_exists)
            # Maintain self.selected for easy iterating.
            if sel.iter_is_selected(photo.iter):
                self.selected.add(photo)
        # Highlight and center the map view over the selected photos.
        if selection_exists:
            area = [ float('inf') ] * 2 + [ float('-inf') ] * 2
            for photo in self.selected:
                photo.set_marker_highlight(area, False)
            if valid_coords(area[0], area[1]):
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
    
    def track_color_changed(self, selection):
        """Update the color of any loaded GPX tracks."""
        color = selection.get_current_color()
        track_color.red   = color.red   / 256
        track_color.green = color.green / 256
        track_color.blue  = color.blue  / 256
        track_color_alt   = track_color.lighten().lighten()
        polygons = self.polygons[:]
        while len(polygons) > 0:
            polygons.pop().set_stroke_color(track_color_alt
                if len(polygons) % 2 else   track_color)
        self.gconf_set("track_red",   track_color.red)
        self.gconf_set("track_green", track_color.green)
        self.gconf_set("track_blue",  track_color.blue)
    
    def lookup_tz_changed(self, radio):
        """Control whether to lookup GPX timezones when preferences change."""
        self.lookup_timezone = 1 if radio.get_active() else 0
        self.gconf_set("lookup_timezone", self.lookup_timezone)
        if self.lookup_timezone:
            self.cache.request_geoname(self.gpx[-1])
        else:
            self.handle_gpx_timezone(self.system_timezone)
    
    def clear_all_gpx(self, widget=None):
        """Forget all GPX data, start over with a clean slate."""
        for polygon in self.polygons:
            polygon.hide()
            # Maybe some day...
            #polygon.clear_points()
            #self.map_view.remove_polygon(polygon)
        
        self.gpx       = []
        self.polygons  = []
        self.tracks    = {}
        self.metadata  = {
            'delta': 0,                  # Time offset
            'omega': float('-inf'),      # Final GPX track point
            'alpha': float('inf') }      # Initial GPX track point
        self.update_sensitivity()
    
################################################################################
# File data handling. These methods interact with files (loading, saving, etc)
################################################################################
    
    def open_files(self, files):
        """Attempt to load all of the specified files."""
        self.progressbar.show()
        invalid_files, total = [], len(files)
        while len(files) > 0:
            filename = files.pop()
            self.redraw_interface(1 - len(files) / total,
                os.path.basename(filename))
            # Assume the file is an image; if that fails, assume it's GPX;
            # if that fails, show an error
            try:
                try:            self.add_or_reload_photo(filename)
                except IOError: self.load_gpx_from_file(filename)
            except IOError:
                invalid_files.append(os.path.basename(filename))
        if len(invalid_files) > 0:
            self.status_message(_("Could not open: %s") %
                ", ".join(invalid_files))
        self.progressbar.hide()
        self.update_sensitivity()
        self.update_all_marker_highlights(self.listsel)
    
    def add_or_reload_photo(self, filename):
        """Create or update a row in the ListStore.
        
        Checks if the file has already been loaded, and if not, creates a new
        row in the ListStore. Either way, it then populates that row with
        photo metadata as read from disk. Effectively, this is used both for
        loading new photos, and reverting old photos, discarding any changes.
        
        Raises IOError if filename refers to a file that is not a photograph.
        """
        photo = Photograph(filename, self.cache, self.modify_summary)
        photo.update( {
            'iter':   self.liststore.append([None] * 4),
            'marker': self.add_marker(filename)
        } if filename not in self.photo else {
            'iter':   self.photo[filename].iter,
            'marker': self.photo[filename].marker
        } )
        
        photo.position_marker()
        self.modified.discard(photo)
        self.photo[filename] = photo
        self.liststore.set_value(photo.iter, self.PATH,      photo.filename)
        self.liststore.set_value(photo.iter, self.THUMB,     photo.thumb)
        self.liststore.set_value(photo.iter, self.TIMESTAMP, photo.timestamp)
        self.liststore.set_value(photo.iter, self.SUMMARY,   photo.long_summary())
        self.auto_timestamp_comparison(photo)
        self.update_sensitivity()
    
    def load_gpx_from_file(self, filename):
        """Parse GPX data, drawing each GPS track segment on the map."""
        self.remember_location()
        start_points = len(self.tracks)
        start_time   = time.clock()
        
        gpx = GPXLoader(filename, self.map_view, self.progressbar,
            self.handle_gpx_timezone)
        self.tracks.update(gpx.tracks)
        self.gpx.append(gpx)
        self.polygons.extend(gpx.polygons)
        
        self.metadata['alpha'] = min(self.metadata['alpha'], gpx.alpha)
        self.metadata['omega'] = max(self.metadata['omega'], gpx.omega)
        
        self.update_sensitivity()
        self.status_message(_("%d points loaded in %.2fs.") %
            (len(self.tracks) - start_points, time.clock() - start_time))
        if len(gpx.tracks) > 0:
            self.map_view.ensure_visible(*gpx.area + [False])
        if self.lookup_timezone:
            self.cache.request_geoname(gpx)
        for photo in self.photo.values():
            self.auto_timestamp_comparison(photo)
    
    def save_all_files(self, widget=None):
        """Ensure all loaded files are saved."""
        self.progressbar.show()
        total, key = len(self.modified), 'Exif.GPSInfo.GPS'
        for photo in self.modified.copy():
            self.redraw_interface(1 - len(self.modified) / total,
                os.path.basename(photo.filename))
            exif = photo.exif
            if photo.altitude is not None:
                exif[key + 'Altitude']    = float_to_rational(photo.altitude)
                exif[key + 'AltitudeRef'] = '0' if photo.altitude >= 0 else '1'
            exif[key + 'Latitude']     = decimal_to_dms(photo.latitude)
            exif[key + 'LatitudeRef']  = "N" if photo.latitude >= 0 else "S"
            exif[key + 'Longitude']    = decimal_to_dms(photo.longitude)
            exif[key + 'LongitudeRef'] = "E" if photo.longitude >= 0 else "W"
            exif[key + 'MapDatum']     = 'WGS-84'
            for iptc in geonames_of_interest.values():
                if photo[iptc] is not None:
                    exif['Iptc.Application2.' + iptc] = [photo[iptc]]
            try:
                exif.write()
            except Exception as inst:
                self.status_message(", ".join(inst.args))
            else:
                self.modified.discard(photo)
                self.liststore.set_value(photo.iter, self.SUMMARY,
                    photo.long_summary())
        self.update_sensitivity()
        self.progressbar.hide()
    
################################################################################
# Data manipulation. These methods modify the loaded files in some way.
################################################################################
    
    def auto_timestamp_comparison(self, photo):
        """Use GPX data to calculate photo coordinates and elevation."""
        if photo.manual or len(self.tracks) < 2:
            return
        timestamp = photo.timestamp + self.metadata['delta']
        # Chronological first and last timestamp created by the GPX device.
        hi = self.metadata['omega']
        lo = self.metadata['alpha']
        # If the photo is out of range, simply peg it to the end of the range.
        timestamp = min(max(timestamp, lo), hi)
        try:
            lat = self.tracks[timestamp]['point'].lat
            lon = self.tracks[timestamp]['point'].lon
            ele = self.tracks[timestamp]['elevation']
        except KeyError:
            # Iterate over the available gpx points, find the two that are
            # nearest (in time) to the photo timestamp.
            for point in self.tracks:
                if point > timestamp: hi = min(point, hi)
                if point < timestamp: lo = max(point, lo)
            delta = hi - lo    # in seconds
            # lo_perc and hi_perc are ratios (between 0 and 1) representing the
            # proportional amount of time between the photo and the points.
            hi_perc = (timestamp - lo) / delta
            lo_perc = (hi - timestamp) / delta
            # Find intermediate values using the proportional ratios.
            lat = ((self.tracks[lo]['point'].lat * lo_perc)  +
                   (self.tracks[hi]['point'].lat * hi_perc))
            lon = ((self.tracks[lo]['point'].lon * lo_perc)  +
                   (self.tracks[hi]['point'].lon * hi_perc))
            ele = ((self.tracks[lo]['elevation'] * lo_perc)  +
                   (self.tracks[hi]['elevation'] * hi_perc))
        photo.set_location(lat, lon, ele)
    
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
            for photo in self.photo.values():
                self.auto_timestamp_comparison(photo)
        for spinbutton in self.offset.values():
            spinbutton.handler_unblock_by_func(self.time_offset_changed)
    
    def apply_selected_photos(self, button=None):
        """Manually apply map center coordinates to all selected photos."""
        for photo in self.selected:
            photo.manual = True
            photo.set_location(
                self.map_view.get_property('latitude'),
                self.map_view.get_property('longitude'))
        self.update_sensitivity()
    
    def revert_selected_photos(self, button=None):
        """Discard any modifications to all selected photos."""
        self.progressbar.show()
        mod_in_sel = self.modified & self.selected
        total = len(mod_in_sel)
        while len(mod_in_sel) > 0:
            photo = mod_in_sel.pop()
            self.redraw_interface(1 - len(mod_in_sel) / total,
                os.path.basename(photo.filename))
            self.add_or_reload_photo(photo.filename)
        self.progressbar.hide()
        self.update_sensitivity()
        self.update_all_marker_highlights(self.listsel)
    
    def close_selected_photos(self, button=None):
        """Discard all selected photos."""
        for photo in self.selected.copy():
            photo.marker.destroy()
            self.liststore.remove(photo.iter)
            self.modified.discard(photo)
            del self.photo[photo.filename]
        self.builder.get_object("select_all_button").set_active(False)
        self.update_sensitivity()
    
    def handle_gpx_timezone(self, timezone):
        """Recalculate photo timestamps when correct timezone is discovered."""
        os.environ["TZ"] = timezone
        for photo in self.photo.values():
            photo.calculate_timestamp()
            self.auto_timestamp_comparison(photo)
    
    def modify_summary(self, photo):
        """Insert the current photo summary into the liststore."""
        self.modified.add(photo)
        self.liststore.set_value(photo.iter, self.SUMMARY,
            ('<b>%s</b>' % photo.long_summary()))
    
################################################################################
# Dialogs. Various dialog-related methods for user interaction.
################################################################################
    
    def update_preview(self, chooser):
        """Display photo thumbnail and geotag data in file chooser."""
        label = self.builder.get_object("preview_label")
        label.set_label(self.strings.preview)
        image = self.builder.get_object("preview_image")
        image.set_from_stock(Gtk.STOCK_FILE, Gtk.IconSize.DIALOG)
        try:
            photo = Photograph(chooser.get_preview_filename(), self.cache, self.modify_summary, 300)
        except IOError:
            return
        image.set_from_pixbuf(photo.thumb)
        label.set_label("%s\n%s" % (photo.short_summary(), photo.maps_link()))
    
    def add_files_dialog(self, widget=None, data=None):
        """Display a file chooser, and attempt to load chosen files."""
        chooser = self.builder.get_object("open")
        response = chooser.run()
        chooser.hide()
        if response == Gtk.ResponseType.OK:
            self.open_files(chooser.get_filenames())
    
    def preferences_dialog(self, widget=None, event=None):
        """Allow the user to configure this application."""
        colorpicker  = self.builder.get_object("colorselection")
        radio_lookup = self.builder.get_object("lookup_timezone")
        radio_system = self.builder.get_object("use_system_time")
        previous     = ReadableDictionary({
            'lookup': radio_lookup.get_active(),
            'color':  Gdk.Color(
                track_color.red   * 256,
                track_color.green * 256,
                track_color.blue  * 256
            )
        })
        colorpicker.set_current_color(previous.color)
        colorpicker.set_previous_color(previous.color)
        dialog = self.builder.get_object("preferences")
        if not dialog.run():
            colorpicker.set_current_color(previous.color)
            colorpicker.set_previous_color(previous.color)
            radio_lookup.set_active(previous.lookup)
            radio_system.set_active(not previous.lookup)
        dialog.hide()
    
    def confirm_quit_dialog(self, widget=None, event=None):
        """Teardown method, inform user of unsaved files, if any."""
        self.remember_location_with_gconf()
        # If there's no unsaved data, just close without confirmation.
        if len(self.modified) == 0:
            Gtk.main_quit()
            return True
        dialog = self.builder.get_object("quit")
        dialog.format_secondary_markup(self.strings.quit % len(self.modified))
        response = dialog.run()
        dialog.hide()
        self.redraw_interface()
        if response == Gtk.ResponseType.ACCEPT: self.save_all_files()
        if response <> Gtk.ResponseType.CANCEL: Gtk.main_quit()
        return True
    
    def about_dialog(self, widget=None, data=None):
        """Describe this application to the user."""
        dialog = self.builder.get_object("about")
        dialog.run()
        dialog.hide()
    
################################################################################
# Initialization and Gtk boilerplate/housekeeping type stuff and such.
################################################################################
    
    def __init__(self, animate_crosshair=True):
        self.actors   = ReadableDictionary()
        self.cache    = GeoCache()
        self.selected = set()
        self.modified = set()
        self.polygons = []
        self.history  = []
        self.photo    = {}
        self.gpx      = []
        
        GtkClutter.init([])
        self.champlain       = GtkChamplain.Embed()
        self.map_photo_layer = Champlain.Layer()
        self.map_view        = self.champlain.get_view()
        self.map_view.add_layer(self.map_photo_layer)
        self.map_view.set_property('show-scale', True)
        self.map_view.set_scroll_mode(Champlain.ScrollMode.KINETIC)
        for signal in [ 'height', 'width', 'latitude', 'longitude' ]:
            self.map_view.connect('notify::%s' % signal, self.display_actors)
        
        self.stage = self.map_view.get_stage()
        self.actors.coords_bg = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(255, 255, 255, 164))
        self.actors.coords_bg.set_position(0, 0)
        self.actors.coords = Clutter.Text()
        self.actors.coords.set_single_line_mode(True)
        self.actors.crosshair = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(0, 0, 0, 32))
        self.actors.crosshair.set_property('has-border', True)
        self.actors.crosshair.set_border_color(Clutter.Color.new(0, 0, 0, 128))
        self.actors.crosshair.set_border_width(1)
        for actor in self.actors.values():
            actor.set_parent(self.stage)
            actor.raise_top()
            actor.show()
        
        self.system_timezone = os.environ["TZ"]
        
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(APPNAME.lower())
        self.builder.add_from_file("%s/%s" % (PACKAGE_DIR, "ui.glade"))
        
        self.progressbar = self.builder.get_object("progressbar")
        
        self.strings = ReadableDictionary({
            "quit":    self.builder.get_object("quit").get_property('secondary-text'),
            "preview": self.builder.get_object("preview_label").get_text()
        })
        
        self.offset = ReadableDictionary({
            "hours":   self.builder.get_object("hours"),
            "minutes": self.builder.get_object("minutes"),
            "seconds": self.builder.get_object("seconds")
        })
        for spinbutton in self.offset.values():
            spinbutton.connect("value-changed", self.time_offset_changed)
        self.builder.get_object("colorselection").connect(
            "color-changed", self.track_color_changed)
        self.builder.get_object("open").connect(
            "update-preview", self.update_preview)
        
        # Handy names for the following GtkListStore column numbers.
        self.PATH, self.SUMMARY, self.THUMB, self.TIMESTAMP = range(4)
        self.liststore = Gtk.ListStore(GObject.TYPE_STRING,
            GObject.TYPE_STRING, GdkPixbuf.Pixbuf, GObject.TYPE_INT)
        self.liststore.set_sort_column_id(self.TIMESTAMP,
            Gtk.SortType.ASCENDING)
        
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
        
        self.photos_view = Gtk.TreeView(model=self.liststore)
        self.photos_view.set_enable_search(False)
        self.photos_view.set_reorderable(False)
        self.photos_view.set_headers_visible(False)
        self.photos_view.set_rubber_banding(True)
        self.photos_view.append_column(self.column)
        
        self.listsel = self.photos_view.get_selection()
        self.listsel.set_mode(Gtk.SelectionMode.MULTIPLE)
        self.listsel.connect("changed", self.update_all_marker_highlights)
        self.listsel.connect("changed", self.update_sensitivity)
        
        self.builder.get_object("photoscroller").add(self.photos_view)
        self.builder.get_object("photos_and_map").pack_start(self.champlain, True, True, 0)
        
        self.gconf_client = GConf.Client.get_default()
        self.return_to_last(False)
        
        click_handlers = {
            "open_button":       self.add_files_dialog,
            "save_button":       self.save_all_files,
            "clear_button":      self.clear_all_gpx,
            "close_button":      self.close_selected_photos,
            "revert_button":     self.revert_selected_photos,
            "zoom_out_button":   self.zoom_out,
            "zoom_in_button":    self.zoom_in,
            "back_button":       self.return_to_last,
            "about_button":      self.about_dialog,
            "pref_button":       self.preferences_dialog,
            "apply_button":      self.apply_selected_photos,
            "select_all_button": self.toggle_selected_photos
        }
        for button, handler in click_handlers.items():
            self.builder.get_object(button).connect("clicked", handler)
        
        accel  = Gtk.AccelGroup()
        window = self.builder.get_object("main")
        window.connect("delete_event", self.confirm_quit_dialog)
        window.add_accel_group(accel)
        window.show_all()
        for key in [ 'Left', 'Right', 'Up', 'Down' ]:
            accel.connect(Gdk.keyval_from_name(key),
                Gdk.ModifierType.MOD1_MASK, 0, self.move_map_view_by_arrow_keys)
        
        self.clear_all_gpx()
        self.redraw_interface()
        self.zoom_button_sensitivity()
        self.display_actors(self.stage)
        
        track_color.red   = self.gconf_get("track_red",   int)
        track_color.green = self.gconf_get("track_green", int)
        track_color.blue  = self.gconf_get("track_blue",  int)
        
        self.lookup_timezone = self.gconf_get("lookup_timezone", int)
        radio_lookup = self.builder.get_object("lookup_timezone")
        radio_system = self.builder.get_object("use_system_time")
        if self.lookup_timezone: radio_lookup.set_active(True)
        else:                    radio_system.set_active(True)
        radio_lookup.connect("toggled", self.lookup_tz_changed)
        
        if not animate_crosshair:
            return
        
        # This causes the crosshair to start off huge and invisible, and it
        # quickly shrinks, spins, and fades into existence. The last value for
        # i before it stops will be 8, so: 53-i ends at 45 degrees, and
        # 260-(0.51*i) ends at 255 or full opacity. The numbers come from
        # simplifying the formula ((508-i)/500) * 255.
        xhair = self.actors.crosshair
        for i in range(200, 7, -1):
            xhair.set_size(i, i)
            xhair.set_z_rotation_from_gravity(53-i, Clutter.Gravity.CENTER)
            xhair.set_property('opacity', int(260-(0.51*i)))
            self.display_actors()
            self.redraw_interface()
            time.sleep(0.002)
    
    def toggle_selected_photos(self, button=None):
        """Toggle the selection of photos."""
        if button is None:
            # User typed Ctrl+a, so select all!
            button = self.builder.get_object("select_all_button")
            button.set_active(True)
        if button.get_active(): self.listsel.select_all()
        else:                   self.listsel.unselect_all()
    
    def gconf_set(self, key, value):
        """Sets the given GConf key to the given value."""
        key = gconf_key(key)
        if   type(value) is float: self.gconf_client.set_float(key, value)
        elif type(value) is int:   self.gconf_client.set_int(key, value)
    
    def gconf_get(self, key, type):
        """Gets the given GConf key as the requested type."""
        key = gconf_key(key)
        if   type is float: return self.gconf_client.get_float(key)
        elif type is int:   return self.gconf_client.get_int(key)
    
    def status_message(self, message):
        """Display a message on the GtkStatusBar."""
        status = self.builder.get_object("status")
        status.push(status.get_context_id("msg"), message)
        print message
    
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
        self.builder.get_object("zoom_out_button").set_sensitive(
            self.map_view.get_min_zoom_level() is not zoom_level)
        self.builder.get_object("zoom_in_button").set_sensitive(
            self.map_view.get_max_zoom_level() is not zoom_level)
    
    def update_sensitivity(self, selection=None):
        """Ensure widgets are sensitive only when they need to be.
        
        This method should be called every time any program state changes,
        eg, when modifying a photo in any way, and when the selection changes.
        """
        self.builder.get_object("apply_button").set_sensitive(len(self.selected) > 0)
        self.builder.get_object("close_button").set_sensitive(len(self.selected) > 0)
        self.builder.get_object("save_button").set_sensitive( len(self.modified) > 0)
        self.builder.get_object("revert_button").set_sensitive(
            len(self.modified & self.selected) > 0)
        gpx_sensitive = len(self.tracks) > 0
        for widget in self.offset.values() + [
        self.builder.get_object("offset_label"),
        self.builder.get_object("clear_button") ]:
            widget.set_sensitive(gpx_sensitive)
        left = self.builder.get_object("photos_with_buttons")
        if len(self.photo) > 0: left.show()
        else:                   left.hide()
    
    def main(self):
        """Go!"""
        Gtk.main()

def gconf_key(key):
    """Determine appropriate GConf key that is unique to this application."""
    return "/".join(['', 'apps', APPNAME.lower(), key])

