
""" Main entry point for simulator functionality """

import storytext.gtktoolkit.compat
import baseevents, windowevents, filechooserevents, treeviewevents, miscevents, gtk, gobject, storytext.guishared
import types, inspect, os
from threading import Thread
from storytext.gtktoolkit.widgetadapter import WidgetAdapter
from storytext import applicationEvent
from .. import treeviewextract
import xml.dom.minidom

performInterceptions = miscevents.performInterceptions
origDialog = gtk.Dialog
origFileChooserDialog = gtk.FileChooserDialog
origFileChooserWidget = gtk.FileChooserWidget
origBuilder = gtk.Builder

class DialogHelper(object):
    uiMap = None
    def initialise(self):
        self.dialogRunLevel = 0
        self.handlers = []
        self.tryMonitor()

    def tryMonitor(self):
        if self.uiMap.scriptEngine.active():
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
        def wrapped_handler(handler):
            return method(self.handlers[handler])
        return wrapped_handler

    def connect_and_store(self, signalName, method, *args):
        def wrapped_method(*methodargs, **kw):
            baseevents.DestroyIntercept.inResponseHandler = True
            try:
                method(*methodargs, **kw)
            finally:
                baseevents.DestroyIntercept.inResponseHandler = False
        self.handlers.append(self.connect_for_real(signalName, wrapped_method, *args))

    def run(self):
        if gtk.main_level() == 0 or not hasattr(self, "connect_for_real"):
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
        baseevents.GtkEvent.disableIntercepts(self)
        return self.response_received

    def runResponse(self, dialog, response):
        self.response_received = response
        

class FileChooserHelper(object):
    def __init__(self, action):
        dataMethod = self.getDataMethod(action)
        self.checkHandler = None
        self.latestData = None
        self.addCheckHandler(dataMethod, True)
        
    def addCheckHandler(self, *args):
        if self.checkHandler is None:
            self.checkHandler = gobject.idle_add(self.runCheck, *args)
            
    def getDataMethod(self, action):
        return self.get_current_folder if action == gtk.FILE_CHOOSER_ACTION_SAVE else self.get_filename
    
    def currentFolderChanged(self, widget, dataMethod):
        if dataMethod() != self.latestData:
            self.addCheckHandler(dataMethod, False)
        
    def loadingFromEmpty(self):
        return self.get_property("action") == gtk.FILE_CHOOSER_ACTION_OPEN and self.get_current_folder() and len(os.listdir(self.get_current_folder())) == 0
        
    def runCheck(self, dataMethod, initial):
        data = dataMethod()  
        if (data is None or data == self.latestData) and not self.loadingFromEmpty():
            return True
        self.latestData = data
        if initial:
            self.connect("current-folder-changed", self.currentFolderChanged, dataMethod)
        applicationEvent("file chooser to read file system", "filechooser")
        self.checkHandler = None
        return False


class Dialog(DialogHelper, origDialog):
    def __init__(self, *args, **kw):
        origDialog.__init__(self, *args, **kw)
        self.initialise()
    

class FileChooserDialog(DialogHelper, FileChooserHelper, origFileChooserDialog):
    def __init__(self, title=None, parent=None, action=gtk.FILE_CHOOSER_ACTION_OPEN, buttons=None, backend=None):
        origFileChooserDialog.__init__(self, title, parent, action, buttons, backend)
        FileChooserHelper.__init__(self, action)
        self.initialise()
        
class FileChooserWidget(FileChooserHelper, origFileChooserWidget):
    def __init__(self, action=gtk.FILE_CHOOSER_ACTION_OPEN, backend=None):
        origFileChooserWidget.__init__(self, action, backend)
        FileChooserHelper.__init__(self, action)

class Builder(origBuilder):
    def __init__(self, *args, **kw):
        origBuilder.__init__(self, *args, **kw)
        self.filesRead = []
    
    def get_object(self, *args):
        WidgetAdapter.builderEnabled = True
        realObject = origBuilder.get_object(self, *args)
        if isinstance(realObject, origDialog):
            realObject.uiMap = DialogHelper.uiMap
            self.graftMethods(realObject, DialogHelper)
            realObject.initialise()
        elif isinstance(realObject, gtk.TreeView):
            documents = map(xml.dom.minidom.parse, self.filesRead)
            for column in realObject.get_columns():
                self.graftMethods(column, treeviewextract.TreeViewColumn)
                xmlElement = self.findXmlElement(documents, gtk.Buildable.get_name(column))
                children = xmlElement.getElementsByTagName("child")
                for renderer, child in zip(column.get_cell_renderers(), children):
                    attrs = {}
                    for node in child.getElementsByTagName("attribute"):
                        attrs[node.getAttribute("name")] = int(node.childNodes[0].nodeValue)
                    column.add_model_extractors(renderer, **attrs)
        return realObject

    def graftMethods(self, obj, fromClass):
        for name, member in inspect.getmembers(fromClass, inspect.ismethod):
            newMethod = types.MethodType(member.__func__, obj)
            setattr(obj, name, newMethod)

    def findXmlElement(self, documents, elementId):
        for document in documents:
            for obj in document.getElementsByTagName("object"):
                if obj.getAttribute("id") == elementId:
                    return obj

    def add_from_file(self, file, *args):
        origBuilder.add_from_file(self, file, *args)
        treeviewextract.reverseInterceptions(eventTypes) # These are bad in a builder-based world...
        self.filesRead.append(file)


class UIMap(storytext.guishared.UIMap):
    ignoreWidgetTypes = [ "Label" ]
    def __init__(self, *args): 
        storytext.guishared.UIMap.__init__(self, *args)
        gtk.Builder = Builder
        gtk.Dialog = Dialog
        DialogHelper.uiMap = self
        gtk.FileChooserDialog = FileChooserDialog
        gtk.FileChooserWidget = FileChooserWidget
    
    def monitorChildren(self, widget, *args, **kw):
        if widget.getName() != "Shortcut bar" and \
               not widget.isInstanceOf(gtk.FileChooser) and not widget.isInstanceOf(gtk.ToolItem):
            storytext.guishared.UIMap.monitorChildren(self, widget, *args, **kw)

    def monitorWindow(self, window):
        if window.isInstanceOf(origDialog):
            # Do the dialog contents before we do the dialog itself. This is important for FileChoosers
            # as they have things that use the dialog signals
            self.logger.debug("Monitoring children for dialog with title " + repr(window.getTitle()))
            self.monitorChildren(window, excludeWidgets=self.getResponseWidgets(window, window.action_area))
            self.monitorWidget(window)
            windowevents.ResponseEvent.connectStored(window)
        else:
            storytext.guishared.UIMap.monitorWindow(self, window)

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
