
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

import usecase, gtklogger, gtktreeviewextract, gtk, gobject, os, re, logging, types, sys
from ndict import seqdict

# We really need our ConfigParser to be ordered, copied the one from 2.6 into the repository
if sys.version[:2] >= (2, 6):
    from ConfigParser import ConfigParser
else:
    from ConfigParser26 import ConfigParser

PRIORITY_PYUSECASE_IDLE = gtklogger.PRIORITY_PYUSECASE_IDLE
version = usecase.version

# Useful to have at module level as can't really be done externally
def createShortcutBar(uiMapFiles=[]):
    if not usecase.scriptEngine:
        usecase.scriptEngine = ScriptEngine(universalLogging=False, uiMapFiles=uiMapFiles)
    elif uiMapFiles:
        usecase.scriptEngine.addUiMapFiles(uiMapFiles)
    return usecase.scriptEngine.createShortcutBar()


# Abstract Base class for all GTK events
class GtkEvent(usecase.UserEvent):
    def __init__(self, name, widget, *args):
        usecase.UserEvent.__init__(self, name)
        self.widget = widget
        self.interceptMethod(self.widget.stop_emission, EmissionStopIntercept)
        self.interceptMethod(self.widget.emit_stop_by_name, EmissionStopIntercept)
        self.programmaticChange = False
        self.stopEmissionMethod = None
        self.changeMethod = self.getRealMethod(self.getChangeMethod())
        if self.changeMethod:
            allChangeMethods = [ self.changeMethod ] + self.getProgrammaticChangeMethods()
            for method in allChangeMethods:
                self.interceptMethod(method, ProgrammaticChangeIntercept)

    def interceptMethod(self, method, interceptClass):
        if isinstance(method, MethodIntercept):
            method.addEvent(self)
        else:
            setattr(self.getSelf(method), method.__name__, interceptClass(method, self))

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

    def getProgrammaticChangeMethods(self):
        return []

    def setProgrammaticChange(self, val, *args, **kwargs):
        self.programmaticChange = val

    @classmethod
    def getAssociatedSignatures(cls, widget):
        return set([ cls.getAssociatedSignal(widget) ])
    @classmethod
    def getAssociatedSignal(cls, widget):
        return cls.signalName

    def getRecordSignal(self):
        return self.signalName

    def getUiMapSignature(self):
        return self.getRecordSignal()

    def connectRecord(self, method):
        self._connectRecord(self.widget, method)

    def _connectRecord(self, gobj, method):
        handler = gobj.connect(self.getRecordSignal(), method, self)
        gobj.connect(self.getRecordSignal(), self.stopEmissions)
        return handler

    def outputForScript(self, widget, *args):
        return self._outputForScript(*args)

    def stopEmissions(self, *args):
        if self.stopEmissionMethod:
            self.stopEmissionMethod(self.getRecordSignal())
            self.stopEmissionMethod = None

    def shouldRecord(self, *args):
        return not self.programmaticChange and self.widget.get_property("visible")

    def _outputForScript(self, *args):
        return self.name

    def checkWidgetStatus(self):
        if not self.widget.get_property("visible"):
            raise usecase.UseCaseScriptError, "widget '" + self.widget.get_name() + \
                  "' is not visible at the moment, cannot simulate event " + repr(self.name)

        if not self.widget.get_property("sensitive"):
            raise usecase.UseCaseScriptError, "widget '" + self.widget.get_name() + \
                  "' is not sensitive to input at the moment, cannot simulate event " + repr(self.name)

    def generate(self, argumentString):
        self.checkWidgetStatus()
        args = self.getGenerationArguments(argumentString)
        self.changeMethod(*args)

        
# Generic class for all GTK events due to widget signals. Many won't be able to use this, however
class SignalEvent(GtkEvent):
    def __init__(self, name, widget, signalName=None):
        GtkEvent.__init__(self, name, widget)
        if signalName:
            self.signalName = signalName
        # else we assume it's defined at the class level
    @classmethod
    def getAssociatedSignal(cls, widget):
        if hasattr(cls, "signalName"):
            return cls.signalName
        elif isinstance(widget, gtk.Button) or isinstance(widget, gtk.ToolButton):
            return "clicked"
        elif isinstance(widget, gtk.Entry):
            return "activate"
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

class ProgrammaticChangeIntercept(MethodIntercept):
    def __call__(self, *args, **kwds):
        # Allow for possibly nested programmatic changes, observation can have knock-on effects
        eventsToBlock = filter(lambda event: not event.programmaticChange, self.events)
        for event in eventsToBlock:
            event.setProgrammaticChange(True, *args, **kwds)
        retVal = apply(self.method, args, kwds)
        for event in eventsToBlock:
            event.setProgrammaticChange(False)
        return retVal

class EmissionStopIntercept(MethodIntercept):
    def __call__(self, sigName):
        stdSigName = sigName.replace("_", "-")
        for event in self.events:
            if stdSigName == event.getRecordSignal():
                event.stopEmissionMethod = self.method

# Some widgets have state. We note every change but allow consecutive changes to
# overwrite each other. 
class StateChangeEvent(GtkEvent):
    signalName = "changed"
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

class PaneDragEvent(StateChangeEvent):
    signalName = "notify::position"
    def __init__(self, name, widget, *args):
        StateChangeEvent.__init__(self, name, widget, *args)
        widget.connect("notify::max-position", self.changeMaxMin)
        widget.connect("notify::min-position", self.changeMaxMin)
        self.prevState = ""

    def setProgrammaticChange(self, val, *args, **kwargs):
        if val:
            self.programmaticChange = val

    def changeMaxMin(self, *args):
        if self.totalSpace() > 0:
            self.prevState = self.getStateDescription()

    def shouldRecord(self, *args):
        ret = StateChangeEvent.shouldRecord(self, *args)
        self.programmaticChange = False
        return ret

    def eventIsRelevant(self):
        if self.totalSpace() == 0:
            return False
        
        newState = self.getStateDescription()
        if newState != self.prevState:
            self.prevPos = newState
            return True
        else:
            return False

    def totalSpace(self):
        return self.widget.get_property("max-position") - self.widget.get_property("min-position")

    def getStatePercentage(self):
        return float(100 * (self.widget.get_position() - self.widget.get_property("min-position"))) / self.totalSpace()

    def getStateDescription(self, *args):
        return str(int(self.getStatePercentage() + 0.5)) + "% of the space"

    def getStateChangeArgument(self, argumentString):
        percentage = int(argumentString.split()[0][:-1])
        return int(float(self.totalSpace() * percentage) / 100 + 0.5) + self.widget.get_property("min-position")

    def getProgrammaticChangeMethods(self):
        return [ self.widget.check_resize ]

    def getChangeMethod(self):
        return self.widget.set_position

    
class ActivateEvent(StateChangeEvent):
    signalName = "toggled"
    def __init__(self, name, widget, relevantState):
        StateChangeEvent.__init__(self, name, widget)
        self.relevantState = self.parseState(relevantState)

    def parseState(self, relevantState):
        if type(relevantState) == types.StringType:
            return relevantState == "true"
        else:
            return relevantState

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
    
    def getUiMapSignature(self):
        return self.getRecordSignal() + "." + repr(self.relevantState)

    @classmethod
    def getAssociatedSignatures(cls, widget):
        # Radio buttons can't be unchecked directly
        if isinstance(widget, gtk.RadioButton):
            return [ cls.signalName + ".true" ]
        else:
            return [ cls.signalName + ".true", cls.signalName + ".false" ]


class MenuActivateEvent(ActivateEvent):
    def generate(self, *args):
        self.checkWidgetStatus()
        self.widget.emit("activate-item")


class NotebookPageChangeEvent(StateChangeEvent):
    signalName = "switch-page"
    def getChangeMethod(self):
        return self.widget.set_current_page
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
        raise usecase.UseCaseScriptError, "'" + self.name + "' failed : Could not find page '" + \
            argumentString + "' in the " + self.widget.get_name().replace("Gtk", "") + "." 

# Confusingly different signals used in different circumstances here.
class MenuItemSignalEvent(SignalEvent):
    signalName = "activate"
    def getGenerationArguments(self, *args):
        return [ "activate-item" ]

class TreeColumnClickEvent(SignalEvent):
    signalName = "clicked"
    def __init__(self, name, widget, column):
        self.column = column
        SignalEvent.__init__(self, name, widget)

    def connectRecord(self, method):
        self._connectRecord(self.column, method)

    def getUiMapSignature(self):
        return self.getRecordSignal() + "." + getColumnName(self.column).lower()

    def getChangeMethod(self):
        return self.column.emit

    @classmethod
    def getAssociatedSignatures(cls, widget):
        signatures = []
        for column in widget.get_columns():
            if column.get_clickable():
                signatures.append(cls.signalName + "." + getColumnName(column).lower())
        return signatures


class TreeViewEvent(GtkEvent):
    def __init__(self, name, widget, indexer, *args):
        GtkEvent.__init__(self, name, widget)
        self.indexer = indexer
    def _outputForScript(self, iter, *args):
        return self.name + " " + self.indexer.iter2string(iter)
    def _outputForScriptFromPath(self, path, *args):
        return self.name + " " + self.indexer.path2string(path)
    def getGenerationArguments(self, argumentString):
        return [ self.indexer.string2path(argumentString) ] + self.getTreeViewArgs()
    def getTreeViewArgs(self):
        return []
   
class RowExpandEvent(TreeViewEvent):
    signalName = "row-expanded"
    def getChangeMethod(self):
        return self.widget.expand_row
    def getProgrammaticChangeMethods(self):
        return [ self.widget.expand_to_path, self.widget.expand_all ]
    def getTreeViewArgs(self):
        # don't open all subtree parts
        return [ False ]

class RowCollapseEvent(TreeViewEvent):
    signalName = "row-collapsed"
    def getChangeMethod(self):
        return self.widget.collapse_row

    def implies(self, prevLine, prevEvent, view, iter, path, *args):
        if not isinstance(prevEvent, TreeSelectionEvent):
            return False

        if self.widget is not prevEvent.widget:
            return False

        for deselectName in prevEvent.prevDeselections:
            deselectPath = self.indexer.string2path(deselectName)
            if len(deselectPath) > len(path) and deselectPath[:len(path)] == path:
                return True
        return False


class RowActivationEvent(TreeViewEvent):
    signalName = "row-activated"
    def getChangeMethod(self):
        return self.widget.row_activated

    def _outputForScript(self, path, *args):
        return self._outputForScriptFromPath(path)

    def generate(self, argumentString):
        # clear the selection before generating as that's what the real event does
        self.widget.get_selection().unselect_all()
        TreeViewEvent.generate(self, argumentString)
        
    def getTreeViewArgs(self):
        # We don't care which column right now
        return [ self.widget.get_column(0) ]

    def implies(self, prevLine, prevEvent, *args):
        if not isinstance(prevEvent, TreeSelectionEvent):
            return False

        return self.widget is prevEvent.widget


class ClickEvent(SignalEvent):
    def shouldRecord(self, widget, event, *args):
        return SignalEvent.shouldRecord(self, widget, event, *args) and event.button == self.buttonNumber

    def getEmissionArgs(self, argumentString):
        area = self.getAreaToClick(argumentString)
        event = gtk.gdk.Event(self.eventType)
        event.x = float(area.x) + float(area.width) / 2
        event.y = float(area.y) + float(area.height) / 2
        event.button = self.buttonNumber
        return [ event ]

    def getAreaToClick(self, *args):
        return self.widget.get_allocation()


class LeftClickEvent(ClickEvent):
    signalName = "button-release-event" # Usually when left-clicking things (like buttons) what matters is releasing
    buttonNumber = 1
    eventType = gtk.gdk.BUTTON_RELEASE

class RightClickEvent(ClickEvent):
    signalName = "button-press-event"
    buttonNumber = 3
    eventType = gtk.gdk.BUTTON_PRESS


class RowRightClickEvent(RightClickEvent):
    def __init__(self, name, widget, indexer):
        RightClickEvent.__init__(self, name, widget)
        self.indexer = indexer
        
    def _outputForScript(self, event, *args):
        pathInfo = self.widget.get_path_at_pos(int(event.x), int(event.y))
        return self.name + " " + self.indexer.path2string(pathInfo[0])

    def getAreaToClick(self, argumentString):
        path = self.indexer.string2path(argumentString)
        return self.widget.get_cell_area(path, self.widget.get_column(0))
        

class CellEvent(TreeViewEvent):
    def __init__(self, name, widget, cellRenderer, indexer, property):
        self.cellRenderer = cellRenderer
        self.extractor = gtktreeviewextract.getExtractor(cellRenderer, property)
        TreeViewEvent.__init__(self, name, widget, indexer)

    def getValue(self, renderer, path, *args):
        model = self.widget.get_model()
        iter = model.get_iter(path)
        return self.extractor.getValue(model, iter)

    def getChangeMethod(self):
        return self.cellRenderer.emit

    def connectRecord(self, method):
        self._connectRecord(self.cellRenderer, method)

    def _outputForScript(self, path, *args):
        return self.name + " " + self.indexer.path2string(path)

    def getColumnName(self):
        for column in self.widget.get_columns():
            if self.cellRenderer in column.get_cell_renderers():
                return getColumnName(column)

    def getPathAsString(self, path):
        # For some reason, the treemodel access methods I use
        # don't like the (3,0) list-type paths created by
        # the above call, so we'll have to manually create a
        # '3:0' string-type path instead ...
        strPath = ""
        for i in xrange(0, len(path)):
            strPath += str(path[i])
            if i < len(path) - 1:
                strPath += ":"
        return strPath


class CellToggleEvent(CellEvent):
    signalName = "toggled"
    def __init__(self, name, widget, cellRenderer, indexer, relevantState):
        self.relevantState = relevantState
        CellEvent.__init__(self, name, widget, cellRenderer, indexer, "active")        

    def shouldRecord(self, *args):
        return TreeViewEvent.shouldRecord(self, *args) and self.getValue(*args) == self.relevantState
    
    def getUiMapSignature(self):
        return self.getRecordSignal() + "." + self.getColumnName() + "." + repr(self.relevantState)

    @classmethod
    def getAssociatedSignatures(cls, widget):
        signatures = []
        for column in widget.get_columns():
            for renderer in column.get_cell_renderers():
                if isinstance(renderer, gtk.CellRendererToggle):
                    rootName = cls.signalName + "." + getColumnName(column).lower()
                    signatures.append(rootName + ".true")
                    signatures.append(rootName + ".false")
        return signatures

    def getGenerationArguments(self, argumentString):
        path = TreeViewEvent.getGenerationArguments(self, argumentString)[0]
        return [ self.signalName, self.getPathAsString(path) ]


class CellEditEvent(CellEvent):
    signalName = "edited"
    def __init__(self, *args, **kw):
        CellEvent.__init__(self, property="text", *args, **kw)

    def shouldRecord(self, renderer, path, new_text, *args):
        value = self.getValue(renderer, path)
        return TreeViewEvent.shouldRecord(self, renderer, path, *args) and new_text != str(value)
    
    def _connectRecord(self, widget, method):
        # Push our way to the front of the queue
        # We need to be able to tell when things have changed
        connectInfo = gtktreeviewextract.cellRendererConnectInfo.get(widget, [])
        allArgs = [ info[1] for info in connectInfo ]
        for handler, args in connectInfo:
            widget.disconnect(handler)
        CellEvent._connectRecord(self, widget, method)
        for args in allArgs:
            widget.connect(*args)

    def getUiMapSignature(self):
        return self.getRecordSignal() + "." + self.getColumnName()

    def _outputForScript(self, path, new_text, *args):
        return CellEvent._outputForScript(self, path, new_text, *args) + " = " + new_text

    @classmethod
    def getAssociatedSignatures(cls, widget):
        signatures = []
        for column in widget.get_columns():
            for renderer in column.get_cell_renderers():
                if isinstance(renderer, gtk.CellRendererText) and renderer.get_property("editable"):
                    signatures.append(cls.signalName + "." + getColumnName(column).lower())
        return signatures

    def getGenerationArguments(self, argumentString):
        oldName, newName = argumentString.split(" = ")
        path = TreeViewEvent.getGenerationArguments(self, oldName)[0]
        return [ self.signalName, self.getPathAsString(path), newName ]
    

class DialogEventHandler:      
    def hasUsecaseName(self):
        return not self.name.startswith("Auto.")

    def hasWidgetName(self):
        return "Name=" in self.name

    def superfluousAutoGenerated(self):
        if self.hasUsecaseName():
            return False
        hasWidgetName = self.hasWidgetName() 
        for event, handler, args in self.dialogInfo.get(self.widget):
            if event and (event.hasUsecaseName() or (not hasWidgetName and event.hasWidgetName())):
                return True
        return False

    def connectRecord(self, method):
        handler = self._connectRecord(self.widget, method)
        self.storeHandler(self.widget, handler, self)

    @classmethod
    def storeHandler(cls, widget, handler, event=None, args=()):
        # Dialogs get handled in a special way which leaves them open to duplication...
        cls.dialogInfo.setdefault(widget, []).append((event, handler, args))


# At least on Windows this doesn't seem to happen immediately, but takes effect some time afterwards
# Seems quite capable of generating too many of them also
class FileChooserFolderChangeEvent(DialogEventHandler, StateChangeEvent):
    signalName = "current-folder-changed"
    dialogInfo = {}
    def __init__(self, name, widget, *args):
        self.currentFolder = widget.get_current_folder()
        StateChangeEvent.__init__(self, name, widget)

    def setProgrammaticChange(self, val, filename=None):
        if val:
            self.programmaticChange = val

    def shouldRecord(self, *args):
        if self.superfluousAutoGenerated():
            return False
        hasChanged = self.currentFolder is not None and self.widget.get_current_folder() != self.currentFolder
        self.currentFolder = self.widget.get_current_folder()
        if not hasChanged:
            return False
        ret = StateChangeEvent.shouldRecord(self, *args)
        self.programmaticChange = False
        return ret

    def getProgrammaticChangeMethods(self):
        return [ self.widget.set_filename ]

    def getChangeMethod(self):
        return self.widget.set_current_folder

    def getStateDescription(self, *args):
        return os.path.basename(self.widget.get_current_folder())

    def getStateChangeArgument(self, argumentString):
        if gtklogger.gtk_has_filechooser_bug():
            raise usecase.UseCaseScriptError, "Cannot replay changes of folder in file choosers due to bug in GTK 2.14, fixed in GTK 2.16.3"
        for folder in self.widget.list_shortcut_folders():
            if os.path.basename(folder) == argumentString:
                return folder
        folder = os.path.join(self.widget.get_current_folder(), argumentString)
        if os.path.isdir(folder):
            return folder
        else: 
            raise usecase.UseCaseScriptError, "Cannot find folder '" + argumentString + "' to change to!"

# Base class for selecting a file or typing a file name
class FileChooserFileEvent(DialogEventHandler, StateChangeEvent):
    def __init__(self, name, widget, fileChooser=None):
        self.fileChooser = fileChooser
        if not fileChooser:
            self.fileChooser = widget
        StateChangeEvent.__init__(self, name, widget)
        self.currentName = self.getStateDescription()

    def shouldRecord(self, *args):
        return StateChangeEvent.shouldRecord(self, *args) and not self.superfluousAutoGenerated()

    def eventIsRelevant(self):
        if self.fileChooser.get_filename() is None:
            return False
        return self.currentName != self._getStateDescription()

    def getStateDescription(self, *args):
        self.currentName = self._getStateDescription()
        return self.currentName

    def _getStateDescription(self):
        fileName = self.fileChooser.get_filename()
        if fileName:
            return os.path.basename(fileName)
        else:
            return ""
    
class FileChooserFileSelectEvent(FileChooserFileEvent):
    signalName = "selection-changed"
    dialogInfo = {}
    def getChangeMethod(self):
        return self.fileChooser.select_filename
    
    def getProgrammaticChangeMethods(self):
        return [ self.fileChooser.set_filename ]

    def setProgrammaticChange(self, val, filename=None):
        FileChooserFileEvent.setProgrammaticChange(self, val)
        if val and filename:
            self.currentName = os.path.basename(filename)

    def shouldRecord(self, *args):
        if self.currentName: # once we've got a name, everything is permissible...
            return FileChooserFileEvent.shouldRecord(self, *args)
        else:
            self.currentName = self._getStateDescription()
            return False

    def getStateChangeArgument(self, argumentString):
        path = os.path.join(self.fileChooser.get_current_folder(), argumentString)
        if os.path.exists(path):
            return path
        else:
            raise usecase.UseCaseScriptError, "Cannot select file '" + argumentString + "', no such file in current folder"
    
    @classmethod
    def getAssociatedSignatures(cls, widget):
        if widget.get_property("action") == gtk.FILE_CHOOSER_ACTION_OPEN:
            return [ cls.getAssociatedSignal(widget) ]
        else:
            return []


class FileChooserEntryEvent(FileChooserFileEvent):
    # There is no such signal on FileChooser, but we can pretend...
    # We record by waiting for the dialog to be closed, but we don't want to store that
    signalName = "current-name-changed"
    dialogInfo = {}
    def __init__(self, name, fileChooser, *args):
        FileChooserFileEvent.__init__(self, name, fileChooser)

    def _connectRecord(self, widget, method):
        # Wait for the dialog to be closed before we record
        # We must therefore be first among the handlers so we can record
        # before the dialog close event gets recorded...
        dialog = widget.get_toplevel()
        if dialog is not widget:
            otherHandlers = ResponseEvent.dialogInfo.get(dialog, [])
            for event, handler, args in otherHandlers:
                dialog.disconnect(handler)
        dialog.connect("response", method, self)
        if dialog is not self.widget:
            ResponseEvent.dialogInfo[dialog] = []
            for event, handler, args in otherHandlers:
                if event:
                    event.connectRecord(method)
                else:
                    dialog.connect("response", *args)

    def getChangeMethod(self):
        return self.fileChooser.set_current_name
    
    @classmethod
    def getAssociatedSignatures(cls, widget):
        if widget.get_property("action") == gtk.FILE_CHOOSER_ACTION_SAVE:
            return [ cls.getAssociatedSignal(widget) ]
        else:
            return []


class TreeSelectionEvent(StateChangeEvent):
    def __init__(self, name, widget, selection, indexer):
        self.indexer = indexer
        self.selection = selection
        # cache these before calling base class constructor, or they get intercepted...
        self.unselect_iter = selection.unselect_iter
        self.select_iter = selection.select_iter
        self.prevSelected = []
        self.prevDeselections = []
        StateChangeEvent.__init__(self, name, widget)

    @classmethod
    def getAssociatedSignatures(cls, widget):
        if widget.get_model():
            return [ "changed.selection" ]
        else:
            return []

    def getUiMapSignature(self):
        return "changed.selection"

    def connectRecord(self, method):
        self._connectRecord(self.selection, method)

    def getChangeMethod(self):
        return self.select_iter

    def getModels(self):
        model = self.widget.get_model()
        if isinstance(model, gtk.TreeModelFilter):
            return model, model.get_model()
        else:
            return None, model

    def shouldRecord(self, *args):
        ret = StateChangeEvent.shouldRecord(self, *args)
        if not ret:
            self.getStateDescription() # update internal stores for programmatic changes
        return ret

    def getProgrammaticChangeMethods(self):
        modelFilter, realModel = self.getModels()
        methods = [ self.selection.unselect_all, self.selection.select_all, \
                    self.selection.select_iter, self.selection.unselect_iter, \
                    self.selection.select_path, self.selection.unselect_path,
                    self.widget.set_model, self.widget.row_activated, self.widget.collapse_row,
                    realModel.remove, realModel.clear ]
        if modelFilter:
            methods.append(realModel.set_value) # changing visibility column can change selection
        return methods

    def getStateDescription(self, *args):
        return self._getStateDescription(storeSelected=True)

    def selectedPreviously(self, iter1, iter2):
        selPrev1 = iter1 in self.prevSelected
        selPrev2 = iter2 in self.prevSelected
        if selPrev1 and not selPrev2:
            return -1
        elif selPrev2 and not selPrev1:
            return 1
        elif selPrev1 and selPrev2:
            index1 = self.prevSelected.index(iter1)
            index2 = self.prevSelected.index(iter2)
            return cmp(index1, index2)
        else:
            return 0

    def _getStateDescription(self, storeSelected=False):
        newSelected = self.findSelectedIters()
        newSelected.sort(self.selectedPreviously)
        if storeSelected:
            self.prevDeselections = filter(lambda i: i not in newSelected, self.prevSelected)
            self.prevSelected = newSelected
        return ",".join(newSelected)

    def findSelectedIters(self):
        iters = []
        self.selection.selected_foreach(self.addSelIter, iters)
        return iters

    def addSelIter(self, model, path, iter, iters):
        iters.append(self.indexer.iter2string(iter))
        
    def generate(self, argumentString):
        oldSelected = self.findSelectedIters()
        newSelected = self.parseIterNames(argumentString)
        toUnselect, toSelect = self.findChanges(oldSelected, newSelected)
        if len(toSelect) > 0:
            self.selection.unseen_changes = True
        for iterName in toUnselect:
            self.unselect_iter(self.indexer.string2iter(iterName))
        if len(toSelect) > 0:
            delattr(self.selection, "unseen_changes")
        for iterName in newSelected:
            self.select_iter(self.indexer.string2iter(iterName))
            # In real life there is no way to do this without being in focus, force the focus over
            self.widget.grab_focus()
            
    def findChanges(self, oldSelected, newSelected):
        if oldSelected == newSelected: # re-selecting should be recorded as clear-and-reselect, not do nothing
            return oldSelected, newSelected
        else:
            oldSet = set(oldSelected)
            newSet = set(newSelected)
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

    def parseIterNames(self, argumentString):
        if len(argumentString) == 0:
            return []
        else:
            return argumentString.split(",")

    def implies(self, prevLine, prevEvent, *args):
        if not isinstance(prevEvent, TreeSelectionEvent) or \
               not prevLine.startswith(self.name):
            return False
        prevStateDesc = prevLine[len(self.name) + 1:]
        currStateDesc = self._getStateDescription()
        if len(currStateDesc) > len(prevStateDesc):
            return currStateDesc.startswith(prevStateDesc)
        elif len(currStateDesc) > 0:
            oldSet = set(self.parseIterNames(prevStateDesc))
            newSet = set(self.parseIterNames(currStateDesc))
            return oldSet.issuperset(newSet)
        else:
            return False # always assume deselecting everything marks the beginning of a new conceptual action
                   
    
class ResponseEvent(DialogEventHandler, SignalEvent):
    signalName = "response"
    dialogInfo = {}
    def __init__(self, name, widget, responseId):
        SignalEvent.__init__(self, name, widget)
        self.responseId = self.parseId(responseId)
            
    def shouldRecord(self, widget, responseId, *args):
        return self.responseId == responseId and \
            SignalEvent.shouldRecord(self, widget, responseId, *args) and \
            not self.superfluousAutoGenerated()

    @classmethod
    def getAssociatedSignatures(cls, widget):
        names = filter(lambda x: x.startswith("RESPONSE_"), dir(gtk))
        return set((name.lower().replace("_", ".", 1) for name in names))

    def getProgrammaticChangeMethods(self):
        return [ self.widget.response ]

    def getUiMapSignature(self):
        return self.getRecordSignal() + "." + self.getResponseIdSignature()

    def getResponseIdSignature(self):
        return repr(self.responseId).split()[1].split("_")[-1]

    def getEmissionArgs(self, argumentString):
        return [ self.responseId ]

    def parseId(self, responseId):
        # May have to reverse the procedure in getResponseIdSignature
        if type(responseId) == types.StringType:
            return eval("gtk.RESPONSE_" + responseId.upper())
        else:
            return responseId

class DeletionEvent(SignalEvent):
    signalName = "delete-event"
    def getEmissionArgs(self, argumentString):
        return [ gtk.gdk.Event(gtk.gdk.DELETE) ]
            
    def generate(self, argumentString):
        SignalEvent.generate(self, argumentString)
        self.widget.destroy() # just in case...
            
def getColumnName(column):
    name = column.get_data("name")
    if name:
        return name
    else:
        return column.get_title()

# Class to provide domain-level lookup for rows in a tree. Convert paths to strings and back again
# Can't store rows on TreeModelFilters, store the underlying rows and convert them at the last minute
class TreeViewIndexer:
    def __init__(self, treeview):
        self.givenModel = treeview.get_model()
        self.model = self.findModelToUse()
        self.logger = logging.getLogger("TreeModelIndexer")
        self.name2row = {}
        self.uniqueNames = {}
        self.renderer = self.getFirstTextRenderer(treeview)
        self.extractor = None
        self.tryPopulateMapping()

    def tryPopulateMapping(self):
        if not self.extractor:
            self.extractor = gtktreeviewextract.getTextExtractor(self.renderer)
            if self.extractor:
                self.model.foreach(self.rowInserted)
                self.model.connect("row-changed", self.rowInserted)

    def getFirstTextRenderer(self, treeview):
        for column in treeview.get_columns():
            for renderer in column.get_cell_renderers():
                if isinstance(renderer, gtk.CellRendererText):
                    return renderer

    def getValue(self, *args):
        return str(self.extractor.getValue(*args))

    def iter2string(self, iter):
        self.tryPopulateMapping()
        currentName = self.getValue(self.givenModel, iter)
        if not self.uniqueNames.has_key(currentName):
            return currentName

        path = self.convertFrom(self.givenModel.get_path(iter))
        for uniqueName in self.uniqueNames.get(currentName):
            for row in self.findAllRows(uniqueName):
                if row.get_path() == path:
                    return uniqueName
    
    def path2string(self, path):
        return self.iter2string(self.givenModel.get_iter(path))
                
    def string2iter(self, iterString):
        return self.givenModel.get_iter(self.string2path(iterString))

    def string2path(self, name):
        self.tryPopulateMapping()
        rows = self.findAllRows(name)
        if len(rows) == 1:
            return self.convertTo(rows[0].get_path(), name)
        elif len(rows) == 0:
            raise usecase.UseCaseScriptError, "Could not find row '" + name + "' in Tree View\nKnown names are " + repr(self.name2row.keys())
        else:
            raise usecase.UseCaseScriptError, "'" + name + "' in Tree View is ambiguous, could refer to " \
                  + str(len(rows)) + " different paths"
    
    def usesFilter(self):
        return isinstance(self.givenModel, gtk.TreeModelFilter)

    def findModelToUse(self):
        if self.usesFilter():
            return self.givenModel.get_model()
        else:
            return self.givenModel

    def convertFrom(self, path):
        if self.usesFilter():
            return self.givenModel.convert_path_to_child_path(path)
        else:
            return path

    def convertTo(self, path, name):
        if self.usesFilter():
            pathToUse = self.givenModel.convert_child_path_to_path(path)
            if pathToUse is not None:
                return pathToUse
            else:
                raise usecase.UseCaseScriptError, "Row '" + name + "' is currently hidden and cannot be accessed"
        else:
            return path

    def rowInserted(self, model, path, iter):
        givenName = self.getValue(model, iter)
        if givenName is None:
            return True # break off foreach
        row = gtk.TreeRowReference(model, path)
        if self.store(row, givenName):
            allRows = self.findAllRows(givenName)
            if len(allRows) > 1:
                newNames = self.getNewNames(allRows, givenName)
                self.uniqueNames[givenName] = newNames
                for row, newName in zip(allRows, newNames):
                    self.store(row, newName)

    def findAllRows(self, name):
        storedRows = self.name2row.get(name, [])
        if len(storedRows) > 0:
            validRows = filter(lambda r: r.get_path() is not None, storedRows)
            self.name2row[name] = validRows
            return validRows
        else:
            return storedRows
            
    def store(self, row, name):
        rows = self.name2row.setdefault(name, [])
        if not row.get_path() in [ r.get_path() for r in rows ]:
            self.logger.debug("Storing row named " + repr(name) + " with path " + repr(row.get_path()))
            rows.append(row)
            return True
        else:
            return False

    def getNewNames(self, rows, oldName):
        self.logger.debug(repr(oldName) + " can be applied to " + repr(len(rows)) + 
                          " rows, setting unique names")
        parentSuffices = {}
        for index, row in enumerate(rows):
            if row is None:
                raise usecase.UseCaseScriptError, "Cannot index tree model, there exist non-unique paths for " + oldName
            iter = self.model.get_iter(row.get_path())
            parent = self.model.iter_parent(iter)
            parentSuffix = self.getParentSuffix(parent)
            parentSuffices.setdefault(parentSuffix, []).append(index)
        
        newNames = [ oldName ] * len(rows) 
        for parentSuffix, indices in parentSuffices.items():
            newName = oldName
            if len(parentSuffices) > 1:
                newName += parentSuffix
            if len(indices) == 1:
                self.logger.debug("Name now unique, setting row " + repr(indices[0]) + " name to " + repr(newName))
                newNames[indices[0]] = newName
            else:
                matchingRows = [ rows[ix] for ix in indices ]
                parents = map(self.getParentRow, matchingRows)
                parentNames = self.getNewNames(parents, newName)
                for index, parentName in enumerate(parentNames):
                    self.logger.debug("Name from parents, setting row " + repr(indices[index]) + 
                                      " name to " + repr(parentName))
                    newNames[indices[index]] = parentName
        return newNames

    def getParentRow(self, row):
        parentIter = self.model.iter_parent(self.model.get_iter(row.get_path()))
        if parentIter:
            return gtk.TreeRowReference(self.model, self.model.get_path(parentIter))

    def getParentSuffix(self, parent):
        if parent:
            return " under " + self.getValue(self.model, parent)
        else:
            return " at top level"

origDialog = gtk.Dialog
origFileChooserDialog = gtk.FileChooserDialog    

class DialogHelper:
    def tryMonitor(self):
        self.doneMonitoring = self.uiMap.monitorDialog(self)
        if self.doneMonitoring:
            self.connect = self.connect_after_monitor

    def set_name(self, *args):
        origDialog.set_name(self, *args)
        if not self.doneMonitoring:
            self.uiMap.monitorDialog(self)
            self.connect = self.connect_after_monitor
            
    def connect_after_monitor(self, signalName, *args):
        handler = origDialog.connect(self, signalName, *args)
        if signalName == "response":
            ResponseEvent.storeHandler(self, handler, args=args)
        return handler


class Dialog(DialogHelper, origDialog):
    uiMap = None
    def __init__(self, *args, **kw):
        origDialog.__init__(self, *args, **kw)
        self.tryMonitor()


class FileChooserDialog(DialogHelper, origFileChooserDialog):
    uiMap = None
    def __init__(self, *args, **kw):
        origFileChooserDialog.__init__(self, *args, **kw)
        self.tryMonitor()


class UIMap:
    ignoreWidgetTypes = [ "Label" ]
    def __init__(self, scriptEngine, uiMapFiles): 
        # See top of file: uses the version from 2.6
        self.readParser = ConfigParser(dict_type=seqdict)
        self.readFiles(uiMapFiles)
        self.changed = False
        self.scriptEngine = scriptEngine
        self.windows = []
        self.storedEvents = set()
        self.logger = logging.getLogger("gui map")
        gtk.Dialog = Dialog
        Dialog.uiMap = self
        gtk.FileChooserDialog = FileChooserDialog
        FileChooserDialog.uiMap = self
        gtk.quit_add(1, self.write) # Write changes to the GUI map when the application exits

    def readFiles(self, uiMapFiles):
        self.file = uiMapFiles[-1]
        self.readParser.read(uiMapFiles)
        if len(uiMapFiles) > 1:
            self.writeParser = ConfigParser(dict_type=seqdict)
            self.writeParser.read([ self.file ])
        else:
            self.writeParser = self.readParser

    def monitorDialog(self, dialog):
        if self.monitorWidget(dialog):
            self.logger.debug("Picked up file-monitoring for dialog '" + self.getSectionName(dialog) + 
                              "', blocking instrumentation")
            self.scriptEngine.blockInstrumentation(dialog)
            return True
        else:
            return False
                
    def write(self, *args):
        if self.changed:
            if not os.path.isdir(os.path.dirname(self.file)):
                os.makedirs(os.path.dirname(self.file))
            self.writeParser.write(open(self.file, "w"))
            self.changed = False

    def getTitle(self, widget):
        try:
            return widget.get_title()
        except AttributeError:
            pass

    def getLabel(self, widget):
        text = self.getLabelText(widget)
        if text and "\n" in text:
            return text.splitlines()[0] + "..."
        else:
            return text

    def getLabelText(self, widget):
        try:
            return widget.get_label()
        except AttributeError:
            if isinstance(widget, gtk.MenuItem):
                child = widget.get_child()
                # "child" is normally a gtk.AccelLabel, but in theory it could be anything
                if isinstance(child, gtk.Label): 
                    return child.get_text()
            
    def getSectionName(self, widget):
        widgetName = widget.get_name()
        if not widgetName.startswith("Gtk"): # auto-generated
            return "Name=" + widgetName

        title = self.getTitle(widget)
        if title:
            return "Title=" + title
       
        label = self.getLabel(widget)
        if label:
            return "Label=" + label
        return "Type=" + widgetName.replace("Gtk", "")

    def storeEvent(self, event):
        sectionName = self.getSectionName(event.widget)
        if not sectionName:
            return
        
        self.logger.debug("Storing instrumented event for section '" + sectionName + "'")
        if not self.readParser.has_section(sectionName):
            self.writeParser.add_section(sectionName)
            if self.readParser is not self.writeParser:
                self.readParser.add_section(sectionName)

            self.changed = True
        eventName = event.name
        self.storedEvents.add(eventName)
        if self.storeInfo(sectionName, event.getUiMapSignature(), eventName, addToReadParser=True):
            self.changed = True

    def storeInfo(self, sectionName, signature, eventName, addToReadParser):
        signature = signature.replace("::", "-") # Can't store :: in ConfigParser unfortunately
        if not self.readParser.has_option(sectionName, signature):
            self.writeParser.set(sectionName, signature, eventName)
            if addToReadParser and self.readParser is not self.writeParser:
                self.readParser.set(sectionName, signature, eventName)
            return True
        else:
            return False
 
    def findSection(self, widget, widgetType):
        sectionNames = [ "Name=" + widget.get_name(), "Title=" + str(self.getTitle(widget)), 
                         "Label=" + str(self.getLabel(widget)), "Type=" + widgetType ]
        for sectionName in sectionNames:
            if self.readParser.has_section(sectionName):
                return sectionName

    def widgetHasSignal(self, widget, signalName):
        if signalName == "current-name-changed" and isinstance(widget, gtk.FileChooser):
            return True # Our favourite fake signal...

        # We tried using gobject.type_name and gobject.signal_list_names but couldn't make it work
        # We go for the brute force approach : actually do it and remove it again and see if we succeed...
        try:
            def nullFunc(*args) : pass
            handler = widget.connect(signalName, nullFunc)
            widget.disconnect(handler)
            return True
        except TypeError:
            return False

    def autoInstrument(self, eventName, signature, widget, widgetType):
        parts = signature.split(".", 1)
        signalName = parts[0]
        argumentParseData = None
        relevantState = None
        if len(parts) > 1:
            argumentParseData = parts[1]
        if argumentParseData and widgetType == "TreeView":
            event = self.makeTreeViewEvent(eventName, widget, argumentParseData, signalName)
            if event:
                self.scriptEngine._addEventToScripts(event, autoGenerated=True)
                return signature
        elif self.widgetHasSignal(widget, signalName):
            self.logger.debug("Monitor " + eventName + ", " + signalName + ", " + str(widget.__class__) + ", " + str(argumentParseData))
            self.scriptEngine.monitorSignal(eventName, signalName, widget, argumentParseData, autoGenerated=True)
            return signature
    
    def splitParseData(self, argumentParseData):
        if argumentParseData.endswith(".true") or argumentParseData.endswith(".false"):
            columnName, relevantState = argumentParseData.rsplit(".", 1)
            return columnName, relevantState == "true"
        else:
            return argumentParseData, None

    def makeTreeViewEvent(self, eventName, widget, argumentParseData, signalName):
        if signalName == "changed" and argumentParseData == "selection":
            indexer = self.scriptEngine.getTreeViewIndexer(widget)
            return TreeSelectionEvent(eventName, widget, widget.get_selection(), indexer)
        
        columnName, relevantState = self.splitParseData(argumentParseData)
        column = self.findTreeViewColumn(widget, columnName)
        if not column:
            raise usecase.UseCaseScriptError, "Could not find column with name " + repr(columnName)

        if signalName == "clicked":
            return TreeColumnClickEvent(eventName, widget, column)
        elif signalName == "toggled":
            renderer = self.findRenderer(column, gtk.CellRendererToggle)
            indexer = self.scriptEngine.getTreeViewIndexer(widget)
            return CellToggleEvent(eventName, widget, renderer, indexer, relevantState)
        elif signalName == "edited":
            renderer = self.findRenderer(column, gtk.CellRendererText)
            indexer = self.scriptEngine.getTreeViewIndexer(widget)
            return CellEditEvent(eventName, widget, renderer, indexer)
        else:
            # If we don't know, create a basic event on the column
            return self.scriptEngine._createSignalEvent(eventName, signalName, column, widget)

    def findTreeViewColumn(self, widget, columnName):
        for column in widget.get_columns():
            if getColumnName(column).lower() == columnName:
                return column

    def findRenderer(self, column, cls):
        for renderer in column.get_cell_renderers():
            if isinstance(renderer, cls):
                return renderer

    def instrumentFromMapFile(self, widget):
        widgetType = widget.__class__.__name__
        if widgetType in self.ignoreWidgetTypes:
            return set(), False
        signaturesInstrumented = set()
        autoInstrumented = False
        section = self.findSection(widget, widgetType)
        if section:
            self.logger.debug("Reading map file section " + repr(section) + " for widget of type " + widgetType)
            for signature, eventName in self.readParser.items(section):
                signature = signature.replace("notify-", "notify::")
                if eventName in self.storedEvents:
                    signaturesInstrumented.add(signature)
                else:
                    currSignature = self.autoInstrument(eventName, signature, widget, widgetType)
                    if currSignature:
                        signaturesInstrumented.add(currSignature)
                        autoInstrumented = True
        return signaturesInstrumented, autoInstrumented

    def findAutoInstrumentSignatures(self, widget, preInstrumented):
        signatures = []
        for eventClass in self.scriptEngine.findEventClassesFor(widget):
            for signature in eventClass.getAssociatedSignatures(widget):
                if signature not in signatures and signature not in preInstrumented:
                    signatures.append(signature)
        return signatures

    def monitorWidget(self, widget, mapFileOnly=False):
        signaturesInstrumented, autoInstrumented = self.instrumentFromMapFile(widget)
        if not mapFileOnly and self.scriptEngine.recorderActive():
            widgetType = widget.__class__.__name__
            for signature in self.findAutoInstrumentSignatures(widget, signaturesInstrumented):
                autoEventName = "Auto." + widgetType + "." + signature + ".'" + self.getSectionName(widget) + "'"
                self.autoInstrument(autoEventName, signature, widget, widgetType)
        return autoInstrumented

    def monitorChildren(self, widget, *args, **kw):
        if hasattr(widget, "get_children") and widget.get_name() != "Shortcut bar" and \
               not isinstance(widget, gtk.FileChooser) and not isinstance(widget, gtk.ToolItem):
            for child in widget.get_children():
                self.monitor(child, *args, **kw)

    def monitor(self, widget, excludeWidget=None, mapFileOnly=False):
        mapFileOnly |= widget is excludeWidget
        autoInstrumented = self.monitorWidget(widget, mapFileOnly)
        self.monitorChildren(widget, excludeWidget, mapFileOnly)
        return autoInstrumented

    def getAutoGenerated(self, commands):
        # Find the auto-generated commands and strip them of their arguments
        autoGenerated = []
        for command in commands:
            if command.startswith("Auto."):
                pos = command.rfind("'")
                commandWithoutArg = command[:pos + 1]
                if not commandWithoutArg in autoGenerated:
                    autoGenerated.append(commandWithoutArg)
        return autoGenerated

    def parseAutoGenerated(self, commands):
        autoGenerated = []
        for command in commands:
            parts = command[5:].split("'")
            initialPart = parts[0][:-1]
            widgetType, signalName = initialPart.split(".", 1)
            widgetDescription = parts[1]
            autoGenerated.append((widgetType, widgetDescription, signalName))
        return autoGenerated

    def storeNames(self, toStore):
        self.changed = True
        for ((widgetType, widgetDescription, signalName), eventName) in toStore:
            if not self.readParser.has_section(widgetDescription):
                self.writeParser.add_section(widgetDescription)
            self.storeInfo(widgetDescription, signalName, eventName, addToReadParser=False)
        self.write()

    def monitorNewWindows(self):
        for window in gtk.window_list_toplevels():
            self.monitorWindow(window)
    
    def monitorWindow(self, window):
        if window not in self.windows and window.get_title() != DomainNameGUI.title:
            self.windows.append(window)
            if isinstance(window, origDialog):
                # We've already done the dialog itself when it was empty, only look at the stuff in its vbox
                # which may have been added since then...
                self.logger.debug("Monitoring children for dialog with title " + repr(window.get_title()))
                return self.monitorChildren(window, excludeWidget=window.action_area)
            else:
                self.logger.debug("Monitoring new window with title " + repr(window.get_title()))
                return self.monitor(window)
        else:
            return False


class ScriptEngine(usecase.ScriptEngine):
    eventTypes = [
        (gtk.Button       , [ SignalEvent ]),
        (gtk.ToolButton   , [ SignalEvent ]),
        (gtk.MenuItem     , [ MenuItemSignalEvent ]),
        (gtk.CheckMenuItem, [ MenuActivateEvent ]),
        (gtk.ToggleButton , [ ActivateEvent ]),
        (gtk.Entry        , [ EntryEvent, SignalEvent ]),
        (gtk.FileChooser  , [ FileChooserFileSelectEvent, FileChooserFolderChangeEvent, 
                              FileChooserEntryEvent ]),
        (gtk.Dialog       , [ ResponseEvent, DeletionEvent ]),
        (gtk.Window       , [ DeletionEvent ]),
        (gtk.Notebook     , [ NotebookPageChangeEvent ]),
        (gtk.Paned        , [ PaneDragEvent ]),
        (gtk.TreeView     , [ RowActivationEvent, TreeSelectionEvent, RowExpandEvent, 
                              RowCollapseEvent, RowRightClickEvent, CellToggleEvent,
                              CellEditEvent, TreeColumnClickEvent ])
]
    defaultMapFile = os.path.join(usecase.ScriptEngine.usecaseHome, "ui_map.conf")
    def __init__(self, enableShortcuts=False, uiMapFiles=[ defaultMapFile ], universalLogging=True):
        self.uiMap = None
        if uiMapFiles:
            self.uiMap = UIMap(self, uiMapFiles)
        usecase.ScriptEngine.__init__(self, enableShortcuts, universalLogging=universalLogging)
        self.commandButtons = []
        self.fileChooserInfo = []
        self.dialogsBlocked = []
        self.treeViewIndexers = {}
        gtklogger.setMonitoring(universalLogging)
        if self.uiMap or gtklogger.isEnabled():
            gtktreeviewextract.performInterceptions()

    def addUiMapFiles(self, uiMapFiles):
        if self.uiMap:
            self.uiMap.readFiles(uiMapFiles)
        else:
            self.uiMap = UIMap(self, uiMapFiles)
        if self.replayer:
            self.replayer.addUiMap(self.uiMap)
        if not gtklogger.isEnabled():
            gtktreeviewextract.performInterceptions()
        
    def blockInstrumentation(self, dialog):
        self.dialogsBlocked.append(dialog)

    def connect(self, eventName, signalName, widget, method=None, argumentParseData=None, *data):
        signalEvent = self.monitorSignal(eventName, signalName, widget, argumentParseData)
        if method:
            widget.connect(signalName, method, *data)
        return signalEvent
    
    def standardName(self, name, autoGenerated=False):
        if autoGenerated:
            return name
        else:
            return name.strip().lower()

    def monitorSignal(self, eventName, signalName, widget, argumentParseData=None, autoGenerated=False):
        if self.active() and widget not in self.dialogsBlocked:
            stdName = self.standardName(eventName, autoGenerated)
            signalEvent = self._createSignalEvent(stdName, signalName, widget, argumentParseData)
            self._addEventToScripts(signalEvent, autoGenerated)
            return signalEvent

    def monitor(self, eventName, selection):
        if self.active():
            stdName = self.standardName(eventName)
            tree_view = selection.get_tree_view()
            indexer = self.getTreeViewIndexer(tree_view)
            stateChangeEvent = TreeSelectionEvent(stdName, tree_view, selection, indexer)
            self._addEventToScripts(stateChangeEvent)

    def monitorRightClicks(self, eventName, widget):
        if self.active():
            stdName = self.standardName(eventName)
            if isinstance(widget, gtk.TreeView):
                indexer = self.getTreeViewIndexer(widget)
                rightClickEvent = RowRightClickEvent(stdName, widget, indexer)
            else:
                rightClickEvent = RightClickEvent(stdName, widget)
            self._addEventToScripts(rightClickEvent)
    
    def monitorExpansion(self, treeView, expandDescription, collapseDescription=""):
        if self.active():
            expandName = self.standardName(expandDescription)
            indexer = self.getTreeViewIndexer(treeView)
            expandEvent = RowExpandEvent(expandName, treeView, indexer)
            self._addEventToScripts(expandEvent)
            if collapseDescription:
                collapseName = self.standardName(collapseDescription)
                collapseEvent = RowCollapseEvent(collapseName, treeView, indexer)
                self._addEventToScripts(collapseEvent)        

    def registerEntry(self, entry, description):
        if self.active():
            stateChangeName = self.standardName(description)
            entryEvent = EntryEvent(stateChangeName, entry)
            if self.recorderActive():
                entryEvent.widget.connect("activate", self.recorder.writeEvent, entryEvent)
            self._addEventToScripts(entryEvent)

    def registerPaned(self, paned, description):
        if self.active():
            stateChangeName = self.standardName(description)
            event = PaneDragEvent(stateChangeName, paned)
            self._addEventToScripts(event)

    def registerToggleButton(self, button, checkDescription, uncheckDescription = ""):
        if self.active():
            if isinstance(button, gtk.CheckMenuItem):
                eventClass = MenuActivateEvent
            else:
                eventClass = ActivateEvent
            checkChangeName = self.standardName(checkDescription)
            checkEvent = eventClass(checkChangeName, button, True)
            self._addEventToScripts(checkEvent)
            if uncheckDescription:
                uncheckChangeName = self.standardName(uncheckDescription)
                uncheckEvent = eventClass(uncheckChangeName, button, False)
                self._addEventToScripts(uncheckEvent)

    def registerCellToggleButton(self, renderer, checkDescription, parentTreeView, uncheckDescription=""):
        if self.active():
            checkChangeName = self.standardName(checkDescription)
            indexer = self.getTreeViewIndexer(parentTreeView)
            checkEvent = CellToggleEvent(checkChangeName, parentTreeView, renderer, indexer, True)
            self._addEventToScripts(checkEvent)
            if uncheckDescription:
                uncheckChangeName = self.standardName(uncheckDescription)
                uncheckEvent = CellToggleEvent(uncheckChangeName, parentTreeView, renderer, indexer, False)
                self._addEventToScripts(uncheckEvent)

    def registerCellEdit(self, renderer, description, parentTreeView):
        if self.active():
            stdName = self.standardName(description)
            indexer = self.getTreeViewIndexer(parentTreeView)
            event = CellEditEvent(stdName, parentTreeView, renderer, indexer)
            self._addEventToScripts(event)

    def registerFileChooser(self, fileChooser, fileDesc, folderChangeDesc):
        # Since we have not found and good way to connect to the gtk.Entry for giving filenames to save
        # we'll monitor pressing the (dialog OK) button given to us. When replaying,
        # we'll call the appropriate method to set the file name ...
        # (An attempt was made to find the gtk.Entry widget by looking in the FileChooser's child widgets,
        # which worked fine on linux but crashes on Windows)
        if self.active() and fileChooser not in self.dialogsBlocked:
            stdName = self.standardName(fileDesc)
            action = fileChooser.get_property("action")
            if action == gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER:
                # Selecting folders, do everything with the folder change...
                self.registerFolderChange(fileChooser, stdName)
            else:
                if action == gtk.FILE_CHOOSER_ACTION_OPEN:
                    event = FileChooserFileSelectEvent(stdName, fileChooser)
                else:
                    event = FileChooserEntryEvent(stdName, fileChooser)
                
                self._addEventToScripts(event)
                self.registerFolderChange(fileChooser, folderChangeDesc)
 
    def getTreeViewIndexer(self, treeView):
        return self.treeViewIndexers.setdefault(treeView, TreeViewIndexer(treeView))
            
    def registerFolderChange(self, fileChooser, description):
        stdName = self.standardName(description)
        event = FileChooserFolderChangeEvent(stdName, fileChooser)
        self._addEventToScripts(event)
        return event

    def monitorNotebook(self, notebook, description):
        if self.active():
            stateChangeName = self.standardName(description)
            event = NotebookPageChangeEvent(stateChangeName, notebook)
            self._addEventToScripts(event)
        return notebook

    def createShortcutBar(self):
        # Standard thing to add at the bottom of the GUI...
        buttonbox = gtk.HBox()
        buttonbox.set_name("Shortcut bar")
        existingbox = self.createExistingShortcutBox()
        buttonbox.pack_start(existingbox, expand=False, fill=False)
        newbox = gtk.HBox()
        self.addNewButton(newbox)
        self.addStopControls(newbox, existingbox)
        buttonbox.pack_start(newbox, expand=False, fill=False)
        existingbox.show()
        newbox.show()
        return buttonbox

    def addPrefix(self, fileName):
        if fileName:
            dirname, local = os.path.split(fileName)
            return os.path.join(dirname, "nameentry_" + local)

    def resetInstrumentation(self, testMode):
        self.recorder.scripts = []
        if testMode:
            # Repoint the instrumentation at different files
            replayScriptName = self.addPrefix(os.getenv("USECASE_REPLAY_SCRIPT"))
            if replayScriptName and os.path.isfile(replayScriptName):
                self.replayer.addScript(usecase.ReplayScript(replayScriptName))
            
            recordScriptName = self.addPrefix(os.getenv("USECASE_RECORD_SCRIPT"))
            if recordScriptName:
                self.recorder.addScript(recordScriptName)
        else: # pragma: no cover - results in a non-replaying UI and hence cannot be tested
            guiLogger = logging.getLogger("gui log")
            # This basically disables it
            guiLogger.setLevel(logging.WARNING)

        # Kill off any windows that are still around...
        for window in gtk.window_list_toplevels():
            if window.get_property("visible"):
                # It's not unheard of for the application to connect the "destroy"
                # signal to gtk.main_quit. In this case it will cause a double-quit
                # which throws an exception. So we block that here.
                try:
                    window.handler_block_by_func(gtk.main_quit)
                except TypeError:
                    pass
                window.destroy()

    def makeReplacement(self, command, replacements):
        for origName, newName in replacements:
            if command.startswith(origName):
                if newName:
                    return command.replace(origName, newName)
                else:
                    return
        return command

    def replaceAutoRecordingForShortcut(self, script, parentWindow):
        if self.uiMap:
            autoGenerated = self.uiMap.getAutoGenerated(script.getRecordedCommands())
            if len(autoGenerated) > 0:
                autoGeneratedInfo = self.uiMap.parseAutoGenerated(autoGenerated)
                domainNameGUI = DomainNameGUI(autoGeneratedInfo, self, parentWindow)
                allScripts = self.recorder.scripts + [ script ]
                domainNameGUI.dialog.connect("response", self.performReplacements, 
                                             domainNameGUI, autoGenerated, autoGeneratedInfo, allScripts)
        
    def replaceAutoRecordingForUseCase(self, testMode):
        if len(self.recorder.scripts) > 0:
            script = self.recorder.scripts[-1]
            commands = script.getRecordedCommands()
            autoGenerated = self.uiMap.getAutoGenerated(commands)
            if len(autoGenerated) > 0:
                self.resetInstrumentation(testMode)
                autoGeneratedInfo = self.uiMap.parseAutoGenerated(autoGenerated)
                domainNameGUI = DomainNameGUI(autoGeneratedInfo, self)
                domainNameGUI.dialog.run()
                self.performReplacements(domainNameGUI=domainNameGUI, 
                                         autoGenerated=autoGenerated, 
                                         autoGeneratedInfo=autoGeneratedInfo,
                                         scripts=[ script ])        

    def performReplacements(self, dialog=None, respId=None, domainNameGUI=None, 
                            autoGenerated=[], autoGeneratedInfo=[], scripts=[]):
        newNames = domainNameGUI.collectNames()
        self.uiMap.storeNames(zip(autoGeneratedInfo, newNames))
        replacements = zip(autoGenerated, newNames)
        for script in scripts:
            newCommands = []
            for c in script.getRecordedCommands():
                newCommand = self.makeReplacement(c, replacements)
                if newCommand:
                    newCommands.append(newCommand)
            script.rerecord(newCommands)
                
#private
    def getShortcutFiles(self):
        files = []
        usecaseDir = os.environ["USECASE_HOME"]
        if not os.path.isdir(usecaseDir):
            return files
        for fileName in os.listdir(usecaseDir):
            if fileName.endswith(".shortcut"):
                files.append(os.path.join(usecaseDir, fileName))
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
        self.monitorSignal("create new shortcut", "clicked", newButton, autoGenerated=True)
        newButton.connect("clicked", self.createShortcut, buttonbox)
        newButton.show()
        buttonbox.pack_start(newButton, expand=False, fill=False)

    def addShortcutButton(self, buttonbox, replayScript):
        button = gtk.Button()
        buttonName = replayScript.getShortcutName()
        button.set_use_underline(1)
        button.set_label(buttonName)
        self.monitorSignal(buttonName.lower(), "clicked", button, autoGenerated=True)
        button.connect("clicked", self.replayShortcut, replayScript)
        firstCommand = replayScript.commands[0]
        button.show()
        self.recorder.registerShortcut(replayScript)
        self.commandButtons.append((replayScript, button))
        buttonbox.add(button)

    def addStopControls(self, buttonbox, existingbox):
        label = gtk.Label("Recording shortcut named:")
        buttonbox.pack_start(label, expand=False, fill=False)
        entry = gtk.Entry()
        entry.set_name("Shortcut Name")
        self.monitorSignal("set shortcut name to", "changed", entry, autoGenerated=True)
        buttonbox.pack_start(entry, expand=False, fill=False)
        stopButton = gtk.Button()
        stopButton.set_use_underline(1)
        stopButton.set_label("S_top")
        self.monitorSignal("stop recording", "clicked", stopButton, autoGenerated=True)
        stopButton.connect("clicked", self.stopRecording, label, entry, buttonbox, existingbox)

        self.recorder.blockTopLevel("stop recording")
        self.recorder.blockTopLevel("set shortcut name to")
        buttonbox.pack_start(stopButton, expand=False, fill=False)

    def createShortcut(self, button, buttonbox, *args):
        buttonbox.show_all()
        button.hide()
        tmpFileName = self.getTmpShortcutName()
        self.recorder.addScript(tmpFileName)
        self.replayer.tryAddDescribeHandler()

    def stopRecording(self, button, label, entry, buttonbox, existingbox, *args):
        script = self.recorder.terminateScript()
        self.replayer.tryRemoveDescribeHandler()
        buttonbox.show_all()
        button.hide()
        label.hide()
        entry.hide()
        if script:
            buttonName = entry.get_text()
            # Save 'real' _ (mnemonics9 from being replaced in file name ...
            newScriptName = self.getShortcutFileName(buttonName.replace("_", "#")) 
            scriptExistedPreviously = os.path.isfile(newScriptName)
            script.rename(newScriptName)
            if not scriptExistedPreviously:
                replayScript = usecase.ReplayScript(newScriptName)
                self.addShortcutButton(existingbox, replayScript)
            self.replaceAutoRecordingForShortcut(script, button.get_toplevel())

    def replayShortcut(self, button, script, *args):
        self.replayer.addScript(script)
        if len(self.recorder.scripts):
            self.recorder.suspended = 1
            script.addExitObserver(self.recorder)

    def getTmpShortcutName(self):
        usecaseDir = os.environ["USECASE_HOME"]
        if not os.path.isdir(usecaseDir):
            os.makedirs(usecaseDir)
        return os.path.join(usecaseDir, "new_shortcut." + str(os.getpid()))

    def getShortcutFileName(self, buttonName):
        return os.path.join(os.environ["USECASE_HOME"], buttonName.replace(" ", "_") + ".shortcut")

    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)
                        
    def _addEventToScripts(self, event, autoGenerated=False):
        if self.uiMap and not autoGenerated:
            self.uiMap.storeEvent(event)
        if event.name and self.replayerActive():
            self.replayer.addEvent(event)
        if event.name and self.recorderActive():
            event.connectRecord(self.recorder.writeEvent)

    def findEventClassesFor(self, widget):
        eventClasses = []
        currClass = None
        for widgetClass, currEventClasses in self.eventTypes:
            if isinstance(widget, widgetClass):
                if not currClass or issubclass(widgetClass, currClass):
                    eventClasses = currEventClasses
                    currClass = widgetClass
                elif not issubclass(currClass, widgetClass):
                    eventClasses += currEventClasses
        return eventClasses
        
    def _createSignalEvent(self, eventName, signalName, widget, argumentParseData):
        stdSignalName = signalName.replace("_", "-")
        if isinstance(widget, gtk.TreeView) and argumentParseData is None:
            argumentParseData = self.getTreeViewIndexer(widget)

        for eventClass in self.findEventClassesFor(widget):
            if eventClass is not SignalEvent and eventClass.getAssociatedSignal(widget) == stdSignalName:
                return eventClass(eventName, widget, argumentParseData)
        
        return self._createGenericSignalEvent(signalName, eventName, widget)

    def _createGenericSignalEvent(self, signalName, *args):
        for eventClass in [ LeftClickEvent, RightClickEvent ]:
            if eventClass.signalName == signalName:
                return eventClass(*args)

        newArgs = args + (signalName,)
        return SignalEvent(*newArgs)


# Use the GTK idle handlers instead of a separate thread for replay execution
class UseCaseReplayer(usecase.UseCaseReplayer):
    def __init__(self, uiMap, universalLogging, recorder):
        self.readingEnabled = False
        self.uiMap = uiMap
        self.idleHandler = None
        self.loggerActive = universalLogging
        self.recorder = recorder
        self.tryAddDescribeHandler()
        # Anyone calling events_pending doesn't mean to include our logging events
        # so we intercept it and return the right answer for them...
        self.orig_events_pending = gtk.events_pending
        gtk.events_pending = self.events_pending
        usecase.UseCaseReplayer.__init__(self)

    def addUiMap(self, uiMap):
        self.uiMap = uiMap
        if not self.loggerActive:
            self.tryAddDescribeHandler()
        
    def isMonitoring(self):
        return self.loggerActive or (self.recorder.isActive() and self.uiMap)

    def tryAddDescribeHandler(self):
        if self.idleHandler is None and self.isMonitoring():
            self.idleHandler = gobject.idle_add(self.handleNewWindows, 
                                                priority=gtklogger.PRIORITY_PYUSECASE_IDLE)
        else:
            self.idleHandler = None

    def tryRemoveDescribeHandler(self):
        if not self.isMonitoring() and not self.readingEnabled:
            self.logger.debug("Disabling all idle handlers")
            self._disableIdleHandlers()
            if self.uiMap:
                self.uiMap.windows = [] # So we regenerate everything next time around

    def events_pending(self):
        if not self.isActive():
            self.logger.debug("Removing idle handler for descriptions")
            self._disableIdleHandlers()
        return_value = self.orig_events_pending()
        if not self.isActive():
            if self.readingEnabled:
                self.enableReplayHandler()
            else:
                self.logger.debug("Re-adding idle handler for descriptions")
                self.tryAddDescribeHandler()
        return return_value

    def _disableIdleHandlers(self):
        if self.idleHandler is not None:
            gobject.source_remove(self.idleHandler)
            self.idleHandler = None

    def enableReading(self):
        self.readingEnabled = True
        self._disableIdleHandlers()
        self.enableReplayHandler()
            
    def enableReplayHandler(self):
        # Set a lower than default priority (=high number!), as filechoosers use idle handlers
        # with default priorities. Higher priority than when we're just logging, however, try to block
        # out the application
        self.idleHandler = gobject.idle_add(self.describeAndRun, priority=gtklogger.PRIORITY_PYUSECASE_REPLAY_IDLE)

    def handleNewWindows(self):
        if self.uiMap and (self.isActive() or self.recorder.isActive()):
            self.uiMap.monitorNewWindows()
        if self.loggerActive:
            gtklogger.describeNewWindows()
        return True

    def describeAndRun(self):
        self.handleNewWindows()
        if self.readingEnabled:
            self.readingEnabled = self.runNextCommand()
            if not self.readingEnabled:
                self.idleHandler = None
                self.tryAddDescribeHandler()
                if not self.idleHandler and self.uiMap:
                    # End of shortcut: reset for next time
                    self.logger.debug("Shortcut terminated: Resetting UI map ready for next shortcut")
                    self.uiMap.windows = [] 
                    self.events = {}
        return self.readingEnabled


class DomainNameGUI:
    title = "Enter Usecase names for auto-recorded actions"
    def __init__(self, autoGenerated, scriptEngine, parent=None):
        self.dialog = gtk.Dialog(self.title, parent, flags=gtk.DIALOG_MODAL)
        self.dialog.set_name("Name Entry Window")
        self.allEntries = []
        self.dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        contents = self.createWindowContents(autoGenerated, scriptEngine)
        self.dialog.vbox.pack_start(contents, expand=True, fill=True)
        yesButton = self.dialog.add_button(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
        scriptEngine.monitorSignal("finish name entry editing", "response", self.dialog, gtk.RESPONSE_ACCEPT, autoGenerated=True)
        self.dialog.show_all()
        
    def createMarkupLabel(self, markup):
        label = gtk.Label()
        label.set_markup(markup)
        return label

    def activateEntry(self, *args):
        self.dialog.response(gtk.RESPONSE_ACCEPT)

    def createWindowContents(self, autoGenerated, scriptEngine):
        table = gtk.Table(rows=len(autoGenerated) + 1, columns=4)
        table.set_col_spacings(20)
        headers = [ "Widget Type", "Identified By", "PyGTK Signal Name", "Usecase Name" ]
        for col, header in enumerate(headers):
            table.attach(self.createMarkupLabel("<b><u>" + header + "</u></b>"), 
                         col, col + 1, 0, 1, xoptions=gtk.FILL)
        for rowIndex, (widgetType, widgetDesc, signalName) in enumerate(autoGenerated):
            table.attach(gtk.Label(widgetType), 0, 1, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL)
            table.attach(gtk.Label(widgetDesc), 1, 2, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL)
            table.attach(self.createMarkupLabel("<i>" + signalName + "</i>"), 
                         2, 3, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL)
            entry = gtk.Entry()
            scriptName = "enter usecase name for signal '" + signalName + "' on " + widgetType + " '" + widgetDesc + "' ="
            scriptEngine.monitorSignal(scriptName, "changed", entry, autoGenerated=True)
            entry.connect("activate", self.activateEntry)
            scriptEngine.monitorSignal("finish name entry editing by pressing <enter>", "activate", entry, autoGenerated=True)
            self.allEntries.append(entry)
            table.attach(entry, 3, 4, rowIndex + 1, rowIndex + 2)
        return table

    def collectNames(self):
        names = [ entry.get_text() for entry in self.allEntries ]
        self.dialog.destroy()
        return names
