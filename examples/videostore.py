#!/usr/bin/env python

# Test GUI for 'PyUseCase'. Illustrates use of (a) simple signal connection, as in buttons (b) text entries and (c) the shortcut bar
# Above each use of the PyUseCase script engine is the equivalent code without it, commented.

import gtk, gobject
from gtkusecase import ScriptEngine

class VideoStore:
    def __init__(self):
        self.scriptEngine = ScriptEngine(enableShortcuts=1)
        self.model = gtk.ListStore(gobject.TYPE_STRING)
    def createTopWindow(self):
        # Create toplevel window to show it all.
        win = gtk.Window(gtk.WINDOW_TOPLEVEL)
        win.set_title("The Video Store")
        #win.connect("delete_event", self.quit)
        self.scriptEngine.connect("close", "delete_event", win, self.quit)
        vbox = self.createWindowContents()
        win.add(vbox)
        win.show()
        win.resize(self.getWindowWidth(), self.getWindowHeight())
        return win
    def createWindowContents(self):
        vbox = gtk.VBox()
        vbox.pack_start(self.getTaskBar(), expand=gtk.FALSE, fill=gtk.FALSE)
        vbox.pack_start(self.getVideoView(), expand=gtk.TRUE, fill=gtk.TRUE)
        shortcutBar = self.scriptEngine.createShortcutBar()
        vbox.pack_start(shortcutBar, expand=gtk.FALSE, fill=gtk.FALSE)
        shortcutBar.show()
        vbox.show()
        return vbox
    def getTaskBar(self):
        taskBar = gtk.HBox()
        label = gtk.Label("New Movie Name  ")
        nameEntry = gtk.Entry()
        self.scriptEngine.registerEntry(nameEntry, "set new movie name to")
        self.scriptEngine.connect("add movie by pressing <enter>", "activate", nameEntry, self.addMovie, None, nameEntry)
        button = gtk.Button()
        button.set_label("Add")
        # button.connect("clicked", self.addMovie, nameEntry)
        self.scriptEngine.connect("add movie", "clicked", button, self.addMovie, None, nameEntry)
        sortButton = gtk.Button()
        sortButton.set_label("Sort")
        # sortButton.connect("clicked", self.sortMovies)
        self.scriptEngine.connect("sort movies", "clicked", sortButton, self.sortMovies)
        clearButton = gtk.Button()
        clearButton.set_label("Clear")
        # clearButton.connect("clicked", self.sortMovies)
        self.scriptEngine.connect("clear list", "clicked", clearButton, self.clearMovies)
        taskBar.pack_start(label, expand=gtk.FALSE, fill=gtk.TRUE)
        taskBar.pack_start(nameEntry, expand=gtk.TRUE, fill=gtk.TRUE)
        taskBar.pack_start(button, expand=gtk.FALSE, fill=gtk.FALSE)
        taskBar.pack_start(sortButton, expand=gtk.FALSE, fill=gtk.FALSE)
        taskBar.pack_start(clearButton, expand=gtk.FALSE, fill=gtk.FALSE)
        label.show()
        nameEntry.show()
        button.show()
        sortButton.show()
        clearButton.show()
        taskBar.show()
        return taskBar
    def getVideoView(self):
        view = gtk.TreeView(self.model)
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Movie Name", renderer, text=0)
        view.append_column(column)
        view.expand_all()
        view.show()

        # Create scrollbars around the view.
        scrolled = gtk.ScrolledWindow()
        scrolled.add(view)
        scrolled.show()    
        return scrolled
    def getWindowHeight(self):
        return (gtk.gdk.screen_height() * 2) / 5
    def getWindowWidth(self):
        return (gtk.gdk.screen_width()) / 5
    def run(self):
        # We've got everything and are ready to go
        topWindow = self.createTopWindow()
        gtk.main()
    def addMovie(self, button, entry, *args):
        movieName = entry.get_text()
        if not movieName in self.getMovieNames():
            self.model.append([ movieName ])
            print "Adding movie '" + movieName + "'. There are now", self.model.iter_n_children(None), "movies."
        else:
            self.showError("Movie '" + movieName + "' has already been added")
    def clearMovies(self, *args):
        self.model.clear()
    def sortMovies(self, *args):
        movieNames = self.getMovieNames()
        movieNames.sort()
        self.model.clear()
        for movie in movieNames:
            self.model.append([ movie ])
        print "Sorted movies, now in order:", self.getMovieNames()
    def getMovieNames(self):
        movies = []
        iter = self.model.get_iter_root()
        while iter:
            movies.append(self.model.get_value(iter, 0))
            iter = self.model.iter_next(iter)
        return movies
    def showError(self, message):
        print "ERROR :", message
        dialog = gtk.Dialog("VideoStore Error!", buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
        label = gtk.Label(message)
        dialog.vbox.pack_start(label, expand=gtk.TRUE, fill=gtk.TRUE)
        label.show()
        # dialog.connect("response", self.destroyErrorDialogue, gtk.RESPONSE_ACCEPT)
        self.scriptEngine.connect("accept error saying \"" + message + "\"", "response", dialog, self.destroyErrorDialogue, gtk.RESPONSE_ACCEPT)
        dialog.show()
    def destroyErrorDialogue(self, dialog, *args):
        dialog.destroy()
    def quit(self, *args):
        print "Exiting the video store!"
        gtk.main_quit()
        
if __name__ == "__main__":
    program = VideoStore()
    program.run()
