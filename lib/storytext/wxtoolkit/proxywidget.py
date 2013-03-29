NBR_OF_DASHES_IN_SHORT_LINE = 10
MAX_NBR_OF_DASHES_IN_LONG_LINE = 100


class WidgetBase(object):
    
    replies = {}
    
    @classmethod
    def cacheReplies(cls, identifier, answer):
        cls.replies.setdefault(identifier, []).append(answer)

    def getReturnValueFromCache(self, key=None):
        if key is None:
            key = "Title=" + self.GetTitle()
        userReplies = self.replies.get(key)
        if userReplies is not None:
            userReply = userReplies.pop(0)
            return userReply

    def setRecordHandler(self, handler):
        self.recordHandler = handler 
    
        
class ProxyWidget(WidgetBase):
    
    def __init__(self, title, typename):
        self.recordHandler = None
        self.title = title
        self.type = typename
        
    def GetTitle(self):
        return self.title
    
    def GetLabel(self):
        return self.title
    
    def getTooltip(self):
        return ""

    def GetChildren(self):
        return []
    
    def getType(self):
        return self.typename
    
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
    