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

"""Control the drag & drop behavior.

This class allows three types of drags to happen:

1. Drags from an external source onto the left-hand photo pane.

2. Drags from an external source onto the map.

3. Drags from the left-hand photo pane onto the map.

In cases 2 & 3 where photos are dragged onto the map (regardless of the drag
source), the photos will be tagged with the precise map coordinates that they
were dragged to on the map. Otherwise the photos are simply loaded without
any modifications being made to the location tags.
"""

from __future__ import division

from gi.repository import Gtk, Gdk
from urlparse import urlparse

from common import Struct, get_obj, map_view, selected, modified, photos

class DragController():
    """Control the drag & drop behavior."""
    
    def __init__(self, open_files):
        # Drag source definitons
        photos_view = get_obj('photos_view')
        photos_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK,
            [], Gdk.DragAction.COPY)
        photos_view.drag_source_add_text_targets()
        photos_view.connect('drag-data-get', self.photo_drag_start)
        
        # Drag destination defintions
        photos_view.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        photos_view.drag_dest_add_text_targets()
        photos_view.connect('drag-data-received', self.photo_drag_end,
                            open_files, False)
        
        container = get_obj('map_container')
        container.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        container.drag_dest_add_text_targets()
        container.connect('drag-data-received', self.photo_drag_end,
                          open_files, True)
        
        self.external_drag = True
        self.selection = photos_view.get_selection()
    
    def photo_drag_start(self, widget, drag_context, data, info, time):
        """Allow dragging more than one photo."""
        self.external_drag = False # Don't reload files from disk
        files = [ photo.filename for photo in selected ]
        data.set_text('\n'.join(files), -1)
    
    def photo_drag_end(self, widget, drag_context, x, y,
                       data, info, time, open_files, on_map):
        """Respond to drops and position photos accordingly.
        
        This method allows photos to be dropped in from the photo
        pane or any other drag source, such as the file browser.
        """
        files = [urlparse(s).path.strip() for s in
                 data.get_text().split('\n') if s]
        
        if self.external_drag:
            open_files(files)
        self.external_drag = True
        
        if on_map:
          for filename in files:
                photo = photos.get(filename)
                if photo is not None:
                    photo.manual = True
                    photo.set_location(
                        map_view.y_to_latitude(y),
                        map_view.x_to_longitude(x))
                    modified.add(photo)
        
        self.selection.emit('changed')
        map_view.emit('animation-completed')

