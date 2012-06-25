# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Control the behavior of ChamplainLabels."""

from __future__ import division

from gi.repository import GtkClutter
GtkClutter.init([])

from gi.repository import GObject, Champlain, Clutter
from os.path import basename

from common import Binding, memoize, modified
from widgets import Widgets, MarkerLayer


def clicked(label, event):
    """When a ChamplainLabel is clicked, select it in the GtkListStore.
    
    The interface defined by this method is consistent with the behavior of
    the GtkListStore itself in the sense that a normal click will select
    just one item, but Ctrl+clicking allows you to select multiple.
    """
    photo = label.photo
    assert photo.filename == label.get_name()
    if event.get_state() & Clutter.ModifierType.CONTROL_MASK:
        if label.get_selected():
            Widgets.photos_selection.unselect_iter(photo.iter)
        else:
            Widgets.photos_selection.select_iter(photo.iter)
    else:
        Widgets.photos_selection.unselect_all()
        Widgets.photos_selection.select_iter(photo.iter)


def hover(label, event, factor):
    """Scale a ChamplainLabel by the given factor."""
    label.set_scale(*[scale * factor for scale in label.get_scale()])


@memoize
class Label(Champlain.Label):
    """Extend Champlain.Label to add itself to the map."""
    
    def __init__(self, photo):
        Champlain.Label.__init__(self)
        self.photo = photo
        self.set_name(photo.filename)
        self.set_text(basename(photo.filename))
        self.set_selectable(True)
        self.set_draggable(True)
        self.set_property('reactive', True)
        self.connect('enter-event', hover, 1.05)
        self.connect('leave-event', hover, 1/1.05)
        self.connect('button-press', clicked)
        self.connect('drag-finish',
            lambda *ignore: modified.add(photo)
                and photo.disable_auto_position())
        
        if photo.positioned:
            self.set_location(photo.latitude, photo.longitude)
            self.show()
        else:
            self.hide()
        
        for prop in ('latitude', 'longitude'):
            Binding(photo, prop, self,
                            flags=GObject.BindingFlags.BIDIRECTIONAL)
        Binding(photo, 'positioned', self, 'visible')
        
        MarkerLayer.add_marker(self)
    
    def set_highlight(self, highlight, transparent):
        """Set the highlightedness of the given ChamplainLabel."""
        if self.get_property('visible'):
            scale = 1.1 if highlight else 1
            self.set_scale(scale, scale)
            self.set_selected(highlight)
            self.set_opacity(64 if transparent and not highlight else 255)
            if highlight:
                self.raise_top()
    
    def destroy(self):
        """Remove from map and unload."""
        del Label.cache[self.photo]
        self.unmap()
        Champlain.Label.destroy(self)

