
"""
The idea of this module is to implement a generic record/playback tool for GTK GUIs that
will create scripts in terms of the domain language. These will then be much more stable
than traditional such tools that create complicated Tcl scripts with lots of references
to pixel positions etc., which tend to be extremely brittle if the GUI is updated.

It is based on the generic usecase.py, read the documentation there too.

(1) For user actions such as clicking a button, selecting a list item etc., the general idea
is to add an extra argument to the call to 'connect', so that instead of writing

button.connect("clicked", myMethod)

you would write

scriptEngine.connect("save changes", "clicked", button, myMethod)

thus tying the user action to the script command "save changes". If you set up a record
script, then the module will write "save changes" to the script whenever the button is clicked.
Conversely, if you set up a replay script, then on finding the command "save changes", the
module will emit the "clicked" signal for said button, effectively clicking it programatically.

This means that, so long as my GUI has a concept of "save changes", I can redesign the GUI totally,
making the user choose to do this via a totally different widget, but all my scripts wiill
remaing unchanged.

(2) Some GUI widgets have "state" rather than relying on signals (for example text entries, toggle buttons),
so that the GUI itself may not necessarily make any calls to 'connect'. But you still want to generate
script commands when they change state, and be able to change them programatically. I have done this
by providing a 'register' method, so that an extra call is made to scriptEngine

entry = gtk.Entry()
scriptEngine.registerEntry(entry, "enter file name = ")

which would tie the "focus-out-event" to the script command "enter file name = <current_entry_contents>".

(3) There are also composite widgets like the TreeView where you need to be able to specify an argument.
In this case the application has to provide extra information as to how the text is to be translated
into selecting an item in the tree. So, for example:

treeView.connect("row_activated", myMethod)

might become

scriptEngine.connect("select file", "row_activated", treeView, myMethod, (column, dataIndex))

(column, dataIndex) is a tuple to tell it which data in the tree view we are looking for. So that
the command "select file foobar.txt" will search the tree's column <column> and data index <dataIndex>
for the text "foobar.txt" and select that row accordingly.

(4) There are other widgets supported too, it's probably easiest just to read the code for the API
to these, they're fairly self-explanatory. But there are also many widgets that aren't (I have implemented
what I have needed myself and no more) - happy hacking!

(5) GUI shortcuts

Provided your scriptEngine was created with enableShortcuts=1, you can call the method gtk.createShortcutBar,
which will return a gtk.HBox allowing the user to dynamically record multiple clicks and make extra buttons
appear on this bar so that they can be created. Such shortcuts will be recorded in the directory indicated
by USECASE_HOME (defaulting to ~/usecases). Also, where a user makes a sequence of clicks which correspond to
an existing shortcut, this will be recorded as the shortcut name.

To see this in action, try out the video store example.
"""

import usecase, gtk, os, string

# Base class for all GTK events due to widget signals
class SignalEvent(usecase.UserEvent):
    anyEvent = None
    def __init__(self, name, widget, signalName):
        usecase.UserEvent.__init__(self, name)
        self.widget = widget
        self.signalName = signalName
        # Signals often need to be emitted with a corresponding event.
        # This is very hard to fake. The only way I've found is to seize a random event
        # and use that... this is not foolproof...
        if not self.anyEvent:
            try:
                self.anyEventHandler = self.widget.connect("event", self.storeEvent)
            except TypeError:
                pass
    def storeEvent(self, widget, event, *args):
        SignalEvent.anyEvent = event
        self.widget.disconnect(self.anyEventHandler)
    def outputForScript(self, widget, *args):
        return self._outputForScript(*args)
    def _outputForScript(self, *args):
        return self.name
    def generate(self, argumentString):
        self.widget.grab_focus()
        # Seems grabbing the focus doesn't always generate a focus in event...
        self.widget.emit("focus-in-event", self.anyEvent)
        self._generate(argumentString)
    def _generate(self, argumentString):
        try:
            self.widget.emit(self.signalName)
        except TypeError:
            # The simplest way I could find to fake a gtk.gdk.Event
            self.widget.emit(self.signalName, self.anyEvent)
            
# Events we monitor via GUI focus when we don't want all the gory details
# and don't want programmtic state changes recorded
class StateChangeEvent(SignalEvent):
    def __init__(self, name, widget, relevantState = None):
        SignalEvent.__init__(self, name, widget, "focus-out-event")
        self.relevantState = relevantState
        self.updateState()
        # When we focus in we should update with any programmatic changes.
        self.widget.connect("focus-in-event", self.updateState)
    def updateState(self, *args):
        self.oldState = self.getState()
    def stateDescription(self):
        return self.name
    def shouldRecord(self, *args):
        state = self.getState()
        if not self.relevantState is None and state != self.relevantState:
            self.updateState()
            return 0
        return state != self.oldState
    def _outputForScript(self, *args):
        self.updateState()
        return self.stateDescription()
    def _generate(self, argumentString):
        self.generateStateChange(argumentString)
        self.widget.emit(self.signalName, self.anyEvent)
        
class EntryEvent(StateChangeEvent):
    def getState(self):
        return self.widget.get_text()
    def stateDescription(self):
        return self.name + " " + self.oldState
    def generateStateChange(self, argumentString):
        self.widget.set_text(argumentString)

class ActivateEvent(StateChangeEvent):
    def getState(self):
        return self.widget.get_active()
    def generateStateChange(self, argumentString):
        self.widget.set_active(self.relevantState)
    
class ResponseEvent(SignalEvent):
    def __init__(self, name, widget, responseId):
        SignalEvent.__init__(self, name, widget, "response")
        self.responseId = responseId
    def shouldRecord(self, widget, responseId, *args):
        return self.responseId == responseId
    def _generate(self, argumentString):
        self.widget.emit(self.signalName, self.responseId)

class NotebookPageChangeEvent(SignalEvent):
    def __init__(self, name, widget):
        SignalEvent.__init__(self, name, widget, "switch-page")
    def _outputForScript(self, page, page_num, *args):
        newPage = self.widget.get_nth_page(page_num)
        return self.name + " " + self.widget.get_tab_label_text(newPage)
    def _generate(self, argumentString):
        for i in range(len(self.widget.get_children())):
            page = self.widget.get_nth_page(i)
            if self.widget.get_tab_label_text(page) == argumentString:
                self.widget.set_current_page(i)
                return
        raise usecase.UseCaseScriptError, "Could not find page " + argumentString + " in '" + self.name + "'"

class TreeViewSignalEvent(SignalEvent):
    def __init__(self, name, widget, signalName, indexer):
        SignalEvent.__init__(self, name, widget, signalName)
        self.indexer = indexer
    def _outputForScript(self, path, *args):
        return self.name + " " + self.indexer.path2string(path)
    def _generate(self, argumentString):
        path = self.indexer.string2path(argumentString)
        self.widget.emit(self.signalName, path, self.indexer.column)

class TreeSelectionEvent(StateChangeEvent):
    def __init__(self, name, widget, indexer):
        self.selection = widget
        StateChangeEvent.__init__(self, name, widget.get_tree_view())
        self.indexer = indexer
        # Activating rows should update the state.
        self.widget.connect("row_activated", self.updateState)
    def getState(self):
        return string.join(self.findSelectedPaths(), ",")
    def stateDescription(self):
        return self.name + " " + self.oldState
    def generateStateChange(self, argumentString):
        self.selection.unselect_all()
        paths = map(self.indexer.string2path, argumentString.split(","))
        for path in paths:
            self.selection.select_path(path)
    def findSelectedPaths(self):
        paths = []
        self.selection.selected_foreach(self.addSelPath, paths)
        return paths
    def addSelPath(self, model, path, iter, paths):
        paths.append(self.indexer.path2string(path))

# Class to provide domain-level lookup for rows in a tree. Convert paths to strings and back again
class TreeModelIndexer:
    def __init__(self, model, column, valueId):
        self.model = model
        self.column = column
        self.valueId = valueId
    def path2string(self, path):
        return self.model.get_value(self.model.get_iter(path), self.valueId)
    def string2path(self, pathString):
        path = self._findTreePath(self.model.get_iter_root(), pathString)
        if not path:
            raise usecase.UseCaseScriptError, "Could not find row '" + pathString + "' in Tree View"
        return path
    def _findTreePath(self, iter, argumentText):
        if self._pathHasText(iter, argumentText):
            return self.model.get_path(iter)
        childIter = self.model.iter_children(iter)
        if childIter:
            childPath = self._findTreePath(childIter, argumentText)
            if childPath:
                return childPath
        nextIter = self.model.iter_next(iter)
        if nextIter:
            return self._findTreePath(nextIter, argumentText)
        return None
    def _pathHasText(self, iter, argumentText):
        return self.model.get_value(iter, self.valueId) == argumentText


class ScriptEngine(usecase.ScriptEngine):
    def __init__(self, logger = None, enableShortcuts = 0):
        usecase.ScriptEngine.__init__(self, logger, enableShortcuts)
        self.commandButtons = []
    def connect(self, eventName, signalName, widget, method = None, argumentParseData = None, *data):
        if self.active():
            stdName = self.standardName(eventName)
            signalEvent = self._createSignalEvent(signalName, stdName, widget, argumentParseData)
            self._addEventToScripts(signalEvent)
        if method:
            widget.connect(signalName, method, *data)
    def monitor(self, eventName, selection, argumentParseData = None):
        if self.active():
            stdName = self.standardName(eventName)
            stateChangeEvent = TreeSelectionEvent(stdName, selection, argumentParseData)
            self._addEventToScripts(stateChangeEvent)
    def registerEntry(self, entry, description):
        if self.active():
            stateChangeName = self.standardName(description)
            entryEvent = EntryEvent(stateChangeName, entry)
            if self.recorderActive():
                entryEvent.widget.connect("activate", self.recorder.writeEvent, entryEvent)
            self._addEventToScripts(entryEvent)
    def registerToggleButton(self, button, checkDescription, uncheckDescription = ""):
        if self.active():
            checkChangeName = self.standardName(checkDescription)
            checkEvent = ActivateEvent(checkChangeName, button, gtk.TRUE)
            self._addEventToScripts(checkEvent)
            if uncheckDescription:
                uncheckChangeName = self.standardName(uncheckDescription)
                uncheckEvent = ActivateEvent(uncheckChangeName, button, gtk.FALSE)
                self._addEventToScripts(uncheckEvent)
    def createNotebook(self, description, pages):
        notebook = gtk.Notebook()
        for page, tabText in pages:
            label = gtk.Label(tabText)
            notebook.append_page(page, label)
        if self.active():
            stateChangeName = self.standardName(description)
            event = NotebookPageChangeEvent(stateChangeName, notebook)
            self._addEventToScripts(event)
        return notebook
    def createShortcutBar(self):
        if not self.enableShortcuts:
            return None
        # Standard thing to add at the bottom of the GUI...
        buttonbox = gtk.HBox()
        existingbox = self.createExistingShortcutBox()
        buttonbox.pack_start(existingbox, expand=gtk.FALSE, fill=gtk.FALSE)
        newbox = gtk.HBox()
        self.addNewButton(newbox)
        self.addStopControls(newbox, existingbox)
        buttonbox.pack_start(newbox, expand=gtk.FALSE, fill=gtk.FALSE)
        existingbox.show()
        newbox.show()
        return buttonbox
#private
    def getShortcutFiles(self):
        files = []
        usecaseDir = os.environ["USECASE_HOME"]
        if not os.path.isdir(usecaseDir):
            return files
        for fileName in os.listdir(usecaseDir):
            if fileName.endswith(".shortcut"):
                files.append(os.path.join(os.environ["USECASE_HOME"], fileName))
        return files
    def createExistingShortcutBox(self):
        buttonbox = gtk.HBox()
        files = self.getShortcutFiles()
        label = gtk.Label("Shortcuts:")
        buttonbox.pack_start(label, expand=gtk.FALSE, fill=gtk.FALSE)
        for fileName in files:
            replayScript = usecase.ReplayScript(fileName)
            self.addShortcutButton(buttonbox, replayScript)
        label.show()
        return buttonbox
    def addNewButton(self, buttonbox):
        newButton = gtk.Button()
        newButton.set_label("New")
        self.connect("create new shortcut", "clicked", newButton, self.createShortcut, None, buttonbox)
        newButton.show()
        buttonbox.pack_start(newButton, expand=gtk.FALSE, fill=gtk.FALSE)
    def addShortcutButton(self, buttonbox, replayScript):
        button = gtk.Button()
        buttonName = replayScript.getShortcutName()
        button.set_label(buttonName)
        self.connect(buttonName.lower(), "clicked", button, self.replayShortcut, None, replayScript)
        firstCommand = replayScript.commands[0]
        if self.replayer.findCommandName(firstCommand):
            button.show()
            self.recorder.registerShortcut(replayScript)
        self.commandButtons.append((replayScript, button))
        buttonbox.pack_start(button, expand=gtk.FALSE, fill=gtk.FALSE)
    def addStopControls(self, buttonbox, existingbox):
        label = gtk.Label("Recording shortcut named:")
        buttonbox.pack_start(label, expand=gtk.FALSE, fill=gtk.FALSE)
        entry = gtk.Entry()
        self.registerEntry(entry, "set shortcut name to")
        buttonbox.pack_start(entry, expand=gtk.FALSE, fill=gtk.FALSE)
        stopButton = gtk.Button()
        stopButton.set_label("Stop")
        self.connect("stop recording", "clicked", stopButton, self.stopRecording, None, label, entry, buttonbox, existingbox)
        self.recorder.blockTopLevel("stop recording")
        self.recorder.blockTopLevel("set shortcut name to")
        buttonbox.pack_start(stopButton, expand=gtk.FALSE, fill=gtk.FALSE)
    def createShortcut(self, button, buttonbox, *args):
        buttonbox.show_all()
        button.hide()
        tmpFileName = self.getTmpShortcutName()
        self.recorder.addScript(tmpFileName)
    def stopRecording(self, button, label, entry, buttonbox, existingbox, *args):
        self.recorder.terminateScript()
        buttonbox.show_all()
        button.hide()
        label.hide()
        entry.hide()
        buttonName = entry.get_text()
        newScriptName = self.getShortcutFileName(buttonName)
        scriptExistedPreviously = os.path.isfile(newScriptName)
        os.rename(self.getTmpShortcutName(), newScriptName)
        if not scriptExistedPreviously:
            replayScript = usecase.ReplayScript(newScriptName)
            self.addShortcutButton(existingbox, replayScript)
    def replayShortcut(self, button, script, *args):
        self.replayer.addScript(script)
        if len(self.recorder.scripts):
            self.recorder.suspended = 1
            script.addExitObserver(self.recorder)
    def getTmpShortcutName(self):
        usecaseDir = os.environ["USECASE_HOME"]
        if not os.path.isdir(usecaseDir):
            os.makedirs(usecaseDir)
        return os.path.join(usecaseDir, "new_shortcut")
    def getShortcutFileName(self, buttonName):
        return os.path.join(os.environ["USECASE_HOME"], buttonName.replace(" ", "_") + ".shortcut")
    def createReplayer(self, logger):
        return UseCaseReplayer(logger)
    def showShortcutButtons(self, event):
        for replayScript, button in self.commandButtons:
            if replayScript.commands[0].startswith(event.name):
                button.show()
                self.recorder.registerShortcut(replayScript)
    def _addEventToScripts(self, event):
        if self.enableShortcuts:
            self.showShortcutButtons(event)
        if self.replayerActive():
            self.replayer.addEvent(event)
        if self.recorderActive():
            self.recorder.addEvent(event)
            event.widget.connect(event.signalName, self.recorder.writeEvent, event)
    def _createSignalEvent(self, signalName, eventName, widget, argumentParseData):
        if signalName == "response":
            return ResponseEvent(eventName, widget, argumentParseData)
        elif isinstance(widget, gtk.TreeView):
            return TreeViewSignalEvent(eventName, widget, signalName, argumentParseData)
        else:
            return SignalEvent(eventName, widget, signalName)

# Use the GTK idle handlers instead of a separate thread for replay execution
class UseCaseReplayer(usecase.UseCaseReplayer):
     def executeCommandsInBackground(self):
         gtk.idle_add(self.runNextCommand)
     def runNextCommand(self):
         retValue = usecase.UseCaseReplayer.runNextCommand(self)
         if retValue:
             return gtk.TRUE
         else:
             return gtk.FALSE
