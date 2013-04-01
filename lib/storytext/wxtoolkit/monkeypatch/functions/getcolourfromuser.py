import wx
from storytext.wxtoolkit.monkeypatch import ProxyWidget
from storytext.wxtoolkit.monkeypatch import MonkeyPatchEvent


wxGetColourFromUser = wx.GetColourFromUser
uiMap = None


class GetColourFromUserEvent(MonkeyPatchEvent):
   
    signal = "GetColourFromUserReply"

    @classmethod
    def getSignal(cls):
        return cls.signal
    
    
class GetColourFromUserWidget(ProxyWidget):
    
    @classmethod
    def getAutoPrefix(cls):
        return "Auto.GetColourFromUserWidget.GetColourFromUserReply"
        
    def __init__(self, message, *args, **kw):
        self.uiMap = uiMap
        self._setAttributes(*args, **kw)
        ProxyWidget.__init__(self, self.caption, "GetColourFromUserWidget")
    
    def _setAttributes(self, *args, **kw):
        self.headername = "Get Colour from User"
        self.caption = self._setCaption(*args, **kw)

    def _setCaption(self, *args, **kw):
        caption = self._getAttribute(2, "caption", *args, **kw)
        if caption is None:
            caption = ""
        return caption
    
    def describe(self, logger):
        logger.info("\n" + self._getHeader())
        logger.info("-" * self._getFooterLength())

        
def GetColourFromUser(*args, **kw):
    widget = GetColourFromUserWidget(*args, **kw)
    uiMap.monitorAndDescribe(widget, *args, **kw)
    if uiMap.replaying():
        userReply = widget.getReturnValueFromCache()
        userReply = stringToColour(userReply)
    else:
        userReply = wxGetColourFromUser(*args, **kw)
    if widget.recordHandler:
        widget.recordHandler("%s" % userReply)
    return userReply

def stringToColour(text):
    text = text[1:-1]
    numbers = text.split(",")
    r,g,b,a = (int(numbers[0]), int(numbers[1]), int(numbers[2]), int(numbers[3]))
    try:
        colour = wx.Colour(r,g,b,a)
    except:
        colour = getInvalidColour()
    return colour
    
def getInvalidColour():
    return wx.ColourData().GetCustomColour(15)
        
def wrapGetColourFromUser(uiMapObject):
    wx.GetColourFromUser = GetColourFromUser
    global uiMap
    uiMap = uiMapObject

