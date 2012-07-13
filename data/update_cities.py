#!/usr/bin/python

# This takes the cities1000.txt file from geonames.org and extracts just the
# data we need for the cities.txt file. It's important to strip out the less
# useful data because the file is truly prodigous in size.

# Usage:
# ./update_cities.py cities1000.txt > cities.txt

from fileinput import input

for line in input():
    col = line.split('\t')
    print '\t'.join([col[1], col[4], col[5], col[8], col[10], col[17]])
