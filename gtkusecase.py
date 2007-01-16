
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
from sets import Set

# Abstract Base class for all GTK events
class GtkEvent(usecase.UserEvent):
    def __init__(self, name, widget):
        usecase.UserEvent.__init__(self, name)
        self.widget = widget
        self.programmaticChange = False
        self.changeMethod = self.getRealMethod(self.getChangeMethod())
        if self.changeMethod:
            allChangeMethods = [ self.changeMethod ] + self.getProgrammaticChangeMethods()
            for method in allChangeMethods:
                self.interceptMethod(method)
    def interceptMethod(self, method):
        if isinstance(method, MethodIntercept):
            method.addEvent(self)
        else:
            setattr(self.getSelf(method), method.__name__, MethodIntercept(method, self))
    def getSelf(self, method):
        # seems to be different for built-in and bound methods
        try:
            return method.im_self
        except AttributeError:
            return method.__self__
    def getRealMethod(self, method):
        if isinstance(method, MethodIntercept):
            return method.method
        else:
            return method
    def getChangeMethod(self):
        pass
    def getProgrammaticChangeMethods(self):
        return []
    def getRecordSignal(self):
        pass
    def connectRecord(self, method):
        self.widget.connect(self.getRecordSignal(), method, self)
    def outputForScript(self, widget, *args):
        return self._outputForScript(*args)
    def shouldRecord(self, *args):
        return not self.programmaticChange and self.getProperty("visible")
    def _outputForScript(self, *args):
        return self.name
    def getProperty(self, property):
        try:
            return self.widget.get_property(property)
        except TypeError:
            # Some widgets don't support this in PyGTK 2.4. Should remove this when we have at least 2.6
            return True
    def generate(self, argumentString):
        if not self.getProperty("visible"):
            raise usecase.UseCaseScriptError, "widget " + repr(self.widget) + \
                  " is not visible at the moment, cannot simulate event " + repr(self.name)

        if not self.getProperty("sensitive"):
            raise usecase.UseCaseScriptError, "widget " + repr(self.widget) + \
                  " is not sensitive to input at the moment, cannot simulate event " + repr(self.name)

        args = self.getGenerationArguments(argumentString)
        self.changeMethod(*args)    
        
            
# Generic class for all GTK events due to widget signals. Many won't be able to use this, however
class SignalEvent(GtkEvent):
    def __init__(self, name, widget, signalName):
        GtkEvent.__init__(self, name, widget)
        self.signalName = signalName
    def getRecordSignal(self):
        return self.signalName
    def getChangeMethod(self):
        return self.widget.emit
    def getGenerationArguments(self, argumentString):
        return [ self.signalName ] + self.getEmissionArgs(argumentString)
    def getEmissionArgs(self, argumentString):
        return []

class MethodIntercept:
    def __init__(self, method, event):
        self.method = method
        self.events = [ event ]
    def addEvent(self, event):
        self.events.append(event)
    def __call__(self, *args, **kwds):
        for event in self.events:
            event.programmaticChange = True
        retVal = apply(self.method, args, kwds)
        for event in self.events:
            event.programmaticChange = False
        return retVal

# Some widgets have state. We note every change but allow consecutive changes to
# overwrite each other. Assume that if the state is set programatically the widget won't be in focus
class StateChangeEvent(GtkEvent):
    def getRecordSignal(self):
        return "changed"
    def isStateChange(self):
        return True
    def shouldRecord(self, *args):
        return GtkEvent.shouldRecord(self, *args) and self.eventIsRelevant()
    def eventIsRelevant(self):
        return True
    def getGenerationArguments(self, argumentString):
        return [ self.getStateChangeArgument(argumentString) ]
    def getStateChangeArgument(self, argumentString):
        return argumentString
    def _outputForScript(self, *args):
        return self.name + " " + self.getStateDescription(*args)
        
class EntryEvent(StateChangeEvent):
    def getStateDescription(self, *args):
        return self.widget.get_text()
    def getChangeMethod(self):
        return self.widget.set_text

class ActivateEvent(StateChangeEvent):
    def __init__(self, name, widget, relevantState):
        StateChangeEvent.__init__(self, name, widget)
        self.relevantState = relevantState
    def getRecordSignal(self):
        return "toggled"
    def eventIsRelevant(self):
        return self.widget.get_active() == self.relevantState
    def _outputForScript(self, *args):
        return self.name
    def getStateChangeArgument(self, argumentString):
        return self.relevantState
    def getChangeMethod(self):
        return self.widget.set_active
    def getProgrammaticChangeMethods(self):
        return [ self.widget.toggled ]

class NotebookPageChangeEvent(StateChangeEvent):
    def getChangeMethod(self):
        return self.widget.set_current_page
    def getRecordSignal(self):
        return "switch-page"
    def eventIsRelevant(self):
        # Don't record if there aren't any pages
        return self.widget.get_current_page() != -1
    def getStateDescription(self, ptr, pageNum, *args):
        newPage = self.widget.get_nth_page(pageNum)
        return self.widget.get_tab_label_text(newPage)
    def getStateChangeArgument(self, argumentString):
        for i in range(len(self.widget.get_children())):
            page = self.widget.get_nth_page(i)
            if self.widget.get_tab_label_text(page) == argumentString:
                return i
        raise usecase.UseCaseScriptError, "Could not find page " + argumentString + " in '" + self.name + "'"

class TreeViewEvent(GtkEvent):
    def __init__(self, name, widget, indexer):
        GtkEvent.__init__(self, name, widget)
        self.indexer = indexer
    def _outputForScript(self, iterOrPath, *args):
        return self.name + " " + self.indexer.path2string(iterOrPath)
    def getGenerationArguments(self, argumentString):
        return [ self.indexer.string2path(argumentString) ] + self.getTreeViewArgs()
    def getTreeViewArgs(self):
        return []

class RowExpandEvent(TreeViewEvent):
    def getChangeMethod(self):
        return self.widget.expand_row
    def getProgrammaticChangeMethods(self):
        return [ self.widget.expand_to_path ]
    def getRecordSignal(self):
        return "row-expanded"
    def getTreeViewArgs(self):
        # don't open all subtree parts
        return [ False ]

class RowCollapseEvent(TreeViewEvent):
    def getChangeMethod(self):
        return self.widget.collapse_row
    def getRecordSignal(self):
        return "row-collapsed"

class RowActivationEvent(TreeViewEvent):
    def getChangeMethod(self):
        return self.widget.row_activated
    def getRecordSignal(self):
        return "row-activated"
    def generate(self, argumentString):
        # clear the selection before generating as that's what the real event does
        self.widget.get_selection().unselect_all()
        TreeViewEvent.generate(self, argumentString)
    def getTreeViewArgs(self):
        return [ self.indexer.column ]
    def implies(self, prevLine, prevEvent):
        if not isinstance(prevEvent, TreeSelectionEvent):
            return False
        return self.widget.get_selection() is prevEvent.widget

# Remember: self.widget is not really a widget here,
# since gtk.CellRenderer is not a gtk.Widget.
class CellToggleEvent(TreeViewEvent):
    def getChangeMethod(self):
        return self.widget.emit
    def getRecordSignal(self):
        return "toggled"
    def getGenerationArguments(self, argumentString):
        path = TreeViewEvent.getGenerationArguments(self, argumentString)[0]
        # For some reason, the treemodel access methods I use
        # don't like the (3,0) list-type paths created by
        # the above call, so we'll have to manually create a
        # '3:0' string-type path instead ...
        strPath = ""
        for i in xrange(0, len(path)):
            strPath += str(path[i])
            if i < len(path) - 1:
                strPath += ":"
        return [ "toggled", strPath ]
    
class TreeSelectionEvent(StateChangeEvent):
    def __init__(self, name, widget, indexer):
        self.indexer = indexer
        # cache these before calling base class constructor, or they get intercepted...
        self.unselect_path = widget.unselect_path
        self.select_path = widget.select_path
        self.prevSelected = []
        StateChangeEvent.__init__(self, name, widget)
    def getChangeMethod(self):
        return self.widget.select_path
    def getModels(self):
        model = self.widget.get_tree_view().get_model()
        if isinstance(model, gtk.TreeModelFilter):
            return model, model.get_model()
        else:
            return None, model
    def getProgrammaticChangeMethods(self):
        modelFilter, realModel = self.getModels()
        methods = [ self.widget.unselect_all, self.widget.select_iter, self.widget.unselect_iter, \
                         self.widget.unselect_path, self.widget.get_tree_view().row_activated, \
                         self.widget.get_tree_view().collapse_row, realModel.remove, realModel.clear ]
        if modelFilter:
            methods.append(realModel.set_value) # changing visibility column can change selection
        return methods
    def getStateDescription(self, *args):
        return self._getStateDescription(storeSelected=True)
    def selectedPreviously(self, path1, path2):
        selPrev1 = path1 in self.prevSelected
        selPrev2 = path2 in self.prevSelected
        if selPrev1 and not selPrev2:
            return -1
        elif selPrev2 and not selPrev1:
            return 1
        elif selPrev1 and selPrev2:
            index1 = self.prevSelected.index(path1)
            index2 = self.prevSelected.index(path2)
            return cmp(index1, index2)
        else:
            return 0
    def _getStateDescription(self, storeSelected=False):
        newSelected = self.findSelectedPaths()
        newSelected.sort(self.selectedPreviously)
        if storeSelected:
            self.prevSelected = newSelected
        return string.join(newSelected, ",")
    def findSelectedPaths(self):
        paths = []
        self.widget.selected_foreach(self.addSelPath, paths)
        return paths
    def addSelPath(self, model, path, iter, paths):
        paths.append(self.indexer.path2string(path))
    def getStateChangeArgument(self, argumentString):
        return map(self.indexer.string2path, argumentString.split(","))
    def generate(self, argumentString):
        oldSelected = self.findSelectedPaths()
        newSelected = self.parsePathNames(argumentString)
        toUnselect, toSelect = self.findChanges(oldSelected, newSelected)
        if len(toSelect) > 0:
            self.widget.unseen_changes = True
        for pathName in toUnselect:
            self.unselect_path(self.indexer.string2path(pathName))
        if len(toSelect) > 0:
            delattr(self.widget, "unseen_changes")
        for pathName in newSelected:
            self.select_path(self.indexer.string2path(pathName))
    def findChanges(self, oldSelected, newSelected):
        if oldSelected == newSelected: # re-selecting should be recorded as clear-and-reselect, not do nothing
            return oldSelected, newSelected
        else:
            oldSet = Set(oldSelected)
            newSet = Set(newSelected)
            if oldSet.issuperset(newSet):
                return oldSet.difference(newSet), []
            else:
                index = self.findFirstDifferent(oldSelected, newSelected)
                return oldSelected[index:], newSelected[index:]
    def findFirstDifferent(self, oldSelected, newSelected):
        for index in range(len(oldSelected)):
            if index >= len(newSelected):
                return index
            if oldSelected[index] != newSelected[index]:
                return index
        return len(oldSelected)
    def parsePathNames(self, argumentString):
        if len(argumentString) == 0:
            return []
        else:
            return argumentString.split(",")
    def implies(self, prevLine, prevEvent):
        if not isinstance(prevEvent, TreeSelectionEvent) or not prevLine.startswith(self.name):
            return False
        prevStateDesc = prevLine[len(self.name) + 1:]
        currStateDesc = self._getStateDescription()
        if len(currStateDesc) > len(prevStateDesc):
            return currStateDesc.startswith(prevStateDesc)
        elif len(currStateDesc) > 0:
            oldSet = Set(self.parsePathNames(prevStateDesc))
            newSet = Set(self.parsePathNames(currStateDesc))
            return oldSet.issuperset(newSet)
        else:
            return False # always assume deselecting everything marks the beginning of a new conceptual action
                         
    
class ResponseEvent(SignalEvent):
    def __init__(self, name, widget, responseId):
        SignalEvent.__init__(self, name, widget, "response")
        self.responseId = responseId
    def shouldRecord(self, widget, responseId, *args):
        return self.responseId == responseId
    def getEmissionArgs(self, argumentString):
        return [ self.responseId ]

class DeletionEvent(GtkEvent):
    def __init__(self, name, widget, method):
        GtkEvent.__init__(self, name, widget)
        self.method = method
        self.recordMethod = None
    def getRecordSignal(self):
        return "delete-event"
    def connectRecord(self, method):
        GtkEvent.connectRecord(self, method)
        self.recordMethod = method
    def generate(self, argumentString):
        if self.recordMethod:
            self.recordMethod(self.widget, None, self)
        if not self.method(self.widget, None):
            self.widget.destroy()

# Class to provide domain-level lookup for rows in a tree. Convert paths to strings and back again
class TreeModelIndexer:
    def __init__(self, model, column, valueId):
        self.model = model
        self.column = column
        self.valueId = valueId
    def path2string(self, iterOrPath):
        iter = self.getIter(iterOrPath)
        return self.model.get_value(iter, self.valueId)
    def getIter(self, iterOrPath):
        try:
            return self.model.get_iter(iterOrPath)
        except TypeError:
            return iterOrPath
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
  
# A utility class to set and get the indices of options in radio button groups.
class RadioGroupIndexer:
    def __init__(self, listOfButtons):
        self.buttons = listOfButtons
    def getActiveIndex(self):
        for i in xrange(0, len(self.buttons)):
            if self.buttons[i].get_active():
                return i
    def setActiveIndex(self, index):
        self.buttons[index].set_active(True)

class ScriptEngine(usecase.ScriptEngine):
    def __init__(self, logger = None, enableShortcuts = 0):
        usecase.ScriptEngine.__init__(self, logger, enableShortcuts)
        self.commandButtons = []
    def connect(self, eventName, signalName, widget, method = None, argumentParseData = None, *data):
        if self.active():
            stdName = self.standardName(eventName)
            signalEvent = self._createSignalEvent(stdName, signalName, widget, method, argumentParseData)
            self._addEventToScripts(signalEvent)
        if method:
            widget.connect(signalName, method, *data)
    def monitor(self, eventName, selection, argumentParseData = None):
        if self.active():
            stdName = self.standardName(eventName)
            stateChangeEvent = TreeSelectionEvent(stdName, selection, argumentParseData)
            self._addEventToScripts(stateChangeEvent)
    def monitorExpansion(self, treeView, expandDescription, collapseDescription = "", argumentParseData = None):
        if self.active():
            expandName = self.standardName(expandDescription)
            expandEvent = RowExpandEvent(expandName, treeView, argumentParseData)
            self._addEventToScripts(expandEvent)
            if collapseDescription:
                collapseName = self.standardName(collapseDescription)
                collapseEvent = RowCollapseEvent(collapseName, treeView, argumentParseData)
                self._addEventToScripts(collapseEvent)
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
    def monitorNotebook(self, notebook, description):
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
        tmpFileName = self.getTmpShortcutName()
        if os.path.isfile(tmpFileName):
            os.rename(tmpFileName, newScriptName)
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
    def _createSignalEvent(self, eventName, signalName, widget, method, argumentParseData):
        if signalName == "delete_event":
            return DeletionEvent(eventName, widget, method)
        if signalName == "response":
            return ResponseEvent(eventName, widget, argumentParseData)
        elif signalName == "row_activated":
            return RowActivationEvent(eventName, widget, argumentParseData)
        elif isinstance(widget, gtk.CellRendererToggle) and signalName == "toggled":
            return CellToggleEvent(eventName, widget, argumentParseData)
        else:
            return SignalEvent(eventName, widget, signalName)

# Use the GTK idle handlers instead of a separate thread for replay execution
class UseCaseReplayer(usecase.UseCaseReplayer):
     def executeCommandsInBackground(self):
         idle_add(self.runNextCommand)
