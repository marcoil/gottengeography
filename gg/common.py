# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Common classes and datatypes used throughout the app.

The `selected` and `modified` set()s contain Photograph() instances, and
are frequently used for iteration and membership testing throughout the app.

The `points` dict maps epoch seconds to ChamplainCoordinate() instances. This
is used to place photos on the map by looking up their timestamps.
"""

from __future__ import division

from gi.repository import GObject, Gio, GLib
from types import FunctionType

from version import PACKAGE

# These variables are used for sharing data between classes
selected = set()
modified = set()
points   = {}


def singleton(cls):
    """Decorate a class with @singleton when There Can Be Only One.
    
    >>> @singleton
    ... class Highlander: pass
    >>> Highlander() is Highlander() is Highlander
    True
    >>> id(Highlander()) == id(Highlander)
    True
    """
    instance = cls()
    instance.__call__ = lambda: instance
    return instance


def memoize(obj):
    """General-purpose cache for classes, methods, and functions.
    
    >>> @memoize
    ... def doubler(foo):
    ...     print 'performing expensive calculation...'
    ...     return foo * 2
    >>> doubler(50)
    performing expensive calculation...
    100
    >>> doubler(50)
    100
    
    >>> @memoize
    ... class Memorable:
    ...     instances = {}
    ...     def __init__(self, foo): pass
    >>> Memorable('alpha') is Memorable('alpha')
    True
    >>> Memorable('alpha') is Memorable('beta')
    False
    >>> len(Memorable.instances)
    2
    """
    if type(obj) is FunctionType:
        obj.instances = {}
    
    cache = obj.instances
    
    def memoizer(*args, **kwargs):
        """Do cache lookups and populate the cache in the case of misses."""
        key = args[0] if len(args) is 1 else args
        if key not in cache:
            cache[key] = obj(*args, **kwargs)
        return cache[key]
    
    # Make the memoizer func masquerade as the object we are memoizing.
    # This makes class attributes and static methods behave as expected.
    for k, v in obj.__dict__.items():
        memoizer.__dict__[k] = v.__func__ if type(v) is staticmethod else v
    return memoizer


@memoize
class Binding(GObject.Binding):
    """Make it easier to bind properties between GObjects."""
    instances = {}
    
    def __init__(self, source, sprop, target, tprop=None,
                 flags=GObject.BindingFlags.DEFAULT):
        GObject.Binding.__init__(self,
            source=source, source_property=sprop,
            target=target, target_property=tprop or sprop,
            flags=flags)


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
    
    def set_color(self, color):
        """Convert the GdkColor to a three-int tuple."""
        Gio.Settings.set_value(self, 'track-color',
            GLib.Variant('(iii)', (color.red, color.green, color.blue)))


class Struct:
    """This is a generic object which can be assigned arbitrary attributes.
    
    >>> foo = Struct({'one': 2})
    >>> foo.one
    2
    >>> foo.four = 4
    >>> foo.four
    4
    """
    
    def __init__(self, attributes={}):
        self.__dict__.update(attributes)


class Dummy(Struct):
    """This is a do-nothing stub that can pretend to be anything.
    
    >>> Dummy().this_method_doesnt_exist(1, 2, 3, 4)
    True
    """
    
    def __getattr__(self, attribute):
        """Any method you attempt to call will return True."""
        return lambda *dummy: True
    
    def __hash__(self):
        """Instances can be uniquely identified."""
        return id(self)

