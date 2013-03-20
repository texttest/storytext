import wx


wxMessageBox = wx.MessageBox
replayingMethod = None
monitor = None


class MessageBoxWidget():
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
        return self.title
    
    def getTooltip(self):
        return ""
    
    def getType(self):
        return "MessageBoxWidget"

    def GetChildren(self):
        return []
    
    def getReturnValueFromCache(self):
        userReplies = self.messageBoxReplies["Title=" + self.title]
        userReply = userReplies.pop(0).lower()
        return getattr(wx, userReply.upper())

    def setRecordHandler(self, handler):
        self.recordHandler = handler 
     
        
def MessageBox(*args, **kw):
    widget = MessageBoxWidget(args[1])
    monitor(widget, *args, **kw)
    if replaying():
        userReply = widget.getReturnValueFromCache()
    else:
        userReply = wxMessageBox(*args, **kw)
    if widget.recordHandler:
        widget.recordHandler(userReply)
    return userReply

    
def wrap_message_box(replayingMethod, monitorMethod):
    wx.MessageBox = MessageBox
    global replaying, monitor
    replaying = replayingMethod
    monitor = monitorMethod
