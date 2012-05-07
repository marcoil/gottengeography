Status
======

1.1 is released, and it's targetted for Fedora 16, meaning that Fedora 16 ships with everything needed to run my program (if not in the default install, available through yum with a minimum of hassle). Users of other distros who want to run GottenGeography 1.0 will need to make sure they have libchamplain 0.9 or later, pyexiv2 0.3 or later, pygobject 2.28 or later, Gtk 3.0, and Python 2.7 (no other version of Python will work, it MUST be 2.7).

GottenGeography
===============

GottenGeography is a geotagging application written for the GNOME desktop. It stores geographical information directly into your photos' EXIF data, so you never forget where your photos were taken.

It is currently able to:

* Display maps using [libchamplain](http://projects.gnome.org/libchamplain/) and [OpenStreetMap](http://www.openstreetmap.org/).

* Parse GPX/KML (xml) files and display the GPS tracks on the map, using [expat](http://docs.python.org/library/pyexpat.html).

* Read pre-existing geotags inside photo EXIF data using [pyexiv2](http://tilloy.net/dev/pyexiv2/) and display markers on the map indicating where those photos were taken.

* Manually geotag images, using either of two methods: by clicking the 'apply' button, the selected photos are placed onto the center of the map, or by directly dragging map markers across the map, they will remember where you place them.

* Automatically geotag images using timestamp comparison between photos and GPX data, proportionally calculating photo coordinates that fall in-between gpx track points. No clicking necessary! Simply load a GPX file along with your images, and they will automatically be placed along the track based on their timestamp.

* Reverse geocode using a db dump of [GeoNames.org](http://www.geonames.org/export/web-services.html) geolocation data. Stores city, province/state, and country names in IPTC data automatically.

* Automatically determine the timezone that your photos were taken in so that you don't have to specify it manually when you go travelling.

* Remember the last viewed location in [GConf](http://projects.gnome.org/gconf/), and return to it the next time you run the program.

* Save EXIF/IPTC data into your photos using pyexiv2.

You may be interested in hacking on GottenGeography if you enjoy writing Python code, have some experience with the [GObject Introspection](http://live.gnome.org/GObjectIntrospection), or are a huge GPS nerd like myself.

GottenGeography is heavily inspired by the OSX application [PhotoLinker.app](http://www.earlyinnovations.com/photolinker/), however I am not affiliated in any way with EarlyInnovations. Please don't sue me, etc.

If you have any questions, feel free to [give me a shout](mailto:rbpark@exolucere.ca).

Testing
-------

I feel I have tested most aspects of this application fairly thoroughly. However, I only own two cameras, and only one GPS unit, so my test data is limited. You should backup your files before using GottenGeography. If you find that GottenGeography fails with your files, please send them to me and I'll do my best to get everything working. I have supplied some demo data with the program to show you how it is *supposed* to work ;-)

If you want to try out the included demo data and you're not in the Mountain Standard Time timezone, you'll have to turn on the auto-timezone lookup in the preferences (Timezone tab, click the second radio button), and that will give correct results regardless of what timezone your computer is set to.

Happy Tagging! --[Robert](mailto:rbpark@exolucere.ca)
