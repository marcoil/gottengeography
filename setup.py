#!/usr/bin/env python

from os import makedirs, system
from os.path import join, basename, dirname, exists
from distutils.command.install_data import install_data
from distutils.dep_util import newer
from distutils.core import setup
from distutils.log import info
from glob import glob

from gg.version import *

class InstallData(install_data):
    """This class is copied from setup.py in Rapid Photo Downloader 0.3.4
    by Damon Lynch <damonlynch@gmail.com>.
    """
    def run (self):
        self.data_files.extend(self._compile_po_files())
        install_data.run(self)
    
    def _compile_po_files (self):
        data_files = []
        
        PO_DIR = 'po'
        for po in glob(join(PO_DIR, '*.po')):
            lang = basename(po[:-3])
            mo = join('build', 'mo', lang, '%s.mo' % PACKAGE)
            
            directory = dirname(mo)
            if not exists(directory):
                info('creating %s' % directory)
                makedirs(directory)
            
            if newer(po, mo):
                # True if mo doesn't exist
                cmd = 'msgfmt -o %s %s' % (mo, po)
                info('compiling %s -> %s' % (po, mo))
                if system(cmd) != 0:
                    raise SystemExit('Error while running msgfmt')
                
                dest = dirname(join('share', 'locale', lang, 'LC_MESSAGES', '%s.mo' % PACKAGE))
                data_files.append((dest, [mo]))
        
        return data_files

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
    data_files=[('share/applications', ['data/gottengeography.desktop']),
                ('share/doc/%s' % PACKAGE, ['README.md', 'AUTHORS', 'COPYING'])],
    cmdclass={'install_data': InstallData}
)
