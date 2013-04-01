import os

import wx

from storytext.wxtoolkit.signalevent import SignalEvent
from storytext.wxtoolkit.monkeypatch.dialogs import MonkeyPatchDialog


wxFileDialog = wx.FileDialog


class FileDialogEvent(SignalEvent):
    signal = "SelectFile"
    
    @classmethod
    def getSignal(cls):
        return cls.signal
        
    def connectRecord(self, method):
        def handler(path, d):
            method(path, d, self)
        self.widget.setRecordHandler(handler)

    def outputForScript(self, path, directory, *args):
        if directory and path.startswith(directory):
            path = path.replace(directory + os.sep, "")
        return self.name + " " + path


class FileDialog(wxFileDialog, MonkeyPatchDialog):

    @classmethod
    def getAutoPrefix(cls):
        return "Auto.FileDialog.SelectFile"
    
    @classmethod
    def wrap(cls, uiMap):
        cls.uiMap = uiMap
        wx.FileDialog = cls

    def __init__(self, *args, **kw):
        wxFileDialog.__init__(self, *args, **kw)
        MonkeyPatchDialog.__init__(self)
        self.addDirectoryToReply()

    def addDirectoryToReply(self):
        self.origDirectory = self.GetDirectory()
        if self.reply is not None and not os.path.isabs(self.reply):
                self.reply = os.path.join(self.origDirectory, self.reply)
        
    def ShowModal(self):
        if self.uiMap.replaying():
            return self.fakeShowModal()
        else:
            return wxFileDialog.ShowModal(self)
            
    def GetPath(self):
        if self.reply is None:
            self.reply = wxFileDialog.GetPath(self)
        if self.recordHandler:
            self.recordHandler(self.reply, self.origDirectory)
        return self.reply

    def GetFilename(self):
        return os.path.basename(self.GetPath()) 
