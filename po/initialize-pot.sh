#!/bin/bash

# This is just a quick little something I whipped up to help me regenerate
# the gottengeography.pot translation template when the strings in my program
# change. You can think of this as a macro that just fills in the basic details
# so that I don't have to copy & paste my name and email address every time
# the file changes. If you're translating GottenGeography, you shouldn't really
# have any need for this script, just follow the instructions in the README.md
# file. Thanks for stopping by!

cd ..

xgettext gg/*.{py,glade} --package-name gottengeography --package-version 0.5 \
                         --msgid-bugs-address="Robert Park <rbpark@exolucere.ca>" \
                         -o po/temp.pot

echo '# GottenGeography translation template.
# Copyright (C) 2010 Robert Park
# This file is distributed under the same license as the GottenGeography package.
# Robert Park <rbpark@exolucere.ca>, 2010' > po/gottengeography.pot

tail -n +5 po/temp.pot >> po/gottengeography.pot

rm po/temp.pot
