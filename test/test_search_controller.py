
"""Test that we can search the map."""

from gg.widgets import Widgets, MapView

from test import gui

def test_search():
    """Make sure the search box functions"""
    entry = Widgets.search_box
    
    assert len(gui.search.results) == 0
    
    entry.set_text('jo')
    assert len(gui.search.results) == 0
    
    entry.set_text('edm')
    assert len(gui.search.results) == 23
    
    get_title = Widgets.main.get_title
    for result in gui.search.results:
        gui.search.search_completed(entry,
                                    gui.search.results,
                                    result.iter,
                                    MapView)
        loc, lat, lon = result
        assert lat == MapView.get_property('latitude')
        assert lon == MapView.get_property('longitude')
    
    entry.set_text('calg')
    assert len(gui.search.results) == 652
    
    entry.set_text('st.')
    assert len(gui.search.results) == 671

