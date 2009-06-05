
"""
The idea of this module is to implement a generic record/playback tool, independent of
particular GUIs or anything. Objects of class "ScriptEngine" may be constructed.

scriptEngine = ScriptEngine(logger = None, enableShortcuts = 0)

(here <logger> is a log4py logger for logging replayed events, if desired: if not they
are logged to standard output. enableShortcuts turns on GUI shortcuts, see later)

The module reads the following environment variables, all of which are set appropriately by TextTest:
USECASE_RECORD_SCRIPT
USECASE_REPLAY_SCRIPT
USECASE_REPLAY_DELAY
USECASE_RECORD_STDIN

These will then be capable of

(1) Recording standard input for later replay.
    - This is acheived by calling scriptEngine.readStdin() instead of sys.stdin.readline()
    directly. The results are recorded to the script indicated by USECASE_RECORD_STDIN
    
(2) Record and replaying external signals received by the process
    - If USECASE_RECORD_SCRIPT is defined, they will be recorded there. If USECASE_REPLAY_SCRIPT
    is defined and a signal command read from it, they will be generated.
    
(3) Recording specified 'application events'
    - These are events that are not caused by the user doing something, generally the
    application enters a certain state. 

    scriptEngine.applicationEvent("idle handler exit")

    Recording will take the form of recording a "wait" command in USECASE_RECORD_SCRIPT in this
    case as "wait for idle handler exit". When such a command is read from USECASE_REPLAY_SCRIPT,
    the script will suspend and wait to be told that this application event has occurred before proceeding.

    By default, these will overwrite each other, so that only the last one before any other event
    is recorded in the script.

    To override this, you can provide an optional second argument as a 'category', meaning that
    only events in the same category will overwrite each other. Events with no category will
    overwrite all events in all categories.

(4) Being extended to be able to deal with GUI events and shortcuts.
    - This is necessarily specific to particular GUI libraries. One such extension is currently
    available for PyGTK (gtkusecase.py)

(5) Being able to pause between replaying replay script events.
    - This allows you to see what is happening more easily and is controlled by the environment
    variable USECASE_REPLAY_DELAY.

(6) Monitoring and killing external processes started by the system under test
    - This is achieved by calling scriptEngine.monitorProcess, passing the process and a name to refer
    to it. The process should be an object with the methods hasTerminated and killAll provided. An example
    class for child processes on UNIX is provided below (UnixChildProcess). Note that the code does not
    actually use this class but only the interface it fulfils.

    In record mode, PyUseCase will then check before recording anything else whether the process is still
    running (according to hasTerminated), if it is not, it will record "terminate process that" followed
    by the description passed to monitorProcess. On reading such a command in replay mode, naturally,
    it will call the killAll() method.

(7) Simulating file edits made by such external programs as monitored in (6)
    - By providing a list of files that may be edited by the program in the third argument of monitorProcess,
    you can ensure a check is made to see if they are updated when the program is closed. If they are and you
    are in record mode, a "make changes to file" statement is recorded along with the file name. The new contents
    of the file are then stored in a directory called 'file_edits' relative to where the script is being recorded.
    In replay mode this will cause the actual file to be overwritten with the contents of the one in file_edits.
"""

import os, string, sys, signal, time, stat, logging
from threading import Thread
from ConfigParser import ConfigParser, NoSectionError, NoOptionError
from ndict import seqdict
from shutil import copyfile
from jobprocess import JobProcess, killSubProcessAndChildren

# Hard coded commands
waitCommandName = "wait for"
signalCommandName = "receive signal"
terminateCommandName = "terminate process that"
fileEditCommandName = "make changes to file"

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
    def shouldRecord(self, *args):
        return True
    def outputForScript(self, *args):
        return self.name
    def generate(self, argumentString):
        pass
    def readyForGeneration(self):
        # If this is false, recorder will wait and then try again
        return True
    def isStateChange(self):
        # If this is true, recorder will wait before recording and only record if a different event comes in
        return False
    def implies(self, stateChangeLine, stateChangeEvent):
        # If this is true, recorder will not record the state change if immediately followed by this event
        return self is stateChangeEvent

# Behaves as a singleton...
class ScriptEngine:
    instance = None
    def __init__(self, enableShortcuts = 0):
        if not os.environ.has_key("USECASE_HOME"):
            os.environ["USECASE_HOME"] = os.path.expanduser("~/usecases")
        else:
            os.environ["USECASE_HOME"] = os.path.abspath(os.environ["USECASE_HOME"])
        self.replayer = self.createReplayer()
        self.recorder = UseCaseRecorder()
        self.enableShortcuts = enableShortcuts
        self.stdinScript = None
        stdinScriptName = os.getenv("USECASE_RECORD_STDIN")
        if stdinScriptName:
            self.stdinScript = RecordScript(stdinScriptName)
        ScriptEngine.instance = self
    def recorderActive(self):
        return self.enableShortcuts or len(self.recorder.scripts) > 0
    def replayerActive(self):
        return self.enableShortcuts or self.replayer.isActive()
    def active(self):
        return self.replayerActive() or self.recorderActive()
    def createReplayer(self):
        return UseCaseReplayer()
    def applicationEvent(self, name, category = None, timeDelay = 0):
        if self.recorderActive():
            self.recorder.registerApplicationEvent(name, category)
        if self.replayerActive():
            self.replayer.registerApplicationEvent(name, timeDelay)
    def applicationEventRename(self, *args):
        # We don't care in the recorder, the name we recorded is still valid
        if self.replayerActive():
            self.replayer.applicationEventRename(*args)
    def monitorProcess(self, name, process, filesEditing = []):
        if self.recorderActive():
            self.recorder.monitorProcess(name, process, filesEditing)
        if self.replayerActive():
            for file in filesEditing:
                self.replayer.registerEditableFile(file)
            self.replayer.monitorProcess(name, process)
    def readStdin(self):
        line = sys.stdin.readline().strip()
        if self.stdinScript:
            self.stdinScript.record(line)
        return line
    def standardName(self, name):
        return name.strip().lower()

class ReplayScript:
    def __init__(self, scriptName):
        self.commands = []
        self.exitObservers = []
        self.pointer = 0
        self.name = scriptName
        if not os.path.isfile(scriptName):
            raise UseCaseScriptError, "Cannot replay script " + scriptName + ", no such file or directory"
        for line in open(scriptName).xreadlines():
            line = line.strip()
            if line != "" and line[0] != "#":
                self.commands.append(line)

    def addExitObserver(self, observer):
        self.exitObservers.append(observer)

    def getShortcutName(self):
        return os.path.basename(self.name).split(".")[0].replace("_", " ").replace("#", "_")

    def rollback(self, amount):
        self.pointer -= amount

    def getCommand(self, name=""):
        if self.pointer >= len(self.commands):
            for observer in self.exitObservers:
                observer.notifyExit()
            if len(name) == 0:
                # reset the script only if we weren't trying for a specific command
                self.pointer = 0
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
        self.delay = int(os.getenv("USECASE_REPLAY_DELAY", 0))
        self.waitingForEvents = []
        self.applicationEventNames = []
        self.processes = {}
        self.fileFullPaths = {}
        self.fileEditDir = None
        self.replayThread = None
        self.timeDelayNextCommand = 0
        replayScript = os.getenv("USECASE_REPLAY_SCRIPT")
        if replayScript:
            replayDir, local = os.path.split(replayScript)
            self.fileEditDir = os.path.join(replayDir, "file_edits")
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
    def registerEditableFile(self, fullPath):
        self.fileFullPaths[os.path.basename(fullPath)] = fullPath
    def enableReading(self):
        # If events fail, we store them and wait for the relevant handler
        self.waitingForEvents = []
        self.executeCommandsInBackground()
    def executeCommandsInBackground(self):
        # By default, we create a separate thread for background execution
        # GUIs will want to do this as idle handlers
        self.replayThread = Thread(target=self.runCommands)
        self.replayThread.start()
        #gtk.idle_add(method)
    def registerApplicationEvent(self, eventName, timeDelay = 0):
        self.applicationEventNames.append(eventName)
        if self.waitingCompleted():
            if self.replayThread:
                self.replayThread.join()
            for eventName in self.waitingForEvents:
                self.write("Expected application event '" + eventName + "' occurred, proceeding.")
                self.applicationEventNames.remove(eventName)
            self.timeDelayNextCommand = timeDelay
            self.enableReading()
    def applicationEventRename(self, oldName, newName):
        toRename = filter(lambda eventName: eventName.find(oldName) != -1 and eventName.find(newName) == -1,
                          self.applicationEventNames)
        for eventName in toRename:
            newEventName = eventName.replace(oldName, newName)
            self.registerApplicationEvent(newEventName)
    def waitingCompleted(self):
        if len(self.waitingForEvents) == 0:
            return False
        for eventName in self.waitingForEvents:
            if not eventName in self.applicationEventNames:
                return False
        return True
    def monitorProcess(self, name, process):
        self.processes[name] = process
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
        if self.timeDelayNextCommand:
            time.sleep(self.timeDelayNextCommand)
            self.timeDelayNextCommand = 0
        commands = self.getCommands()
        if len(commands) == 0:
            return False
        for command in commands:
            try:
                commandName, argumentString = self.parseCommand(command)
                if commandName == waitCommandName:
                    if not self.processWait(argumentString):
                        return False
                elif not self.processCommand(commandName, argumentString):
                    self.scripts[-1].rollback(len(commands))
                    return True
            except UseCaseScriptError:
                type, value, traceback = sys.exc_info()
                self.write("ERROR: " + str(value))
            # We don't terminate scripts if they contain errors
        return True
    
    def write(self, line):
        try:
            self.logger.info(line)
        except IOError:
            # Can get interrupted system call here as it tries to close the file
            # This isn't worth crashing over!
            pass

    def processCommand(self, commandName, argumentString):
        if self.delay:
            time.sleep(self.delay)
        if commandName == fileEditCommandName:
            return self.processFileEditCommand(argumentString)
        if commandName == terminateCommandName:
            return self.processTerminateCommand(argumentString)
        elif commandName == signalCommandName:
            return self.processSignalCommand(argumentString)
        else:
            event = self.events[commandName]
            if event.readyForGeneration():
                self.write("")
                self.write("'" + commandName + "' event created with arguments '" + argumentString + "'")
                event.generate(argumentString)
                return True
            else:
                return False

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
        if command.startswith(fileEditCommandName):
            return fileEditCommandName
        if command.startswith(terminateCommandName):
            return terminateCommandName
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
        return True
    def processFileEditCommand(self, fileName):
        self.write("")
        self.write("Making changes to file " + fileName + "...")
        sourceFile = os.path.join(self.fileEditDir, fileName)
        if os.path.isfile(sourceFile):
            if self.fileFullPaths.has_key(fileName):
                targetFile = self.fileFullPaths[fileName]
                copyfile(sourceFile, targetFile)
            else:
                self.write("ERROR: No file named '" + fileName + "' is being edited, cannot update!")
        else:
            self.write("ERROR: Could not find updated version of file " + fileName)
        return True
    def processTerminateCommand(self, procName):
        self.write("")
        self.write("Terminating process that " + procName + "...")
        if self.processes.has_key(procName):
            process = self.processes[procName]
            killSubProcessAndChildren(process)
            del self.processes[procName]
        else:
            self.write("ERROR: Could not find process that '" + procName + "' to terminate!!")
        return True

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
        self.unmatchedCommands.append(line)
        return 0
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
        self._record(line)
        for tracker in self.shortcutTrackers:
            if tracker.updateCompletes(line):
                self.rerecord(tracker.getNewCommands())
    def _record(self, line):
        if not self.fileForAppend:
            self.fileForAppend = open(self.scriptName, "w")
        self.fileForAppend.write(line + "\n")
    def registerShortcut(self, shortcut):
        self.shortcutTrackers.append(ShortcutTracker(shortcut))
    def rerecord(self, newCommands):
        self.fileForAppend.close()
        os.remove(self.scriptName)
        self.fileForAppend = None
        for command in newCommands:
            self._record(command)

class UseCaseRecorder:
    def __init__(self):
        self.events = []
        # Store events we don't record at the top level, usually controls on recording...
        self.eventsBlockedTopLevel = []
        self.scripts = []
        self.processId = os.getpid()
        self.applicationEvents = seqdict()
        self.translationParser = self.readTranslationFile()
        self.suspended = 0
        self.realSignalHandlers = {}
        self.origSignal = signal.signal
        self.signalNames = {}
        self.processes = []
        self.recordDir = None
        self.stateChangeEventInfo = None
        recordScript = os.getenv("USECASE_RECORD_SCRIPT")
        if recordScript:
            self.addScript(recordScript)
            self.recordDir, local = os.path.split(recordScript)
        for entry in dir(signal):
            if entry.startswith("SIG") and not entry.startswith("SIG_"):
                exec "number = signal." + entry
                self.signalNames[number] = entry
    def notifyExit(self):
        self.suspended = 0
    def addScript(self, scriptName):
        self.scripts.append(RecordScript(scriptName))
        if len(self.scripts) == 1:
            self.addSignalHandlers()
    def addSignalHandlers(self):
        signal.signal = self.appRegistersSignal
        for signum in range(signal.NSIG):
            try:
                # Don't record SIGCHLD unless told to, these are generally ignored
                # Also don't record SIGCONT, which is sent by LSF when suspension resumed
                if signum != signal.SIGCHLD and signum != signal.SIGCONT:
                    self.realSignalHandlers[signum] = self.origSignal(signum, self.recordSignal)
            except:
                # Various signals aren't really valid here...
                pass
    def appRegistersSignal(self, signum, handler):
        # Don't want to interfere after a fork, leave child processes to the application to manage...
        if os.getpid() == self.processId:
            self.realSignalHandlers[signum] = handler
        else:
            self.origSignal(signum, handler)
            
    def removeSignalHandlers(self):
        for signum, handler in self.realSignalHandlers.items():
            self.origSignal(signum, handler)
        self.realSignalHandlers = {}
    def blockTopLevel(self, eventName):
        self.eventsBlockedTopLevel.append(eventName)
    def terminateScript(self):
        del self.scripts[-1]
        if len(self.scripts) == 0:
            self.removeSignalHandlers()
    def readTranslationFile(self):
        fileName = os.path.join(os.environ["USECASE_HOME"], "usecase_translation")
        configParser = ConfigParser()
        if os.path.isfile(fileName):
            try:
                configParser.read(fileName)
            except:
                # If we can't read it, press on...
                pass
        return configParser
    def modifiedTime(self, file):
        if os.path.isfile(file):
            return os.stat(file)[stat.ST_MTIME]
        else:
            return 0
    def monitorProcess(self, name, process, filesEdited):
        filesWithDates = []
        for file in filesEdited:
            filesWithDates.append((file, self.modifiedTime(file)))
        self.processes.append((name, process, filesWithDates))
    def recordTermination(self, name, filesWithDates):
        for file, oldModTime in filesWithDates:
            if self.modifiedTime(file) != oldModTime:
                self.recordFileUpdate(file)
        self.record(terminateCommandName + " " + name)
    def recordFileUpdate(self, file):
        localName = os.path.basename(file)
        editDir = os.path.join(self.recordDir, "file_edits")
        if not os.path.isdir(editDir):
            os.makedirs(editDir)
        copyfile(file, os.path.join(editDir, localName))
        self.record(fileEditCommandName + " " + localName)
    def checkProcesses(self):
        newProcesses = []
        for name, process, filesWithDates in self.processes:
            if process.poll() is not None:
                self.recordTermination(name, filesWithDates)
            else:
                newProcesses.append((name, process, filesWithDates))
        self.processes = newProcesses
    def recordSignal(self, signum, stackFrame):
        self.writeApplicationEventDetails()
        self.checkProcesses()
        self.record(signalCommandName + " " + self.signalNames[signum])
        # Reset the handler and send the signal to ourselves again...
        realHandler = self.realSignalHandlers[signum]
        # If there was no handler-override installed, resend the signal with the handler reset
        if realHandler == signal.SIG_DFL:
            self.origSignal(signum, self.realSignalHandlers[signum])
            print "Killing process", self.processId, "with signal", signum
            os.kill(self.processId, signum)
            # If we're still alive, set the signal handler back again to record future signals
            self.origSignal(signum, self.recordSignal)
        else:
            # If there was a handler, just call it
            realHandler(signum, stackFrame)
    def translate(self, line, eventName):
        try:
            newName = self.translationParser.get("use case actions", eventName)
            return line.replace(eventName, newName)
        except (NoSectionError, NoOptionError):
            return line
    def addEvent(self, event):
        self.events.append(event)
    def writeEvent(self, *args):
        if len(self.scripts) == 0 or self.suspended == 1:
            return
        event = self.findEvent(*args)
        if not event.shouldRecord(*args):
            return

        if self.stateChangeEventInfo:
            if not event.implies(*self.stateChangeEventInfo):
                self.record(*self.stateChangeEventInfo)

        scriptOutput = event.outputForScript(*args)
        lineToRecord = self.translate(scriptOutput, event.name)
        self.checkProcesses()
        self.writeApplicationEventDetails()
        if event.isStateChange():
            self.stateChangeEventInfo = lineToRecord, event
        else:
            self.stateChangeEventInfo = None
            self.record(lineToRecord, event)
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
    def registerApplicationEvent(self, eventName, category):
        if category:
            self.applicationEvents[category] = eventName
        else:
            # Non-categorised event makes all previous ones irrelevant
            self.applicationEvents = seqdict()
            self.applicationEvents["gtkscript_DEFAULT"] = eventName
    def writeApplicationEventDetails(self):
        if len(self.applicationEvents) > 0:
            eventString = string.join(self.applicationEvents.values(), ", ")
            self.record(waitCommandName + " " + eventString)
            self.applicationEvents = seqdict()
    def registerShortcut(self, replayScript):
        for script in self.scripts:
            script.registerShortcut(replayScript)
    
