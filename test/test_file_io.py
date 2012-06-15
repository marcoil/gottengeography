
"""These tests cover loading and saving files."""

from gg.label import Label
from gg.widgets import Widgets
from gg.photos import Photograph
from gg.xmlfiles import TrackFile
from gg.common import points, selected, modified

from test import gui, teardown, setup, DEMOFILES

def test_demo_data():
    """Load the demo data and ensure that we're reading it in properly."""
    teardown()
    assert len(points) == 0
    assert len(TrackFile.instances) == 0
    assert len(TrackFile.range) == 0
    Widgets.photos_selection.emit('changed')
    # No buttons should be sensitive yet because nothing's loaded.
    buttons = {}
    for button in ('jump', 'save', 'revert', 'close'):
        buttons[button] = Widgets[button + '_button']
        assert not buttons[button].get_sensitive()
    
    # Load only the photos first.
    for filename in DEMOFILES:
        if filename.endswith('JPG'):
            try:
                gui.load_gpx_from_file(filename)
            except IOError:
                pass
            else:
                assert False # Because it should have raised the exception
    gui.open_files([uri for uri in DEMOFILES if uri.endswith('JPG')])
    
    # Nothing is yet selected or modified, so buttons still insensitive.
    for button in buttons.values():
        # TODO fix this test here.
        assert not button.get_sensitive()
    
    # Something loaded in the liststore?
    assert len(Widgets.loaded_photos) == 6
    assert Widgets.loaded_photos.get_iter_first()
    
    assert Photograph.instances
    for photo in Photograph.files:
        assert not photo in modified
        assert not photo in selected
        
        # Pristine demo data shouldn't have any tags.
        assert photo.altitude == 0.0
        assert photo.latitude == 0.0
        assert photo.longitude == 0.0
        assert not photo.positioned
        
        # Add some crap
        photo.latitude  = 10.0
        photo.altitude  = 650
        photo.longitude = 45.0
        assert photo.positioned
        
        # photo.read() should discard all the crap we added above.
        # This is in response to a bug where I was using pyexiv2 wrongly
        # and it would load data from disk without discarding old data.
        photo.read()
        photo.lookup_geodata()
        assert photo.geoname == ''
        assert photo.altitude == 0.0
        assert photo.latitude == 0.0
        assert photo.longitude == 0.0
        assert not photo.positioned
        assert photo.filename == Label(photo).get_name()
        assert Label(photo).photo.filename == Label(photo).get_name()
    
    # Load the GPX
    gpx = [filename for filename in DEMOFILES if filename.endswith('gpx')]
    try:
        gui.load_img_from_file(gpx[0])
    except IOError:
        pass
    else:
        assert False # Because it should have raised the exception
    gui.open_files(gpx)
    
    # Check that the GPX is loaded
    assert len(points) == 374
    assert len(TrackFile.instances) == 1
    assert TrackFile.range[0] == 1287259751
    assert TrackFile.range[1] == 1287260756
    
    for photo in Photograph.instances.values():
        photo.update_derived_properties()
    
    Widgets.photos_selection.emit('changed')
    
    # The save button should be sensitive because loading GPX modifies
    # photos, but nothing is selected so the others are insensitive.
    assert buttons['save'].get_sensitive()
    for button in ('jump', 'revert', 'close'):
        assert not buttons[button].get_sensitive()
    
    assert Photograph.instances
    for photo in Photograph.files:
        assert photo in modified
        
        assert photo.latitude
        assert photo.longitude
        assert photo.positioned
        assert Label(photo).get_property('visible')
    
    # Unload the GPX data.
    TrackFile.clear_all()
    assert len(points) == 0
    assert len(TrackFile.instances) == 0
    assert len(TrackFile.range) == 0
    
    # Save all photos
    buttons['save'].emit('clicked')
    assert len(modified) == 0
    for button in ('save', 'revert'):
        assert not buttons[button].get_sensitive()
    
    Widgets.photos_selection.select_all()
    assert len(selected) == 6
    for button in ('save', 'revert'):
        assert not buttons[button].get_sensitive()
    for button in ('jump', 'close'):
        assert buttons[button].get_sensitive()
    
    # Close all the photos.
    files = [photo.filename for photo in selected]
    buttons['close'].emit('clicked')
    for button in ('save', 'revert', 'close'):
        assert not buttons[button].get_sensitive()
    assert len(Photograph.instances) == 0
    assert len(modified) == 0
    assert len(selected) == 0
    
    # Re-read the photos back from disk to make sure that the saving
    # was successful.
    assert files
    for filename in files:
        photo = Photograph(filename)
        photo.read()
        photo.update_derived_properties()
        assert photo.positioned
        assert photo.altitude > 600
        assert photo.geoname == 'Edmonton, Alberta, Canada'

