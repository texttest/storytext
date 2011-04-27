
""" Main entry point for simulator functionality """

import baseevents, windowevents, filechooserevents, treeviewevents, miscevents, gtk, usecase.guishared

performInterceptions = miscevents.performInterceptions
origDialog = gtk.Dialog
origFileChooserDialog = gtk.FileChooserDialog    

class DialogHelper:
    def tryMonitor(self):
        if self.uiMap.scriptEngine.recorderActive():
            self.connect_for_real = self.connect
            self.connect = self.store_connect
            self.disconnect_for_real = self.disconnect
            handlerAttrs = [ "disconnect", "handler_is_connected", "handler_disconnect",
                             "handler_block", "handler_unblock" ]
            for attrName in handlerAttrs:
                setattr(self, attrName, self.handlerWrap(attrName))
            
    def store_connect(self, signalName, *args):
        return windowevents.ResponseEvent.storeApplicationConnect(self, signalName, *args)

    def handlerWrap(self, attrName):
        method = getattr(self, attrName)
        def wrapped_method(handler):
            return method(self.handlers[handler])
        return wrapped_method

    def connect_and_store(self, *args):
        self.handlers.append(self.connect_for_real(*args))

    def run(self):
        if gtk.main_level() == 0:
            # Dialog.run can be used instead of the mainloop, don't interfere then
            return origDialog.run(self)
        
        origModal = self.get_modal()
        self.set_modal(True)
        self.dialogRunLevel += 1
        self.uiMap.monitorAndStoreWindow(self)
        self.connect_for_real("response", self.runResponse)
        self.show_all()
        self.response_received = None
        while self.response_received is None:
            self.uiMap.scriptEngine.replayer.runMainLoopWithReplay()

        self.dialogRunLevel -= 1
        self.set_modal(origModal)
        return self.response_received

    def runResponse(self, dialog, response):
        self.response_received = response
        

class Dialog(DialogHelper, origDialog):
    uiMap = None
    def __init__(self, *args, **kw):
        origDialog.__init__(self, *args, **kw)
        self.dialogRunLevel = 0
        self.handlers = []
        self.tryMonitor()
    

class FileChooserDialog(DialogHelper, origFileChooserDialog):
    uiMap = None
    def __init__(self, *args, **kw):
        origFileChooserDialog.__init__(self, *args, **kw)
        self.dialogRunLevel = 0
        self.handlers = []
        self.tryMonitor()


class UIMap(usecase.guishared.UIMap):
    ignoreWidgetTypes = [ "Label" ]
    def __init__(self, *args): 
        usecase.guishared.UIMap.__init__(self, *args)
        gtk.Dialog = Dialog
        Dialog.uiMap = self
        gtk.FileChooserDialog = FileChooserDialog
        FileChooserDialog.uiMap = self
        gtk.quit_add(1, self.fileHandler.write) # Write changes to the GUI map when the application exits
    
    def monitorChildren(self, widget, *args, **kw):
        if widget.getName() != "Shortcut bar" and \
               not widget.isInstanceOf(gtk.FileChooser) and not widget.isInstanceOf(gtk.ToolItem):
            usecase.guishared.UIMap.monitorChildren(self, widget, *args, **kw)

    def monitorWindow(self, window):
        if window.isInstanceOf(origDialog):
            # Do the dialog contents before we do the dialog itself. This is important for FileChoosers
            # as they have things that use the dialog signals
            self.logger.debug("Monitoring children for dialog with title " + repr(window.getTitle()))
            self.monitorChildren(window, excludeWidgets=self.getResponseWidgets(window, window.action_area))
            self.monitorWidget(window)
            windowevents.ResponseEvent.connectStored(window)
        else:
            usecase.guishared.UIMap.monitorWindow(self, window)

    def getResponseWidgets(self, dialog, widget):
        widgets = []
        for child in widget.get_children():
            if dialog.get_response_for_widget(child) != gtk.RESPONSE_NONE:
                widgets.append(child)
        return widgets

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
