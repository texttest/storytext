
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

which would tie the "leave-notify-event" to the script command "enter file name = <current_entry_contents>".

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
from gobject import idle_add

# Abstract Base class for all GTK events
class GtkEvent(usecase.UserEvent):
    def __init__(self, name, widget):
        usecase.UserEvent.__init__(self, name)
        self.widget = widget
    def getRecordSignal(self):
        pass
    def connectRecord(self, method):
        self.widget.connect(self.getRecordSignal(), method, self)
    def outputForScript(self, widget, *args):
        return self._outputForScript(*args)
    def _outputForScript(self, *args):
        return self.name
            
# Base class for all GTK events due to widget signals
class SignalEvent(GtkEvent):
    def __init__(self, name, widget, signalName):
        GtkEvent.__init__(self, name, widget)
        self.signalName = signalName
    def getRecordSignal(self):
        return self.signalName
    def generate(self, argumentString):
        self.widget.grab_focus()
        if self.widget.get_property("visible"):
            if self.widget.get_property("sensitive"):
                self.widget.emit(self.signalName)
            else:
                raise usecase.UseCaseScriptError, "widget " + repr(self.widget) + " is not sensitive to input at the moment, cannot simulate event " + repr(self.name)
        else:
            raise usecase.UseCaseScriptError, "widget " + repr(self.widget) + " is not visible at the moment, cannot simulate event " + repr(self.name)
            
# Some widgets have state. We note every change but allow consecutive changes to
# overwrite each other. Assume that if the state is set programatically the widget won't be in focus
class StateChangeEvent(GtkEvent):
    def getRecordSignal(self):
        return "changed"
    def isStateChange(self):
        return True
    def shouldRecord(self, *args):
        return self.widget.is_focus()
    def generate(self, argumentString):
        self.widget.grab_focus()
        self.generateStateChange(argumentString)
    def _outputForScript(self, *args):
        return self.name + " " + self.getStateDescription()
        
class EntryEvent(StateChangeEvent):
    def getStateDescription(self):
        return self.widget.get_text()
    def generateStateChange(self, argumentString):
        self.widget.set_text(argumentString)

class ActivateEvent(StateChangeEvent):
    def __init__(self, name, widget, relevantState):
        StateChangeEvent.__init__(self, name, widget)
        self.relevantState = relevantState
    def getRecordSignal(self):
        return "toggled"
    def shouldRecord(self, *args):
        return self.widget.is_focus() and self.widget.get_active() == self.relevantState
    def _outputForScript(self, *args):
        return self.name
    def getStateDescription(self):
        return self.name
    def generateStateChange(self, argumentString):
        self.widget.set_active(self.relevantState)

class TreeSelectionEvent(StateChangeEvent):
    def __init__(self, name, widget, indexer):
        self.selection = widget
        StateChangeEvent.__init__(self, name, widget.get_tree_view())
        self.indexer = indexer
    def connectRecord(self, method):
        self.selection.connect("changed", method, self)
    def getStateDescription(self):
        return string.join(self.findSelectedPaths(), ",")
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
    
class ResponseEvent(SignalEvent):
    def __init__(self, name, widget, responseId):
        SignalEvent.__init__(self, name, widget, "response")
        self.responseId = responseId
    def shouldRecord(self, widget, responseId, *args):
        return self.responseId == responseId
    def generate(self, argumentString):
        self.widget.emit(self.signalName, self.responseId)

class DeletionEvent(SignalEvent):
    anyWindowingEvent = None
    def __init__(self, name, widget, signalName):
        SignalEvent.__init__(self, name, widget, signalName)
        self.captureWindowingEvents()
    def captureWindowingEvents(self):
        # Signals often need to be emitted with a corresponding event.
        # This is very hard to fake. The only way I've found is to seize a random event
        # and use that... this is not foolproof...
        if not self.anyWindowingEvent:
            try:
                self.anyEventHandler = self.widget.connect("event", self.storeWindowingEvent)
            except TypeError:
                pass
    def storeWindowingEvent(self, widget, event, *args):
        DeletionEvent.anyWindowingEvent = event
        self.widget.disconnect(self.anyEventHandler)
    def generate(self, argumentString):
        # Hack - may not work everywhere. Can't find out how to programatically delete windows and still
        # be able to respond to the deletion...
        self.widget.emit("delete_event", self.anyWindowingEvent)
    
class NotebookPageChangeEvent(SignalEvent):
    def __init__(self, name, widget):
        SignalEvent.__init__(self, name, widget, "switch-page")
    def _outputForScript(self, page, page_num, *args):
        newPage = self.widget.get_nth_page(page_num)
        return self.name + " " + self.widget.get_tab_label_text(newPage)
    def generate(self, argumentString):
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
    def generate(self, argumentString):
        path = self.indexer.string2path(argumentString)
        self.widget.emit(self.signalName, path, self.indexer.column)

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
            checkEvent = ActivateEvent(checkChangeName, button, True)
            self._addEventToScripts(checkEvent)
            if uncheckDescription:
                uncheckChangeName = self.standardName(uncheckDescription)
                uncheckEvent = ActivateEvent(uncheckChangeName, button, False)
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
        buttonbox.pack_start(existingbox, expand=False, fill=False)
        newbox = gtk.HBox()
        self.addNewButton(newbox)
        self.addStopControls(newbox, existingbox)
        buttonbox.pack_start(newbox, expand=False, fill=False)
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
        buttonbox.pack_start(label, expand=False, fill=False)
        for fileName in files:
            replayScript = usecase.ReplayScript(fileName)
            self.addShortcutButton(buttonbox, replayScript)
        label.show()
        return buttonbox
    def addNewButton(self, buttonbox):
        newButton = gtk.Button()
        newButton.set_use_underline(1)
        newButton.set_label("_New")
        self.connect("create new shortcut", "clicked", newButton, self.createShortcut, None, buttonbox)
        newButton.show()
        buttonbox.pack_start(newButton, expand=False, fill=False)
    def addShortcutButton(self, buttonbox, replayScript):
        button = gtk.Button()
        buttonName = replayScript.getShortcutName()
        button.set_use_underline(1)
        button.set_label(buttonName)
        self.connect(buttonName.lower(), "clicked", button, self.replayShortcut, None, replayScript)
        firstCommand = replayScript.commands[0]
        if self.replayer.findCommandName(firstCommand):
            button.show()
            self.recorder.registerShortcut(replayScript)
        self.commandButtons.append((replayScript, button))
        buttonbox.pack_start(button, expand=False, fill=False)
    def addStopControls(self, buttonbox, existingbox):
        label = gtk.Label("Recording shortcut named:")
        buttonbox.pack_start(label, expand=False, fill=False)
        entry = gtk.Entry()
        self.registerEntry(entry, "set shortcut name to")
        buttonbox.pack_start(entry, expand=False, fill=False)
        stopButton = gtk.Button()
        stopButton.set_use_underline(1)
        stopButton.set_label("S_top")
        self.connect("stop recording", "clicked", stopButton, self.stopRecording, None, label, entry, buttonbox, existingbox)
        self.recorder.blockTopLevel("stop recording")
        self.recorder.blockTopLevel("set shortcut name to")
        buttonbox.pack_start(stopButton, expand=False, fill=False)
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
        newScriptName = self.getShortcutFileName(buttonName.replace("_", "#")) # Save 'real' _ (mnemonics9 from being replaced in file name ...
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
            event.connectRecord(self.recorder.writeEvent)
    def _createSignalEvent(self, signalName, eventName, widget, argumentParseData):
        if signalName == "delete_event":
            return DeletionEvent(eventName, widget, signalName)
        if signalName == "response":
            return ResponseEvent(eventName, widget, argumentParseData)
        elif isinstance(widget, gtk.TreeView):
            return TreeViewSignalEvent(eventName, widget, signalName, argumentParseData)
        else:
            return SignalEvent(eventName, widget, signalName)

# Use the GTK idle handlers instead of a separate thread for replay execution
class UseCaseReplayer(usecase.UseCaseReplayer):
     def executeCommandsInBackground(self):
         idle_add(self.runNextCommand)
