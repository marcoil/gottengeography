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

"""Main application code that ties all the other modules together."""

from __future__ import division

from version import APPNAME, PACKAGE, VERSION
from build_info import PKG_DATA_DIR, REVISION

import gettext
gettext.bindtextdomain(PACKAGE)
gettext.textdomain(PACKAGE)

from gi.repository import GObject, GtkClutter

GObject.threads_init()
GObject.set_prgname(PACKAGE)
GtkClutter.init([])

from gi.repository import Gtk, Gdk
from gi.repository import GdkPixbuf
from gi.repository import Champlain, Pango
from os.path import join, basename, abspath
from gettext import gettext as _
from time import clock
from sys import argv

# "If I have seen a little further it is by standing on the shoulders of Giants."
#                                    --- Isaac Newton

from photos import Photograph
from xmlfiles import get_trackfile
from common import polygons, points, photos
from common import metadata, selected, modified
from common import Struct, get_obj, gst, map_view
from common import gpx_sensitivity, clear_all_gpx

from drag import DragController
from actor import ActorController
from label import LabelController
from search import SearchController
from navigation import NavigationController
from preferences import PreferencesController
from camera import known_cameras

# Handy names for GtkListStore column numbers.
PATH, SUMMARY, THUMB, TIMESTAMP = range(4)

def toggle_selected_photos(button, sel):
    """Toggle the selection of photos."""
    (sel.select_all if button.get_active() else sel.unselect_all)()


class GottenGeography():
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
        invalid, total = [], len(files)
        for i, name in enumerate(files, 1):
            self.redraw_interface(i / total, basename(name))
            try:
                try:            self.load_img_from_file(name)
                except IOError: self.load_gpx_from_file(name)
            except IOError:
                invalid.append(basename(name))
        if len(invalid) > 0:
            self.status_message(_('Could not open: ') + ', '.join(invalid))
        
        # Ensure camera has found correct timezone regardless of the order
        # that the GPX/KML files were loaded in.
        for camera in known_cameras.values():
            camera.set_timezone()
        self.progressbar.hide()
        self.labels.selection.emit('changed')
        map_view.emit('animation-completed')
    
    def load_img_from_file(self, uri):
        """Create or update a row in the ListStore.
        
        Checks if the file has already been loaded, and if not, creates a new
        row in the ListStore. Either way, it then populates that row with
        photo metadata as read from disk. Effectively, this is used both for
        loading new photos, and reverting old photos, discarding any changes.
        
        Raises IOError if filename refers to a file that is not a photograph.
        """
        photo = photos.get(uri) or Photograph(uri, self.modify_summary)
        photo.read()
        if uri not in photos:
            photo.iter  = self.liststore.append()
            photo.label = self.labels.add(uri)
            photos[uri] = photo
        photo.calculate_timestamp()
        modified.discard(photo)
        self.liststore.set_row(photo.iter,
            [uri, photo.long_summary(), photo.thumb, photo.timestamp])
    
    def load_gpx_from_file(self, uri):
        """Parse GPX data, drawing each GPS track segment on the map."""
        start_time = clock()
        
        gpx = get_trackfile(uri)
        
        # Emitting this signal ensures the new tracks get the correct color.
        self.prefs.colorpicker.emit('color-set')
        
        self.status_message(_('%d points loaded in %.2fs.') %
            (len(gpx.tracks), clock() - start_time), True)
        
        if len(gpx.tracks) < 2:
            return
        
        points.update(gpx.tracks)
        metadata.alpha = min(metadata.alpha, gpx.alpha)
        metadata.omega = max(metadata.omega, gpx.omega)
        
        map_view.emit('realize')
        map_view.set_zoom_level(map_view.get_max_zoom_level())
        bounds = Champlain.BoundingBox.new()
        for poly in polygons:
            bounds.compose(poly.get_bounding_box())
        gpx.latitude, gpx.longitude = bounds.get_center()
        map_view.ensure_visible(bounds, False)
        
        for camera in known_cameras.values():
            camera.set_found_timezone(gpx.lookup_geoname())
        gpx_sensitivity()
    
    def apply_selected_photos(self, button, view):
        """Manually apply map center coordinates to all selected photos."""
        for photo in selected:
            photo.manual = True
            photo.set_location(
                view.get_property('latitude'),
                view.get_property('longitude'))
        self.labels.selection.emit('changed')
    
    def revert_selected_photos(self, button=None):
        """Discard any modifications to all selected photos."""
        self.open_files([photo.filename for photo in modified & selected])
    
    def close_selected_photos(self, button=None):
        """Discard all selected photos."""
        for photo in selected.copy():
            self.labels.layer.remove_marker(photo.label)
            photo.camera.photos.discard(photo)
            del photos[photo.filename]
            modified.discard(photo)
            self.liststore.remove(photo.iter)
        self.labels.select_all.set_active(False)
    
    def save_all_files(self, widget=None):
        """Ensure all loaded files are saved."""
        self.progressbar.show()
        total = len(modified)
        for i, photo in enumerate(list(modified), 1):
            self.redraw_interface(i / total, basename(photo.filename))
            try:
                photo.write()
            except Exception as inst:
                self.status_message(str(inst))
            else:
                modified.discard(photo)
                self.liststore.set_value(photo.iter, SUMMARY,
                    photo.long_summary())
        self.progressbar.hide()
        self.labels.selection.emit('changed')
    
################################################################################
# Data manipulation. These methods modify the loaded files in some way.
################################################################################
    
    def modify_summary(self, photo):
        """Insert the current photo summary into the liststore."""
        modified.add(photo)
        self.liststore.set_value(photo.iter, SUMMARY,
            ('<b>%s</b>' % photo.long_summary()))
    
################################################################################
# Dialogs. Various dialog-related methods for user interaction.
################################################################################
    
    def update_preview(self, chooser, label, image):
        """Display photo thumbnail and geotag data in file chooser."""
        label.set_label(self.strings.preview)
        image.set_from_stock(Gtk.STOCK_FILE, Gtk.IconSize.DIALOG)
        try:
            photo = Photograph(chooser.get_preview_filename(),
                               lambda x: None, 300)
            photo.read()
        except IOError:
            return
        image.set_from_pixbuf(photo.thumb)
        label.set_label(
            '\n'.join([photo.short_summary(), photo.maps_link()]))
    
    def add_files_dialog(self, button, chooser):
        """Display a file chooser, and attempt to load chosen files."""
        response = chooser.run()
        chooser.hide()
        if response == Gtk.ResponseType.OK:
            self.open_files(chooser.get_filenames())
    
    def confirm_quit_dialog(self, *args):
        """Teardown method, inform user of unsaved files, if any."""
        if len(modified) == 0:
            Gtk.main_quit()
            return True
        dialog = get_obj('quit')
        dialog.format_secondary_markup(self.strings.quit % len(modified))
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
        self.progressbar = get_obj('progressbar')
        
        self.error = Struct({
            'message': get_obj('error_message'),
            'icon': get_obj('error_icon'),
            'bar': get_obj('error_bar')
        })
        
        self.error.bar.connect('response', lambda widget, signal: widget.hide())
        
        self.strings = Struct({
            'quit':    get_obj('quit').get_property('secondary-text'),
            'preview': get_obj('preview_label').get_text()
        })
        
        self.liststore = get_obj('loaded_photos')
        self.liststore.set_sort_column_id(TIMESTAMP, Gtk.SortType.ASCENDING)
        
        cell_string = Gtk.CellRendererText()
        cell_string.set_property('wrap-mode', Pango.WrapMode.WORD)
        cell_string.set_property('wrap-width', 200)
        cell_thumb  = Gtk.CellRendererPixbuf()
        cell_thumb.set_property('stock-id', Gtk.STOCK_MISSING_IMAGE)
        cell_thumb.set_property('ypad', 6)
        cell_thumb.set_property('xpad', 12)
        
        column = Gtk.TreeViewColumn('Photos')
        column.pack_start(cell_thumb, False)
        column.add_attribute(cell_thumb, 'pixbuf', THUMB)
        column.pack_start(cell_string, False)
        column.add_attribute(cell_string, 'markup', SUMMARY)
        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        
        get_obj('photos_view').append_column(column)
        
        self.drag      = DragController(self.open_files)
        self.navigator = NavigationController()
        self.search    = SearchController()
        self.prefs     = PreferencesController()
        self.labels    = LabelController()
        self.actors    = ActorController()
        
        about = get_obj('about')
        about.set_version(REVISION)
        about.set_program_name(APPNAME)
        about.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(
            join(PKG_DATA_DIR, PACKAGE + '.svg'), 192, 192))
        
        click_handlers = {
            'open_button':       [self.add_files_dialog, get_obj('open')],
            'save_button':       [self.save_all_files],
            'clear_button':      [clear_all_gpx],
            'close_button':      [self.close_selected_photos],
            'revert_button':     [self.revert_selected_photos],
            'about_button':      [lambda b, d: d.run() and d.hide(), about],
            'apply_button':      [self.apply_selected_photos, map_view],
            'select_all_button': [toggle_selected_photos, self.labels.selection]
        }
        for button, handler in click_handlers.items():
            get_obj(button).connect('clicked', *handler)
        
        accel  = Gtk.AccelGroup()
        window = get_obj('main')
        window.resize(*gst.get('window-size'))
        window.connect('delete_event', self.confirm_quit_dialog)
        window.add_accel_group(accel)
        window.show_all()
        
        # Hide the unused button that appears beside the map source menu.
        get_obj('map_source_menu_button').get_child().get_children()[0].set_visible(False)
        
        save_size = lambda v, s, size: gst.set_window_size(size())
        for prop in ['width', 'height']:
            map_view.connect('notify::' + prop, save_size, window.get_size)
        
        accel.connect(Gdk.keyval_from_name('q'),
            Gdk.ModifierType.CONTROL_MASK, 0, self.confirm_quit_dialog)
        
        self.labels.selection.emit('changed')
        clear_all_gpx()
        
        gst.bind('left-pane-page', get_obj('photo_camera_gps'), 'page')
        gst.bind('show-buttons', get_obj('photo_btn_bar'), 'visible')
        
        get_obj('open').connect('update-preview', self.update_preview,
            get_obj('preview_label'), get_obj('preview_image'))
    
    def redraw_interface(self, fraction=None, text=None):
        """Tell Gtk to redraw the user interface, so it doesn't look hung.
        
        Primarily used to update the progressbar, but also for disappearing
        some dialogs while things are processing in the background. Won't
        modify the progressbar if called with no arguments.
        """
        if fraction is not None: self.progressbar.set_fraction(fraction)
        if text is not None:     self.progressbar.set_text(str(text))
        while Gtk.events_pending(): Gtk.main_iteration()
    
    def status_message(self, message, info=False):
        """Display a message with the GtkInfoBar."""
        self.error.message.set_markup('<b>%s</b>' % message)
        self.error.bar.set_message_type(
            Gtk.MessageType.INFO if info else Gtk.MessageType.WARNING)
        self.error.icon.set_from_stock(
            Gtk.STOCK_DIALOG_INFO if info else Gtk.STOCK_DIALOG_WARNING, 6)
        self.error.bar.show()
    
    def main(self, anim=True):
        """Animate the crosshair and begin user interaction."""
        if argv[1:]:
            self.open_files([abspath(f) for f in argv[1:]])
            anim=False
        self.actors.animate_in(anim)
        Gtk.main()

