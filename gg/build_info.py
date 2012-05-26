# Copyright (C) 2012 Robert Park <rbpark@exolucere.ca>

"""Determine the location of GottenGeography's data files.

Distutils has been customized to clobber this file at build time, so
that an installed copy of gottengeography is able to find it's data files.
It's important for the source tree to maintain this copy of this file in this
state so that the program can run uninstalled. Please be cautious not to
accidentally git commit the clobbered version of this file.
"""

from os import environ
from os.path import dirname, join
from subprocess import Popen, PIPE

# Make GSettings run without being installed into the system first.
environ['GSETTINGS_SCHEMA_DIR'] = 'data'
Popen(['glib-compile-schemas', 'data'])

# Figure out where we are and what version is running.
PREFIX = dirname(dirname(__file__))
PKG_DATA_DIR = join(PREFIX, 'data')
REVISION = Popen(
    ['git', 'rev-parse', 'HEAD'],
    stdout=PIPE
).communicate()[0].strip()

