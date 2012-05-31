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

"""Control the behavior of various application preferences."""

from __future__ import division

from gi.repository import Gtk, Gdk
from gi.repository import Champlain
from gi.repository import Clutter
from time import tzset
from os import environ

from common import Struct, photos, map_view
from common import auto_timestamp_comparison, get_obj, gst

class PreferencesController():
    """Controls the behavior of the preferences dialog."""
    
    def __init__(self):
        gst.bind('use-dark-theme', Gtk.Settings.get_default(),
                 'gtk-application-prefer-dark-theme')

