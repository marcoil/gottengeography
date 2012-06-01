#!/usr/bin/env python

from glob import glob
from os import listdir
from os.path import join
from distutils.core import setup
from subprocess import Popen, PIPE
from DistUtilsExtra.command import *
from distutils.command.build_py import build_py as _build_py

from gg.version import *

data_files = [
    ('share/icons/hicolor/scalable/apps', ['data/%s.svg' % PACKAGE]),
    ('share/glib-2.0/schemas', ['data/ca.exolucere.%s.gschema.xml' % PACKAGE]),
    ('share/applications', ['data/%s.desktop' % PACKAGE]),
    ('share/doc/' + PACKAGE, ['README.md', 'AUTHORS', 'COPYING']),
    ('share/' + PACKAGE, ['data/cities.txt', 'data/trackfile.ui', 'data/camera.ui',
        'data/%s.ui' % PACKAGE, 'data/%s.svg' % PACKAGE])
]

for helplang in listdir('help'):
    data_files.append(('share/gnome/help/%s/%s' % (PACKAGE, helplang),
                      glob(join('help', helplang, '*'))))

build_info_template = """# -*- coding: UTF-8 -*-

# Distutils installation details:
PREFIX='%s'
PKG_DATA_DIR='%s'
REVISION='%s'
"""

class build_py(_build_py): 
    """Clobber gg/build_info.py with the real package data dir.
    
    Inspired by a distutils-sig posting by Wolodja Wentland in Sept 2009.
    """
    def build_module (self, module, module_file, package):
        if ('%s/%s' % (package, module) == 'gg/build_info'):
            try:
                iobj = self.distribution.command_obj['install']
                with open(module_file, 'w') as module_fp:
                    module_fp.write(build_info_template % (
                        iobj.prefix,
                        join(iobj.prefix, 'share', PACKAGE),
                        Popen(['git', 'describe'],
                            stdout=PIPE).communicate()[0].strip()
                    ))
            except KeyError:
                pass
        
        _build_py.build_module(self, module, module_file, package)

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
                 "build_i18n" :  build_i18n.build_i18n,
                 "build_py": build_py }
)

