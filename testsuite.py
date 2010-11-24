#!/usr/bin/env python
# coding=utf-8

from __future__ import division
import unittest, os, re, datetime, time, math, random
from gottengeography import GottenGeography
from xml.parsers.expat import ExpatError
from gi.repository import Gdk, Clutter

class GottenGeographyTester(unittest.TestCase):
    def setUp(self):
        """Start the GottenGeography application."""
        
        # Make the tests work for people outside my time zone.
        os.environ["TZ"] = "America/Edmonton"
        
        self.gui = GottenGeography(animate_crosshair=False)
        # TODO add code to do a git checkout of the demo data so that
        # it's always pristine.
    
    def test_gtk_window(self):
        """Make sure that various widgets were created properly."""
        
        self.assertEqual(
            str(type(self.gui.gconf_client)), 
            "<class 'gi.repository.GConf.Client'>"
        )
        
        self.assertEqual(self.gui.loaded_photos.get_n_columns(), 4)
        self.assertEqual(self.gui.window.get_size(), (900, 700))
        
        self.assertTrue(self.gui.app_container.get_visible())
        
        self.assertEqual(len(self.gui.button), 11)
        self.assertEqual(len(self.gui.offset), 3)
    
    def test_demo_data(self):
        """Load the demo data and ensure that we're reading it in properly."""
        
        self.assertEqual(len(self.gui.tracks), 0)
        self.assertEqual(len(self.gui.polygons), 0)
        self.assertEqual(self.gui.metadata['alpha'], float('inf'))
        self.assertEqual(self.gui.metadata['omega'], float('-inf'))
        self.assertEqual(
            self.gui.metadata['area'],
            [float('inf'), float('inf'), float('-inf'), float('-inf'), False]
        )
        
        # Load only the photos first
        os.chdir('./demo/')
        for demo in os.listdir('.'):
            filename = "%s/%s" % (os.getcwd(), demo)
            if not re.search(r'gpx$', demo):
                self.assertRaises(ExpatError,
                    self.gui.load_gpx_from_file,
                    filename
                )
                self.gui.add_or_reload_photo(
                    filename=filename,
                    data=[[], 1]
                )
        
        iter = self.gui.loaded_photos.get_iter_first()
        self.assertTrue(iter[0])
        
        filename = self.gui.loaded_photos.get_value(iter[1], self.gui.PATH)
        # Test that a photo has no coordinates to begin with
        self.assertIsNone(self.gui.photo[filename].latitude)
        self.assertIsNone(self.gui.photo[filename].longitude)
        
        # Load the GPX
        gpx_filename="%s/%s" % (os.getcwd(), "20101016.gpx")
        self.assertRaises(IOError,
            self.gui.add_or_reload_photo,
            filename=gpx_filename,
            data=[[], 1]
        )
        self.gui.load_gpx_from_file(gpx_filename)
        
        # Check that the GPX is loaded
        self.assertEqual(len(self.gui.tracks),   374)
        self.assertEqual(len(self.gui.polygons), 1)
        self.assertEqual(self.gui.metadata['alpha'], 1287259751)
        self.assertEqual(self.gui.metadata['omega'], 1287260756)
        self.assertEqual(
            self.gui.metadata['area'],
            [53.522495999999997, -113.453148,
             53.537399000000001, -113.443061, False]
        )
        
        photo = self.gui.photo[filename]
        self.assertAlmostEqual(photo.latitude,   53.529963999999993, 9)
        self.assertAlmostEqual(photo.longitude, -113.44800866666665, 9)
        
        self.assertEqual(photo.marker.get_scale(), (1, 1))
        self.gui.marker_mouse_in(photo.marker, None)
        self.assertEqual(photo.marker.get_scale(), (1.05, 1.05))
        self.gui.marker_mouse_out(photo.marker, None)
        self.assertEqual(photo.marker.get_scale(), (1, 1))
        
        self.gui.marker_clicked(photo.marker, Clutter.Event())
        self.assertTrue(self.gui.photo_selection.iter_is_selected(photo.iter))
        self.assertEqual(self.gui.photo_selection.count_selected_rows(), 1)
        self.assertEqual(photo.marker.get_scale(), (1.2, 1.2))
        
        self.gui.set_marker_highlight(self.gui.loaded_photos, None, photo.iter, (None, True))
        self.assertEqual(photo.marker.get_property('opacity'), 64)
        self.assertFalse(photo.marker.get_highlighted())
        self.gui.set_marker_highlight(self.gui.loaded_photos, None, photo.iter, ([0,0,0,0,False], False))
        self.assertEqual(photo.marker.get_property('opacity'), 255)
        self.assertTrue(photo.marker.get_highlighted())
    
    def test_string_functions(self):
        """Ensure that strings print properly."""
        
        self.assertEqual(
            self.gui.pretty_coords(None, None),
            "Not geotagged"
        )
        self.assertEqual(
            self.gui.pretty_coords(10.0, 10.0),
            "N 10.00000, E 10.00000"
        )
        self.assertEqual(
            self.gui.pretty_coords(-10.0, -10.0),
            "S 10.00000, W 10.00000"
        )
        
        self.assertEqual(
            self.gui.pretty_time(999999999),
            "2001-09-08 07:46:39 PM"
        )
        self.assertEqual(
            self.gui.pretty_time(None),
            "No timestamp"
        )
        
        self.assertEqual(
            self.gui.pretty_elevation(None),
            ""
        )
        self.assertEqual(
            self.gui.pretty_elevation(-10.20005),
            "10.2m below sea level"
        )
        self.assertEqual(
            self.gui.pretty_elevation(600.71),
            "600.7m above sea level"
        )
        
        self.assertEqual(self.gui.maps_link(None, None, 'foo'), 'foo')
        self.assertRegexpMatches(self.gui.maps_link(10.0, 10.0), r'href="http://maps.google.com')
        
        self.gui.display_coords()
        self.assertRegexpMatches(self.gui.coords_label.get_label(), r'href="http://maps.google.com')
    
    def test_gps_math(self):
        """Test coordinate conversion functions."""
        
        # Really important that this method is bulletproof
        self.assertFalse(self.gui.valid_coords(None, None))
        self.assertFalse(self.gui.valid_coords("", ""))
        self.assertFalse(self.gui.valid_coords(True, True))
        self.assertFalse(self.gui.valid_coords(False, False))
        self.assertFalse(self.gui.valid_coords(45, 270))
        self.assertFalse(self.gui.valid_coords(100, 50))
        self.assertFalse(self.gui.valid_coords([], 50))
        self.assertFalse(self.gui.valid_coords(45, {'grunt':42}))
        self.assertFalse(self.gui.valid_coords("ya", "dun goofed"))
        
        # Pick 100 random coordinates on the globe, convert them from decimal
        # to sexagesimal and then back, and ensure that they are always equal.
        for i in range(100):
            # Oh, and test altitudes too
            altitude = round(abs(random_coord(100)), 6)
            fraction = self.gui.float_to_rational(altitude)
            self.assertAlmostEqual(
                altitude,
                fraction.numerator / fraction.denominator,
                3
            )
            
            decimal_lat = round(random_coord(90),  6)
            decimal_lon = round(random_coord(180), 6)
            
            self.assertTrue(self.gui.valid_coords(decimal_lat, decimal_lon))
            
            dms_lat = self.gui.decimal_to_dms(decimal_lat, True)
            dms_lon = self.gui.decimal_to_dms(decimal_lon, False)
            
            self.assertEqual(len(dms_lat),    2)
            self.assertEqual(len(dms_lat[0]), 3)
            self.assertEqual(
                dms_lat[0][0].numerator,
                math.floor(abs(decimal_lat))
            )
            
            self.assertEqual(len(dms_lon),    2)
            self.assertEqual(len(dms_lon[0]), 3)
            self.assertEqual(
                dms_lon[0][0].numerator,
                math.floor(abs(decimal_lon))
            )
            
            self.assertAlmostEqual(
                decimal_lat, 
                self.gui.dms_to_decimal(*dms_lat), 
                10 # equal to 10 places
            )
            self.assertAlmostEqual(
                decimal_lon, 
                self.gui.dms_to_decimal(*dms_lon), 
                10 # equal to 10 places
            )
    
    def test_map_navigation(self):
        """Ensure that it's possible to navigate the map."""
        
        history_length = len(self.gui.history)
        
        self.assertEqual(history_length, 0)
        self.gui.remember_location()
        self.assertEqual(history_length + 1, len(self.gui.history))
        
        coords = []
        
        coords.append([
            self.gui.map_view.get_property('latitude'),
            self.gui.map_view.get_property('longitude')
        ])
        
        lat = round(random_coord(90),  6)
        lon = round(random_coord(180), 6)
        
        self.gui.map_view.center_on(lat, lon)
        
        coords.append([lat, lon])
        zoom = self.gui.map_view.get_zoom_level()
        
        self.gui.remember_location()
        self.assertEqual(history_length + 2, len(self.gui.history))
        self.assertAlmostEqual(lat, self.gui.history[-1][0], 1)
        self.assertAlmostEqual(lon, self.gui.history[-1][1], 1)
        
        lat = round(random_coord(90),  6)
        lon = round(random_coord(180), 6)
        
        self.gui.map_view.center_on(lat, lon)
        
        self.gui.map_view.set_zoom_level(1)
        self.gui.zoom_in()
        self.assertEqual(2, self.gui.map_view.get_zoom_level())
        self.gui.zoom_in()
        self.assertEqual(3, self.gui.map_view.get_zoom_level())
        self.gui.zoom_out()
        self.assertEqual(2, self.gui.map_view.get_zoom_level())
        
        self.gui.return_to_last()
        self.assertEqual(history_length + 1, len(self.gui.history))
        self.assertEqual(zoom, self.gui.map_view.get_zoom_level())
        
        self.gui.return_to_last()
        self.assertEqual(history_length, len(self.gui.history))
        
        self.gui.map_view.set_zoom_level(5)
        
        lat = self.gui.map_view.get_property('latitude')
        lon = self.gui.map_view.get_property('longitude')
        
        self.gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Left"), None)
        self.assertGreater(lon, self.gui.map_view.get_property('longitude'))
        
        self.gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Right"), None)
        #self.assertAlmostEqual(lon, self.gui.map_view.get_property('longitude'), 5)
        self.gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Right"), None)
        self.assertLess(lon, self.gui.map_view.get_property('longitude'))
        
        self.gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Left"), None)
        #self.assertAlmostEqual(lon, self.gui.map_view.get_property('longitude'), 5)
        
        self.gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Up"), None)
        #self.assertAlmostEqual(lon, self.gui.map_view.get_property('longitude'), 5)
        self.assertLess(lat, self.gui.map_view.get_property('latitude'))
        
        self.gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Down"), None)
        #self.assertAlmostEqual(lon, self.gui.map_view.get_property('longitude'), 5)
        
        self.gui.move_map_view_by_arrow_keys(None, None, Gdk.keyval_from_name("Down"), None)
        #self.assertAlmostEqual(lon, self.gui.map_view.get_property('longitude'), 5)
        self.assertGreater(lat, self.gui.map_view.get_property('latitude'))
    
    def test_map_objects(self):
        """Put a marker on the map, and then take it off."""
        
        lat = random_coord(90)
        lon = random_coord(180)
        
        marker = self.gui.add_marker("foobar", lat, lon)
        
        self.assertEqual(marker.get_property('latitude'), lat)
        self.assertEqual(marker.get_property('longitude'), lon)
        
        self.assertTrue(marker.get_parent())
        
        marker.destroy()
        
        self.assertFalse(marker.get_parent())
        
        self.assertEqual(len(self.gui.polygons), 0)
        self.gui.create_polygon()
        self.assertEqual(self.gui.polygons[-1].get_stroke_width(), 5)
        self.assertEqual(len(self.gui.polygons), 1)
        self.gui.create_polygon()
        self.assertEqual(self.gui.polygons[-1].get_stroke_width(), 5)
        self.assertEqual(len(self.gui.polygons), 2)
    
    def test_gconf(self):
        self.assertEqual(
            self.gui.gconf_key('foobar'),
            '/apps/gottengeography/foobar'
        )
        
        orig_lat = self.gui.gconf_get('last_latitude', float)
        orig_lon = self.gui.gconf_get('last_longitude', float)
        orig_zoom = self.gui.gconf_get('last_zoom_level', int)
        
        self.gui.gconf_set('last_zoom_level', 0)
        self.assertEqual(self.gui.gconf_get('last_zoom_level', int), 0)
        self.gui.gconf_set('last_zoom_level', 3)
        self.assertEqual(self.gui.gconf_get('last_zoom_level', int), 3)
        
        self.gui.gconf_set('last_latitude', 10.0)
        self.assertEqual(self.gui.gconf_get('last_latitude', float), 10.0)
        self.gui.gconf_set('last_latitude', -53.0)
        self.assertEqual(self.gui.gconf_get('last_latitude', float), -53.0)
        
        self.gui.gconf_set('last_longitude', 10.0)
        self.assertEqual(self.gui.gconf_get('last_longitude', float), 10.0)
        self.gui.gconf_set('last_longitude', 113.0)
        self.assertEqual(self.gui.gconf_get('last_longitude', float), 113.0)
        
        lat = random_coord(90)
        lon = random_coord(180)
        
        self.gui.map_view.center_on(lat, lon)
        
        self.gui.remember_location_with_gconf()
        
        self.assertAlmostEqual(lat, self.gui.gconf_get('last_latitude',  float), 4)
        self.assertAlmostEqual(lon, self.gui.gconf_get('last_longitude', float), 4)
        self.assertEqual(
            self.gui.map_view.get_zoom_level(),
            self.gui.gconf_get('last_zoom_level', int)
        )
        
        self.gui.gconf_set('last_latitude', orig_lat)
        self.gui.gconf_set('last_longitude', orig_lon)
        self.gui.gconf_set('last_zoom_level', orig_zoom)

        
#    def test_writing_files(self):
#        pass
#        # TODO

def random_coord(maximum=180):
    """Generate a random number -maximum <= x <= maximum."""
    
    return (random.random() * maximum * 2) - maximum

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromTestCase(GottenGeographyTester)
    )
