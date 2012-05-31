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

# "If I have seen a little further it is by standing on the shoulders of Giants."
#                                    --- Isaac Newton

from photos import Photograph
from camera import known_cameras
from common import points, photos
from common import metadata, selected, modified
from common import Struct, get_obj, gst, map_view
from xmlfiles import clear_all_gpx, get_trackfile, known_trackfiles

from drag import DragController
from actor import ActorController
from label import LabelController
from search import SearchController
from navigation import NavigationController

# Handy names for GtkListStore column numbers.
PATH, SUMMARY, THUMB, TIMESTAMP = range(4)


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
        get_obj('empty_camera_list').hide()
    
    def load_gpx_from_file(self, uri):
        """Parse GPX data, drawing each GPS track segment on the map."""
        start_time = clock()
        
        gpx = get_trackfile(uri)
        
        self.status_message(_('%d points loaded in %.2fs.') %
            (len(gpx.tracks), clock() - start_time), True)
        
        if len(gpx.tracks) < 2:
            return
        
        metadata.alpha = min(metadata.alpha, gpx.alpha)
        metadata.omega = max(metadata.omega, gpx.omega)
        
        map_view.emit('realize')
        map_view.set_zoom_level(map_view.get_max_zoom_level())
        bounds = Champlain.BoundingBox.new()
        for trackfile in known_trackfiles.values():
            for polygon in trackfile.polygons:
                bounds.compose(polygon.get_bounding_box())
        map_view.ensure_visible(bounds, False)
        
        for camera in known_cameras.values():
            camera.set_found_timezone(gpx.timezone)
        
        get_obj('empty_trackfile_list').hide()
    
    def apply_selected_photos(self, button):
        """Manually apply map center coordinates to all unpositioned photos."""
        for photo in photos.values():
            if photo.manual:
                continue
            photo.manual = True
            photo.set_location(
                map_view.get_property('latitude'),
                map_view.get_property('longitude'))
        self.labels.selection.emit('changed')
    
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
        self.message_timeout_source = None
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
        self.labels    = LabelController()
        self.actors    = ActorController()
        
        about = get_obj('about')
        about.set_version(REVISION)
        about.set_program_name(APPNAME)
        about.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(
            join(PKG_DATA_DIR, PACKAGE + '.svg'), 192, 192))
        
        click_handlers = {
            'open_button':
                [self.add_files_dialog, get_obj('open')],
            'save_button':
                [self.save_all_files],
            'close_button':
                [lambda btn: [p.destroy() for p in selected.copy()]],
            'revert_button':
                [lambda btn: self.open_files(
                    [p.filename for p in modified & selected])],
            'about_button':
                [lambda yes, you_can: you_can.run() and you_can.hide(), about],
            'apply_button':
                [self.apply_selected_photos],
        }
        for button, handler in click_handlers.items():
            get_obj(button).connect('clicked', *handler)
        
        # Deal with multiple selection drag and drop.
        self.defer_select = False
        get_obj('photos_view').connect('button-press-event', self.photoview_pressed)
        get_obj('photos_view').connect('button-release-event', self.photoview_released)
        
        gst.bind('use-dark-theme', Gtk.Settings.get_default(),
                 'gtk-application-prefer-dark-theme')
        
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
        
        button = get_obj('apply_button')
        gst.bind('left-pane-page', get_obj('photo_camera_gps'), 'page')
        gst.bind('show-buttons', button, 'visible')
        button.set_visible(False)
        
        # This bit of magic will only show the apply button when there is
        # at least one photo loaded that is not manually positioned.
        # In effect, it allows you to manually drag & drop some photos,
        # then batch-apply all the rest
        btn_visible = lambda *x: button.set_visible(
            [photo for photo in photos.values() if not photo.manual])
        self.liststore.connect('row-changed', btn_visible, button)
        self.liststore.connect('row-deleted', btn_visible, button)
        
        empty = get_obj('empty_photo_list')
        empty_visible = lambda l, *x: empty.set_visible(l.get_iter_first() is None)
        self.liststore.connect('row-changed', empty_visible)
        self.liststore.connect('row-deleted', empty_visible)
        
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
    
    def dismiss_message(self):
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
        target = tree.get_path_at_pos(int(event.x), int(event.y))
        if (target
            and event.type == Gdk.EventType.BUTTON_PRESS
            and not (event.state & (Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.SHIFT_MASK))
            and tree.get_selection().path_is_selected(target[0])):
                # disable selection
                tree.get_selection().set_select_function(lambda *ignore: False, None)
                self.defer_select = target[0]
     
    def photoview_released(self, tree, event):
        # re-enable selection
        tree.get_selection().set_select_function(lambda *ignore: True, None)
        
        target = tree.get_path_at_pos(int(event.x), int(event.y))
        if (self.defer_select and target
            and self.defer_select == target[0]
            and not (event.x == 0 and event.y == 0)): # certain drag and drop
                tree.set_cursor(target[0], target[1], False)
    
    def main(self, anim=True):
        """Animate the crosshair and begin user interaction."""
        if argv[1:]:
            self.open_files([abspath(f) for f in argv[1:]])
            anim=False
        self.actors.animate_in(anim)
        Gtk.main()

