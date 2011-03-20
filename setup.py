#!/usr/bin/env python

from distutils.core import setup
from distutils.command.install_data import install_data
from distutils.dep_util import newer
from distutils.log import info
import glob
import os

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
        for po in glob.glob(os.path.join(PO_DIR, '*.po')):
            print po
            lang = os.path.basename(po[:-3])
            mo = os.path.join('build', 'mo', lang, '%s.mo' % PACKAGE)
            
            directory = os.path.dirname(mo)
            if not os.path.exists(directory):
                info('creating %s' % directory)
                os.makedirs(directory)
            
            if newer(po, mo):
                # True if mo doesn't exist
                cmd = 'msgfmt -o %s %s' % (mo, po)
                info('compiling %s -> %s' % (po, mo))
                if os.system(cmd) != 0:
                    raise SystemExit('Error while running msgfmt')
                
                dest = os.path.dirname(os.path.join('share', 'locale', lang, 'LC_MESSAGES', '%s.mo' % PACKAGE))
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
    download_url="https://github.com/robru/GottenGeography/downloads",
    license="GPLv3",
    packages=['gg'],
    package_data={'gg': ['ui.glade', 'cities.txt', 'AUTHORS', 'COPYING']},
    scripts=['gottengeography'],
    data_files=[('share/applications', ['data/gottengeography.desktop'])],
    cmdclass={'install_data': InstallData}
)
