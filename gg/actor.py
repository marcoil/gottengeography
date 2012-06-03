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

from common import gst, get_obj, map_view
from gpsmath import format_coords

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


def map_source_menu():
    """Load the predefined map sources into a menu the user can use."""
    radio_group = []
    map_menu = get_obj('map_source_menu')
    last_source = gst.get_string('map-source-id')
    gst.bind_with_convert('map-source-id', map_view, 'map-source',
        MAP_SOURCES.get, lambda x: x.get_id())
    menu_item_clicked = (lambda item, mapid: item.get_active() and
        map_view.set_map_source(MAP_SOURCES[mapid]))
    
    for i, source_id in enumerate(sorted(MAP_SOURCES.keys())):
        source = MAP_SOURCES[source_id]
        menu_item = Gtk.RadioMenuItem.new_with_label(radio_group,
                                                     source.get_name())
        radio_group.append(menu_item)
        if last_source == source_id:
            menu_item.set_active(True)
        menu_item.connect('activate', menu_item_clicked, source_id)
        map_menu.attach(menu_item, 0, 1, i, i+1)
    map_menu.show_all()

def display(view, param, mlink, label):
    """Display map center coordinates when they change."""
    lat, lon = [ view.get_property(x) for x in ('latitude', 'longitude') ]
    label.set_markup(format_coords(lat, lon))
    mlink.set_uri('%s?ll=%s,%s&amp;spn=%s,%s'
        % ('http://maps.google.com/maps', lat, lon,
        lon - view.x_to_longitude(0), view.y_to_latitude(0) - lat))


class ActorController():
    """Controls the behavior of the custom actors I have placed over the map."""
    
    def __init__(self):
        self.black = Clutter.Box.new(Clutter.BinLayout())
        self.black.set_color(Clutter.Color.new(0, 0, 0, 96))
        self.label = Clutter.Text()
        self.label.set_color(Clutter.Color.new(255, 255, 255, 255))
        self.xhair = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(0, 0, 0, 64))
        for signal in [ 'latitude', 'longitude' ]:
            map_view.connect('notify::' + signal, display,
                get_obj('maps_link'), self.label)
        map_view.connect('notify::width',
            lambda view, param, black:
                black.set_size(view.get_width(), 30),
            self.black)
        
        scale = Champlain.Scale.new()
        scale.connect_view(map_view)
        gst.bind('show-map-scale', scale, 'visible')
        gst.bind('show-map-center', self.xhair, 'visible')
        gst.bind('show-map-coords', self.black, 'visible')
        map_view.bin_layout_add(scale,
            Clutter.BinAlignment.START, Clutter.BinAlignment.END)
        map_view.bin_layout_add(self.black,
            Clutter.BinAlignment.START, Clutter.BinAlignment.START)
        self.black.get_layout_manager().add(self.label,
            Clutter.BinAlignment.CENTER, Clutter.BinAlignment.CENTER)
        
        map_source_menu()
    
    def animate_in(self, anim=True):
        """Animate the crosshair."""
        map_view.bin_layout_add(self.xhair,
            Clutter.BinAlignment.CENTER, Clutter.BinAlignment.CENTER)
        self.xhair.set_z_rotation_from_gravity(45, Clutter.Gravity.CENTER)
        for i in xrange(gst.get_int('animation-steps') if anim else 8, 7, -1):
            self.xhair.set_size(i, i)
            opacity = 0.6407035175879398 * (400 - i) # don't ask
            for actor in [self.xhair, self.label, self.black]:
                actor.set_opacity(opacity)
            while Gtk.events_pending():
                Gtk.main_iteration()
            sleep(0.01)

