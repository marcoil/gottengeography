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

from unittest import TestCase, TextTestRunner, TestLoader
from os import listdir, getcwd, system, environ
from gi.repository import Gdk, Clutter
from random import random
from os.path import join
from math import floor
from time import tzset
from re import search

import app
from datatypes import *
from gps import *

gui = app.GottenGeography()
get_obj = app.get_obj

class GottenGeographyTester(TestCase):
    def setUp(self):
        """Start the GottenGeography application."""
        # Make the tests work for people outside my time zone.
        environ["TZ"] = "America/Edmonton"
        tzset()
        self.history = gconf_get("history")
        get_obj("system_timezone").clicked()
    
    def tearDown(self):
        """Restore history."""
        gconf_set("history", self.history)
    
    def test_gtk_window(self):
        """Make sure that various widgets were created properly."""
        self.assertEqual(gui.liststore.get_n_columns(), 4)
        self.assertEqual(gui.search_results.get_n_columns(), 3)
        self.assertEqual(get_obj("main").get_size(), (800, 600))
        
        # Button sensitivity
        self.assertFalse(get_obj("apply_button").get_sensitive())
        self.assertFalse(get_obj("close_button").get_sensitive())
        self.assertFalse(get_obj("save_button").get_sensitive())
        self.assertFalse(get_obj("revert_button").get_sensitive())
        self.assertFalse(get_obj("clear_button").get_sensitive())
        gui.selected.add(True)
        gui.modified.add(True)
        gui.tracks["herp"] = "derp"
        gui.update_sensitivity()
        self.assertTrue(get_obj("apply_button").get_sensitive())
        self.assertTrue(get_obj("close_button").get_sensitive())
        self.assertTrue(get_obj("save_button").get_sensitive())
        self.assertTrue(get_obj("revert_button").get_sensitive())
        self.assertTrue(get_obj("clear_button").get_sensitive())
    
    def test_demo_data(self):
        """Load the demo data and ensure that we're reading it in properly."""
        system("git checkout demo")
        self.assertEqual(len(gui.tracks), 0)
        self.assertEqual(len(gui.gpx), 0)
        self.assertEqual(gui.metadata['alpha'], float('inf'))
        self.assertEqual(gui.metadata['omega'], float('-inf'))
        
        # Load only the photos first
        for demo in listdir('./demo/'):
            filename = join(getcwd(), "demo", demo)
            if not search(r'gpx$', demo):
                self.assertRaises(IOError, gui.load_gpx_from_file, filename)
                gui.load_img_from_file(filename)
        
        treeiter = gui.liststore.get_iter_first()
        self.assertTrue(treeiter)
        
        for filename in gui.photo:
            self.assertFalse(filename in gui.modified)
            self.assertFalse(filename in gui.selected)
            
            self.assertIsNone(gui.photo[filename].altitude)
            self.assertIsNone(gui.photo[filename].latitude)
            self.assertIsNone(gui.photo[filename].longitude)
            self.assertFalse(gui.photo[filename].manual)
            gui.photo[filename].manual = True
            gui.photo[filename].latitude = 10.0
            gui.photo[filename].altitude = 650
            gui.photo[filename].latitude = 45.0
            gui.photo[filename].read()
            self.assertIsNone(gui.photo[filename].altitude)
            self.assertIsNone(gui.photo[filename].latitude)
            self.assertIsNone(gui.photo[filename].longitude)
            self.assertFalse(gui.photo[filename].manual)
            self.assertEqual(filename, gui.photo[filename].marker.get_name())
            self.assertEqual(gui.photo[filename].timestamp,
                gui.liststore.get_value(
                    gui.photo[filename].iter, app.TIMESTAMP
                )
            )
        
        select_all = get_obj("select_all_button")
        self.assertEqual(len(gui.selected), 0)
        select_all.set_active(True)
        self.assertEqual(len(gui.selected), 6)
        select_all.set_active(False)
        self.assertEqual(len(gui.selected), 0)
        
        # Load the GPX
        gpx_filename=join(getcwd(), "demo", "20101016.gpx")
        self.assertRaises(IOError, gui.load_img_from_file, gpx_filename)
        gui.load_gpx_from_file(gpx_filename)
        
        # Check that the GPX is loaded
        self.assertEqual(len(gui.tracks), 374)
        self.assertEqual(len(gui.gpx), 1)
        self.assertEqual(len(gui.gpx[0].polygons), 1)
        self.assertEqual(len(gui.gpx[0].tracks), 374)
        self.assertEqual(gui.gpx[0].alpha, 1287259751)
        self.assertEqual(gui.gpx[0].omega, 1287260756)
        self.assertEqual(gui.metadata['alpha'], 1287259751)
        self.assertEqual(gui.metadata['omega'], 1287260756)
        self.assertEqual(
            gui.gpx[0].area,
            [53.522495999999997, -113.453148,
             53.537399000000001, -113.443061]
        )
        
        for photo in gui.photo.values():
            self.assertTrue(photo in gui.modified)
            
            self.assertIsNotNone(photo.latitude)
            self.assertIsNotNone(photo.longitude)
            
            self.assertEqual(photo.marker.get_scale(), (1, 1))
            gui.marker_mouse_in(photo.marker, None)
            self.assertEqual(photo.marker.get_scale(), (1.05, 1.05))
            gui.marker_mouse_out(photo.marker, None)
            self.assertEqual(photo.marker.get_scale(), (1, 1))
            
            gui.marker_clicked(photo.marker, Clutter.Event())
            self.assertTrue(gui.listsel.iter_is_selected(photo.iter))
            self.assertEqual(gui.listsel.count_selected_rows(), 1)
            self.assertTrue(photo in gui.selected)
            self.assertEqual(len(gui.selected), 1)
            self.assertEqual(photo.marker.get_scale(), (1.1, 1.1))
            self.assertTrue(photo.marker.get_highlighted())
            
            for other in gui.photo.values():
                if other.filename == photo.filename: continue
                self.assertFalse(gui.listsel.iter_is_selected(other.iter))
                self.assertFalse(other in gui.selected)
                self.assertEqual(other.marker.get_scale(), (1, 1))
                self.assertFalse(other.marker.get_highlighted())
            
            photo.set_marker_highlight(None, True)
            self.assertEqual(photo.marker.get_property('opacity'), 64)
            self.assertFalse(photo.marker.get_highlighted())
            photo.set_marker_highlight([0,0,0,0,False], False)
            self.assertEqual(photo.marker.get_property('opacity'), 255)
            self.assertTrue(photo.marker.get_highlighted())
        
        gui.clear_all_gpx()
        self.assertEqual(len(gui.gpx), 0)
        self.assertEqual(len(gui.tracks), 0)
        
        gui.save_all_files()
        self.assertEqual(len(gui.modified), 0)
        
        gui.listsel.select_all()
        self.assertEqual(len(gui.selected), 6)
        files = [photo.filename for photo in gui.selected]
        gui.close_selected_photos()
        self.assertEqual(len(gui.photo), 0)
        self.assertEqual(len(gui.modified), 0)
        self.assertEqual(len(gui.selected), 0)
        
        for filename in files:
            photo = Photograph(filename, gui.geonamer, gui.modify_summary)
            self.assertTrue(photo.valid_coords())
            self.assertGreater(photo.altitude, 600)
            self.assertEqual(photo.City, "Edmonton")
            self.assertEqual(photo.ProvinceState, "Alberta")
            self.assertEqual(photo.CountryName, "Canada")
    
    def test_auto_timestamp(self):
        """Ensure that we can determine the correct timezone if it is set incorrectly."""
        environ["TZ"] = "Europe/Paris"
        tzset()
        get_obj("lookup_timezone").clicked()
        self.test_demo_data()
        environ["TZ"] = "America/Edmonton"
        tzset()
    
    def test_string_functions(self):
        """Ensure that strings print properly."""
        environ["TZ"] = "America/Edmonton"
        tzset()
        
        marker = ReadableDictionary()
        marker.get_text = lambda: get_file('../demo/IMG_2411.JPG')
        photo = Photograph(marker.get_text(), gui.geonamer, gui.modify_summary)
        photo.marker = marker
        
        for iptc in iptc_keys:
            photo[iptc] = None
        
        photo.latitude  = None
        photo.longitude = None
        self.assertEqual(photo.pretty_coords(), "Not geotagged")
        photo.latitude  = 10.0
        photo.longitude = 10.0
        self.assertEqual(photo.pretty_coords(), "N 10.00000, E 10.00000")
        photo.latitude  = -10.0
        photo.longitude = -10.0
        self.assertEqual(photo.pretty_coords(), "S 10.00000, W 10.00000")
        
        photo.timestamp = None
        self.assertIsNone(photo.pretty_time())
        photo.timestamp = 999999999
        self.assertEqual(photo.pretty_time(), "2001-09-08 07:46:39 PM")
        
        photo.altitude = None
        self.assertIsNone(photo.pretty_elevation())
        photo.altitude = -10.20005
        self.assertEqual(photo.pretty_elevation(), "10.2m below sea level")
        photo.altitude = 600.71
        self.assertEqual(photo.pretty_elevation(), "600.7m above sea level")
        
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
            maps_link(10.0, 10.0),
            r'href="http://maps.google.com'
        )
        
        gui.display_actors()
        self.assertRegexpMatches(
            get_obj("maps_link").get_label(),
            r'href="http://maps.google.com'
        )
    
    def test_gps_math(self):
        """Test coordinate conversion functions."""
        
        # Really important that this method is bulletproof
        self.assertFalse(valid_coords(None, None))
        self.assertFalse(valid_coords("", ""))
        self.assertFalse(valid_coords(True, True))
        self.assertFalse(valid_coords(False, False))
        self.assertFalse(valid_coords(45, 270))
        self.assertFalse(valid_coords(100, 50))
        self.assertFalse(valid_coords([], 50))
        self.assertFalse(valid_coords(45, {'grunt':42}))
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
                dms_to_decimal(*dms_lat + ["N" if decimal_lat >= 0 else "S"]),
                10 # equal to 10 places
            )
            self.assertAlmostEqual(
                decimal_lon,
                dms_to_decimal(*dms_lon + ["E" if decimal_lon >= 0 else "W"]),
                10 # equal to 10 places
            )
    
    def test_map_navigation(self):
        """Ensure that it's possible to navigate the map."""
        
        history_length = len(gui.history)
        
        self.assertEqual(history_length, len(gui.history))
        gui.remember_location()
        self.assertEqual(history_length + 1, len(gui.history))
        
        coords = []
        
        coords.append([
            gui.map_view.get_property('latitude'),
            gui.map_view.get_property('longitude')
        ])
        
        lat = round(random_coord(90),  6)
        lon = round(random_coord(180), 6)
        
        gui.map_view.center_on(lat, lon)
        
        coords.append([lat, lon])
        zoom = gui.map_view.get_zoom_level()
        
        gui.remember_location()
        self.assertEqual(history_length + 2, len(gui.history))
        self.assertAlmostEqual(lat, gui.history[-1][0], 1)
        self.assertAlmostEqual(lon, gui.history[-1][1], 1)
        
        lat = round(random_coord(90),  6)
        lon = round(random_coord(180), 6)
        
        gui.map_view.center_on(lat, lon)
        
        zoom_in  = get_obj("zoom_in_button")
        zoom_out = get_obj("zoom_out_button")
        gui.map_view.set_zoom_level(0)
        gui.zoom_button_sensitivity()
        self.assertFalse(zoom_out.get_sensitive())
        self.assertTrue(zoom_in.get_sensitive())
        gui.zoom_in()
        self.assertTrue(zoom_out.get_sensitive())
        self.assertTrue(zoom_in.get_sensitive())
        self.assertEqual(1, gui.map_view.get_zoom_level())
        gui.zoom_in()
        self.assertEqual(2, gui.map_view.get_zoom_level())
        gui.zoom_in()
        self.assertEqual(3, gui.map_view.get_zoom_level())
        gui.zoom_out()
        self.assertEqual(2, gui.map_view.get_zoom_level())
        gui.map_view.set_zoom_level(gui.map_view.get_max_zoom_level()-1)
        self.assertTrue(zoom_out.get_sensitive())
        self.assertTrue(zoom_in.get_sensitive())
        gui.zoom_in()
        self.assertTrue(zoom_out.get_sensitive())
        self.assertFalse(zoom_in.get_sensitive())
        self.assertEqual(gui.map_view.get_max_zoom_level(),
            gui.map_view.get_zoom_level())
        
        gui.return_to_last(get_obj("back_button"))
        self.assertEqual(history_length + 1, len(gui.history))
        self.assertEqual(zoom, gui.map_view.get_zoom_level())
        
        gui.return_to_last(get_obj("back_button"))
        self.assertEqual(history_length, len(gui.history))
        
        gui.map_view.set_zoom_level(5)
        
        lat = gui.map_view.get_property('latitude')
        lon = gui.map_view.get_property('longitude')
        
        gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Left"), None)
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 4)
        self.assertGreater(    lon, gui.map_view.get_property('longitude'))
        
        gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Right"), None)
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 4)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 0)
        
        gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Right"), None)
        self.assertLess(       lon, gui.map_view.get_property('longitude'))
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 4)
        
        gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Left"), None)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 0)
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 4)
        
        lon = gui.map_view.get_property('longitude')
        
        gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Up"), None)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 4)
        self.assertLess(       lat, gui.map_view.get_property('latitude'))
        
        gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Down"), None)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 4)
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 0)
        
        gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Down"), None)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 4)
        self.assertGreater(    lat, gui.map_view.get_property('latitude'))
        
        gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Up"), None)
        self.assertAlmostEqual(lon, gui.map_view.get_property('longitude'), 4)
        self.assertAlmostEqual(lat, gui.map_view.get_property('latitude'), 0)
    
    def test_map_objects(self):
        """Test ChamplainMarkers."""
        
        lat = random_coord(90)
        lon = random_coord(180)
        
        marker = gui.add_marker("foobar")
        marker.set_position(lat, lon)
        
        self.assertEqual(marker.get_latitude(), lat)
        self.assertEqual(marker.get_longitude(), lon)
        
        self.assertTrue(marker.get_parent())
        
        marker.destroy()
        
        self.assertFalse(marker.get_parent())
    
    def test_gconf(self):
        history = gconf_get("history")
        
        gconf_set('history', [[0,0,0]])
        self.assertEqual(gconf_get('history'), [[0,0,0]])
        gconf_set('history', [[50,-113,11]])
        self.assertEqual(gconf_get('history'), [[50,-113,11]])
        
        lat = random_coord(90)
        lon = random_coord(180)
        
        gui.map_view.center_on(lat, lon)
        
        gui.remember_location()
        
        gconf_val = gconf_get("history")
        self.assertAlmostEqual(lat, gconf_val[-1][0], 4)
        self.assertAlmostEqual(lon, gconf_val[-1][1], 4)
        self.assertEqual(gui.map_view.get_zoom_level(), gconf_val[-1][2])
        
        gconf_set('history', history)
    
    def test_time_offset(self):
        """Fiddle with the time offset setting."""
        minutes = get_obj("minutes")
        seconds = get_obj("seconds")
        seconds.set_value(0)
        minutes.set_value(0)
        self.assertEqual(gui.metadata['delta'], 0)
        minutes.set_value(1)
        self.assertEqual(gui.metadata['delta'], 60)
        seconds.set_value(1)
        self.assertEqual(gui.metadata['delta'], 61)
        
        seconds.set_value(59)
        self.assertEqual(gui.metadata['delta'], 119)
        minutes.set_value(59)
        self.assertEqual(gui.metadata['delta'], 3599)
        
        seconds.set_value(60)
        self.assertEqual(seconds.get_value(), 0)
        self.assertEqual(minutes.get_value(), 60)
        self.assertEqual(gui.metadata['delta'], 3600)

def random_coord(maximum=180):
    """Generate a random number -maximum <= x <= maximum."""
    return (random() * maximum * 2) - maximum

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(
        TestLoader().loadTestsFromTestCase(GottenGeographyTester)
    )
