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

# If I have seen a little further it is by standing on the shoulders of Giants.
#                                    --- Isaac Newton

if not GLib.get_application_name():
    GLib.set_application_name(APPNAME)
    GObject.set_prgname(PACKAGE)

GtkClutter.init([])

from camera import Camera
from actor import animate_in
from xmlfiles import TrackFile
from gpsmath import Coordinates
from widgets import Widgets, MapView
from photos import Photograph, fetch_thumbnail
from navigation import go_back, move_by_arrow_keys
from common import Gst, Binding, selected, modified

from drag import DragController
from search import SearchController

# Handy names for GtkListStore column numbers.
PATH, SUMMARY, THUMB, TIMESTAMP = range(4)

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
            [self.add_files_dialog],
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
    
    Widgets.open.connect('update-preview', self.update_preview, Widgets.preview)
    
    actions = {'open': self.add_files_dialog,
               'quit': self.confirm_quit_dialog}
    
    for name in actions:
        action = Gio.SimpleAction(name=name)
        action.connect('activate', actions[name])
        self.add_action(action)
    self.set_app_menu(Widgets.appmenu)
    
    accel = Gtk.AccelGroup()
    for key in [ 'Left', 'Right', 'Up', 'Down' ]:
        accel.connect(Gdk.keyval_from_name(key),
            Gdk.ModifierType.MOD1_MASK, 0, move_by_arrow_keys)
    
    Widgets.main.add_accel_group(accel)
    Widgets.main.connect('delete_event', self.confirm_quit_dialog)
    self.add_window(Widgets.main)
    
    save_size = lambda v, s, size: Gst.set_window_size(size())
    for prop in ['width', 'height']:
        MapView.connect('notify::' + prop, save_size, Widgets.main.get_size)
    
    Widgets.button_sensitivity()
    
    Gst.connect('changed::thumbnail-size', Photograph.resize_all_photos)
    
    center = Coordinates()
    Binding(MapView, 'latitude', center)
    Binding(MapView, 'longitude', center)
    center.do_modified()
    Binding(center, 'geoname', Widgets.main, 'title')
    center.timeout_seconds = 10 # Only update titlebar every 10 seconds
    
    Widgets.launch()
    animate_in(self.do_fade_in)


class GottenGeography(Gtk.Application):
    """Provides a graphical interface to automagically geotag photos.
    
    Just load your photos, and load a GPX file, and GottenGeography will
    automatically cross-reference the timestamps on the photos to the timestamps
    in the GPX to determine the three-dimensional coordinates of each photo.
    """
    
    def __init__(self, do_fade_in=True):
        Gtk.Application.__init__(
            self, application_id='ca.exolucere.' + APPNAME,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        
        self.connect('activate', lambda *ignore: Widgets.main.present())
        self.connect('command-line', command_line)
        self.connect('startup', startup)
        
        self.do_fade_in = do_fade_in
    
    def open_files(self, files):
        """Attempt to load all of the specified files.
        
        >>> len(Photograph.instances)
        0
        >>> GottenGeography().open_files(
        ...     ['demo/IMG_2411.JPG', 'demo/IMG_2412.JPG'])
        >>> len(Photograph.instances)
        2
        """
        Widgets.progressbar.show()
        invalid, total = [], len(files)
        for i, name in enumerate(files, 1):
            Widgets.redraw_interface(i / total, basename(name))
            try:
                try:
                    Photograph.load_from_file(name)
                except IOError:
                    TrackFile.load_from_file(name)
            except IOError:
                invalid.append(basename(name))
        if invalid:
            Widgets.status_message(_('Could not open: ') + ', '.join(invalid))
        
        # Ensure camera has found correct timezone regardless of the order
        # that the GPX/KML files were loaded in.
        likely_zone = TrackFile.query_all_timezones()
        if likely_zone:
            Camera.set_all_found_timezone(likely_zone)
        Camera.timezone_handler_all()
        Widgets.progressbar.hide()
        Widgets.button_sensitivity()
    
    def apply_selected_photos(self, button):
        """Manually apply map center coordinates to selected photos."""
        lat, lon = MapView.get_center_latitude(), MapView.get_center_longitude()
        for photo in selected:
            photo.manual = True
            photo.set_location(lat, lon)
        Widgets.button_sensitivity()
    
    def save_all_files(self, widget=None):
        """Ensure all loaded files are saved."""
        Widgets.progressbar.show()
        total = len(modified)
        for i, photo in enumerate(list(modified), 1):
            Widgets.redraw_interface(i / total, basename(photo.filename))
            try:
                photo.write()
            except Exception as inst:
                Widgets.status_message(str(inst))
        Widgets.progressbar.hide()
        Widgets.button_sensitivity()
    
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
        except (IOError, TypeError):
            return
    
    def add_files_dialog(self, *ignore):
        """Display a file chooser, and attempt to load chosen files."""
        response = Widgets.open.run()
        Widgets.open.hide()
        Widgets.redraw_interface()
        if response == Gtk.ResponseType.OK:
            self.open_files(Widgets.open.get_filenames())
    
    def confirm_quit_dialog(self, *ignore):
        """Teardown method, inform user of unsaved files, if any."""
        if not modified:
            self.quit()
            return True
        Widgets.quit.format_secondary_markup(self.quit_message % len(modified))
        response = Widgets.quit.run()
        Widgets.quit.hide()
        Widgets.redraw_interface()
        if response == Gtk.ResponseType.ACCEPT:
            self.save_all_files()
        if response != Gtk.ResponseType.CANCEL:
            self.quit()
        return True

