import wx

from storytext.wxtoolkit.monkeypatch import WidgetBase
from storytext.wxtoolkit.widgetadapter import WidgetAdapter

class MonkeyPatchDialog(WidgetBase):
 
    def __init__(self):
        self.recordHandler = None
        adapter = WidgetAdapter(self)
        self.uiMap.monitorWidget(adapter)
        self.reply = self.getReply(adapter)
    
    def fakeShowModal(self):
        if self.reply == None:
            return wx.ID_CANCEL
        else:
            return wx.ID_OK

    def getReply(self, adapter):
        for uiMapId in self.uiMap.allUIMapIdCombinations(adapter):
            if uiMapId in self.replies:
                paths = self.replies.get(uiMapId)
                return paths.pop(0)
        