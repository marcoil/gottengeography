#!/usr/bin/env python

from distutils.core import setup

setup(
    name='GottenGeography',
    version='0.5',
    description="Automagically geotag photos with GPX data.",
    long_description=
"""GottenGeography is a GNOME application that aims to make it easy to record
geotags into your photographs. If you have a GPS device, GottenGeography can
load it's GPX data and directly compare timestamps between the GPX data and the
photos, automatically determining where each photo was taken. If you do not have
a GPS device, GottenGeography allows you to manually place photos onto a map,
and then record those locations into the photos.
""",
    author="Robert Park",
    author_email="rbpark@exolucere.ca",
    url="https://github.com/robru/GottenGeography/wiki",
    download_url="https://github.com/robru/GottenGeography/downloads",
    license="GPLv3",
    packages=['gg'],
    package_data={'gg': ['ui.glade', 'cities.txt']},
    scripts=['gottengeography'],
    data_files=[('share/applications', ['data/gottengeography.desktop'])],
)
