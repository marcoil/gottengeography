# GottenGeography - Control how the custom map actors behave.
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

from gi.repository import Champlain, Clutter
from gettext import gettext as _

from common import CommonAttributes, get_obj, map_view
from utils import format_coords

class ActorController(CommonAttributes):
    """Controls the behavior of the custom actors I have placed over the map."""
    
    def __init__(self):
        self.stage = map_view.get_stage()
        self.black = Clutter.Box.new(Clutter.BinLayout())
        self.black.set_color(Clutter.Color.new(0, 0, 0, 64))
        self.label = Clutter.Text()
        self.label.set_color(Clutter.Color.new(255, 255, 255, 255))
        self.xhair = Clutter.Rectangle.new_with_color(
            Clutter.Color.new(0, 0, 0, 64))
        for signal in [ 'latitude', 'longitude' ]:
            map_view.connect('notify::' + signal, self.display,
                get_obj("maps_link"), self.label)
        map_view.connect('notify::width',
            lambda view, param, black:
                black.set_size(view.get_width(), 30),
            self.black)
        
        scale = Champlain.Scale.new()
        scale.connect_view(map_view)
        map_view.bin_layout_add(scale,
            Clutter.BinAlignment.START, Clutter.BinAlignment.END)
        map_view.bin_layout_add(self.black,
            Clutter.BinAlignment.START, Clutter.BinAlignment.START)
        self.black.get_layout_manager().add(self.label,
            Clutter.BinAlignment.CENTER, Clutter.BinAlignment.CENTER)
    
    def display(self, view, param, mlink, label):
        """Display map center coordinates when they change."""
        lat, lon = [ view.get_property(x) for x in ('latitude', 'longitude') ]
        label.set_markup(format_coords(lat, lon))
        mlink.set_markup(
            '<a title="%s" href="http://maps.google.com/maps?ll=%s,%s&amp;spn=%s,%s">Google</a>'
            % (_("View in Google Maps"), lat, lon,
            lon - view.x_to_longitude(0), view.y_to_latitude(0) - lat))
    
    def animate_in(self, start=400):
        """Animate the crosshair."""
        map_view.bin_layout_add(self.xhair,
            Clutter.BinAlignment.CENTER, Clutter.BinAlignment.CENTER)
        self.xhair.set_z_rotation_from_gravity(45, Clutter.Gravity.CENTER)
        for i in xrange(start, 7, -1):
            self.xhair.set_size(i, i)
            opacity = 0.6407035175879398 * (400 - i) # don't ask
            for actor in [self.xhair, self.label, self.black]:
                actor.set_opacity(opacity)
            while Gtk.events_pending():
                Gtk.main_iteration()
            sleep(0.002)

