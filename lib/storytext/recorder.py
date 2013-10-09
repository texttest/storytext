
""" Generic recorder classes. GUI-specific stuff is in guishared.py """

import os, sys, signal, logging
from copy import copy
import replayer, encodingutils
from definitions import *
from threading import Lock

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

# Take care not to record empty files...
class RecordScript:
    def __init__(self, scriptName, shortcuts):
        self.scriptName = scriptName
        self.fileForAppend = None
        self.shortcutTrackers = []
        self.initShortcutManager(shortcuts)
        self.registerShortcuts()
        
    def initShortcutManager(self, shortcuts):
        self.shortcutManager = replayer.ShortcutManager()
        for shortcut in shortcuts:
            self.shortcutManager.add(shortcut)

    def findCompletedTracker(self, line):
        bestTracker = None
        for tracker in self.shortcutTrackers:
            if tracker.updateCompletes(line) and (bestTracker is None or tracker.isLongerThan(bestTracker)):
                bestTracker = tracker
        
        return bestTracker

    def recordWithTracker(self, line, bestTracker):
        for tracker in self.shortcutTrackers:
            tracker.addCommand(line)
        
        if bestTracker:
            newCommands = bestTracker.getNewCommands()
            self.rerecord(newCommands)
            for tracker in self.shortcutTrackers:
                if tracker is not bestTracker:
                    tracker.rerecord(newCommands)
        else:
            self._record(line)
            
    def findPartLineCompleting(self, eventPairs):
        for eventPair in eventPairs:
            partLine1, partLine2 = eventPair
            partTracker = self.findCompletedTracker(partLine1)
            if partTracker:
                return partLine1, partTracker, partLine2
            partTracker = self.findCompletedTracker(partLine2)
            if partTracker:
                return partLine2, partTracker, partLine1
            
        return None, None, None
    
    def isSplittable(self, line):
        return line.startswith(waitCommandName) and ("," in line or "*" in line)
    
    @staticmethod
    def splitLine(line):
        eventPairs = set()
        parsedEvents = replayer.parseWaitCommand(line)
        for i, (baseEvent, count) in enumerate(parsedEvents):
            otherEvents = parsedEvents[:i] + parsedEvents[i+1:]
            if len(otherEvents):
                basicPair = frozenset([ replayer.assembleWaitCommand(parsedEvents[i:i+1]),
                              replayer.assembleWaitCommand(otherEvents) ])
                eventPairs.add(basicPair)
            if count > 1:
                for j in range(1, count):
                    currEvent = [ (baseEvent, j) ]
                    currOthers = otherEvents + [ (baseEvent, count - j)]
                    parts = (replayer.assembleWaitCommand(currEvent), replayer.assembleWaitCommand(currOthers))
                    partSet = frozenset(parts)
                    eventPairs.add(partSet if len(partSet) == 2 else parts)
        return eventPairs

    def record(self, line):
        try:
            bestTracker = self.findCompletedTracker(line)
            if bestTracker is None and self.isSplittable(line):
                eventPairs = self.splitLine(line)
                partLine, partTracker, otherPartLine = self.findPartLineCompleting(eventPairs)
                if partLine is not None:
                    self.recordWithTracker(partLine, partTracker)
                    self.recordWithTracker(otherPartLine, None)
                    return
                    
            self.recordWithTracker(line, bestTracker)
            
        except IOError:
            sys.stderr.write("ERROR: Unable to record " + repr(line) + " to file " + repr(self.scriptName) + "\n") 
    
    def _record(self, line):
        if not self.fileForAppend:
            self.fileForAppend = encodingutils.openEncoded(self.scriptName, "w")
        # File is in binary mode, must use correct line ending explicitly, "\n" will be UNIX line endings on all platforms
        self.fileForAppend.write(line + os.linesep)
        self.fileForAppend.flush()
    
    def registerShortcuts(self):
        for _, shortcut in self.shortcutManager.shortcuts:
            self.shortcutTrackers.append(ShortcutTracker(shortcut, self.shortcutManager))

    def registerShortcut(self, shortcut):
        self.shortcutManager.add(shortcut)
        self.shortcutTrackers.append(ShortcutTracker(shortcut, self.shortcutManager))
    
    def unregisterShortcut(self, shortcut):
        shortcuts = [s for s in self.shortcutManager.shortcuts]
        trackers = [t for t in self.shortcutTrackers]
        for regexp, script in shortcuts:
            if script.name == shortcut.name:
                self.shortcutManager.shortcuts.remove((regexp,script))
                break
        for tracker in trackers:
            if tracker.replayScript.name == shortcut.name:
                self.shortcutTrackers.remove(tracker)
                break

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
    def __init__(self, replayScript, shortcutManager):
        self.replayScript = replayScript
        self.currentShortcuts = []
        self.commandsForMatch = []
        self.commandsForMismatch = []
        self.visitedShortcuts = []
        self.logger = logging.getLogger("Shortcut Tracker")
        self.shortcutManager = shortcutManager
        self.reset()

    def reset(self):
        self.replayScript = replayer.ReplayScript(self.replayScript.name, ignoreComments=True)
        self.currentShortcuts = []
        self.commandsForMatch = copy(self.commandsForMismatch)
        self.argsUsed = []
        self.currentArgs = []
        self.visitedShortcuts = []
        self.currRegexp = self.getCommandRegexp()

    def hasStarted(self):
        return self.commandsForMismatch != self.commandsForMatch

    def updateCompletes(self, line):
        if self.currRegexp is None:
            return False # We already reached the end and should forever be ignored...
        match = self.currRegexp.match(line)
        self.logger.debug("Update completes? " +  self.replayScript.getShortcutName() + ", " + self.currRegexp.pattern \
                          + ", " +  repr(line) + ", " + repr(self.commandsForMismatch) + ", " + repr(self.commandsForMatch))
        return match and self.isCurrentScript() and self.replayScript.hasTerminated()
    
    def addCommand(self, line):
        if self.currRegexp is None:
            self.logger.debug("Ignore " +  self.replayScript.getShortcutName())  # We already reached the end and should forever be ignored...
            return
        match = self.currRegexp.match(line)
        if match:
            self.commandsForMismatch.append(line)
            self.logger.debug("Match " +  self.replayScript.getShortcutName() + ", " + self.currRegexp.pattern \
                               + ", " +  repr(line) + ", " + repr(self.commandsForMismatch) + ", " + repr(self.commandsForMatch))
            positions = self.getPositions(self.currentArgs)
            self.currRegexp = self.getCommandRegexp()
            groupdict = match.groupdict()
            if groupdict: # numbered arguments
                for key, val in groupdict.items():
                    argPos = int(key.replace("var", "")) - 1
                    if len(positions):
                        self.handleNumberedArg(positions, argPos, val)
                    else:
                        while len(self.argsUsed) <= argPos:
                            self.argsUsed.append("")
                        self.argsUsed[argPos] = val
            else:
                groups = match.groups()
                if len(positions):
                    self.handleUnnumberedArgs(positions, groups)
                else:
                    self.argsUsed += groups
        else:
            if self.hasStarted():
                self.reset()
                self.logger.debug("Reset " + self.replayScript.getShortcutName() + ", " + repr(self.commandsForMismatch))
                self.addCommand(line)
            else:
                self.commandsForMismatch.append(line)
                self.reset()
    
    def getPositions(self, args):
        positions = []
        for index, arg in enumerate(args):
            newArg = arg.replace("$", "")
            if newArg.isdigit():
                positions.append([int(newArg) -1, True])
            elif arg.startswith("$"):
                positions.append([index, False])
            else:
                positions.append([-1, False])
        return positions

    def handleUnnumberedArgs(self, positions, groups):
        for index, [pos, numbered] in enumerate(positions):
            if pos >= 0 and len(groups):
                if numbered:
                    while len(self.argsUsed) <= pos:
                        self.argsUsed.append("")
                    self.argsUsed[pos] = groups[index]
                else:
                    self.argsUsed.append(groups[index])

    def handleNumberedArg(self, positions, currentPos, value):
        pos, numbered = positions[currentPos]
        if numbered:
            while len(self.argsUsed) <= pos:
                self.argsUsed.append("")
            self.argsUsed[pos] = value
        elif pos >= 0:
            self.argsUsed.append(value)
        
    def rerecord(self, newCommands):
        # Some other tracker has completed, include it in our unmatched commands...
        started = self.hasStarted()
        self.commandsForMismatch = copy(newCommands)
        if self.currRegexp is None: # we completed, but haven't been chosen, because there was a better one to use
            self.reset()
        elif not started:
            self.commandsForMatch = copy(self.commandsForMismatch)
        self.logger.debug("Rerecord " + self.replayScript.getShortcutName() + ", " + repr(self.commandsForMismatch) + ", " + repr(self.commandsForMatch))
        
    def getNewCommands(self):
        shortcutName = self.replayScript.getShortcutNameWithArgs(self.argsUsed)
        self.commandsForMatch.append(shortcutName)
        self.commandsForMismatch = self.commandsForMatch
        self.reset()
        return self.commandsForMatch
    
    def isLongerThan(self, otherTracker):
        return self.getLength() > otherTracker.getLength()

    def getCommandRegexp(self):
        nestedShortcut = self.findNestedShortcut(self.currentShortcuts[-1] if not self.isCurrentScript() else self.replayScript)
        if nestedShortcut and self.replayScript.name == nestedShortcut.name:
            return None
        while  nestedShortcut:
            newScript = replayer.ReplayScript(nestedShortcut.name, ignoreComments=True)
            self.visitedShortcuts.append(newScript)
            self.currentShortcuts.append(newScript)
            nestedShortcut = self.findNestedShortcut(self.currentShortcuts[-1] if not self.isCurrentScript() else self.replayScript)

        if not self.isCurrentScript():
            cmdRegexp = self.currentShortcuts[-1].getCommandRegexp()
            if self.currentShortcuts[-1].hasTerminated():
                self.currentShortcuts.pop()
            if cmdRegexp:
                return cmdRegexp
            else:
                return self.getCommandRegexp()
        return self.replayScript.getCommandRegexp()
    
    def findNestedShortcut(self, replayScript):
        scriptCommand = replayScript.getCommand(matching=self.shortcutManager.getRegexps())
        if scriptCommand:
            shortcut, args = self.shortcutManager.findShortcut(scriptCommand)
            if replayScript == self.replayScript:
                self.currentArgs = args
            return shortcut
    
    def isCurrentScript(self):
        return len(self.currentShortcuts) == 0

    def getLength(self):
        length = 0
        for shortcut in self.visitedShortcuts:
            length += len(shortcut.commands)
        return length + len(self.replayScript.commands) - len(self.visitedShortcuts)

class UseCaseRecorder:
    def __init__(self, shortcuts):
        self.logger = logging.getLogger("storytext record")
        # Store events we don't record at the top level, usually controls on recording...
        self.eventsBlockedTopLevel = []
        self.scripts = []
        self.comments = []
        self.processId = os.getpid()
        self.applicationEvents = OrderedDict()
        self.supercededAppEventCategories = {}
        self.suspended = 0
        self.realSignalHandlers = {}
        self.origSignal = signal.signal
        self.signalNames = {}
        self.stateChangeEventInfo = {}
        self.delayedEvents = []
        self.applicationEventLock = Lock()
        self.hasAutoRecordings = False
        recordScript = os.getenv("USECASE_RECORD_SCRIPT")
        if recordScript:
            self.addScript(recordScript, shortcuts)
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

    def storeComment(self, comment):
        self.logger.debug("Storing comment " + repr(comment))
        self.comments.append(comment)

    def addScript(self, scriptName, shortcuts=[]):
        self.scripts.append(RecordScript(scriptName, shortcuts))

    def closeScripts(self, exitHook):
        if any((c is not None for c in self.comments)):
            if exitHook:
                sys.stderr.write("NOTE: discarded terminal comments in usecase file, these are not supported for Java applications.\n")
            else:
                self.recordComments()
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
            if event.checkPreviousWhenRejected():
                delayLevel = event.delayLevel(*args)
                if delayLevel in self.stateChangeEventInfo:
                    stateChangeOutput, stateChangeEvent, stateChangeAppEvents = self.stateChangeEventInfo[delayLevel]
                    if event.implies(stateChangeOutput, stateChangeEvent, *args):
                        self.logger.debug("Discarded event implies previous state change event, ignoring previous also")
                        self.applicationEvents.update(stateChangeAppEvents)
                        del self.stateChangeEventInfo[delayLevel]
            return
        
        impliesPrevious = False
        delayLevel = event.delayLevel(*args)
        if delayLevel in self.stateChangeEventInfo:
            stateChangeOutput, stateChangeEvent, appEvents = self.stateChangeEventInfo[delayLevel]
            impliesPrevious = event.implies(stateChangeOutput, stateChangeEvent, *args)
            self.writeApplicationEventDetails(appEvents, delayLevel)
            if impliesPrevious:
                self.logger.debug("Implies previous state change event, ignoring previous")
            else:
                self.recordOrDelay(stateChangeOutput, delayLevel, stateChangeEvent)
            del self.stateChangeEventInfo[delayLevel]

        scriptOutput = event.outputForScript(*args)
        if event.isStateChange() and delayLevel >= self.getMaximumStoredDelay():
            appEvents = {} if impliesPrevious else self.transferAppEvents(delayLevel)                
            self.logger.debug("Storing up state change event " + repr(scriptOutput) + " with delay level " + repr(delayLevel) + " and app events " + repr(appEvents))
            self.stateChangeEventInfo[delayLevel] = scriptOutput, event, appEvents
        else:
            # If impliesPrevious is true, it means any app events since the last state change event were essentially generated by the current event
            # In that case they should not be recorded at the moment. We still need to adjust the delay levels though
            delayLevelForAppEvents = max(delayLevel, int(impliesPrevious))
            self.writeApplicationEventDetails(self.applicationEvents, delayLevelForAppEvents)
            if self.recordOrDelay(scriptOutput, delayLevel, event):
                self.processDelayedEvents(self.delayedEvents)
                self.delayedEvents = []

    def transferAppEvents(self, delayLevel):
        appEvents = OrderedDict()
        for appEventKey, eventName in self.applicationEvents.items():
            _, currDelayLevel = appEventKey
            if currDelayLevel < delayLevel:
                continue
            appEvents[appEventKey] = eventName
            del self.applicationEvents[appEventKey]
        return appEvents

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

    def popComment(self):
        # Make this atomic, it can be called from different threads
        try:
            return self.comments.pop(0)
        except IndexError:
            pass
        
    def recordComments(self):
        comment = self.popComment()
        while comment is not None:
            self._record(comment)
            comment = self.popComment()
                
    def record(self, line, event=None):
        self.recordComments()
        self._record(line, event)
        
    def _record(self, line, event=None):
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
        self.applicationEventLock.acquire()
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
        self.applicationEventLock.release()

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

    def applicationEventDelay(self, name, fromLevel=0, increase=True):
        for appEventKey, eventName in self.applicationEvents.items():
            categoryName, oldDelayLevel = appEventKey
            if eventName == name and oldDelayLevel == fromLevel:
                del self.applicationEvents[appEventKey]
                newDelayLevel = oldDelayLevel + 1 if increase else oldDelayLevel - 1
                self.registerApplicationEvent(name, categoryName, delayLevel=newDelayLevel)
                
    def makeMultiple(self, text, count):
        if count == 1:
            return text
        else:
            return text + " * " + str(count)

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
            del events[appEventKey]
        return appEventInfo
                            
    def writeApplicationEventDetails(self, events, minDelayLevel):
        appEventInfo = self.getCurrentApplicationEvents(events, minDelayLevel)
        for delayLevel, eventInfo in appEventInfo.items():
            eventNames = sorted((e[0] for e in eventInfo))
            eventString = ", ".join(eventNames)
            self.recordOrDelay(waitCommandName + " " + eventString, delayLevel, eventInfo)

    def registerShortcut(self, replayScript):
        for script in self.scripts:
            script.registerShortcut(replayScript)

    def unregisterShortcut(self, replayScript):
        for script in self.scripts:
            script.unregisterShortcut(replayScript)
            
    def unregisterApplicationEvent(self, matchFunction):
        for appEventKey, eventName in self.applicationEvents.items():
            categoryName, delayLevel = appEventKey
            if matchFunction(eventName, delayLevel):
                basicName, count = replayer.parseMultiples(eventName)
                if count == 1:
                    self.logger.debug("Unregistering application event " + repr(eventName) + " in category " + repr(categoryName))
                    del self.applicationEvents[appEventKey]
                else:
                    self.reduceApplicationEventCount(basicName, categoryName, delayLevel, count - 1)
                return True
        return False
    
