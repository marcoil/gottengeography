# Author: Robert Park <rbpark@exolucere.ca>, (C) 2012
# Copyright: See COPYING file included with this distribution.

"""Orchestrate the construction of widgets with GtkBuilder."""

from gi.repository import GtkChamplain, Champlain
from gi.repository import Gdk, GdkPixbuf
from gi.repository import Gtk, GLib
from os.path import join

from version import APPNAME, PACKAGE
from build_info import PKG_DATA_DIR, REVISION
from common import Gst, singleton, memoize
from common import modified, selected

CONTROL_MASK = Gdk.ModifierType.CONTROL_MASK
SHIFT_MASK = Gdk.ModifierType.SHIFT_MASK


class Builder(Gtk.Builder):
    """Load GottenGeography's UI definitions."""
    def __init__(self, filename=PACKAGE):
        Gtk.Builder.__init__(self)
        
        self.set_translation_domain(PACKAGE)
        self.add_from_file(join(PKG_DATA_DIR, filename + '.ui'))
    
    @memoize
    def __getattr__(self, widget):
        """Make calls to Gtk.Builder().get_object() more pythonic.
        
        Here is a quick comparison of execution performance:
        
        Executing this method, no memoize:  6.50 microseconds
        Calling get_object directly:        4.35 microseconds
        Executing this method with memoize: 1.34 microseconds
        Accessing an instance attribute:    0.08 microseconds
        Accessing a local variable:         0.03 microseconds
        
        (averaged over a million executions with the timeit package)
        
        Considering that this method is 3 orders of magnitude slower than
        accessing variables, you should avoid it inside performance-critical
        inner loops, however thanks to memoization, it's faster than calling
        get_object() directly, so don't sweat it.
        """
        return self.get_object(widget)
    
    __getitem__ = __getattr__


@singleton
class Widgets(Builder):
    """Tweak the GtkBuilder results specifically for the main window."""
    message_timeout_source = None
    defer_select = False
    
    def __init__(self):
        Builder.__init__(self)
    
    def launch(self):
        """Do some things that GtkBuilder XML can't do.
        
        Ideally this method would not exist. If you see something here that
        can be done directly in the GtkBuilder XML, please let me know.
        """
        self.loaded_photos.set_sort_column_id(3, Gtk.SortType.ASCENDING)
        
        self.about.set_version(REVISION)
        self.about.set_program_name(APPNAME)
        self.about.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(
            join(PKG_DATA_DIR, PACKAGE + '.svg'), 192, 192))
        
        self.main.resize(*Gst.get('window-size'))
        self.main.show_all()
        
        Gst.bind('left-pane-page', self.photo_camera_gps, 'page')
        Gst.bind('use-dark-theme', Gtk.Settings.get_default(),
                 'gtk-application-prefer-dark-theme')
        
        placeholder = self.empty_photo_list
        toolbar = self.photo_btn_bar
        
        def photo_pane_visibility(liststore, *ignore):
            """Hide the placeholder and show the toolbar when appropriate."""
            empty = liststore.get_iter_first() is None
            placeholder.set_visible(empty)
            toolbar.set_visible(not empty)
        
        self.loaded_photos.connect('row-inserted', photo_pane_visibility)
        self.loaded_photos.connect('row-deleted', photo_pane_visibility)
        self.photos_view.connect('button-press-event', self.photoview_pressed)
        self.photos_view.connect('button-release-event', self.photoview_released)
        self.photos_selection.connect('changed', self.update_highlights)
        self.photos_selection.connect('changed', self.button_sensitivity)
        
        self.error_bar.connect('response',
            lambda widget, signal: widget.hide())
    
    def update_highlights(self, selection):
        """Ensure only the selected labels are highlighted."""
        selection_exists = selection.count_selected_rows() > 0
        selected.clear()
        for label in MarkerLayer.get_markers():
            photo = label.photo
            itr = photo.iter
            if itr and selection.iter_is_selected(itr):
                selected.add(photo)
            label.set_highlight(photo in selected, selection_exists)
    
    def button_sensitivity(self, *ignore):
        """Control the sensitivity of various widgets."""
        self.close_button.set_sensitive(selected)
        self.apply_button.set_sensitive(selected)
        self.save_button.set_sensitive(modified)
        self.revert_button.set_sensitive(modified & selected)
        self.jump_button.set_sensitive(
            [photo for photo in selected if photo.positioned])
    
    # Multiple selection drag and drop copied from Kevin Mehall, adapted
    # to use it with the standard GtkTreeView.
    # http://blog.kevinmehall.net/2010/pygtk_multi_select_drag_drop
    def photoview_pressed(self, tree, event):
        """Allow drag & drop with multiple photos selected."""
        target = tree.get_path_at_pos(int(event.x), int(event.y))
        if (target and event.type == Gdk.EventType.BUTTON_PRESS
                   and not (event.state & (CONTROL_MASK|SHIFT_MASK))
                   and self.photos_selection.path_is_selected(target[0])):
            # disable selection
            self.photos_selection.set_select_function(
                lambda *ignore: False, None)
            self.defer_select = target[0]
     
    def photoview_released(self, tree, event):
        """Restore normal selection behavior while not dragging."""
        self.photos_selection.set_select_function(lambda *ignore: True, None)
        target = tree.get_path_at_pos(int(event.x), int(event.y))
        if (target and self.defer_select
                   and self.defer_select == target[0]
                   and not (event.x == 0 and event.y == 0)): # certain drag&drop
            tree.set_cursor(target[0], target[1], False)
    
    def redraw_interface(self, fraction=None, text=None):
        """Tell Gtk to redraw the user interface, so it doesn't look hung.
        
        Primarily for updating the progressbar, but won't touch it if called
        with no arguments.
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
        self.error_bar.hide()
        return False
    
    def status_message(self, message, info=False):
        """Display a message with the GtkInfoBar."""
        self.error_message.set_markup('<b>%s</b>' % message)
        self.error_bar.set_message_type(
            Gtk.MessageType.INFO if info else Gtk.MessageType.WARNING)
        self.error_icon.set_from_stock(
            Gtk.STOCK_DIALOG_INFO if info else Gtk.STOCK_DIALOG_WARNING, 6)
        self.error_bar.show()
        
        # Remove any previous message timeout
        if self.message_timeout_source is not None:
            GLib.source_remove(self.message_timeout_source)
        if info:
            self.message_timeout_source = \
                GLib.timeout_add_seconds(10, self.dismiss_message)


@singleton
class ChamplainEmbedder(GtkChamplain.Embed):
    """Put the map view onto the main window."""
    
    def __init__(self):
        GtkChamplain.Embed.__init__(self)
        Widgets.map_container.add(self)


# Just pretend that MapView is also a singleton...
MapView = ChamplainEmbedder.get_view()


@singleton
class MarkerLayer(Champlain.MarkerLayer):
    def __init__(self):
        Champlain.MarkerLayer.__init__(self)
        MapView.add_layer(self)

