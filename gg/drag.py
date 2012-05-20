# GottenGeography - Control the drag & drop behavior.
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

from __future__ import division

from gi.repository import Gtk, Gdk
from urlparse import urlparse

from common import CommonAttributes, Struct
from common import get_obj, map_view
from common import selected

class DragController(CommonAttributes):
    """Control the drag & drop behavior."""
    
    def __init__(self, open_files):
        self.external_drag = True
        
        photos_view = get_obj('photos_view')
        photos_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK,
            [], Gdk.DragAction.COPY)
        photos_view.drag_source_add_text_targets()
        photos_view.connect('drag-data-get', self.photo_drag_start)
        
        map_container = get_obj('map_container')
        map_container.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        map_container.drag_dest_add_text_targets()
        map_container.connect('drag-data-received', self.photo_drag_end, open_files)
    
    def photo_drag_start(self, widget, drag_context, data, info, time):
        """Allow dragging more than one photo."""
        self.external_drag = False # Don't reload files from disk
        files = [ photo.filename for photo in selected ]
        data.set_text('\n'.join(files), -1)
    
    def photo_drag_end(self, widget, drag_context, x, y, data, info, time, open_files):
        """Respond to drops and position photos accordingly.
        
        This method allows photos to be dropped in from the photo pane or any
        other drag source, such as the file browser.
        """
        files = [urlparse(s).path.strip() for s in data.get_text().split('\n') if s]
        
        if self.external_drag:
            open_files(files)
        self.external_drag = True
        
        # The dummy is used in the case of XML files, which can be opened by
        # drag & drop but then don't need to have set_location called on them.
        dummy = Struct({'set_location': lambda x,y: None})
        for filename in files:
            self.photo.get(filename, dummy).set_location(
                map_view.y_to_latitude(y),
                map_view.x_to_longitude(x))
        
        map_view.emit('animation-completed')

