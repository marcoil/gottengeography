# GottenGeography - Parse GPX files with expat
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

import re
import time
import calendar

from xml.parsers import expat
from gi.repository import Champlain, Clutter

class GPXLoader:
    """Use expat to parse GPX data quickly."""
    
    def __init__(self, gui, filename):
        """Create the parser and begin parsing."""
        self.gui      = gui
        self.polygons = []
        self.state    = {}
        self.tracks   = {}
        self.clock    = time.clock()
        self.alpha    = float('inf')
        self.omega    = float('-inf')
        self.area     = [ float('inf') ] * 2 + [ float('-inf') ] * 2
        
        # TODO this should be user-configurable.
        self.track_a = Clutter.Color.new(128, 0,  192, 128)
        self.track_b = Clutter.Color.new(192, 64, 192, 128)
        
        # GPX files use ISO 8601 dates, which look like 2010-10-16T20:09:13Z.
        # This regex splits that up into a list like 2010, 10, 16, 20, 09, 13.
        self.delimiters = re.compile(r'[:TZ-]')
        
        self.parser = expat.ParserCreate()
        self.parser.StartElementHandler  = self.element_root
        self.parser.CharacterDataHandler = self.element_data
        self.parser.EndElementHandler    = self.element_end
        
        try:
            with open(filename) as gpx:
                self.parser.ParseFile(gpx)
        except expat.ExpatError:
            # Changing the exception raised means that I don't have to
            # import expat in app.py at all.
            raise IOError
    
    def element_root(self, name, attributes):
        """Expat StartElementHandler.
        
        This is only called on the top level element in the given XML file.
        """
        if name <> 'gpx':
            raise IOError
        self.parser.StartElementHandler = self.element_start
    
    def element_start(self, name, attributes):
        """Expat StartElementHandler.
        
        This method creates new ChamplainPolygons when necessary and initializes
        variables for the CharacterDataHandler. It also extracts latitude and
        longitude from GPX element attributes. For example:
        
        <trkpt lat="45.147445" lon="-81.469507">
        """
        self.element     = name
        self.state[name] = ""
        self.state.update(attributes)
        if name == "trkseg":
            self.polygons.append(Champlain.Polygon())
            self.polygons[-1].set_stroke_width(5)
            self.polygons[-1].set_stroke_color(self.track_a
                if len(self.polygons) % 2 else self.track_b)
            self.polygons[-1].show()
            self.gui.map_view.add_polygon(self.polygons[-1])
    
    def element_data(self, data):
        """Expat CharacterDataHandler.
        
        This method extracts elevation and time data from GPX elements.
        For example:
        
        <ele>671.092</ele>
        <time>2010-10-16T20:09:13Z</time>
        """
        data = data.strip()
        if not data:
            return
        # Sometimes expat calls this handler multiple times each with just
        # a chunk of the whole data, so += is necessary to collect all of it.
        self.state[self.element] += data
    
    def element_end(self, name):
        """Expat EndElementHandler.
        
        This method does most of the heavy lifting, including parsing time
        strings into UTC epoch seconds, appending to the ChamplainPolygons,
        keeping track of the first and last points loaded, as well as the
        entire area covered by the polygon, and occaisionally redrawing the
        screen so that the user can see what's going on while stuff is
        loading.
        """
        # We only care about the trkpt element closing, because that means
        # there is a new, fully-loaded GPX point to play with.
        if name <> "trkpt":
            return
        try:
            timestamp = calendar.timegm(map(int,
                self.delimiters.split(self.state['time'])[0:6]))
            lat = float(self.state['lat'])
            lon = float(self.state['lon'])
        except:
            # If any of lat, lon, or time is missing, we cannot continue.
            # Better to just give up on this track point and go to the next.
            return
        self.tracks[timestamp] = {
            'elevation': float(self.state.get('ele', 0.0)),
            'point':     self.polygons[-1].append_point(lat, lon)
        }
        
        self.state.clear()
        self.omega   = max(self.omega, timestamp)
        self.alpha   = min(self.alpha, timestamp)
        self.area[0] = min(self.area[0], lat)
        self.area[1] = min(self.area[1], lon)
        self.area[2] = max(self.area[2], lat)
        self.area[3] = max(self.area[3], lon)
        if time.clock() - self.clock > .2:
            self.gui.map_view.ensure_visible(*self.area + [False])
            self.gui.progressbar.pulse()
            self.gui.redraw_interface()
            self.clock = time.clock()

