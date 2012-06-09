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

"""Control how the custom map actors behave."""

from __future__ import division

from gi.repository import Gtk, Champlain, Clutter
from time import sleep

from common import Widgets, memoize, gst, map_view
from gpsmath import format_coords

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
    mapid, name, min_zoom, max_zoom, size, license, lic_uri, tile_uri = map_desc
    
    c = Champlain.MapSourceChain()
    c.push(Champlain.MapSourceFactory.dup_default().create_error_source(size))
    
    c.push(Champlain.NetworkTileSource.new_full(
        mapid, name, license, lic_uri, min_zoom, max_zoom,
        size, Champlain.MapProjection.MAP_PROJECTION_MERCATOR,
        tile_uri, Champlain.ImageRenderer()))
    
    c.push(Champlain.FileCache.new_full(1e8, None, Champlain.ImageRenderer()))
    c.push(Champlain.MemoryCache.new_full(100,     Champlain.ImageRenderer()))
    MAP_SOURCES[mapid] = c


class Sources:
    """Set up the source menu and link to GSettings."""
    
    def __init__(self):
        last_source = gst.get_string('map-source-id')
        gst.bind_with_convert('map-source-id', map_view, 'map-source',
            MAP_SOURCES.get, lambda x: x.get_id())
        
        for source_id in sorted(MAP_SOURCES):
            menu_item = RadioMenuItem(MAP_SOURCES[source_id])
            if last_source == source_id:
                menu_item.set_active(True)
        
        Widgets.map_source_menu.show_all()


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
            map_view.set_map_source(MAP_SOURCES[map_id])


class Crosshair(Clutter.Rectangle):
    """Display a target at map center for placing photos."""
    
    def __init__(self):
        Clutter.Rectangle.__init__(self)
        self.set_color(Clutter.Color.new(0, 0, 0, 64))
        self.set_z_rotation_from_gravity(45, Clutter.Gravity.CENTER)
        gst.bind('show-map-center', self, 'visible')
        map_view.bin_layout_add(self, CENTER, CENTER)


class Scale(Champlain.Scale):
    """Display a distance scale on the map."""
    
    def __init__(self):
        Champlain.Scale.__init__(self)
        self.connect_view(map_view)
        gst.bind('show-map-scale', self, 'visible')
        map_view.bin_layout_add(self, START, END)


class Box(Clutter.Box):
    """Draw the black coordinate display bar atop map."""
    
    def __init__(self):
        Clutter.Box.__init__(self)
        self.set_layout_manager(Clutter.BinLayout())
        self.set_color(Clutter.Color.new(0, 0, 0, 96))
        gst.bind('show-map-coords', self, 'visible')
        map_view.bin_layout_add(self, START, START)
        self.get_layout_manager().add(CoordLabel(), CENTER, CENTER)
        map_view.connect('notify::width',
            lambda *ignore: self.set_size(map_view.get_width(), 30))


class CoordLabel(Clutter.Text):
    """Put the current map coordinates into the black coordinate bar."""
    
    def __init__(self):
        Clutter.Text.__init__(self)
        self.set_color(Clutter.Color.new(255, 255, 255, 255))
        for signal in ('latitude', 'longitude'):
            map_view.connect('notify::' + signal, self.display)
    
    def display(self, view, param, mlink=Widgets.maps_link):
        """Display map center coordinates when they change."""
        lat, lon = [ view.get_property(x) for x in ('latitude', 'longitude') ]
        self.set_markup(format_coords(lat, lon))
        mlink.set_uri('%s?ll=%s,%s&amp;spn=%s,%s'
            % ('http://maps.google.com/maps', lat, lon,
            lon - view.x_to_longitude(0), view.y_to_latitude(0) - lat))


srces = Sources()
xhair = Crosshair()
scale = Scale()
black = Box()


def animate_in(anim=True):
    """Animate the crosshair."""
    for i in xrange(8, 7, -1):
        xhair.set_size(i, i)
        opacity = 0.6407035175879398 * (400 - i) # don't ask
        for actor in (xhair, black):
            actor.set_opacity(opacity)
        while Gtk.events_pending():
            Gtk.main_iteration()
        sleep(0.01)

