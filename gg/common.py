# GottenGeography - Common things used throughout the app.
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

from gi.repository import Gtk, Gio, GLib
from gi.repository import GtkChamplain
from os.path import join

from build_info import PKG_DATA_DIR
from version import PACKAGE


class Builder(Gtk.Builder):
    """Load GottenGeography's UI definitions."""
    def __init__(self):
        Gtk.Builder.__init__(self)
        
        self.set_translation_domain(PACKAGE)
        self.add_from_file(join(PKG_DATA_DIR, PACKAGE + '.ui'))


class GSettings(Gio.Settings):
    """Override GSettings to be more useful to me."""
    get = Gio.Settings.get_value
    
    def __init__(self):
        Gio.Settings.__init__(self, 'ca.exolucere.' + PACKAGE)
        
        # These are used to avoid infinite looping.
        self._ignore_key_changed = False
        self._ignore_prop_changed = True
    
    def bind(self, key, widget, prop, flags=Gio.SettingsBindFlags.DEFAULT):
        """Don't make me specify the default flags every time."""
        Gio.Settings.bind(self, key, widget, prop, flags)
    
    def set(self, key, value):
        """Convert arrays to GVariants.
        
        This makes it easier to set the back button history and the window size.
        """
        use_matrix = type(value) is list
        do_override = type(value) is tuple or use_matrix
        Gio.Settings.set_value(self, key, value if not do_override else
            GLib.Variant('aad' if use_matrix else '(ii)', value))
    
    def bind_with_convert(self, key, widget, prop, key_to_prop, prop_to_key):
        """Recreate g_settings_bind_with_mapping from scratch.
        
        This method was shamelessly stolen from John Stowers'
        gnome-tweak-tool on May 14, 2012.
        """
        def key_changed(settings, key):
            if self._ignore_key_changed: return
            orig_value = self[key]
            converted_value = key_to_prop(orig_value)
            self._ignore_prop_changed = True
            try:
                widget.set_property(prop, converted_value)
            except TypeError:
                print "TypeError: %s not a valid %s." % (converted_value, prop)
            self._ignore_prop_changed = False
        
        def prop_changed(widget, param):
            if self._ignore_prop_changed: return
            orig_value = widget.get_property(prop)
            converted_value = prop_to_key(orig_value)
            self._ignore_key_changed = True
            try:
                self[key] = converted_value
            except TypeError:
                print "TypeError: %s not a valid %s." % (converted_value, key)
            self._ignore_key_changed = False
        
        self.connect("changed::" + key, key_changed)
        widget.connect("notify::" + prop, prop_changed)
        key_changed(self,key) # init default state


class Struct:
    """This is a generic object which can be assigned arbitrary attributes."""
    
    def __init__(self, attributes={}):
        self.__dict__.update(attributes)


class CommonAttributes:
    """Define attributes required by all Controller classes.
    
    This class is never instantiated, it is only inherited by classes that
    need to manipulate the map, or the loaded photos.
    """
    champlain = GtkChamplain.Embed()
    map_view  = champlain.get_view()
    slide_to  = map_view.go_to
    metadata  = Struct()
    selected  = set()
    modified  = set()
    polygons  = []
    tracks    = {}
    photo     = {}


# Initialize GtkBuilder and GSettings
get_obj = Builder().get_object
gst = GSettings()

