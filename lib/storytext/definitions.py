
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
    def delayLevel(self):
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
