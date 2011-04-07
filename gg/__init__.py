# GottenGeography - Print friendlier errors when dependencies are not met.
# Copyright (C) 2010 Robert Park <rbpark@exolucere.ca>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from sys import exit

def need(dependency):
    """Exit the program and tell the user what dependency was missing."""
    exit('GottenGeography requires at least ' + dependency)

try:
    from fractions import Fraction
    # Raises TypeError with Python 2.6, so 2.7 is required.
    Fraction(0.5).numerator
except:
    need('Python 2.7')

try:
    import gi
    # Raises AttributeError with pygobject 2.21.
    gi.require_version('Gtk', '3.0')
except:
    need('Gtk 3.0 (via pygobject 2.28)')

try:
    from gi.repository import Champlain
    # Raises AttributeError with libchamplain 0.8 or earlier.
    Champlain.PathLayer
except:
    need('libchamplain 0.9')

try:
    import pyexiv2
    if pyexiv2.version_info < (0, 3):
        raise ImportError
except:
    need('pyexiv2 0.3')
