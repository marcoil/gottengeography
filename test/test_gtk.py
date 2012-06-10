
"""Basic sanity check on low-level Gtk things."""

from gg.widgets import Widgets, MapView

from test import Gst, gui

def test_gtk_builder():
    """GtkBuilder should be creating some widgets for us"""
    assert Widgets.loaded_photos.get_n_columns() == 4
    assert Widgets.search_results.get_n_columns() == 3
    size = Widgets.main.get_size()
    assert size[1] > 300
    assert size[0] > 400
    assert Widgets.photos_selection.count_selected_rows() == 0
    assert Widgets.error_message is Widgets['error_message']
    assert Widgets.photos_selection is \
        Widgets.get_object('photos_view').get_selection()

def test_gsettings():
    """GSettings should be storing data correctly"""
    Gst.reset('history')
    assert Gst.get('history')[0] == (34.5, 15.8, 2)
    
    MapView.set_zoom_level(2)
    MapView.center_on(12.3, 45.6)
    assert Gst.get_double('latitude') == 12.3
    assert Gst.get_double('longitude') == 45.6
    
    MapView.zoom_in()
    MapView.emit('realize')
    assert list(Gst.get('history')) == [(34.5, 15.8, 2), (12.3, 45.6, 3)]

