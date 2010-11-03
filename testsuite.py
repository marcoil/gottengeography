#!/usr/bin/env python
# coding=utf-8

from __future__ import division
import unittest, os, re, time, random
from gottengeography import GottenGeography
from xml.parsers.expat import ExpatError

class GottenGeographyTester(unittest.TestCase):
    def setUp(self):
        """Start the GottenGeography application."""
        
        # Make the tests work for people outside my time zone.
        os.environ["TZ"] = "America/Edmonton"
        
        self.gui = GottenGeography()
        # TODO add code to do a git checkout of the demo data so that
        # it's always pristine.
    
    def test_gtk_window(self):
        """Make sure that various widgets were created properly."""
        
        self.assertEqual(
            str(type(self.gui.gconf_client)), 
            "<class 'gi.repository.GConf.Client'>"
        )
        
        self.assertEqual(self.gui.loaded_photos.get_n_columns(), 8)
        self.assertEqual(self.gui.window.get_size(), (900, 700))
    
    def test_demo_data(self):
        """Load the demo data and ensure that we're reading it in properly."""
        
        self.assertEqual(len(self.gui.tracks), 0)
        self.assertEqual(len(self.gui.modified), 0)
        self.assertEqual(len(self.gui.polygons), 0)
        self.assertEqual(self.gui.current['lowest'],  "")
        self.assertEqual(self.gui.current['highest'], None)
        self.assertEqual(
            self.gui.current['area'], 
            ['', '', None, None, False]
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
        
        # Test that a photo has no coordinates to begin with
        self.assertEqual(
            self.gui.loaded_photos.get_value(iter[1], self.gui.PHOTO_LATITUDE), 
            0.0
        )
        self.assertEqual(
            self.gui.loaded_photos.get_value(iter[1], self.gui.PHOTO_LONGITUDE),
            0.0
        )
        
        # Load the GPX
        filename="%s/%s" % (os.getcwd(), "20101016.gpx")
        self.assertRaises(IOError, 
            self.gui.add_or_reload_photo,
            filename=filename,
            data=[[], 1]
        )
        self.gui.load_gpx_from_file(filename)
        
        # Check that the GPX is loaded
        self.assertEqual(len(self.gui.tracks),   374)
        self.assertEqual(len(self.gui.modified), 6)
        self.assertEqual(len(self.gui.current),  4)
        self.assertEqual(len(self.gui.polygons), 1)
        self.assertEqual(self.gui.current['lowest'],  1287259751)
        self.assertEqual(self.gui.current['highest'], 1287260756)
        self.assertEqual(
            self.gui.current['area'], 
            [53.522495999999997, -113.453148, 
             53.537399000000001, -113.443061, False]
        )
        
        # check that a photo has the correct coordinates.
        self.assertAlmostEqual(
            self.gui.loaded_photos.get_value(iter[1], self.gui.PHOTO_LATITUDE), 
            53.529963999999993, 9
        )
        self.assertAlmostEqual(
            self.gui.loaded_photos.get_value(iter[1], self.gui.PHOTO_LONGITUDE),
            -113.44800866666665, 9
        )
    
    def test_string_functions(self):
        """Ensure that strings print properly."""
        
        self.assertEqual(
            self.gui._pretty_coords(10, 10),
            "N 10.00000, E 10.00000"
        )
        self.assertEqual(
            self.gui._pretty_coords(-10, -10),
            "S 10.00000, W 10.00000"
        )
        
        self.assertEqual(
            self.gui._pretty_time(999999999), 
            "2001-09-08 07:46:39 PM"
        )
        
        self.assertEqual(
            self.gui._create_summary(
                "photo.jpg", 
                999999999, 
                43.646719, 
                -79.334382, 
                101, 
                True
            ), 
            """<b>photo.jpg
<span color="#BBBBBB" size="smaller">2001-09-08 07:46:39 PM
N 43.64672, W 79.33438
101.0m above sea level</span></b>"""
        )
        
        self.assertEqual(
            self.gui._create_summary(
                "image.dng", 
                999999999, 
                48.440344, 
                -89.204751, 
                186, 
                False
            ), 
            """image.dng
<span color="#BBBBBB" size="smaller">2001-09-08 07:46:39 PM
N 48.44034, W 89.20475
186.0m above sea level</span>"""
        )
    
    def test_gps_math(self):
        """Test coordinate conversion functions."""
        
        self.assertFalse(self.gui.valid_coords(None, None))
        self.assertFalse(self.gui.valid_coords("", ""))
        
        # Pick 100 random coordinates on the globe, convert them from decimal
        # to sexagesimal and then back, and ensure that they are always equal.
        for i in range(100):
            # Oh, and test altitudes too
            altitude = round(random.random() * 100, 6)
            fraction = self.gui.float_to_rational(altitude)
            self.assertAlmostEqual(
                altitude,
                fraction.numerator / fraction.denominator,
                5
            )
            
            decimal_lat = round(random.random() * 180 - 90,  6)
            decimal_lon = round(random.random() * 360 - 180, 6)
            
            self.assertTrue(self.gui.valid_coords(decimal_lat, decimal_lon))
            
            dms_lat = self.gui.decimal_to_dms(decimal_lat, True)
            dms_lon = self.gui.decimal_to_dms(decimal_lon, False)
            
            self.assertEqual(len(dms_lat),    2)
            self.assertEqual(len(dms_lat[0]), 3)
            
            self.assertEqual(len(dms_lon),    2)
            self.assertEqual(len(dms_lon[0]), 3)
            
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
        
        self.gui.remember_location()
        self.assertEqual(history_length + 1, len(self.gui.history))
        
        coords = []
        
        coords.append([
            self.gui.map_view.get_property('latitude'),
            self.gui.map_view.get_property('longitude')
        ])
        
        self.gui.map_view.center_on(
            round(random.random() * 160 - 80,  6),
            round(random.random() * 360 - 180, 6)
        )
        
        coords.append([
            self.gui.map_view.get_property('latitude'),
            self.gui.map_view.get_property('longitude')
        ])
        
        self.gui.remember_location()
        self.assertEqual(history_length + 2, len(self.gui.history))
        
        self.gui.map_view.center_on(
            round(random.random() * 160 - 80,  6),
            round(random.random() * 360 - 180, 6)
        )
        
        self.gui.return_to_last()
        self.assertEqual(history_length + 1, len(self.gui.history))
        
        # These assertAlmostEqual calls are less accurate than the other ones
        # because they're testing the ChamplainView coordinates more than
        # anything else, which rounds a bit more loosely than my own code does.
        self.assertAlmostEqual(
            self.gui.map_view.get_property('latitude'),
            coords[-1][0],
            2
        )
        self.assertAlmostEqual(
            self.gui.map_view.get_property('longitude'),
            coords[-1][1],
            2
        )
        
        self.gui.return_to_last()
        self.assertEqual(history_length, len(self.gui.history))
    
    def test_map_markers(self):
        """Put a marker on the map, and then take it off."""
        
        lat = random.random() * 180 - 90
        lon = random.random() * 360 - 180
        
        marker = self.gui.add_marker("foobar", lat, lon)
        
        self.assertEqual(marker.get_property('latitude'), lat)
        self.assertEqual(marker.get_property('longitude'), lon)
        
        self.assertTrue(marker.get_parent())
        
        marker.destroy()
        
        self.assertFalse(marker.get_parent())
        
#    def test_writing_files(self):
#        pass
#        # TODO

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(GottenGeographyTester)
    unittest.TextTestRunner(verbosity=2).run(suite)

