#!/usr/bin/env python
# coding=utf-8

# GottenGeography - Automatically geotags photos based on timestamps in GPX data
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

import pygtk, gtk, gobject, os, re, time, calendar, xml, pprint
from xml.dom import minidom

pygtk.require('2.0')

# "If I have seen a little further it is by standing on the shoulders of Giants."
#                                    --- Isaac Newton

# TODO:
# Needs libchamplain
# Needs to be able to sync GPX with image timestamps
# Needs manual tagging of GPS coords based on user map entry alone, no GPX data
# Needs to be able to save EXIF data
# Needs photo thumbnails
# Needs to be able to load files via drag&drop

class GottenGeography:
	# Shorthand for a little bit of GTK magic to make my code read more smoothly. (this gets called a lot)
	def redraw_interface(self):
		while gtk.events_pending(): gtk.main_iteration()
		
	# Take a GtkTreeIter, check if it is unsaved, and if so, increment the 
	# modified file count (used exclusively in the following method)
	def increment_modified(self, model, path, iter):
		if model.get(iter, self.PHOTO_MODIFIED)[0]:
			self.mod_count += 1
	
	# If given a GtkTreeSelection, will return true if there are any unsaved files in 
	# the selection. Otherwise, will return true if there are any unsaved files at all.
	# Also sets the value of self.mod_count
	def any_modified(self, selection=None):
		self.mod_count = 0
		if selection:
			selection.selected_foreach(self.increment_modified)
		else:
			self.liststore.foreach(self.increment_modified)
		return self.mod_count > 0
	
	# Creates the Pango-formatted display string used in the GtkTreeView
	def create_summary(self, iter, modified=False):
		if self.liststore.get(iter, self.PHOTO_COORDINATES)[0]:
			summary = ", ".join(self.liststore.get(iter, self.PHOTO_LATITUDE, self.PHOTO_LONGITUDE))
		else:
			summary = "Not geotagged"

		# This says "filename on the first line, then date in a smaller font on the second line, 
		# and GPS coords in a smaller font on the third line"
		# TODO I don't think I actually want the date displayed here at all, this was just added
		# for debugging, so I could ensure the date was being loaded properly
		summary = '%s\n<small><span color="#777777">%s\n%s</span></small>' % (
			os.path.basename(self.liststore.get(iter, self.PHOTO_PATH)[0]), 
			time.ctime(self.liststore.get(iter, self.PHOTO_TIMESTAMP)[0]),
			summary 
		)
		
		# Embolden text if this image has unsaved data
		if modified: summary = '<b>%s</b>' % summary
		return summary
	
	# This just might be the single most important method ever written. In the history of computing.
	# TODO needs logo
	def about_dialog(self, widget, data=None):
		dialog = gtk.AboutDialog()
		dialog.set_name("GottenGeography")
		dialog.set_version("0.0.1")
		dialog.set_copyright(u"\u00A9 Robert Park, 2010")
		dialog.set_license(LICENSE)
		dialog.set_comments("This program is written in the Python programming language, and allows you to geotag your photos. The name \"Gotten Geography\" is an anagram of \"Python Geotagger\".")
		dialog.set_website("http://exolucere.ca")
		dialog.set_website_label("exolucere.ca")
		dialog.set_authors(["Robert Park <rbpark@exolucere.ca>"])
		dialog.set_documenters(["Robert Park <rbpark@exolucere.ca>"])
		dialog.set_artists(["Robert Park <rbpark@exolucere.ca>"])
		#dialog.set_translator_credits("Nobody!")
		dialog.run()
		dialog.destroy()
	
	def about_dialog_old(self, widget, data=None):
		dialog = gtk.MessageDialog(parent=self.window, 
		                           flags=gtk.DIALOG_MODAL,
		                           type=gtk.MESSAGE_INFO, 
		                           buttons=gtk.BUTTONS_NONE)
		dialog.set_title("About GottenGeography")
		
		dialog.set_markup(u"<span size=\"larger\"><span weight=\"bold\" size=\"larger\">GottenGeography v0.0.1 Alpha</span>\n\n\u00A9 2010 Robert Park</span>\nrbpark@exolucere.ca")
		dialog.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
		dialog.set_default_response(gtk.RESPONSE_CLOSE)
		
		dialog.run()
		dialog.destroy()
	
	# This is called when the user clicks "x" button in windowmanager
	# As far as I'm aware, this method is 100% GNOME HIG compliant.
	# http://library.gnome.org/devel/hig-book/stable/windows-alert.html.en#save-confirmation-alerts
	def delete_event(self, widget, event, data=None):
		# If there's no unsaved data, just close without confirmation.
		if not self.any_modified():
			return False
		
		dialog = gtk.MessageDialog(parent=self.window, 
		                           flags=gtk.DIALOG_MODAL,
		                           type=gtk.MESSAGE_WARNING, 
		                           buttons=gtk.BUTTONS_NONE,
		                           message_format="Save changes to your photos before closing?")
		dialog.set_title(" ")
		
		# self.mod_count is accurate due to self.any_modified() being called above
		dialog.format_secondary_text("The changes you've made to %d of your photos will be permanently lost if you do not save." % self.mod_count)
		dialog.add_button("Close _without Saving", gtk.RESPONSE_CLOSE)
		dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
		dialog.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
		dialog.set_default_response(gtk.RESPONSE_ACCEPT)
		
		# We need to destroy the dialog immediately so that the interface feels responsive,
		# even if it takes some time to save the files and then close.
		response = dialog.run()
		dialog.destroy()
		self.redraw_interface()
		
		# Close without saving
		if response == gtk.RESPONSE_CLOSE:
			return False
		
		# Save and then close
		elif response == gtk.RESPONSE_ACCEPT:
			self.save_files()
			return False
		
		# Do not close
		else:
			return True
	
	# This function gets called automagically if the previous one returns False
	def destroy(self, widget, data=None):
		gtk.main_quit()

	# This method gets called whenever the GtkTreeView selection changes, and it sets the sensitivity of
	# a few buttons such that buttons which don't do anything useful in that context are desensitized.
	def selection_changed(self, selection, data=None):
		sensitivity = selection.count_selected_rows() > 0
		
		# Apply and Delete buttons get activated if there is any selection at all
		self.apply_button.set_sensitive(sensitivity)
		self.delete_button.set_sensitive(sensitivity)
		
		# The Revert button is only activated if the selection contains unsaved files.
		self.revert_button.set_sensitive(self.any_modified(selection))
		
	# This function creates a nested dictionary (that is, a dictionary of dictionaries)
	# in which the top level keys are epoch seconds, and the bottom level keys are elevation/latitude/longitude.
	# TODO you'll probably want to offer the user some way to unload/clear this data without restarting the program
	def parse_track(self, track, filename):
		# I find GPS-generated names to be ugly, so I only show them in the progress meter,
		# they're not stored anywhere or used after that
		self.progressbar.set_text("Loading %s from %s..." % (
			track.getElementsByTagName('name')[0].firstChild.data, 
			os.path.basename(filename))
		)
		
		# In the event that the user loads a file (or multiple files) containing more than one track point
		# for a given epoch second, the most-recently-loaded is kept, and the rest are clobbered. 
		# Effectively this makes the assumption that the user cannot be in two places at once, although
		# it is possible that the user might attempt to load two different GPX files from two different
		# GPS units. If you do that, you're stupid, and I hate you.
		for segment in track.getElementsByTagName('trkseg'):
			points = segment.getElementsByTagName('trkpt')
			
			count = 0.0
			total = float(len(points))
			
			for point in points:
				self.progressbar.set_fraction(count/total)
				count += 1.0
				self.redraw_interface()
				
				# Convert GPX time (RFC 3339 time) into UTC epoch time for simplicity in sorting and comparing
				timestamp = point.getElementsByTagName('time')[0].firstChild.data
				timestamp = time.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
				timestamp = calendar.timegm(timestamp)
				
				self.tracks[timestamp]={
					'latitude': float(point.getAttribute('lat')),
					'longitude': float(point.getAttribute('lon')),
					'elevation': float(point.getElementsByTagName('ele')[0].firstChild.data)
				}
	
	# Displays nice GNOME file chooser dialog and allows user to select either images or GPX files.
	# TODO Need to be able to load files with drag & drop, not just this thing
	# TODO file previews would be nice
	# TODO Sort liststore by timestamp after load is successful.
	def add_file(self, widget, data=None):
		chooser = gtk.FileChooserDialog(
			title="Open files...",
			action=gtk.FILE_CHOOSER_ACTION_OPEN,
			buttons=(
				gtk.STOCK_CANCEL,  gtk.RESPONSE_CANCEL, 
				gtk.STOCK_OPEN,    gtk.RESPONSE_OK
			)
		)
		chooser.set_default_response(gtk.RESPONSE_OK)
		chooser.set_select_multiple(True)
		
		
		# By default, we only want to show a combination of images and GPX data files
		# It makes sense to mix these into one view because
		#    a) the user is unlikely to have these mixed into the same directory, and
		#    b) it's a needless hassle to make the user switch between one or the other when trying to open files
		# TODO don't limit this to just DNG and JPG
		filter = gtk.FileFilter()
		filter.set_name("Images & GPX")
		filter.add_mime_type('image/jpeg')
		filter.add_pattern('*.jpg')
		filter.add_pattern('*.jpeg')
		filter.add_pattern('*.dng')
		filter.add_pattern('*.gpx')
		chooser.add_filter(filter)
		
		# In the event that the user has an image that isn't presented in the above filter, I'll allow them to display all files
		# Can't promise I'll be able to open just anything, though.
		filter = gtk.FileFilter()
		filter.set_name("All Files")
		filter.add_pattern('*')
		chooser.add_filter(filter)
		
		# Exit if the user clicked anything other than "OK"
		if not (chooser.run() == gtk.RESPONSE_OK):
			chooser.destroy()
			return
		
		# Show the progress meter, because loading files is slow!
		self.progressbar.show()
		
		# We need to make the chooser disappear immediately after clicking a button,
		# Anything else is really slow and feels unresponsive
		files = chooser.get_filenames()
		chooser.destroy()
		self.progressbar.set_text("Loading files (please be patient)...")
		self.redraw_interface()
		
		# Iterate over files and attempt to load them.
		for filename in files:
			# TODO Currently, this code assumes the file is GPX XML, and then if the xml parser fails, 
			# it assumes it's photo data. Once pyexiv2 starts working, we'll want to assume
			# that the files are photos (since that will be the most likely thing), and if
			# pyexiv2 fails to read the files, THEN assume that they're GPX after.
			try:
				self.progressbar.set_fraction(0)
				self.progressbar.set_text("Parsing GPS data (please be patient)...")
				# self.window.get_window().set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH)) # not working in X11.app, hopefully this works on Linux
				self.redraw_interface()
				
				# TODO what happens to this if I load an XML file that isn't GPX?
				# TODO any way to make this faster?
				# TODO any way to pulse the progress bar while this runs?
				gpx = minidom.parse(filename)
				
				self.progressbar.set_text("Normalizing GPS data...") # Reticulating splines...
				self.redraw_interface()
				gpx.normalize()
				
				# self.parse_track will take over the statusbar while it works
				for node in gpx.documentElement.getElementsByTagName('trk'): self.parse_track(node, filename)
				
			# File sure wasn't XML! Let's try to load it as an image instead
			except xml.parsers.expat.ExpatError:
				self.treeview.show() 
				
				# File wasn't XML, so try loading it with pyexiv2 here instead
				# (I think the most common use case will be the user loading MANY images and only few
				# GPX files, so make pyexiv2 the outermost case, and then load the GPX from within the exception there.
				
				# TODO placeholder strings here should be replaced with data from pyexiv2 once that works
				# This is somewhat clumsy, but it's column-order-agnostic, so if I feel like changing the 
				# arrangement of columns later, I don't have to change this or worry about it at all here.
				iter = self.liststore.append()
				
				# TODO replace with real thumbnail from pyexiv2
				# Should pyexiv2 fail to produce a thumbnail, don't be afraid to leave this blank,
				# because the TreeView will use the stock image missing icon in it's place and that'll work out peachy.
				thumb = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, 100, 75)
				thumb.fill(0xAAAAAAFF)
				
				self.liststore.set(iter,
					self.PHOTO_THUMB,		thumb,
					self.PHOTO_PATH,		filename,
					self.PHOTO_TIMESTAMP,		int(os.stat(filename).st_mtime), # Get this from pyexiv2 instead
					self.PHOTO_COORDINATES,		False,
					self.PHOTO_LATITUDE,		'latitude',
					self.PHOTO_LONGITUDE,		'longitude',
					self.PHOTO_MODIFIED,		False
				)
				
				# This has to be called separately because self.create_summary relies on 
				# the previous data already being present
				self.liststore.set(iter, self.PHOTO_SUMMARY, self.create_summary(iter))
		self.progressbar.hide()
		pp = pprint.PrettyPrinter(indent=4)
		pp.pprint(self.tracks)
	
	# Saves all modified files
	def save_files(self, widget=None, data=None):
		if not self.any_modified():
			return
		
		self.progressbar.show()
		
		# Data needed to start iterating over the images
		count = 0.0
		iter = self.liststore.get_iter_first()
		
		while iter:
			if self.liststore.get(iter, self.PHOTO_MODIFIED)[0]:
				time.sleep(0.1) # Simulates the delay of actually saving a file, which we don't actually do yet
				# TODO Actually write data to file here
				self.liststore.set_value(iter, self.PHOTO_MODIFIED, False)
				self.liststore.set_value(iter, self.PHOTO_SUMMARY, re.sub(r'</?b>', '', self.liststore.get(iter, self.PHOTO_SUMMARY)[0])) # Remove bolding of text
				self.progressbar.set_fraction(count/self.mod_count)
				self.progressbar.set_text("Saving %s..." % os.path.basename(self.liststore.get(iter, self.PHOTO_PATH)[0]))
				self.redraw_interface()
				count += 1.0
			iter = self.liststore.iter_next(iter)

		# Update sensitivity of save/revert buttons based on current state, and hide the progressbar.
		self.revert_button.set_sensitive(self.any_modified(self.treeselection))
		self.save_button.set_sensitive(self.any_modified())
		self.progressbar.hide()
	
	# This method handles all three of apply, revert, and delete. Those three actions are
	# much more alike than you might intuitively suspect. They all iterate over the GtkTreeSelection,
	# They all modify the GtkListStore data... having this as three separate methods felt very redundant,
	# so I merged it all into here. I hope this isn't TOO cluttered.
	def apply_changes(self, widget, apply=True, delete=False):
		(model, pathlist) = self.treeselection.get_selected_rows()
		
		# Sorted from highest to lowest prevents delete from breaking
		# (deleting a row reduces the path # for all higher rows)
		for path in sorted(pathlist, key=lambda a: a[0], reverse=True):
			iter = model.get_iter(path)
			if delete:
				model.remove(iter)
				continue # Skip the rest of this loop because shit just got deleted
			#if not apply:
				# TODO Reload the data from the original file here
				# Make sure to set PHOTO_COORDINATES based on whether or not there are any, not "False because we're reverting"
			#else:
				# TODO save GPS data from libchamplain into PHOTO_LATITUDE and PHOTO_LONGITUDE
			model.set_value(iter, self.PHOTO_COORDINATES, apply) # TODO this is incorrect in the case that we're reverting a photo that had GPS data from before
			model.set_value(iter, self.PHOTO_MODIFIED, apply)
			model.set_value(iter, self.PHOTO_SUMMARY, self.create_summary(iter, apply))
			
		# Set sensitivity of buttons as appropriate for the changes we've just made
		self.revert_button.set_sensitive(self.any_modified(self.treeselection))
		self.save_button.set_sensitive(self.any_modified())
		# Hide the TreeView if it's empty, because it shows an ugly white strip
		if delete and not self.liststore.get_iter_first(): self.treeview.hide()
	
	def __init__(self):
		# Will store GPS data once GPX files loaded by user
		self.tracks = {}
		
		# Warning, mod_count is not updated in real time, you must call 
		# self.any_modified() first if you want this value to mean anything.
		self.mod_count = 0
		
		self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
		self.window.set_title("GottenGeography - Geotag your photos!")
		self.window.set_size_request(700,500)
		
		self.vbox = gtk.VBox(spacing=0)
		
		# Create the toolbar with standard buttons and some tooltips
		self.toolbar = gtk.Toolbar()
		self.load_button = gtk.ToolButton(gtk.STOCK_OPEN)
		self.load_button.set_tooltip_text("Load photos or GPS data")
		
		self.delete_button = gtk.ToolButton(gtk.STOCK_DELETE) # TODO Is this appropriate? I don't want the user to think his photos will be deleted. It's just for unloading photos.
		self.delete_button.set_tooltip_text("Remove selected photos")
		self.delete_button.set_sensitive(False)
		
		self.toolbar_spacer = gtk.SeparatorToolItem()
		
		self.apply_button = gtk.ToolButton(gtk.STOCK_APPLY)
		self.apply_button.set_tooltip_text("Link displayed GPS data with selected photos")
		self.apply_button.set_sensitive(False)
		
		self.save_button = gtk.ToolButton(gtk.STOCK_SAVE)
		self.save_button.set_tooltip_text("Save all modified GPS data into your photos")
		self.save_button.set_label("Save All")
		self.save_button.set_sensitive(False)
		
		self.revert_button = gtk.ToolButton(gtk.STOCK_REVERT_TO_SAVED)
		self.revert_button.set_tooltip_text("Revert any changes made to selected photos")
		self.revert_button.set_sensitive(False)
		
		self.toolbar_spacer2 = gtk.SeparatorToolItem()
		
		self.zoom_in_button = gtk.ToolButton(gtk.STOCK_ZOOM_IN)
		self.zoom_out_button = gtk.ToolButton(gtk.STOCK_ZOOM_OUT)
		
		self.toolbar_spacer3 = gtk.SeparatorToolItem()
		self.toolbar_spacer3.set_expand(True)
		self.toolbar_spacer3.set_draw(False)
		
		self.about_button = gtk.ToolButton(gtk.STOCK_ABOUT)
		
		#self.toolbar.set_style(gtk.TOOLBAR_ICONS) # TODO let user decide this
		
		self.hbox = gtk.HBox()
		
		# This code defines how the photo list will appear
		# TODO Image thumbnails / pyexiv2
		# TODO sort by timestamp (needs pyexiv2)
		self.liststore = gtk.ListStore(
			gobject.TYPE_STRING,  # 0 Path to image file
			gobject.TYPE_STRING,  # 1 "Nice" name for display purposes
			gtk.gdk.Pixbuf,       # 2 Thumbnail (one day...)
			gobject.TYPE_INT,     # 3 Timestamp in Epoch seconds
			gobject.TYPE_BOOLEAN, # 4 Coordinates (true if lat/long are present)
			gobject.TYPE_STRING,  # 5 Latitude
			gobject.TYPE_STRING,  # 6 Longitude
			gobject.TYPE_BOOLEAN  # 7 'Have we modified the file?' flag
		)
		
		# These constants will make referencing the above columns much easier
		self.PHOTO_PATH =		0
		self.PHOTO_SUMMARY =		1
		self.PHOTO_THUMB =		2
		self.PHOTO_TIMESTAMP =		3
		self.PHOTO_COORDINATES =	4
		self.PHOTO_LATITUDE =		5
		self.PHOTO_LONGITUDE =		6
		self.PHOTO_MODIFIED =		7
		
		self.treeview = gtk.TreeView(self.liststore)
		self.treeview.set_enable_search(False)
		self.treeview.set_reorderable(False)
		self.treeview.set_headers_visible(False)
		self.treeview.set_rubber_banding(True)
		
		self.treeselection = self.treeview.get_selection()
		self.treeselection.set_mode(gtk.SELECTION_MULTIPLE)
		
		self.cell_string = gtk.CellRendererText()
		self.cell_thumb = gtk.CellRendererPixbuf()
		self.cell_thumb.set_property('stock-id', gtk.STOCK_MISSING_IMAGE)
		self.cell_thumb.set_property('ypad', 6)
		self.cell_thumb.set_property('xpad', 6)
		
		self.img_column = gtk.TreeViewColumn('Thumbnails', self.cell_thumb)
		self.img_column.add_attribute(self.cell_thumb, 'pixbuf', self.PHOTO_THUMB)
		self.img_column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
		self.treeview.append_column(self.img_column)
		
		self.name_column = gtk.TreeViewColumn('Summary', self.cell_string, markup=self.PHOTO_SUMMARY)
		self.name_column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
		self.treeview.append_column(self.name_column)
		
		self.photoscroller = gtk.ScrolledWindow()
		self.photoscroller.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		
		self.champlain = gtk.Label("libchamplain goes here")
		
		self.progressbar = gtk.ProgressBar()
		
		# This adds each widget into it's place in the window.
		self.photoscroller.add(self.treeview)
		self.hbox.pack_start(self.photoscroller, expand=0, fill=1)
		self.hbox.pack_end(self.champlain, expand=1, fill=1)
		self.toolbar.add(self.load_button)
		self.toolbar.add(self.save_button)
		self.toolbar.add(self.toolbar_spacer)
		self.toolbar.add(self.apply_button)
		self.toolbar.add(self.revert_button)
		self.toolbar.add(self.delete_button)
		self.toolbar.add(self.toolbar_spacer2)
		self.toolbar.add(self.zoom_in_button)
		self.toolbar.add(self.zoom_out_button)
		self.toolbar.add(self.toolbar_spacer3)
		self.toolbar.add(self.about_button)
		self.vbox.pack_start(self.toolbar, expand=0)
		self.vbox.pack_start(self.hbox, expand=1)
		self.vbox.pack_end(self.progressbar, expand=0, padding=6)
		self.window.add(self.vbox)
		
		# Connect all my precious signal handlers
		self.window.connect("delete_event", self.delete_event)
		self.window.connect("destroy", self.destroy)
		self.load_button.connect("clicked", self.add_file)
		self.delete_button.connect("clicked", self.apply_changes, False, True)
		self.save_button.connect("clicked", self.save_files)
		self.revert_button.connect("clicked", self.apply_changes, False)
		self.apply_button.connect("clicked", self.apply_changes, True)
		self.about_button.connect("clicked", self.about_dialog)
		self.treeselection.connect("changed", self.selection_changed)
		
		# Causes all widgets to be displayed except the empty TreeView and the progressbar
		self.window.show_all()
		self.treeview.hide()
		self.progressbar.hide()

	def main(self):
		gtk.main()

LICENSE = """
                    GNU GENERAL PUBLIC LICENSE
                       Version 3, 29 June 2007

 Copyright (C) 2007 Free Software Foundation, Inc. <http://fsf.org/>
 Everyone is permitted to copy and distribute verbatim copies
 of this license document, but changing it is not allowed.

                            Preamble

  The GNU General Public License is a free, copyleft license for
software and other kinds of works.

  The licenses for most software and other practical works are designed
to take away your freedom to share and change the works.  By contrast,
the GNU General Public License is intended to guarantee your freedom to
share and change all versions of a program--to make sure it remains free
software for all its users.  We, the Free Software Foundation, use the
GNU General Public License for most of our software; it applies also to
any other work released this way by its authors.  You can apply it to
your programs, too.

  When we speak of free software, we are referring to freedom, not
price.  Our General Public Licenses are designed to make sure that you
have the freedom to distribute copies of free software (and charge for
them if you wish), that you receive source code or can get it if you
want it, that you can change the software or use pieces of it in new
free programs, and that you know you can do these things.

  To protect your rights, we need to prevent others from denying you
these rights or asking you to surrender the rights.  Therefore, you have
certain responsibilities if you distribute copies of the software, or if
you modify it: responsibilities to respect the freedom of others.

  For example, if you distribute copies of such a program, whether
gratis or for a fee, you must pass on to the recipients the same
freedoms that you received.  You must make sure that they, too, receive
or can get the source code.  And you must show them these terms so they
know their rights.

  Developers that use the GNU GPL protect your rights with two steps:
(1) assert copyright on the software, and (2) offer you this License
giving you legal permission to copy, distribute and/or modify it.

  For the developers' and authors' protection, the GPL clearly explains
that there is no warranty for this free software.  For both users' and
authors' sake, the GPL requires that modified versions be marked as
changed, so that their problems will not be attributed erroneously to
authors of previous versions.

  Some devices are designed to deny users access to install or run
modified versions of the software inside them, although the manufacturer
can do so.  This is fundamentally incompatible with the aim of
protecting users' freedom to change the software.  The systematic
pattern of such abuse occurs in the area of products for individuals to
use, which is precisely where it is most unacceptable.  Therefore, we
have designed this version of the GPL to prohibit the practice for those
products.  If such problems arise substantially in other domains, we
stand ready to extend this provision to those domains in future versions
of the GPL, as needed to protect the freedom of users.

  Finally, every program is threatened constantly by software patents.
States should not allow patents to restrict development and use of
software on general-purpose computers, but in those that do, we wish to
avoid the special danger that patents applied to a free program could
make it effectively proprietary.  To prevent this, the GPL assures that
patents cannot be used to render the program non-free.

  The precise terms and conditions for copying, distribution and
modification follow.

                       TERMS AND CONDITIONS

  0. Definitions.

  "This License" refers to version 3 of the GNU General Public License.

  "Copyright" also means copyright-like laws that apply to other kinds of
works, such as semiconductor masks.

  "The Program" refers to any copyrightable work licensed under this
License.  Each licensee is addressed as "you".  "Licensees" and
"recipients" may be individuals or organizations.

  To "modify" a work means to copy from or adapt all or part of the work
in a fashion requiring copyright permission, other than the making of an
exact copy.  The resulting work is called a "modified version" of the
earlier work or a work "based on" the earlier work.

  A "covered work" means either the unmodified Program or a work based
on the Program.

  To "propagate" a work means to do anything with it that, without
permission, would make you directly or secondarily liable for
infringement under applicable copyright law, except executing it on a
computer or modifying a private copy.  Propagation includes copying,
distribution (with or without modification), making available to the
public, and in some countries other activities as well.

  To "convey" a work means any kind of propagation that enables other
parties to make or receive copies.  Mere interaction with a user through
a computer network, with no transfer of a copy, is not conveying.

  An interactive user interface displays "Appropriate Legal Notices"
to the extent that it includes a convenient and prominently visible
feature that (1) displays an appropriate copyright notice, and (2)
tells the user that there is no warranty for the work (except to the
extent that warranties are provided), that licensees may convey the
work under this License, and how to view a copy of this License.  If
the interface presents a list of user commands or options, such as a
menu, a prominent item in the list meets this criterion.

  1. Source Code.

  The "source code" for a work means the preferred form of the work
for making modifications to it.  "Object code" means any non-source
form of a work.

  A "Standard Interface" means an interface that either is an official
standard defined by a recognized standards body, or, in the case of
interfaces specified for a particular programming language, one that
is widely used among developers working in that language.

  The "System Libraries" of an executable work include anything, other
than the work as a whole, that (a) is included in the normal form of
packaging a Major Component, but which is not part of that Major
Component, and (b) serves only to enable use of the work with that
Major Component, or to implement a Standard Interface for which an
implementation is available to the public in source code form.  A
"Major Component", in this context, means a major essential component
(kernel, window system, and so on) of the specific operating system
(if any) on which the executable work runs, or a compiler used to
produce the work, or an object code interpreter used to run it.

  The "Corresponding Source" for a work in object code form means all
the source code needed to generate, install, and (for an executable
work) run the object code and to modify the work, including scripts to
control those activities.  However, it does not include the work's
System Libraries, or general-purpose tools or generally available free
programs which are used unmodified in performing those activities but
which are not part of the work.  For example, Corresponding Source
includes interface definition files associated with source files for
the work, and the source code for shared libraries and dynamically
linked subprograms that the work is specifically designed to require,
such as by intimate data communication or control flow between those
subprograms and other parts of the work.

  The Corresponding Source need not include anything that users
can regenerate automatically from other parts of the Corresponding
Source.

  The Corresponding Source for a work in source code form is that
same work.

  2. Basic Permissions.

  All rights granted under this License are granted for the term of
copyright on the Program, and are irrevocable provided the stated
conditions are met.  This License explicitly affirms your unlimited
permission to run the unmodified Program.  The output from running a
covered work is covered by this License only if the output, given its
content, constitutes a covered work.  This License acknowledges your
rights of fair use or other equivalent, as provided by copyright law.

  You may make, run and propagate covered works that you do not
convey, without conditions so long as your license otherwise remains
in force.  You may convey covered works to others for the sole purpose
of having them make modifications exclusively for you, or provide you
with facilities for running those works, provided that you comply with
the terms of this License in conveying all material for which you do
not control copyright.  Those thus making or running the covered works
for you must do so exclusively on your behalf, under your direction
and control, on terms that prohibit them from making any copies of
your copyrighted material outside their relationship with you.

  Conveying under any other circumstances is permitted solely under
the conditions stated below.  Sublicensing is not allowed; section 10
makes it unnecessary.

  3. Protecting Users' Legal Rights From Anti-Circumvention Law.

  No covered work shall be deemed part of an effective technological
measure under any applicable law fulfilling obligations under article
11 of the WIPO copyright treaty adopted on 20 December 1996, or
similar laws prohibiting or restricting circumvention of such
measures.

  When you convey a covered work, you waive any legal power to forbid
circumvention of technological measures to the extent such circumvention
is effected by exercising rights under this License with respect to
the covered work, and you disclaim any intention to limit operation or
modification of the work as a means of enforcing, against the work's
users, your or third parties' legal rights to forbid circumvention of
technological measures.

  4. Conveying Verbatim Copies.

  You may convey verbatim copies of the Program's source code as you
receive it, in any medium, provided that you conspicuously and
appropriately publish on each copy an appropriate copyright notice;
keep intact all notices stating that this License and any
non-permissive terms added in accord with section 7 apply to the code;
keep intact all notices of the absence of any warranty; and give all
recipients a copy of this License along with the Program.

  You may charge any price or no price for each copy that you convey,
and you may offer support or warranty protection for a fee.

  5. Conveying Modified Source Versions.

  You may convey a work based on the Program, or the modifications to
produce it from the Program, in the form of source code under the
terms of section 4, provided that you also meet all of these conditions:

    a) The work must carry prominent notices stating that you modified
    it, and giving a relevant date.

    b) The work must carry prominent notices stating that it is
    released under this License and any conditions added under section
    7.  This requirement modifies the requirement in section 4 to
    "keep intact all notices".

    c) You must license the entire work, as a whole, under this
    License to anyone who comes into possession of a copy.  This
    License will therefore apply, along with any applicable section 7
    additional terms, to the whole of the work, and all its parts,
    regardless of how they are packaged.  This License gives no
    permission to license the work in any other way, but it does not
    invalidate such permission if you have separately received it.

    d) If the work has interactive user interfaces, each must display
    Appropriate Legal Notices; however, if the Program has interactive
    interfaces that do not display Appropriate Legal Notices, your
    work need not make them do so.

  A compilation of a covered work with other separate and independent
works, which are not by their nature extensions of the covered work,
and which are not combined with it such as to form a larger program,
in or on a volume of a storage or distribution medium, is called an
"aggregate" if the compilation and its resulting copyright are not
used to limit the access or legal rights of the compilation's users
beyond what the individual works permit.  Inclusion of a covered work
in an aggregate does not cause this License to apply to the other
parts of the aggregate.

  6. Conveying Non-Source Forms.

  You may convey a covered work in object code form under the terms
of sections 4 and 5, provided that you also convey the
machine-readable Corresponding Source under the terms of this License,
in one of these ways:

    a) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by the
    Corresponding Source fixed on a durable physical medium
    customarily used for software interchange.

    b) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by a
    written offer, valid for at least three years and valid for as
    long as you offer spare parts or customer support for that product
    model, to give anyone who possesses the object code either (1) a
    copy of the Corresponding Source for all the software in the
    product that is covered by this License, on a durable physical
    medium customarily used for software interchange, for a price no
    more than your reasonable cost of physically performing this
    conveying of source, or (2) access to copy the
    Corresponding Source from a network server at no charge.

    c) Convey individual copies of the object code with a copy of the
    written offer to provide the Corresponding Source.  This
    alternative is allowed only occasionally and noncommercially, and
    only if you received the object code with such an offer, in accord
    with subsection 6b.

    d) Convey the object code by offering access from a designated
    place (gratis or for a charge), and offer equivalent access to the
    Corresponding Source in the same way through the same place at no
    further charge.  You need not require recipients to copy the
    Corresponding Source along with the object code.  If the place to
    copy the object code is a network server, the Corresponding Source
    may be on a different server (operated by you or a third party)
    that supports equivalent copying facilities, provided you maintain
    clear directions next to the object code saying where to find the
    Corresponding Source.  Regardless of what server hosts the
    Corresponding Source, you remain obligated to ensure that it is
    available for as long as needed to satisfy these requirements.

    e) Convey the object code using peer-to-peer transmission, provided
    you inform other peers where the object code and Corresponding
    Source of the work are being offered to the general public at no
    charge under subsection 6d.

  A separable portion of the object code, whose source code is excluded
from the Corresponding Source as a System Library, need not be
included in conveying the object code work.

  A "User Product" is either (1) a "consumer product", which means any
tangible personal property which is normally used for personal, family,
or household purposes, or (2) anything designed or sold for incorporation
into a dwelling.  In determining whether a product is a consumer product,
doubtful cases shall be resolved in favor of coverage.  For a particular
product received by a particular user, "normally used" refers to a
typical or common use of that class of product, regardless of the status
of the particular user or of the way in which the particular user
actually uses, or expects or is expected to use, the product.  A product
is a consumer product regardless of whether the product has substantial
commercial, industrial or non-consumer uses, unless such uses represent
the only significant mode of use of the product.

  "Installation Information" for a User Product means any methods,
procedures, authorization keys, or other information required to install
and execute modified versions of a covered work in that User Product from
a modified version of its Corresponding Source.  The information must
suffice to ensure that the continued functioning of the modified object
code is in no case prevented or interfered with solely because
modification has been made.

  If you convey an object code work under this section in, or with, or
specifically for use in, a User Product, and the conveying occurs as
part of a transaction in which the right of possession and use of the
User Product is transferred to the recipient in perpetuity or for a
fixed term (regardless of how the transaction is characterized), the
Corresponding Source conveyed under this section must be accompanied
by the Installation Information.  But this requirement does not apply
if neither you nor any third party retains the ability to install
modified object code on the User Product (for example, the work has
been installed in ROM).

  The requirement to provide Installation Information does not include a
requirement to continue to provide support service, warranty, or updates
for a work that has been modified or installed by the recipient, or for
the User Product in which it has been modified or installed.  Access to a
network may be denied when the modification itself materially and
adversely affects the operation of the network or violates the rules and
protocols for communication across the network.

  Corresponding Source conveyed, and Installation Information provided,
in accord with this section must be in a format that is publicly
documented (and with an implementation available to the public in
source code form), and must require no special password or key for
unpacking, reading or copying.

  7. Additional Terms.

  "Additional permissions" are terms that supplement the terms of this
License by making exceptions from one or more of its conditions.
Additional permissions that are applicable to the entire Program shall
be treated as though they were included in this License, to the extent
that they are valid under applicable law.  If additional permissions
apply only to part of the Program, that part may be used separately
under those permissions, but the entire Program remains governed by
this License without regard to the additional permissions.

  When you convey a copy of a covered work, you may at your option
remove any additional permissions from that copy, or from any part of
it.  (Additional permissions may be written to require their own
removal in certain cases when you modify the work.)  You may place
additional permissions on material, added by you to a covered work,
for which you have or can give appropriate copyright permission.

  Notwithstanding any other provision of this License, for material you
add to a covered work, you may (if authorized by the copyright holders of
that material) supplement the terms of this License with terms:

    a) Disclaiming warranty or limiting liability differently from the
    terms of sections 15 and 16 of this License; or

    b) Requiring preservation of specified reasonable legal notices or
    author attributions in that material or in the Appropriate Legal
    Notices displayed by works containing it; or

    c) Prohibiting misrepresentation of the origin of that material, or
    requiring that modified versions of such material be marked in
    reasonable ways as different from the original version; or

    d) Limiting the use for publicity purposes of names of licensors or
    authors of the material; or

    e) Declining to grant rights under trademark law for use of some
    trade names, trademarks, or service marks; or

    f) Requiring indemnification of licensors and authors of that
    material by anyone who conveys the material (or modified versions of
    it) with contractual assumptions of liability to the recipient, for
    any liability that these contractual assumptions directly impose on
    those licensors and authors.

  All other non-permissive additional terms are considered "further
restrictions" within the meaning of section 10.  If the Program as you
received it, or any part of it, contains a notice stating that it is
governed by this License along with a term that is a further
restriction, you may remove that term.  If a license document contains
a further restriction but permits relicensing or conveying under this
License, you may add to a covered work material governed by the terms
of that license document, provided that the further restriction does
not survive such relicensing or conveying.

  If you add terms to a covered work in accord with this section, you
must place, in the relevant source files, a statement of the
additional terms that apply to those files, or a notice indicating
where to find the applicable terms.

  Additional terms, permissive or non-permissive, may be stated in the
form of a separately written license, or stated as exceptions;
the above requirements apply either way.

  8. Termination.

  You may not propagate or modify a covered work except as expressly
provided under this License.  Any attempt otherwise to propagate or
modify it is void, and will automatically terminate your rights under
this License (including any patent licenses granted under the third
paragraph of section 11).

  However, if you cease all violation of this License, then your
license from a particular copyright holder is reinstated (a)
provisionally, unless and until the copyright holder explicitly and
finally terminates your license, and (b) permanently, if the copyright
holder fails to notify you of the violation by some reasonable means
prior to 60 days after the cessation.

  Moreover, your license from a particular copyright holder is
reinstated permanently if the copyright holder notifies you of the
violation by some reasonable means, this is the first time you have
received notice of violation of this License (for any work) from that
copyright holder, and you cure the violation prior to 30 days after
your receipt of the notice.

  Termination of your rights under this section does not terminate the
licenses of parties who have received copies or rights from you under
this License.  If your rights have been terminated and not permanently
reinstated, you do not qualify to receive new licenses for the same
material under section 10.

  9. Acceptance Not Required for Having Copies.

  You are not required to accept this License in order to receive or
run a copy of the Program.  Ancillary propagation of a covered work
occurring solely as a consequence of using peer-to-peer transmission
to receive a copy likewise does not require acceptance.  However,
nothing other than this License grants you permission to propagate or
modify any covered work.  These actions infringe copyright if you do
not accept this License.  Therefore, by modifying or propagating a
covered work, you indicate your acceptance of this License to do so.

  10. Automatic Licensing of Downstream Recipients.

  Each time you convey a covered work, the recipient automatically
receives a license from the original licensors, to run, modify and
propagate that work, subject to this License.  You are not responsible
for enforcing compliance by third parties with this License.

  An "entity transaction" is a transaction transferring control of an
organization, or substantially all assets of one, or subdividing an
organization, or merging organizations.  If propagation of a covered
work results from an entity transaction, each party to that
transaction who receives a copy of the work also receives whatever
licenses to the work the party's predecessor in interest had or could
give under the previous paragraph, plus a right to possession of the
Corresponding Source of the work from the predecessor in interest, if
the predecessor has it or can get it with reasonable efforts.

  You may not impose any further restrictions on the exercise of the
rights granted or affirmed under this License.  For example, you may
not impose a license fee, royalty, or other charge for exercise of
rights granted under this License, and you may not initiate litigation
(including a cross-claim or counterclaim in a lawsuit) alleging that
any patent claim is infringed by making, using, selling, offering for
sale, or importing the Program or any portion of it.

  11. Patents.

  A "contributor" is a copyright holder who authorizes use under this
License of the Program or a work on which the Program is based.  The
work thus licensed is called the contributor's "contributor version".

  A contributor's "essential patent claims" are all patent claims
owned or controlled by the contributor, whether already acquired or
hereafter acquired, that would be infringed by some manner, permitted
by this License, of making, using, or selling its contributor version,
but do not include claims that would be infringed only as a
consequence of further modification of the contributor version.  For
purposes of this definition, "control" includes the right to grant
patent sublicenses in a manner consistent with the requirements of
this License.

  Each contributor grants you a non-exclusive, worldwide, royalty-free
patent license under the contributor's essential patent claims, to
make, use, sell, offer for sale, import and otherwise run, modify and
propagate the contents of its contributor version.

  In the following three paragraphs, a "patent license" is any express
agreement or commitment, however denominated, not to enforce a patent
(such as an express permission to practice a patent or covenant not to
sue for patent infringement).  To "grant" such a patent license to a
party means to make such an agreement or commitment not to enforce a
patent against the party.

  If you convey a covered work, knowingly relying on a patent license,
and the Corresponding Source of the work is not available for anyone
to copy, free of charge and under the terms of this License, through a
publicly available network server or other readily accessible means,
then you must either (1) cause the Corresponding Source to be so
available, or (2) arrange to deprive yourself of the benefit of the
patent license for this particular work, or (3) arrange, in a manner
consistent with the requirements of this License, to extend the patent
license to downstream recipients.  "Knowingly relying" means you have
actual knowledge that, but for the patent license, your conveying the
covered work in a country, or your recipient's use of the covered work
in a country, would infringe one or more identifiable patents in that
country that you have reason to believe are valid.

  If, pursuant to or in connection with a single transaction or
arrangement, you convey, or propagate by procuring conveyance of, a
covered work, and grant a patent license to some of the parties
receiving the covered work authorizing them to use, propagate, modify
or convey a specific copy of the covered work, then the patent license
you grant is automatically extended to all recipients of the covered
work and works based on it.

  A patent license is "discriminatory" if it does not include within
the scope of its coverage, prohibits the exercise of, or is
conditioned on the non-exercise of one or more of the rights that are
specifically granted under this License.  You may not convey a covered
work if you are a party to an arrangement with a third party that is
in the business of distributing software, under which you make payment
to the third party based on the extent of your activity of conveying
the work, and under which the third party grants, to any of the
parties who would receive the covered work from you, a discriminatory
patent license (a) in connection with copies of the covered work
conveyed by you (or copies made from those copies), or (b) primarily
for and in connection with specific products or compilations that
contain the covered work, unless you entered into that arrangement,
or that patent license was granted, prior to 28 March 2007.

  Nothing in this License shall be construed as excluding or limiting
any implied license or other defenses to infringement that may
otherwise be available to you under applicable patent law.

  12. No Surrender of Others' Freedom.

  If conditions are imposed on you (whether by court order, agreement or
otherwise) that contradict the conditions of this License, they do not
excuse you from the conditions of this License.  If you cannot convey a
covered work so as to satisfy simultaneously your obligations under this
License and any other pertinent obligations, then as a consequence you may
not convey it at all.  For example, if you agree to terms that obligate you
to collect a royalty for further conveying from those to whom you convey
the Program, the only way you could satisfy both those terms and this
License would be to refrain entirely from conveying the Program.

  13. Use with the GNU Affero General Public License.

  Notwithstanding any other provision of this License, you have
permission to link or combine any covered work with a work licensed
under version 3 of the GNU Affero General Public License into a single
combined work, and to convey the resulting work.  The terms of this
License will continue to apply to the part which is the covered work,
but the special requirements of the GNU Affero General Public License,
section 13, concerning interaction through a network will apply to the
combination as such.

  14. Revised Versions of this License.

  The Free Software Foundation may publish revised and/or new versions of
the GNU General Public License from time to time.  Such new versions will
be similar in spirit to the present version, but may differ in detail to
address new problems or concerns.

  Each version is given a distinguishing version number.  If the
Program specifies that a certain numbered version of the GNU General
Public License "or any later version" applies to it, you have the
option of following the terms and conditions either of that numbered
version or of any later version published by the Free Software
Foundation.  If the Program does not specify a version number of the
GNU General Public License, you may choose any version ever published
by the Free Software Foundation.

  If the Program specifies that a proxy can decide which future
versions of the GNU General Public License can be used, that proxy's
public statement of acceptance of a version permanently authorizes you
to choose that version for the Program.

  Later license versions may give you additional or different
permissions.  However, no additional obligations are imposed on any
author or copyright holder as a result of your choosing to follow a
later version.

  15. Disclaimer of Warranty.

  THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY
APPLICABLE LAW.  EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT
HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY
OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO,
THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE.  THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM
IS WITH YOU.  SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF
ALL NECESSARY SERVICING, REPAIR OR CORRECTION.

  16. Limitation of Liability.

  IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING
WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS
THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY
GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE
USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF
DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD
PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS),
EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF
SUCH DAMAGES.

  17. Interpretation of Sections 15 and 16.

  If the disclaimer of warranty and limitation of liability provided
above cannot be given local legal effect according to their terms,
reviewing courts shall apply local law that most closely approximates
an absolute waiver of all civil liability in connection with the
Program, unless a warranty or assumption of liability accompanies a
copy of the Program in return for a fee.

                     END OF TERMS AND CONDITIONS
"""

if __name__ == "__main__":
	gui = GottenGeography()
	gui.main()
