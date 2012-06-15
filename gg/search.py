# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Control how the map is searched."""

from __future__ import division

from gi.repository import Gtk
from os.path import join

from territories import get_state, get_country
from widgets import Widgets, MapView
from build_info import PKG_DATA_DIR

# ListStore column names
LOCATION, LATITUDE, LONGITUDE = range(3)


class SearchController():
    """Controls the behavior for searching the map."""
    last_search = None
    
    def __init__(self):
        """Make the search box and insert it into the window."""
        self.search = None
        self.results = Widgets.search_results
        search = Widgets.search_completion
        search.set_match_func(
            lambda c, s, itr, get:
                (get(itr, LOCATION) or '').lower().find(self.search) > -1,
            self.results.get_value)
        search.connect('match-selected', self.search_completed)
        entry = Widgets.search_box
        entry.connect('changed', self.load_results, self.results.append)
        entry.connect('icon-release', lambda entry, i, e: entry.set_text(''))
        entry.connect('icon-release', lambda *ignore: entry.emit('grab_focus'))
        entry.connect('activate', self.repeat_last_search, self.results)
    
    def load_results(self, entry, append, searched=set()):
        """Load a few search results based on what's been typed.
        
        Requires at least three letters typed, and is careful not to load
        duplicate results.
        
        The searched argument persists across calls to this method, and should
        not be passed as an argument unless your intention is to trigger the
        loading of duplicate results.
        """
        self.search = entry.get_text().lower()
        three = self.search[0:3]
        if len(three) == 3 and three not in searched:
            searched.add(three)
            with open(join(PKG_DATA_DIR, 'cities.txt')) as cities:
                for line in cities:
                    city, lat, lon, country, state = line.split('\t')[0:5]
                    if city.lower().find(three) > -1:
                        append([
                            ', '.join([s for s in [city,
                                                   get_state(country, state),
                                                   get_country(country)] if s]),
                            float(lat),
                            float(lon)])
    
    def search_completed(self, entry, model, itr):
        """Go to the selected location."""
        self.last_search = itr.copy()
        MapView.emit('realize')
        MapView.set_zoom_level(MapView.get_max_zoom_level())
        Widgets.redraw_interface()
        MapView.center_on(*model.get(itr, LATITUDE, LONGITUDE))
        MapView.set_zoom_level(11)
    
    def repeat_last_search(self, entry, model):
        """Snap back to the last-searched location when user hits enter key."""
        if self.last_search is not None:
            self.search_completed(entry, model, self.last_search)

