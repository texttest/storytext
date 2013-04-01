import wx
from storytext.wxtoolkit.monkeypatch import ProxyWidget
from storytext.wxtoolkit.monkeypatch import MonkeyPatchEvent


NO_FONT_SELECTED = "No font selected"


wxGetFontFromUser = wx.GetFontFromUser
uiMap = None


class GetFontFromUserEvent(MonkeyPatchEvent):
   
    signal = "GetFontFromUserReply"

    @classmethod
    def getSignal(cls):
        return cls.signal

    
class GetFontFromUserWidget(ProxyWidget):
    
    @classmethod
    def getAutoPrefix(cls):
        return "Auto.GetFontFromUserWidget.GetFontFromUserReply"
        
    def __init__(self, message, *args, **kw):
        self.uiMap = uiMap
        self._setAttributes(*args, **kw)
        ProxyWidget.__init__(self, self.caption, "GetFontFromUserWidget")
    
    def _setAttributes(self, *args, **kw):
        self.headername = "Get Font from User"
        self.caption = self._setCaption(*args, **kw)

    def _setCaption(self, *args, **kw):
        caption = self._getAttribute(2, "caption", *args, **kw)
        if caption is None:
            caption = ""
        return caption
    
    def describe(self, logger):
        logger.info("\n" + self._getHeader())
        logger.info("-" * self._getFooterLength())

        
def GetFontFromUser(*args, **kw):
    widget = GetFontFromUserWidget(*args, **kw)
    uiMap.monitorAndDescribe(widget, *args, **kw)
    if uiMap.replaying():
        userReply = widget.getReturnValueFromCache()
        userReply = stringToFont(userReply)
    else:
        userReply = wxGetFontFromUser(*args, **kw)
    if widget.recordHandler:
        if userReply.IsOk():
            widget.recordHandler("%s" % userReply.GetNativeFontInfoDesc())
        else:
            widget.recordHandler(NO_FONT_SELECTED)
    return userReply

def stringToFont(text):
    font = wx.Font(1, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
    fi = wx.NativeFontInfo()
    fi.FromString(text)
    font.SetNativeFontInfo(fi)
    if text == NO_FONT_SELECTED:
        invalidateFonf(font)
    return font
    

def invalidateFonf(font):
    font.SetFaceName("")

        
def wrapGetFontFromUser(uiMapObject):
    wx.GetFontFromUser = GetFontFromUser
    global uiMap
    uiMap = uiMapObject

