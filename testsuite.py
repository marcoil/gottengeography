#!/usr/bin/env python
# coding=utf-8

import unittest, os, re, time
from gottengeography import GottenGeography
from xml.parsers.expat import ExpatError

class GottenGeographyTester(unittest.TestCase):
    def setUp(self):
        """Start the GottenGeography application."""
        
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
        self.assertEqual(self.gui.current['lowest'],  None)
        self.assertEqual(self.gui.current['highest'], None)
        self.assertEqual(
            self.gui.current['area'], 
            ['', '', None, None, False]
        )
        
        # Make the tests work for people outside my time zone.
        os.environ["TZ"] = "America/Edmonton"
        
        os.chdir('./demo/')
        for demo in os.listdir('.'):
            filename = "%s/%s" % (os.getcwd(), demo)
            if re.search(r'gpx$', demo):
                self.assertRaises(IOError, 
                    self.gui.add_or_reload_photo,
                    filename=filename,
                    data=[[], 1]
                )

                self.gui.load_gpx_from_file(filename)
            else:
                self.assertRaises(ExpatError, 
                    self.gui.load_gpx_from_file,
                    filename
                )
                self.gui.add_or_reload_photo(
                    filename=filename,
                    data=[[], 1]
                )
        
        # GPX parser uses 'start' for timing the GPX loading process, but we fed
        # it an invalid file above, which caused it to raise an exception, 
        # so this didn't get cleaned up.
        del self.gui.current['start']
        
        self.assertEqual(len(self.gui.tracks),   374)
        self.assertEqual(len(self.gui.modified), 6)
        self.assertEqual(len(self.gui.current),  4)
        self.assertEqual(self.gui.current['lowest'],  1287259751)
        self.assertEqual(self.gui.current['highest'], 1287260756)
        self.assertEqual(
            self.gui.current['area'], 
            [53.522495999999997, -113.453148, 
             53.537399000000001, -113.443061, False]
        )
        
        iter = self.gui.loaded_photos.get_iter_first()
        self.assertTrue(iter[0])
        self.assertAlmostEqual(
            self.gui.loaded_photos.get_value(iter[1], self.gui.PHOTO_LATITUDE), 
            53.530006, 6
        )
        self.assertAlmostEqual(
            self.gui.loaded_photos.get_value(iter[1], self.gui.PHOTO_LONGITUDE),
            -113.448004333, 9
        )
    
    def test_writing_files(self):
        pass
        # TODO

if __name__ == '__main__':
    unittest.main()
