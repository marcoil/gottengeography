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

from gi.repository import Gio

from version import PACKAGE

# TODO: subclass from GObject so that we can bind properties to settings easily.
class Camera():
    """Store per-camera configuration in GSettings."""
    
    def __init__(self, exif):
        names = {'Make': 'Unknown Make', 'Model': 'Unknown Camera'}
        keys = ['Exif.Image.' + key for key in names.keys()
            + ['CameraSerialNumber']] + ['Exif.Photo.BodySerialNumber']
        
        for key in keys:
            try:
                names.update({key.split('.')[-1]: exif[key].value})
            except KeyError:
                pass
        
        camera_id = '_'.join(sorted(names.values())).lower().replace(' ', '_')
        
        self.gst = Gio.Settings.new_with_path(
            'ca.exolucere.%s.camera' % PACKAGE,
            '/ca/exolucere/%s/cameras/%s/'
                % (PACKAGE, camera_id))
        
        self.gst.set_string('make', names['Make'])
        self.gst.set_string('model', names['Model'])

