
""" Event-handling around gtk.FileChoosers of various sorts """

from baseevents import StateChangeEvent
from windowevents import DialogEventHandler, ResponseEvent
from usecase import UseCaseScriptError
import gtk, gtklogger, os

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
            raise UseCaseScriptError, "Cannot replay changes of folder in file choosers due to bug in GTK 2.14, fixed in GTK 2.16.3"
        for folder in self.widget.list_shortcut_folders():
            if os.path.basename(folder) == argumentString:
                return folder
        folder = os.path.join(self.widget.get_current_folder(), argumentString)
        if os.path.isdir(folder):
            return folder
        else: 
            raise UseCaseScriptError, "Cannot find folder '" + argumentString + "' to change to!"

# Base class for selecting a file or typing a file name
class FileChooserFileEvent(DialogEventHandler, StateChangeEvent):
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
    
class FileChooserFileSelectEvent(FileChooserFileEvent):
    signalName = "selection-changed"
    dialogInfo = {}
    def getChangeMethod(self):
        return self.fileChooser.select_filename
    
    def connectRecord(self, *args):
        FileChooserFileEvent.connectRecord(self, *args)
        self.fileChooser.connect("current-folder-changed", self.getStateDescription)

    def getProgrammaticChangeMethods(self):
        return [ self.fileChooser.set_filename, self.fileChooser.set_current_folder ]

    def setProgrammaticChange(self, val, filename=None):
        FileChooserFileEvent.setProgrammaticChange(self, val)
        if val and filename:
            self.currentName = os.path.basename(filename)

    def shouldRecord(self, *args):
        if self.currentName: # once we've got a name, everything is permissible...
            return FileChooserFileEvent.shouldRecord(self, *args)
        else:
            self.getStateDescription()
            return False

    def getStateChangeArgument(self, argumentString):
        path = os.path.join(self.fileChooser.get_current_folder(), argumentString)
        if os.path.exists(path):
            return path
        else:
            raise UseCaseScriptError, "Cannot select file '" + argumentString + "', no such file in current folder"
    
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

    @staticmethod
    def widgetHasSignal(widget, signalName):
        return widget.isInstanceOf(gtk.FileChooser) # not a real signal, so we fake it

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
