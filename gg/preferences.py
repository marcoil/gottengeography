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

"""Control the behavior of various application preferences."""

from __future__ import division

from gi.repository import Gtk, Gdk
from gi.repository import Champlain
from gi.repository import Clutter
from time import tzset
from os import environ

from common import Struct, polygons, photos, map_view
from common import auto_timestamp_comparison, get_obj, gst
from territories import tz_regions, get_timezone

def make_clutter_color(color):
    """Generate a Clutter.Color from the currently chosen color."""
    return Clutter.Color.new(
        *[x / 256 for x in [color.red, color.green, color.blue, 32768]])

def create_map_source(id, name, license, license_uri, min_zoom, max_zoom,
                      tile_size, uri_format):
    """Put together a chain of caches for the specified map source details."""
    chain = Champlain.MapSourceChain()
    chain.push(Champlain.MapSourceFactory.dup_default().create_error_source(
        tile_size))
    
    chain.push(Champlain.NetworkTileSource.new_full(
        id, name, license, license_uri, min_zoom, max_zoom, tile_size,
        Champlain.MapProjection.MAP_PROJECTION_MERCATOR,
        uri_format, Champlain.ImageRenderer()))
    
    chain.push(Champlain.FileCache.new_full(1e8, None, Champlain.ImageRenderer()))
    chain.push(Champlain.MemoryCache.new_full(100, Champlain.ImageRenderer()))
    
    return chain

map_sources = {
    'osm-mapnik':
    create_map_source('osm-mapnik', 'OpenStreetMap Mapnik',
    'Map data is CC-BY-SA 2.0 OpenStreetMap contributors',
    'http://creativecommons.org/licenses/by-sa/2.0/',
    0, 18, 256, 'http://tile.openstreetmap.org/#Z#/#X#/#Y#.png'),
    
    'osm-cyclemap':
    create_map_source('osm-cyclemap', 'OpenStreetMap Cycle Map',
    'Map data is CC-BY-SA 2.0 OpenStreetMap contributors',
    'http://creativecommons.org/licenses/by-sa/2.0/',
    0, 17, 256, 'http://a.tile.opencyclemap.org/cycle/#Z#/#X#/#Y#.png'),
    
    'osm-transport':
    create_map_source('osm-transport', 'OpenStreetMap Transport Map',
    'Map data is CC-BY-SA 2.0 OpenStreetMap contributors',
    'http://creativecommons.org/licenses/by-sa/2.0/',
    0, 18, 256, 'http://tile.xn--pnvkarte-m4a.de/tilegen/#Z#/#X#/#Y#.png'),
    
    'mapquest-osm':
    create_map_source('mapquest-osm', 'MapQuest OSM',
    'Map data provided by MapQuest, Open Street Map and contributors',
    'http://creativecommons.org/licenses/by-sa/2.0/',
    0, 17, 256, 'http://otile1.mqcdn.com/tiles/1.0.0/osm/#Z#/#X#/#Y#.png'),
    
    'mff-relief':
    create_map_source('mff-relief', 'Maps for Free Relief',
    'Map data available under GNU Free Documentation license, v1.2 or later',
    'http://www.gnu.org/copyleft/fdl.html',
    0, 11, 256,
    'http://maps-for-free.com/layer/relief/z#Z#/row#Y#/#Z#_#X#-#Y#.jpg')
}


class PreferencesController():
    """Controls the behavior of the preferences dialog."""
    gpx_timezone = ''
    
    def __init__(self):
        self.region = region = get_obj('timezone_region')
        self.cities = cities = get_obj('timezone_cities')
        pref_button = get_obj('pref_button')
        
        for name in tz_regions:
            region.append(name, name)
        region.connect('changed', self.region_handler, cities)
        cities.connect('changed', self.cities_handler)
        gst.bind('timezone-region', region, 'active')
        gst.bind('timezone-cities', cities, 'active')
        
        self.colorpicker = get_obj('colorselection')
        gst.bind_with_convert('track-color', self.colorpicker, 'current-color',
            lambda x: Gdk.Color(*x), lambda x: (x.red, x.green, x.blue))
        self.colorpicker.connect('color-changed', self.track_color_changed)
        
        radio_group = []
        map_menu = get_obj('map_source_menu')
        last_source = gst.get('map-source-id').get_string()
        gst.bind_with_convert('map-source-id', map_view, 'map-source',
            map_sources.get, lambda x: x.get_id())
        menu_item_clicked = (lambda item, mapid: item.get_active() and
            map_view.set_map_source(map_sources[mapid]))
        for i, source_id in enumerate(sorted(map_sources.keys())):
            source = map_sources[source_id]
            menu_item = Gtk.RadioMenuItem.new_with_label(radio_group,
                                                         source.get_name())
            radio_group.append(menu_item)
            if last_source == source_id:
                menu_item.set_active(True)
            menu_item.connect('activate', menu_item_clicked, source_id)
            map_menu.attach(menu_item, 0, 1, i, i+1)
        map_menu.show_all()
        
        pref_button.connect('clicked', self.preferences_dialog,
            get_obj('preferences'), region, cities, self.colorpicker)
        
        self.radios = {}
        for option in ['system', 'lookup', 'custom']:
            option += '-timezone'
            radio = get_obj(option)
            radio.set_name(option)
            gst.bind(option, radio, 'active')
            self.radios[option] = radio
            radio.connect('clicked', self.radio_handler)
        gst.bind('custom-timezone', get_obj('custom_timezone_combos'),
                 'sensitive')
    
    def preferences_dialog(self, button, dialog, region, cities, colorpicker):
        """Allow the user to configure this application."""
        previous = Struct({
            'system': gst.get_boolean('system-timezone'),
            'lookup': gst.get_boolean('lookup-timezone'),
            'custom': gst.get_boolean('custom-timezone'),
            'region': region.get_active(),
            'city':   cities.get_active(),
            'color':  colorpicker.get_current_color()
        })
        if not dialog.run():
            colorpicker.set_current_color(previous.color)
            colorpicker.set_previous_color(previous.color)
            gst.set_boolean('system-timezone', previous.system)
            gst.set_boolean('lookup-timezone', previous.lookup)
            gst.set_boolean('custom-timezone', previous.custom)
            region.set_active(previous.region)
            cities.set_active(previous.city)
        dialog.hide()
    
    def set_timezone(self):
        """Set the timezone to the given zone and update all photos."""
        if 'TZ' in environ:
            del environ['TZ']
        if gst.get_boolean('lookup-timezone'):
            environ['TZ'] = self.gpx_timezone
        elif gst.get_boolean('custom-timezone'):
            region = self.region.get_active_id()
            city   = self.cities.get_active_id()
            if region is not None and city is not None:
                environ['TZ'] = '%s/%s' % (region, city)
        tzset()
        for photo in photos.values():
            photo.calculate_timestamp()
            auto_timestamp_comparison(photo)
    
    def radio_handler(self, radio):
        """Reposition photos depending on which timezone the user selected."""
        if radio.get_active():
            self.set_timezone()
    
    def region_handler(self, regions, cities):
        """Populate the list of cities when a continent is selected."""
        cities.remove_all()
        for city in get_timezone(regions.get_active_id(), []):
            cities.append(city, city)
    
    def cities_handler(self, cities):
        """When a city is selected, update the chosen timezone."""
        if cities.get_active_id() is not None:
            self.set_timezone()
    
    def track_color_changed(self, selection):
        """Update the color of any loaded GPX tracks."""
        color = selection.get_current_color()
        one   = make_clutter_color(color)
        two   = one.lighten().lighten()
        for i, polygon in enumerate(polygons):
            polygon.set_stroke_color(two if i % 2 else one)

