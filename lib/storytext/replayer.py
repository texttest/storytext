
""" Generic recorder classes. GUI-specific stuff is in guishared.py """

import os, sys, signal, time, logging, re
from threading import Thread, Timer
from definitions import *
from copy import copy
waitRegexp = re.compile(waitCommandName + ".*")

class ReplayScript:
    def __init__(self, scriptName, ignoreComments=False):
        self.commands = []
        self.exitObservers = []
        self.pointer = 0
        self.name = scriptName
        if not os.path.isfile(scriptName):
            raise UseCaseScriptError, "Cannot replay script " + repr(scriptName) + ", no such file or directory."
        for line in open(scriptName):
            line = line.strip()
            if not ignoreComments or (line != "" and line[0] != "#"):
                self.commands.append(line)

    def addExitObserver(self, observer):
        self.exitObservers.append(observer)

    def getShortcutName(self):
        return os.path.basename(self.name).split(".")[0].replace("_", " ").replace("#", "_")

    def getShortcutRegexp(self):
        return self.getRegexp(self.getShortcutName())

    def getShortcutNameWithArgs(self, args):
        splittedName = self.getShortcutName().lower().split("$")
        if len(splittedName) == 1:
            return splittedName[0]
        name = ""
        for i ,part in enumerate(splittedName):
            if i < len(args):
                name += part + args[i]
            else:
                name += part
        return name

    def transformToRegexp(self, text):
        for char in "^[]{}*?|+()":
            text = text.replace(char, "\\" + char)
        # handle numbered variables
        text = re.sub("\$([0-9]+)", "(?P<var\\1>.*)", text)
        # handle unnumbered variables, and make sure we don't match anything longer
        return text.replace("$", "(.*)") + "$"
    
    def getRegexp(self, command):
        return re.compile(self.transformToRegexp(command)) if command else None

    def hasTerminated(self):
        return self.pointer >= len(self.commands)

    def checkTermination(self):
        if self.hasTerminated():
            # reset the script and notify exit only if we weren't trying for a specific command
            self.pointer = 0
            for observer in self.exitObservers:
                observer.notifyExit()
            return True
        else:
            return False

    def getCommandRegexp(self):
        return self.getRegexp(self.getCommand())

    def getCommand(self, args=[], matching=[]):
        if not self.hasTerminated():
            nextCommand = self.commands[self.pointer]
            if len(matching) == 0 or any((regexp.match(nextCommand) for regexp in matching)):
                # Filter blank lines and comments
                self.pointer += 1
                return self.replaceArgs(nextCommand, args)


    def getArgument(self, nextCommand, args):
        pos = nextCommand.find("$")
        if pos + 1 < len(nextCommand):
            followingChar = nextCommand[pos + 1]
            if followingChar.isdigit():
                index = int(followingChar) - 1
                if index < len(args):
                    return args[index]
        currArg = args.pop(0)
        args.append(currArg) # cycle through them...
        return currArg

    def replaceArgs(self, nextCommand, args):
        origCommand = nextCommand
        if args:
            for n in origCommand.split():
                if "$" in n:
                    currArg = self.getArgument(nextCommand, args)
                    nextCommand = re.sub("\$[0-9]*", currArg, nextCommand, 1)
            
        return nextCommand
            
    def getCommandsSoFar(self, args):
        rawCommands = self.commands[:self.pointer - 1] if self.pointer else []
        return [ self.replaceArgs(cmd, args) for cmd in rawCommands]

    @staticmethod
    def isComment(command):
        return len(command) == 0 or command.startswith("#")

    def extractAllComments(self):
        comments = []
        while self.pointer < len(self.commands):
            nextCommand = self.commands[self.pointer]
            if self.isComment(nextCommand):
                comments.append(nextCommand)
                self.pointer += 1
            else:
                break
        return comments

    def getCommands(self, args):
        commands = self.extractAllComments()
        command = self.getCommand(args)
        if command is None:
            return commands
        
        commands.append(command)
        pointerWithCommand = self.pointer
        commentsAfter = self.extractAllComments()

        # Process application events together with the previous command so the log comes out sensibly...
        waitCommand = self.getCommand(args, [ waitRegexp ])
        if waitCommand:
            commands += commentsAfter
            commands.append(waitCommand)
        else:
            self.pointer = pointerWithCommand
        return commands
        
        
class ShortcutManager:
    def __init__(self):
        self.shortcuts = []
        
    def add(self, shortcut):
        self.shortcuts.append((shortcut.getShortcutRegexp(), shortcut))

    def getShortcuts(self):
        # Drop the trailing $ from the pattern
        return sorted(((r.pattern[:-1], shortcut) for r, shortcut in self.shortcuts))
    
    def getRegexps(self):
        return [ r for r, _ in self.shortcuts ]
    
    def findShortcut(self, command):
        bestShortcut, bestArgs = None, []
        for regex, shortcut in self.shortcuts:
            match = regex.match(command)
            if match:
                args = list(match.groups())
                if bestShortcut is None or self.isBetterShortcut(args, bestArgs):
                    bestShortcut, bestArgs = shortcut, args
        return bestShortcut, bestArgs

    def isBetterShortcut(self, args1, args2):
        if len(args1) != len(args2):
            return len(args1) > len(args2)
        
        # If we have the same arguments, choose the shortcut with least text in arguments
        # which implies more text in the given name
        argLength1 = sum(map(len, args1))
        argLength2 = sum(map(len, args2))
        return argLength1 < argLength2
    
    
class UseCaseReplayer:
    def __init__(self, timeout=60):
        self.logger = logging.getLogger("storytext replay log")
        self.scripts = []
        self.shortcutManager = ShortcutManager()
        self.events = {}
        self.waitingForEvents = []
        self.applicationEventNames = set()
        self.replayThread = None
        self.timeDelayNextCommand = 0
        self.eventHappenedMessage = ""
        self.appEventTimer = None
        self.appEventTimeout = timeout
        if os.name == "posix":
            os.setpgrp() # Makes it easier to kill subprocesses

        replayScript = os.getenv("USECASE_REPLAY_SCRIPT")
        if replayScript:
            self.scripts.append((ReplayScript(replayScript), []))
                
    def isActive(self):
        return len(self.scripts) > 0

    def registerShortcut(self, shortcut):
        self.shortcutManager.add(shortcut)

    def getShortcuts(self):
        return self.shortcutManager.getShortcuts()
    
    def addEvent(self, event):
        self.events.setdefault(event.name, []).append(event)
    
    def addScript(self, script, arguments=[], enableReading=False):
        self.scripts.append((script, arguments))
        self.runScript(script, enableReading)

    def tryRunScript(self):
        if self.isActive():
            script, _ = self.scripts[-1]
            self.runScript(script, enableReading=True)

    def runScript(self, script, enableReading):
        if self.shortcutManager.shortcuts:
            scriptCommand = script.getCommand(matching=self.shortcutManager.getRegexps())
            if scriptCommand:
                newScript, args = self.shortcutManager.findShortcut(scriptCommand)
                return self.addScript(newScript, args, enableReading)
        
        if enableReading and self.processInitialWait(script):
            self.enableReading()
            
    def processInitialWait(self, script):
        waitCommand = script.getCommand(matching=[ waitRegexp ])
        if waitCommand:
            self.logger.debug("Initial " + repr(waitCommand) + ", not starting replayer")
            self.handleComment(None) # Keep the comments in the right order...
            return self.processWait(self.getArgument(waitCommand, waitCommandName))
        else:
            return True
        
    def enableReading(self):
        # By default, we create a separate thread for background execution
        # GUIs will want to do this as idle handlers
        self.logger.debug("Spawning replay thread...")
        self.replayThread = Thread(target=self.runCommands)
        self.replayThread.start()
        #gtk.idle_add(method)

    def resetWaitingInfo(self):
        self.eventHappenedMessage = self.makeAppEventMessage()
        self.waitingForEvents = []
        self.applicationEventNames = set()

    def notifyWaitingCompleted(self):
        if self.replayThread:
            self.replayThread.join()
                
        self.resetWaitingInfo()
        self.enableReading()

    def makeAppEventMessage(self):
        text = ""
        for eventName in self.waitingForEvents:
            if eventName in self.applicationEventNames:
                text += "\nExpected application event '" + eventName + "' occurred, proceeding."
            else:
                text += "\nERROR: Expected application event '" + eventName + "' timed out after " + \
                    str(self.appEventTimeout) + " seconds! Trying to proceed."
        return text

    def timeoutApplicationEvents(self):
        self.logger.debug("Waiting aborted after " + str(self.appEventTimeout) + " seconds.")
        self.notifyWaitingCompleted()

    def completedApplicationEvents(self):
        self.logger.debug("Waiting completed, proceeding...")
        if self.appEventTimer:
            self.appEventTimer.cancel()
            self.appEventTimer = None
        self.notifyWaitingCompleted()

    def registerApplicationEvent(self, eventName, timeDelay):
        origEventName = eventName
        count = 2
        while eventName in self.applicationEventNames:
            eventName = origEventName + " * " + str(count)
            count += 1
        self.applicationEventNames.add(eventName)
        self.logger.debug("Replayer got application event " + repr(eventName))
        self.timeDelayNextCommand = timeDelay
        if len(self.waitingForEvents) > 0 and self.waitingCompleted():
            self.completedApplicationEvents()
            
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
        return set(self.waitingForEvents).issubset(self.applicationEventNames)

    def runCommands(self):
        while self.runNextCommand()[0]:
            pass

    def getCommands(self):
        script, scriptArgs = self.scripts[-1]
        nextCommands = script.getCommands(scriptArgs)
        if len(nextCommands) > 0:
            return nextCommands
        
        self.logger.debug("Script '" + script.getShortcutName() + "' has terminated when getting commands, removing from list")
        del self.scripts[-1]
        if len(self.scripts) > 0:
            return self.getCommands()
        else:
            return []

    def checkTermination(self):
        if len(self.scripts) == 0:
            return True
        script, scriptArgs = self.scripts[-1]
        if script.checkTermination():
            self.logger.debug("Script '" + script.getShortcutName() + "' has terminated when checked, removing from list")
            del self.scripts[-1]
            return self.checkTermination()
        else:
            return False

    def describeAppEventsWaiting(self, eventNames):
        self.write("") # blank line
        for eventName in eventNames:
            self.write("Waiting for application event '" + eventName + "' to occur.")    

    def describeAppEventsHappened(self):
        if self.eventHappenedMessage:
            self.write(self.eventHappenedMessage)
            self.eventHappenedMessage = ""

    def handleComment(self, comment):
        pass # Can't do anything here, don't know about the recorder...

    def runNextCommand(self, **kw):
        if self.timeDelayNextCommand:
            self.logger.debug("Sleeping for " + repr(self.timeDelayNextCommand) + " seconds...")
            time.sleep(self.timeDelayNextCommand)
            self.timeDelayNextCommand = 0
        commands = self.getCommands()
        if len(commands) == 0:
            return False, False
        
        for command in commands:
            if ReplayScript.isComment(command):
                self.handleComment(command)
                continue
            
            script, arguments = self.shortcutManager.findShortcut(command)
            if script:
                self.logger.debug("Found shortcut '" + script.getShortcutName() + "' adding to list of script")
                if commands[-1].startswith(waitCommandName):
                    self.logger.debug("Adding wait command '" + commands[-1] + "' to end of shortcut file")
                    script.commands.append(commands[-1])
                self.addScript(script, arguments)
                return self.runNextCommand(**kw)
            else:
                #  Add a delimiter to show that we've replayed something else
                # Helps the recorder know what order to put things in
                self.handleComment(None)
            if command.startswith(waitCommandName):
                eventName = self.getArgument(command, waitCommandName)
                if self.processWait(eventName):
                    self.logger.debug("Event '" + eventName + "' has already happened, no waiting to do")
                    self.resetWaitingInfo()
                else:
                    self.logger.debug("Suspending replay waiting for event '" + eventName + "'")
                    return False, not self.checkTermination()
            else:
                self.parseAndProcess(command, **kw)
        return not self.checkTermination(), False
    
    def write(self, line):
        try:
            self.logger.info(line)
        except IOError: # pragma: no cover - not easy to reproduce this
            # Can get interrupted system call here as it tries to close the file
            # This isn't worth crashing over!
            pass

    def _parseAndProcess(self, command, **kw):
        self.describeAppEventsHappened()
        commandName, argumentString = self.parseCommand(command)
        self.logger.debug("About to perform " + repr(commandName) + " with arguments " + repr(argumentString))
        self.processCommand(commandName, argumentString)

    def parseAndProcess(self, command, **kw):
        try:
            self._parseAndProcess(command, **kw)
        except UseCaseScriptError:
            # We don't terminate scripts if they contain errors
            type, value, _ = sys.exc_info()
            self.write("ERROR: Could not simulate command " + repr(command) + " - " + str(value))
            
    def describeEvent(self, commandName, argumentString):
        self.write("")
        self.write("'" + commandName + "' event created with arguments '" + argumentString + "'")

    def processCommand(self, commandName, argumentString):
        if commandName == signalCommandName:
            self.processSignalCommand(argumentString)
        else:
            self.describeEvent(commandName, argumentString)
            possibleEvents = self.events[commandName]
            # We may have several plausible events with this name,
            # but some of them won't work because widgets are disabled, invisible etc
            # Go backwards to preserve back-compatibility, previously only the last one was considered.
            # The more recently it was added, the more likely it is to work also
            for event in reversed(possibleEvents[1:]):
                try:
                    event.generate(argumentString)
                    return
                except UseCaseScriptError:
                    type, value, _ = sys.exc_info()
                    self.logger.debug("Error, trying another: " + str(value))  
            possibleEvents[0].generate(argumentString)
            
    def parseCommand(self, scriptCommand):
        commandName = self.findCommandName(scriptCommand)
        if not commandName:
            raise UseCaseScriptError, self.getParseError(scriptCommand)
        argumentString = self.getArgument(scriptCommand, commandName)
        return commandName, argumentString

    def getParseError(self, scriptCommand):
        return "could not parse the given text."

    def getArgument(self, scriptCommand, commandName):
        return scriptCommand.replace(commandName, "").strip()

    def findCommandName(self, command):
        if command.startswith(signalCommandName):
            return signalCommandName

        longestEventName = ""
        for eventName in self.events.keys():
            if command.startswith(eventName) and len(eventName) > len(longestEventName):
                longestEventName = eventName
        return longestEventName            

    def startTimer(self, timer):
        self.appEventTimer = timer
        self.appEventTimer.start()

    def setAppEventTimer(self):
        # Break the timer up into 5 sub-timers
        # The point is to prevent timing out too early if the process gets suspended
        subTimerCount = 5 # whatever
        subTimerTimeout = float(self.appEventTimeout) / subTimerCount
        timer = Timer(subTimerTimeout, self.timeoutApplicationEvents)
        for _ in range(subTimerCount - 1):
            timer = Timer(subTimerTimeout, self.startTimer, [ timer ])
        self.startTimer(timer)
    
    def processWait(self, applicationEventStr):
        eventsToWaitFor = applicationEventStr.split(", ")
        self.describeAppEventsWaiting(eventsToWaitFor)
        allEventsToWaitFor = self.waitingForEvents + eventsToWaitFor
        # Must make sure this is atomic - don't add events one at a time with +=
        self.waitingForEvents = allEventsToWaitFor
        complete = self.waitingCompleted()
        if not complete:
            self.setAppEventTimer()
        return complete
    
    def processSignalCommand(self, signalArg):
        signalNum = getattr(signal, signalArg)
        self.write("")
        self.write("Generating signal " + signalArg)
        # Seems os.killpg doesn't exist under Jython
        if os.name == "java":
            os.kill(os.getpid(), signalNum)
        else:
            os.killpg(os.getpgid(0), signalNum) # So we can generate signals for ourselves... @UndefinedVariable
        self.logger.debug("Signal " + signalArg + " has been sent")
