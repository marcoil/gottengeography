#!/usr/bin/env python

from os import makedirs, system
from os.path import join, basename, dirname, exists
from distutils.dep_util import newer
from distutils.core import setup
from glob import glob

from gg.version import *

data_files = [
    ('share/applications', ['data/gottengeography.desktop']),
    ('share/doc/%s' % PACKAGE, ['README.md', 'AUTHORS', 'COPYING'])
]

"""Compile all human-readable .po files into system-usable .mo files.
This uses msgfmt and is why you need intltool installed for a source install."""
for po in glob(join('po', '*.po')):
    lang = basename(po[:-3])
    mo = join('locale', lang, 'LC_MESSAGES', '%s.mo' % PACKAGE)
    
    directory = dirname(mo)
    if not exists(directory):
        print 'creating %s' % directory
        makedirs(directory)
    
    if newer(po, mo):
        # True if mo doesn't exist
        print 'compiling %s -> %s' % (po, mo)
        if system('msgfmt -o %s %s' % (mo, po)) != 0:
            raise SystemExit('Error while running msgfmt')

"""This second loop is slightly redundant, but it's necessary because setup.py
calls itself recursively a couple of different times from inside a FAKEROOT.
The .po files are only accessible to compile the very first time, but the .mo
files need to be included in `data_files` every time, otherwise they don't
make it into the final RPM."""
for locale in glob(join('locale', '*')):
    data_files.append(('share/%s/LC_MESSAGES' % locale,
        [join(locale, 'LC_MESSAGES', '%s.mo' % PACKAGE)]))

setup(
    name=APPNAME,
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
    package_data={'gg': ['ui.glade', 'cities.txt']},
    scripts=['gottengeography'],
    data_files=data_files
)
