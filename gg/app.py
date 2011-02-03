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
from gettext import gettext as _
from os.path import basename
from os import environ

# "If I have seen a little further it is by standing on the shoulders of Giants."
#                                    --- Isaac Newton

from utils import ReadableDictionary
from files import Photograph, GPXLoader
from utils import LOCATION, LATITUDE, LONGITUDE
from utils import PATH, SUMMARY, THUMB, TIMESTAMP
from utils import format_coords, valid_coords, maps_link
from utils import get_file, gconf_get, gconf_set, format_list
from utils import load_results, match_func, search_completed, search_bar_clicked
from territories import tz_regions, get_timezone, get_state, get_country

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


class GottenGeography:
    """Provides a graphical interface to automagically geotag photos.
    
    Just load your photos, and load a GPX file, and GottenGeography will
    automatically cross-reference the timestamps on the photos to the timestamps
    in the GPX to determine the three-dimensional coordinates of each photo.
    """
    
################################################################################
# Map navigation section. These methods move and zoom the map around.
################################################################################
    
    def remember_location(self):
        """Add the current location to the history stack."""
        self.history.append( [
            self.map_view.get_property('latitude'),
            self.map_view.get_property('longitude'),
            self.map_view.get_zoom_level()
        ] )
        gconf_set("history", self.history[-5:len(self.history)])
        get_obj("back_button").set_sensitive(True)
    
    def return_to_last(self, button):
        """Return the map view to where the user last set it."""
        lat, lon, zoom = self.history.pop()
        self.map_view.center_on(lat, lon)
        self.map_view.set_zoom_level(zoom)
        button.set_sensitive(len(self.history) > 0)
    
    def move_map_view_by_arrow_keys(self, accel_group, acceleratable, keyval, modifier):
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
    
################################################################################
# Map features section. These methods control map objects.
################################################################################
    
    def display_actors(self, *args):
        """Position and update my custom ClutterActors.
        
        self.actors.coords:       Map center coordinates at top of map view.
        self.actors.coords_bg:    Translucent white bar at top of map view.
        self.actors.crosshair:    Black diamond at map center.
        
        This method is called whenever the size of the map view changes, and
        whenever the map center coordinates change, so that everything is
        always positioned and sized correctly, and displaying the correct
        coordinates.
        """
        stage_width  = self.stage.get_width()
        stage_height = self.stage.get_height()
        self.actors.crosshair.set_position(
            (stage_width  - self.actors.crosshair.get_width())  / 2,
            (stage_height - self.actors.crosshair.get_height()) / 2
        )
        
        if len(args) > 0:
            lat   = self.map_view.get_property('latitude')
            lon   = self.map_view.get_property('longitude')
            label = self.actors.coords
            white = self.actors.coords_bg
            label.set_markup(format_coords(lat, lon))
            white.set_size(stage_width, label.get_height() + 10)
            label.set_position((stage_width - label.get_width()) / 2, 5)
            get_obj("maps_link").set_markup(maps_link(lat, lon))
    
    def update_all_marker_highlights(self, sel):
        """Ensure only the selected markers are highlighted."""
        selection_exists = sel.count_selected_rows() > 0
        self.selected.clear()
        for photo in self.photo.values():
            photo.set_marker_highlight(None, selection_exists)
            # Maintain self.selected for easy iterating.
            if sel.iter_is_selected(photo.iter):
                self.selected.add(photo)
        # Highlight and center the map view over the selected photos.
        if selection_exists:
            area = [ float('inf') ] * 2 + [ float('-inf') ] * 2
            for photo in self.selected:
                photo.set_marker_highlight(area, False)
            if valid_coords(area[0], area[1]):
                self.remember_location()
                self.map_view.ensure_visible(*area + [False])
    
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
    
    def clear_all_gpx(self, widget=None):
        """Forget all GPX data, start over with a clean slate."""
        for polygon in self.polygons:
            polygon.hide()
            # Maybe some day...
            #polygon.clear_points()
            #self.map_view.remove_polygon(polygon)
        
        self.gpx       = []
        self.polygons  = []
        self.tracks    = {}
        self.metadata  = ReadableDictionary({
            'delta': 0,                  # Time offset
            'omega': float('-inf'),      # Final GPX track point
            'alpha': float('inf')        # Initial GPX track point
        })
        gpx_sensitivity(self.tracks)
    
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
            status_message(_("Could not open: ") + format_list(invalid_files))
        self.progressbar.hide()
        self.update_all_marker_highlights(self.listsel)
    
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
            self.photo[filename].update( {
                'iter':   self.liststore.append(),
                'marker': add_marker(filename, self.map_photo_layer, self.listsel, self.photo)
            } )
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
        self.remember_location()
        start_time   = clock()
        
        gpx = GPXLoader(filename, self.gpx_pulse, self.create_polygon)
        status_message(_("%d points loaded in %.2fs.") %
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
    
    def save_all_files(self, widget=None):
        """Ensure all loaded files are saved."""
        self.progressbar.show()
        photos = list(self.modified)
        for i, photo in enumerate(photos, 1):
            self.redraw_interface(i / len(photos), basename(photo.filename))
            try:
                photo.write()
            except Exception as inst:
                status_message(str(inst))
            else:
                self.modified.discard(photo)
                self.liststore.set_value(photo.iter, SUMMARY,
                    photo.long_summary())
        self.progressbar.hide()
    
################################################################################
# Data manipulation. These methods modify the loaded files in some way.
################################################################################
    
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
    
    def apply_selected_photos(self, button=None):
        """Manually apply map center coordinates to all selected photos."""
        for photo in self.selected:
            photo.manual = True
            photo.set_location(
                self.map_view.get_property('latitude'),
                self.map_view.get_property('longitude'))
    
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
        color = make_clutter_color(self.colorpicker)
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
    
    def update_preview(self, chooser):
        """Display photo thumbnail and geotag data in file chooser."""
        label = get_obj("preview_label")
        label.set_label(self.strings.preview)
        image = get_obj("preview_image")
        image.set_from_stock(Gtk.STOCK_FILE, Gtk.IconSize.DIALOG)
        try:
            photo = Photograph(chooser.get_preview_filename(), lambda x: None, 300)
        except IOError:
            return
        image.set_from_pixbuf(photo.thumb)
        label.set_label(format_list([photo.short_summary(), photo.maps_link()], "\n"))
    
    def add_files_dialog(self, *args):
        """Display a file chooser, and attempt to load chosen files."""
        chooser = get_obj("open")
        response = chooser.run()
        chooser.hide()
        if response == Gtk.ResponseType.OK:
            self.open_files(chooser.get_filenames())
    
    def preferences_dialog(self, button, region, cities):
        """Allow the user to configure this application."""
        previous = ReadableDictionary({
            'method': gconf_get("timezone_method"),
            'region': region.get_active(),
            'city':   cities.get_active(),
            'color':  self.colorpicker.get_current_color()
        })
        dialog = get_obj("preferences")
        if not dialog.run():
            self.colorpicker.set_current_color(previous.color)
            self.colorpicker.set_previous_color(previous.color)
            get_obj(previous.method).set_active(True)
            region.set_active(previous.region)
            cities.set_active(previous.city)
        dialog.hide()
    
    def confirm_quit_dialog(self, *args):
        """Teardown method, inform user of unsaved files, if any."""
        self.remember_location()
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
    
    def about_dialog(self, *args):
        """Describe this application to the user."""
        dialog = get_obj("about")
        dialog.run()
        dialog.hide()
    
################################################################################
# Initialization and Gtk boilerplate/housekeeping type stuff and such.
################################################################################
    
    def __init__(self):
        self.history  = gconf_get("history", [[34.5,15.8,2]])
        self.selected = set()
        self.modified = set()
        self.timezone = None
        self.polygons = []
        self.photo    = {}
        self.gpx      = []
        
        champlain            = GtkChamplain.Embed()
        self.map_photo_layer = Champlain.Layer()
        self.map_view        = champlain.get_view()
        self.map_view.add_layer(self.map_photo_layer)
        self.map_view.set_property('show-scale', True)
        self.map_view.set_scroll_mode(Champlain.ScrollMode.KINETIC)
        for signal in [ 'height', 'width', 'latitude', 'longitude' ]:
            self.map_view.connect('notify::' + signal, self.display_actors)
        self.map_view.connect("notify::zoom-level", zoom_button_sensitivity,
            get_obj("zoom_in_button"), get_obj("zoom_out_button"))
        self.map_view.connect("paint", paint_handler)
        
        self.stage  = self.map_view.get_stage()
        self.actors = ReadableDictionary()
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
        for actor in ["coords_bg", "coords"]:
            self.actors[actor].set_parent(self.stage)
            self.actors[actor].raise_top()
            self.actors[actor].show()
        
        self.progressbar = get_obj("progressbar")
        
        self.strings = ReadableDictionary({
            "quit":    get_obj("quit").get_property('secondary-text'),
            "preview": get_obj("preview_label").get_text()
        })
        
        objs = [get_obj("save_button"), get_obj("revert_button"), get_obj("photos_with_buttons"), self.modified, self.selected, self.photo]
        self.liststore = Gtk.ListStore(GObject.TYPE_STRING,
            GObject.TYPE_STRING, GdkPixbuf.Pixbuf, GObject.TYPE_INT)
        self.liststore.set_sort_column_id(TIMESTAMP, Gtk.SortType.ASCENDING)
        self.liststore.connect("row-changed", modification_sensitivity, *objs)
        
        self.cell_string = Gtk.CellRendererText()
        self.cell_thumb  = Gtk.CellRendererPixbuf()
        self.cell_thumb.set_property('stock-id', Gtk.STOCK_MISSING_IMAGE)
        self.cell_thumb.set_property('ypad', 6)
        self.cell_thumb.set_property('xpad', 6)
        
        self.column = Gtk.TreeViewColumn('Photos')
        self.column.pack_start(self.cell_thumb, False)
        self.column.add_attribute(self.cell_thumb, 'pixbuf', THUMB)
        self.column.pack_start(self.cell_string, False)
        self.column.add_attribute(self.cell_string, 'markup', SUMMARY)
        self.column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        
        self.photos_view = Gtk.TreeView(model=self.liststore)
        self.photos_view.set_enable_search(False)
        self.photos_view.set_reorderable(False)
        self.photos_view.set_headers_visible(False)
        self.photos_view.set_rubber_banding(True)
        self.photos_view.append_column(self.column)
        
        self.listsel = self.photos_view.get_selection()
        self.listsel.set_mode(Gtk.SelectionMode.MULTIPLE)
        self.listsel.connect("changed", self.update_all_marker_highlights)
        self.listsel.connect("changed", modification_sensitivity, *objs)
        self.listsel.connect("changed", selection_sensitivity,
            get_obj("apply_button"), get_obj("close_button"))
        
        get_obj("photoscroller").add(self.photos_view)
        get_obj("search_and_map").pack_start(champlain, True, True, 0)
        
        self.search_results = Gtk.ListStore(GObject.TYPE_STRING,
            GObject.TYPE_DOUBLE, GObject.TYPE_DOUBLE)
        search = Gtk.EntryCompletion.new()
        search.set_model(self.search_results)
        search.set_match_func(match_func, self.search_results)
        search.connect("match-selected", search_completed, self.map_view, self.remember_location)
        search.set_minimum_key_length(3)
        search.set_text_column(0)
        entry = get_obj("search")
        entry.set_completion(search)
        entry.connect("changed", load_results, self.search_results)
        entry.connect("icon-release", search_bar_clicked, self.map_view)
        
        self.return_to_last(get_obj("back_button"))
        
        region_box = Gtk.ComboBoxText.new()
        cities_box = Gtk.ComboBoxText.new()
        tz_combos = get_obj("custom_timezone_combos")
        tz_combos.pack_start(region_box, False, False, 10)
        tz_combos.pack_start(cities_box, False, False, 10)
        tz_combos.show_all()
        for name in tz_regions:
            region_box.append(name, name)
        region_box.connect("changed", self.region_handler, cities_box)
        cities_box.connect("changed", self.cities_handler, region_box)
        timezone = gconf_get("timezone", [-1, -1])
        region_box.set_active(timezone[0])
        cities_box.set_active(timezone[1])
        
        click_handlers = {
            "open_button":       [self.add_files_dialog],
            "save_button":       [self.save_all_files],
            "clear_button":      [self.clear_all_gpx],
            "close_button":      [self.close_selected_photos],
            "revert_button":     [self.revert_selected_photos],
            "zoom_out_button":   [zoom_out, self.map_view],
            "zoom_in_button":    [zoom_in, self.map_view],
            "back_button":       [self.return_to_last],
            "about_button":      [self.about_dialog],
            "pref_button":       [self.preferences_dialog, region_box, cities_box],
            "apply_button":      [self.apply_selected_photos],
            "select_all_button": [toggle_selected_photos, self.listsel]
        }
        for button, handler in click_handlers.items():
            get_obj(button).connect("clicked", *handler)
        
        accel  = Gtk.AccelGroup()
        window = get_obj("main")
        window.connect("delete_event", self.confirm_quit_dialog)
        window.add_accel_group(accel)
        window.show_all()
        for key in [ 'Left', 'Right', 'Up', 'Down' ]:
            accel.connect(Gdk.keyval_from_name(key),
                Gdk.ModifierType.MOD1_MASK, 0, self.move_map_view_by_arrow_keys)
        accel.connect(Gdk.keyval_from_name("q"),
            Gdk.ModifierType.CONTROL_MASK, 0, self.confirm_quit_dialog)
        
        modification_sensitivity(*objs)
        self.clear_all_gpx()
        self.redraw_interface()
        self.display_actors(self.map_view)
        
        offset = gconf_get("clock_offset", [0, 0])
        for name in [ "seconds", "minutes" ]:
            spinbutton = get_obj(name)
            spinbutton.connect("value-changed", self.time_offset_changed)
            spinbutton.set_value(offset.pop())
        get_obj("open").connect(
            "update-preview", self.update_preview)
        
        colors = gconf_get("track_color", [32768, 0, 65535])
        self.colorpicker = get_obj("colorselection")
        self.colorpicker.connect("color-changed", track_color_changed, self.polygons)
        self.colorpicker.set_current_color(Gdk.Color(*colors))
        self.colorpicker.set_previous_color(Gdk.Color(*colors))
        
        for option in ["system_timezone", "lookup_timezone", "custom_timezone"]:
            radio = get_obj(option)
            radio.connect("clicked", self.radio_handler, tz_combos)
            radio.set_name(option)
        timezone_method = gconf_get("timezone_method", "system_timezone")
        get_obj(timezone_method).clicked()
    
    def redraw_interface(self, fraction=None, text=None):
        """Tell Gtk to redraw the user interface, so it doesn't look hung.
        
        Primarily used to update the progressbar, but also for disappearing
        some dialogs while things are processing in the background. Won't
        modify the progressbar if called with no arguments.
        """
        if fraction is not None: self.progressbar.set_fraction(fraction)
        if text is not None:     self.progressbar.set_text(str(text))
        while Gtk.events_pending(): Gtk.main_iteration()
    
    def main(self):
        """Animate the crosshair and begin user interaction."""
        xhair = self.actors.crosshair
        xhair.set_parent(self.stage)
        xhair.raise_top()
        xhair.show()
        # This causes the crosshair to start off huge and invisible, and it
        # quickly shrinks, spins, and fades into existence.
        for i in range(500, 7, -1):
            xhair.set_size(i, i)
            xhair.set_z_rotation_from_gravity(53-i, Clutter.Gravity.CENTER)
            xhair.set_property('opacity', int(259-(0.5*i)))
            self.display_actors()
            self.redraw_interface()
            sleep(0.002)
        Gtk.main()

################################################################################
# Misc. functions. TODO: organize these better.
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

def zoom_button_sensitivity(view, signal, zoom_in, zoom_out):
    """Ensure zoom buttons are only sensitive when they need to be."""
    zoom = view.get_zoom_level()
    zoom_out.set_sensitive(view.get_min_zoom_level() is not zoom)
    zoom_in.set_sensitive( view.get_max_zoom_level() is not zoom)

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
    
def paint_handler(map_view):
    """Force the map to redraw.
    
    This is a workaround for this libchamplain bug:
    https://bugzilla.gnome.org/show_bug.cgi?id=638652
    """
    map_view.queue_redraw()

def track_color_changed(selection, polygons):
    """Update the color of any loaded GPX tracks."""
    color = selection.get_current_color()
    one   = make_clutter_color(selection)
    two   = one.lighten().lighten()
    for i, polygon in enumerate(polygons):
        polygon.set_stroke_color(two if i % 2 else one)
    gconf_set("track_color", [color.red, color.green, color.blue])

def make_clutter_color(colorpicker):
    """Generate a Clutter.Color from the currently chosen color."""
    color = colorpicker.get_current_color()
    return Clutter.Color.new(
        *[x / 256 for x in [color.red, color.green, color.blue, 32768]])
    
def add_marker(label, photo_layer, selection, photos):
    """Create a new ChamplainMarker and add it to the map."""
    marker = Champlain.Marker()
    marker.set_name(label)
    marker.set_text(basename(label))
    marker.set_property('reactive', True)
    marker.connect("button-press-event", marker_clicked, selection, photos)
    marker.connect("enter-event", marker_mouse_in)
    marker.connect("leave-event", marker_mouse_out)
    photo_layer.add_marker(marker)
    return marker
    
def marker_clicked(marker, event, selection, photos):
    """When a ChamplainMarker is clicked, select it in the GtkListStore.
    
    The interface defined by this method is consistent with the behavior of
    the GtkListStore itself in the sense that a normal click will select
    just one item, but Ctrl+clicking allows you to select multiple.
    """
    photo = photos[marker.get_name()]
    if event.get_state() & Clutter.ModifierType.CONTROL_MASK:
        if marker.get_highlighted(): selection.unselect_iter(photo.iter)
        else:                        selection.select_iter(photo.iter)
    else:
        get_obj("select_all_button").set_active(False)
        selection.unselect_all()
        selection.select_iter(photo.iter)

def marker_mouse_in(marker, event):
    """Enlarge a hovered-over ChamplainMarker by 5%."""
    marker.set_scale(*[scale * 1.05 for scale in marker.get_scale()])

def marker_mouse_out(marker, event):
    """Reduce a no-longer-hovered ChamplainMarker to it's original size."""
    marker.set_scale(*[scale / 1.05 for scale in marker.get_scale()])

def zoom_in(button, view):
    """Zoom the map in by one level."""
    view.zoom_in()

def zoom_out(button, view):
    """Zoom the map out by one level."""
    view.zoom_out()

def toggle_selected_photos(button, selection):
    """Toggle the selection of photos."""
    if button.get_active(): selection.select_all()
    else:                   selection.unselect_all()

def status_message(message):
    """Display a message on the GtkStatusBar."""
    status = get_obj("status")
    status.push(status.get_context_id("msg"), message)

