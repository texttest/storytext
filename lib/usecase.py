
"""
The idea of this module is to implement a generic record/playback framework, independent of
particular GUI frameworks or anything. The only GUI toolkit support by PyUseCase right now is
PyGTK but in principle all the code in this module would be useful for PyQT or wxPython also.

It's also useful for console applications in recording and replaying signals sent to the process.

The module reads the following environment variables. These are set by TextTest, and also
from the pyusecase command line
USECASE_RECORD_SCRIPT (-r)
USECASE_REPLAY_SCRIPT (-p)
USECASE_REPLAY_DELAY  (-d)

The functionality present here is therefore
    
(1) Record and replay for signals received by the process
    - This just happens. If the process gets SIGINT, 'receive signal SIGINT' is recorded
    
(2) Recording specified 'application events'
    - These are events that are not caused by the user doing something, generally the
    application enters a certain state. 

    usecase.applicationEvent("idle handler exit")

    Recording will take the form of recording a "wait" command in USECASE_RECORD_SCRIPT in this
    case as "wait for idle handler exit". When such a command is read from USECASE_REPLAY_SCRIPT,
    the script will suspend and wait to be told that this application event has occurred before proceeding.

    By default, these will overwrite each other, so that only the last one before any other event
    is recorded in the script.

    To override this, you can provide an optional second argument as a 'category', meaning that
    only events in the same category will overwrite each other. Events with no category will
    overwrite all events in all categories.

(3) Basic framework for GUI testing
    - The aim is to handle the boilerplate around a recorder and a replayer here, while
    letting particular extensions fill out which widgets they support. One such extension is currently
    available for PyGTK (gtkusecase.py)
"""

import os, string, sys, signal, time, stat, logging
from threading import Thread
from ndict import seqdict
from shutil import copyfile
from jobprocess import JobProcess

version = "trunk"

# Hard coded commands
waitCommandName = "wait for"
signalCommandName = "receive signal"

# Used by the command-line interface to store the instance it creates
scriptEngine = None

def applicationEvent(*args, **kwargs):
    if scriptEngine:
        scriptEngine.applicationEvent(*args, **kwargs)

def applicationEventRename(*args, **kwargs):
    if scriptEngine:
        scriptEngine.applicationEventRename(*args, **kwargs)

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
    def outputForScript(self, *args): # pragma: no cover - just documenting interface
        return self.name
    def generate(self, argumentString): # pragma: no cover - just documenting interface
        raise UseCaseScriptError, "Don't know how to generate for " + repr(self.outputForScript(argumentString))
    def isStateChange(self):
        # If this is true, recorder will wait before recording and only record if a different event comes in
        return False
    def implies(self, stateChangeLine, stateChangeEvent, *args):
        # If this is true, recorder will not record the state change if immediately followed by this event
        return self is stateChangeEvent

# Behaves as a singleton...
class ScriptEngine:
    usecaseHome = os.path.abspath(os.getenv("USECASE_HOME", os.path.expanduser("~/usecases")))
    def __init__(self, enableShortcuts=False, **kwargs):
        os.environ["USECASE_HOME"] = self.usecaseHome
        self.enableShortcuts = enableShortcuts
        self.recorder = UseCaseRecorder()
        self.replayer = self.createReplayer(**kwargs)

    def recorderActive(self):
        return self.enableShortcuts or self.recorder.isActive()

    def replayerActive(self):
        return self.enableShortcuts or self.replayer.isActive()

    def active(self):
        return self.replayerActive() or self.recorderActive()

    def createReplayer(self, **kwargs):
        return UseCaseReplayer()

    def applicationEvent(self, name, category=None, supercedeCategories=[], timeDelay=0.001):
        # Small time delay to avoid race conditions: see replayer
        if self.recorderActive():
            self.recorder.registerApplicationEvent(name, category, supercedeCategories)
        if self.replayerActive():
            self.replayer.registerApplicationEvent(name, timeDelay)
            
    def applicationEventRename(self, oldName, newName, oldCategory=None, newCategory=None):
        # May need to recategorise in the recorder
        if self.recorderActive() and oldCategory != newCategory:
            self.recorder.applicationEventRename(oldName, newName, oldCategory, newCategory)
        if self.replayerActive():
            self.replayer.applicationEventRename(oldName, newName)
    

class ReplayScript:
    def __init__(self, scriptName):
        self.commands = []
        self.exitObservers = []
        self.pointer = 0
        self.name = scriptName
        if not os.path.isfile(scriptName):
            raise UseCaseScriptError, "Cannot replay script " + repr(scriptName) + ", no such file or directory."
        for line in open(scriptName).xreadlines():
            line = line.strip()
            if line != "" and line[0] != "#":
                self.commands.append(line)

    def addExitObserver(self, observer):
        self.exitObservers.append(observer)

    def getShortcutName(self):
        return os.path.basename(self.name).split(".")[0].replace("_", " ").replace("#", "_")

    def getCommand(self, name=""):
        if self.pointer >= len(self.commands):
            if len(name) == 0:
                # reset the script and notify exit only if we weren't trying for a specific command
                self.pointer = 0
                for observer in self.exitObservers:
                    observer.notifyExit()
        else:
            nextCommand = self.commands[self.pointer]
            if len(name) == 0 or nextCommand.startswith(name):
                # Filter blank lines and comments
                self.pointer += 1
                return nextCommand        

    def getCommands(self):
        command = self.getCommand()
        if not command:
            return []

        # Process application events together with the previous command so the log comes out sensibly...
        waitCommand = self.getCommand(waitCommandName)
        if waitCommand:
            return [ command, waitCommand ]
        else:
            return [ command ]
        
    
class UseCaseReplayer:
    def __init__(self):
        self.logger = logging.getLogger("usecase replay log")
        self.scripts = []
        self.events = {}
        self.waitingForEvents = []
        self.applicationEventNames = []
        self.replayThread = None
        self.timeDelayNextCommand = 0
        replayScript = os.getenv("USECASE_REPLAY_SCRIPT")
        if replayScript:
            self.addScript(ReplayScript(replayScript))
    
    def isActive(self):
        return len(self.scripts) > 0
    
    def addEvent(self, event):
        self.events[event.name] = event
    
    def addScript(self, script):
        self.scripts.append(script)
        waitCommand = script.getCommand(waitCommandName)
        if waitCommand:
            self.processWait(self.getArgument(waitCommand, waitCommandName))
        else:
            self.enableReading()
        
    def enableReading(self):
        # By default, we create a separate thread for background execution
        # GUIs will want to do this as idle handlers
        self.replayThread = Thread(target=self.runCommands)
        self.replayThread.start()
        #gtk.idle_add(method)

    def registerApplicationEvent(self, eventName, timeDelay):
        self.applicationEventNames.append(eventName)
        self.logger.debug("Replayer got application event " + repr(eventName))
        self.timeDelayNextCommand = timeDelay
        if self.waitingCompleted():
            if self.replayThread:
                self.replayThread.join()
            for eventName in self.waitingForEvents:
                self.applicationEventNames.remove(eventName)
            self.enableReading()
            
    def applicationEventRename(self, oldName, newName):
        toRename = filter(lambda eventName: oldName in eventName and newName not in eventName,
                          self.applicationEventNames)
        self.logger.debug("Renaming events " + repr(oldName) + " to " + repr(newName))
        for eventName in toRename:
            self.applicationEventNames.remove(eventName)
            newEventName = eventName.replace(oldName, newName)
            self.registerApplicationEvent(newEventName, timeDelay=0)
        self.logger.debug("Finished renaming")

    def waitingCompleted(self):
        if len(self.waitingForEvents) == 0:
            return False
        for eventName in self.waitingForEvents:
            if not eventName in self.applicationEventNames:
                return False
        return True

    def runCommands(self):
        while self.runNextCommand():
            pass

    def getCommands(self):
        nextCommands = self.scripts[-1].getCommands()
        if len(nextCommands) > 0:
            return nextCommands

        del self.scripts[-1]
        if len(self.scripts) > 0:
            return self.getCommands()
        else:
            return []
        
    def runNextCommand(self):
        if len(self.waitingForEvents):
            self.write("")
        for eventName in self.waitingForEvents:
            self.write("Expected application event '" + eventName + "' occurred, proceeding.")
        self.waitingForEvents = []
        if self.timeDelayNextCommand:
            self.logger.debug("Sleeping for " + repr(self.timeDelayNextCommand) + " seconds...")
            time.sleep(self.timeDelayNextCommand)
            self.timeDelayNextCommand = 0
        commands = self.getCommands()
        if len(commands) == 0:
            return False
        for command in commands:
            try:
                commandName, argumentString = self.parseCommand(command)
                self.logger.debug("About to perform " + repr(commandName) + " with arguments " + repr(argumentString))
                if commandName == waitCommandName:
                    if not self.processWait(argumentString):
                        return False
                else:
                    self.processCommand(commandName, argumentString)
            except UseCaseScriptError:
                type, value, traceback = sys.exc_info()
                self.write("ERROR: " + str(value))
            # We don't terminate scripts if they contain errors
        return True
    
    def write(self, line):
        try:
            self.logger.info(line)
        except IOError: # pragma: no cover - not easy to reproduce this
            # Can get interrupted system call here as it tries to close the file
            # This isn't worth crashing over!
            pass

    def processCommand(self, commandName, argumentString):
        if commandName == signalCommandName:
            self.processSignalCommand(argumentString)
        else:
            event = self.events[commandName]
            self.write("")
            self.write("'" + commandName + "' event created with arguments '" + argumentString + "'")
            event.generate(argumentString)
            
    def parseCommand(self, scriptCommand):
        commandName = self.findCommandName(scriptCommand)
        if not commandName:
            raise UseCaseScriptError, "Could not parse script command '" + scriptCommand + "'"
        argumentString = self.getArgument(scriptCommand, commandName)
        return commandName, argumentString

    def getArgument(self, scriptCommand, commandName):
        return scriptCommand.replace(commandName, "").strip()

    def findCommandName(self, command):
        if command.startswith(waitCommandName):
            return waitCommandName
        if command.startswith(signalCommandName):
            return signalCommandName

        longestEventName = ""
        for eventName in self.events.keys():
            if command.startswith(eventName) and len(eventName) > len(longestEventName):
                longestEventName = eventName
        return longestEventName            
    
    def processWait(self, applicationEventStr):
        allHappened = True
        self.write("") # blank line
        for applicationEventName in applicationEventStr.split(", "):
            self.write("Waiting for application event '" + applicationEventName + "' to occur.")
            if applicationEventName in self.applicationEventNames:
                self.write("Expected application event '" + applicationEventName + "' occurred, proceeding.")
                self.applicationEventNames.remove(applicationEventName)
            else:
                self.waitingForEvents.append(applicationEventName)
                allHappened = False
        return allHappened

    def processSignalCommand(self, signalArg):
        exec "signalNum = signal." + signalArg
        self.write("")
        self.write("Generating signal " + signalArg)
        JobProcess(os.getpid()).killAll(signalNum) # So we can generate signals for ourselves...
        self.logger.debug("Signal " + signalArg + " has been sent")


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
        

class UseCaseRecorder:
    def __init__(self):
        self.logger = logging.getLogger("usecase record")
        # Store events we don't record at the top level, usually controls on recording...
        self.eventsBlockedTopLevel = []
        self.scripts = []
        self.processId = os.getpid()
        self.applicationEvents = seqdict()
        self.supercededAppEventCategories = {}
        self.suspended = 0
        self.realSignalHandlers = {}
        self.origSignal = signal.signal
        self.signalNames = {}
        self.stateChangeEventInfo = None
        recordScript = os.getenv("USECASE_RECORD_SCRIPT")
        if recordScript:
            self.addScript(recordScript)
            if os.name != "nt":
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
            if event.implies(*(self.stateChangeEventInfo + args)):
                self.logger.debug("Implies previous state change event, ignoring previous")
            else:
                self.logger.debug("Recording previous state change " + repr(self.stateChangeEventInfo[0]))
                self.record(*self.stateChangeEventInfo)

        scriptOutput = event.outputForScript(*args)
        self.writeApplicationEventDetails()
        if event.isStateChange():
            self.logger.debug("Storing up state change event " + repr(scriptOutput))
            self.stateChangeEventInfo = scriptOutput, event
        else:
            self.logger.debug("Recording  " + repr(scriptOutput))
            self.stateChangeEventInfo = None
            self.record(scriptOutput, event)

    def record(self, line, event=None):
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
            self.applicationEvents = seqdict()
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
            self.logger.debug("Recording wait for " + repr(eventString))
            self.applicationEvents = seqdict()

    def registerShortcut(self, replayScript):
        for script in self.scripts:
            script.registerShortcut(replayScript)
