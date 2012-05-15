#!/usr/bin/env python

from distutils.core import setup
from DistUtilsExtra.command import *

from gg.version import *

data_files = [
    ('share/' + PACKAGE, ['data/cities.txt', 'data/%s.ui' % PACKAGE]),
    ('share/applications', ['data/%s.desktop' % PACKAGE]),
    ('share/glib-2.0/schemas', ['data/ca.exolucere.%s.gschema.xml' % PACKAGE]),
    ('share/doc/' + PACKAGE, ['README.md', 'AUTHORS', 'COPYING'])
]

setup(
    name=PACKAGE,
    version=VERSION,
    description="Automagically geotag photos with GPX data.",
    long_description=
"""GottenGeography is a GNOME application that aims to make it easy to record
geotags into your photographs. If you have a GPS device, GottenGeography can
load it's GPX data and directly compare timestamps between the GPX data and the
photos, automatically determining where each photo was taken. If you do not have
a GPS device, GottenGeography allows you to manually place photos onto a map,
and then record those locations into the photos.
""",
    author=AUTHOR,
    author_email=EMAIL,
    url="http://exolucere.ca/gottengeography",
    download_url="https://github.com/robru/GottenGeography/tags",
    license="GPLv3",
    packages=['gg'],
    scripts=['gottengeography'],
    data_files=data_files,
    cmdclass = { "build" : build_extra.build_extra,
                 "build_i18n" :  build_i18n.build_i18n }
)
