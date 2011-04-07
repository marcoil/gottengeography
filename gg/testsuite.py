# GottenGeography - Test suite ensures that GottenGeography functions correctly
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

from __future__ import division

from gi.repository import Gdk, Clutter, GObject, Champlain
from unittest import TestCase, TextTestRunner, TestLoader
from os import listdir, getcwd, system, environ
from fractions import Fraction
from random import random
from os.path import join
from math import floor
from time import tzset

import app
from files import Photograph
from utils import Polygon, make_clutter_color
from utils import get_file, gconf_get, gconf_set
from utils import maps_link, valid_coords, Struct
from utils import decimal_to_dms, dms_to_decimal, float_to_rational

# Disable animations so tests pass more quickly.
app.CommonAttributes.slide_to = app.CommonAttributes.map_view.center_on

gui = app.GottenGeography()
get_obj = app.get_obj

class GottenGeographyTester(TestCase):
    def setUp(self):
        """Start the GottenGeography application."""
        # Make the tests work for people outside my time zone.
        system('git checkout demo')
        environ['TZ'] = 'America/Edmonton'
        tzset()
        self.restore = {}
        for key in ('clock_offset', 'history', 'timezone', 'timezone_method', 'track_color'):
            self.restore[key] = gconf_get(key)
        get_obj('system_timezone').clicked()
    
    def tearDown(self):
        """Restore history."""
        system('git checkout demo')
        for key in self.restore:
            gconf_set(key, self.restore[key])
    
    def test_gtk_window(self):
        """Make sure that various widgets were created properly."""
        self.assertEqual(gui.liststore.get_n_columns(), 4)
        self.assertEqual(gui.search.results.get_n_columns(), 3)
        size = get_obj('main').get_size()
        self.assertGreater(size[1], 500)
        self.assertGreater(size[0], 799)
        self.assertEqual(gui.labels.selection.count_selected_rows(), 0)
    
    def test_demo_data(self):
        """Load the demo data and ensure that we're reading it in properly."""
        
        # Start with a fresh state.
        system('git checkout demo')
        self.assertEqual(len(gui.tracks), 0)
        self.assertEqual(len(gui.polygons), 0)
        self.assertEqual(gui.metadata.alpha, float('inf'))
        self.assertEqual(gui.metadata.omega, float('-inf'))
        
        # No buttons should be sensitive yet because nothing's loaded.
        buttons = {}
        for button in ('save', 'revert', 'apply', 'close', 'clear'):
            buttons[button] = get_obj(button + '_button')
            self.assertFalse(buttons[button].get_sensitive())
        
        # Load only the photos first.
        for demo in listdir('./demo/'):
            filename = join(getcwd(), 'demo', demo)
            if demo[-3:] != 'gpx':
                self.assertRaises(IOError, gui.load_gpx_from_file, filename)
                gui.load_img_from_file(filename)
        
        # Nothing is yet selected or modified, so buttons still insensitive.
        for button in buttons.values():
            self.assertFalse(button.get_sensitive())
        
        # Something loaded in the liststore?
        self.assertEqual(len(gui.liststore), 6)
        self.assertTrue(gui.liststore.get_iter_first())
        
        for photo in gui.photo.values():
            self.assertFalse(photo in gui.modified)
            self.assertFalse(photo in gui.selected)
            self.assertFalse(photo.label.get_property('visible'))
            
            # Test that missing the provincestate doesn't break the geoname.
            photo.set_geodata(['Anytown', None, 'US', 'timezone'])
            self.assertEqual(photo.pretty_geoname(), 'Anytown, United States')
            self.assertEqual(photo.timezone, 'timezone')
            
            # Pristine demo data shouldn't have any tags.
            self.assertIsNone(photo.altitude)
            self.assertIsNone(photo.latitude)
            self.assertIsNone(photo.longitude)
            self.assertFalse(photo.manual)
            
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
        self.assertEqual(len(gui.selected), 0)
        select_all.set_active(True)
        self.assertEqual(len(gui.selected), len(gui.liststore))
        select_all.set_active(False)
        self.assertEqual(len(gui.selected), 0)
        
        # Load the GPX
        gpx_filename=join(getcwd(), 'demo', '20101016.gpx')
        self.assertRaises(IOError, gui.load_img_from_file, gpx_filename)
        gui.load_gpx_from_file(gpx_filename)
        self.assertTrue(buttons['clear'].get_sensitive())
        gui.labels.selection.emit('changed')
        
        # Check that the GPX is loaded
        self.assertEqual(len(gui.tracks), 374)
        self.assertEqual(len(gui.polygons), 1)
        self.assertEqual(gui.metadata.alpha, 1287259751)
        self.assertEqual(gui.metadata.omega, 1287260756)
        
        # The save button should be sensitive because loading GPX modifies
        # photos, but nothing is selected so the others are insensitive.
        self.assertTrue(buttons['save'].get_sensitive())
        for button in ('revert', 'apply', 'close'):
            self.assertFalse(buttons[button].get_sensitive())
        
        for photo in gui.photo.values():
            self.assertTrue(photo in gui.modified)
            
            self.assertIsNotNone(photo.latitude)
            self.assertIsNotNone(photo.longitude)
            self.assertTrue(photo.valid_coords())
            self.assertTrue(photo.label.get_property('visible'))
            
            # Play with ChamplainLabels for a bit.
            self.assertEqual(photo.label.get_scale(), (1, 1))
            photo.label.emit("enter-event", Clutter.Event())
            self.assertEqual(photo.label.get_scale(), (1.05, 1.05))
            photo.label.emit("leave-event", Clutter.Event())
            self.assertEqual(photo.label.get_scale(), (1, 1))
            
            # Are Labels clickable?
            photo.label.emit("button-press", Clutter.Event())
            for button in ('save', 'revert', 'apply', 'close'):
                self.assertTrue(buttons[button].get_sensitive())
            self.assertTrue(gui.labels.selection.iter_is_selected(photo.iter))
            self.assertEqual(gui.labels.selection.count_selected_rows(), 1)
            self.assertTrue(photo in gui.selected)
            self.assertEqual(len(gui.selected), 1)
            self.assertEqual(photo.label.get_scale(), (1.1, 1.1))
            self.assertTrue(photo.label.get_selected())
            self.assertEqual(photo.label.get_property('opacity'), 255)
            
            # Make sure the Labels that we didn't click on are deselected.
            for other in gui.photo.values():
                if other.filename == photo.filename: continue
                self.assertFalse(gui.labels.selection.iter_is_selected(other.iter))
                self.assertFalse(other in gui.selected)
                self.assertEqual(other.label.get_scale(), (1, 1))
                self.assertFalse(other.label.get_selected())
                self.assertEqual(other.label.get_property('opacity'), 64)
        
        # Unload the GPX data.
        buttons['clear'].emit('clicked')
        self.assertEqual(len(gui.tracks), 0)
        self.assertEqual(len(gui.polygons), 0)
        self.assertFalse(buttons['clear'].get_sensitive())
        
        # Save all photos
        buttons['save'].emit('clicked')
        self.assertEqual(len(gui.modified), 0)
        for button in ('save', 'revert'):
            self.assertFalse(buttons[button].get_sensitive())
        
        gui.labels.selection.select_all()
        self.assertEqual(len(gui.selected), 6)
        for button in ('save', 'revert'):
            self.assertFalse(buttons[button].get_sensitive())
        for button in ('apply', 'close'):
            self.assertTrue(buttons[button].get_sensitive())
        
        # Close all the photos.
        files = [photo.filename for photo in gui.selected]
        buttons['close'].emit('clicked')
        for button in ('save', 'revert', 'apply', 'close'):
            self.assertFalse(buttons[button].get_sensitive())
        self.assertEqual(len(gui.photo), 0)
        self.assertEqual(len(gui.modified), 0)
        self.assertEqual(len(gui.selected), 0)
        
        # Re-read the photos back from disk to make sure that the saving
        # was successful.
        for filename in files:
            photo = Photograph(filename, lambda x: None)
            photo.read()
            self.assertTrue(photo.valid_coords())
            self.assertGreater(photo.altitude, 600)
            self.assertEqual(photo.pretty_geoname(), 'Edmonton, Alberta, Canada')
    
    def test_auto_timestamp(self):
        """Ensure that we can determine the correct timezone if it is set incorrectly."""
        environ['TZ'] = 'Europe/Paris'
        tzset()
        get_obj('lookup_timezone').clicked()
        self.test_demo_data()
        environ['TZ'] = 'America/Edmonton'
        tzset()
    
    def test_string_functions(self):
        """Ensure that strings print properly."""
        environ['TZ'] = 'America/Edmonton'
        tzset()
        
        # Make a photo with a dummy ChamplainLabel.
        label = Struct()
        label.get_text = lambda: get_file('../demo/IMG_2411.JPG')
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
    
    def test_map_navigation(self):
        """Ensure that it's possible to navigate the map."""
        
        coords = [[
            gui.map_view.get_property('latitude'),
            gui.map_view.get_property('longitude')
        ]]
        gui.map_view.emit('realize')
        
        lat = round(random_coord(90),  6)
        lon = round(random_coord(180), 6)
        gui.map_view.center_on(lat, lon)
        coords.append([lat, lon])
        
        self.assertAlmostEqual(coords[0][0], gconf_get('history')[-1][0], 5)
        self.assertAlmostEqual(coords[0][1], gconf_get('history')[-1][1], 5)
        
        lat = round(random_coord(80),  6)
        lon = round(random_coord(170), 6)
        gui.map_view.center_on(lat, lon)
        
        zoom_in  = get_obj('zoom_in_button')
        zoom_out = get_obj('zoom_out_button')
        gui.map_view.set_zoom_level(0)
        self.assertFalse(zoom_out.get_sensitive())
        self.assertTrue(zoom_in.get_sensitive())
        zoom_in.emit('clicked')
        self.assertTrue(zoom_out.get_sensitive())
        self.assertTrue(zoom_in.get_sensitive())
        self.assertEqual(1, gui.map_view.get_zoom_level())
        zoom_in.emit('clicked')
        self.assertEqual(2, gui.map_view.get_zoom_level())
        zoom_in.emit('clicked')
        self.assertEqual(3, gui.map_view.get_zoom_level())
        zoom_out.emit('clicked')
        self.assertEqual(2, gui.map_view.get_zoom_level())
        gui.map_view.set_zoom_level(gui.map_view.get_max_zoom_level()-1)
        self.assertTrue(zoom_out.get_sensitive())
        self.assertTrue(zoom_in.get_sensitive())
        zoom = gui.map_view.get_zoom_level()
        zoom_in.emit('clicked')
        self.assertTrue(zoom_out.get_sensitive())
        self.assertFalse(zoom_in.get_sensitive())
        self.assertEqual(gui.map_view.get_max_zoom_level(),
            gui.map_view.get_zoom_level())
        
        get_obj("back_button").emit('clicked')
        
        gui.map_view.set_zoom_level(5)
        
        lat = gui.map_view.get_property('latitude')
        lon = gui.map_view.get_property('longitude')
        
        gui.navigator.move_by_arrow_keys(None, None, Gdk.keyval_from_name("Left"), None)
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 4)
        self.assertGreater(    lon, gui.map_view.get_property('longitude'))
        
        gui.navigator.move_by_arrow_keys(None, None, Gdk.keyval_from_name("Right"), None)
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 4)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 0)
        
        gui.navigator.move_by_arrow_keys(None, None, Gdk.keyval_from_name("Right"), None)
        self.assertLess(       lon, gui.map_view.get_property('longitude'))
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 4)
        
        gui.navigator.move_by_arrow_keys(None, None, Gdk.keyval_from_name("Left"), None)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 0)
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 4)
        
        lon = gui.map_view.get_property('longitude')
        
        gui.navigator.move_by_arrow_keys(None, None, Gdk.keyval_from_name("Up"), None)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 4)
        self.assertLess(       lat, gui.map_view.get_property('latitude'))
        
        gui.navigator.move_by_arrow_keys(None, None, Gdk.keyval_from_name("Down"), None)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 4)
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 0)
        
        gui.navigator.move_by_arrow_keys(None, None, Gdk.keyval_from_name("Down"), None)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 4)
        self.assertGreater(    lat, gui.map_view.get_property('latitude'))
        
        gui.navigator.move_by_arrow_keys(None, None, Gdk.keyval_from_name("Up"), None)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 4)
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 0)
    
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
    
    def test_gconf(self):
        """Read and write some stuff from GConf."""
        history = gconf_get("history")
        
        gconf_set('history', [[0,0,0]])
        self.assertEqual(gconf_get('history'), [[0,0,0]])
        gconf_set('history', [[50,-113,11]])
        self.assertEqual(gconf_get('history'), [[50,-113,11]])
        
        gconf_set('ran_testsuite', True)
        self.assertTrue(gconf_get('ran_testsuite', False))
        
        gconf_set('history', history)
    
    def test_time_offset(self):
        """Fiddle with the time offset setting."""
        minutes = get_obj("minutes")
        seconds = get_obj("seconds")
        seconds.set_value(0)
        minutes.set_value(0)
        self.assertEqual(gui.metadata.delta, 0)
        minutes.set_value(1)
        self.assertEqual(gui.metadata.delta, 60)
        seconds.set_value(1)
        self.assertEqual(gui.metadata.delta, 61)
        
        seconds.set_value(59)
        self.assertEqual(gui.metadata.delta, 119)
        minutes.set_value(59)
        self.assertEqual(gui.metadata.delta, 3599)
        
        seconds.set_value(60)
        self.assertEqual(seconds.get_value(), 0)
        self.assertEqual(minutes.get_value(), 60)
        self.assertEqual(gui.metadata.delta, 3600)
    
    def test_search(self):
        """Make sure the search box functions."""
        entry = get_obj('search')
        
        self.assertEqual(len(gui.search.results), 0)
        
        entry.set_text('jo')
        self.assertEqual(len(gui.search.results), 0)
        
        entry.set_text('edm')
        self.assertEqual(len(gui.search.results), 8)
        
        entry.set_text('calg')
        self.assertEqual(len(gui.search.results), 339)
        
        for result in gui.search.results:
            gui.search.search_completed(entry, gui.search.results, result.iter, gui.map_view)
            loc, lat, lon = result
            self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 4)
            self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 4)
    
    def test_preferences(self):
        """Make sure the preferences dialog behaves."""
        gui.prefs.colorpicker.set_current_color(Gdk.Color(0, 0, 0))
        new = gui.prefs.colorpicker.get_current_color()
        self.assertEqual(new.red, 0)
        self.assertEqual(new.green, 0)
        self.assertEqual(new.blue, 0)
        self.assertEqual(gconf_get('track_color'), [0, 0, 0])
        
        gui.prefs.colorpicker.set_current_color(Gdk.Color(32768, 32768, 32768))
        new = gui.prefs.colorpicker.get_current_color()
        self.assertEqual(new.red, 32768)
        self.assertEqual(new.green, 32768)
        self.assertEqual(new.blue, 32768)
        self.assertEqual(gconf_get('track_color'), [32768, 32768, 32768])

def random_coord(maximum=180):
    """Generate a random number -maximum <= x <= maximum."""
    return (random() * maximum * 2) - maximum

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(
        TestLoader().loadTestsFromTestCase(GottenGeographyTester)
    )
