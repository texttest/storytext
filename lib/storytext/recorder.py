
""" Generic recorder classes. GUI-specific stuff is in guishared.py """

import os, sys, signal, logging
from copy import copy
from replayer import ReplayScript
from definitions import *

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

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
                newCommands = bestTracker.getNewCommands()
                self.rerecord(newCommands)
                for tracker in self.shortcutTrackers:
                    if tracker is not bestTracker:
                        tracker.rerecord(newCommands)
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
        self.commandsForMatch = []
        self.commandsForMismatch = []
        self.logger = logging.getLogger("Shortcut Tracker")
        self.reset()

    def reset(self):
        self.replayScript = ReplayScript(self.replayScript.name)
        self.commandsForMatch = copy(self.commandsForMismatch)
        self.argsUsed = []
        self.currRegexp = self.replayScript.getCommandRegexp()


    def hasStarted(self):
        return self.commandsForMismatch != self.commandsForMatch

    def updateCompletes(self, line):
        if self.currRegexp is None:
            self.logger.debug("Ignore " +  self.replayScript.getShortcutName())
            return False # We already reached the end and should forever be ignored...
        match = self.currRegexp.match(line)
        if match:
            self.commandsForMismatch.append(line)
            self.logger.debug("Match " +  self.replayScript.getShortcutName() + ", " + self.currRegexp.pattern \
                               + ", " +  repr(line) + ", " + repr(self.commandsForMismatch) + ", " + repr(self.commandsForMatch))
            self.currRegexp = self.replayScript.getCommandRegexp()
            groupdict = match.groupdict()
            if groupdict: # numbered arguments
                for key, val in groupdict.items():
                    argPos = int(key.replace("var", "")) - 1
                    while len(self.argsUsed) <= argPos:
                        self.argsUsed.append("")
                    self.argsUsed[argPos] = val
            else:
                self.argsUsed += match.groups()
            return not self.currRegexp
        else:
            if self.hasStarted():
                self.reset()
                self.logger.debug("Reset " + self.replayScript.getShortcutName() + ", " + repr(self.commandsForMismatch))
                return self.updateCompletes(line)
            else:
                self.commandsForMismatch.append(line)
                pattern = copy(self.currRegexp.pattern)
                self.reset()
                self.logger.debug(pattern + ", " +  repr(line) + ", " + self.replayScript.getShortcutName() + ", " + repr(self.commandsForMismatch))
                return False
        
    def rerecord(self, newCommands):
        # Some other tracker has completed, include it in our unmatched commands...
        started = self.hasStarted()
        self.commandsForMismatch = copy(newCommands)
        if not started:
            self.commandsForMatch = copy(self.commandsForMismatch)
        self.logger.debug(self.replayScript.getShortcutName() + ", " + repr(self.commandsForMismatch) + ", " + repr(self.commandsForMatch))
        
    def getNewCommands(self):
        shortcutName = self.replayScript.getShortcutNameWithArgs(self.argsUsed)
        self.commandsForMatch.append(shortcutName)
        self.commandsForMismatch = self.commandsForMatch
        self.reset()
        return self.commandsForMatch
    
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
        ignoreSignals = [ signal.SIGCHLD, signal.SIGCONT, signal.SIGBUS, signal.SIGSEGV ] #@UndefinedVariable
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
        self.writeApplicationEventDetails(self.applicationEvents, minDelayLevel=0) # no means of delaying received signals
        self.record(signalCommandName + " " + self.signalNames[signum])
        self.processDelayedEvents(self.delayedEvents)
        self.delayedEvents = []
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
            if event.checkPreviousWhenRejected() and self.stateChangeEventInfo:
                stateChangeOutput, stateChangeEvent, _, _ = self.stateChangeEventInfo
                if event.implies(stateChangeOutput, stateChangeEvent, *args):
                    self.logger.debug("Discarded event implies previous state change event, ignoring previous also")
                    self.stateChangeEventInfo = None
            return
        
        impliesPrevious, writtenAppEvents = False, False
        if self.stateChangeEventInfo:
            stateChangeOutput, stateChangeEvent, stateChangeDelayLevel, appEvents = self.stateChangeEventInfo
            if stateChangeDelayLevel >= event.delayLevel(*args):
                impliesPrevious = event.implies(stateChangeOutput, stateChangeEvent, *args)
                writtenAppEvents = self.writeApplicationEventDetails(appEvents, stateChangeDelayLevel)
                if impliesPrevious:
                    self.logger.debug("Implies previous state change event, ignoring previous")
                else:
                    self.recordOrDelay(stateChangeOutput, stateChangeDelayLevel, stateChangeEvent)
                self.stateChangeEventInfo = None

        scriptOutput = event.outputForScript(*args)
        delayLevel = event.delayLevel(*args)
        if event.isStateChange() and delayLevel >= self.getMaximumStoredDelay():
            self.logger.debug("Storing up state change event " + repr(scriptOutput) + " with delay level " + repr(delayLevel))
            appEvents = {} if impliesPrevious else copy(self.applicationEvents)
            self.stateChangeEventInfo = scriptOutput, event, delayLevel, appEvents
        else:
            if not writtenAppEvents or not impliesPrevious:
                self.writeApplicationEventDetails(self.applicationEvents, delayLevel)
            if self.recordOrDelay(scriptOutput, delayLevel, event):
                self.processDelayedEvents(self.delayedEvents)
                self.delayedEvents = []

    def getMaximumStoredDelay(self):
        return max((i[1] for i in self.delayedEvents)) if self.delayedEvents else 0

    def recordOrDelay(self, scriptOutput, delayLevel, source):
        if delayLevel:
            self.logger.debug("Delaying event " + repr(scriptOutput) + " at level " + repr(delayLevel))
            self.delayedEvents.append((scriptOutput, delayLevel, source))
            return False
        else:
            self.record(scriptOutput, source)
            return True

    def restoreDelayedAppEvents(self, level, source):
        # An application event is the last thing we have
        # Don't record it directly, it might be superceded by other things...
        self.logger.debug("Restoring delayed application events...")
        newDelayLevel = level - 1
        # Must reset this, or we can't register new events without them colliding with our stored ones...
        self.delayedEvents = []
        for eventName, category in source:
            self.registerApplicationEvent(eventName, category, delayLevel=newDelayLevel)
        
        self.logger.debug("Done restoring delayed application events.")
        
    def processDelayedEvents(self, events, level=1):
        if len(events):
            self.logger.debug("Processing delayed events at level " + str(level))
            nextLevelEvents = []
            for i, (scriptOutput, delayLevel, source) in enumerate(events):
                if delayLevel == level:
                    userSource = isinstance(source, UserEvent)
                    if not userSource and i == len(events) -1:
                        self.restoreDelayedAppEvents(level, source)
                    else:
                        self.record(scriptOutput, source)
                        if userSource and not source.isStateChange():
                            self.processDelayedEvents(nextLevelEvents, level + 1)
                            nextLevelEvents = []
                else:
                    nextLevelEvents.append((scriptOutput, delayLevel, source))
                
    def record(self, line, event=None):
        self.logger.debug("Recording " + repr(line))
        self.hasAutoRecordings |= line.startswith("Auto.")
        for script in self.getScriptsToRecord(event):
            script.record(line)

    def getScriptsToRecord(self, event):   
        if isinstance(event, UserEvent) and (event.name in self.eventsBlockedTopLevel):
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
        appEventKey = category, delayLevel
        if appEventKey in self.applicationEvents:
            existingEvent = self.applicationEvents.get(appEventKey)
            if existingEvent == eventName:
                eventName += " * 2"
            elif existingEvent.startswith(eventName + " *"):
                currentNumber = int(existingEvent.split()[-1])
                eventName += " * " + str(currentNumber + 1)
            
        self.applicationEvents[appEventKey] = eventName
        self.logger.debug("Got application event '" + eventName + "' in category " + repr(category) +
                          " with delay level " + str(delayLevel))
        for supercededCategory in self.supercededAppEventCategories.get(category, []):
            supercedeKey = supercededCategory, delayLevel
            if supercedeKey in self.applicationEvents:
                self.logger.debug("Superceded and discarded application event " + self.applicationEvents[supercedeKey])
                del self.applicationEvents[supercedeKey]
        if category != "storytext_DEFAULT":
            for supercedeCategory in supercedeCategories + [ "storytext_DEFAULT" ]:
                self.logger.debug("Adding supercede info : " + category + " will be superceded by " + supercedeCategory)
                self.supercededAppEventCategories.setdefault(supercedeCategory, set()).add(category)

    def applicationEventRename(self, oldName, newName, oldCategory, newCategory):
        for appEventKey, oldEventName in self.applicationEvents.items():
            categoryName, delayLevel = appEventKey
            if oldCategory in categoryName:
                del self.applicationEvents[appEventKey]
                newEventName = oldEventName.replace(oldName, newName)
                self.registerApplicationEvent(newEventName, newCategory, delayLevel=delayLevel)
        
        for supercedeCategory, categories in self.supercededAppEventCategories.items():
            if oldCategory in categories:
                categories.remove(oldCategory)
                categories.add(newCategory)
                self.logger.debug("Swapping for " + repr(supercedeCategory) + ": " + repr(oldCategory) + " -> " + repr(newCategory))

    def applicationEventDelay(self, name):
        for appEventKey, eventName in self.applicationEvents.items():
            categoryName, oldDelayLevel = appEventKey
            if eventName == name and oldDelayLevel == 0:
                del self.applicationEvents[appEventKey]
                self.registerApplicationEvent(name, categoryName, delayLevel=1)
                
    def makeMultiple(self, text, count):
        if count == 1:
            return text
        else:
            return text + " * " + str(count)
        
    def parseMultiples(self, text):
        words = text.split()
        if len(words) > 2 and words[-2] == "*" and words[-1].isdigit():
            return " ".join(words[:-2]), int(words[-1])
        else:
            return text, 1

    def reduceApplicationEventCount(self, name, categoryName, delayLevel, remainder):
        newEventName = self.makeMultiple(name, remainder)
        self.logger.debug("Reducing stored application event, now " + newEventName + " at delay level " + repr(delayLevel))
        self.applicationEvents[categoryName, delayLevel] = newEventName

    def getCurrentApplicationEvents(self, events, minDelayLevel):
        allEvents = events.items()
        appEventInfo = {}
        for appEventKey, eventName in allEvents:
            categoryName, currDelayLevel = appEventKey
            if currDelayLevel < minDelayLevel:
                continue
            appEventInfo.setdefault(currDelayLevel, []).append((eventName, categoryName))
            if appEventKey in self.applicationEvents:
                storedFullName = self.applicationEvents[appEventKey]
                if eventName == storedFullName:
                    del self.applicationEvents[appEventKey]
                else:
                    storedName, storedCount = self.parseMultiples(storedFullName)
                    givenName, givenCount = self.parseMultiples(eventName)
                    if storedName == givenName:
                        remainder = storedCount - givenCount
                        self.reduceApplicationEventCount(givenName, categoryName, currDelayLevel, remainder)
        return appEventInfo
                            
    def writeApplicationEventDetails(self, events, minDelayLevel):
        appEventInfo = self.getCurrentApplicationEvents(events, minDelayLevel)
        for delayLevel, eventInfo in appEventInfo.items():
            eventNames = sorted((e[0] for e in eventInfo))
            eventString = ", ".join(eventNames)
            self.recordOrDelay(waitCommandName + " " + eventString, delayLevel, eventInfo)
        return len(appEventInfo) > 0

    def registerShortcut(self, replayScript):
        for script in self.scripts:
            script.registerShortcut(replayScript)
            
    def unregisterApplicationEvent(self, matchFunction):
        for appEventKey, eventName in self.applicationEvents.items():
            categoryName, delayLevel = appEventKey
            if matchFunction(eventName, delayLevel):
                basicName, count = self.parseMultiples(eventName)
                if count == 1:
                    self.logger.debug("Unregistering application event " + repr(eventName) + " in category " + repr(categoryName))
                    del self.applicationEvents[appEventKey]
                else:
                    self.reduceApplicationEventCount(basicName, categoryName, delayLevel, count - 1)
                return True
        return False
    
