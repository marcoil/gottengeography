#!/usr/bin/python

"""This script parses geonames.org db dumps into the territories.py file.

You'll need to download countryInfo.txt, admin1CodesASCII.txt, and
timeZones.txt from http://download.geonames.org/export/dump/
"""

print """# coding=UTF-8

\"\"\"Define an exhaustive list of countries and administrative regions.

This data was provided by geonames.org and is licensed
under the Creative Commons Attribution 3.0 License,
see http://creativecommons.org/licenses/by/3.0/

The data is provided "as is" without warranty or any
representation of accuracy, timeliness or completeness.

The data was then converted from tab-delimited UTF8 into
python source code by Robert Park <rbpark@exolucere.ca>
\"\"\"

from os import listdir
from os.path import sep, join, isdir
"""

print 'countries = {'
with open('countryInfo.txt') as countries:
    for line in countries:
        if line[0] == '#':
            continue
        code, x, y, z, name = line.split('\t')[:5]
        print '"%s": "%s",' % (code, name)
print '}'

print
print 'territories = {'
with open('admin1CodesASCII.txt') as states:
    for line in states:
        code, name = line.split('\t')[:2]
        print '"%s": "%s",' % (code, name)
print '}'

print """
zoneinfo = join(sep, 'usr', 'share', 'zoneinfo')
zones = {}
for region in listdir(zoneinfo):
    region_path = join(zoneinfo, region)
    if not isdir(region_path) or region in ('posix', 'Etc', 'right'):
        continue
    zones[region] = sorted(listdir(region_path))

tz_regions   = sorted(zones.keys())
get_timezone = zones.get
get_country  = countries.get

def get_state(country, state):
    \"\"\"Returns the name of a province/state given a Geonames.org admin1code.\"\"\"
    return territories.get("%s.%s" % (country, state))
"""
