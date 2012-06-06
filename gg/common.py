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

"""Common classes and datatypes used throughout the app.

The `selected` and `modified` set()s contain Photograph() instances, and
are frequently used for iteration and membership testing throughout the app.

The `points` dict maps epoch seconds to ChamplainCoordinate() instances. This
is used to place photos on the map by looking up their timestamps.

The `photos` dict maps absolute filename paths to Photograph() instances, and
is used for most of the photo manipulations (eg, loading, saving, etc).
"""

from __future__ import division

from gi.repository import GObject, Gtk, Gio, GLib
from gi.repository import GtkChamplain
from os.path import join

from build_info import PKG_DATA_DIR
from version import PACKAGE

# These variables are used for sharing data between classes
selected = set()
modified = set()
points   = {}

def memoize(cls):
    """Cache instances of a class. Decorate the class with @memoize to use.
    
    Note, this rudimentary implementation is incompatible with keyword
    arguments, so don't use those. Most of the classes that I memoize just
    take a single argument and it's a filename, so this isn't a big deal.
    """
    def memoized(*args):
        key = '//'.join(map(str, args))
        if key not in cls.instances:
            cls.instances[key] = cls(*args)
        return cls.instances[key]
    return memoized

def bind_properties(source, source_prop,
                    target, target_prop=None,
                    flags=GObject.BindingFlags.DEFAULT):
    """Make it easier to bind properties between GObjects."""
    if target_prop is None:
        target_prop = source_prop
    return GObject.Binding(source = source,
                           source_property = source_prop,
                           target = target,
                           target_property = target_prop,
                           flags = flags)

class Builder(Gtk.Builder):
    """Load GottenGeography's UI definitions."""
    def __init__(self, filename=PACKAGE):
        Gtk.Builder.__init__(self)
        
        self.set_translation_domain(PACKAGE)
        self.add_from_file(join(PKG_DATA_DIR, filename + '.ui'))
    
    def __getattr__(self, widget):
        """Make calls to Gtk.Builder().get_object() more pythonic."""
        built = self.get_object(widget)
        if built:
            return built
        else:
            raise AttributeError('Unknown widget: ' + widget)
    
    __getitem__ = __getattr__


class GSettings(Gio.Settings):
    """Override GSettings to be more useful to me."""
    get = Gio.Settings.get_value
    
    def __init__(self, schema='ca.exolucere.' + PACKAGE, path=None):
        if path is not None:
            path = '/ca/exolucere/%s/%ss/%s/' % (PACKAGE, schema, path)
            schema = 'ca.exolucere.%s.%s' % (PACKAGE, schema)
        
        Gio.Settings.__init__(self, schema, path)
        
        # These are used to avoid infinite looping.
        self._ignore_key_changed = False
        self._ignore_prop_changed = True
    
    def bind(self, key, widget, prop=None, flags=Gio.SettingsBindFlags.DEFAULT):
        """Don't make me specify the default flags every time."""
        if prop is None:
            prop = key
        Gio.Settings.bind(self, key, widget, prop, flags)
    
    def set_history(self, value):
        """Convert the map history to an array of tuples."""
        Gio.Settings.set_value(self, 'history', GLib.Variant('a(ddi)', value))
    
    def set_window_size(self, value):
        """Convert the window size to a pair of ints."""
        Gio.Settings.set_value(self, 'window-size', GLib.Variant('(ii)', value))
    
    def bind_with_convert(self, key, widget, prop, key_to_prop, prop_to_key):
        """Recreate g_settings_bind_with_mapping from scratch.
        
        This method was shamelessly stolen from John Stowers'
        gnome-tweak-tool on May 14, 2012.
        """
        def key_changed(settings, key):
            """Update widget property."""
            if self._ignore_key_changed: return
            self._ignore_prop_changed = True
            widget.set_property(prop, key_to_prop(self[key]))
            self._ignore_prop_changed = False
        
        def prop_changed(widget, param):
            """Update GSettings key."""
            if self._ignore_prop_changed: return
            self._ignore_key_changed = True
            self[key] = prop_to_key(widget.get_property(prop))
            self._ignore_key_changed = False
        
        self.connect('changed::' + key, key_changed)
        widget.connect('notify::' + prop, prop_changed)
        key_changed(self, key) # init default state


class ChamplainEmbedder(GtkChamplain.Embed):
    """Put the map view onto the main window."""
    
    def __init__(self):
        GtkChamplain.Embed.__init__(self)
        Widgets.map_container.add(self)


class Struct:
    """This is a generic object which can be assigned arbitrary attributes."""
    
    def __init__(self, attributes={}):
        self.__dict__.update(attributes)


# Initialize GtkBuilder, Champlain, and GSettings
Widgets  = Builder()
map_view = ChamplainEmbedder().get_view()
gst      = GSettings()

