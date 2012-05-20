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

from version import APPNAME, PACKAGE, VERSION

import gettext
gettext.bindtextdomain(PACKAGE)
gettext.textdomain(PACKAGE)

from gi.repository import GObject, GtkClutter

GObject.threads_init()
GObject.set_prgname(PACKAGE)
GtkClutter.init([])

from gi.repository import Gtk, Gdk
from gi.repository import Champlain
from os.path import basename, abspath
from gettext import gettext as _
from time import clock
from sys import argv

# "If I have seen a little further it is by standing on the shoulders of Giants."
#                                    --- Isaac Newton

from common import get_obj, gst, map_view
from common import Struct, CommonAttributes
from common import auto_timestamp_comparison
from files import Photograph, GPXFile, KMLFile
from utils import format_list, format_coords
from utils import Coordinates, valid_coords

from drag import DragController
from actor import ActorController
from label import LabelController
from search import SearchController
from navigation import NavigationController
from preferences import PreferencesController

# Handy names for GtkListStore column numbers.
PATH, SUMMARY, THUMB, TIMESTAMP = range(4)

class GottenGeography(CommonAttributes):
    """Provides a graphical interface to automagically geotag photos.
    
    Just load your photos, and load a GPX file, and GottenGeography will
    automatically cross-reference the timestamps on the photos to the timestamps
    in the GPX to determine the three-dimensional coordinates of each photo.
    """
    
################################################################################
# File data handling. These methods interact with files (loading, saving, etc)
################################################################################
    
    def open_files(self, files):
        """Attempt to load all of the specified files."""
        self.progressbar.show()
        invalid_files, total = [], len(files)
        # abspath is used to correct relative paths entered on the commandline
        for i, name in enumerate([abspath(f) for f in files], 1):
            self.redraw_interface(i / total, basename(name))
            try:
                try:            self.load_img_from_file(name)
                except IOError: self.load_gpx_from_file(name)
            except IOError:
                invalid_files.append(basename(name))
        if len(invalid_files) > 0:
            self.status_message(_("Could not open: ") + format_list(invalid_files))
        self.progressbar.hide()
        self.labels.selection.emit("changed")
        map_view.emit("animation-completed")
    
    def load_img_from_file(self, filename):
        """Create or update a row in the ListStore.
        
        Checks if the file has already been loaded, and if not, creates a new
        row in the ListStore. Either way, it then populates that row with
        photo metadata as read from disk. Effectively, this is used both for
        loading new photos, and reverting old photos, discarding any changes.
        
        Raises IOError if filename refers to a file that is not a photograph.
        """
        photo = self.photo.get(filename) or Photograph(filename, self.modify_summary)
        photo.read()
        if filename not in self.photo:
            photo.iter           = self.liststore.append()
            photo.label          = self.labels.add(filename)
            self.photo[filename] = photo
        photo.position_label()
        self.modified.discard(photo)
        self.liststore.set_row(photo.iter,
            [filename, photo.long_summary(), photo.thumb, photo.timestamp])
        auto_timestamp_comparison(photo, self.tracks, self.metadata)
    
    def load_gpx_from_file(self, filename):
        """Parse GPX data, drawing each GPS track segment on the map."""
        start_time = clock()
        
        open_file = KMLFile if filename[-3:].lower() == 'kml' else GPXFile
        gpx = open_file(filename, self.progressbar, self.polygons)
        
        # Emitting this signal ensures the new tracks get the correct color.
        get_obj('colorselection').emit('color-changed')
        
        self.status_message(_("%d points loaded in %.2fs.") %
            (len(gpx.tracks), clock() - start_time))
        
        if len(gpx.tracks) < 2:
            return
        
        self.tracks.update(gpx.tracks)
        self.metadata.alpha = min(self.metadata.alpha, gpx.alpha)
        self.metadata.omega = max(self.metadata.omega, gpx.omega)
        
        map_view.emit("realize")
        map_view.set_zoom_level(map_view.get_max_zoom_level())
        bounds = Champlain.BoundingBox.new()
        for poly in self.polygons:
            bounds.compose(poly.get_bounding_box())
        gpx.latitude, gpx.longitude = bounds.get_center()
        map_view.ensure_visible(bounds, False)
        
        self.prefs.gpx_timezone = gpx.lookup_geoname()
        self.prefs.set_timezone()
        self.gpx_sensitivity()
    
    def apply_selected_photos(self, button, selected, view):
        """Manually apply map center coordinates to all selected photos."""
        for photo in selected:
            photo.manual = True
            photo.set_location(
                view.get_property('latitude'),
                view.get_property('longitude'))
        self.labels.selection.emit("changed")
    
    def revert_selected_photos(self, button=None):
        """Discard any modifications to all selected photos."""
        self.open_files([photo.filename for photo in self.modified & self.selected])
    
    def close_selected_photos(self, button=None):
        """Discard all selected photos."""
        for photo in self.selected.copy():
            self.labels.layer.remove_marker(photo.label)
            del self.photo[photo.filename]
            self.modified.discard(photo)
            self.liststore.remove(photo.iter)
        self.labels.select_all.set_active(False)
    
    def clear_all_gpx(self, widget=None):
        """Forget all GPX data, start over with a clean slate."""
        assert self.polygons is CommonAttributes.polygons
        assert self.metadata is CommonAttributes.metadata
        for polygon in self.polygons:
            map_view.remove_layer(polygon)
        
        del self.polygons[:]
        self.tracks.clear()
        self.metadata.omega = float('-inf')   # Final GPX track point
        self.metadata.alpha = float('inf')    # Initial GPX track point
        self.gpx_sensitivity()
    
    def save_all_files(self, widget=None):
        """Ensure all loaded files are saved."""
        self.progressbar.show()
        photos, total = list(self.modified), len(self.modified)
        for i, photo in enumerate(photos, 1):
            self.redraw_interface(i / total, basename(photo.filename))
            try:
                photo.write()
            except Exception as inst:
                self.status_message(str(inst))
            else:
                self.modified.discard(photo)
                self.liststore.set_value(photo.iter, SUMMARY,
                    photo.long_summary())
        self.progressbar.hide()
        self.labels.selection.emit("changed")
    
################################################################################
# Data manipulation. These methods modify the loaded files in some way.
################################################################################
    
    def time_offset_changed(self, widget):
        """Update all photos each time the camera's clock is corrected."""
        seconds = self.secbutton.get_value()
        minutes = self.minbutton.get_value()
        offset  = int((minutes * 60) + seconds)
        if offset != self.metadata.delta:
            self.metadata.delta = offset
            if abs(seconds) == 60 and abs(minutes) != 60:
                minutes += seconds / 60
                self.secbutton.set_value(0)
                self.minbutton.set_value(minutes)
            for photo in self.photo.values():
                auto_timestamp_comparison(photo, self.tracks, self.metadata)
    
    def modify_summary(self, photo):
        """Insert the current photo summary into the liststore."""
        self.modified.add(photo)
        self.liststore.set_value(photo.iter, SUMMARY,
            ('<b>%s</b>' % photo.long_summary()))
    
    def toggle_selected_photos(self, button, selection):
        """Toggle the selection of photos."""
        if button.get_active(): selection.select_all()
        else:                   selection.unselect_all()
    
################################################################################
# Dialogs. Various dialog-related methods for user interaction.
################################################################################
    
    def update_preview(self, chooser, label, image):
        """Display photo thumbnail and geotag data in file chooser."""
        label.set_label(self.strings.preview)
        image.set_from_stock(Gtk.STOCK_FILE, Gtk.IconSize.DIALOG)
        try:
            photo = Photograph(chooser.get_preview_filename(), lambda x: None, 300)
            photo.read()
        except IOError:
            return
        image.set_from_pixbuf(photo.thumb)
        label.set_label(format_list([photo.short_summary(), photo.maps_link()], "\n"))
    
    def add_files_dialog(self, button, chooser):
        """Display a file chooser, and attempt to load chosen files."""
        response = chooser.run()
        chooser.hide()
        if response == Gtk.ResponseType.OK:
            self.open_files(chooser.get_filenames())
    
    def confirm_quit_dialog(self, *args):
        """Teardown method, inform user of unsaved files, if any."""
        if len(self.modified) == 0:
            Gtk.main_quit()
            return True
        dialog = get_obj("quit")
        dialog.format_secondary_markup(self.strings.quit % len(self.modified))
        response = dialog.run()
        dialog.hide()
        self.redraw_interface()
        if response == Gtk.ResponseType.ACCEPT: self.save_all_files()
        if response != Gtk.ResponseType.CANCEL: Gtk.main_quit()
        return True
    
################################################################################
# Initialization and Gtk boilerplate/housekeeping type stuff and such.
################################################################################
    
    def __init__(self):
        self.progressbar = get_obj("progressbar")
        self.status      = get_obj("status")
        
        self.strings = Struct({
            "quit":    get_obj("quit").get_property('secondary-text'),
            "preview": get_obj("preview_label").get_text()
        })
        
        self.liststore = get_obj("loaded_photos")
        self.liststore.set_sort_column_id(TIMESTAMP, Gtk.SortType.ASCENDING)
        
        cell_string = Gtk.CellRendererText()
        cell_thumb  = Gtk.CellRendererPixbuf()
        cell_thumb.set_property('stock-id', Gtk.STOCK_MISSING_IMAGE)
        cell_thumb.set_property('ypad', 6)
        cell_thumb.set_property('xpad', 6)
        
        column = Gtk.TreeViewColumn('Photos')
        column.pack_start(cell_thumb, False)
        column.add_attribute(cell_thumb, 'pixbuf', THUMB)
        column.pack_start(cell_string, False)
        column.add_attribute(cell_string, 'markup', SUMMARY)
        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        
        get_obj("photos_view").append_column(column)
        
        self.drag      = DragController(self.open_files)
        self.navigator = NavigationController()
        self.search    = SearchController()
        self.prefs     = PreferencesController()
        self.labels    = LabelController()
        self.actors    = ActorController()
        
        about_dialog = get_obj("about")
        about_dialog.set_version(VERSION)
        about_dialog.set_program_name(APPNAME)
        
        click_handlers = {
            "open_button":       [self.add_files_dialog, get_obj("open")],
            "save_button":       [self.save_all_files],
            "clear_button":      [self.clear_all_gpx],
            "close_button":      [self.close_selected_photos],
            "revert_button":     [self.revert_selected_photos],
            "about_button":      [lambda b, d: d.run() and d.hide(), about_dialog],
            "apply_button":      [self.apply_selected_photos, self.selected, map_view],
            "select_all_button": [self.toggle_selected_photos, self.labels.selection]
        }
        for button, handler in click_handlers.items():
            get_obj(button).connect("clicked", *handler)
        
        accel  = Gtk.AccelGroup()
        window = get_obj("main")
        window.resize(*gst.get('window-size'))
        window.connect("delete_event", self.confirm_quit_dialog)
        window.add_accel_group(accel)
        window.show_all()
        
        save_size = lambda v,s,size: gst.set('window-size', size())
        for prop in ['width', 'height']:
            map_view.connect('notify::' + prop, save_size, window.get_size)
        
        map_source_button = get_obj("map_source_label").get_parent()
        if map_source_button:
            map_source_button.set_property("visible", False)
        
        accel.connect(Gdk.keyval_from_name("q"),
            Gdk.ModifierType.CONTROL_MASK, 0, self.confirm_quit_dialog)
        
        self.labels.selection.emit("changed")
        self.clear_all_gpx()
        
        self.metadata.delta = 0
        self.secbutton, self.minbutton = get_obj("seconds"), get_obj("minutes")
        gst.bind("offset-minutes", self.minbutton, "value")
        gst.bind("offset-seconds", self.secbutton, "value")
        for spinbutton in [ self.secbutton, self.minbutton ]:
            spinbutton.connect("value-changed", self.time_offset_changed)
        
        get_obj("open").connect("update-preview", self.update_preview,
            get_obj("preview_label"), get_obj("preview_image"))
    
    def gpx_sensitivity(self):
        """Control the sensitivity of GPX-related widgets."""
        gpx_sensitive = len(self.tracks) > 0
        get_obj('clear_button').set_sensitive(gpx_sensitive)
        for widget in [ 'minutes', 'seconds', 'offset_label' ]:
            get_obj(widget).set_visible(gpx_sensitive)
    
    def redraw_interface(self, fraction=None, text=None):
        """Tell Gtk to redraw the user interface, so it doesn't look hung.
        
        Primarily used to update the progressbar, but also for disappearing
        some dialogs while things are processing in the background. Won't
        modify the progressbar if called with no arguments.
        """
        if fraction is not None: self.progressbar.set_fraction(fraction)
        if text is not None:     self.progressbar.set_text(str(text))
        while Gtk.events_pending(): Gtk.main_iteration()
    
    def status_message(self, message):
        """Display a message on the GtkStatusBar."""
        self.status.push(self.status.get_context_id("msg"), message)
    
    def main(self, anim_start=400):
        """Animate the crosshair and begin user interaction."""
        if argv[1:]:
            self.open_files(argv[1:])
            anim_start = 10
        self.actors.animate_in(anim_start)
        Gtk.main()

