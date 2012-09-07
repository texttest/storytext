
"""
The idea of this module is to implement a generic record/playback tool for GTK GUIs that
will create scripts in terms of the domain language. These will then be much more stable
than traditional such tools that create complicated Tcl scripts with lots of references
to pixel positions etc., which tend to be extremely brittle if the GUI is updated.
"""

import storytext.guishared, storytext.replayer
import widgetadapter, simulator, describer, treeviewextract, gtk, gobject, os, logging, sys, time
from ordereddict import OrderedDict

interceptionModules = [ simulator, treeviewextract ]
# If hildon can be imported at all, chances are we want to use it...
# Add in the support for hildon widgets
try:
    import hildontoolkit
    hildontoolkit.addHildonSupport()
    interceptionModules.append(hildontoolkit)
except ImportError:
    pass


PRIORITY_STORYTEXT_IDLE = describer.PRIORITY_STORYTEXT_IDLE


class ScriptEngine(storytext.guishared.ScriptEngine):
    eventTypes = simulator.eventTypes
    signalDescs = { 
        "row-activated" : "double-clicked row",
        "changed.selection" : "clicked on row",
        "delete-event": "closed",
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
        storytext.guishared.ScriptEngine.__init__(self, universalLogging=universalLogging, **kw)
        describer.setMonitoring(universalLogging)
        if self.uiMap or describer.isEnabled():
            self.performInterceptions()
            
    def createUIMap(self, uiMapFiles):
        if uiMapFiles:
            return simulator.UIMap(self, uiMapFiles)
        
    def addUiMapFiles(self, uiMapFiles):
        if self.uiMap:
            self.uiMap.readFiles(uiMapFiles)
        else:
            self.uiMap = simulator.UIMap(self, uiMapFiles)
        if self.replayer:
            self.replayer.addUiMap(self.uiMap)
        if not describer.isEnabled():
            self.performInterceptions()

    def performInterceptions(self):
        eventTypeReplacements = {}
        for mod in interceptionModules:
            eventTypeReplacements.update(mod.performInterceptions())
        for index, (widgetClass, currEventClasses) in enumerate(self.eventTypes):
            if widgetClass in eventTypeReplacements:
                self.eventTypes[index] = eventTypeReplacements[widgetClass], currEventClasses
                
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
    def createExistingShortcutBox(self):
        buttonbox = gtk.HBox()
        label = gtk.Label("Shortcuts:")
        buttonbox.pack_start(label, expand=False, fill=False)
        for name, script in self.replayer.getShortcuts():
            self.addShortcutButton(buttonbox, name, script)
        label.show()
        return buttonbox

    def addNewButton(self, buttonbox):
        newButton = gtk.Button()
        newButton.set_use_underline(1)
        newButton.set_label("_New")
        self.monitorSignal("create new shortcut", "clicked", newButton)
        newButton.connect("clicked", self.createShortcut, buttonbox)
        newButton.show()
        buttonbox.pack_start(newButton, expand=False, fill=False)

    def addShortcutButton(self, buttonbox, name, script):
        button = gtk.Button()
        button.set_use_underline(1)
        button.set_label(name)
        self.monitorSignal(name, "clicked", button)
        button.connect("clicked", self.replayShortcut, script)
        button.show()
        buttonbox.add(button)

    def addStopControls(self, buttonbox, existingbox):
        label = gtk.Label("Recording shortcut named:")
        buttonbox.pack_start(label, expand=False, fill=False)
        entry = gtk.Entry()
        entry.set_name("Shortcut Name")
        self.monitorSignal("set shortcut name to", "changed", entry)
        buttonbox.pack_start(entry, expand=False, fill=False)
        stopButton = gtk.Button()
        stopButton.set_use_underline(1)
        stopButton.set_label("S_top")
        self.monitorSignal("stop recording", "clicked", stopButton)
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
                replayScript = storytext.replayer.ReplayScript(newScriptName, ignoreComments=True)
                self.addShortcutButton(existingbox, buttonName, replayScript)
            self.replaceAutoRecordingForShortcut(script)

    def replayShortcut(self, button, script, *args):
        self.replayer.addScript(script, enableReading=True)
        if len(self.recorder.scripts):
            self.recorder.suspended = 1
            script.addExitObserver(self.recorder)

    def getTmpShortcutName(self):
        storytextDir = os.environ["STORYTEXT_HOME"]
        if not os.path.isdir(storytextDir):
            os.makedirs(storytextDir)
        return os.path.join(storytextDir, "new_shortcut." + str(os.getpid()))

    def getShortcutFileName(self, buttonName):
        return os.path.join(os.environ["STORYTEXT_HOME"], buttonName.replace(" ", "_") + ".shortcut")

    def createReplayer(self, universalLogging=False, **kw):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder, **kw)
                                
    def _createSignalEvent(self, eventName, signalName, widget, argumentParseData):
        stdSignalName = signalName.replace("_", "-")
        eventClasses = self.findEventClassesFor(widget) + simulator.universalEventClasses
        for eventClass in eventClasses:
            if eventClass.canHandleEvent(widget, stdSignalName, argumentParseData):
                return eventClass(eventName, widget, argumentParseData)

        if simulator.fallbackEventClass.widgetHasSignal(widget, stdSignalName):
            return simulator.fallbackEventClass(eventName, widget, stdSignalName)

    def getDescriptionInfo(self):
        return "PyGTK", "gtk", "signals", "http://library.gnome.org/devel/pygtk/stable/class-gtk"

    def addSignals(self, classes, widgetClass, currEventClasses, module):
        try:
            widget = widgetadapter.WidgetAdapter(widgetClass())
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
        return describer.Describer.supportedWidgets


# Use the GTK idle handlers instead of a separate thread for replay execution
class UseCaseReplayer(storytext.guishared.IdleHandlerUseCaseReplayer):
    def __init__(self, *args, **kw):
        storytext.guishared.IdleHandlerUseCaseReplayer.__init__(self, *args, **kw)
        # Anyone calling events_pending doesn't mean to include our logging events
        # so we intercept it and return the right answer for them...
        self.orig_events_pending = gtk.events_pending
        gtk.events_pending = self.events_pending

    def addUiMap(self, uiMap):
        self.uiMap = uiMap
        if not self.loggerActive:
            self.tryAddDescribeHandler()
        
    def makeDescribeHandler(self, method):
        return gobject.idle_add(method, priority=describer.PRIORITY_STORYTEXT_IDLE)
            
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
        return gobject.timeout_add(milliseconds, method, priority=describer.PRIORITY_STORYTEXT_REPLAY_IDLE)

    def makeIdleReplayHandler(self, method):
        return gobject.idle_add(method, priority=describer.PRIORITY_STORYTEXT_REPLAY_IDLE)

    def shouldMonitorWindow(self, window):
        hint = window.get_type_hint()
        if hint == gtk.gdk.WINDOW_TYPE_HINT_TOOLTIP or hint == gtk.gdk.WINDOW_TYPE_HINT_COMBO:
            return False
        elif isinstance(window.child, gtk.Menu) and isinstance(window.child.get_attach_widget(), gtk.ComboBox):
            return False
        else:
            return True

    def findWindowsForMonitoring(self):
        return filter(self.shouldMonitorWindow, gtk.window_list_toplevels())

    def describeNewWindow(self, window):
        if window.get_property("visible"):
            describer.describeNewWindow(window)

    def callReplayHandlerAgain(self, *args):
        return True # GTK's way of saying the handle should come again

    def runMainLoopWithReplay(self):
        while gtk.events_pending():
            gtk.main_iteration()
        if self.delay:
            time.sleep(self.delay)
        if self.isActive():
            self.describeAndRun()
