Status
======

Version 2.0 is released, and it's targetted for Fedora 17, meaning that Fedora 17 ships with everything needed to run GottenGeography. Users of other distros who want to run it will need to make sure they have libchamplain 0.12.2 or later, pyexiv2 0.3 or later, pygobject3 3.0.3 or later, Gtk 3.0 or later, and Python 2.7.

Unfortunately Fedora 16 does not provide the necessary dependencies to run v2.0 and so users of Fedora 16 should be using v1.1.

GottenGeography
===============

GottenGeography is a geotagging application written for the GNOME desktop. It stores geographical information directly into your photos' EXIF data, so you never forget where your photos were taken.

It is currently able to:

* Display maps using [libchamplain](http://projects.gnome.org/libchamplain/) and [OpenStreetMap](http://www.openstreetmap.org/).

* Parse GPX, KML, TCX (xml) files and display the GPS tracks on the map, using [expat](http://docs.python.org/library/pyexpat.html). There is also support for CSV files.

* Read pre-existing geotags inside photo EXIF data using [pyexiv2](http://tilloy.net/dev/pyexiv2/) and display markers on the map indicating where those photos were taken.

* Manually geotag images, using either of two methods: by clicking the 'apply' button, the selected photos are placed onto the center of the map, or by drag & drop. Photos can be dragged in from the file browser, or dragged from the left pane onto the map, or dragged around the map once they're already on the map. Any way you do it, GottenGeography will record where the photos were dragged to and store that location into the photos.

* Automatically geotag images using timestamp comparison between photos and GPX data, proportionally calculating photo coordinates that fall in-between gpx track points. No clicking necessary! Simply load a GPX file along with your images, and they will automatically be placed along the track based on their timestamp.

* Reverse geocode using a db dump of [GeoNames.org](http://www.geonames.org/export/web-services.html) geolocation data. Stores city, province/state, and country names in IPTC data automatically.

* Automatically determine the timezone that your photos were taken in so that you don't have to specify it manually when you go travelling.

* Extensive use of [GSettings](https://live.gnome.org/GnomeGoals/GSettingsMigration) to store program state, meaning that each time you launch GottenGeography, it remembers things like where on the map you were last browsing, what map you were using, what size the window was, etc.

* Save EXIF/IPTC data into your photos using pyexiv2.

You may be interested in hacking on GottenGeography if you enjoy writing Python code, have some experience with the [GObject Introspection](http://live.gnome.org/GObjectIntrospection), or are a huge GPS nerd like myself.

GottenGeography is heavily inspired by the OSX application [PhotoLinker.app](http://www.earlyinnovations.com/photolinker/), however I am not affiliated in any way with EarlyInnovations. Please don't sue me, etc.

If you have any questions, feel free to [give me a shout](mailto:rbpark@exolucere.ca).

Testing
-------

I feel I have tested most aspects of this application fairly thoroughly. However, I only own two cameras, and only one GPS unit, so my test data is limited. You should backup your files before using GottenGeography. If you find that GottenGeography fails with your files, please send them to me and I'll do my best to get everything working. I have supplied some demo data with the program to show you how it is *supposed* to work ;-)

If you want to try out the included demo data and you're not in the Mountain Standard Time timezone, you'll have to choose "use the local timezone" on the Cameras tab, and that will give correct results regardless of what timezone your computer is set to.

Happy Tagging! --[Robert](mailto:rbpark@exolucere.ca)
