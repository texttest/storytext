
""" Main entry point for simulator functionality """

import baseevents, windowevents, filechooserevents, treeviewevents, miscevents, gtk, guiusecase

performInterceptions = miscevents.performInterceptions
origDialog = gtk.Dialog
origFileChooserDialog = gtk.FileChooserDialog    

class DialogHelper:
    def tryMonitor(self):
        self.doneMonitoring = self.doMonitoring()
        if self.doneMonitoring:
            self.connect = self.connect_after_monitor

    def set_name(self, *args):
        origDialog.set_name(self, *args)
        if not self.doneMonitoring:
            self.doMonitoring()
            self.connect = self.connect_after_monitor

    def doMonitoring(self):
        return self.uiMap.monitorDialog(self)
            
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
        gtk.Dialog = Dialog
        Dialog.uiMap = self
        gtk.FileChooserDialog = FileChooserDialog
        FileChooserDialog.uiMap = self
        gtk.quit_add(1, self.fileHandler.write) # Write changes to the GUI map when the application exits
        
    def monitorDialog(self, dialog):
        adaptedDialog = guiusecase.WidgetAdapter.adapt(dialog)
        if self.monitorWidget(adaptedDialog):
            self.logger.debug("Picked up file-monitoring for dialog '" + self.getSectionName(adaptedDialog))
            return True
        else:
            return False
                             
    def tryAutoInstrument(self, eventName, signature, signaturesInstrumented, *args):
        signature = signature.replace("notify-", "notify::")
        return guiusecase.UIMap.tryAutoInstrument(self, eventName, signature, signaturesInstrumented, *args)
    
    def monitorChildren(self, widget, *args, **kw):
        if widget.getName() != "Shortcut bar" and \
               not widget.isInstanceOf(gtk.FileChooser) and not widget.isInstanceOf(gtk.ToolItem):
            guiusecase.UIMap.monitorChildren(self, widget)

    def monitorWindow(self, window):
        if window.isInstanceOf(origDialog):
            # We've already done the dialog itself when it was empty, only look at the stuff in its vbox
            # which may have been added since then...
            self.logger.debug("Monitoring children for dialog with title " + repr(window.getTitle()))
            return self.monitorChildren(window, excludeWidget=window.action_area)
        else:
            return guiusecase.UIMap.monitorWindow(self, window)

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
        (gtk.TextView         , [ miscevents.TextViewEvent ]),
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

universalEventClasses = [ baseevents.LeftClickEvent, baseevents.RightClickEvent ]
fallbackEventClass = baseevents.SignalEvent
