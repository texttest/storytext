
"""
The idea of this module is to implement a generic record/playback tool for GTK GUIs that
will create scripts in terms of the domain language. These will then be much more stable
than traditional such tools that create complicated Tcl scripts with lots of references
to pixel positions etc., which tend to be extremely brittle if the GUI is updated.

It is based on the generic usecase.py, read the documentation there too.

The instrumentation that was necessary here up until version 3.0 is still present
in the ScriptEngine class for back-compatibility but is no longer the expected way to proceed.
Instead, it works by traversing the GUI objects downwards each time an idle handler is called,
finding widgets, recording actions on them and then asking the user for names at the end.

GUI shortcuts

The only reason to import this module in application code now is to call the method gtkusecase.createShortcutBar,
which will return a gtk.HBox allowing the user to dynamically record multiple clicks and make extra buttons
appear on this bar so that they can be created. Such shortcuts will be recorded in the directory indicated
by USECASE_HOME (defaulting to ~/usecases). Also, where a user makes a sequence of clicks which correspond to
an existing shortcut, this will be recorded as the shortcut name.

To see this in action, try out the video store example.
"""

import baseevents, windowevents, filechooserevents, treeviewevents, miscevents
import guiusecase, usecase, gtklogger, gtktreeviewextract, gtk, gobject, os, logging, sys
from ndict import seqdict


PRIORITY_PYUSECASE_IDLE = gtklogger.PRIORITY_PYUSECASE_IDLE
version = usecase.version

# Useful to have at module level as can't really be done externally
def createShortcutBar(uiMapFiles=[]):
    if not usecase.scriptEngine:
        usecase.scriptEngine = ScriptEngine(universalLogging=False, uiMapFiles=uiMapFiles)
    elif uiMapFiles:
        usecase.scriptEngine.addUiMapFiles(uiMapFiles)
    return usecase.scriptEngine.createShortcutBar()
        

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
            windowevents.ResponseEvent.storeHandler(self, handler, args=args)
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


class UIMap(guiusecase.UIMap):
    ignoreWidgetTypes = [ "Label" ]
    def __init__(self, *args): 
        guiusecase.UIMap.__init__(self, *args)
        self.storedEvents = set()
        gtk.Dialog = Dialog
        Dialog.uiMap = self
        gtk.FileChooserDialog = FileChooserDialog
        FileChooserDialog.uiMap = self
        gtk.quit_add(1, self.fileHandler.write) # Write changes to the GUI map when the application exits
        
    def monitorDialog(self, dialog):
        if self.monitorWidget(dialog):
            self.logger.debug("Picked up file-monitoring for dialog '" + self.getSectionName(dialog) + 
                              "', blocking instrumentation")
            self.scriptEngine.blockInstrumentation(dialog)
            return True
        else:
            return False
                
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
        if isinstance(widget, gtk.MenuItem):
            child = widget.get_child()
            # "child" is normally a gtk.AccelLabel, but in theory it could be anything
            if isinstance(child, gtk.Label):
                return child.get_text()
        elif hasattr(widget, "get_label"):
            return widget.get_label()
            
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
        self.logger.debug("Storing instrumented event for section '" + sectionName + "'")
        eventName = event.name
        self.storedEvents.add(eventName)
        if self.fileHandler.storeInfo(sectionName, event.getUiMapSignature(), 
                                      eventName, addToReadParser=len(self.fileHandler.writeParsers) > 1):
            self.changed = True
 
    def findPossibleSectionNames(self, widget):
        return [ "Name=" + widget.get_name(), "Title=" + str(self.getTitle(widget)), 
                 "Label=" + str(self.getLabel(widget)) ]

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

    def tryAutoInstrument(self, eventName, signature, signaturesInstrumented, *args):
        signature = signature.replace("notify-", "notify::")
        if eventName in self.storedEvents:
            signaturesInstrumented.add(signature)
            return False
        else:
            return guiusecase.UIMap.tryAutoInstrument(self, eventName, signature, signaturesInstrumented, *args)
                   
    def autoInstrument(self, eventName, signalName, widget, argumentParseData, widgetType):
        if argumentParseData and isinstance(widget, gtk.TreeView):
            event = self.makeTreeViewEvent(eventName, widget, argumentParseData, signalName)
            if event:
                self.scriptEngine._addEventToScripts(event, autoGenerated=True)
                return True
        elif self.widgetHasSignal(widget, signalName):
            return guiusecase.UIMap.autoInstrument(self, eventName, signalName, widget, argumentParseData)
        else:
            return False
    
    def splitParseData(self, argumentParseData):
        if argumentParseData.endswith(".true") or argumentParseData.endswith(".false"):
            columnName, relevantState = argumentParseData.rsplit(".", 1)
            return columnName, relevantState == "true"
        else:
            return argumentParseData, None

    def makeTreeViewEvent(self, eventName, widget, argumentParseData, signalName):
        if signalName == "changed" and argumentParseData == "selection":
            return treeviewevents.TreeSelectionEvent(eventName, widget, widget.get_selection())
        
        columnName, relevantState = self.splitParseData(argumentParseData)
        column = self.findTreeViewColumn(widget, columnName)
        if not column:
            raise usecase.UseCaseScriptError, "Could not find column with name " + repr(columnName)

        if signalName == "clicked":
            return treeviewevents.TreeColumnClickEvent(eventName, widget, column)
        elif signalName == "toggled":
            renderer = self.findRenderer(column, gtk.CellRendererToggle)
            return treeviewevents.CellToggleEvent(eventName, widget, renderer, column, relevantState)
        elif signalName == "edited":
            renderer = self.findRenderer(column, gtk.CellRendererText)
            return treeviewevents.CellEditEvent(eventName, widget, renderer, column)
        else:
            # If we don't know, create a basic event on the column
            return self.scriptEngine._createSignalEvent(eventName, signalName, column, widget)

    def findTreeViewColumn(self, widget, columnName):
        for column in widget.get_columns():
            if treeviewevents.getColumnName(column) == columnName:
                return column

    def findRenderer(self, column, cls):
        for renderer in column.get_cell_renderers():
            if isinstance(renderer, cls):
                return renderer

    def monitorChildren(self, widget, *args, **kw):
        if hasattr(widget, "get_children") and widget.get_name() != "Shortcut bar" and \
               not isinstance(widget, gtk.FileChooser) and not isinstance(widget, gtk.ToolItem):
            for child in widget.get_children():
                self.monitor(child, *args, **kw)

    def monitorWindow(self, window):
        if window not in self.windows:
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


class ScriptEngine(guiusecase.ScriptEngine):
    eventTypes = [
        (gtk.Button           , [ baseevents.SignalEvent ]),
        (gtk.ToolButton       , [ baseevents.SignalEvent ]),
        (gtk.MenuItem         , [ miscevents.MenuItemSignalEvent ]),
        (gtk.CheckMenuItem    , [ miscevents.MenuActivateEvent ]),
        (gtk.ToggleButton     , [ miscevents.ActivateEvent ]),
        (gtk.ToggleToolButton , [ miscevents.ActivateEvent ]),
        (gtk.ComboBoxEntry    , []), # just use the entry, don't pick up ComboBoxEvents
        (gtk.ComboBox         , [ miscevents.ComboBoxEvent ]),
        (gtk.Entry            , [ miscevents.EntryEvent, 
                                  baseevents.SignalEvent ]),
        (gtk.FileChooser      , [ filechooserevents.FileChooserFileSelectEvent, 
                                  filechooserevents.FileChooserFolderChangeEvent, 
                                  filechooserevents.FileChooserEntryEvent ]),
        (gtk.Dialog           , [ windowevents.ResponseEvent, 
                                  windowevents.DeletionEvent ]),
        (gtk.Window           , [ windowevents.DeletionEvent ]),
        (gtk.Notebook         , [ miscevents.NotebookPageChangeEvent ]),
        (gtk.Paned            , [ miscevents.PaneDragEvent ]),
        (gtk.TreeView         , [ treeviewevents.RowActivationEvent, 
                                  treeviewevents.TreeSelectionEvent, 
                                  treeviewevents.RowExpandEvent, 
                                  treeviewevents.RowCollapseEvent, 
                                  treeviewevents.RowRightClickEvent, 
                                  treeviewevents.CellToggleEvent,
                                  treeviewevents.CellEditEvent, 
                                  treeviewevents.TreeColumnClickEvent ])
]
    signalDescs = { 
        "row-activated" : "double-clicked row",
        "changed.selection" : "clicked on row",
        "delete-event": "closed",
        "notify::position": "dragged separator", 
        "toggled.true": "checked",
        "toggled.false": "unchecked",
        "button-press-event": "right-clicked row",
        "current-name-changed": "filename changed"
        }
    columnSignalDescs = {
        "toggled.true": "checked box in column",
        "toggled.false": "unchecked box in column",
        "edited": "edited cell in column",
        "clicked": "clicked column header"
        }
    def __init__(self, universalLogging=True, **kw):
        guiusecase.ScriptEngine.__init__(self, universalLogging=universalLogging, **kw)
        self.dialogsBlocked = []
        gtklogger.setMonitoring(universalLogging)
        if self.uiMap or gtklogger.isEnabled():
            gtktreeviewextract.performInterceptions()
            miscevents.performInterceptions()

    def createUIMap(self, uiMapFiles):
        if uiMapFiles:
            return UIMap(self, uiMapFiles)
        
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
    
    def monitorSignal(self, eventName, signalName, widget, argumentParseData=None, autoGenerated=False):
        if widget not in self.dialogsBlocked:
            guiusecase.ScriptEngine.monitorSignal(self, eventName, signalName, widget, argumentParseData, autoGenerated)

    def monitor(self, eventName, selection):
        if self.active():
            stdName = self.standardName(eventName)
            tree_view = selection.get_tree_view()
            stateChangeEvent = treeviewevents.TreeSelectionEvent(stdName, tree_view, selection)
            self._addEventToScripts(stateChangeEvent)

    def monitorRightClicks(self, eventName, widget):
        if self.active():
            stdName = self.standardName(eventName)
            if isinstance(widget, gtk.TreeView):
                rightClickEvent = treeviewevents.RowRightClickEvent(stdName, widget)
            else:
                rightClickEvent = baseevents.RightClickEvent(stdName, widget)
            self._addEventToScripts(rightClickEvent)
    
    def monitorExpansion(self, treeView, expandDescription, collapseDescription=""):
        if self.active():
            expandName = self.standardName(expandDescription)
            expandEvent = treeviewevents.RowExpandEvent(expandName, treeView)
            self._addEventToScripts(expandEvent)
            if collapseDescription:
                collapseName = self.standardName(collapseDescription)
                collapseEvent = treeviewevents.RowCollapseEvent(collapseName, treeView)
                self._addEventToScripts(collapseEvent)        

    def registerEntry(self, entry, description):
        if self.active():
            stateChangeName = self.standardName(description)
            entryEvent = miscevents.EntryEvent(stateChangeName, entry)
            if self.recorderActive():
                entryEvent.widget.connect("activate", self.recorder.writeEvent, entryEvent)
            self._addEventToScripts(entryEvent)

    def registerComboBox(self, combobox, description):
        if self.active():
            stateChangeName = self.standardName(description)
            event = miscevents.ComboBoxEvent(stateChangeName, combobox)
            self._addEventToScripts(event)

    def registerPaned(self, paned, description):
        if self.active():
            stateChangeName = self.standardName(description)
            event = miscevents.PaneDragEvent(stateChangeName, paned)
            self._addEventToScripts(event)

    def registerToggleButton(self, button, checkDescription, uncheckDescription = ""):
        if self.active():
            if isinstance(button, gtk.CheckMenuItem):
                eventClass = miscevents.MenuActivateEvent
            else:
                eventClass = miscevents.ActivateEvent
            checkChangeName = self.standardName(checkDescription)
            checkEvent = eventClass(checkChangeName, button, True)
            self._addEventToScripts(checkEvent)
            if uncheckDescription:
                uncheckChangeName = self.standardName(uncheckDescription)
                uncheckEvent = eventClass(uncheckChangeName, button, False)
                self._addEventToScripts(uncheckEvent)

    def registerCellToggleButton(self, renderer, checkDescription, column, parentTreeView, uncheckDescription=""):
        if self.active():
            checkChangeName = self.standardName(checkDescription)
            checkEvent = treeviewevents.CellToggleEvent(checkChangeName, parentTreeView, renderer, column, True)
            self._addEventToScripts(checkEvent)
            if uncheckDescription:
                uncheckChangeName = self.standardName(uncheckDescription)
                uncheckEvent = treeviewevents.CellToggleEvent(uncheckChangeName, parentTreeView, renderer, column, False)
                self._addEventToScripts(uncheckEvent)

    def registerCellEdit(self, renderer, description, column, parentTreeView):
        if self.active():
            stdName = self.standardName(description)
            event = treeviewevents.CellEditEvent(stdName, parentTreeView, renderer, column)
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
            if action == gtk.FILE_CHOOSER_ACTION_OPEN:
                event = filechooserevents.FileChooserFileSelectEvent(stdName, fileChooser)
            elif action == gtk.FILE_CHOOSER_ACTION_SAVE:
                event = filechooserevents.FileChooserEntryEvent(stdName, fileChooser)
                
            if event:
                self._addEventToScripts(event)
            self.registerFolderChange(fileChooser, folderChangeDesc)
             
    def registerFolderChange(self, fileChooser, description):
        stdName = self.standardName(description)
        event = filechooserevents.FileChooserFolderChangeEvent(stdName, fileChooser)
        self._addEventToScripts(event)
        return event

    def monitorNotebook(self, notebook, description):
        if self.active():
            stateChangeName = self.standardName(description)
            event = miscevents.NotebookPageChangeEvent(stateChangeName, notebook)
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
            self.replaceAutoRecordingForShortcut(script)

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
        guiusecase.ScriptEngine._addEventToScripts(self, event, autoGenerated)
        
    def _createSignalEvent(self, eventName, signalName, widget, argumentParseData):
        stdSignalName = signalName.replace("_", "-")
        for eventClass in self.findEventClassesFor(widget):
            if eventClass is not baseevents.SignalEvent and eventClass.getAssociatedSignal(widget) == stdSignalName:
                return eventClass(eventName, widget, argumentParseData)
        
        try:
            widget.get_property("sensitive")
        except:
            raise usecase.UseCaseScriptError, "Cannot create events for " + widget.__class__.__name__ + \
                ", it doesn't support basic widget properties"
        return self._createGenericSignalEvent(signalName, eventName, widget)

    def _createGenericSignalEvent(self, signalName, *args):
        for eventClass in [ baseevents.LeftClickEvent, baseevents.RightClickEvent ]:
            if eventClass.signalName == signalName:
                return eventClass(*args)

        newArgs = args + (signalName,)
        return baseevents.SignalEvent(*newArgs)

    def getDescriptionInfo(self):
        return "PyGTK", "gtk", "signals", "http://library.gnome.org/devel/pygtk/stable/class-gtk"

    def addSignals(self, classes, widgetClass, currEventClasses, module):
        try:
            widget = widgetClass()
        except:
            widget = None
        signalNames = set()
        for eventClass in currEventClasses:
            try:
                className = self.getClassName(eventClass.getClassWithSignal(), module)
                classes[className] = [ eventClass.signalName ]
            except:
                if widget:
                    signalNames.add(eventClass.getAssociatedSignal(widget))
                else:
                    signalNames.add(eventClass.signalName)
        className = self.getClassName(widgetClass, module)
        classes[className] = sorted(signalNames)

    def getSupportedLogWidgets(self):
        return gtklogger.Describer.supportedWidgets


# Use the GTK idle handlers instead of a separate thread for replay execution
class UseCaseReplayer(guiusecase.UseCaseReplayer):
    def __init__(self, *args):
        guiusecase.UseCaseReplayer.__init__(self, *args)
        # Anyone calling events_pending doesn't mean to include our logging events
        # so we intercept it and return the right answer for them...
        self.orig_events_pending = gtk.events_pending
        gtk.events_pending = self.events_pending

    def addUiMap(self, uiMap):
        self.uiMap = uiMap
        if not self.loggerActive:
            self.tryAddDescribeHandler()
        
    def makeDescribeHandler(self, method):
        return gobject.idle_add(method, priority=gtklogger.PRIORITY_PYUSECASE_IDLE)
            
    def tryRemoveDescribeHandler(self):
        if not self.isMonitoring() and not self.readingEnabled: # pragma: no cover - cannot test code with replayer disabled
            self.logger.debug("Disabling all idle handlers")
            self._disableIdleHandlers()
            if self.uiMap:
                self.uiMap.windows = [] # So we regenerate everything next time around

    def events_pending(self): # pragma: no cover - cannot test code with replayer disabled
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

    def removeHandler(self, handler):
        gobject.source_remove(handler)

    def makeTimeoutReplayHandler(self, method, milliseconds):
        return gobject.timeout_add(milliseconds, method, priority=gtklogger.PRIORITY_PYUSECASE_REPLAY_IDLE)

    def makeIdleReplayHandler(self, method):
        return gobject.idle_add(method, priority=gtklogger.PRIORITY_PYUSECASE_REPLAY_IDLE)

    def shouldMonitorWindow(self, window):
        hint = window.get_type_hint()
        if hint == gtk.gdk.WINDOW_TYPE_HINT_TOOLTIP:
            return False
        elif isinstance(window.child, gtk.Menu) and isinstance(window.child.get_attach_widget(), gtk.ComboBox):
            return False
        else:
            return True

    def findWindowsForMonitoring(self):
        return filter(self.shouldMonitorWindow, gtk.window_list_toplevels())

    def describeNewWindow(self, window):
        if window.get_property("visible"):
            gtklogger.describeNewWindow(window)

    def callHandleAgain(self):
        return True # GTK's way of saying the handle should come again
