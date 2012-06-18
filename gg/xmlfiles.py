# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Define classes used for parsing GPX and KML XML files."""

from __future__ import division

from xml.parsers.expat import ParserCreate, ExpatError
from gi.repository import Champlain, Clutter, Gtk, Gdk
from dateutil.parser import parse as parse_date
from re import compile as re_compile
from gettext import gettext as _
from os.path import basename
from calendar import timegm
from time import clock

from camera import Camera
from gpsmath import Coordinates
from widgets import Widgets, Builder, MapView
from common import GSettings, Gst, Struct, memoize, points

BOTTOM = Gtk.PositionType.BOTTOM
RIGHT = Gtk.PositionType.RIGHT


def make_clutter_color(color):
    """Generate a Clutter.Color from the currently chosen color."""
    return Clutter.Color.new(
        *[x / 256 for x in [color.red, color.green, color.blue, 49152]])


def track_color_changed(selection, polys):
    """Update the color of any loaded GPX tracks."""
    color = selection.get_color()
    Gst.set_color(color)
    one = make_clutter_color(color)
    two = one.lighten().lighten()
    for i, polygon in enumerate(polys):
        polygon.set_stroke_color(two if i % 2 else one)


class Polygon(Champlain.PathLayer):
    """Extend a Champlain.PathLayer to do things more the way I like them."""
    
    def __init__(self):
        Champlain.PathLayer.__init__(self)
        self.set_stroke_width(4)
        MapView.add_layer(self)
    
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
        if not data.strip():
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


class TrackFile():
    """Parent class for all types of GPS track files.
    
    Subclasses must implement element_start and element_end, and call them in
    the base class.
    """
    range = []
    instances = {}
    files = instances.viewvalues()
    
    @staticmethod
    def update_range():
        """Ensure that TrackFile.range contains the correct info."""
        while TrackFile.range:
            TrackFile.range.pop()
        if not TrackFile.instances:
            Widgets.empty_trackfile_list.show()
        else:
            Widgets.empty_trackfile_list.hide()
            TrackFile.range.extend([min(points), max(points)])
    
    @staticmethod
    def get_bounding_box():
        """Determine the smallest box that contains all loaded polygons."""
        bounds = Champlain.BoundingBox.new()
        for trackfile in TrackFile.files:
            for polygon in trackfile.polygons:
                bounds.compose(polygon.get_bounding_box())
        return bounds
    
    @staticmethod
    def query_all_timezones():
        """Try to determine the most likely timezone the user is in.
        
        First we check all loaded GPX/KML files for the timezone at their
        starting point, and if those timezones are all identical, we report it.
        If they do not match, then the user must travel a lot, and then we
        simply have no idea what timezone is likely to be the one that their
        camera is set to.
        """
        zones = {}
        for trackfile in TrackFile.instances.values():
            zones[trackfile.start.geotimezone] = True
        return None if len(zones) != 1 else zones.keys()[0]
    
    @staticmethod
    def clear_all(*ignore):
        """Forget all GPX data, start over with a clean slate."""
        for trackfile in TrackFile.instances.values():
            trackfile.destroy()
        
        TrackFile.instances.clear()
        points.clear()
    
    @staticmethod
    def load_from_file(uri):
        """Determine the correct subclass to instantiate.
        
        Also time everything and report how long it took. Raises IOError if
        the file extension is unknown, or no track points were found.
        """
        start_time = clock()
        
        try:
            gpx = globals()[uri[-3:].upper() + 'File'](uri)
        except KeyError:
            raise IOError
        
        Widgets.status_message(_('%d points loaded in %.2fs.') %
            (len(gpx.tracks), clock() - start_time), True)
        
        if len(gpx.tracks) < 2:
            return
        
        MapView.emit('realize')
        MapView.set_zoom_level(MapView.get_max_zoom_level())
        MapView.ensure_visible(TrackFile.get_bounding_box(), False)
        
        TrackFile.update_range()
        Camera.set_all_found_timezone(gpx.start.geotimezone)
    
    def __init__(self, filename, root, watch):
        self.watchlist = watch
        self.filename = filename
        self.progress = Widgets.progressbar
        self.polygons = set()
        self.widgets = Builder('trackfile')
        self.append = None
        self.tracks = {}
        self.clock = clock()
        
        self.gst = GSettings('trackfile', basename(filename))
        if self.gst.get_string('start-timezone') is '':
            # Then this is the first time this file has been loaded
            # and we should honor the user-selected global default
            # track color instead of using the schema-defined default
            self.gst.set_value('track-color', Gst.get_value('track-color'))
        
        self.gst.bind_with_convert(
            'track-color',
            self.widgets.colorpicker,
            'color',
            lambda x: Gdk.Color(*x),
            lambda x: (x.red, x.green, x.blue))
        
        self.widgets.trackfile_label.set_text(basename(filename))
        self.widgets.unload.connect('clicked', self.destroy)
        self.widgets.colorpicker.set_title(basename(filename))
        self.widgets.colorpicker.connect('color-set',
                                         track_color_changed,
                                         self.polygons)
        
        Widgets.trackfile_unloads_group.add_widget(self.widgets.unload)
        Widgets.trackfile_colors_group.add_widget(self.widgets.colorpicker)
        Widgets.trackfiles_group.add_widget(self.widgets.trackfile_label)
        
        if callable(root):
            root(filename)
        else:
            self.parser = XMLSimpleParser(root, watch)
            self.parser.parse(filename, self.element_start, self.element_end)
        
        if not self.tracks:
            raise IOError('No points found')
        
        points.update(self.tracks)
        keys = self.tracks.keys()
        self.alpha = min(keys)
        self.omega = max(keys)
        self.start = Coordinates(latitude = self.tracks[self.alpha].lat,
                                 longitude = self.tracks[self.alpha].lon)
        
        self.gst.set_string('start-timezone', self.start.lookup_geodata())
        
        Widgets.trackfiles_view.add(self.widgets.trackfile_settings)
    
    def element_start(self, name, attributes=None):
        """Determine when new tracks start and create a new Polygon."""
        if name == self.watchlist[0]:
            polygon = Polygon()
            self.polygons.add(polygon)
            self.append = polygon.append_point
            self.widgets.colorpicker.emit('color-set')
            return False
        return True
    
    def element_end(self, name=None, state=None):
        """Occasionally redraw the screen so the user can see activity."""
        if clock() - self.clock > .2:
            self.progress.pulse()
            while Gtk.events_pending():
                Gtk.main_iteration()
            self.clock = clock()
    
    def destroy(self, button=None):
        """Die a horrible death."""
        for polygon in self.polygons:
            MapView.remove_layer(polygon)
        for timestamp in self.tracks:
            del points[timestamp]
        self.polygons.clear()
        self.widgets.trackfile_settings.destroy()
        del TrackFile.instances[self.filename]
        TrackFile.update_range()


# GPX files use ISO 8601 dates, which look like 2010-10-16T20:09:13Z.
# This regex splits that up into a list like 2010, 10, 16, 20, 09, 13.
split = re_compile(r'[:T.Z-]').split


@memoize
class GPXFile(TrackFile):
    """Support for the open GPS eXchange format."""
    
    def __init__(self, filename):
        TrackFile.__init__(self, filename, 'gpx', ['trkseg', 'trkpt'])
    
    def element_end(self, name, state):
        """Collect and use all the parsed data."""
        if name != 'trkpt':
            return
        try:
            timestamp = timegm(map(int, split(state['time'])[0:6]))
            lat = float(state['lat'])
            lon = float(state['lon'])
        except Exception as error:
            print error
            return
        
        self.tracks[timestamp] = self.append(lat, lon,
                                             float(state.get('ele', 0.0)))
        
        TrackFile.element_end(self, name, state)


@memoize
class TCXFile(TrackFile):
    """Support for Garmin's Training Center XML."""
    
    def __init__(self, filename):
        TrackFile.__init__(self, filename, 'TrainingCenterDatabase',
                           ['Track', 'Trackpoint', 'Time', 'LatitudeDegrees',
                           'LongitudeDegrees', 'AltitudeMeters'])
    
    def element_end(self, name, state):
        """Collect and use all the parsed data."""
        if name != 'Trackpoint':
            return
        try:
            timestamp = timegm(map(int, split(state['Time'])[0:6]))
            lat = float(state['LatitudeDegrees'])
            lon = float(state['LongitudeDegrees'])
        except Exception as error:
            print error
            return
        
        self.tracks[timestamp] = self.append(
            lat, lon, float(state.get('AltitudeMeters', 0.0)))
        
        TrackFile.element_end(self, name, state)


@memoize
class KMLFile(TrackFile):
    """Support for Google's Keyhole Markup Language."""
    
    def __init__(self, filename):
        self.whens    = []
        self.coords   = []
        
        TrackFile.__init__(self, filename, 'kml',
                           ['gx:Track', 'when', 'gx:coord'])
    
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


# This regex ignores commas inside quotes, so '"foo,bar","baz,qux"' would be
# interpreted as having only two columns.
parse_csv = re_compile(r'"([^"]+)",+').findall


@memoize
class CSVFile(TrackFile):
    """Support for Google's MyTracks' Comma Separated Values format.
    
    This implementation ignores everything before the first blank line,
    allowing you to have any arbitrary preamble you like, and then the first
    line after the first blank line must contain the following column titles
    (in any order you like). Extra columns are harmlessly ignored. All "values"
    must be "quoted" with "double quotes".
    """
    columns = None
    
    def __init__(self, filename):
        TrackFile.__init__(self, filename, self.parser,
            ['Segment', 'Latitude (deg)', 'Longitude (deg)',
             'Altitude (m)', 'Time'])
    
    def parser(self, filename):
        """Call the appropriate handler for each line of the file."""
        self.caller = self.ignore_preamble
        
        with open(filename) as lines:
            for line in lines:
                self.caller(parse_csv(line), self.columns)
    
    def ignore_preamble(self, state, columns):
        """Discard all of the lines before the first blank line."""
        if not state:
            self.caller = self.parse_header
    
    def parse_header(self, state, columns):
        """The first line after the first blank line contains column headers."""
        try:
            self.columns = Struct({col.split(' ')[0].lower():
                state.index(col) for col in self.watchlist})
        except ValueError:
            raise IOError('This CSV file is missing necessary headers')
        self.caller = self.parse_row
    
    def parse_row(self, state, col):
        """All subsequent lines contain one track point each."""
        try:
            if int(state[col.segment]) > len(self.polygons):
                self.element_start('Segment')
            
            timestamp = timegm(map(int, split(state[col.time])[0:6]))
            lat = float(state[col.latitude])
            lon = float(state[col.longitude])
        except Exception as error:
            print error
            return
        
        self.tracks[timestamp] = self.append(
            lat, lon, float(state[col.altitude] or 0.0))
        
        TrackFile.element_end(self)

