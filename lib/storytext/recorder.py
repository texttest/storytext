
""" Generic recorder classes. GUI-specific stuff is in guishared.py """

import os, sys, signal, logging
from replayer import ReplayScript
try:
    from collections import OrderedDict
except ImportError:
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
            bestTracker = None
            for tracker in self.shortcutTrackers:
                if tracker.updateCompletes(line) and \
                    (bestTracker is None or tracker.isLongerThan(bestTracker)):
                    bestTracker = tracker
            if bestTracker:
                self.rerecord(bestTracker.getNewCommands())
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
            if not self.fileForAppend.closed:
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
            self.unmatchedCommands += self.replayScript.getCommandsSoFar()
            self.unmatchedCommands.append(line)
            self.reset()
            return False

    def getNewCommands(self):
        self.reset()
        self.unmatchedCommands.append(self.replayScript.getShortcutName().lower())
        return self.unmatchedCommands
    
    def isLongerThan(self, otherTracker):
        return len(self.replayScript.commands) > len(otherTracker.replayScript.commands)


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
        self.hasAutoRecordings = False
        recordScript = os.getenv("USECASE_RECORD_SCRIPT")
        if recordScript:
            self.addScript(recordScript)
            if os.pathsep != ";": # Not windows! os.name and sys.platform don't give this information if using Jython
                self.addSignalHandlers()

        for entry in dir(signal):
            if entry.startswith("SIG") and not entry.startswith("SIG_"):
                number = getattr(signal, entry)
                self.signalNames[number] = entry

    def notifyExit(self):
        self.suspended = 0

    def isActive(self):
        return len(self.scripts) > 0

    def addScript(self, scriptName):
        self.scripts.append(RecordScript(scriptName))

    def closeScripts(self):
        for script in self.scripts:
            script.close()
    
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
        self.writeApplicationEventDetails(recordingEvent=True)
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
            try:
                realHandler(signum, stackFrame)
            except TypeError:
                if os.name == "java":
                    from sun.misc import Signal
                    sigName = self.signalNames[signum].replace("SIG", "")
                    realHandler.handle(Signal(sigName))

    def writeEvent(self, *args):
        if len(self.scripts) == 0 or self.suspended == 1:
            self.logger.debug("Received event, but recording is disabled or suspended")
            return
        event = self.findEvent(*args)
        self.logger.debug("Event of type " + event.__class__.__name__ + " for recording")
        if not event.shouldRecord(*args):
            self.logger.debug("Told we should not record it : args were " + repr(args))
            return
        
        haveRecorded = False 
        if self.stateChangeEventInfo:
            stateChangeOutput, stateChangeEvent, stateChangeDelayLevel = self.stateChangeEventInfo
            if stateChangeDelayLevel >= event.delayLevel(*args):
                if event.implies(stateChangeOutput, stateChangeEvent, *args):
                    self.logger.debug("Implies previous state change event, ignoring previous")
                else:
                    haveRecorded = self.recordOrDelay(stateChangeOutput, stateChangeEvent, stateChangeDelayLevel)
                self.stateChangeEventInfo = None

        scriptOutput = event.outputForScript(*args)
        willRecord = not event.delayLevel(*args) and not event.isStateChange()
        self.writeApplicationEventDetails(haveRecorded or willRecord)
        delayLevel = event.delayLevel(*args)
        if event.isStateChange() and delayLevel >= self.getMaximumStoredDelay():
            self.logger.debug("Storing up state change event " + repr(scriptOutput) + " with delay level " + repr(delayLevel))
            self.stateChangeEventInfo = scriptOutput, event, delayLevel
        else:
            if self.recordOrDelay(scriptOutput, event, delayLevel):
                self.processDelayedEvents(self.delayedEvents)
                self.delayedEvents = []

    def getMaximumStoredDelay(self):
        return max((i[-1] for i in self.delayedEvents)) if self.delayedEvents else 0

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
                    if not event.isStateChange():
                        self.processDelayedEvents(nextLevelEvents, level + 1)
                        nextLevelEvents = []
                else:
                    nextLevelEvents.append((scriptOutput, event, delayLevel))
                
    def record(self, line, event=None):
        self.logger.debug("Recording " + repr(line))
        self.hasAutoRecordings |= line.startswith("Auto.")
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
            
    def registerApplicationEvent(self, eventName, category, supercedeCategories=[], delayLevel=0):
        category = category or "storytext_DEFAULT"
        delayLevel = max(delayLevel, self.getMaximumStoredDelay())
        if category in self.applicationEvents:
            existingEvent = self.applicationEvents[category][0]
            if existingEvent == eventName:
                eventName += " * 2"
            elif existingEvent.startswith(eventName + " *"):
                currentNumber = int(existingEvent.split()[-1])
                eventName += " * " + str(currentNumber + 1)
            
        if category != "storytext_DEFAULT":
            self.applicationEvents[category] = eventName, delayLevel
            self.logger.debug("Got application event '" + eventName + "' in category " + repr(category) +
                              " with delay level " + str(delayLevel))
            for supercededCategory in self.supercededAppEventCategories.get(category, []):
                if supercededCategory in self.applicationEvents:
                    self.logger.debug("Superceded and discarded application event " + self.applicationEvents[supercededCategory][0])
                    del self.applicationEvents[supercededCategory]
            for supercedeCategory in supercedeCategories:
                self.supercededAppEventCategories.setdefault(supercedeCategory, set()).add(category)
        else:
            # Non-categorised event makes all previous ones irrelevant
            self.applicationEvents = OrderedDict()
            self.logger.debug("Got application event '" + eventName + "' in global category with delay level " + str(delayLevel))
            self.supercededAppEventCategories = {}
            self.applicationEvents["storytext_DEFAULT"] = eventName, delayLevel

    def applicationEventRename(self, oldName, newName, oldCategory, newCategory):
        for categoryName, (oldEventName, delayLevel) in self.applicationEvents.items():
            if oldCategory in categoryName:
                newCategoryName = categoryName.replace(oldCategory, newCategory)
                del self.applicationEvents[categoryName]
                newEventName = oldEventName.replace(oldName, newName)
                self.registerApplicationEvent(newEventName, newCategory, delayLevel=delayLevel)
        
        for supercedeCategory, categories in self.supercededAppEventCategories.items():
            if oldCategory in categories:
                categories.remove(oldCategory)
                categories.add(newCategory)
                self.logger.debug("Swapping for " + repr(supercedeCategory) + ": " + repr(oldCategory) + " -> " + repr(newCategory))

    def applicationEventDelay(self, name):
        for categoryName, (eventName, oldDelayLevel) in self.applicationEvents.items():
            if eventName == name and oldDelayLevel == 0:
                del self.applicationEvents[categoryName]
                self.registerApplicationEvent(name, categoryName, delayLevel=1)

    def getCurrentApplicationEvents(self, recordingEvent):
        currEvents = []
        allEvents = self.applicationEvents.items()
        for categoryName, (eventName, delayLevel) in allEvents:
            if delayLevel == 0:
                currEvents.append(eventName)
                del self.applicationEvents[categoryName]
            elif recordingEvent:
                self.logger.debug("Delaying application event " + eventName + ", level now " + str(delayLevel - 1))
                self.applicationEvents[categoryName] = eventName, delayLevel - 1
            else:
                self.logger.debug("Ignoring delaying application event " + eventName + ", as not recording anyway")
        return sorted(currEvents)
                            
    def writeApplicationEventDetails(self, recordingEvent):
        eventNames = self.getCurrentApplicationEvents(recordingEvent)
        if len(eventNames) > 0:
            eventString = ", ".join(eventNames)
            self.record(waitCommandName + " " + eventString)

    def registerShortcut(self, replayScript):
        for script in self.scripts:
            script.registerShortcut(replayScript)
