Status
======

With thanks to J5's workaround, GottenGeography is now no longer crippled by [bgo#643510](https://bugzilla.gnome.org/show_bug.cgi?id=643510), which means I'm considering the possibility of potentially forming a committee to explore the likelihood of making a 1.0 release. 

What's going on is that the code is currently written to use the as-yet-unreleased libchamplain 0.10, a decision which I'd made on the assumption that 0.10 would be done in time to be included in the next major Fedora release. With each passing day it seems increasingly likely that Fedora 15 will ship with libchamplain 0.8 instead of 0.10 (in fact it may already be too late for libchamplain 0.10's inclusion, I'm not quite clear on this point), which means that if I want to have any hope of my app being usable by any Fedora 15 users, I'll have to backport my app from 0.10 to 0.8 (libchamplain underwent a fairly extensive API overhaul between those versions, so it's actually a bit of work). Seeing as Fedora 15 was my primary release target, it seems like I have no choice here. Naturally I won't discard the work I did for the 0.10 API, so I guess I'll have to do some kind of simultaneous 0.8/0.10 launch... or write a bunch of glue code so that the app can use either API regardless of what's installed on the user's system... hmmmmmm...

GottenGeography
===============

GottenGeography is a geotagging application written for the GNOME desktop. It stores geographical information directly into your photos' EXIF data, so you never forget where your photos were taken.

It is currently able to:

* Display maps using [libchamplain](http://projects.gnome.org/libchamplain/) and [OpenStreetMap](http://www.openstreetmap.org/).

* Parse GPX (xml) files and display the GPS tracks on the map, using [expat](http://docs.python.org/library/pyexpat.html).

* Read pre-existing geotags inside photo EXIF data using [pyexiv2](http://tilloy.net/dev/pyexiv2/) and display markers on the map indicating where those photos were taken.

* Manually geotag images, using either of two methods: by clicking the 'apply' button, the selected photos are placed onto the center of the map, or by directly dragging map markers across the map, they will remember where you place them.

* Automatically geotag images using timestamp comparison between photos and GPX data, proportionally calculating photo coordinates that fall in-between gpx track points. No clicking necessary! Simply load a GPX file along with your images, and they will automatically be placed along the track based on their timestamp.

* Reverse geocode using a db dump of [GeoNames.org](http://www.geonames.org/export/web-services.html) geolocation data. Stores city, province/state, and country names in IPTC data automatically.

* Automatically determine the timezone that your photos were taken in so that you don't have to specify it manually when you go travelling.

* Remember the last viewed location in [GConf](http://projects.gnome.org/gconf/), and return to it the next time you run the program.

* Save EXIF/IPTC data into your photos using pyexiv2.

You may be interested in hacking on GottenGeography if you enjoy writing Python code, have some experience with the [GObject Introspection](http://live.gnome.org/GObjectIntrospection), or are a huge GPS nerd like myself. You are viewing the jhbuild branch of GottenGeography, which is developed in the [jhbuild development environment](http://library.gnome.org/devel/jhbuild/stable/). If you want to test this version, you'll need to install and configure jhbuild. Older versions are available for Fedora 14 and Ubuntu Maverick, but they are unmaintained and lacking in features.

GottenGeography is heavily inspired by the OSX application [PhotoLinker.app](http://www.earlyinnovations.com/photolinker/), however I am not affiliated in any way with EarlyInnovations. Please don't sue me, etc.

If you have any questions, feel free to [give me a shout](mailto:rbpark@exolucere.ca).

Testing
-------

I feel I have tested most aspects of this application fairly thoroughly. However, I only own two cameras, and only one GPS unit, so my test data is limited. You should backup your files before using GottenGeography. If you find that GottenGeography fails with your files, please send them to me and I'll do my best to get everything working. I have supplied some demo data with the program to show you how it is *supposed* to work ;-)

If you want to try out the included demo data and you're not in the Mountain Standard Time timezone, you'll have to turn on the auto-timezone lookup in the preferences (Timezone tab, click the second radio button), and that will give correct results regardless of what timezone your computer is set to.

Happy Tagging! --[Robert](mailto:rbpark@exolucere.ca)
