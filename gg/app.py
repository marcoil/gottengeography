# GottenGeography - Automagically geotags photos by comparing timestamps to GPX data
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

APPNAME = "GottenGeography"
VERSION = "0.5a"

import gettext

gettext.bindtextdomain(APPNAME.lower())
gettext.textdomain(APPNAME.lower())

from gi.repository import GtkClutter, Clutter, GtkChamplain, Champlain
from gi.repository import Gtk, GObject, Gdk, GdkPixbuf
from time import tzset, sleep, clock
from re import search, IGNORECASE
from gettext import gettext as _
from os.path import basename
from os import environ

# "If I have seen a little further it is by standing on the shoulders of Giants."
#                                    --- Isaac Newton

from files import Photograph, GPXLoader
from utils import format_coords, valid_coords, maps_link
from utils import get_file, gconf_get, gconf_set, format_list
from utils import MarkerController, Struct, paint_handler, make_clutter_color
from territories import tz_regions, get_timezone, get_state, get_country

# Handy names for GtkListStore column numbers.
PATH, SUMMARY, THUMB, TIMESTAMP = range(4)
LOCATION, LATITUDE, LONGITUDE = range(3)

GtkClutter.init([])

builder = Gtk.Builder()
builder.set_translation_domain(APPNAME.lower())
builder.add_from_file(get_file("ui.glade"))
get_obj = builder.get_object

# This function embodies almost the entirety of my application's logic.
# The things that come after this method are just implementation details.
def auto_timestamp_comparison(photo, points, metadata):
    """Use GPX data to calculate photo coordinates and elevation."""
    if photo.manual or len(points) < 2:
        return
    
    stamp = metadata.delta + photo.timestamp # in epoch seconds
    hi    = metadata.omega                   # Latest timestamp in GPX file.
    lo    = metadata.alpha                   # Earliest timestamp in GPX file.
    stamp = min(max(stamp, lo), hi)          # Keep timestamp within range.
    
    try:
        lat = points[stamp]['point'].lat     # Try to use an exact match,
        lon = points[stamp]['point'].lon     # if such a thing were to exist.
        ele = points[stamp]['elevation']     # It's more likely than you think.
    
    except KeyError:
        # Find the two points that are nearest (in time) to the photo.
        hi = min([point for point in points if point > stamp])
        lo = max([point for point in points if point < stamp])
        hi_ratio = (stamp - lo) / (hi - lo)  # Proportional amount of time
        lo_ratio = (hi - stamp) / (hi - lo)  # between each point & the photo.
        
        # Find intermediate values using the proportional ratios.
        lat = ((points[lo]['point'].lat * lo_ratio)  +
               (points[hi]['point'].lat * hi_ratio))
        lon = ((points[lo]['point'].lon * lo_ratio)  +
               (points[hi]['point'].lon * hi_ratio))
        ele = ((points[lo]['elevation'] * lo_ratio)  +
               (points[hi]['elevation'] * hi_ratio))
    
    photo.set_location(lat, lon, ele)


class NavigationController:
    """Controls how users navigate the map."""
    default = [[34.5,15.8,2]] # Default lat, lon, zoom for first run.
    
    def __init__(self, view):
        """Start the map at the previous location, and connect signals."""
        self.map_view        = view
        self.back_button     = get_obj("back_button")
        self.zoom_in_button  = get_obj("zoom_in_button")
        self.zoom_out_button = get_obj("zoom_out_button")
        self.back_button.connect("clicked", self.go_back)
        self.zoom_in_button.connect("clicked", self.zoom_in, view)
        self.zoom_out_button.connect("clicked", self.zoom_out, view)
        accel = Gtk.AccelGroup()
        get_obj("main").add_accel_group(accel)
        for key in [ 'Left', 'Right', 'Up', 'Down' ]:
            accel.connect(Gdk.keyval_from_name(key),
                Gdk.ModifierType.MOD1_MASK, 0, self.move_by_arrow_keys)
        self.go_back()
        self.location = [view.get_property(x) for x in
            ('latitude', 'longitude', 'zoom-level')]
        view.connect("notify::latitude", self.remember_location)
        view.connect("notify::longitude", self.remember_location)
        view.connect("notify::zoom-level", self.zoom_button_sensitivity,
            self.zoom_in_button, self.zoom_out_button)
    
    def move_by_arrow_keys(self, accel_group, acceleratable, keyval, modifier):
        """Move the map view by 5% of its length in the given direction."""
        x   = self.map_view.get_width()  / 2
        y   = self.map_view.get_height() / 2
        key = Gdk.keyval_name(keyval)
        lat = self.map_view.get_property('latitude')
        lon = self.map_view.get_property('longitude')
        lat2, lon2 = self.map_view.get_coords_at(
            *[i * (0.9 if key in ("Up", "Left") else 1.1) for i in (x, y)])
        if   key in ("Up", "Down"):    lat = lat2
        elif key in ("Left", "Right"): lon = lon2
        if valid_coords(lat, lon):
            self.map_view.center_on(lat, lon)
    
    def remember_location(self, view, param):
        """Add the current location to the history stack."""
        location = [view.get_property(x) for x in
            ('latitude', 'longitude', 'zoom-level')]
        for x, y in zip(location[0:2], self.location[0:2]):
            if abs(x-y) > 0.25:
                history = gconf_get("history") or self.default
                if history[-1] != location:
                    history.append(self.location)
                    gconf_set("history", history[-30:len(history)])
                    self.back_button.set_sensitive(True)
                    self.location = location
                    break
    
    def force_remember(self):
        """Ignore threshholds, add current location to history stack."""
        history = gconf_get("history") or self.default
        history.append([self.map_view.get_property(x) for x in
            ('latitude', 'longitude', 'zoom-level')])
        gconf_set("history", history)
    
    def go_back(self, *args):
        """Return the map view to where the user last set it."""
        history = gconf_get("history") or self.default
        lat, lon, zoom = history.pop()
        if valid_coords(lat, lon):
            self.map_view.center_on(lat, lon)
            self.map_view.set_zoom_level(zoom)
        self.back_button.set_sensitive(len(history) > 0)
        gconf_set("history", history)
    
    def zoom_in(self, button, view):
        """Zoom the map in by one level."""
        view.zoom_in()
    
    def zoom_out(self, button, view):
        """Zoom the map out by one level."""
        view.zoom_out()
    
    def zoom_button_sensitivity(self, view, signal, zoom_in, zoom_out):
        """Ensure zoom buttons are only sensitive when they need to be."""
        zoom = view.get_zoom_level()
        zoom_out.set_sensitive(view.get_min_zoom_level() is not zoom)
        zoom_in.set_sensitive( view.get_max_zoom_level() is not zoom)


class SearchController:
    """Controls the behavior for searching the map."""
    def __init__(self, view):
        """Make the search box and insert it into the window."""
        self.results = Gtk.ListStore(GObject.TYPE_STRING,
            GObject.TYPE_DOUBLE, GObject.TYPE_DOUBLE)
        search = Gtk.EntryCompletion.new()
        search.set_model(self.results)
        search.set_match_func(self.match_func, self.results)
        search.connect("match-selected", self.search_completed, view)
        search.set_minimum_key_length(3)
        search.set_text_column(0)
        entry = get_obj("search")
        entry.set_completion(search)
        entry.connect("changed", self.load_results, self.results)
        entry.connect("icon-release", self.search_bar_clicked, view)
    
    def load_results(self, entry, results, searched=set()):
        """Load a few search results based on what's been typed.
        
        Requires at least three letters typed, and is careful not to load
        duplicate results.
        
        The searched argument persists across calls to this method, and should
        not be passed as an argument unless your intention is to trigger the
        loading of duplicate results.
        """
        text = entry.get_text().lower()[0:3]
        if len(text) == 3 and text not in searched:
            searched.add(text)
            with open(get_file("cities.txt")) as cities:
                append = results.append
                for line in cities:
                    city, lat, lon, country, state, tz = line.split("\t")
                    if search('(^|\s)' + text, city, flags=IGNORECASE):
                        state    = get_state(country, state)
                        country  = get_country(country)
                        location = format_list([city, state, country])
                        append([location, float(lat), float(lon)])
    
    def match_func(self, completion, string, itr, model):
        """Determine whether or not to include a given search result.
        
        This matches the beginning of any word in the name of the city. For
        example, a search for "spring" will contain "Palm Springs" as well as
        "Springfield".
        """
        location = model.get_value(itr, LOCATION)
        if location and search('(^|\s)' + string, location, flags=IGNORECASE):
            return True
    
    def search_completed(self, entry, model, itr, view):
        """Go to the selected location."""
        loc, lat, lon = model.get(itr, LOCATION, LATITUDE, LONGITUDE)
        gconf_set("searched", [loc, lat, lon])
        view.center_on(lat, lon)
        view.set_zoom_level(11)
    
    def search_bar_clicked(self, entry, icon_pos, event, view):
        """Go to the most recent location when the user clicks the jump icon."""
        location, lat, lon = gconf_get("searched", [None, None, None])
        if valid_coords(lat, lon):
            entry.set_text(location)
            view.center_on(lat, lon)


class PreferencesController:
    """Controls the behavior of the preferences dialog."""
    def __init__(self, set_timezone):
        self.set_timezone = set_timezone
        self.pref_button  = get_obj("pref_button")
        self.region       = Gtk.ComboBoxText.new()
        self.cities       = Gtk.ComboBoxText.new()
        tz_combos         = get_obj("custom_timezone_combos")
        tz_combos.pack_start(self.region, False, False, 10)
        tz_combos.pack_start(self.cities, False, False, 10)
        tz_combos.show_all()
        
        for name in tz_regions:
            self.region.append(name, name)
        self.region.connect("changed", self.region_handler, self.cities)
        self.cities.connect("changed", self.cities_handler, self.region)
        timezone = gconf_get("timezone", [-1, -1])
        self.region.set_active(timezone[0])
        self.cities.set_active(timezone[1])
        
        self.pref_button.connect("clicked", self.preferences_dialog,
            get_obj("preferences"), self.region, self.cities)
        
        colors = gconf_get("track_color", [32768, 0, 65535])
        self.colorpicker = get_obj("colorselection")
        self.colorpicker.connect("color-changed", self.track_color_changed, GottenGeography.polygons)
        self.colorpicker.set_current_color(Gdk.Color(*colors))
        self.colorpicker.set_previous_color(Gdk.Color(*colors))
        
        for option in ["system", "lookup", "custom"]:
            option += "_timezone"
            radio = get_obj(option)
            radio.connect("clicked", self.radio_handler, tz_combos)
            radio.set_name(option)
        timezone_method = gconf_get("timezone_method", "system_timezone")
        get_obj(timezone_method).clicked()
    
    def preferences_dialog(self, button, dialog, region, cities):
        """Allow the user to configure this application."""
        previous = Struct({
            'method': gconf_get("timezone_method"),
            'region': region.get_active(),
            'city':   cities.get_active(),
            'color':  self.colorpicker.get_current_color()
        })
        if not dialog.run():
            self.colorpicker.set_current_color(previous.color)
            self.colorpicker.set_previous_color(previous.color)
            get_obj(previous.method).set_active(True)
            region.set_active(previous.region)
            cities.set_active(previous.city)
        dialog.hide()
    
    def radio_handler(self, radio, combos):
        """Reposition photos depending on which timezone the user selected."""
        if radio.get_active():
            gconf_set("timezone_method", radio.get_name())
            combos.set_sensitive(radio.get_name() == "custom_timezone")
            self.set_timezone()
    
    def region_handler(self, regions, cities):
        """Populate the list of cities when a continent is selected."""
        cities.remove_all()
        for city in get_timezone(regions.get_active_id(), []):
            cities.append(city, city)
    
    def cities_handler(self, cities, regions):
        """When a city is selected, update the chosen timezone."""
        gconf_set("timezone",
            [regions.get_active(), cities.get_active()])
        if cities.get_active_id() is not None:
            self.set_timezone()
    
    def track_color_changed(self, selection, polygons):
        """Update the color of any loaded GPX tracks."""
        color = selection.get_current_color()
        one   = make_clutter_color(color)
        two   = one.lighten().lighten()
        for i, polygon in enumerate(polygons):
            polygon.set_stroke_color(two if i % 2 else one)
        gconf_set("track_color", [color.red, color.green, color.blue])


class GottenGeography:
    """Provides a graphical interface to automagically geotag photos.
    
    Just load your photos, and load a GPX file, and GottenGeography will
    automatically cross-reference the timestamps on the photos to the timestamps
    in the GPX to determine the three-dimensional coordinates of each photo.
    """
    
    selected = set()
    modified = set()
    timezone = None
    polygons = []
    tracks   = {}
    photo    = {}
    gpx      = []
    
################################################################################
# File data handling. These methods interact with files (loading, saving, etc)
################################################################################
    
    def open_files(self, files):
        """Attempt to load all of the specified files."""
        self.progressbar.show()
        invalid_files = []
        for i, name in enumerate(files, 1):
            self.redraw_interface(i / len(files), basename(name))
            try:
                try:            self.load_img_from_file(name)
                except IOError: self.load_gpx_from_file(name)
            except IOError:
                invalid_files.append(basename(name))
        if len(invalid_files) > 0:
            self.status_message(_("Could not open: ") + format_list(invalid_files))
        self.progressbar.hide()
        self.listsel.emit("changed")
    
    def load_img_from_file(self, filename):
        """Create or update a row in the ListStore.
        
        Checks if the file has already been loaded, and if not, creates a new
        row in the ListStore. Either way, it then populates that row with
        photo metadata as read from disk. Effectively, this is used both for
        loading new photos, and reverting old photos, discarding any changes.
        
        Raises IOError if filename refers to a file that is not a photograph.
        """
        if filename not in self.photo:
            self.photo[filename] = Photograph(filename, self.modify_summary)
            self.photo[filename].iter   = self.liststore.append()
            self.photo[filename].marker = self.markers.add(filename)
        else:
            self.photo[filename].read()
        photo = self.photo[filename]
        photo.position_marker()
        self.modified.discard(photo)
        self.liststore.set_row(photo.iter,
            [filename, photo.long_summary(), photo.thumb, photo.timestamp])
        auto_timestamp_comparison(photo, self.tracks, self.metadata)
    
    def load_gpx_from_file(self, filename):
        """Parse GPX data, drawing each GPS track segment on the map."""
        start_time = clock()
        
        gpx = GPXLoader(filename, self.gpx_pulse, self.create_polygon)
        self.status_message(_("%d points loaded in %.2fs.") %
            (len(gpx.tracks), clock() - start_time))
        
        self.tracks.update(gpx.tracks)
        self.gpx.append(gpx)
        self.metadata.alpha = min(self.metadata.alpha, gpx.alpha)
        self.metadata.omega = max(self.metadata.omega, gpx.omega)
        if len(gpx.tracks) > 0:
            self.map_view.set_zoom_level(self.map_view.get_max_zoom_level())
            self.map_view.ensure_visible(*gpx.area + [False])
        self.timezone = gpx.lookup_geoname()
        gpx_sensitivity(self.tracks)
        self.set_timezone()
    
    def apply_selected_photos(self, button, selected, view):
        """Manually apply map center coordinates to all selected photos."""
        for photo in selected:
            photo.manual = True
            photo.set_location(
                view.get_property('latitude'),
                view.get_property('longitude'))
    
    def revert_selected_photos(self, button=None):
        """Discard any modifications to all selected photos."""
        self.open_files([photo.filename for photo in self.modified & self.selected])
    
    def close_selected_photos(self, button=None):
        """Discard all selected photos."""
        for photo in self.selected.copy():
            photo.marker.destroy()
            del self.photo[photo.filename]
            self.modified.discard(photo)
            self.liststore.remove(photo.iter)
        get_obj("select_all_button").set_active(False)
    
    def save_all_files(self, widget=None):
        """Ensure all loaded files are saved."""
        self.progressbar.show()
        photos = list(self.modified)
        for i, photo in enumerate(photos, 1):
            self.redraw_interface(i / len(photos), basename(photo.filename))
            try:
                photo.write()
            except Exception as inst:
                self.status_message(str(inst))
            else:
                self.modified.discard(photo)
                self.liststore.set_value(photo.iter, SUMMARY,
                    photo.long_summary())
        self.progressbar.hide()
    
################################################################################
# Map features section. These methods control map objects.
################################################################################
    
    def display_actors(self, view, param, mlink):
        """Position and update my custom ClutterActors.
        
        label:    Map center coordinates at top of map view.
        white:    Translucent white bar at top of map view.
        xhair:    Black diamond at map center.
        mlink:    Link to google maps in status bar.
        
        This method is called whenever the size of the map view changes, and
        whenever the map center coordinates change, so that everything is
        always positioned and sized correctly, and displaying the correct
        coordinates.
        """
        xhair = self.actors.crosshair
        stage_width  = view.get_width()
        stage_height = view.get_height()
        xhair.set_position(
            (stage_width  - xhair.get_width())  / 2,
            (stage_height - xhair.get_height()) / 2
        )
        
        if param is not None:
            label, white = self.actors.coords, self.actors.coords_bg
            lat   = view.get_property('latitude')
            lon   = view.get_property('longitude')
            label.set_markup(format_coords(lat, lon))
            white.set_size(stage_width, label.get_height() + 10)
            label.set_position((stage_width - label.get_width()) / 2, 5)
            mlink.set_markup(maps_link(lat, lon))
    
    def toggle_selected_photos(self, button, selection):
        """Toggle the selection of photos."""
        if button.get_active(): selection.select_all()
        else:                   selection.unselect_all()
    
    def clear_all_gpx(self, widget=None):
        """Forget all GPX data, start over with a clean slate."""
        for polygon in self.polygons:
            polygon.hide()
            # Maybe some day...
            #polygon.clear_points()
            #self.map_view.remove_polygon(polygon)
        
        del self.gpx[:]
        del self.polygons[:]
        self.tracks.clear()
        self.metadata = Struct({
            'delta': 0,                  # Time offset
            'omega': float('-inf'),      # Final GPX track point
            'alpha': float('inf')        # Initial GPX track point
        })
        gpx_sensitivity(self.tracks)
    
################################################################################
# Data manipulation. These methods modify the loaded files in some way.
################################################################################
    
    def set_timezone(self):
        """Set the timezone to the given zone and update all photos."""
        option = gconf_get("timezone_method")
        if "TZ" in environ:
            del environ["TZ"]
        if   option == "lookup_timezone" and self.timezone is not None:
            environ["TZ"] = self.timezone
        elif option == "custom_timezone":
            region, cities = get_obj("custom_timezone_combos").get_children()
            region = region.get_active_id()
            city   = cities.get_active_id()
            if region is not None and city is not None:
                environ["TZ"] = "%s/%s" % (region, city)
        tzset()
        for photo in self.photo.values():
            photo.calculate_timestamp()
            auto_timestamp_comparison(photo, self.tracks, self.metadata)
    
    def time_offset_changed(self, widget):
        """Update all photos each time the camera's clock is corrected."""
        seconds = get_obj("seconds").get_value()
        minutes = get_obj("minutes").get_value()
        offset  = int((minutes * 60) + seconds)
        gconf_set("clock_offset", [minutes, seconds])
        if offset != self.metadata.delta:
            self.metadata.delta = offset
            if abs(seconds) == 60 and abs(minutes) != 60:
                minutes += seconds / 60
                get_obj("seconds").set_value(0)
                get_obj("minutes").set_value(minutes)
            for photo in self.photo.values():
                auto_timestamp_comparison(photo, self.tracks, self.metadata)
    
    def modify_summary(self, photo):
        """Insert the current photo summary into the liststore."""
        self.modified.add(photo)
        self.liststore.set_value(photo.iter, SUMMARY,
            ('<b>%s</b>' % photo.long_summary()))
    
    def gpx_pulse(self, gpx):
        """Update the display during GPX parsing.
        
        This is called by GPXLoader every 0.2s during parsing so that we
        can prevent the display from looking hung.
        """
        self.progressbar.pulse()
        while Gtk.events_pending():
            Gtk.main_iteration()
    
    def create_polygon(self):
        """Get a newly created Champlain.Polygon and decorate it."""
        color = make_clutter_color(self.prefs.colorpicker.get_current_color())
        polygon = Champlain.Polygon()
        self.polygons.append(polygon)
        polygon.set_stroke_width(5)
        polygon.set_stroke_color(
            color if len(self.polygons) % 2 else color.lighten().lighten())
        polygon.show()
        self.map_view.add_polygon(polygon)
        return polygon.append_point
    
################################################################################
# Dialogs. Various dialog-related methods for user interaction.
################################################################################
    
    def update_preview(self, chooser, label, image):
        """Display photo thumbnail and geotag data in file chooser."""
        label.set_label(self.strings.preview)
        image.set_from_stock(Gtk.STOCK_FILE, Gtk.IconSize.DIALOG)
        try:
            photo = Photograph(chooser.get_preview_filename(), lambda x: None, 300)
        except IOError:
            return
        image.set_from_pixbuf(photo.thumb)
        label.set_label(format_list([photo.short_summary(), photo.maps_link()], "\n"))
    
    def add_files_dialog(self, button, chooser):
        """Display a file chooser, and attempt to load chosen files."""
        response = chooser.run()
        chooser.hide()
        if response == Gtk.ResponseType.OK:
            self.open_files(chooser.get_filenames())
    
    def confirm_quit_dialog(self, *args):
        """Teardown method, inform user of unsaved files, if any."""
        self.navigator.force_remember()
        if len(self.modified) == 0:
            Gtk.main_quit()
            return True
        dialog = get_obj("quit")
        dialog.format_secondary_markup(self.strings.quit % len(self.modified))
        response = dialog.run()
        dialog.hide()
        self.redraw_interface()
        if response == Gtk.ResponseType.ACCEPT: self.save_all_files()
        if response != Gtk.ResponseType.CANCEL: Gtk.main_quit()
        return True
    
    def about_dialog(self, button, dialog):
        """Describe this application to the user."""
        # you can
        dialog.run()
        # but you can't
        dialog.hide()
        # ahahahhahahah!
    
################################################################################
# Initialization and Gtk boilerplate/housekeeping type stuff and such.
################################################################################
    
    def __init__(self):
        champlain            = GtkChamplain.Embed()
        self.map_photo_layer = Champlain.Layer()
        self.map_view        = champlain.get_view()
        self.map_view.add_layer(self.map_photo_layer)
        self.map_view.set_property('show-scale', True)
        self.map_view.set_scroll_mode(Champlain.ScrollMode.KINETIC)
        
        self.navigator = NavigationController(self.map_view)
        
        self.stage  = self.map_view.get_stage()
        self.actors = Struct()
        self.actors.coords_bg = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(255, 255, 255, 164))
        self.actors.coords_bg.set_position(0, 0)
        self.actors.coords = Clutter.Text()
        self.actors.coords.set_single_line_mode(True)
        self.actors.crosshair = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(0, 0, 0, 32))
        self.actors.crosshair.set_property('has-border', True)
        self.actors.crosshair.set_border_color(Clutter.Color.new(0, 0, 0, 128))
        self.actors.crosshair.set_border_width(1)
        for actor in [self.actors.coords_bg, self.actors.coords]:
            actor.set_parent(self.stage)
            actor.raise_top()
            actor.show()
        for signal in [ 'height', 'width', 'latitude', 'longitude' ]:
            self.map_view.connect('notify::' + signal, self.display_actors,
                get_obj("maps_link"))
        self.map_view.connect("paint", paint_handler)
        
        self.progressbar = get_obj("progressbar")
        self.status      = get_obj("status")
        
        self.strings = Struct({
            "quit":    get_obj("quit").get_property('secondary-text'),
            "preview": get_obj("preview_label").get_text()
        })
        
        objs = [get_obj("save_button"), get_obj("revert_button"),
            get_obj("photos_with_buttons"), self.modified, self.selected,
            self.photo]
        self.liststore = Gtk.ListStore(GObject.TYPE_STRING,
            GObject.TYPE_STRING, GdkPixbuf.Pixbuf, GObject.TYPE_INT)
        self.liststore.set_sort_column_id(TIMESTAMP, Gtk.SortType.ASCENDING)
        self.liststore.connect("row-changed", modification_sensitivity, *objs)
        
        cell_string = Gtk.CellRendererText()
        cell_thumb  = Gtk.CellRendererPixbuf()
        cell_thumb.set_property('stock-id', Gtk.STOCK_MISSING_IMAGE)
        cell_thumb.set_property('ypad', 6)
        cell_thumb.set_property('xpad', 6)
        
        column = Gtk.TreeViewColumn('Photos')
        column.pack_start(cell_thumb, False)
        column.add_attribute(cell_thumb, 'pixbuf', THUMB)
        column.pack_start(cell_string, False)
        column.add_attribute(cell_string, 'markup', SUMMARY)
        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        
        photos_view = Gtk.TreeView(model=self.liststore)
        photos_view.set_enable_search(False)
        photos_view.set_reorderable(False)
        photos_view.set_headers_visible(False)
        photos_view.set_rubber_banding(True)
        photos_view.append_column(column)
        
        self.listsel = photos_view.get_selection()
        self.listsel.set_mode(Gtk.SelectionMode.MULTIPLE)
        
        get_obj("photoscroller").add(photos_view)
        get_obj("search_and_map").pack_start(champlain, True, True, 0)
        
        self.search  = SearchController(self.map_view)
        self.prefs   = PreferencesController(self.set_timezone)
        self.markers = MarkerController(self.map_photo_layer, self.listsel,
            get_obj("select_all_button"), self.selected, self.photo, self.map_view)
        
        self.listsel.connect("changed", modification_sensitivity, *objs)
        self.listsel.connect("changed", selection_sensitivity,
            get_obj("apply_button"), get_obj("close_button"))
        
        click_handlers = {
            "open_button":       [self.add_files_dialog, get_obj("open")],
            "save_button":       [self.save_all_files],
            "clear_button":      [self.clear_all_gpx],
            "close_button":      [self.close_selected_photos],
            "revert_button":     [self.revert_selected_photos],
            "about_button":      [self.about_dialog, get_obj("about")],
            "apply_button":      [self.apply_selected_photos, self.selected, self.map_view],
            "select_all_button": [self.toggle_selected_photos, self.listsel]
        }
        for button, handler in click_handlers.items():
            get_obj(button).connect("clicked", *handler)
        
        accel  = Gtk.AccelGroup()
        window = get_obj("main")
        window.connect("delete_event", self.confirm_quit_dialog)
        window.add_accel_group(accel)
        window.show_all()
        accel.connect(Gdk.keyval_from_name("q"),
            Gdk.ModifierType.CONTROL_MASK, 0, self.confirm_quit_dialog)
        
        modification_sensitivity(*objs)
        self.clear_all_gpx()
        
        offset = gconf_get("clock_offset", [0, 0])
        for name in [ "seconds", "minutes" ]:
            spinbutton = get_obj(name)
            spinbutton.connect("value-changed", self.time_offset_changed)
            spinbutton.set_value(offset.pop())
        get_obj("open").connect("update-preview", self.update_preview,
            get_obj("preview_label"), get_obj("preview_image"))
        
        self.redraw_interface()
    
    def redraw_interface(self, fraction=None, text=None):
        """Tell Gtk to redraw the user interface, so it doesn't look hung.
        
        Primarily used to update the progressbar, but also for disappearing
        some dialogs while things are processing in the background. Won't
        modify the progressbar if called with no arguments.
        """
        if fraction is not None: self.progressbar.set_fraction(fraction)
        if text is not None:     self.progressbar.set_text(str(text))
        while Gtk.events_pending(): Gtk.main_iteration()
    
    def status_message(self, message):
        """Display a message on the GtkStatusBar."""
        self.status.push(self.status.get_context_id("msg"), message)
    
    def main(self):
        """Animate the crosshair and begin user interaction."""
        xhair = self.actors.crosshair
        xhair.set_parent(self.stage)
        xhair.raise_top()
        xhair.show()
        display = [self.map_view, None, get_obj("maps_link")]
        # This causes the crosshair to start off huge and invisible, and it
        # quickly shrinks, spins, and fades into existence.
        for i in range(500, 7, -1):
            xhair.set_size(i, i)
            xhair.set_z_rotation_from_gravity(53-i, Clutter.Gravity.CENTER)
            xhair.set_property('opacity', int(259-(0.5*i)))
            self.display_actors(*display)
            self.redraw_interface()
            sleep(0.002)
        Gtk.main()

################################################################################
# Sensitivity. These methods ensure proper sensitivity of various widgets.
################################################################################

def modification_sensitivity(*args):
    """Ensure save and revert buttons are sensitive only when they need to be.
    
    The signature of this method is weird because it's the handler for two
    different signals that pass a different number of irrelevant arguments.
    """
    save, revert, left, modified, selected, photo = args[-6:len(args)]
    save.set_sensitive(  len(modified) > 0)
    revert.set_sensitive(len(modified & selected) > 0)
    if len(photo) > 0: left.show()
    else:              left.hide()

def gpx_sensitivity(tracks):
    """Control the sensitivity of GPX-related widgets."""
    gpx_sensitive = len(tracks) > 0
    for widget in [ "minutes", "seconds", "offset_label", "clear_button" ]:
        get_obj(widget).set_sensitive(gpx_sensitive)

def selection_sensitivity(selection, apply_button, close_button):
    """Control the sensitivity of Apply and Close buttons."""
    sensitive = selection.count_selected_rows() > 0
    apply_button.set_sensitive(sensitive)
    close_button.set_sensitive(sensitive)

