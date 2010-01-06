
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
import usecase, gtklogger, gtktreeviewextract, gtk, gobject, os, logging, sys
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


class WriteParserHandler:
    def __init__(self, fileName):
        self.fileName = fileName
        self.parser = ConfigParser(dict_type=seqdict)
        self.parser.read([ self.fileName ])
        self.changed = False

    def write(self):
        if self.changed:
            if not os.path.isdir(os.path.dirname(self.fileName)):
                os.makedirs(os.path.dirname(self.fileName))
            self.parser.write(open(self.fileName, "w"))
            self.changed = False

    def add_section(self, *args):
        self.changed = True
        self.parser.add_section(*args)

    def set(self, *args):
        self.changed = True
        self.parser.set(*args)

    def __getattr__(self, name):
        return getattr(self.parser, name)


class UIMap:
    ignoreWidgetTypes = [ "Label" ]
    def __init__(self, scriptEngine, uiMapFiles): 
        self.readFiles(uiMapFiles)
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
        # See top of file: uses the version from 2.6
        self.writeParsers = map(WriteParserHandler, uiMapFiles)
        if len(self.writeParsers) == 1:
            self.readParser = self.writeParsers[0]
        else:
            self.readParser = ConfigParser(dict_type=seqdict)
            self.readParser.read(uiMapFiles)
        
    def monitorDialog(self, dialog):
        if self.monitorWidget(dialog):
            self.logger.debug("Picked up file-monitoring for dialog '" + self.getSectionName(dialog) + 
                              "', blocking instrumentation")
            self.scriptEngine.blockInstrumentation(dialog)
            return True
        else:
            return False
                
    def write(self, *args):
        for parserHandler in self.writeParsers:
            parserHandler.write()

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
        self.logger.debug("Storing instrumented event for section '" + sectionName + "'")
        if not self.readParser.has_section(sectionName):
            self.writeParsers[-1].add_section(sectionName)
            if len(self.writeParsers) > 1:
                self.readParser.add_section(sectionName)

        eventName = event.name
        self.storedEvents.add(eventName)
        if self.storeInfo(sectionName, event.getUiMapSignature(), eventName, addToReadParser=True):
            self.changed = True

    def storeInfo(self, sectionName, signature, eventName, addToReadParser):
        signature = signature.replace("::", "-") # Can't store :: in ConfigParser unfortunately
        if not self.readParser.has_option(sectionName, signature):
            for writeParser in self.writeParsers:
                if writeParser.has_section(sectionName):
                    writeParser.set(sectionName, signature, eventName)
            if addToReadParser and len(self.writeParsers) > 1:
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
            return treeviewevents.TreeSelectionEvent(eventName, widget, widget.get_selection())
        
        columnName, relevantState = self.splitParseData(argumentParseData)
        column = self.findTreeViewColumn(widget, columnName)
        if not column:
            sys.stderr.write("ERROR in UI map file: Could not find column with name " + repr(columnName) + "\n")
            return

        if signalName == "clicked":
            return treeviewevents.TreeColumnClickEvent(eventName, widget, column)
        elif signalName == "toggled":
            renderer = self.findRenderer(column, gtk.CellRendererToggle)
            return treeviewevents.CellToggleEvent(eventName, widget, renderer, relevantState)
        elif signalName == "edited":
            renderer = self.findRenderer(column, gtk.CellRendererText)
            return treeviewevents.CellEditEvent(eventName, widget, renderer)
        else:
            # If we don't know, create a basic event on the column
            return self.scriptEngine._createSignalEvent(eventName, signalName, column, widget)

    def findTreeViewColumn(self, widget, columnName):
        for column in widget.get_columns():
            if treeviewevents.getColumnName(column).lower() == columnName:
                return column

    def findRenderer(self, column, cls):
        for renderer in column.get_cell_renderers():
            if isinstance(renderer, cls):
                return renderer

    def tryImproveSectionName(self, widget, section):
        if not section.startswith("Name="):
            newName = self.getSectionName(widget)
            if newName != section:
                return self.updateSectionName(section, newName)
        return section

    def findWriteParser(self, section):
        for parser in self.writeParsers:
            if parser.has_section(section):
                return parser

    def updateSectionName(self, section, newName):
        writeParser = self.findWriteParser(section)
        if not writeParser.has_section(newName):
            writeParser.add_section(newName)
        for name, value in self.readParser.items(section):
            writeParser.set(newName, name, value)
        writeParser.remove_section(section)
        return newName

    def instrumentFromMapFile(self, widget):
        widgetType = widget.__class__.__name__
        if widgetType in self.ignoreWidgetTypes:
            return set(), False
        signaturesInstrumented = set()
        autoInstrumented = False
        section = self.findSection(widget, widgetType)
        if section:
            section = self.tryImproveSectionName(widget, section)
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
            autoGenerated.append((command, widgetType, widgetDescription, signalName))
        return autoGenerated

    def storeNames(self, toStore):
        for ((command, widgetType, widgetDescription, signalName), eventName) in toStore:
            if not self.readParser.has_section(widgetDescription):
                self.writeParsers[-1].add_section(widgetDescription)
            self.storeInfo(widgetDescription, signalName, eventName, addToReadParser=False)
        self.write()

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
    defaultMapFile = os.path.join(usecase.ScriptEngine.usecaseHome, "ui_map.conf")
    def __init__(self, enableShortcuts=False, uiMapFiles=[ defaultMapFile ], universalLogging=True):
        self.uiMap = None
        if uiMapFiles:
            self.uiMap = UIMap(self, uiMapFiles)
        usecase.ScriptEngine.__init__(self, enableShortcuts, universalLogging=universalLogging)
        self.dialogsBlocked = []
        gtklogger.setMonitoring(universalLogging)
        if self.uiMap or gtklogger.isEnabled():
            gtktreeviewextract.performInterceptions()
            miscevents.performInterceptions()

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

    def registerCellToggleButton(self, renderer, checkDescription, parentTreeView, uncheckDescription=""):
        if self.active():
            checkChangeName = self.standardName(checkDescription)
            checkEvent = treeviewevents.CellToggleEvent(checkChangeName, parentTreeView, renderer, True)
            self._addEventToScripts(checkEvent)
            if uncheckDescription:
                uncheckChangeName = self.standardName(uncheckDescription)
                uncheckEvent = treeviewevents.CellToggleEvent(uncheckChangeName, parentTreeView, renderer, False)
                self._addEventToScripts(uncheckEvent)

    def registerCellEdit(self, renderer, description, parentTreeView):
        if self.active():
            stdName = self.standardName(description)
            event = treeviewevents.CellEditEvent(stdName, parentTreeView, renderer)
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
            commands = script.getRecordedCommands()
            autoGenerated = self.uiMap.getAutoGenerated(commands)
            if len(autoGenerated) > 0:
                autoGeneratedInfo = self.uiMap.parseAutoGenerated(autoGenerated)
                domainNameGUI = DomainNameGUI(autoGeneratedInfo, commands, self, parentWindow)
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
                domainNameGUI = DomainNameGUI(autoGeneratedInfo, commands, self)
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
        for eventClass in self.findEventClassesFor(widget):
            if eventClass is not baseevents.SignalEvent and eventClass.getAssociatedSignal(widget) == stdSignalName:
                return eventClass(eventName, widget, argumentParseData)
        
        return self._createGenericSignalEvent(signalName, eventName, widget)

    def _createGenericSignalEvent(self, signalName, *args):
        for eventClass in [ baseevents.LeftClickEvent, baseevents.RightClickEvent ]:
            if eventClass.signalName == signalName:
                return eventClass(*args)

        newArgs = args + (signalName,)
        return baseevents.SignalEvent(*newArgs)

    def getClassName(self, widgetClass):
        return "gtk." + widgetClass.__name__

    def addSignals(self, classes, widgetClass, currEventClasses):
        try:
            widget = widgetClass()
        except:
            widget = None
        signalNames = set()
        for eventClass in currEventClasses:
            try:
                classes[self.getClassName(eventClass.getClassWithSignal())] = [ eventClass.signalName ]
            except:
                if widget:
                    signalNames.add(eventClass.getAssociatedSignal(widget))
                else:
                    signalNames.add(eventClass.signalName)
        classes[self.getClassName(widgetClass)] = sorted(signalNames)

    def getFormatted(self, text, html, title):
        if html:
            return '<div class="Text_Header">' + title + "</div>\n" + \
                '<div class="Text_Normal">' + text + "</div>"
        else:
            return text

    def describeSupportedWidgets(self, html=False):
        intro = """The following lists the PyGTK widget types and the associated signals on them which 
PyUseCase %s is currently capable of recording and replaying. Any type derived from the listed
types is also supported.
""" % usecase.version
        print self.getFormatted(intro, html, "PyGTK Widgets and signals supported for record/replay")
        classes = {}
        for widgetClass, currEventClasses in self.eventTypes:
            if len(currEventClasses):
                self.addSignals(classes, widgetClass, currEventClasses)
        classNames = sorted(classes.keys())
        if html:
            self.writeHtmlTable(classNames, classes)
        else:
            self.writeAsciiTable(classNames, classes)

        logIntro = """
The following lists the PyGTK widget types whose status and changes PyUseCase %s is 
currently capable of monitoring and logging. Any type derived from the listed types 
is also supported but will only have features of the listed type described.
""" % usecase.version
        print self.getFormatted(logIntro, html, "PyGTK Widgets supported for automatic logging")
        classNames = [ self.getClassName(w) for w in gtklogger.Describer.supportedWidgets ]
        classNames.sort()
        if html:
            self.writeHtmlList(classNames)
        else:
            for className in classNames:
                print className

    def writeAsciiTable(self, classNames, classes):
        for className in classNames:
            print className.ljust(25) + ":", " , ".join(classes[className])

    def writeHtmlTable(self, classNames, classes):
        print '<div class="Text_Normal"><table border=1 cellpadding=1 cellspacing=1>'
        for className in classNames:
            print '<tr><td>' + self.getLink(className) + '</td><td><div class="Table_Text_Normal">' + \
                " , ".join(classes[className]) + "</div></td></tr>"
        print "</table></div>"

    def getLink(self, className):
        docName = className.replace(".", "").lower()
        return '<a class="Text_Link" href=http://library.gnome.org/devel/pygtk/stable/class-' + \
            docName + '.html>' + className + '</a>'

    def writeHtmlList(self, classNames):
        print '<div class="Text_Normal">'
        for className in classNames:
            print '<li>' + self.getLink(className)
        print '</div><div class="Text_Normal"><i>(Note that a textual version of this page can be auto-generated by running "pyusecase -s")</i></div>'


# Use the GTK idle handlers instead of a separate thread for replay execution
class UseCaseReplayer(usecase.UseCaseReplayer):
    def __init__(self, uiMap, universalLogging, recorder):
        self.readingEnabled = False
        self.uiMap = uiMap
        self.idleHandler = None
        self.loggerActive = universalLogging
        self.recorder = recorder
        self.delay = float(os.getenv("USECASE_REPLAY_DELAY", 0.0))
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
        self.idleHandler = self._enableReplayHandler(self.describeAndRun, 
                                                     priority=gtklogger.PRIORITY_PYUSECASE_REPLAY_IDLE)

    def _enableReplayHandler(self, *args, **kw):
        if self.delay:
            milliseconds = int(self.delay * 1000)
            return gobject.timeout_add(milliseconds, *args, **kw)
        else:
            return gobject.idle_add(*args, **kw)

    def shouldMonitorWindow(self, window):
        hint = window.get_type_hint()
        if hint == gtk.gdk.WINDOW_TYPE_HINT_TOOLTIP:
            return False
        elif isinstance(window.child, gtk.Menu) and isinstance(window.child.get_attach_widget(), gtk.ComboBox):
            return False
        else:
            return True

    def handleNewWindows(self):
        for window in gtk.window_list_toplevels():
            if self.shouldMonitorWindow(window):
                if self.uiMap and (self.isActive() or self.recorder.isActive()):
                    self.uiMap.monitorWindow(window)
                if self.loggerActive and window.get_property("visible"):
                    gtklogger.describeNewWindow(window)
        return True

    def describeAndRun(self):
        self.handleNewWindows()
        if self.readingEnabled:
            self.readingEnabled = self.runNextCommand()
            if not self.readingEnabled:
                self.idleHandler = None
                self.tryAddDescribeHandler()
                if not self.idleHandler and self.uiMap: # pragma: no cover - cannot test with replayer disabled
                    # End of shortcut: reset for next time
                    self.logger.debug("Shortcut terminated: Resetting UI map ready for next shortcut")
                    self.uiMap.windows = [] 
                    self.events = {}
        return self.readingEnabled


class DomainNameGUI:
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
    title = "Enter Usecase names for auto-recorded actions"
    def __init__(self, autoGenerated, commands, scriptEngine, parent=None):
        self.dialog = gtk.Dialog(self.title, parent, flags=gtk.DIALOG_MODAL)
        self.dialog.set_name("Name Entry Window")
        self.allEntries = seqdict()
        self.dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        contents = self.createTable(autoGenerated, scriptEngine)
        self.dialog.vbox.pack_start(contents, expand=True, fill=True)
        preview = self.createPreview(commands)
        self.dialog.vbox.pack_start(gtk.HSeparator())
        self.dialog.vbox.pack_start(preview, expand=True, fill=True)
        yesButton = self.dialog.add_button(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
        scriptEngine.monitorSignal("finish name entry editing", "response", self.dialog, gtk.RESPONSE_ACCEPT, autoGenerated=True)
        self.dialog.show_all()
        
    def createMarkupLabel(self, markup):
        label = gtk.Label()
        label.set_markup(markup)
        return label

    def activateEntry(self, *args):
        self.dialog.response(gtk.RESPONSE_ACCEPT)

    def getActionDescription(self, signalName, widgetType):
        desc = self.signalDescs.get(signalName)
        if desc:
            return desc
        if signalName == "activate":
            if "Entry" in widgetType:
                return "pressed Enter"
            else:
                return "selected"
        elif signalName == "changed":
            if "Entry" in widgetType:
                return "edited text"
            else:
                return "selected item"

        parts = signalName.split(".")
        if len(parts) == 1:
            return signalName.replace("-", " ")

        if parts[0] == "response":
            return parts[1]

        columnName = parts[1]
        remaining = parts[0]
        if remaining == "toggled":
            remaining = ".".join([ remaining, parts[-1] ])
        return self.columnSignalDescs.get(remaining, remaining) + " '" + columnName + "'"
        
    def splitAutoCommand(self, command):
        for cmd in self.allEntries.keys():
            if command.startswith(cmd):
                arg = command.replace(cmd, "")
                return cmd, arg
        return None, None

    def updatePreview(self, entry, data):
        buffer, lineNo, arg = data
        text = entry.get_text()
        toUse = "?"
        if text:
            toUse = text + arg 
        start = buffer.get_iter_at_line(lineNo)
        end = buffer.get_iter_at_line(lineNo + 1)
        buffer.delete(start, end)
        buffer.insert(start, toUse + "\n")

    def createPreview(self, commands):
        frame = gtk.Frame("Current Usecase Preview")
        view = gtk.TextView()
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_wrap_mode(gtk.WRAP_WORD)
        buffer = view.get_buffer()
        for ix, command in enumerate(commands):
            autoCmdName, autoArg = self.splitAutoCommand(command)
            if autoCmdName:
                buffer.insert(buffer.get_end_iter(), "?\n")
                entry = self.allEntries.get(autoCmdName)
                entry.connect("changed", self.updatePreview, (buffer, ix, autoArg))
            else:                
                buffer.insert(buffer.get_end_iter(), command + "\n")
        frame.add(view)
        return frame

    def createTable(self, autoGenerated, scriptEngine):
        table = gtk.Table(rows=len(autoGenerated) + 1, columns=4)
        table.set_col_spacings(20)
        headers = [ "Widget Type", "Identified By", "Action Performed", "Usecase Name" ]
        for col, header in enumerate(headers):
            table.attach(self.createMarkupLabel("<b><u>" + header + "</u></b>"), 
                         col, col + 1, 0, 1, xoptions=gtk.FILL)
        for rowIndex, (command, widgetType, widgetDesc, signalName) in enumerate(autoGenerated):
            table.attach(gtk.Label(widgetType), 0, 1, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL)
            actionDesc = self.getActionDescription(signalName, widgetType)
            table.attach(gtk.Label(widgetDesc), 1, 2, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL)
            table.attach(gtk.Label(actionDesc), 2, 3, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL)
            entry = gtk.Entry()
            scriptName = "enter usecase name for signal '" + signalName + "' on " + widgetType + " '" + widgetDesc + "' ="
            scriptEngine.monitorSignal(scriptName, "changed", entry, autoGenerated=True)
            entry.connect("activate", self.activateEntry)
            scriptEngine.monitorSignal("finish name entry editing by pressing <enter>", "activate", entry, autoGenerated=True)
            self.allEntries[command] = entry
            table.attach(entry, 3, 4, rowIndex + 1, rowIndex + 2)
        frame = gtk.Frame("Previously unseen actions: provide names for the interesting ones")
        frame.add(table)
        return frame

    def collectNames(self):
        names = [ entry.get_text() for entry in self.allEntries.values() ]
        self.dialog.destroy()
        return names
