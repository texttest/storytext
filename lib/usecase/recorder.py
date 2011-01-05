
""" Generic recorder classes. GUI-specific stuff is in guishared.py """

import os, sys, signal, logging
from replayer import ReplayScript
from ordereddict import OrderedDict
from definitions import *

# Take care not to record empty files...
class RecordScript:
    def __init__(self, scriptName):
        self.scriptName = scriptName
        self.fileForAppend = None
        self.shortcutTrackers = []
    
    def record(self, line):
        try:
            self._record(line)
            for tracker in self.shortcutTrackers:
                if tracker.updateCompletes(line):
                    self.rerecord(tracker.getNewCommands())
        except IOError:
            sys.stderr.write("ERROR: Unable to record " + repr(line) + " to file " + repr(self.scriptName) + "\n") 
    
    def _record(self, line):
        if not self.fileForAppend:
            self.fileForAppend = open(self.scriptName, "w")
        self.fileForAppend.write(line + "\n")
        self.fileForAppend.flush()
    
    def registerShortcut(self, shortcut):
        self.shortcutTrackers.append(ShortcutTracker(shortcut))
    
    def close(self):
        if self.fileForAppend:
            self.fileForAppend.close()
            self.fileForAppend = None

    def rerecord(self, newCommands):
        self.close()
        os.remove(self.scriptName)
        for command in newCommands:
            self._record(command)
    
    def rename(self, newName):
        self.close()
        os.rename(self.scriptName, newName)
        self.scriptName = newName


class ShortcutTracker:
    def __init__(self, replayScript):
        self.replayScript = replayScript
        self.unmatchedCommands = []
        self.reset()

    def reset(self):
        self.replayScript = ReplayScript(self.replayScript.name)
        self.currCommand = self.replayScript.getCommand()

    def updateCompletes(self, line):
        if line == self.currCommand:
            self.currCommand = self.replayScript.getCommand()
            return not self.currCommand
        else:
            self.unmatchedCommands.append(line)
            self.reset()
            return False

    def getNewCommands(self):
        self.reset()
        self.unmatchedCommands.append(self.replayScript.getShortcutName().lower())
        return self.unmatchedCommands


class UseCaseRecorder:
    def __init__(self):
        self.logger = logging.getLogger("usecase record")
        # Store events we don't record at the top level, usually controls on recording...
        self.eventsBlockedTopLevel = []
        self.scripts = []
        self.processId = os.getpid()
        self.applicationEvents = OrderedDict()
        self.supercededAppEventCategories = {}
        self.suspended = 0
        self.realSignalHandlers = {}
        self.origSignal = signal.signal
        self.signalNames = {}
        self.stateChangeEventInfo = None
        self.delayedEvents = []
        recordScript = os.getenv("USECASE_RECORD_SCRIPT")
        if recordScript:
            self.addScript(recordScript)
            if os.pathsep != ";": # Not windows! os.name and sys.platform don't give this information if using Jython
                self.addSignalHandlers()

        for entry in dir(signal):
            if entry.startswith("SIG") and not entry.startswith("SIG_"):
                exec "number = signal." + entry
                self.signalNames[number] = entry

    def notifyExit(self):
        self.suspended = 0

    def isActive(self):
        return len(self.scripts) > 0

    def addScript(self, scriptName):
        self.scripts.append(RecordScript(scriptName))
    
    def addSignalHandlers(self):
        signal.signal = self.appRegistersSignal
        # Don't record SIGCHLD unless told to, these are generally ignored
        # Also don't record SIGCONT, which is sent by LSF when suspension resumed
        # SIGBUS and SIGSEGV are usually internaly errors
        ignoreSignals = [ signal.SIGCHLD, signal.SIGCONT, signal.SIGBUS, signal.SIGSEGV ]
        for signum in range(signal.NSIG):
            try:
                if signum not in ignoreSignals:
                    self.realSignalHandlers[signum] = self.origSignal(signum, self.recordSignal)
            except:
                # Various signals aren't really valid here...
                pass
    
    def appRegistersSignal(self, signum, handler):
        # Don't want to interfere after a fork, leave child processes to the application to manage...
        if os.getpid() == self.processId:
            self.realSignalHandlers[signum] = handler
        else:  # pragma: no cover - coverage isn't active after a fork anyway
            self.origSignal(signum, handler)

    def blockTopLevel(self, eventName):
        self.eventsBlockedTopLevel.append(eventName)

    def terminateScript(self):
        script = self.scripts.pop()
        if script.fileForAppend:
            return script

    def recordSignal(self, signum, stackFrame):
        self.writeApplicationEventDetails()
        self.record(signalCommandName + " " + self.signalNames[signum])
        # Reset the handler and send the signal to ourselves again...
        realHandler = self.realSignalHandlers[signum]
        # If there was no handler-override installed, resend the signal with the handler reset
        if realHandler == signal.SIG_DFL: 
            self.origSignal(signum, self.realSignalHandlers[signum])
            print "Killing process", self.processId, "with signal", signum
            sys.stdout.flush()
            os.kill(self.processId, signum)
            # If we're still alive, set the signal handler back again to record future signals
            self.origSignal(signum, self.recordSignal)
        elif realHandler is not None and realHandler != signal.SIG_IGN:
            # If there was a handler, just call it
            realHandler(signum, stackFrame)

    def writeEvent(self, *args):
        if len(self.scripts) == 0 or self.suspended == 1:
            self.logger.debug("Received event, but recording is disabled or suspended")
            return
        event = self.findEvent(*args)
        self.logger.debug("Event of type " + event.__class__.__name__ + " for recording")
        if not event.shouldRecord(*args):
            self.logger.debug("Told we should not record it : args were " + repr(args))
            return

        if self.stateChangeEventInfo:
            stateChangeOutput, stateChangeEvent, stateChangeDelayLevel = self.stateChangeEventInfo
            if event.implies(stateChangeOutput, stateChangeEvent, *args):
                self.logger.debug("Implies previous state change event, ignoring previous")
            else:
                self.recordOrDelay(stateChangeOutput, stateChangeEvent, stateChangeDelayLevel)
            self.stateChangeEventInfo = None

        scriptOutput = event.outputForScript(*args)
        self.writeApplicationEventDetails()
        delayLevel = event.delayLevel()
        if event.isStateChange():
            self.logger.debug("Storing up state change event " + repr(scriptOutput))
            self.stateChangeEventInfo = scriptOutput, event, delayLevel
        else:
            if self.recordOrDelay(scriptOutput, event, delayLevel):
                self.processDelayedEvents(self.delayedEvents)
                self.delayedEvents = []

    def recordOrDelay(self, scriptOutput, event, delayLevel):
        if delayLevel:
            self.logger.debug("Delaying event " + repr(scriptOutput) + " at level " + repr(delayLevel))
            self.delayedEvents.append((scriptOutput, event, delayLevel))
            return False
        else:
            self.record(scriptOutput, event)
            return True

    def processDelayedEvents(self, events, level=1):
        if len(events):
            self.logger.debug("Processing delayed events at level " + str(level))
            nextLevelEvents = []
            for scriptOutput, event, delayLevel in events:
                if delayLevel == level:
                    self.record(scriptOutput, event)
                    self.processDelayedEvents(nextLevelEvents, level + 1)
                    nextLevelEvents = []
                else:
                    nextLevelEvents.append((scriptOutput, event, delayLevel))
                
    def record(self, line, event=None):
        self.logger.debug("Recording " + repr(line))
        for script in self.getScriptsToRecord(event):
            script.record(line)

    def getScriptsToRecord(self, event):   
        if event and (event.name in self.eventsBlockedTopLevel):
            return self.scripts[:-1]
        else:
            return self.scripts

    def findEvent(self, *args):
        for arg in args:
            if isinstance(arg, UserEvent):
                return arg
            
    def registerApplicationEvent(self, eventName, category, supercedeCategories=[]):
        if category:
            self.applicationEvents[category] = eventName
            self.logger.debug("Got application event '" + eventName + "' in category " + repr(category))
            for supercededCategory in self.supercededAppEventCategories.get(category, []):
                if supercededCategory in self.applicationEvents:
                    self.logger.debug("Superceded and discarded application event " + self.applicationEvents[supercededCategory])
                    del self.applicationEvents[supercededCategory]
            for supercedeCategory in supercedeCategories:
                self.supercededAppEventCategories.setdefault(supercedeCategory, set()).add(category)
        else:
            # Non-categorised event makes all previous ones irrelevant
            self.applicationEvents = OrderedDict()
            self.supercededAppEventCategories = {}
            self.applicationEvents["gtkscript_DEFAULT"] = eventName

    def applicationEventRename(self, oldName, newName, oldCategory, newCategory):
        for categoryName, oldEventName in self.applicationEvents.items():
            if oldCategory in categoryName:
                newCategoryName = categoryName.replace(oldCategory, newCategory)
                del self.applicationEvents[categoryName]
                newEventName = oldEventName.replace(oldName, newName)
                self.registerApplicationEvent(newEventName, newCategory)
        
        for supercedeCategory, categories in self.supercededAppEventCategories.items():
            if oldCategory in categories:
                categories.remove(oldCategory)
                categories.add(newCategory)
                self.logger.debug("Swapping for " + repr(supercedeCategory) + ": " + repr(oldCategory) + " -> " + repr(newCategory))
            
    def writeApplicationEventDetails(self):
        if len(self.applicationEvents) > 0:
            eventString = ", ".join(sorted(self.applicationEvents.values()))
            self.record(waitCommandName + " " + eventString)
            self.applicationEvents = OrderedDict()

    def registerShortcut(self, replayScript):
        for script in self.scripts:
            script.registerShortcut(replayScript)
