import wx

wxMessageBox = wx.MessageBox
uiMap = None

class MessageBoxWidget:
    messageBoxReplies = {}    
    def __init__(self, title):
        self.title = title
        self.recordHandler = None
        
    @classmethod
    def cacheMessageBoxReplies(cls, identifier, answer):
        cls.messageBoxReplies.setdefault(identifier, []).append(answer)
        
    def GetTitle(self):
        return self.title
    
    def GetLabel(self):
        return ""
    
    def getTooltip(self):
        return ""
    
    def getType(self):
        return "MessageBoxWidget"

    def GetChildren(self):
        return []
    
    def getReturnValueFromCache(self):
        for uiMapId in uiMap.allUIMapIdCombinations(self):
            if uiMapId in self.messageBoxReplies:
                userReplies = self.messageBoxReplies[uiMapId]
                userReply = userReplies.pop(0).lower()
                return getattr(wx, userReply.upper())
            
    def findPossibleUIMapIdentifiers(self):
        return [ "Title=" + self.title, "Type=" + self.getType() ]

    def setRecordHandler(self, handler):
        self.recordHandler = handler 
     
        
def MessageBox(*args, **kw):
    widget = MessageBoxWidget(args[1])
    uiMap.monitorAndDescribe(widget, *args, **kw)
    if uiMap.replaying():
        userReply = widget.getReturnValueFromCache()
    else:
        userReply = wxMessageBox(*args, **kw)
    if widget.recordHandler:
        widget.recordHandler(userReply)
    return userReply

    
def wrap_message_box(uiMapRef):
    wx.MessageBox = MessageBox
    global uiMap
    uiMap = uiMapRef
