# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Custom map sources are defined here:

>>> MAP_SOURCES['osm-mapnik']                                #doctest: +ELLIPSIS
<MapSourceChain object at 0x... (ChamplainMapSourceChain at 0x...)>


Gtk.RadioMenuItem is subclassed to add itself to the menu. You just need
to instantiate it:

>>> RadioMenuItem(MAP_SOURCES['osm-cyclemap']).get_label()
'OpenStreetMap Cycle Map'

>>> len(Widgets.map_source_menu.get_children()) == len(MAP_SOURCES)
True


Custom map actors are defined here as well:

>>> isinstance(Crosshair, Champlain.Point)
True
>>> isinstance(Scale, Champlain.Scale)
True
>>> isinstance(Box, Clutter.Box)
True
>>> isinstance(CoordLabel, Clutter.Text)
True

>>> MapView.center_on(53.554177, -116.792299)
>>> CoordLabel.get_text()
'N 53.55418, W 116.79230'
"""

from __future__ import division

from gi.repository import GtkClutter
GtkClutter.init([])

from gi.repository import Gtk, Champlain, Clutter
from time import sleep

from gpsmath import format_coords
from widgets import Widgets, MapView
from common import Gst, singleton, memoize

START  = Clutter.BinAlignment.START
CENTER = Clutter.BinAlignment.CENTER
END    = Clutter.BinAlignment.END

MAP_SOURCES = {}

for map_desc in [
    ['osm-mapnik', 'OpenStreetMap Mapnik', 0, 18, 256,
    'Map data is CC-BY-SA 2.0 OpenStreetMap contributors',
    'http://creativecommons.org/licenses/by-sa/2.0/',
    'http://tile.openstreetmap.org/#Z#/#X#/#Y#.png'],
    
    ['osm-cyclemap', 'OpenStreetMap Cycle Map', 0, 17, 256,
    'Map data is CC-BY-SA 2.0 OpenStreetMap contributors',
    'http://creativecommons.org/licenses/by-sa/2.0/',
    'http://a.tile.opencyclemap.org/cycle/#Z#/#X#/#Y#.png'],
    
    ['osm-transport', 'OpenStreetMap Transport Map', 0, 18, 256,
    'Map data is CC-BY-SA 2.0 OpenStreetMap contributors',
    'http://creativecommons.org/licenses/by-sa/2.0/',
    'http://tile.xn--pnvkarte-m4a.de/tilegen/#Z#/#X#/#Y#.png'],
    
    ['mapquest-osm', 'MapQuest OSM', 0, 17, 256,
    'Map data provided by MapQuest, Open Street Map and contributors',
    'http://creativecommons.org/licenses/by-sa/2.0/',
    'http://otile1.mqcdn.com/tiles/1.0.0/osm/#Z#/#X#/#Y#.png'],
    
    ['mff-relief', 'Maps for Free Relief', 0, 11, 256,
    'Map data available under GNU Free Documentation license, v1.2 or later',
    'http://www.gnu.org/copyleft/fdl.html',
    'http://maps-for-free.com/layer/relief/z#Z#/row#Y#/#Z#_#X#-#Y#.jpg'],
    ]:
    mapid, name, min_zoom, max_zoom, size, lic, lic_uri, tile_uri = map_desc
    
    c = Champlain.MapSourceChain()
    c.push(Champlain.MapSourceFactory.dup_default().create_error_source(size))
    
    c.push(Champlain.NetworkTileSource.new_full(
        mapid, name, lic, lic_uri, min_zoom, max_zoom,
        size, Champlain.MapProjection.MAP_PROJECTION_MERCATOR,
        tile_uri, Champlain.ImageRenderer()))
    
    c.push(Champlain.FileCache.new_full(1e8, None, Champlain.ImageRenderer()))
    c.push(Champlain.MemoryCache.new_full(100,     Champlain.ImageRenderer()))
    MAP_SOURCES[mapid] = c


@memoize
class RadioMenuItem(Gtk.RadioMenuItem):
    """Create the individual menu items for choosing map sources."""
    instances = {}
    
    def __init__(self, source):
        Gtk.RadioMenuItem.__init__(self)
        if self.instances:
            self.set_property('group', self.instances.values()[0])
        self.set_label(source.get_name())
        self.connect('activate', self.menu_item_clicked, source.get_id())
        Widgets.map_source_menu.append(self)
    
    def menu_item_clicked(self, item, map_id):
        """Switch to the clicked map source."""
        if self.get_active():
            MapView.set_map_source(MAP_SOURCES[map_id])


@singleton
class Sources:
    """Set up the source menu and link to GSettings."""
    
    def __init__(self):
        last_source = Gst.get_string('map-source-id')
        Gst.bind_with_convert('map-source-id', MapView, 'map-source',
            MAP_SOURCES.get, lambda x: x.get_id())
        
        for source_id in sorted(MAP_SOURCES):
            menu_item = RadioMenuItem(MAP_SOURCES[source_id])
            if last_source == source_id:
                menu_item.set_active(True)
        
        Widgets.map_source_menu.show_all()


@singleton
class Crosshair(Champlain.Point):
    """Display a target at map center for placing photos."""
    
    def __init__(self):
        Champlain.Point.__init__(self)
        self.set_size(4)
        self.set_color(Clutter.Color.new(0, 0, 0, 64))
        Gst.bind('show-map-center', self, 'visible')
        MapView.bin_layout_add(self, CENTER, CENTER)


@singleton
class Scale(Champlain.Scale):
    """Display a distance scale on the map."""
    
    def __init__(self):
        Champlain.Scale.__init__(self)
        self.connect_view(MapView)
        Gst.bind('show-map-scale', self, 'visible')
        MapView.bin_layout_add(self, START, END)


@singleton
class CoordLabel(Clutter.Text):
    """Put the current map coordinates into the black coordinate bar."""
    
    def __init__(self):
        Clutter.Text.__init__(self)
        self.set_color(Clutter.Color.new(255, 255, 255, 255))
        for signal in ('latitude', 'longitude'):
            MapView.connect('notify::' + signal, self.display)
    
    def display(self, view, param):
        """Display map center coordinates when they change."""
        self.set_markup(format_coords(
            MapView.get_center_latitude(),
            MapView.get_center_longitude()))


@singleton
class Box(Clutter.Box):
    """Draw the black coordinate display bar atop map."""
    
    def __init__(self):
        Clutter.Box.__init__(self)
        self.set_layout_manager(Clutter.BinLayout())
        self.set_color(Clutter.Color.new(0, 0, 0, 96))
        Gst.bind('show-map-coords', self, 'visible')
        MapView.bin_layout_add(self, START, START)
        self.get_layout_manager().add(CoordLabel, CENTER, CENTER)
        MapView.connect('notify::width',
            lambda *ignore: self.set_size(MapView.get_width(), 30))


def animate_in(anim=True):
    """Fade in all the map actors."""
    for i in xrange(Gst.get_int('animation-steps') if anim else 1, 0, -1):
        for actor in (Crosshair, Box, Scale):
            actor.set_opacity(256 - i)
        Widgets.redraw_interface()
        sleep(0.01)

