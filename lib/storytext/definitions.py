
__version__ = "trunk"

# Hard coded commands
waitCommandName = "wait for"
signalCommandName = "receive signal"

# Exception to throw when scripts go wrong
class UseCaseScriptError(RuntimeError):
    pass


# Base class for events caused by the action of a user on a GUI. Generally assumed
# to be doing something on a particular widget, and being named explicitly by the
# programmer in some language domain.

# Record scripts will call shouldRecord and will not record anything if this
# returns false: this is to allow for widgets with state which may not necessarily
# have changed in an appopriate way just because of the signal. They will then call outputForScript
# and write this to the script

# Replay scripts will call generate in order to simulate the event over again.
class UserEvent:
    def __init__(self, name):
        self.name = name
    def shouldRecord(self, *args): # pragma: no cover - just documenting interface
        return True
    def delayLevel(self, *args):
        return False
    def outputForScript(self, *args): # pragma: no cover - just documenting interface
        return self.name
    def generate(self, argumentString): # pragma: no cover - just documenting interface
        raise UseCaseScriptError("Don't know how to generate for " + repr(self.outputForScript(argumentString)))
    def isStateChange(self):
        # If this is true, recorder will wait before recording and only record if a different event comes in
        return False
    def implies(self, stateChangeLine, stateChangeEvent, *args):
        # If this is true, recorder will not record the state change if immediately followed by this event
        return self is stateChangeEvent
    def checkPreviousWhenRejected(self):
        # If this is true, 'implies' will be called even when 'shouldRecord' returns false
        # Historical assumption has been that 'shouldRecord' often takes out events that are totally irrelevant
        # But in some circumstances they can still be relevant in that sense
        return False
    def isPreferred(self):
        # If this is true, this event should be executed even if others also match
        return False
    def getWarning(self):
        return ""
    def checkWidgetStatus(self):
        pass # raise UseCaseScriptError if anything is wrong
    def parseArguments(self, argumentString):
        return argumentString
    def makePartialParseFailure(self, parsedArgs, unparsedArgs, firstEvent=True):
        return CompositeEventProxy(unparsedArgs, self, parsedArgs, firstEvent)

# Class for encapsulating when we can only perform some of an action, and marking progress
class CompositeEventProxy:
    def __init__(self, unparsedArgs, event=None, parsedArgs=None, firstEvent=True):
        self.eventsWithArgs = []
        self.firstEvent = firstEvent
        if event:
            self.addEvent(event, parsedArgs)
        self.unparsedArgs = unparsedArgs
        
    def addEvent(self, event, parsedArgs):
        if self.firstEvent:
            self.eventsWithArgs.append((event, parsedArgs))
        else:
            self.eventsWithArgs.insert(0, (event, parsedArgs))
        self.unparsedArgs = ""
        
    def updateFromProxy(self, proxy):
        if self.firstEvent or not proxy.firstEvent:
            self.eventsWithArgs += proxy.eventsWithArgs
        else:
            self.eventsWithArgs = proxy.eventsWithArgs + self.eventsWithArgs
        self.unparsedArgs = proxy.unparsedArgs
        self.firstEvent = proxy.firstEvent
        
    def getWarning(self):
        if self.unparsedArgs:
            try:
                self.eventsWithArgs[0][0].parseArguments(self.unparsedArgs)
            except UseCaseScriptError, e:
                return str(e)
        
    def generate(self, *args):
        for i, (event, parsedArgs) in enumerate(self.eventsWithArgs):
            event.generate(parsedArgs, partial=bool(i))
            
    def hasEvents(self):
        return len(self.eventsWithArgs) > 0
    
    def isPreferred(self):
        return True # If this is good, return it immediately
        
        