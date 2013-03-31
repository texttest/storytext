from storytext.wxtoolkit.signalevent import SignalEvent


NBR_OF_DASHES_IN_SHORT_LINE = 10
MAX_NBR_OF_DASHES_IN_LONG_LINE = 100


class MonkeyPatchEvent(SignalEvent):
    
    def connectRecord(self, method):
        def handler(reply):
            method(reply, self)
        self.widget.setRecordHandler(handler)

    def outputForScript(self, reply, *args):
        return self.name + " " + reply
        
        
class WidgetBase(object):
    
    replies = {}
    
    @classmethod
    def cacheReplies(cls, identifier, answer):
        cls.replies.setdefault(identifier, []).append(answer)

    def getReturnValueFromCache(self):
        for uiMapId in self.uiMap.allUIMapIdCombinations(self):
            if uiMapId in self.replies:
                userReplies = self.replies[uiMapId]
                return userReplies.pop(0)

    def setRecordHandler(self, handler):
        self.recordHandler = handler 
    
        
class ProxyWidget(WidgetBase):
    
    def __init__(self, title, typename):
        self.recordHandler = None
        self.title = title
        self.typename = typename
        
    def GetTitle(self):
        return self.title
    
    def GetLabel(self):
        return ""
    
    def getTooltip(self):
        return ""

    def GetChildren(self):
        return []
    
    def getType(self):
        return self.__class__.__name__
    
    def _getAttribute(self, pos, key, *args, **kw):
        if kw.has_key(key):
            value = kw[key]
        else:
            try:
                value = args[pos]
            except IndexError:
                value = None
        return value

    def _getHeader(self):
        return "-" * NBR_OF_DASHES_IN_SHORT_LINE + " %s '" % self.headername + self.title + "' " +  "-" * NBR_OF_DASHES_IN_SHORT_LINE
        
    def _getFooterLength(self):
        return min(len(self._getHeader()), MAX_NBR_OF_DASHES_IN_LONG_LINE)         
    
    def findPossibleUIMapIdentifiers(self):
        return ["Title=" + self.title, "Type=" + self.getType()]
