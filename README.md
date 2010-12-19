GottenGeography
===============

GottenGeography is a geotagging application written for the GNOME desktop. It stores geographical information directly into your photos' EXIF data, so you never forget where your photos were taken.

It is currently able to:

* Display maps using [libchamplain](http://projects.gnome.org/libchamplain/) and [OpenStreetMap](http://www.openstreetmap.org/).

* Parse GPX (xml) files and display the GPS tracks on the map, using [expat](http://docs.python.org/library/pyexpat.html).

* Read pre-existing geotags inside photo EXIF data using [pyexiv2](http://tilloy.net/dev/pyexiv2/) and display markers on the map indicating where those photos were taken.

* Manually geotag images (upon clicking the 'apply' button, the selected photos are placed onto the center of the map).

* Automatically geotag images using timestamp comparison between photos and GPX data, proportionally calculating photo coordinates that fall in-between gpx track points. No clicking necessary! Simply load a GPX file along with your images, and they will automatically be placed along the track based on their timestamp.

* Reverse geocode using [GeoNames.org JSON webservices](http://www.geonames.org/export/web-services.html). Stores city, province/state, and country names in IPTC data automatically.

* Remember the last viewed location in [GConf](http://projects.gnome.org/gconf/), and return to it the next time you run the program.

* Save EXIF/IPTC data into your photos using pyexiv2.

You may be interested in hacking on GottenGeography if you enjoy writing Python code, have some experience with the [GObject Introspection](http://live.gnome.org/GObjectIntrospection), or are a huge GPS nerd like myself. GottenGeography is currently developed for Fedora 14, and depends only upon packages available for that distribution (an older version is available for Ubuntu Maverick).

GottenGeography is heavily inspired by the OSX application [PhotoLinker.app](http://www.earlyinnovations.com/photolinker/), however I am not affiliated in any way with EarlyInnovations. Please don't sue me, etc.

If you have any questions, feel free to [give me a shout](mailto:rbpark@exolucere.ca).

Testing
-------

I feel I have tested most aspects of this application fairly thoroughly. However, I only own two cameras, and only one GPS unit, so my test data is limited. You should backup your files before using GottenGeography. If you find that GottenGeography fails with your files, please send them to me and I'll do my best to get everything working. I have supplied some demo data with the program to show you how it is *supposed* to work ;-)

GottenGeography depends upon your system timezone being set the same as your camera's timezone, so if you want to try out the included demo data and you're not in Mountain Standard Time (UTC-7), you'll have to invoke GottenGeography like this:

    TZ=MST ./gottengeography.py

Happy Tagging! --[Robert](mailto:rbpark@exolucere.ca)
