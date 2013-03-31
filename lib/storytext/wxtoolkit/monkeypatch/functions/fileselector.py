import wx
from storytext.wxtoolkit.monkeypatch import ProxyWidget
from storytext.wxtoolkit.monkeypatch import MonkeyPatchEvent


wxFileSelector = wx.FileSelector
uiMap = None

class FileSelectorEvent(MonkeyPatchEvent):
    
    signal = "FileSelectorReply"
    
    @classmethod
    def getSignal(cls):
        return cls.signal
    
    
class FileSelectorWidget(ProxyWidget):
    
    def __init__(self, message, *args, **kw):
        self.uiMap = uiMap
        self._setAttributes(*args, **kw)
        ProxyWidget.__init__(self, message, "FileSelectorWidget")
    
    def _setAttributes(self, *args, **kw):
        self.headername = "File Selector"
        self.defaultFile = self._setDefaultFile(*args, **kw)
        self.flags = self._setFlags(*args, **kw)

    def _setDefaultFile(self, *args, **kw):
        return self._getAttribute(0, "default_file", *args, **kw)
                
    def _setFlags(self, *args, **kw):
        return self._getAttribute(1, "flags", *args, **kw)

    def describe(self, logger):
        logger.info("\n" + self._getHeader())
        logger.info("DefaultFile: %s" % self.defaultFile)
        logger.info("Flags      : %s" % self._getFlags())
        logger.info("-" * self._getFooterLength())

    def _getFlags(self):
        flags = []
        if self.flags:
            if self.styleHasFlag(wx.FD_OPEN):
                flags.append("wx.FD_OPEN") 
            if self.styleHasFlag(wx.FD_SAVE):
                flags.append("wx.FD_SAVE") 
            if self.styleHasFlag(wx.FD_OVERWRITE_PROMPT):
                flags.append("wx.FD_OVERWRITE_PROMPT") 
            if self.styleHasFlag(wx.FD_FILE_MUST_EXIST):
                flags.append("wx.FD_FILE_MUST_EXIST") 
        return " | ".join(flags)
    
    def styleHasFlag(self, flag):
        return (self.flags | flag) == self.flags

    def getReturnValueFromCache(self):
        for uiMapId in uiMap.allUIMapIdCombinations(self):
            if uiMapId in self.replies:
                userReplies = self.replies[uiMapId]
                return userReplies.pop(0)

        
def FileSelector(*args, **kw):
    widget = FileSelectorWidget(*args, **kw)
    uiMap.monitorAndDescribe(widget, *args, **kw)
    if uiMap.replaying():
        userReply = widget.getReturnValueFromCache()
    else:
        userReply = wxFileSelector(*args, **kw)
    if widget.recordHandler:
        widget.recordHandler(userReply)
    return userReply

    
def wrapFileSelector(uiMapObject):
    wx.FileSelector = FileSelector
    global uiMap
    uiMap = uiMapObject
