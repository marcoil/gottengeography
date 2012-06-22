# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Control the drag & drop behavior.

This class allows three types of drags to happen:

1. Drags from an external source onto the left-hand photo pane.

2. Drags from an external source onto the map.

3. Drags from the left-hand photo pane onto the map.

In cases 2 & 3 where photos are dragged onto the map (regardless of the drag
source), the photos will be tagged with the precise map coordinates that they
were dragged to on the map. Otherwise the photos are simply loaded without
any modifications being made to the location tags.

Note that the code controlling dragging ChamplainLabels around within the map
is defined in label.py
"""

from __future__ import division

from gi.repository import Gtk, Gdk
from urlparse import urlparse
from urllib import unquote

from widgets import Widgets, MapView
from common import selected, modified
from photos import Photograph

class DragController():
    """Control the drag & drop behavior."""
    
    def __init__(self, open_files):
        # Drag source definitons
        photos_view = Widgets.photos_view
        photos_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK,
            [], Gdk.DragAction.COPY)
        photos_view.drag_source_add_text_targets()
        photos_view.connect('drag-data-get', self.photo_drag_start)
        
        # Drag destination defintions
        notebook = Widgets.photo_camera_gps
        notebook.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        notebook.drag_dest_add_text_targets()
        notebook.connect('drag-data-received', self.photo_drag_end, False)
        
        container = Widgets.map_container
        container.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        container.drag_dest_add_text_targets()
        container.connect('drag-data-received', self.photo_drag_end, True)
        
        self.external_drag = True
        self.selection = photos_view.get_selection()
        self.open_files = open_files
    
    def photo_drag_start(self, widget, drag_context, data, info, time):
        """Allow dragging more than one photo."""
        self.external_drag = False # Don't reload files from disk
        files = [ photo.filename for photo in selected ]
        data.set_text('\n'.join(files), -1)
    
    def photo_drag_end(self, widget, drag_context, x, y,
                       data, info, time, on_map):
        """Respond to drops and position photos accordingly.
        
        This method allows photos to be dropped in from the photo
        pane or any other drag source, such as the file browser.
        """
        if not data.get_text():
            return
        
        lat, lon = MapView.y_to_latitude(y), MapView.x_to_longitude(x)
        
        files = [unquote(urlparse(s).path.strip()) for s in
                 data.get_text().split('\n') if s]
        
        if self.external_drag:
            self.open_files(files)
        self.external_drag = True
        
        if on_map:
            for filename in files:
                photo = Photograph.instances.get(filename)
                if photo is not None:
                    photo.manual = True
                    photo.set_location(lat, lon)
        
        self.selection.emit('changed')

