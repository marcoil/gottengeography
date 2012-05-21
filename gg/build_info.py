# Copyright (C) 2012 Robert Park <rbpark@exolucere.ca>

"""Determine the location of GottenGeography's data files.

Distutils has been customized to clobber this file at build time, so
that an installed copy of gottengeography is able to find it's data files.
It's important for the source tree to maintain this copy of this file in this
state so that the program can run uninstalled. Please be cautious not to
accidentally git commit the clobbered version of this file.
"""

from os.path import dirname, join
PKG_DATA_DIR = join(dirname(dirname(__file__)), 'data')

# Make GSettings run without being installed into the system first.
from os import system, environ
environ['GSETTINGS_SCHEMA_DIR'] = 'data'
system('glib-compile-schemas data')
