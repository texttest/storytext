import wx
from signalevent import SignalEvent
from proxywidget import ProxyWidget


wxMessageBox = wx.MessageBox
replayingMethod = None
monitor = None
MESSAGE_BOX_REPLIES = {wx.YES: "Yes", wx.NO: "No", wx.CANCEL: "Cancel", wx.OK: "Ok"}


class MessageBoxEvent(SignalEvent):
    signal = "MessageBoxReply"
    
    def connectRecord(self, method):
        def handler(reply):
            method(reply, self)
        self.widget.setRecordHandler(handler)

    def outputForScript(self, reply, *args):
        return self.name + " " + MESSAGE_BOX_REPLIES[reply]

    @classmethod
    def getSignal(cls):
        return cls.signal


class MessageBoxWidget(ProxyWidget):
    
    def __init__(self, *args, **kw):
        self._setAttributes(*args, **kw)
        ProxyWidget.__init__(self, self.title, "MessageBoxWidget")
        
    def _setAttributes(self, *args, **kw):
        self.headername = "Message Box"
        self.message = self._setMessage(*args, **kw)
        self.title = self._setTitle(*args, **kw)
        self.style = self._setStyle(*args, **kw)

    def _setMessage(self, *args, **kw):
        return args[0]

    def _setTitle(self, *args, **kw):
        return self._getAttribute(1, "caption", *args, **kw)

    def _setStyle(self, *args, **kw):
        return self._getAttribute(2, "style", *args, **kw)
        
    def getReturnValueFromCache(self):
        userReply = super(MessageBoxWidget, self).getReturnValueFromCache()
        return getattr(wx, userReply.upper())

    def describe(self, logger):
        logger.info("\n" + self._getHeader())
        logger.info(self.message)
        if self.style:
            logger.info(".....")
            buttons = []
            for reply, name in sorted(MESSAGE_BOX_REPLIES.items()):
                if self.style & reply:
                    buttons.append("Button '" + name + "'")
            if buttons:
                logger.info("  ".join(buttons))
        logger.info("-" * self._getFooterLength())     
        
        
def MessageBox(*args, **kw):
    widget = MessageBoxWidget(*args, **kw)
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
