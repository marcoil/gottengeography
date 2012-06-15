#!/bin/bash

if [ $1 ]; then
    CHECK=$1
else
    CHECK=gg
fi

# pylint doesn't actually play very well with Gtk, so
# let's disable some false positives:
pylint -d E0611,E1101,W0613,W0403,W0142,W0141,W0102,R0903 --include-ids=y $CHECK
