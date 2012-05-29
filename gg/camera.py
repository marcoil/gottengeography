# Copyright (C) 2012 Robert Park <rbpark@exolucere.ca>
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

"""The Camera class handles per-camera configuration.

It uniquely identifies each camera model that the user owns and stores
settings such as what timezone to use and how wrong the camera's clock is.
A 'relocatable' GSettings schema is used to persist this data across application
launches.
"""

from gi.repository import Gio, GObject, Gtk
from gettext import gettext as _

from version import PACKAGE
from common import get_obj

known_cameras = {}

def get_camera(exif):
    """This method caches Camera instances."""
    names = {'Make': 'Unknown Make', 'Model': 'Unknown Camera'}
    keys = ['Exif.Image.' + key for key in names.keys()
        + ['CameraSerialNumber']] + ['Exif.Photo.BodySerialNumber']
    
    for key in keys:
        try:
            names.update({key.split('.')[-1]: exif[key].value})
        except KeyError:
            pass
    
    camera_id = '_'.join(sorted(names.values())).lower().replace(' ', '_')
    
    if camera_id in known_cameras:
        return known_cameras[camera_id]
    else:
        camera = Camera(camera_id, names['Make'], names['Model'])
        known_cameras[camera_id] = camera
        return camera


class Camera():
    """Store per-camera configuration in GSettings."""
    
    def __init__(self, camera_id, make, model):
        self.camera_id = camera_id
        self.make = make
        self.model = model
        
        label = Gtk.Label()
        label.set_markup('<span size="larger" weight="heavy">%s</span>' % model)
        label.set_property('margin-top', 12)
        
        offset_label = Gtk.Label(_('Clock Offset:'))
        offset = Gtk.SpinButton.new_with_range(-3600, 3600, 1)
        
        grid = get_obj('cameras_view')
        grid.attach_next_to(label, None, Gtk.PositionType.BOTTOM, 2, 1)
        grid.attach_next_to(offset_label, label, Gtk.PositionType.BOTTOM, 1, 1)
        grid.attach_next_to(offset, offset_label, Gtk.PositionType.RIGHT, 1, 1)
        grid.show_all()
        
        self.gst = Gio.Settings.new_with_path(
            'ca.exolucere.%s.camera' % PACKAGE,
            '/ca/exolucere/%s/cameras/%s/'
                % (PACKAGE, camera_id))
        
        self.gst.set_string('make', make)
        self.gst.set_string('model', model)
        
        self.gst.bind('offset', offset, 'value', Gio.SettingsBindFlags.DEFAULT)

