
import sys, codecs, logging, locale

localeEncoding = None

def openEncoded(file, mode="r"):
    encoding = getLocaleEncoding()
    return codecs.open(file, mode, encoding, errors="replace")
    
def encodeToLocale(unicodeText):
    if pythonVersion3():
        return unicodeText # don't need to mess about if we're in Python 3 anyway
    elif unicodeText:
        return unicodeText.encode(getLocaleEncoding(), 'replace')
    else:
        return ""
        
def pythonVersion3():
    return sys.version_info[0] == 3
    
def getLocaleEncoding():
    global localeEncoding
    if localeEncoding:
        return localeEncoding
    
    try:
        localeEncoding = locale.getdefaultlocale()[1] or "utf-8"
    except ValueError:
        # Get this if locale is invalid for example
        # Return the text as-is and hope for the best
        localeEncoding = "utf-8"
    return localeEncoding
    
class EncodingLoggerProxy:
    def __init__(self, logger):
        self.logger = logger
        
    def info(self, msg):
        self.logger.info(encodeToLocale(msg))

    def debug(self, msg):
        self.logger.debug(encodeToLocale(msg))
        
    def __getattr__(self, name):
        return getattr(self.logger, name)

    
def getEncodedLogger(*args):
    return EncodingLoggerProxy(logging.getLogger(*args))
