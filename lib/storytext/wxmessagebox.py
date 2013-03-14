import wx


wxMessageBox = wx.MessageBox
replayingMethod = None
monitor = None


class MessageBoxWidget():
    
    messageBoxReplies = {}
    callCounts = {}
    
    def __init__(self, title):
        self._incrementCallCount(title)
        self.title = self._concatenateTitleAndCallCount(title)
        self.recordHandler = None
        
    @classmethod
    def cacheMessageBoxReplies(cls, identifier, answer):
        cls.messageBoxReplies[identifier] = answer
        
    @classmethod
    def _incrementCallCount(cls, title):
        if title in cls.callCounts.keys():
            cls.callCounts[title] = int(cls.callCounts[title]) + 1
        else:
            cls.callCounts[title] = 1

    def _concatenateTitleAndCallCount(self, title):
        return "%s-%d" % (title, self.callCounts[title])

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
        userReply = self.messageBoxReplies["Title=" + self.title].lower()
        return getattr(wx, userReply.upper())

    def setRecordHandler(self, handler):
        self.recordHandler = handler 
     
        
def MessageBox(*args, **kw):
    widget = MessageBoxWidget(args[1])
    monitor(widget)
    if replaying():
        return widget.getReturnValueFromCache()
    else:
        userReply = wxMessageBox(*args, **kw)
        widget.recordHandler(userReply)
        return userReply

    
def wrap_message_box(replayingMethod, monitorMethod):
    wx.MessageBox = MessageBox
    global replaying, monitor
    replaying = replayingMethod
    monitor = monitorMethod
