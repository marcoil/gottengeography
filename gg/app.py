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

from version import APPNAME, PACKAGE
from build_info import PKG_DATA_DIR, REVISION

import gettext
gettext.bindtextdomain(PACKAGE)
gettext.textdomain(PACKAGE)

from gi.repository import GLib, GObject, GtkClutter

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

# If I have seen a little further it is by standing on the shoulders of Giants.
#                                    --- Isaac Newton

from camera import Camera
from photos import Photograph, fetch_thumbnail
from xmlfiles import TrackFile, GPXFile, KMLFile, clear_all_gpx
from common import Struct, Widgets, gst, map_view
from common import selected, modified
from actor import animate_in

from drag import DragController
from search import SearchController
from navigation import NavigationController

# Handy names for GtkListStore column numbers.
PATH, SUMMARY, THUMB, TIMESTAMP = range(4)

CONTROL_MASK = Gdk.ModifierType.CONTROL_MASK
SHIFT_MASK = Gdk.ModifierType.SHIFT_MASK

selection = Widgets.photos_view.get_selection()


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
                try:
                    self.load_img_from_file(name)
                except IOError:
                    self.load_gpx_from_file(name)
            except IOError:
                invalid.append(basename(name))
        if len(invalid) > 0:
            self.status_message(_('Could not open: ') + ', '.join(invalid))
        
        # Ensure camera has found correct timezone regardless of the order
        # that the GPX/KML files were loaded in.
        Camera.timezone_handler_all()
        self.progressbar.hide()
        selection.emit('changed')
        map_view.emit('animation-completed')
    
    def load_img_from_file(self, uri):
        """Create or update a row in the ListStore.
        
        Checks if the file has already been loaded, and if not, creates a new
        row in the ListStore. Either way, it then populates that row with
        photo metadata as read from disk. Effectively, this is used both for
        loading new photos, and reverting old photos, discarding any changes.
        
        Raises IOError if filename refers to a file that is not a photograph.
        """
        photo = Photograph(uri)
        photo.read()
        
        Widgets.empty_camera_list.hide()
        
        camera_id = Camera.generate_id(photo.camera_info)
        camera = Camera.get(camera_id, photo.camera_info)
        camera.add_photo(photo)
        
        # If the user has selected the lookup method, then the timestamp
        # was probably calculated incorrectly the first time (before the
        # timezone was discovered). So call it again to get the correct value.
        if camera.timezone_method == 'lookup':
            photo.calculate_timestamp(camera.offset)
        
        modified.discard(photo)
        Widgets.apply_button.set_sensitive(True)
    
    def load_gpx_from_file(self, uri):
        """Parse GPX data, drawing each GPS track segment on the map."""
        start_time = clock()
        
        gpx = (GPXFile if uri.lower().endswith('gpx') else KMLFile)(uri)
        
        self.status_message(_('%d points loaded in %.2fs.') %
            (len(gpx.tracks), clock() - start_time), True)
        
        if len(gpx.tracks) < 2:
            return
        
        map_view.emit('realize')
        map_view.set_zoom_level(map_view.get_max_zoom_level())
        map_view.ensure_visible(TrackFile.get_bounding_box(), False)
        
        TrackFile.update_range()
        Camera.set_all_found_timezone(gpx.timezone)
    
    def apply_selected_photos(self, button):
        """Manually apply map center coordinates to all unpositioned photos."""
        for photo in Photograph.instances.values():
            if photo.manual:
                continue
            photo.manual = True
            photo.set_location(
                map_view.get_property('latitude'),
                map_view.get_property('longitude'))
        selection.emit('changed')
        Widgets.apply_button.set_sensitive(False)
    
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
        self.progressbar.hide()
        selection.emit('changed')
    
    def jump_to_photo(self, button):
        """Center on the first selected photo."""
        photo = selected.copy().pop()
        if photo.valid_coords():
            map_view.emit('realize')
            map_view.center_on(photo.latitude, photo.longitude)
    
################################################################################
# Dialogs. Various dialog-related methods for user interaction.
################################################################################
    
    def update_preview(self, chooser, image):
        """Display photo thumbnail and geotag data in file chooser."""
        image.set_from_stock(Gtk.STOCK_FILE, Gtk.IconSize.DIALOG)
        try:
            image.set_from_pixbuf(fetch_thumbnail(
                chooser.get_preview_filename(), 300))
        except IOError:
            return
        except TypeError:
            return
    
    def add_files_dialog(self, button, chooser):
        """Display a file chooser, and attempt to load chosen files."""
        response = chooser.run()
        chooser.hide()
        if response == Gtk.ResponseType.OK:
            self.open_files(chooser.get_filenames())
    
    def confirm_quit_dialog(self, *ignore):
        """Teardown method, inform user of unsaved files, if any."""
        if len(modified) == 0:
            Gtk.main_quit()
            return True
        dialog = Widgets.quit
        dialog.format_secondary_markup(self.strings.quit % len(modified))
        response = dialog.run()
        dialog.hide()
        self.redraw_interface()
        if response == Gtk.ResponseType.ACCEPT:
            self.save_all_files()
        if response != Gtk.ResponseType.CANCEL:
            Gtk.main_quit()
        return True
    
################################################################################
# Initialization and Gtk boilerplate/housekeeping type stuff and such.
################################################################################
    
    def __init__(self):
        self.message_timeout_source = None
        self.progressbar = Widgets.progressbar
        
        self.error = Struct({
            'message': Widgets.error_message,
            'icon': Widgets.error_icon,
            'bar': Widgets.error_bar
        })
        
        self.error.bar.connect('response', lambda widget, signal: widget.hide())
        
        self.strings = Struct({
            'quit':    Widgets.quit.get_property('secondary-text'),
        })
        
        self.liststore = Widgets.loaded_photos
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
        
        # Deal with multiple selection drag and drop.
        self.defer_select = False
        photos_view = Widgets.photos_view
        photos_view.connect('button-press-event', self.photoview_pressed)
        photos_view.connect('button-release-event', self.photoview_released)
        photos_view.append_column(column)
        
        self.drag      = DragController(self.open_files)
        self.navigator = NavigationController()
        self.search    = SearchController()
        
        about = Widgets.about
        about.set_version(REVISION)
        about.set_program_name(APPNAME)
        about.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(
            join(PKG_DATA_DIR, PACKAGE + '.svg'), 192, 192))
        
        click_handlers = {
            'open_button':
                [self.add_files_dialog, Widgets.open],
            'save_button':
                [self.save_all_files],
            'close_button':
                [lambda btn: [p.destroy() for p in selected.copy()]],
            'revert_button':
                [lambda btn: self.open_files(
                    [p.filename for p in modified & selected])],
            'about_button':
                [lambda yes, you_can: you_can.run() and you_can.hide(), about],
            'help_button':
                [lambda *ignore: Gtk.show_uri(Gdk.Screen.get_default(),
                    'ghelp:gottengeography', Gdk.CURRENT_TIME)],
            'jump_button':
                [self.jump_to_photo],
            'apply_button':
                [self.apply_selected_photos],
        }
        for button, handler in click_handlers.items():
            Widgets[button].connect('clicked', *handler)
        
        # Hide the unused button that appears beside the map source menu.
        ugly = Widgets.map_source_menu_button.get_child().get_children()[0]
        ugly.set_no_show_all(True)
        ugly.hide()
        
        accel  = Gtk.AccelGroup()
        window = Widgets.main
        window.resize(*gst.get('window-size'))
        window.connect('delete_event', self.confirm_quit_dialog)
        window.add_accel_group(accel)
        window.show_all()
        
        save_size = lambda v, s, size: gst.set_window_size(size())
        for prop in ['width', 'height']:
            map_view.connect('notify::' + prop, save_size, window.get_size)
        
        accel.connect(Gdk.keyval_from_name('q'),
            Gdk.ModifierType.CONTROL_MASK, 0, self.confirm_quit_dialog)
        
        selection.emit('changed')
        clear_all_gpx()
        
        gst.bind('left-pane-page', Widgets.photo_camera_gps, 'page')
        gst.bind('use-dark-theme', Gtk.Settings.get_default(),
                 'gtk-application-prefer-dark-theme')
        
        placeholder = Widgets.empty_photo_list
        toolbar = Widgets.photo_btn_bar
        
        def photo_pane_visibility(liststore, *ignore):
            """Hide the placeholder and show the toolbar when appropriate."""
            empty = liststore.get_iter_first() is None
            placeholder.set_visible(empty)
            toolbar.set_visible(not empty)
        
        self.liststore.connect('row-changed', photo_pane_visibility)
        self.liststore.connect('row-deleted', photo_pane_visibility)
        
        Widgets.open.connect('update-preview', self.update_preview,
            Widgets.preview)
    
    def redraw_interface(self, fraction=None, text=None):
        """Tell Gtk to redraw the user interface, so it doesn't look hung.
        
        Primarily used to update the progressbar, but also for disappearing
        some dialogs while things are processing in the background. Won't
        modify the progressbar if called with no arguments.
        """
        if fraction is not None:
            self.progressbar.set_fraction(fraction)
        if text is not None:
            self.progressbar.set_text(str(text))
        while Gtk.events_pending():
            Gtk.main_iteration()
    
    def dismiss_message(self):
        """Responsible for hiding the GtkInfoBar after a timeout."""
        self.message_timeout_source = None
        self.error.bar.hide()
        return False
    
    def status_message(self, message, info=False):
        """Display a message with the GtkInfoBar."""
        self.error.message.set_markup('<b>%s</b>' % message)
        self.error.bar.set_message_type(
            Gtk.MessageType.INFO if info else Gtk.MessageType.WARNING)
        self.error.icon.set_from_stock(
            Gtk.STOCK_DIALOG_INFO if info else Gtk.STOCK_DIALOG_WARNING, 6)
        self.error.bar.show()
        # Remove any previous message timeout
        if self.message_timeout_source is not None:
            GLib.source_remove(self.message_timeout_source)
        if info:
            self.message_timeout_source = \
                GLib.timeout_add_seconds(5, self.dismiss_message)
    
    # Multiple selection drag and drop copied from Kevin Mehall, adapted
    # to use it with the standard GtkTreeView.
    # http://blog.kevinmehall.net/2010/pygtk_multi_select_drag_drop
    def photoview_pressed(self, tree, event):
        """Allow the user to drag photos without losing the selection."""
        target = tree.get_path_at_pos(int(event.x), int(event.y))
        if (target and event.type == Gdk.EventType.BUTTON_PRESS
                   and not (event.state & (CONTROL_MASK|SHIFT_MASK))
                   and selection.path_is_selected(target[0])):
            # disable selection
            selection.set_select_function(lambda *ignore: False, None)
            self.defer_select = target[0]
     
    def photoview_released(self, tree, event):
        """Restore normal selection behavior while not dragging."""
        selection.set_select_function(lambda *ignore: True, None)
        target = tree.get_path_at_pos(int(event.x), int(event.y))
        if (target and self.defer_select
                   and self.defer_select == target[0]
                   and not (event.x == 0 and event.y == 0)): # certain drag&drop
            tree.set_cursor(target[0], target[1], False)
    
    def main(self, anim=True):
        """Animate the crosshair and begin user interaction."""
        if argv[1:]:
            self.open_files([abspath(f) for f in argv[1:]])
            anim = False
        animate_in(anim)
        Gtk.main()

