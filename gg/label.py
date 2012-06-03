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

"""Control the behavior of ChamplainLabels."""

from __future__ import division

from gi.repository import Gtk, Champlain, Clutter
from os.path import basename

from common import get_obj, map_view, selected, modified, photos

layer = Champlain.MarkerLayer()
selection = get_obj('photos_view').get_selection()
selection.set_mode(Gtk.SelectionMode.MULTIPLE)
map_view.add_layer(layer)


def update_highlights(selection):
    """Ensure only the selected labels are highlighted."""
    selection_exists = selection.count_selected_rows() > 0
    selected.clear()
    for photo in photos.values():
        # Maintain the 'selected' set() for easier iterating later.
        if selection.iter_is_selected(photo.iter):
            selected.add(photo)
        photo.set_label_highlight(photo in selected, selection_exists)

def selection_sensitivity(selection, close, save, revert, jump):
    """Control the sensitivity of various widgets."""
    sensitive = selection.count_selected_rows() > 0
    close.set_sensitive(sensitive)
    jump.set_sensitive(sensitive)
    save.set_sensitive(len(modified) > 0)
    revert.set_sensitive(len(modified & selected) > 0)

def clicked(label, event):
    """When a ChamplainLabel is clicked, select it in the GtkListStore.
    
    The interface defined by this method is consistent with the behavior of
    the GtkListStore itself in the sense that a normal click will select
    just one item, but Ctrl+clicking allows you to select multiple.
    """
    photo = photos[label.get_name()]
    assert photo.filename == label.get_name()
    if event.get_state() & Clutter.ModifierType.CONTROL_MASK:
        if label.get_selected(): selection.unselect_iter(photo.iter)
        else:                    selection.select_iter(photo.iter)
    else:
        selection.unselect_all()
        selection.select_iter(photo.iter)

def drag_finish(label, event):
    """Update photos with new locations after photos have been dragged."""
    photo = photos[label.get_name()]
    photo.set_location(label.get_latitude(), label.get_longitude())
    photo.manual = True
    selection.emit('changed')
    map_view.emit('animation-completed')

def hover(label, event, factor):
    """Scale a ChamplainLabel by the given factor."""
    label.set_scale(*[scale * factor for scale in label.get_scale()])

class Label(Champlain.Label):
    def __init__(self, name):
        """Create a new ChamplainLabel and add it to the map."""
        Champlain.Label.__init__(self)
        self.set_name(name)
        self.set_text(basename(name))
        self.set_selectable(True)
        self.set_draggable(True)
        self.set_property('reactive', True)
        self.hide()
        self.connect('enter-event', hover, 1.05)
        self.connect('leave-event', hover, 1/1.05)
        self.connect('drag-finish', drag_finish)
        self.connect('button-press', clicked)
        layer.add_marker(self)


selection.connect('changed', update_highlights)
selection.connect('changed', selection_sensitivity,
    *[get_obj(name) for name in ('close_button',
        'save_button', 'revert_button', 'jump_button')])

