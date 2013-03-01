
import sys, codecs, logging, locale

def openEncoded(file, mode="r"):
    try:
        encoding = getLocaleEncoding()
        return codecs.open(file, mode, encoding, errors="replace")
    except ValueError:
        return open(file, mode)
    
def encodeToLocale(unicodeText):
    if pythonVersion3():
        return unicodeText # don't need to mess about if we're in Python 3 anyway
    elif unicodeText:
        try:
            return unicodeText.encode(getLocaleEncoding(), 'replace')
        except ValueError:
            # Get this if locale is invalid for example
            # Return the text as-is and hope for the best
            return unicodeText
    else:
        return ""
        
def pythonVersion3():
    return sys.version_info[0] == 3
    
def getLocaleEncoding():
    return locale.getdefaultlocale()[1] or "utf-8"

    
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
