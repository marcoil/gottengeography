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

"""Control how the map is searched."""

from __future__ import division

from os.path import join
from re import compile as re_compile, IGNORECASE

from territories import get_state, get_country
from common import get_obj, map_view
from build_info import PKG_DATA_DIR
from gpsmath import format_list

# ListStore column names
LOCATION, LATITUDE, LONGITUDE = range(3)

class SearchController():
    """Controls the behavior for searching the map."""
    last_search = None
    
    def __init__(self):
        """Make the search box and insert it into the window."""
        self.search = None
        self.results = get_obj('search_results')
        self.slide_to = map_view.go_to
        search = get_obj('search_completion')
        search.set_match_func(
            lambda c, s, itr, get: self.search(get(itr, LOCATION) or ''),
            self.results.get_value)
        search.connect('match-selected', self.search_completed, map_view)
        entry = get_obj('search_box')
        entry.connect('changed', self.load_results, self.results.append)
        entry.connect('icon-release', lambda entry, i, e: entry.set_text(''))
        entry.connect('activate', self.repeat_last_search,
                      self.results, map_view)
    
    def load_results(self, entry, append, searched=set()):
        """Load a few search results based on what's been typed.
        
        Requires at least three letters typed, and is careful not to load
        duplicate results.
        
        The searched argument persists across calls to this method, and should
        not be passed as an argument unless your intention is to trigger the
        loading of duplicate results.
        """
        text  = entry.get_text().lower()
        three = text[0:3]
        self.search, search = [ re_compile('(^|\s)' + string,
            flags=IGNORECASE).search for string in (text, three) ]
        if len(three) == 3 and three not in searched:
            searched.add(three)
            with open(join(PKG_DATA_DIR, 'cities.txt')) as cities:
                for line in cities:
                    city, lat, lon, country, state = line.split('\t')[0:5]
                    if search(city):
                        append([format_list([city,
                                             get_state(country, state),
                                             get_country(country)]),
                                float(lat),
                                float(lon)])
    
    def search_completed(self, entry, model, itr, view):
        """Go to the selected location."""
        self.last_search = itr.copy()
        map_view.emit('realize')
        view.set_zoom_level(11)
        self.slide_to(*model.get(itr, LATITUDE, LONGITUDE))
    
    def repeat_last_search(self, entry, model, view):
        """Snap back to the last-searched location when user hits enter key."""
        if self.last_search is not None:
            self.search_completed(entry, model, self.last_search, view)

