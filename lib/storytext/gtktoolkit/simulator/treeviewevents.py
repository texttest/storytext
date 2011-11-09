
""" Wrappers for events around gtk.TreeView objects """

import baseevents, gtk, logging
from .. import treeviewextract
from storytext.definitions import UseCaseScriptError

class TreeColumnHelper:
    @classmethod
    def findColumn(cls, treeView, columnName):
        for column in treeView.get_columns():
            if cls.getColumnName(column) == columnName:
                return column
        raise UseCaseScriptError, "Could not find column with name " + repr(columnName)

    @staticmethod
    def getColumnName(column):
        name = column.get_data("name")
        if name:
            return name
        else:
            # PyGTK 2.16 has started returning None here...
            return column.get_title() or ""


class TreeColumnClickEvent(baseevents.SignalEvent):
    signalName = "clicked"
    def __init__(self, name, widget, argumentParseData):
        self.column = TreeColumnHelper.findColumn(widget, argumentParseData)
        baseevents.SignalEvent.__init__(self, name, widget)

    def connectRecord(self, method):
        self._connectRecord(self.column, method)
        
    @classmethod
    def getClassWithSignal(cls):
        return gtk.TreeViewColumn

    def getChangeMethod(self):
        return self.column.emit

    @classmethod
    def getAssociatedSignatures(cls, widget):
        signatures = []
        for column in widget.get_columns():
            if column.get_clickable():
                signatures.append(cls.signalName + "." + TreeColumnHelper.getColumnName(column))
        return signatures


class TreeViewEvent(baseevents.GtkEvent):
    def __init__(self, name, widget, *args):
        baseevents.GtkEvent.__init__(self, name, widget)
        self.indexer = TreeViewIndexer.getIndexer(widget)

    def _outputForScript(self, iter, *args):
        return self.name + " " + self.indexer.iter2string(iter)

    def _outputForScriptFromPath(self, path, *args):
        return self.name + " " + self.indexer.path2string(path)

    def getGenerationArguments(self, argumentString):
        return [ self.indexer.string2path(argumentString) ] + self.getTreeViewArgs()

    def getTreeViewArgs(self):
        return []

    def isRelevantSelection(self, prevEvent):
        return isinstance(prevEvent, TreeSelectionEvent) and self.widget is prevEvent.widget
   

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
        return self.isRelevantSelection(prevEvent) and self.isDeselectionUnder(prevEvent, path)

    def isDeselectionUnder(self, prevEvent, path):
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
        return self.isRelevantSelection(prevEvent)


class RowRightClickEvent(baseevents.RightClickEvent):
    def __init__(self, name, widget, *args):
        baseevents.RightClickEvent.__init__(self, name, widget)
        self.indexer = TreeViewIndexer.getIndexer(widget)
        
    def _outputForScript(self, event, *args):
        pathInfo = self.widget.get_path_at_pos(int(event.x), int(event.y))
        return self.name + " " + self.indexer.path2string(pathInfo[0])

    def getAreaToClick(self, argumentString):
        path = self.indexer.string2path(argumentString)
        return self.widget.get_cell_area(path, self.widget.get_column(0))


class CellEvent(TreeViewEvent):
    def __init__(self, name, widget, columnName, property):
        column = TreeColumnHelper.findColumn(widget, columnName)
        self.cellRenderer = self.findRenderer(column)
        self.extractor = treeviewextract.getExtractor(column, self.cellRenderer, property)
        TreeViewEvent.__init__(self, name, widget)

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

    @classmethod
    def findRenderer(cls, column):
        for renderer in column.get_cell_renderers():
            if isinstance(renderer, cls.getClassWithSignal()):
                return renderer

    @classmethod
    def getAssociatedSignatures(cls, widget):
        signatures = []
        for column in widget.get_columns():
            if cls.findRenderer(column):
                rootName = cls.signalName + "." + TreeColumnHelper.getColumnName(column)
                signatures += cls.getSignaturesFrom(rootName)
        return signatures
    
    @classmethod
    def getSignaturesFrom(cls, rootName):
        return [ rootName ]


class CellToggleEvent(CellEvent):
    signalName = "toggled"
    def __init__(self, name, widget, argumentParseData):
        columnName, stateStr = argumentParseData.rsplit(".", 1)
        self.relevantState = stateStr == "true"
        CellEvent.__init__(self, name, widget, columnName, "active")        
        
    @classmethod
    def getClassWithSignal(cls):
        return gtk.CellRendererToggle

    def shouldRecord(self, *args):
        return TreeViewEvent.shouldRecord(self, *args) and self.getValue(*args) == self.relevantState
    
    def getGenerationArguments(self, argumentString):
        path = TreeViewEvent.getGenerationArguments(self, argumentString)[0]
        return [ self.signalName, self.getPathAsString(path) ]

    @classmethod
    def getSignaturesFrom(cls, rootName):
        return [ rootName + ".true", rootName + ".false" ]



class CellEditEvent(CellEvent):
    signalName = "edited"
    def __init__(self, *args, **kw):
        CellEvent.__init__(self, property="text", *args, **kw)

    @classmethod
    def getClassWithSignal(cls):
        return gtk.CellRendererText

    def shouldRecord(self, renderer, path, new_text, *args):
        value = self.getValue(renderer, path)
        return TreeViewEvent.shouldRecord(self, renderer, path, *args) and new_text != str(value)
    
    def _connectRecord(self, widget, method):
        # Push our way to the front of the queue
        # We need to be able to tell when things have changed
        connectInfo = treeviewextract.cellRendererConnectInfo.get(widget, [])
        allArgs = [ info[1] for info in connectInfo ]
        for handler, args in connectInfo:
            if widget.handler_is_connected(handler):
                widget.disconnect(handler)
        CellEvent._connectRecord(self, widget, method)
        for args in allArgs:
            widget.connect(*args)

    def _outputForScript(self, path, new_text, *args):
        return CellEvent._outputForScript(self, path, new_text, *args) + " = " + new_text

    def getGenerationArguments(self, argumentString):
        oldName, newName = argumentString.split(" = ")
        path = TreeViewEvent.getGenerationArguments(self, oldName)[0]
        return [ self.signalName, self.getPathAsString(path), newName ]


class TreeSelectionEvent(baseevents.StateChangeEvent):
    def __init__(self, name, widget, *args):
        self.indexer = TreeViewIndexer.getIndexer(widget)
        self.selection = widget.get_selection()
        # cache these before calling base class constructor, or they get intercepted...
        self.unselect_iter = self.selection.unselect_iter
        self.select_iter = self.selection.select_iter
        self.prevSelected = []
        self.prevDeselections = []
        baseevents.StateChangeEvent.__init__(self, name, widget)

    @classmethod
    def getClassWithSignal(cls):
        return gtk.TreeSelection

    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "changed.selection" ]
        
    def connectRecord(self, method):
        def selection_disallowed(path):
            method(self.selection, path, self)
        # Must record event if the selection is rejected
        if isinstance(self.selection.set_select_function, treeviewextract.FunctionSelectWrapper):
            self.selection.set_select_function.fail_method = selection_disallowed
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
        if len(args) > 1 and isinstance(args[1], tuple):
            # from selection_disallowed above
            return not self.programmaticChange
        ret = baseevents.StateChangeEvent.shouldRecord(self, *args)
        if not ret:
            self.getStateDescription() # update internal stores for programmatic changes
        return ret

    def getProgrammaticChangeMethods(self):
        modelFilter, realModel = self.getModels()
        methods = [ self.selection.unselect_all, self.selection.select_all, \
                    self.selection.select_iter, self.selection.unselect_iter, \
                    self.selection.select_path, self.selection.unselect_path,self.selection.set_mode,
                    self.widget.set_model, self.widget.row_activated, self.widget.collapse_row,
                    realModel.remove, realModel.clear ]

        return methods

    def eventIsRelevant(self):
        return not self.isEmptyReselect() and not self.previousSelectionNowHidden()

    def isEmptyReselect(self):
        # The user has no way to re-select 0 rows, if this is generated, it's internal/programmatic
        return len(self.prevSelected) == 0 and self.selection.count_selected_rows() == 0

    def previousSelectionNowHidden(self):
        # We assume any change here that involves previously selected rows ceasing to be visible
        # implies that a row has been deselected by being hidden, i.e. programmatically
        modelFilter, realModel = self.getModels()
        if modelFilter:
            for rowName in self.prevSelected:
                try:
                    self.indexer.string2iter(rowName)
                except UseCaseScriptError:
                    return True

        return False

    def getStateDescription(self, *args):
        return self._getStateDescription(args, storeSelected=True)

    def previousIndex(self, iter):
        try:
            return self.prevSelected.index(iter)
        except ValueError:
            return len(self.prevSelected)

    def _getStateDescription(self, args, storeSelected=False):
        if args and isinstance(args[0], tuple):
            # selection function returned false...
            return self.indexer.path2string(args[0])

        newSelected = self.findSelectedIters()
        newSelected.sort(key=self.previousIndex)
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
            # Old set isn't a superset, so index cannot overflow "newSelected" here
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
        currStateDesc = self._getStateDescription(args[1:])
        if len(currStateDesc) > len(prevStateDesc):
            return currStateDesc.startswith(prevStateDesc)
        elif len(currStateDesc) > 0:
            oldSet = set(self.parseIterNames(prevStateDesc))
            newSet = set(self.parseIterNames(currStateDesc))
            return oldSet.issuperset(newSet)
        else:
            return False # always assume deselecting everything marks the beginning of a new conceptual action


# Class to provide domain-level lookup for rows in a tree. Convert paths to strings and back again
# Can't store rows on TreeModelFilters, store the underlying rows and convert them at the last minute
class TreeViewIndexer:
    allIndexers = {}
    @classmethod
    def getIndexer(cls, treeView):
        return cls.allIndexers.setdefault(treeView, cls(treeView))

    def __init__(self, treeview):
        self.givenModel = treeview.get_model()
        self.model = self.findModelToUse()
        self.logger = logging.getLogger("TreeModelIndexer")
        self.name2row = {}
        self.uniqueNames = {}
        self.rendererInfo = self.getFirstTextRenderer(treeview)
        self.extractor = None
        self.tryPopulateMapping()

    def tryPopulateMapping(self):
        if not self.extractor:
            self.extractor = treeviewextract.getTextExtractor(*self.rendererInfo)
            if self.extractor:
                self.model.foreach(self.rowInserted)
                self.model.connect("row-changed", self.rowInserted)

    def getFirstTextRenderer(self, treeview):
        for column in treeview.get_columns():
            for renderer in column.get_cell_renderers():
                if isinstance(renderer, gtk.CellRendererText):
                    return column, renderer
        return None, None

    def getValue(self, *args):
        return str(self.extractor.getValue(*args)).replace("\n", " / ")

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
            raise UseCaseScriptError, "Could not find row '" + name + "' in Tree View\nKnown names are " + repr(self.name2row.keys())
        else:
            raise UseCaseScriptError, "'" + name + "' in Tree View is ambiguous, could refer to " \
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
                raise UseCaseScriptError, "Row '" + name + "' is currently hidden and cannot be accessed"
        else:
            return path

    def rowInserted(self, model, path, iter):
        givenName = self.getValue(model, iter)
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
                if None not in parents:
                    parentNames = self.getNewNames(parents, newName)
                    for index, parentName in enumerate(parentNames):
                        self.logger.debug("Name from parents, setting row " + repr(indices[index]) + 
                                          " name to " + repr(parentName))
                        newNames[indices[index]] = parentName
                else:
                    # No other option, enumerate them and identify them by index
                    for index, row in enumerate(matchingRows):
                        newNames[indices[index]] = newName + " (" + str(index + 1) + ")"

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
