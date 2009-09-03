
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

import usecase, gtklogger, gtk, gobject, os, re, logging, types
from ConfigParser import ConfigParser
from ndict import seqdict
PRIORITY_PYUSECASE_IDLE = gtklogger.PRIORITY_PYUSECASE_IDLE
version = usecase.version

# Useful to have at module level as can't really be done externally
def createShortcutBar():
    if usecase.scriptEngine:
        return usecase.scriptEngine.createShortcutBar()


# Abstract Base class for all GTK events
class GtkEvent(usecase.UserEvent):
    def __init__(self, name, widget, *args):
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
            raise usecase.UseCaseScriptError, "widget '" + self.widget.get_name() + \
                  "' is not visible at the moment, cannot simulate event " + repr(self.name)

        if not self.getProperty("sensitive"):
            raise usecase.UseCaseScriptError, "widget '" + self.widget.get_name() + \
                  "' is not sensitive to input at the moment, cannot simulate event " + repr(self.name)

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
        elif isinstance(widget, gtk.Button):
            return "clicked"
        elif isinstance(widget, gtk.Entry) or isinstance(widget, gtk.MenuItem):
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
    def __call__(self, *args, **kwds):
        # Allow for possibly nested programmatic changes, observation can have knock-on effects
        eventsToBlock = filter(lambda event: not event.programmaticChange, self.events)
        for event in eventsToBlock:
            event.setProgrammaticChange(True, *args, **kwds)
        retVal = apply(self.method, args, kwds)
        for event in eventsToBlock:
            event.setProgrammaticChange(False)
        return retVal

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
        self.relevantState = relevantState
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
        raise usecase.UseCaseScriptError, "Could not find page " + argumentString + " in '" + self.name + "'"

class TreeViewEvent(GtkEvent):
    def __init__(self, name, widget, indexer):
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
    def implies(self, prevLine, prevEvent):
        if not isinstance(prevEvent, TreeSelectionEvent):
            return False
        return self.widget.get_selection() is prevEvent.widget

class RightClickEvent(SignalEvent):
    signalName = "button_press_event"
    def shouldRecord(self, widget, event, *args):
        return SignalEvent.shouldRecord(self, widget, event, *args) and event.button == 3

    def getEmissionArgs(self, argumentString):
        area = self.getAreaToClick(argumentString)
        event = gtk.gdk.Event(gtk.gdk.BUTTON_PRESS)
        event.x = float(area.x) + float(area.width) / 2
        event.y = float(area.y) + float(area.height) / 2
        event.button = 3
        return [ event ]

    def getAreaToClick(self, *args):
        return self.widget.get_allocation()

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
        
# Remember: self.widget is not really a widget here,
# since gtk.CellRenderer is not a gtk.Widget.
class CellToggleEvent(TreeViewEvent):
    signalName = "toggled"
    def getChangeMethod(self):
        return self.widget.emit
    def _outputForScript(self, path, *args):
        return self.name + " " + self.indexer.path2string(path)
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


# At least on Windows this doesn't seem to happen immediately, but takes effect some time afterwards
# Seems quite capable of generating too many of them also
class FileChooserFolderChangeEvent(StateChangeEvent):
    signalName = "current-folder-changed"
    def __init__(self, name, widget):
        self.currentFolder = widget.get_current_folder()
        StateChangeEvent.__init__(self, name, widget)
    def setProgrammaticChange(self, val, filename=None):
        if val:
            self.programmaticChange = val
    def shouldRecord(self, *args):
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
        return os.path.join(self.widget.get_current_folder(), argumentString)

# Base class for selecting a file or typing a file name
class FileChooserFileEvent(StateChangeEvent):
    def __init__(self, name, widget, fileChooser=None):
        self.fileChooser = fileChooser
        if not fileChooser:
            self.fileChooser = widget
        StateChangeEvent.__init__(self, name, widget)
        self.currentName = self.getStateDescription()
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
    def getStateChangeArgument(self, argumentString):
        return os.path.join(self.fileChooser.get_current_folder(), argumentString)
    
class FileChooserFileSelectEvent(FileChooserFileEvent):
    signalName = "selection-changed"
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

class FileChooserEntryEvent(FileChooserFileEvent):
    signalName = "clicked"
    def getChangeMethod(self):
        return self.fileChooser.set_current_name                                    
                                    
class TreeSelectionEvent(StateChangeEvent):
    def __init__(self, name, widget, indexer):
        self.indexer = indexer
        # cache these before calling base class constructor, or they get intercepted...
        self.unselect_iter = widget.unselect_iter
        self.select_iter = widget.select_iter
        self.prevSelected = []
        StateChangeEvent.__init__(self, name, widget)
    def getChangeMethod(self):
        return self.widget.select_iter
    def getModels(self):
        model = self.widget.get_tree_view().get_model()
        if isinstance(model, gtk.TreeModelFilter):
            return model, model.get_model()
        else:
            return None, model
    def getProgrammaticChangeMethods(self):
        modelFilter, realModel = self.getModels()
        methods = [ self.widget.unselect_all, self.widget.select_all, \
                    self.widget.select_iter, self.widget.unselect_iter, \
                    self.widget.select_path, self.widget.unselect_path,
                    self.widget.get_tree_view().row_activated, self.widget.get_tree_view().collapse_row,
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
            self.prevSelected = newSelected
        return ",".join(newSelected)
    def findSelectedIters(self):
        iters = []
        self.widget.selected_foreach(self.addSelIter, iters)
        return iters
    def addSelIter(self, model, path, iter, iters):
        iters.append(self.indexer.iter2string(iter))
    def getStateChangeArgument(self, argumentString):
        return map(self.indexer.string2iter, argumentString.split(","))
    def generate(self, argumentString):
        oldSelected = self.findSelectedIters()
        newSelected = self.parseIterNames(argumentString)
        toUnselect, toSelect = self.findChanges(oldSelected, newSelected)
        if len(toSelect) > 0:
            self.widget.unseen_changes = True
        for iterName in toUnselect:
            self.unselect_iter(self.indexer.string2iter(iterName))
        if len(toSelect) > 0:
            delattr(self.widget, "unseen_changes")
        for iterName in newSelected:
            self.select_iter(self.indexer.string2iter(iterName))
            
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
    def implies(self, prevLine, prevEvent):
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
                         
    
class ResponseEvent(SignalEvent):
    signalName = "response"
    def __init__(self, name, widget, responseId):
        SignalEvent.__init__(self, name, widget)
        self.responseId = self.parseId(responseId)
    def shouldRecord(self, widget, responseId, *args):
        return self.responseId == responseId and SignalEvent.shouldRecord(self, widget, responseId, *args)
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
            
            
# Class to provide domain-level lookup for rows in a tree. Convert paths to strings and back again
# Application needs to guarantee unique values for get_value(iter, self.valueId) for all iter
class TreeModelIndexer:
    def __init__(self, model, column):
        self.model = model
        self.column = column
    def iter2string(self, iter):
        return self.getValue(iter)
    def path2string(self, path):
        return self.iter2string(self.model.get_iter(path))
    def string2path(self, iterString):
        return self.model.get_path(self.string2iter(iterString))
    def getValue(self, iter):
        fromModel = self.model.get_value(iter, self.column)
        if fromModel is not None:
            return re.sub("<[^>]*>", "", fromModel)
    def string2iter(self, iterString):
        iter = self._findTreeIter(self.model.get_iter_root(), iterString)
        if not iter:
            raise usecase.UseCaseScriptError, "Could not find row '" + iterString + "' in Tree View"
        return iter
    def _findTreeIter(self, iter, argumentText):
        if self._pathHasText(iter, argumentText):
            return iter
        childIter = self.model.iter_children(iter)
        if childIter:
            foundIter = self._findTreeIter(childIter, argumentText)
            if foundIter:
                return foundIter
        nextIter = self.model.iter_next(iter)
        if nextIter:
            return self._findTreeIter(nextIter, argumentText)

    def _pathHasText(self, iter, argumentText):
        return self.getValue(iter) == argumentText

# Where names aren't guaranteed to be unique, this more complex version will create and store such names for itself...
# Can't store iterators on TreeModelFilters, store the underlying iterators and convert them at the last minute
class NonUniqueTreeModelIndexer(TreeModelIndexer):
    def __init__(self, model, valueId):
        self.givenModel = model
        modelToUse = self.findModelToUse()
        TreeModelIndexer.__init__(self, modelToUse, valueId)
        self.iter2name = {}
        self.name2iter = {}
        self.model.foreach(self.rowInserted)
        self.model.connect("row-changed", self.rowChanged)
        self.model.connect("row-inserted", self.rowInserted)
        self.model.connect("row-deleted", self.rowDeleted)
    def string2path(self, iterString):
        return self.givenModel.get_path(self.string2iter(iterString))
    def path2string(self, path):
        return self.iter2string(self.givenModel.get_iter(path))
    def usesFilter(self):
        return isinstance(self.givenModel, gtk.TreeModelFilter)
    def findModelToUse(self):
        if self.usesFilter():
            return self.givenModel.get_model()
        else:
            return self.givenModel
    def convertFrom(self, iter):
        if self.usesFilter():
            return self.givenModel.convert_iter_to_child_iter(iter)
        else:
            return iter
    def convertTo(self, iter, name):
        if self.usesFilter():
            try:
                return self.givenModel.convert_child_iter_to_iter(iter)
            except RuntimeError:
                raise usecase.UseCaseScriptError, "Row '" + name + "' is currently hidden and cannot be accessed"
        else:
            return iter
    def findStoredIter(self, iter):
        name = self.getValue(iter)
        path = self.model.get_path(iter)
        return self._findStoredIter(path, self.name2iter.get(name, []))
    def _findStoredIter(self, path, list):
        for storedIter in list:
            if self.model.get_path(storedIter) == path:
                return storedIter
        
    def iter2string(self, iter):
        actualIter = self.findStoredIter(self.convertFrom(iter))
        names = self.iter2name.get(actualIter)
        if len(names) > 0:
            return names[-1]
        else:
            raise usecase.UseCaseScriptError, "Could not find name for path " + repr(self.givenModel.get_path(iter)) +\
                  "\nKnown paths are " + repr(map(self.model.get_path, self.iter2name.keys()))
    def string2iter(self, name):
        iters = self.name2iter.get(name, [])
        if len(iters) == 1:
            return self.convertTo(iters[0], name)
        elif len(iters) == 0:
            raise usecase.UseCaseScriptError, "Could not find row '" + name + "' in Tree View\nKnown names are " + repr(self.name2iter.keys())
        else:
            raise usecase.UseCaseScriptError, "'" + name + "' in Tree View is ambiguous, could refer to " \
                  + str(len(iters)) + " different paths"    
    def rowInserted(self, model, path, iter):
        givenName = self.getValue(iter)
        if givenName is None:
            return
        iterCopy = iter.copy()
        self.store(iterCopy, givenName)
        allIterators = self.name2iter.get(givenName, [])
        if len(allIterators) > 1:
            newNames = self.getNewNames(allIterators, givenName)
            for currIter in allIterators:
                self.store(currIter, newNames[currIter])
        
    def rowDeleted(self, *args):
        # The problem here is that we don't have a clue what's been removed, as the path is not valid any more!
        # So we do a blanket check of all iterators and remove anything that isn't valid
        for iter in self.iter2name.keys():
            if not self.model.iter_is_valid(iter):
                self.removeIter(iter)
        
    def removeIter(self, iter):
        for storedName in self.iter2name.get(iter):
            self.name2iter[storedName].remove(iter)
            if len(self.name2iter[storedName]) == 0:
                del self.name2iter[storedName]
        del self.iter2name[iter]

    def rowChanged(self, model, path, iter):
        # Basically to pick up name changes
        givenName = self.getValue(iter)
        if givenName is not None:
            storedIterMatchingName = self.findStoredIter(iter)
            if storedIterMatchingName is None:
                storedIter = self._findStoredIter(path, self.iter2name.keys())
                if storedIter:
                    self.removeIter(storedIter)
                self.rowInserted(model, path, iter)
        
    def store(self, iter, name):
        namelist = self.iter2name.setdefault(iter, [])
        if not name in namelist:
            namelist.append(name)
        iterlist = self.name2iter.setdefault(name, [])
        if not iter in iterlist:
            iterlist.append(iter)

    def getNewNames(self, iters, oldName):
        parentSuffices = {}
        for iter in iters:
            if iter is None:
                raise usecase.UseCaseScriptError, "Cannot index tree model, there exist non-unique paths for " + oldName
            parent = self.model.iter_parent(iter)
            parentSuffix = self.getParentSuffix(parent)
            parentSuffices.setdefault(parentSuffix, []).append(iter)
        
        newNames = {}
        for parentSuffix, iters in parentSuffices.items():
            newName = oldName
            if len(parentSuffices) > 1:
                newName += parentSuffix
            if len(iters) == 1:
                newNames[iters[0]] = newName
            else:
                parents = map(self.model.iter_parent, iters)
                parents2names = self.getNewNames(parents, newName)
                for index, parent in enumerate(parents):
                    newNames[iters[index]] = parents2names[parent]
        return newNames

    def getParentSuffix(self, parent):
        if parent:
            return " under " + self.getValue(parent)
        else:
            return " at top level"
  
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

class UIMap:
    ignoreWidgetTypes = [ "Label" ]
    def __init__(self, scriptEngine):
        usecaseDir = os.getenv("USECASE_HOME")
        if not os.path.isdir(usecaseDir):
            os.makedirs(usecaseDir)
        self.file = os.path.join(usecaseDir, "ui_map.conf")
        try:
            # works in Python 2.6
            self.parser = ConfigParser(dict_type=seqdict)
        except TypeError:
            # hacks for older versions
            self.parser = ConfigParser()
            self.parser._sections = seqdict()

        self.parser.read([ self.file ])
        self.changed = False
        self.scriptEngine = scriptEngine
        self.windows = []
        self.storedEvents = set()
        self.logger = logging.getLogger("gui map")
        self.realDialog = gtk.Dialog
        gtk.Dialog = self.createDialog

    def createDialog(self, *args, **kwargs):
        dialog = self.realDialog(*args, **kwargs)
        if self.monitorWindow(dialog):
            self.scriptEngine.blockInstrumentation(dialog)
        return dialog
        
    def write(self, *args):
        if self.changed:
            self.parser.write(open(self.file, "w"))

    def getTitle(self, widget):
        try:
            return widget.get_title()
        except AttributeError:
            pass

    def getLabel(self, widget):
        try:
            return widget.get_label()
        except AttributeError:
            if isinstance(widget, gtk.MenuItem):
                return widget.get_child().get_text()
            
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
        if not self.parser.has_section(sectionName):
            self.parser.add_section(sectionName)
            self.changed = True
        eventName = event.name
        self.storedEvents.add(eventName)
        signalName = event.getUiMapSignature()
        if not self.parser.has_option(sectionName, signalName):
            self.parser.set(sectionName, signalName, eventName)
            self.changed = True
        if isinstance(event, DeletionEvent):
            event.widget.connect("delete-event", self.write)

    def findSection(self, widget, widgetType):
        sectionNames = [ "Name=" + widget.get_name(), "Title=" + str(self.getTitle(widget)), 
                         "Label=" + str(self.getLabel(widget)), "Type=" + widgetType ]
        for sectionName in sectionNames:
            if self.parser.has_section(sectionName):
                return sectionName

    def widgetHasSignal(self, widget, signalName):
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
        parts = signature.split(".")
        signalName = parts[0]
        if self.widgetHasSignal(widget, signalName):
            argumentParseData = None
            if len(parts) > 1:
                argumentParseData = parts[1]
            self.logger.debug("Monitor " + eventName + ", " + signalName + ", " + str(widget) + ", " + str(argumentParseData))
            self.scriptEngine.monitorSignal(eventName, signalName, widget, argumentParseData, autoGenerated=True)
            if signalName.startswith("delete"):
                widget.connect(signalName, self.write)
            return signature

    def instrumentFromMapFile(self, widget):
        widgetType = widget.__class__.__name__
        if widgetType in self.ignoreWidgetTypes:
            return set(), False
        signaturesInstrumented = set()
        autoInstrumented = False
        section = self.findSection(widget, widgetType)
        if section:
            for signature, eventName in self.parser.items(section):
                if eventName in self.storedEvents:
                    signaturesInstrumented.add(signature)
                else:
                    currSignature = self.autoInstrument(eventName, signature, widget, widgetType)
                    if currSignature:
                        signaturesInstrumented.add(currSignature)
                        autoInstrumented = True
        return signaturesInstrumented, autoInstrumented

    def findSupportedSignatures(self, widget):
        eventClasses = self.scriptEngine.findEventClassesFor(widget)
        return reduce(set.union, (eventClass.getAssociatedSignatures(widget) for eventClass in eventClasses), set())

    def monitor(self, widget):
        signaturesInstrumented, autoInstrumented = self.instrumentFromMapFile(widget)
        if self.scriptEngine.recorderActive():
            signaturesSupported = self.findSupportedSignatures(widget)
            for signature in signaturesSupported.difference(signaturesInstrumented):
                widgetType = widget.__class__.__name__
                autoEventName = "Auto." + widgetType + "." + signature + ".'" + self.getSectionName(widget) + "'"
                self.autoInstrument(autoEventName, signature, widget, widgetType)

        if hasattr(widget, "get_children"):
            for child in widget.get_children():
                if child.get_name() != "Shortcut bar":
                    self.monitor(child)
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
            if not self.parser.has_section(widgetDescription):
                self.parser.add_section(widgetDescription)
            if not self.parser.has_option(widgetDescription, signalName):
                self.parser.set(widgetDescription, signalName, eventName)
        self.write()

    def monitorNewWindows(self):
        for window in gtk.window_list_toplevels():
            self.monitorWindow(window)
    
    def monitorWindow(self, window):
        if window not in self.windows and window.get_title() != DomainNameGUI.title:
            self.windows.append(window)
            return self.monitor(window)
        else:
            return False


class ScriptEngine(usecase.ScriptEngine):
    eventTypes = {
        gtk.Button   : [ SignalEvent ],
        gtk.MenuItem : [ SignalEvent ],
        gtk.Entry    : [ EntryEvent, SignalEvent ],
        gtk.Dialog   : [ ResponseEvent ],
        gtk.Window   : [ DeletionEvent ],
        gtk.Notebook : [ NotebookPageChangeEvent ]
# Causes trouble, leave this out for now...
#        gtk.TreeView : [ RowActivationEvent, TreeSelectionEvent, RowExpandEvent, 
#                         RowCollapseEvent, RowRightClickEvent ]
}
    def __init__(self, enableShortcuts=False, useUiMap=False, universalLogging=True):
        self.uiMap = None
        if useUiMap:
            self.uiMap = UIMap(self)
        usecase.ScriptEngine.__init__(self, enableShortcuts, universalLogging=universalLogging)
        self.commandButtons = []
        self.fileChooserInfo = []
        self.dialogsBlocked = []
        self.treeViewIndexers = {}
        gtklogger.setMonitoring(universalLogging, self.replayerActive())
        
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

    def monitor(self, eventName, selection, keyColumn=0, guaranteeUnique=False):
        if self.active():
            stdName = self.standardName(eventName)
            indexer = self.getTreeViewIndexer(selection.get_tree_view(), keyColumn, guaranteeUnique)
            stateChangeEvent = TreeSelectionEvent(stdName, selection, indexer)
            self._addEventToScripts(stateChangeEvent)

    def monitorRightClicks(self, eventName, widget, **kwargs):
        if self.active():
            stdName = self.standardName(eventName)
            if isinstance(widget, gtk.TreeView):
                indexer = self.getTreeViewIndexer(widget, **kwargs)
                rightClickEvent = RowRightClickEvent(stdName, widget, indexer)
            else:
                rightClickEvent = RightClickEvent(stdName, widget)
            self._addEventToScripts(rightClickEvent)
    
    def monitorExpansion(self, treeView, expandDescription, collapseDescription="", keyColumn=0, guaranteeUnique=False):
        if self.active():
            expandName = self.standardName(expandDescription)
            indexer = self.getTreeViewIndexer(treeView, keyColumn, guaranteeUnique)
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
            checkChangeName = self.standardName(checkDescription)
            checkEvent = ActivateEvent(checkChangeName, button, True)
            self._addEventToScripts(checkEvent)
            if uncheckDescription:
                uncheckChangeName = self.standardName(uncheckDescription)
                uncheckEvent = ActivateEvent(uncheckChangeName, button, False)
                self._addEventToScripts(uncheckEvent)

    def registerCellToggleButton(self, button, description, parentTreeView, *args, **kwargs):
        if self.active():
            eventName = self.standardName(description)
            event = CellToggleEvent(eventName, button, self.getTreeViewIndexer(parentTreeView, *args, **kwargs))
            self._addEventToScripts(event)

    def registerSaveFileChooser(self, fileChooser, fileDesc, folderChangeDesc, saveDesc, cancelDesc, 
                                respondMethod, saveButton=None, cancelButton=None, respondMethodArg=None):
        # Since we have not found and good way to connect to the gtk.Entry for giving filenames to save
        # we'll monitor pressing the (dialog OK) button given to us. When replaying,
        # we'll call the appropriate method to set the file name ...
        # (An attempt was made to find the gtk.Entry widget by looking in the FileChooser's child widgets,
        # which worked fine on linux but crashes on Windows)
        if self.active():
            stdName = self.standardName(fileDesc)
            event = FileChooserEntryEvent(stdName, saveButton, fileChooser)
            self._addEventToScripts(event)
            self.registerFolderChange(fileChooser, folderChangeDesc)
            self.createOKEvent(fileChooser, saveDesc, respondMethod, saveButton, respondMethodArg)
            self.createCancelEvent(fileChooser, cancelDesc, respondMethod, cancelButton, respondMethodArg)

    def registerOpenFileChooser(self, fileChooser, fileSelectDesc, folderChangeDesc, openDesc, cancelDesc, 
                                respondMethod, openButton=None, cancelButton=None, respondMethodArg=None):
        if self.active():
            stdName = self.standardName(fileSelectDesc)
            if fileChooser.get_property("action") == gtk.FILE_CHOOSER_ACTION_OPEN:
                event = FileChooserFileSelectEvent(stdName, fileChooser)
                self._addEventToScripts(event)
                self.registerFolderChange(fileChooser, folderChangeDesc)
            else:
                # Selecting folders, do everything with the folder change...
                self.registerFolderChange(fileChooser, stdName)
            self.createOKEvent(fileChooser, openDesc, respondMethod, openButton, respondMethodArg)
            self.createCancelEvent(fileChooser, cancelDesc, respondMethod, cancelButton, respondMethodArg)
 
    def createOKEvent(self, fileChooser, OKDesc, respondMethod, OKButton, respondMethodArg):
        if OKButton:
            # The OK button is what we monitor in the scriptEngine, so simulate that it is pressed ...
            fileChooser.connect("file-activated", self.simulateOKClick, OKButton)
            return self.connect(OKDesc, "clicked", OKButton, respondMethod, None, True, respondMethodArg)
        else:
            return self.connect(OKDesc, "response", fileChooser, respondMethod, gtk.RESPONSE_OK, respondMethodArg)
        
    def simulateOKClick(self, filechooser, button):
        button.clicked()

    def createCancelEvent(self, fileChooser, cancelDesc, respondMethod, cancelButton, respondMethodArg):
        if cancelButton:
            return self.connect(cancelDesc, "clicked", cancelButton, respondMethod, None, False, respondMethodArg)
        else:
            return self.connect(cancelDesc, "response", fileChooser, respondMethod, gtk.RESPONSE_CANCEL, respondMethodArg)

    def getTreeViewIndexer(self, treeView, *args, **kwargs):
        if self.treeViewIndexers.has_key(treeView):
            return self.treeViewIndexers[treeView]

        newIndexer = self.createTreeViewIndexer(treeView, *args, **kwargs)
        self.treeViewIndexers[treeView] = newIndexer
        return newIndexer

    def createTreeViewIndexer(self, treeView, keyColumn=0, guaranteeUnique=False):
        model = treeView.get_model()
        if guaranteeUnique:
            return TreeModelIndexer(model, keyColumn)
        else:
            return NonUniqueTreeModelIndexer(model, keyColumn)
            
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
        if not self.enableShortcuts:
            return None
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
        else:
            guiLogger = logging.getLogger("gui log")
            # This basically disables it
            guiLogger.setLevel(logging.WARNING)

        # Kill off any windows that are still around...
        for window in gtk.window_list_toplevels():
            if window.get_property("visible"):
                window.destroy()

    def makeReplacement(self, command, replacements):
        for origName, newName in replacements:
            if command.startswith(origName):
                return command.replace(origName, newName)
        return command

    def replaceAutoRecordingForShortcut(self, script, parentWindow):
        autoGenerated = self.uiMap.getAutoGenerated(script.getRecordedCommands())
        if len(autoGenerated) > 0:
            autoGeneratedInfo = self.uiMap.parseAutoGenerated(autoGenerated)
            domainNameGUI = DomainNameGUI(autoGeneratedInfo, self, parentWindow)
            allScripts = self.recorder.scripts + [ script ]
            domainNameGUI.dialog.connect("response", self.performReplacements, 
                                         domainNameGUI, autoGenerated, autoGeneratedInfo, allScripts)
        
    def replaceAutoRecordingForUseCase(self, testMode):
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
            newCommands = [ self.makeReplacement(c, replacements) for c in script.getRecordedCommands() ]
            script.rerecord(newCommands)
                
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
        if self.replayer.findCommandName(firstCommand):
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

    def stopRecording(self, button, label, entry, buttonbox, existingbox, *args):
        script = self.recorder.terminateScript()
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
        return os.path.join(usecaseDir, "new_shortcut")

    def getShortcutFileName(self, buttonName):
        return os.path.join(os.environ["USECASE_HOME"], buttonName.replace(" ", "_") + ".shortcut")

    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging)

    def showShortcutButtons(self, event):
        for replayScript, button in self.commandButtons:
            if replayScript.commands[0].startswith(event.name):
                button.show()
                self.recorder.registerShortcut(replayScript)
                
    def _addEventToScripts(self, event, autoGenerated=False):
        if self.enableShortcuts:
            self.showShortcutButtons(event)
        if self.uiMap and not autoGenerated:
            self.uiMap.storeEvent(event)
        if self.replayerActive():
            self.replayer.addEvent(event)
        if self.recorderActive():
            event.connectRecord(self.recorder.writeEvent)

    def findEventClassesFor(self, widget):
        eventClasses = []
        for widgetClass, currEventClasses in self.eventTypes.items():
            if isinstance(widget, widgetClass):
                eventClasses += currEventClasses
        return eventClasses

    def _createSignalEvent(self, eventName, signalName, widget, argumentParseData):
        stdSignalName = signalName.replace("_", "-")
        if stdSignalName == "row-activated":
            return RowActivationEvent(eventName, widget, self.getIndexerFromParseData(widget, argumentParseData))
        for eventClass in self.findEventClassesFor(widget):
            if eventClass is not SignalEvent and eventClass.getAssociatedSignal(widget) == stdSignalName:
                return eventClass(eventName, widget, argumentParseData)
        
        return SignalEvent(eventName, widget, signalName)

    def getIndexerFromParseData(self, widget, argumentParseData):
        if argumentParseData is not None:
            return self.getTreeViewIndexer(widget, *argumentParseData)
        else:
            return self.getTreeViewIndexer(widget)

# Use the GTK idle handlers instead of a separate thread for replay execution
class UseCaseReplayer(usecase.UseCaseReplayer):
    def __init__(self, uiMap, universalLogging):
        self.readingEnabled = False
        self.uiMap = uiMap
        self.loggerActive = universalLogging
        self.tryAddDescribeHandler()
        usecase.UseCaseReplayer.__init__(self)

    def tryAddDescribeHandler(self):
        if self.loggerActive or self.uiMap:
            self.idleHandler = gobject.idle_add(self.handleNewWindows, 
                                                priority=gtklogger.PRIORITY_PYUSECASE_IDLE)
        else:
            self.idleHandler = None

    def disableIdleHandlers(self):
        # If we aren't replaying, we need to accept user input. So we have to block the idle handlers here
        if not self.isActive():
            self._disableIdleHandlers()

    def _disableIdleHandlers(self):
        if self.idleHandler is not None:
            gobject.source_remove(self.idleHandler)
            self.idleHandler = None

    def reenableIdleHandlers(self):
        if self.idleHandler is None and not self.isActive():
            if self.readingEnabled:
                self.enableReplayHandler()
            else:
                self.tryAddDescribeHandler()

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
        if self.uiMap:
            self.uiMap.monitorNewWindows()
        if self.loggerActive:
            gtklogger.describeNewWindows()

    def describeAndRun(self):
        self.handleNewWindows()
        if self.readingEnabled:
            self.readingEnabled = self.runNextCommand()
            if not self.readingEnabled:
                self.tryAddDescribeHandler()
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
