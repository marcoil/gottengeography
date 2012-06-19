# Author: Robert Park <rbpark@exolucere.ca>, (C) 2010
# Copyright: See COPYING file included with this distribution.

"""Control the behavior of ChamplainLabels."""

from __future__ import division

from gi.repository import GObject, Champlain, Clutter
from os.path import basename

from widgets import Widgets, MapView
from common import selected, modified
from common import bind_properties, memoize

layer = Champlain.MarkerLayer()
MapView.add_layer(layer)


def update_highlights(*ignore):
    """Ensure only the selected labels are highlighted."""
    selection_exists = Widgets.photos_selection.count_selected_rows() > 0
    selected.clear()
    for label in layer.get_markers():
        # Maintain the 'selected' set() for easier iterating later.
        if label.photo.iter and Widgets.photos_selection.iter_is_selected(
                                label.photo.iter):
            selected.add(label.photo)
        label.set_highlight(label.photo in selected, selection_exists)

def selection_sensitivity(selection, close, save, revert, jump, aply):
    """Control the sensitivity of various widgets."""
    sensitive = selection.count_selected_rows() > 0
    close.set_sensitive(sensitive)
    jump.set_sensitive([photo for photo in selected if photo.positioned])
    save.set_sensitive(len(modified) > 0)
    revert.set_sensitive(len(modified & selected) > 0)
    aply.set_sensitive(len(selected) > 0)

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
    instances = {}
    
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
        
        self.bindings = {}
        for prop in ('latitude', 'longitude'):
            self.bindings[prop] = bind_properties(
                photo, prop, self,
                flags=GObject.BindingFlags.BIDIRECTIONAL)
        self.bindings['visible'] = bind_properties(
            photo, 'positioned', self, 'visible')
        
        layer.add_marker(self)
    
    def set_highlight(self, highlight, transparent):
        """Set the highlightedness of the given ChamplainLabel."""
        if self.get_property('visible'):
            self.set_scale(*[1.1 if highlight else 1] * 2)
            self.set_selected(highlight)
            self.set_opacity(64 if transparent and not highlight else 255)
            if highlight:
                self.raise_top()
    
    def destroy(self):
        """Remove from map and unload."""
        del Label.instances[self.photo]
        self.unmap()
        Champlain.Label.destroy(self)


Widgets.photos_selection.connect('changed', update_highlights)
Widgets.photos_selection.connect('changed', selection_sensitivity,
    *[Widgets[b + '_button'] for b in
        ('close', 'save', 'revert', 'jump', 'apply')])

