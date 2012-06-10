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
"""

from __future__ import division

from gi.repository import GObject, Gio, GLib
from inspect import getcallargs
from types import FunctionType

from version import PACKAGE

# These variables are used for sharing data between classes
selected = set()
modified = set()
points   = {}


def singleton(cls):
    """Decorate a class with @singleton when There Can Be Only One."""
    instance = cls()
    instance.__call__ = lambda: instance
    return instance


class memoize(object):
    """Cache instances of a class. Decorate the class with @memoize to use.
    
    This is the only implementation of memoization I am aware of that
    allows you to use keyword arguments and still get cached results, ie,
    Photograph('/file/name') will give you the *same* Photograph instance
    as Photograph(filename='/file/name').
    """
    
    def __init__(self, cls):
        """Expose the cached class's attributes as our own.
        
        This allows Photograph.instances to work even though when you
        say 'Photograph' you're really getting a memoize instance instead
        of the Photograph class.
        """
        if type(cls) is FunctionType:
            raise TypeError('This is for classes only.')
        self.cls = cls
        self.__dict__.update(cls.__dict__)
        
        # This bit allows staticmethods to work as you would expect.
        for attr, val in cls.__dict__.items():
            if type(val) is staticmethod:
                self.__dict__[attr] = val.__func__
    
    def __call__(self, *args, **kwargs):
        """Return a cached instance of the appropriate class if it exists.
        
        This uses inspect.getcallargs in order to allow F(foo=1) to return
        the *same* cached result as if you had called F(1). dicts are passed
        along to your method but not used for generating the cache lookup
        key, so if your method expects a dict as an argument, you'll need to
        ensure that your method signature is unique without the dict, otherwise
        you'll get cache collisions.
        """
        signature = getcallargs(self.cls.__init__, None, *args, **kwargs)
        del signature['self']
        key = tuple(signature[key] for key in sorted(signature)
            if signature[key] and type(signature[key]) not in (dict, list))
        key = key[0] if len(key) is 1 else key
        if key not in self.cls.instances:
            self.cls.instances[key] = self.cls(*args, **kwargs)
        return self.cls.instances[key]


def memoize_method(share=False):
    """Build a memoizer that can either share cache between instances or not."""
    def method_memoizer(func):
        """Decorate the method with @memoize_method(share=True/False) to use.
        
        Pick True if you want different instances sharing cache, or False
        if you need different instances to have unique caches."""
        cache = {}
        def memoized(*args):
            """Fetch the result from the cache."""
            key = args[1:] if share else args
            if key not in cache:
                cache[key] = func(*args)
            return cache[key]
        return memoized
    return method_memoizer


def bind_properties(source, source_prop,
                    target, target_prop=None,
                    flags=GObject.BindingFlags.DEFAULT):
    """Make it easier to bind properties between GObjects."""
    return GObject.Binding(source = source,
                           source_property = source_prop,
                           target = target,
                           target_property = target_prop or source_prop,
                           flags = flags)


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
        Gio.Settings.bind(self, key, widget, prop or key, flags)
    
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


@singleton
class Gst(GSettings):
    """This is the primary GSettings instance for main app settings only.
    
    It cannot be used to access the relocatable schema, for that you'll have
    to create a new GSettings() instance.
    """
    
    def __init__(self):
        GSettings.__init__(self)
    
    def set_history(self, value):
        """Convert the map history to an array of tuples."""
        Gio.Settings.set_value(self, 'history', GLib.Variant('a(ddi)', value))
    
    def set_window_size(self, value):
        """Convert the window size to a pair of ints."""
        Gio.Settings.set_value(self, 'window-size', GLib.Variant('(ii)', value))


class Struct:
    """This is a generic object which can be assigned arbitrary attributes."""
    
    def __init__(self, attributes={}):
        self.__dict__.update(attributes)

