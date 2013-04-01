import wx
from storytext.wxtoolkit.monkeypatch import ProxyWidget
from storytext.wxtoolkit.monkeypatch import MonkeyPatchEvent


wxDirSelector = wx.DirSelector
uiMap = None


class DirSelectorEvent(MonkeyPatchEvent):
   
    signal = "DirSelectorReply"

    @classmethod
    def getSignal(cls):
        return cls.signal
    
    
class DirSelectorWidget(ProxyWidget):
    
    @classmethod
    def getAutoPrefix(cls):
        return "Auto.DirSelectorWidget.DirSelectorReply"
        
    def __init__(self, message, *args, **kw):
        self.uiMap = uiMap
        self._setAttributes(*args, **kw)
        ProxyWidget.__init__(self, message, "DirSelectorWidget")
    
    def _setAttributes(self, *args, **kw):
        self.headername = "Dir Selector"
        self.defaultPath = self._setDefaultPath(*args, **kw)
        self.style = self._setStyle(*args, **kw)

    def _setDefaultPath(self, *args, **kw):
        return self._getAttribute(0, "defaultPath", *args, **kw)
                
    def _setStyle(self, *args, **kw):
        return self._getAttribute(1, "style", *args, **kw)

    def describe(self, logger):
        logger.info("\n" + self._getHeader())
        logger.info("DefaultDir: %s" % self.defaultPath)
        logger.info("Style     : %s" % self._getStyles())
        logger.info("-" * self._getFooterLength())

    def _getStyles(self):
        styles = []
        if self.style:
            if self.styleHasFlag(wx.DD_DIR_MUST_EXIST):
                styles.append("wx.DD_DIR_MUST_EXIST") 
            if self.styleHasFlag(wx.DD_DEFAULT_STYLE):
                styles.append("wx.DD_DEFAULT_STYLE") 
            if self.styleHasFlag(wx.DD_CHANGE_DIR):
                styles.append("wx.DD_CHANGE_DIR") 
        return " | ".join(styles)
    
    def styleHasFlag(self, flag):
        return (self.style | flag) == self.style

        
def DirSelector(*args, **kw):
    widget = DirSelectorWidget(*args, **kw)
    uiMap.monitorAndDescribe(widget, *args, **kw)
    if uiMap.replaying():
        userReply = widget.getReturnValueFromCache()
    else:
        userReply = wxDirSelector(*args, **kw)
    if widget.recordHandler:
        widget.recordHandler(userReply)
    return userReply

    
def wrapDirSelector(uiMapObject):
    wx.DirSelector = DirSelector
    global uiMap
    uiMap = uiMapObject

