# GottenGeography - GPS-related functions including GPX parsing
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

import re
import time

from gi.repository import Gtk, Champlain, Clutter
from math import modf as split_float
from gettext import gettext as _
from fractions import Fraction
from xml.parsers import expat
from pyexiv2 import Rational
from calendar import timegm

# Don't export everything, that's too sloppy.
__all__ = [ 'dms_to_decimal', 'decimal_to_dms', 'float_to_rational',
    'valid_coords', 'maps_link', 'format_coords', 'GPXLoader' ]

def dms_to_decimal(degrees, minutes, seconds, sign=""):
    """Convert degrees, minutes, seconds into decimal degrees."""
    return (-1 if re.match(r'[SWsw]', sign) else 1) * (
        degrees.to_float()        +
        minutes.to_float() / 60   +
        seconds.to_float() / 3600
    )

def decimal_to_dms(decimal):
    """Convert decimal degrees into degrees, minutes, seconds."""
    remainder, degrees = split_float(abs(decimal))
    remainder, minutes = split_float(remainder * 60)
    return [
        Rational(degrees, 1),
        Rational(minutes, 1),
        float_to_rational(remainder * 60)
    ]

def float_to_rational(value):
    """Create a pyexiv2.Rational with help from fractions.Fraction."""
    frac = Fraction(abs(value)).limit_denominator(99999)
    return Rational(frac.numerator, frac.denominator)

def valid_coords(lat, lon):
    """Determine the validity of coordinates."""
    if type(lat) not in (float, int): return False
    if type(lon) not in (float, int): return False
    return abs(lat) <= 90 and abs(lon) <= 180

def maps_link(lat, lon, anchor=_("View in Google Maps")):
    """Create a Pango link to Google Maps."""
    return '<a href="http://maps.google.com/maps?q=%s,%s">%s</a>' % (lat, lon, anchor)

def format_coords(lat, lon):
    """Add cardinal directions to decimal coordinates."""
    return "%s %.5f, %s %.5f" % (
        _("N") if lat >= 0 else _("S"), abs(lat),
        _("E") if lon >= 0 else _("W"), abs(lon)
    )

# GPX files use ISO 8601 dates, which look like 2010-10-16T20:09:13Z.
# This regex splits that up into a list like 2010, 10, 16, 20, 09, 13.
split = re.compile(r'[:TZ-]').split

class GPXLoader:
    """Use expat to parse GPX data quickly."""
    
    def __init__(self, filename, polygons, map_view, progressbar, color):
        """Create the parser and begin parsing."""
        self.polygons = polygons
        self.state    = {}
        self.tracks   = {}
        self.clock    = time.clock()
        self.alpha    = float('inf')
        self.omega    = float('-inf')
        self.area     = [ float('inf') ] * 2 + [ float('-inf') ] * 2
        self.map_view = map_view
        self.progress = progressbar
        self.color_a  = color
        self.color_b  = color.lighten().lighten()
        
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
        
        self.latitude  = (self.area[0] + self.area[2]) / 2
        self.longitude = (self.area[1] + self.area[3]) / 2
    
    def valid_coords(self):
        """Check if the median point of this GPX file is valid."""
        return valid_coords(self.latitude, self.longitude)
    
    def element_root(self, name, attributes):
        """Expat StartElementHandler.
        
        This is only called on the top level element in the given XML file.
        """
        if name != 'gpx':
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
            self.polygons[-1].set_stroke_color(self.color_a
                if len(self.polygons) % 2 else self.color_b)
            self.polygons[-1].show()
            self.map_view.add_polygon(self.polygons[-1])
    
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
        if name != "trkpt":
            return
        try:
            timestamp = timegm(map(int, split(self.state['time'])[0:6]))
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
            self.map_view.ensure_visible(*self.area + [False])
            self.progress.pulse()
            while Gtk.events_pending():
                Gtk.main_iteration()
            self.clock = time.clock()

