import os

import wx


from storytext.wxtoolkit.monkeypatch.dialogs import MonkeyPatchDialog
from storytext.wxtoolkit.monkeypatch import MonkeyPatchEvent


wxDirDialog = wx.DirDialog


class DirDialogEvent(MonkeyPatchEvent):
    signal = "SelectDir"


class DirDialog(wxDirDialog, MonkeyPatchDialog):

    @classmethod
    def wrap(cls, uiMap):
        cls.uiMap = uiMap
        wx.DirDialog = cls

    def __init__(self, *args, **kw):
        wxDirDialog.__init__(self, *args, **kw)
        MonkeyPatchDialog.__init__(self)
        
    def ShowModal(self):
        if self.uiMap.replaying():
            return self.fakeShowModal()
        else:
            return wxDirDialog.ShowModal(self)
        
    def GetPath(self):
        if self.reply is None:
            self.reply = wxDirDialog.GetPath(self)
        if self.recordHandler:
            self.recordHandler(self.reply)
        return self.reply
