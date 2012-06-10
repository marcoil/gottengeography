
"""Orchestrate the construction of widgets with GtkBuilder."""

from gi.repository import Gtk, GtkChamplain
from gi.repository import GdkPixbuf, Pango
from os.path import join

from version import APPNAME, PACKAGE
from build_info import PKG_DATA_DIR, REVISION
from common import Gst, singleton, memoize_method


class Builder(Gtk.Builder):
    """Load GottenGeography's UI definitions."""
    def __init__(self, filename=PACKAGE):
        Gtk.Builder.__init__(self)
        
        self.set_translation_domain(PACKAGE)
        self.add_from_file(join(PKG_DATA_DIR, filename + '.ui'))
    
    @memoize_method(share=False)
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
        
        # Hide the unused button that appears beside the map source menu.
        ugly = self.map_source_menu_button.get_child().get_children()[0]
        ugly.set_no_show_all(True)
        ugly.hide()
        
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
        
        self.loaded_photos.connect('row-changed', photo_pane_visibility)
        self.loaded_photos.connect('row-deleted', photo_pane_visibility)
        
        self.error_bar.connect('response',
            lambda widget, signal: widget.hide())


@singleton
class ChamplainEmbedder(GtkChamplain.Embed):
    """Put the map view onto the main window."""
    
    def __init__(self):
        GtkChamplain.Embed.__init__(self)
        Widgets.map_container.add(self)


# Just pretend that MapView is also a singleton...
MapView = ChamplainEmbedder.get_view()
MapView.__call__ = lambda: MapView

