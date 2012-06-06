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

"""Define classes used for parsing GPX and KML XML files."""

from __future__ import division

from xml.parsers.expat import ParserCreate, ExpatError
from dateutil.parser import parse as parse_date
from gi.repository import Champlain, Clutter
from gi.repository import Gtk, Gdk, GLib
from re import compile as re_compile
from os.path import basename
from calendar import timegm
from time import clock

from gpsmath import Coordinates
from common import GSettings, Builder, Widgets, gst
from common import memoize, map_view, points

BOTTOM = Gtk.PositionType.BOTTOM
RIGHT = Gtk.PositionType.RIGHT

def make_clutter_color(color):
    """Generate a Clutter.Color from the currently chosen color."""
    return Clutter.Color.new(
        *[x / 256 for x in [color.red, color.green, color.blue, 49152]])

def track_color_changed(selection, polys):
    """Update the color of any loaded GPX tracks."""
    color = selection.get_color()
    gst.set_value('track-color',
        GLib.Variant('(iii)', (color.red, color.green, color.blue)))
    one = make_clutter_color(color)
    two = one.lighten().lighten()
    for i, polygon in enumerate(polys):
        polygon.set_stroke_color(two if i % 2 else one)

def clear_all_gpx(*ignore):
    """Forget all GPX data, start over with a clean slate."""
    for trackfile in TrackFile.instances.values():
        trackfile.destroy()
    
    TrackFile.instances.clear()
    points.clear()


class Polygon(Champlain.PathLayer):
    """Extend a Champlain.PathLayer to do things more the way I like them."""
    
    def __init__(self):
        Champlain.PathLayer.__init__(self)
        self.set_stroke_width(4)
    
    def append_point(self, latitude, longitude, elevation):
        """Simplify appending a point onto a polygon."""
        coord = Champlain.Coordinate.new_full(latitude, longitude)
        coord.lat = latitude
        coord.lon = longitude
        coord.ele = elevation
        self.add_node(coord)
        return coord


class XMLSimpleParser:
    """A simple wrapper for the Expat XML parser."""
    
    def __init__(self, rootname, watchlist):
        self.rootname = rootname
        self.watchlist = watchlist
        self.call_start = None
        self.call_end = None
        self.element = None
        self.tracking = None
        self.state = {}
        
        self.parser = ParserCreate()
        self.parser.StartElementHandler = self.element_root
    
    def parse(self, filename, call_start, call_end):
        """Begin the loading and parsing of the XML file."""
        self.call_start = call_start
        self.call_end = call_end
        try:
            with open(filename) as xml:
                self.parser.ParseFile(xml)
        except ExpatError:
            raise IOError
   
    def element_root(self, name, attributes):
        """Called on the root XML element, we check if it's the one we want."""
        if self.rootname != None and name != self.rootname:
            raise IOError
        self.parser.StartElementHandler = self.element_start
    
    def element_start(self, name, attributes):
        """Only collect the attributes from XML elements that we care about."""
        if not self.tracking:
            if name not in self.watchlist:
                return
            if self.call_start(name, attributes):
                # Start tracking this element, accumulate everything under it.
                self.tracking = name
                self.parser.CharacterDataHandler = self.element_data
                self.parser.EndElementHandler = self.element_end
        
        if self.tracking is not None:
            self.element = name
            self.state[name] = ''
            self.state.update(attributes)
    
    def element_data(self, data):
        """Accumulate all data for an element.
        
        Expat can call this handler multiple times with data chunks.
        """
        if not data or data.strip() == '':
            return
        self.state[self.element] += data
    
    def element_end(self, name):
        """When the tag closes, pass it's data to the end callback and reset."""
        if name != self.tracking:
            return
        
        self.call_end(name, self.state)
        self.tracking = None
        self.state.clear()
        self.parser.CharacterDataHandler = None
        self.parser.EndElementHandler = None


class TrackFile(Coordinates):
    """Parent class for all types of GPS track files.
    
    Subclasses must implement element_start and element_end, and call them in
    the base class.
    """
    range = [float('inf'), float('-inf')]
    instances = {}
    
    @staticmethod
    def update_range():
        """Ensure that TrackFile.range contains the correct info."""
        if not TrackFile.instances:
            Widgets.empty_trackfile_list.show()
            TrackFile.range[0] = float('inf')
            TrackFile.range[1] = float('-inf')
        else:
            Widgets.empty_trackfile_list.hide()
            files = TrackFile.instances.values()
            TrackFile.range[0] = min([gpx.alpha for gpx in files])
            TrackFile.range[1] = max([gpx.omega for gpx in files])
    
    @staticmethod
    def get_bounding_box():
        """Determine the smallest box that contains all loaded polygons."""
        bounds = Champlain.BoundingBox.new()
        for trackfile in TrackFile.instances.values():
            for polygon in trackfile.polygons:
                bounds.compose(polygon.get_bounding_box())
        return bounds
    
    def __init__(self, filename, root, watch):
        self.filename = filename
        self.progress = Widgets.progressbar
        self.clock    = clock()
        self.append   = None
        self.tracks   = {}
        self.polygons = set()
        
        self.parser = XMLSimpleParser(root, watch)
        self.parser.parse(filename, self.element_start, self.element_end)
        
        points.update(self.tracks)
        keys = self.tracks.keys()
        self.alpha = min(keys)
        self.omega = max(keys)
        self.latitude = self.tracks[self.alpha].lat
        self.longitude = self.tracks[self.alpha].lon
        
        builder = Builder('trackfile')
        self.label = builder.trackfile_label
        self.label.set_text(basename(filename))
        
        self.trash = builder.unload
        self.trash.connect('clicked', self.destroy)
        
        self.colorpicker = builder.colorpicker
        self.colorpicker.set_title(basename(filename))
        self.colorpicker.connect('color-set',
                                 track_color_changed,
                                 self.polygons)
        
        Widgets.trackfiles_view.attach_next_to(
            builder.trackfile_settings, None, BOTTOM, 1, 1)
        
        self.gst = GSettings('trackfile', basename(filename))
        
        if self.gst.get_string('start-timezone') is '':
            # Then this is the first time this file has been loaded
            # and we should honor the user-selected global default
            # track color instead of using the schema-defined default
            self.gst.set_value('track-color', gst.get_value('track-color'))
        
        self.gst.set_string('start-timezone', self.lookup_geoname())
        self.gst.bind_with_convert('track-color', self.colorpicker, 'color',
            lambda x: Gdk.Color(*x), lambda x: (x.red, x.green, x.blue))
        self.colorpicker.emit('color-set')
    
    def element_start(self, name, attributes):
        """Placeholder for a method that gets overridden in subclasses."""
        return False
    
    def element_end(self, name, state):
        """Occasionally redraw the screen so the user can see activity."""
        if clock() - self.clock > .2:
            self.progress.pulse()
            while Gtk.events_pending():
                Gtk.main_iteration()
            self.clock = clock()
    
    def destroy(self, button=None):
        """Die a horrible death."""
        for polygon in self.polygons:
            map_view.remove_layer(polygon)
        for timestamp in self.tracks:
            del points[timestamp]
        self.polygons.clear()
        for widget in (self.label, self.colorpicker, self.trash):
            widget.destroy()
        del TrackFile.instances[self.filename]
        TrackFile.update_range()


# GPX files use ISO 8601 dates, which look like 2010-10-16T20:09:13Z.
# This regex splits that up into a list like 2010, 10, 16, 20, 09, 13.
split = re_compile(r'[:TZ-]').split


@memoize
class GPXFile(TrackFile):
    """Parse a GPX file."""
    
    def __init__(self, filename):
        TrackFile.__init__(self, filename, 'gpx', ['trkseg', 'trkpt'])
    
    def element_start(self, name, attributes):
        """Adds new polygon for each segment, and watches for track points."""
        if name == 'trkseg':
            polygon = Polygon()
            map_view.add_layer(polygon)
            self.polygons.add(polygon)
            self.append = polygon.append_point
        if name == 'trkpt':
            return True
        return False
    
    def element_end(self, name, state):
        """Collect and use all the parsed data.
        
        This method does most of the heavy lifting, including parsing time
        strings into UTC epoch seconds, appending to the ChamplainMarkerLayers,
        keeping track of the first and last points loaded.
        """
        # We only care about the trkpt element closing, because that means
        # there is a new, fully-loaded GPX point to play with.
        if name != 'trkpt':
            return
        try:
            timestamp = timegm(map(int, split(state['time'])[0:6]))
            lat = float(state['lat'])
            lon = float(state['lon'])
        except Exception as error:
            print error
            # If any of lat, lon, or time is missing, we cannot continue.
            # Better to just give up on this track point and go to the next.
            return
        
        self.tracks[timestamp] = self.append(lat, lon,
                                             float(state.get('ele', 0.0)))
        
        TrackFile.element_end(self, name, state)


@memoize
class KMLFile(TrackFile):
    """Parse a KML file."""
    
    def __init__(self, filename):
        self.whens    = []
        self.coords   = []
        
        TrackFile.__init__(self, filename, 'kml',
                           ['gx:Track', 'when', 'gx:coord'])
    
    def element_start(self, name, attributes):
        """Adds new polygon for each gx:Track, and watches for location data."""
        if name == 'gx:Track':
            polygon = Polygon()
            map_view.add_layer(polygon)
            self.polygons.add(polygon)
            self.append = polygon.append_point
            return False
        return True
    
    def element_end(self, name, state):
        """Watch for complete pairs of when and gx:coord tags.
        
        This is accomplished by maintaining parallel arrays of each tag.
        """
        if name == 'when':
            try:
                timestamp = timegm(parse_date(state['when']).utctimetuple())
            except Exception as error:
                print error
                return
            self.whens.append(timestamp)
        if name == 'gx:coord':
            self.coords.append(state['gx:coord'].split())
        
        complete = min(len(self.whens), len(self.coords))
        if complete > 0:
            for i in range(0, complete):
                self.tracks[self.whens[i]] = \
                    self.append(float(self.coords[i][1]), \
                                float(self.coords[i][0]), \
                                float(self.coords[i][2]))
            self.whens = self.whens[complete:]
            self.coords = self.coords[complete:]
        
        TrackFile.element_end(self, name, state)

