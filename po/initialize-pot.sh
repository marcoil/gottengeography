#!/bin/bash

# This is just a quick little something I whipped up to help me regenerate
# the gottengeography.pot translation template when the strings in my program
# change. You can think of this as a macro that just fills in the basic details
# so that I don't have to copy & paste my name and email address every time
# the file changes. If you're translating GottenGeography, you shouldn't really
# have any need for this script, just follow the instructions in the README.md
# file. Thanks for stopping by!

DATES=$(echo $(seq 2010 $(date +%Y)))

. ../gg/version.py

intltool-update -r *.po -g $PACKAGE

mv $PACKAGE.pot temp.pot

cat <<EOF > $PACKAGE.pot
# $APPNAME translation template.
# Copyright (C) $DATES $AUTHOR
# This file is distributed under the same license as the $APPNAME package.
# $AUTHOR <$EMAIL>, $DATES
#
#, fuzzy
msgid ""
msgstr ""
"Project-Id-Version: $PACKAGE $VERSION\n"
"Report-Msgid-Bugs-To: $AUTHOR <$EMAIL>\n"
EOF

tail -n +11 temp.pot >> $PACKAGE.pot

rm temp.pot
