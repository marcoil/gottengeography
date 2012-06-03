#!/bin/bash

# pylint doesn't actually play very well with Gtk, so
# let's disable some false positives:
IGNORE=E0611,E1101

pylint -d $IGNORE --include-ids=y gg

pylint -d $IGNORE --include-ids=y test
