#!/usr/bin/env python

# Test GUI for 'PyUseCase'. Illustrates use of
#  (a) simple signal connection, as in buttons
#  (b) text entries and
#  (c) the shortcut bar
#  (d) menus
#  (e) notebooks

# Has universal logging enabled, via the first line, printed on standard output

# Also illustrates an idiom for making sure nothing happens if PyUseCase isn't available.

import gtk, gobject, logging, sys
try:
    from gtkusecase import ScriptEngine
except ImportError:
    class ScriptEngine:
        # Calling anything has no effect...
        def __init__(*args, **kwargs):
            pass
        def __getattr__(self, name):
            return self
        def __call__(*args, **kwargs):
            pass

class VideoStore:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
        self.scriptEngine = ScriptEngine(enableShortcuts=True, useUiMap=True)
        self.model = gtk.ListStore(gobject.TYPE_STRING)
        self.nameEntry = gtk.Entry()
        self.nameEntry.set_name("Movie Name")
        self.buttons = []
    def createTopWindow(self):
        # Create toplevel window to show it all.
        win = gtk.Window(gtk.WINDOW_TOPLEVEL)
        win.set_title("The Video Store")
        win.connect("delete_event", self.quit)
        self.scriptEngine.monitorSignal("close", "delete_event", win, method=self.quit)
        vbox = self.createWindowContents()
        win.add(vbox)
        win.show()
        win.resize(self.getWindowWidth(), self.getWindowHeight())
        return win
    def createWindowContents(self):
        vbox = gtk.VBox()
        vbox.pack_start(self.getMenuBar(), expand=False, fill=False)
        vbox.pack_start(self.getTaskBar(), expand=False, fill=False)
        vbox.pack_start(self.getNotebook(), expand=True, fill=True)
        shortcutBar = self.scriptEngine.createShortcutBar()
        if shortcutBar:
            vbox.pack_start(shortcutBar, expand=False, fill=False)
            shortcutBar.show()
        vbox.show()
        return vbox
    def getMenuBar(self):
        addItem = gtk.MenuItem("Add")
        deleteItem = gtk.MenuItem("Delete")
        sortItem = gtk.MenuItem("Sort")
        clearItem = gtk.MenuItem("Clear")
        buttonsItem = gtk.CheckMenuItem("Show buttons")
        buttons2Item = gtk.CheckMenuItem("Enable buttons")
        sepItem = gtk.SeparatorMenuItem() # Works?
        quitItem = gtk.MenuItem("Quit")
        buttonsItem.set_active(True)
        buttons2Item.set_active(True)
        
        actionsSubMenu = gtk.Menu()
        actionsSubMenu.append(addItem)
        actionsSubMenu.append(deleteItem)
        actionsSubMenu.append(sortItem)
        actionsSubMenu.append(clearItem)
        actionsItem = gtk.MenuItem("Actions")
        actionsItem.set_submenu(actionsSubMenu)
        
        fileMenu = gtk.Menu()
        fileMenu.append(actionsItem)
        fileMenu.append(buttonsItem)        
        fileMenu.append(buttons2Item)        
        fileMenu.append(quitItem)        
        fileItem = gtk.MenuItem("File")
        fileItem.set_submenu(fileMenu)        
        
        self.scriptEngine.monitorSignal("select menu 'File'", "activate", fileItem)
        self.scriptEngine.monitorSignal("select menu item 'Actions'", "activate", actionsItem)
        
        addItem.connect("activate", self.addMovie, self.nameEntry)
        deleteItem.connect("activate", self.deleteMovie, self.nameEntry)
        sortItem.connect("activate", self.sortMovies)
        clearItem.connect("activate", self.clearMovies)
        buttonsItem.connect("activate", self.hideButtons)
        buttons2Item.connect("activate", self.enableButtons)
        quitItem.connect("activate", self.quit)

        self.scriptEngine.monitorSignal("select menu item 'Add'", "activate", addItem)
        self.scriptEngine.monitorSignal("select menu item 'Delete'", "activate", deleteItem)
        self.scriptEngine.monitorSignal("select menu item 'Sort'", "activate", sortItem)
        self.scriptEngine.monitorSignal("select menu item 'Clear'", "activate", clearItem)
        self.scriptEngine.monitorSignal("select menu item 'Show buttons'", "activate", buttonsItem)
        self.scriptEngine.monitorSignal("select menu item 'Enable buttons'", "activate", buttons2Item)
        self.scriptEngine.monitorSignal("select menu item 'Quit'", "activate", quitItem)
        
        menuBar = gtk.MenuBar()
        menuBar.append(fileItem)
        menuBar.show_all()
        return menuBar
    def getTaskBar(self):
        taskBar = gtk.HBox()
        label = gtk.Label("New Movie Name  ")
        self.scriptEngine.registerEntry(self.nameEntry, "set new movie name to")
        self.nameEntry.connect("activate", self.addMovie, self.nameEntry)
        self.scriptEngine.monitorSignal("add movie by pressing <enter>", "activate", self.nameEntry)
        button = gtk.Button()
        button.set_label("Add")
        button.connect("clicked", self.addMovie, self.nameEntry)
        self.scriptEngine.monitorSignal("add movie", "clicked", button)
        deleteButton = gtk.Button()
        deleteButton.set_label("Delete")
        deleteButton.connect("clicked", self.deleteMovie, self.nameEntry)
        self.scriptEngine.monitorSignal("delete movie", "clicked", deleteButton)
        sortButton = gtk.Button()
        sortButton.set_label("Sort")
        sortButton.connect("clicked", self.sortMovies)
        self.scriptEngine.monitorSignal("sort movies", "clicked", sortButton)
        clearButton = gtk.Button()
        clearButton.set_label("Clear")
        clearButton.connect("clicked", self.clearMovies)
        self.scriptEngine.monitorSignal("clear list", "clicked", clearButton)

        # Place buttons
        taskBar.pack_start(label, expand=False, fill=True)
        taskBar.pack_start(self.nameEntry, expand=True, fill=True)
        taskBar.pack_start(button, expand=False, fill=False)
        taskBar.pack_start(deleteButton, expand=False, fill=False)
        taskBar.pack_start(sortButton, expand=False, fill=False)
        taskBar.pack_start(clearButton, expand=False, fill=False)

        # Store buttons, to be able to hide/disable them later
        self.buttons.append(button)
        self.buttons.append(deleteButton)
        self.buttons.append(sortButton)
        self.buttons.append(clearButton)

        taskBar.show_all()
        return taskBar
    def getNotebook(self):
        notebook = gtk.Notebook()
        notebook.append_page(self.getTextView(), gtk.Label("text info"))
        notebook.append_page(self.getVideoView(), gtk.Label("video view"))
        self.scriptEngine.monitorNotebook(notebook, "show")
        notebook.show()
        notebook.set_current_page(1)
        return notebook
    def getVideoView(self):
        view = gtk.TreeView(self.model)
        view.set_name("Movie Tree")
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
    def getTextView(self):
        textview = gtk.TextView()
        textbuffer = textview.get_buffer()
        textbuffer.set_text("This is the Video Store, an example program for PyUseCase")
        textview.show()
        return textview
    def hideButtons(self, item):
        if item.get_active():
            for b in self.buttons:
                b.show()
        else:
            for b in self.buttons:
                b.hide()            
    def enableButtons(self, item):
        if item.get_active():
            for b in self.buttons:
                b.set_sensitive(True)
        else:
            for b in self.buttons:
                b.set_sensitive(False)            
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
        else:
            self.showError("Movie '" + movieName + "' has already been added")
    def deleteMovie(self, button, entry, *args):
        movieName = entry.get_text()
        if movieName in self.getMovieNames():
            iter = self.model.get_iter_root()
            while iter:
                if self.model.get_value(iter, 0) == movieName:
                    self.model.remove(iter)
                    break
                iter = self.model.iter_next(iter)
        else:
            self.showError("Movie '" + movieName + "' does not exist.")
    def clearMovies(self, *args):
        self.model.clear()
    def sortMovies(self, *args):
        movieNames = self.getMovieNames()
        movieNames.sort()
        self.model.clear()
        for movie in movieNames:
            self.model.append([ movie ])
    def getMovieNames(self):
        movies = []
        iter = self.model.get_iter_root()
        while iter:
            movies.append(self.model.get_value(iter, 0))
            iter = self.model.iter_next(iter)
        return movies
    def showError(self, message):
        dialog = gtk.Dialog("VideoStore Error!", buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
        label = gtk.Label(message)
        dialog.vbox.pack_start(label, expand=True, fill=True)
        label.show()
        self.scriptEngine.monitorSignal("accept videostore error", "response", dialog, gtk.RESPONSE_ACCEPT)
        dialog.connect("response", self.destroyErrorDialogue)
        dialog.show()
    def destroyErrorDialogue(self, dialog, *args):
        dialog.destroy()
    def quit(self, *args):
        gtk.main_quit()
        
if __name__ == "__main__":
    program = VideoStore()
    program.run()
