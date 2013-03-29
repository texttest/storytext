import os

import wx

from widgetadapter import WidgetAdapter
from signalevent import SignalEvent
from proxywidget import WidgetBase


wxFileDialog = wx.FileDialog


class FileDialogEvent(SignalEvent):
    signal = "SelectFile"
    
    def connectRecord(self, method):
        def handler(path, d):
            method(path, d, self)
        self.widget.setRecordHandler(handler)

    def outputForScript(self, path, directory, *args):
        if directory and path.startswith(directory):
            path = path.replace(directory + os.sep, "")
        return self.name + " " + path



class FileDialog(wxFileDialog, WidgetBase):

    @classmethod
    def wrap(cls, monitorMethod, replayingMethod):
        cls.monitor = monitorMethod
        cls.replaying = replayingMethod
        wx.FileDialog = cls

    def __init__(self, *args, **kw):
        wxFileDialog.__init__(self, *args, **kw)
        self.recordHandler = None
        self.origDirectory = self.GetDirectory()
        adapter = WidgetAdapter(self)
        self.monitor(adapter)
        self.path = self.getReturnValueFromCache(adapter.getUIMapIdentifier())
        
    def ShowModal(self):
        if self.replaying():
            return self.fakeShowModal()
        else:
            return wxFileDialog.ShowModal(self)
 
    def fakeShowModal(self):
        if self.path == None:
            return wx.ID_CANCEL
        else:
            return wx.ID_OK
        
    def GetPath(self):
        if self.path is None:
            self.path = wxFileDialog.GetPath(self)
        if self.recordHandler:
            self.recordHandler(self.path, self.origDirectory)
        return self.path

    def GetFilename(self):
        return os.path.basename(self.GetPath()) 
    
    