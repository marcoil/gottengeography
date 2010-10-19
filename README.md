GottenGeography
===============

GottenGeography is a program to allow you to geotag your photos, that is, store latitude and longitude coordinates directly into the EXIF data of your images, so you never forget where your photos were taken.

Note that GottenGeography is currently in a highly alpha pre-release state: it is not currently capable of saving any data (there is a save button, but it's just a placeholder at the moment).

However, in it's current state it's able to:

* display maps using [libchamplain](http://projects.gnome.org/libchamplain/)

* parse GPX (xml) files and display the GPS tracks on the libchamplain map, using [minidom](http://docs.python.org/library/xml.dom.minidom.html)

* read pre-existing geotags inside photo EXIF data using [pyexiv2](http://tilloy.net/dev/pyexiv2/) and display markers on the libchamplain map indicating where those photos were taken

* manually geotag images (upon clicking the 'apply' button, the selected photos are placed onto the center of the map)

* automatically geotag images using timestamp comparison between photos and GPX data, including proportionally calculating photo coordinates that fall in-between gpx tracks. No clicking necessary! Simply load a GPX file along with your images, and they will automatically be placed along the track based on their timestamp.

* remember the last viewed location (using [GConf](http://projects.gnome.org/gconf/)) and return to it the next time you run the program
    
You may be interested in hacking on GottenGeography if you enjoy writing Python code, have some experience with the poorly-documented [GObject Introspection](http://live.gnome.org/GObjectIntrospection) black magic, or are a huge GPS nerd like myself. GottenGeography is developed for Ubuntu Maverick, and depends only upon packages available for that distribution. I'm aware that the versions of pyexiv2 and libchamplain I'm using are quite old, but one of the primary goals of this application is to be easy to use, so I have chosen to avoid having my users chase down and compile obscure dependencies. Everything can be installed directly from inside Synaptic. 

GottenGeography is heavily inspired by the OSX application [PhotoLinker.app](http://www.earlyinnovations.com/photolinker/), however I am not affiliated in any way with EarlyInnovations. Please don't sue me, etc. 

If you have any questions, feel free to [give me a shout](mailto:rbpark@exolucere.ca). This little project is my baby, and I'm eager to see it to completion.

Testing
-------

I feel I have tested this application fairly thoroughly. However, I only own two cameras, and only one GPS unit, so my test data is somewhat limited. If you find that GottenGeography fails with your files, please send them to me and I'll do my best to get everything working. I have supplied some demo data with the program to show you how it is *supposed* to work ;-)

Happy Tagging!
    --Robert
