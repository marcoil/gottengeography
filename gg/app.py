# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Main application code that ties all the other modules together."""

from __future__ import division

from version import APPNAME, PACKAGE

import gettext
gettext.bindtextdomain(PACKAGE)
gettext.textdomain(PACKAGE)

from gi.repository import GLib, GObject, GtkClutter, Gtk, Gdk, Gio
from os.path import basename, abspath
from gettext import gettext as _
from time import clock

# If I have seen a little further it is by standing on the shoulders of Giants.
#                                    --- Isaac Newton

if not GLib.get_application_name():
    GLib.set_application_name(APPNAME)
    GObject.set_prgname(PACKAGE)

GtkClutter.init([])

from label import Label
from actor import animate_in
from widgets import Widgets, MapView
from camera import Camera, CameraView
from photos import Photograph, fetch_thumbnail
from navigation import go_back, move_by_arrow_keys
from xmlfiles import TrackFile, GPXFile, KMLFile
from common import Gst, selected, modified

from drag import DragController
from search import SearchController

# Handy names for GtkListStore column numbers.
PATH, SUMMARY, THUMB, TIMESTAMP = range(4)

CONTROL_MASK = Gdk.ModifierType.CONTROL_MASK
SHIFT_MASK = Gdk.ModifierType.SHIFT_MASK

# Just pretend these functions are actually GottenGeography() instance methods.
# The 'self' argument gets passed in by GtkApplication instead of Python.

def command_line(self, commands):
    """Open the files passed in at the commandline.
    
    This method collects any commandline arguments from any invocation of
    GottenGeography and reports them to the primary instance for opening.
    """
    files = commands.get_arguments()[1:]
    if files:
        self.activate()
        self.open_files([abspath(f) for f in files])
    return 0

def startup(self):
    """Display the primary window and connect some signals."""
    self.quit_message = Widgets.quit.get_property('secondary-text')
    
    self.drag   = DragController(self.open_files)
    self.search = SearchController()
    
    screen = Gdk.Screen.get_default()
    
    click_handlers = {
        'open':
            [self.add_files_dialog, Widgets.open],
        'save':
            [self.save_all_files],
        'close':
            [lambda btn: [p.destroy() for p in selected.copy()]],
        'revert':
            [lambda btn: self.open_files(
                [p.filename for p in modified & selected])],
        'about':
            [lambda yes, you_can: you_can.run() and you_can.hide(),
                Widgets.about],
        'help':
            [lambda *ignore: Gtk.show_uri(screen,
                'ghelp:gottengeography', Gdk.CURRENT_TIME)],
        'jump':
            [self.jump_to_photo],
        'apply':
            [self.apply_selected_photos],
        'map_source_menu':
            [lambda *ignore: Gtk.show_uri(
                screen, 'http://maps.google.com/maps?q=%s,%s' % (
                MapView.get_center_latitude(),
                MapView.get_center_longitude()),
                Gdk.CURRENT_TIME)],
    }
    for button, handler in click_handlers.items():
        Widgets[button + '_button'].connect('clicked', *handler)
    
    Widgets.zoom_in_button.connect('clicked', lambda *x: MapView.zoom_in())
    Widgets.zoom_out_button.connect('clicked', lambda *x: MapView.zoom_out())
    Widgets.back_button.connect('clicked', go_back)
    
    # Deal with multiple selection drag and drop.
    Widgets.photos_view.connect('button-press-event', self.photoview_pressed)
    Widgets.photos_view.connect('button-release-event', self.photoview_released)
    
    Widgets.open.connect('update-preview', self.update_preview, Widgets.preview)
    
    accel  = Gtk.AccelGroup()
    accel.connect(Gdk.keyval_from_name('q'),
        Gdk.ModifierType.CONTROL_MASK, 0, self.confirm_quit_dialog)
    for key in [ 'Left', 'Right', 'Up', 'Down' ]:
        accel.connect(Gdk.keyval_from_name(key),
            Gdk.ModifierType.MOD1_MASK, 0, move_by_arrow_keys)
    
    Widgets.main.add_accel_group(accel)
    Widgets.main.connect('delete_event', self.confirm_quit_dialog)
    self.add_window(Widgets.main)
    
    save_size = lambda v, s, size: Gst.set_window_size(size())
    for prop in ['width', 'height']:
        MapView.connect('notify::' + prop, save_size, Widgets.main.get_size)
    
    Widgets.photos_selection.emit('changed')
    
    Gst.connect('changed::thumbnail-size', Photograph.resize_all_photos)
    
    Widgets.launch()
    animate_in(self.do_fade_in)


class GottenGeography(Gtk.Application):
    """Provides a graphical interface to automagically geotag photos.
    
    Just load your photos, and load a GPX file, and GottenGeography will
    automatically cross-reference the timestamps on the photos to the timestamps
    in the GPX to determine the three-dimensional coordinates of each photo.
    """
    message_timeout_source = None
    defer_select = False
    
    def __init__(self, do_fade_in=True):
        Gtk.Application.__init__(
            self, application_id='ca.exolucere.' + APPNAME,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        
        self.connect('activate', lambda *ignore: Widgets.main.present())
        self.connect('command-line', command_line)
        self.connect('startup', startup)
        
        self.do_fade_in = do_fade_in
    
    def open_files(self, files):
        """Attempt to load all of the specified files."""
        Widgets.progressbar.show()
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
        likely_zone = TrackFile.query_all_timezones()
        if likely_zone:
            Camera.set_all_found_timezone(likely_zone)
        Camera.timezone_handler_all()
        Widgets.progressbar.hide()
        Widgets.photos_selection.emit('changed')
    
    def load_img_from_file(self, uri):
        """Create or update a row in the ListStore.
        
        Checks if the file has already been loaded, and if not, creates a new
        row in the ListStore. Either way, it then populates that row with
        photo metadata as read from disk. Effectively, this is used both for
        loading new photos, and reverting old photos, discarding any changes.
        
        Raises IOError if filename refers to a file that is not a photograph.
        """
        photo = Photograph(uri)
        modified.discard(photo)
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
        
        Widgets.apply_button.set_sensitive(True)
    
    def load_gpx_from_file(self, uri):
        """Parse GPX data, drawing each GPS track segment on the map."""
        start_time = clock()
        
        gpx = (GPXFile if uri.lower().endswith('gpx') else KMLFile)(uri)
        
        self.status_message(_('%d points loaded in %.2fs.') %
            (len(gpx.tracks), clock() - start_time), True)
        
        if len(gpx.tracks) < 2:
            return
        
        MapView.emit('realize')
        MapView.set_zoom_level(MapView.get_max_zoom_level())
        MapView.ensure_visible(TrackFile.get_bounding_box(), False)
        
        TrackFile.update_range()
        Camera.set_all_found_timezone(gpx.start.geotimezone)
    
    def apply_selected_photos(self, button):
        """Manually apply map center coordinates to all unpositioned photos."""
        for photo in Photograph.files:
            if photo.manual:
                continue
            photo.disable_auto_position()
            photo.set_location(
                MapView.get_property('latitude'),
                MapView.get_property('longitude'))
        Widgets.photos_selection.emit('changed')
        Widgets.apply_button.set_sensitive(False)
    
    def save_all_files(self, widget=None):
        """Ensure all loaded files are saved."""
        Widgets.progressbar.show()
        total = len(modified)
        for i, photo in enumerate(list(modified), 1):
            self.redraw_interface(i / total, basename(photo.filename))
            try:
                photo.write()
            except Exception as inst:
                self.status_message(str(inst))
        Widgets.progressbar.hide()
        Widgets.photos_selection.emit('changed')
    
    def jump_to_photo(self, button):
        """Center on the first selected photo."""
        photo = selected.copy().pop()
        if photo.positioned:
            MapView.emit('realize')
            MapView.center_on(photo.latitude, photo.longitude)
    
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
        if not modified:
            self.quit()
            return True
        Widgets.quit.format_secondary_markup(self.quit_message % len(modified))
        response = Widgets.quit.run()
        Widgets.quit.hide()
        self.redraw_interface()
        if response == Gtk.ResponseType.ACCEPT:
            self.save_all_files()
        if response != Gtk.ResponseType.CANCEL:
            self.quit()
        return True
    
    def redraw_interface(self, fraction=None, text=None):
        """Tell Gtk to redraw the user interface, so it doesn't look hung.
        
        Primarily used to update the progressbar, but also for disappearing
        some dialogs while things are processing in the background. Won't
        modify the progressbar if called with no arguments.
        """
        if fraction is not None:
            Widgets.progressbar.set_fraction(fraction)
        if text is not None:
            Widgets.progressbar.set_text(str(text))
        while Gtk.events_pending():
            Gtk.main_iteration()
    
    def dismiss_message(self):
        """Responsible for hiding the GtkInfoBar after a timeout."""
        self.message_timeout_source = None
        Widgets.error_bar.hide()
        return False
    
    def status_message(self, message, info=False):
        """Display a message with the GtkInfoBar."""
        Widgets.error_message.set_markup('<b>%s</b>' % message)
        Widgets.error_bar.set_message_type(
            Gtk.MessageType.INFO if info else Gtk.MessageType.WARNING)
        Widgets.error_icon.set_from_stock(
            Gtk.STOCK_DIALOG_INFO if info else Gtk.STOCK_DIALOG_WARNING, 6)
        Widgets.error_bar.show()
        
        # Remove any previous message timeout
        if self.message_timeout_source is not None:
            GLib.source_remove(self.message_timeout_source)
        if info:
            self.message_timeout_source = \
                GLib.timeout_add_seconds(10, self.dismiss_message)
    
    # Multiple selection drag and drop copied from Kevin Mehall, adapted
    # to use it with the standard GtkTreeView.
    # http://blog.kevinmehall.net/2010/pygtk_multi_select_drag_drop
    def photoview_pressed(self, tree, event):
        """Allow the user to drag photos without losing the selection."""
        target = tree.get_path_at_pos(int(event.x), int(event.y))
        if (target and event.type == Gdk.EventType.BUTTON_PRESS
                   and not (event.state & (CONTROL_MASK|SHIFT_MASK))
                   and Widgets.photos_selection.path_is_selected(target[0])):
            # disable selection
            Widgets.photos_selection.set_select_function(
                lambda *ignore: False, None)
            self.defer_select = target[0]
     
    def photoview_released(self, tree, event):
        """Restore normal selection behavior while not dragging."""
        Widgets.photos_selection.set_select_function(lambda *ignore: True, None)
        target = tree.get_path_at_pos(int(event.x), int(event.y))
        if (target and self.defer_select
                   and self.defer_select == target[0]
                   and not (event.x == 0 and event.y == 0)): # certain drag&drop
            tree.set_cursor(target[0], target[1], False)

