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

"""Ensure that GottenGeography is behaving correctly."""

from __future__ import division

from gi.repository import Gdk, Clutter, Champlain
from unittest import TestCase, TextTestRunner, TestLoader
from os import listdir, system, environ
from os.path import join, abspath
from fractions import Fraction
from random import random
from math import floor
from time import tzset

import app
from photos import Photograph
from gpsmath import Coordinates, valid_coords
from gpsmath import decimal_to_dms, dms_to_decimal, float_to_rational
from preferences import MAP_SOURCES, make_clutter_color
from common import Struct, Polygon, polygons, map_view
from common import points, photos, selected, modified
from navigation import move_by_arrow_keys
from build_info import PKG_DATA_DIR
from camera import known_cameras
from common import clear_all_gpx

gui = app.GottenGeography()
get_obj = app.get_obj
gst_get = app.gst.get

# Disable animations so tests pass more quickly.
gui.search.slide_to = map_view.center_on

DEMOFILES = [abspath(join(PKG_DATA_DIR, '..', 'demo', f))
             for f in listdir('./demo/')]

class GottenGeographyTester(TestCase):
    def setUp(self):
        """Start the GottenGeography application."""
        # Make the tests work for people outside my time zone.
        system('git checkout demo')
        environ['TZ'] = 'America/Edmonton'
        tzset()
    
    def tearDown(self):
        """Undo whatever mess the testsuite created."""
        for photo in photos.values():
            gui.labels.layer.remove_marker(photo.label)
            del photos[photo.filename]
            modified.discard(photo)
        gui.labels.select_all.set_active(False)
        gui.liststore.clear()
        system('git checkout demo')
        for key in app.gst.list_keys():
            app.gst.reset(key)
        clear_all_gpx()
    
    def test_actor_controller(self):
        """Make sure the actors are behaving."""
        from actor import ActorController
        control = ActorController()
        link = get_obj('maps_link')
        map_view.center_on(50, 50)
        self.assertEqual(control.label.get_text(), 'N 50.00000, E 50.00000')
        self.assertEqual(link.get_current_uri()[:45],
            'http://maps.google.com/maps?ll=50.0,50.0&spn=')
        map_view.center_on(-10, -30)
        self.assertEqual(control.label.get_text(), 'S 10.00000, W 30.00000')
        self.assertEqual(link.get_current_uri()[:47],
            'http://maps.google.com/maps?ll=-10.0,-30.0&spn=')
        for rot in control.xhair.get_rotation(Clutter.RotateAxis.Z_AXIS):
            self.assertEqual(rot, 0)
        control.animate_in(10)
        self.assertEqual(control.xhair.get_rotation(Clutter.RotateAxis.Z_AXIS)[0], 45)
        self.assertEqual(control.black.get_width(), map_view.get_width())
    
    def test_drag_controller(self):
        """Make sure that we can drag photos around."""
        # Can we load files?
        data = Struct({'get_text': lambda: '\n'.join(DEMOFILES)})
        self.assertEqual(len(photos), 0)
        self.assertEqual(len(points), 0)
        gui.drag.photo_drag_end(None, None, 20, 20, data,
                                None, None, True)
        self.assertEqual(len(photos), 6)
        self.assertEqual(len(points), 374)
        self.tearDown()
        self.assertEqual(len(photos), 0)
        self.assertEqual(len(points), 0)
        
        gui.open_files(DEMOFILES)
        for photo in photos.values():
            # 'Drag' a ChamplainLabel and make sure the photo location matches.
            photo.label.set_location(random_coord(80), random_coord(180))
            photo.label.emit('drag-finish', Clutter.Event())
            self.assertEqual(photo.label.get_latitude(), photo.latitude)
            self.assertEqual(photo.label.get_longitude(), photo.longitude)
            self.assertGreater(len(photo.pretty_geoname()), 5)
            old = [photo.latitude, photo.longitude]
            
            # 'Drag' a photo onto the map and make sure that also works.
            selected.add(photo)
            data = Struct({'get_text': lambda: photo.filename})
            gui.drag.photo_drag_end(None, None, 20, 20, data,
                                    None, None, True)
            self.assertEqual(photo.label.get_latitude(), photo.latitude)
            self.assertEqual(photo.label.get_longitude(), photo.longitude)
            self.assertGreater(len(photo.pretty_geoname()), 5)
            self.assertNotEqual(photo.latitude, old[0])
            self.assertNotEqual(photo.longitude, old[1])
    
    def test_label_controller(self):
        """Make sure that ChamplainLabels are behaving."""
        gui.open_files(DEMOFILES)
        for photo in photos.values():
            self.assertEqual(photo.label.get_scale(), (1, 1))
            photo.label.emit("enter-event", Clutter.Event())
            self.assertEqual(photo.label.get_scale(), (1.05, 1.05))
            photo.label.emit("leave-event", Clutter.Event())
            self.assertEqual(photo.label.get_scale(), (1, 1))
            
            # Are Labels clickable?
            photo.label.emit("button-press", Clutter.Event())
            for button in ('save', 'revert', 'apply', 'close'):
                self.assertTrue(get_obj(button + '_button').get_sensitive())
            self.assertTrue(gui.labels.selection.iter_is_selected(photo.iter))
            self.assertEqual(gui.labels.selection.count_selected_rows(), 1)
            self.assertTrue(photo in selected)
            self.assertEqual(len(selected), 1)
            self.assertEqual(photo.label.get_scale(), (1.1, 1.1))
            self.assertTrue(photo.label.get_selected())
            self.assertEqual(photo.label.get_property('opacity'), 255)
            
            # Make sure the Labels that we didn't click on are deselected.
            for other in photos.values():
                if other.filename == photo.filename: continue
                self.assertFalse(gui.labels.selection.iter_is_selected(other.iter))
                self.assertFalse(other in selected)
                self.assertEqual(other.label.get_scale(), (1, 1))
                self.assertFalse(other.label.get_selected())
                self.assertEqual(other.label.get_property('opacity'), 64)
    
    def test_gtk_builder(self):
        """Make sure that various widgets were created properly."""
        self.assertEqual(gui.liststore.get_n_columns(), 4)
        self.assertEqual(gui.search.results.get_n_columns(), 3)
        size = get_obj('main').get_size()
        self.assertGreater(size[1], 300)
        self.assertGreater(size[0], 400)
        self.assertEqual(gui.labels.selection.count_selected_rows(), 0)
    
    def test_gsettings(self):
        """Make sure that GSettings is storing data correctly."""
        app.gst.reset('history')
        self.assertEqual(gst_get('history')[0], (34.5, 15.8, 2))
        map_view.center_on(12.3, 45.6)
        self.assertEqual(app.gst.get_double('latitude'), 12.3)
        self.assertEqual(app.gst.get_double('longitude'), 45.6)
        map_view.zoom_in()
        map_view.emit('realize')
        self.assertEqual(list(gst_get('history')),
                         [(34.5, 15.8, 2), (12.3, 45.6, 3)])
        map_view.set_map_source(MAP_SOURCES['osm-cyclemap'])
        self.assertEqual(app.gst.get_string('map-source-id'), 'osm-cyclemap')
    
    def test_demo_data(self):
        """Load the demo data and ensure that we're reading it in properly."""
        self.assertEqual(len(points), 0)
        self.assertEqual(len(polygons), 0)
        self.assertEqual(app.metadata.alpha, float('inf'))
        self.assertEqual(app.metadata.omega, float('-inf'))
        
        # No buttons should be sensitive yet because nothing's loaded.
        buttons = {}
        for button in ('save', 'revert', 'apply', 'close', 'clear'):
            buttons[button] = get_obj(button + '_button')
            self.assertFalse(buttons[button].get_sensitive())
        
        # Load only the photos first.
        for filename in DEMOFILES:
            if filename[-3:] != 'gpx':
                self.assertRaises(IOError, gui.load_gpx_from_file, filename)
                gui.load_img_from_file(filename)
        
        # Nothing is yet selected or modified, so buttons still insensitive.
        for button in buttons.values():
            self.assertFalse(button.get_sensitive())
        
        # Something loaded in the liststore?
        self.assertEqual(len(gui.liststore), 6)
        self.assertTrue(gui.liststore.get_iter_first())
        
        for photo in photos.values():
            self.assertFalse(photo in modified)
            self.assertFalse(photo in selected)
            
            # Pristine demo data shouldn't have any tags.
            self.assertIsNone(photo.altitude)
            self.assertIsNone(photo.latitude)
            self.assertIsNone(photo.longitude)
            self.assertFalse(photo.manual)
            
            # Test that missing the provincestate doesn't break the geoname.
            photo.latitude = 47.56494
            photo.longitude = -52.70931
            photo.lookup_geoname()
            self.assertEqual(photo.pretty_geoname(),
                "St. John's,\nNewfoundland and Labrador,\nCanada")
            photo.set_geodata(['Anytown', None, 'US', 'timezone'])
            self.assertEqual(photo.pretty_geoname(), 'Anytown, United States')
            self.assertEqual(photo.timezone, 'timezone')
            
            # Add some crap
            photo.manual    = True
            photo.latitude  = 10.0
            photo.altitude  = 650
            photo.longitude = 45.0
            self.assertTrue(photo.valid_coords())
            
            # photo.read() should discard all the crap we added above.
            # This is in response to a bug where I was using pyexiv2 wrongly
            # and it would load data from disk without discarding old data.
            photo.read()
            self.assertEqual(photo.pretty_geoname(), '')
            self.assertIsNone(photo.altitude)
            self.assertIsNone(photo.latitude)
            self.assertIsNone(photo.longitude)
            self.assertFalse(photo.valid_coords())
            self.assertFalse(photo.manual)
            self.assertEqual(photo.filename, photo.label.get_name())
            self.assertEqual(photo.timestamp,
                gui.liststore.get_value(photo.iter, app.TIMESTAMP))
        
        # Test the select-all button.
        select_all = get_obj('select_all_button')
        select_all.set_active(True)
        self.assertEqual(len(selected), len(gui.liststore))
        select_all.set_active(False)
        self.assertEqual(len(selected), 0)
        
        # Load the GPX
        gpx_filename = join(PKG_DATA_DIR, '..', 'demo', '20101016.gpx')
        self.assertRaises(IOError, gui.load_img_from_file, gpx_filename)
        gui.open_files([gpx_filename])
        self.assertTrue(buttons['clear'].get_sensitive())
        gui.labels.selection.emit('changed')
        
        # Check that the GPX is loaded
        self.assertEqual(len(points), 374)
        self.assertEqual(len(polygons), 1)
        self.assertEqual(app.metadata.alpha, 1287259751)
        self.assertEqual(app.metadata.omega, 1287260756)
        
        # The save button should be sensitive because loading GPX modifies
        # photos, but nothing is selected so the others are insensitive.
        self.assertTrue(buttons['save'].get_sensitive())
        for button in ('revert', 'apply', 'close'):
            self.assertFalse(buttons[button].get_sensitive())
        
        for photo in photos.values():
            self.assertTrue(photo in modified)
            
            self.assertIsNotNone(photo.latitude)
            self.assertIsNotNone(photo.longitude)
            self.assertTrue(photo.valid_coords())
            self.assertTrue(photo.label.get_property('visible'))
        
        # Unload the GPX data.
        buttons['clear'].emit('clicked')
        self.assertEqual(len(points), 0)
        self.assertEqual(len(polygons), 0)
        self.assertFalse(buttons['clear'].get_sensitive())
        
        # Save all photos
        buttons['save'].emit('clicked')
        self.assertEqual(len(modified), 0)
        for button in ('save', 'revert'):
            self.assertFalse(buttons[button].get_sensitive())
        
        gui.labels.selection.select_all()
        self.assertEqual(len(selected), 6)
        for button in ('save', 'revert'):
            self.assertFalse(buttons[button].get_sensitive())
        for button in ('apply', 'close'):
            self.assertTrue(buttons[button].get_sensitive())
        
        # Close all the photos.
        files = [photo.filename for photo in selected]
        buttons['close'].emit('clicked')
        for button in ('save', 'revert', 'apply', 'close'):
            self.assertFalse(buttons[button].get_sensitive())
        self.assertEqual(len(photos), 0)
        self.assertEqual(len(modified), 0)
        self.assertEqual(len(selected), 0)
        
        # Re-read the photos back from disk to make sure that the saving
        # was successful.
        for filename in files:
            photo = Photograph(filename, lambda x: None)
            photo.read()
            self.assertTrue(photo.valid_coords())
            self.assertGreater(photo.altitude, 600)
            self.assertEqual(photo.pretty_geoname(), 'Edmonton, Alberta, Canada')
    
    def test_string_functions(self):
        """Ensure that strings print properly."""
        environ['TZ'] = 'America/Edmonton'
        tzset()
        
        # Make a photo with a dummy ChamplainLabel.
        label = Struct()
        label.get_text = lambda: DEMOFILES[5]
        photo = Photograph(label.get_text(), lambda x: None)
        photo.read()
        photo.label = label
        
        photo.latitude  = None
        photo.longitude = None
        self.assertEqual(photo.pretty_coords(), 'Not geotagged')
        photo.latitude  = 10.0
        photo.longitude = 10.0
        self.assertEqual(photo.pretty_coords(), 'N 10.00000, E 10.00000')
        photo.latitude  = -10.0
        photo.longitude = -10.0
        self.assertEqual(photo.pretty_coords(), 'S 10.00000, W 10.00000')
        
        photo.timestamp = None
        self.assertIsNone(photo.pretty_time())
        photo.timestamp = 999999999
        self.assertEqual(photo.pretty_time(), '2001-09-08 07:46:39 PM')
        
        photo.altitude = None
        self.assertIsNone(photo.pretty_elevation())
        photo.altitude = -10.20005
        self.assertEqual(photo.pretty_elevation(), '10.2m below sea level')
        photo.altitude = 600.71
        self.assertEqual(photo.pretty_elevation(), '600.7m above sea level')
        
        self.assertEqual(photo.short_summary(),
"""2001-09-08 07:46:39 PM
S 10.00000, W 10.00000
600.7m above sea level""")
        self.assertEqual(photo.long_summary(),
"""<span size="larger">IMG_2411.JPG</span>
<span style="italic" size="smaller">2001-09-08 07:46:39 PM
S 10.00000, W 10.00000
600.7m above sea level</span>""")
        
        self.assertRegexpMatches(
            get_obj('maps_link').get_label(),
            r'href="http://maps.google.com'
        )
    
    def test_gps_math(self):
        """Test coordinate conversion functions."""
        rats_to_fracs = lambda rats: [Fraction(rat.to_float()) for rat in rats]
        
        # Really important that this method is bulletproof
        self.assertFalse(valid_coords(None, None))
        self.assertFalse(valid_coords('', ''))
        self.assertFalse(valid_coords(True, True))
        self.assertFalse(valid_coords(False, False))
        self.assertFalse(valid_coords(45, 270))
        self.assertFalse(valid_coords(100, 50))
        self.assertFalse(valid_coords([], 50))
        self.assertFalse(valid_coords(45, {'grunt':42}))
        self.assertFalse(valid_coords(self, 50))
        self.assertFalse(valid_coords(45, valid_coords))
        self.assertFalse(valid_coords("ya", "dun goofed"))
        
        # St. John's broke the math. I'm not sure why.
        # Seriously. Revert commit 362dd6eb and watch this explode.
        stjohns = Coordinates()
        stjohns.latitude = 47.56494
        stjohns.longitude = -52.70931
        stjohns.lookup_geoname()
        self.assertEqual(stjohns.city, "St. John's")
        
        # Pick 100 random coordinates on the globe, convert them from decimal
        # to sexagesimal and then back, and ensure that they are always equal.
        for i in range(100):
            # Oh, and test altitudes too
            altitude = round(random_coord(1000), 6)
            fraction = float_to_rational(altitude)
            self.assertAlmostEqual(
                abs(altitude),
                fraction.numerator / fraction.denominator,
                3
            )
            
            decimal_lat = round(random_coord(80),  6)
            decimal_lon = round(random_coord(180), 6)
            
            self.assertTrue(valid_coords(decimal_lat, decimal_lon))
            
            dms_lat = decimal_to_dms(decimal_lat)
            dms_lon = decimal_to_dms(decimal_lon)
            
            self.assertEqual(len(dms_lat), 3)
            self.assertEqual(
                dms_lat[0].numerator,
                floor(abs(decimal_lat))
            )
            
            self.assertEqual(len(dms_lon), 3)
            self.assertEqual(
                dms_lon[0].numerator,
                floor(abs(decimal_lon))
            )
            
            self.assertAlmostEqual(
                decimal_lat,
                dms_to_decimal(*rats_to_fracs(dms_lat) + ['N' if decimal_lat >= 0 else 'S']),
                10 # equal to 10 places
            )
            self.assertAlmostEqual(
                decimal_lon,
                dms_to_decimal(*rats_to_fracs(dms_lon) + ['E' if decimal_lon >= 0 else 'W']),
                10 # equal to 10 places
            )
    
    def test_navigation_controller(self):
        """Ensure that it's possible to navigate the map."""
        coords = [[
            map_view.get_property('latitude'),
            map_view.get_property('longitude')
        ]]
        map_view.emit('realize')
        map_view.emit('animation-completed')
        self.assertGreater(len(get_obj('main').get_title()[18:]), 5)
        
        lat = round(random_coord(90),  6)
        lon = round(random_coord(180), 6)
        map_view.center_on(lat, lon)
        coords.append([lat, lon])
        
        self.assertAlmostEqual(coords[0][0], gst_get('history')[-1][0], 5)
        self.assertAlmostEqual(coords[0][1], gst_get('history')[-1][1], 5)
        
        lat = round(random_coord(80),  6)
        lon = round(random_coord(170), 6)
        map_view.center_on(lat, lon)
        
        zoom_in  = get_obj('zoom_in_button')
        zoom_out = get_obj('zoom_out_button')
        map_view.set_zoom_level(0)
        self.assertFalse(zoom_out.get_sensitive())
        self.assertTrue(zoom_in.get_sensitive())
        zoom_in.emit('clicked')
        self.assertTrue(zoom_out.get_sensitive())
        self.assertTrue(zoom_in.get_sensitive())
        self.assertEqual(1, map_view.get_zoom_level())
        zoom_in.emit('clicked')
        self.assertEqual(2, map_view.get_zoom_level())
        zoom_in.emit('clicked')
        self.assertEqual(3, map_view.get_zoom_level())
        zoom_out.emit('clicked')
        self.assertEqual(2, map_view.get_zoom_level())
        map_view.set_zoom_level(map_view.get_max_zoom_level()-1)
        self.assertTrue(zoom_out.get_sensitive())
        self.assertTrue(zoom_in.get_sensitive())
        zoom = map_view.get_zoom_level()
        zoom_in.emit('clicked')
        self.assertTrue(zoom_out.get_sensitive())
        self.assertFalse(zoom_in.get_sensitive())
        self.assertEqual(map_view.get_max_zoom_level(),
            map_view.get_zoom_level())
        
        get_obj("back_button").emit('clicked')
        
        map_view.set_zoom_level(5)
        
        lat = map_view.get_property('latitude')
        lon = map_view.get_property('longitude')
        
        move_by_arrow_keys(None, None, Gdk.keyval_from_name("Left"), None)
        self.assertAlmostEqual(lat, map_view.get_property('latitude'), 4)
        self.assertGreater(    lon, map_view.get_property('longitude'))
        
        move_by_arrow_keys(None, None, Gdk.keyval_from_name("Right"), None)
        self.assertAlmostEqual(lat, map_view.get_property('latitude'), 4)
        self.assertAlmostEqual(lon, map_view.get_property('longitude'), 0)
        
        move_by_arrow_keys(None, None, Gdk.keyval_from_name("Right"), None)
        self.assertLess(       lon, map_view.get_property('longitude'))
        self.assertAlmostEqual(lat, map_view.get_property('latitude'), 4)
        
        move_by_arrow_keys(None, None, Gdk.keyval_from_name("Left"), None)
        self.assertAlmostEqual(lon, map_view.get_property('longitude'), 0)
        self.assertAlmostEqual(lat, map_view.get_property('latitude'), 4)
        
        lon = map_view.get_property('longitude')
        
        move_by_arrow_keys(None, None, Gdk.keyval_from_name("Up"), None)
        self.assertAlmostEqual(lon, map_view.get_property('longitude'), 4)
        self.assertLess(       lat, map_view.get_property('latitude'))
        
        move_by_arrow_keys(None, None, Gdk.keyval_from_name("Down"), None)
        self.assertAlmostEqual(lon, map_view.get_property('longitude'), 4)
        self.assertAlmostEqual(lat, map_view.get_property('latitude'), 0)
        
        move_by_arrow_keys(None, None, Gdk.keyval_from_name("Down"), None)
        self.assertAlmostEqual(lon, map_view.get_property('longitude'), 4)
        self.assertGreater(    lat, map_view.get_property('latitude'))
        
        move_by_arrow_keys(None, None, Gdk.keyval_from_name("Up"), None)
        self.assertAlmostEqual(lon, map_view.get_property('longitude'), 4)
        self.assertAlmostEqual(lat, map_view.get_property('latitude'), 0)
    
    def test_map_objects(self):
        """Test ChamplainMarkers."""
        lat = random_coord(90)
        lon = random_coord(180)
        
        label = gui.labels.add("foobar")
        label.set_location(lat, lon)
        
        self.assertEqual(label.get_latitude(), lat)
        self.assertEqual(label.get_longitude(), lon)
        
        color   = make_clutter_color(gui.prefs.colorpicker.get_current_color())
        polygon = Polygon()
        polygon.set_stroke_color(color)
        self.assertTrue(isinstance(polygon, Champlain.PathLayer))
        self.assertEqual(color.to_string(), polygon.get_stroke_color().to_string())
        
        point = polygon.append_point(0,0,0)
        self.assertTrue(isinstance(point, Champlain.Coordinate))
        self.assertEqual(point.lat, 0)
        self.assertEqual(point.lon, 0)
        self.assertEqual(point.ele, 0)
        
        point = polygon.append_point(45,90,1000)
        self.assertTrue(isinstance(point, Champlain.Coordinate))
        self.assertEqual(point.lat, 45)
        self.assertEqual(point.lon, 90)
        self.assertEqual(point.ele, 1000)
        
        self.assertEqual(len(polygon.get_nodes()), 2)
    
    def test_search(self):
        """Make sure the search box functions."""
        entry = get_obj('search_box')
        
        self.assertEqual(len(gui.search.results), 0)
        
        entry.set_text('jo')
        self.assertEqual(len(gui.search.results), 0)
        
        entry.set_text('edm')
        self.assertEqual(len(gui.search.results), 8)
        
        get_title = get_obj("main").get_title
        for result in gui.search.results:
            gui.search.search_completed(entry, gui.search.results, result.iter, map_view)
            loc, lat, lon = result
            self.assertAlmostEqual(lat, map_view.get_property('latitude'), 4)
            self.assertAlmostEqual(lon, map_view.get_property('longitude'), 4)
            
            map_view.emit("animation-completed")
            self.assertEqual(get_title(), "GottenGeography - " + loc)
        
        entry.set_text('calg')
        self.assertEqual(len(gui.search.results), 411)
    
    def test_preferences(self):
        """Make sure the preferences dialog behaves."""
        gui.prefs.colorpicker.set_current_color(Gdk.Color(0, 0, 0))
        new = gui.prefs.colorpicker.get_current_color()
        self.assertEqual(new.red, 0)
        self.assertEqual(new.green, 0)
        self.assertEqual(new.blue, 0)
        self.assertEqual(list(gst_get('track-color')), [0, 0, 0])
        
        gui.prefs.colorpicker.set_current_color(Gdk.Color(32768, 32768, 32768))
        new = gui.prefs.colorpicker.get_current_color()
        self.assertEqual(new.red, 32768)
        self.assertEqual(new.green, 32768)
        self.assertEqual(new.blue, 32768)
        self.assertEqual(list(gst_get('track-color')), [32768, 32768, 32768])
        
        self.assertEqual(str(gst_get('map-source-id')), "<GLib.Variant('%s')>" %
            map_view.get_property('map-source').get_id())
        for menu_item in get_obj("map_source_menu").get_active().get_group():
            menu_item.set_active(True)
            self.assertEqual(map_view.get_property('map-source').get_name(), menu_item.get_label())

def random_coord(maximum=180):
    """Generate a random number -maximum <= x <= maximum."""
    return (random() * maximum * 2) - maximum

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(
        TestLoader().loadTestsFromTestCase(GottenGeographyTester)
    )
