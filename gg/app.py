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
import pyexiv2

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
        
        self.coords:       Map center coordinates at top of map view.
        self.coords_bg:    Translucent white bar at top of map view.
        self.coords_label: Link to Google Maps in the status bar.
        self.crosshair:    Black diamond at map center.
        
        This method is called whenever the size of the map view changes, and
        whenever the map center coordinates change, so that everything is
        always positioned and sized correctly, and displaying the correct
        coordinates.
        """
        stage_width  = self.stage.get_width()
        stage_height = self.stage.get_height()
        self.crosshair.set_position(
            (stage_width  - self.crosshair.get_width())  / 2,
            (stage_height - self.crosshair.get_height()) / 2
        )
        
        if stage is not None:
            lat = self.map_view.get_property('latitude')
            lon = self.map_view.get_property('longitude')
            self.coords.set_markup("%.4f, %.4f" % (lat, lon))
            self.coords_label.set_markup(maps_link(lat, lon))
            self.coords_bg.set_size(stage_width, self.coords.get_height() + 10)
            self.coords.set_position(
                (stage_width - self.coords.get_width()) / 2, 5)
    
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
            self.button.gtk_select_all.set_active(False)
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
    
    def clear_all_gpx(self, widget=None):
        """Forget all GPX data, start over with a clean slate."""
        for gpx in self.gpx:
            for polygon in gpx.polygons:
                polygon.hide()
                # Maybe some day...
                #polygon.clear_points()
                #self.map_view.remove_polygon(polygon)
        
        self.gpx       = []
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
        photo = self.load_exif_from_file(filename)
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
    
    def load_exif_from_file(self, filename, thumb_size=200):
        """Read photo metadata from disk using the pyexiv2 module.
        
        Raises IOError if the specified file is not an image format supported by
        both pyexiv2 and GdkPixbuf. Known to work with JPG, PNG, DNG, and NEF.
        """
        gps = 'Exif.GPSInfo.GPS'
        try:
            exif = pyexiv2.ImageMetadata(filename)
            exif.read()
            thumb = GdkPixbuf.Pixbuf.new_from_file_at_size(
                filename, thumb_size, thumb_size)
            photo = Photograph(filename, thumb, exif,
                self.cache, self.modify_summary)
        except:
            raise IOError
        try:
            # This assumes that the camera and computer have the same timezone.
            photo.timestamp = int(time.mktime(
                exif['Exif.Photo.DateTimeOriginal'].value.timetuple()))
        except:
            photo.timestamp = int(os.stat(filename).st_mtime)
        try:
            photo.latitude = dms_to_decimal(
                *exif[gps + 'Latitude'].value +
                [exif[gps + 'LatitudeRef'].value]
            )
            photo.longitude = dms_to_decimal(
                *exif[gps + 'Longitude'].value +
                [exif[gps + 'LongitudeRef'].value]
            )
        except KeyError:
            pass
        try:
            photo.altitude = exif[gps + 'Altitude'].value.to_float()
            if int(exif[gps + 'AltitudeRef'].value) > 0:
                photo.altitude *= -1
        except:
            pass
        for iptc in geonames_of_interest.values():
            try:
                photo[iptc] = exif['Iptc.Application2.' + iptc].values[0]
            except KeyError:
                pass
        return photo
    
    def load_gpx_from_file(self, filename):
        """Parse GPX data, drawing each GPS track segment on the map."""
        self.remember_location()
        start_points = len(self.tracks)
        start_time   = time.clock()
        
        gpx = GPXLoader(self.map_view, self.progressbar, filename)
        self.tracks.update(gpx.tracks)
        self.gpx.append(gpx)
        
        self.metadata['alpha'] = min(self.metadata['alpha'], gpx.alpha)
        self.metadata['omega'] = max(self.metadata['omega'], gpx.omega)
        
        self.update_sensitivity()
        self.status_message(_("%d points loaded in %.2fs.") %
            (len(self.tracks) - start_points, time.clock() - start_time))
        if len(gpx.tracks) > 0:
            self.map_view.ensure_visible(*gpx.area + [False])
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
        self.button.gtk_select_all.set_active(False)
        self.update_sensitivity()
    
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
            photo = self.load_exif_from_file(chooser.get_preview_filename(), 300)
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
        self.strings  = ReadableDictionary()
        self.cache    = GeoCache()
        self.selected = set()
        self.modified = set()
        self.history  = []
        self.photo    = {}
        self.gpx      = []
        
        GtkClutter.init([])
        self.champlain = GtkChamplain.Embed()
        self.map_view = self.champlain.get_view()
        self.map_view.set_property('show-scale', True)
        self.map_view.set_scroll_mode(Champlain.ScrollMode.KINETIC)
        self.map_photo_layer = Champlain.Layer()
        self.map_view.add_layer(self.map_photo_layer)
        
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(APPNAME.lower())
        self.builder.add_from_file("%s/%s" % (PACKAGE_DIR, "ui.glade"))
        self.augment_gtk_builder()
        
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
        
        self.photo_scroller = Gtk.ScrolledWindow()
        self.photo_scroller.add(self.photos_view)
        self.photo_scroller.set_policy(Gtk.PolicyType.NEVER,
                                       Gtk.PolicyType.AUTOMATIC)
        
        self.button.gtk_apply = Gtk.Button.new_from_stock(Gtk.STOCK_APPLY)
        self.button.gtk_apply.set_tooltip_text(
            _("Place selected photos onto center of map (Ctrl+Return)"))
        self.button.gtk_apply.connect("clicked", self.apply_selected_photos)
        
        self.button.gtk_select_all = Gtk.ToggleButton(label=Gtk.STOCK_SELECT_ALL)
        self.button.gtk_select_all.set_use_stock(True)
        self.button.gtk_select_all.set_tooltip_text(
            _("Toggle whether all photos are selected (Ctrl+A)"))
        self.button.gtk_select_all.connect("clicked", self.toggle_selected_photos)
        
        self.photo_btn_bar = Gtk.HBox(spacing=12)
        self.photo_btn_bar.set_border_width(3)
        for btn in [ 'gtk_select_all', 'gtk_apply' ]:
            self.photo_btn_bar.pack_start(self.button[btn], True, True, 0)
        
        self.photos_with_buttons = Gtk.VBox()
        self.photos_with_buttons.pack_start(self.photo_scroller, True, True, 0)
        self.photos_with_buttons.pack_start(self.photo_btn_bar, False, False, 0)
        
        self.photos_and_map_container = Gtk.HPaned()
        self.photos_and_map_container.add1(self.photos_with_buttons)
        self.photos_and_map_container.add2(self.champlain)
        
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
        
        self.gconf_client = GConf.Client.get_default()
        self.return_to_last(False)
        
        # Key bindings
        self.key_actions = {
            "equal":    self.zoom_in,
            "minus":    self.zoom_out,
            "Left":     self.return_to_last,
            "Return":   self.apply_selected_photos,
            "w":        self.close_selected_photos,
            "a":        self.toggle_selected_photos,
            "z":        self.revert_selected_photos,
            "s":        self.save_all_files,
            "x":        self.clear_all_gpx,
            "o":        self.add_files_dialog,
            "q":        self.confirm_quit_dialog,
            "slash":    self.about_dialog,
            "question": self.about_dialog
        }
        accel = Gtk.AccelGroup()
        self.window.add_accel_group(accel)
        for key in self.key_actions.keys():
            accel.connect(Gdk.keyval_from_name(key),
                Gdk.ModifierType.CONTROL_MASK, 0, self.key_accel)
        
        for key in [ 'Left', 'Right', 'Up', 'Down' ]:
            accel.connect(Gdk.keyval_from_name(key),
                Gdk.ModifierType.MOD1_MASK, 0, self.move_map_view_by_arrow_keys)
        
        self.window.show_all()
        self.progressbar.hide()
        self.clear_all_gpx()
        self.redraw_interface()
        
        self.stage = self.map_view.get_stage()
        
        self.coords_bg = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(255, 255, 255, 164))
        self.coords_bg.set_position(0, 0)
        
        self.coords = Clutter.Text()
        self.coords.set_single_line_mode(True)
        
        self.crosshair = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(0, 0, 0, 32))
        self.crosshair.set_property('has-border', True)
        self.crosshair.set_border_color(Clutter.Color.new(0, 0, 0, 128))
        self.crosshair.set_border_width(1)
        
        for actor in [self.crosshair, self.coords, self.coords_bg]:
            actor.set_parent(self.stage)
            actor.raise_top()
            actor.show()
        
        self.zoom_button_sensitivity()
        self.display_actors(self.stage)
        
        for signal in [ 'height', 'width', 'latitude', 'longitude' ]:
            self.map_view.connect('notify::%s' % signal, self.display_actors)
        
        if not animate_crosshair:
            return
        
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
    
    def augment_gtk_builder(self):
        """Do some initializy stuff to objects constructed by GtkBuilder.
        
        I suspect that this method only exists because I'm using GtkBuilder
        poorly, but we'll see how it goes. YAY learning!"""
        quit = self.builder.get_object("quit")
        quit.add_buttons(
            _("Close _without Saving"), Gtk.ResponseType.CLOSE,
            Gtk.STOCK_CANCEL,           Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE,             Gtk.ResponseType.ACCEPT)
        quit.set_default_response(Gtk.ResponseType.ACCEPT)
        
        opendialog = self.builder.get_object("open")
        opendialog.connect("selection-changed", self.update_preview)
        opendialog.add_buttons(
            Gtk.STOCK_CANCEL,  Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,    Gtk.ResponseType.OK)
        opendialog.set_default_response(Gtk.ResponseType.OK)
        
        self.strings.quit    = quit.get_property('secondary-text')
        self.strings.preview = self.builder.get_object("preview_label").get_text()
    
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
        if label is not None:
            button.set_label(label)
        self.toolbar.add(button)
        self.button[re.sub(r'-', '_', stock_id)] = button
    
    def toggle_selected_photos(self, button=None):
        """Toggle the selection of photos."""
        if button is None:
            # User typed Ctrl+a, so select all!
            button = self.button.gtk_select_all
            button.set_active(True)
        if button.get_active(): self.listsel.select_all()
        else:                   self.listsel.unselect_all()
    
    def key_accel(self, accel_group, acceleratable, keyval, modifier):
        """Respond to keyboard shortcuts as typed by user."""
        self.key_actions[Gdk.keyval_name(keyval)]()
    
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
            len(self.modified & self.selected) > 0)
        gpx_sensitive = len(self.tracks) > 0
        for widget in self.offset.values() + [
            self.offset_label, self.button.gtk_clear ]:
            widget.set_sensitive(gpx_sensitive)
        if len(self.photo) > 0: self.photos_with_buttons.show()
        else:                   self.photos_with_buttons.hide()
    
    def main(self):
        """Go!"""
        Gtk.main()

def gconf_key(key):
    """Determine appropriate GConf key that is unique to this application."""
    return "/".join(['', 'apps', APPNAME.lower(), key])

