
import signal, sys, os, string, time, stat

class UNIXProcessHandler:
    def spawnProcess(self, commandLine, shellTitle, holdShell):
        if shellTitle:
            commandLine = "xterm" + self.getShellOptions(holdShell) + " -bg white -T '" + shellTitle + "' -e " + commandLine

        processId = os.fork()   
        if processId == 0:
            os.system(commandLine)
            os._exit(0)
        else:
            return processId, processId
    def getShellOptions(self, holdShell):
        if holdShell:
            return " -hold"
        else:
            return ""
    def hasTerminated(self, processId, childProcess=0):
        if childProcess:
            # This is much more efficient for forked children than calling ps...
            # Also, it doesn't leave defunct processes. Naturally, it doesn't work on other
            # processes...
            try:
                procId, status = os.waitpid(processId, os.WNOHANG)
                return procId > 0 or status > 0
            except OSError:
                return 1
        else:
            lines = os.popen("ps -p " + str(processId) + " 2> /dev/null").readlines()
            return len(lines) < 2 or lines[-1].strip().endswith("<defunct>")
    def findChildProcesses(self, pid):
        outLines = os.popen("ps -efl").readlines()
        return self.findChildProcessesInLines(pid, outLines)
    def findChildProcessesInLines(self, pid, outLines):
        processes = []
        for line in outLines:
            entries = line.split()
            if len(entries) > 4 and entries[4] == str(pid):
                childPid = int(entries[3])
                processes.append(childPid)
                processes += self.findChildProcessesInLines(childPid, outLines)
        return processes
    def findProcessName(self, pid):
        pslines = os.popen("ps -l -p " + str(pid) + " 2> /dev/null").readlines()
        if len(pslines) == 0:
            return self.findProcessName(pid)
        else:
            return pslines[-1].split()[-1]
    def kill(self, process, killSignal):
        return os.kill(process, killSignal)
    def getCpuTime(self, processId):
        # Not supported, mainly here for Windows
        return None

class WindowsProcessHandler:
    def __init__(self):
        self.processManagement = 1
        stdout = os.popen("handle none").read()
        if stdout.find("administrator") != -1:
            print "Cannot determine process IDs: possibly lack of administrator rights for 'handle'"
            self.processManagement = 0
    def spawnProcess(self, commandLine, shellTitle, holdShell):
        # Start the process in a subshell so redirection works correctly
        args = [os.environ["COMSPEC"], self.getShellOptions(holdShell), commandLine ]
        processHandle = os.spawnv(os.P_NOWAIT, args[0], args)
        if not self.processManagement:
            return None, processHandle
        # As we start a shell, we have a handle on the shell itself, not
        # on the process running in it. Unlike UNIX, killing the shell is not enough!
        cmdProcId = self.findProcessId(processHandle)
        if not cmdProcId:
            # The process may have already exited by this point, don't crash if so!
            return None, processHandle
        for subProcId, subProcHandle in self.findChildProcessesWithHandles(cmdProcId):
            return subProcId, processHandle
        # If no subprocesses can be found, just kill the shell
        return cmdProcId, processHandle
    def getShellOptions(self, holdShell):
        if holdShell:
            return "/K"
        else:
            return "/C"
    def findProcessId(self, processHandle):
        childProcesses = self.findChildProcessesWithHandles(str(os.getpid()))
        for subProcId, subProcHandle in childProcesses:
            if subProcHandle == processHandle:
                return subProcId
    def findChildProcesses(self, processId):
        return [ pid for pid, handle in self.findChildProcessesWithHandles(processId) ]
    def findChildProcessesWithHandles(self, processId):
        subprocesses = []
        stdout = os.popen("handle -a -p " + processId)
        for line in stdout.readlines():
            words = line.split()
            if len(words) < 2:
                continue
            if words[1] == "Process":
                processInfo = words[-1]
                idStart = processInfo.find("(")
                subprocesses.append((processInfo[idStart + 1:-1], self.getHandleId(words)))
        return subprocesses
    def findProcessName(self, processId):
        words = self.getPsWords(processId)
        return words[0]
    def getHandleId(self, words):
        try:
            # Drop trailing colon
            return int(words[0][:-1], 16)
        except ValueError:
            return
    def getPsWords(self, processId):
        try:
            stdin, stdout = os.popen4("pslist " + str(processId))
        except WindowsError:
            # don't really know what this means but seems like we should wait and try again...
            time.sleep(0.1)
            return self.getPsWords(processId)
        lines = stdout.readlines()
        for line in lines:
            words = line.split()
            if len(words) < 2:
                continue
            if words[1] == str(processId):
                return words
        fullStr = string.join(lines, "\n")
        if fullStr.find("used by another process") != -1:
            # don't really know what this means but seems like we should wait and try again...
            time.sleep(0.1)
            return self.getPsWords(processId)
        sys.stderr.write("Unexpected output from pslist for " + str(processId) + ": \n" + repr(lines) + "\n")
        return []
    def hasTerminated(self, processId, childProcess=0):
        words = self.getPsWords(processId)
        if len(words) > 2:
            return words[2] == "was"
        else:
            return 1
    def getCpuTime(self, processId):
        words = self.getPsWords(processId)
        if len(words) < 7:
            return None
        cpuEntry = words[6]
        try:
            hours, mins, seconds = cpuEntry.split(":")
            return 3600 * float(hours) + 60 * float(mins) + float(seconds)
        except ValueError:
            return None
    def kill(self, process, killSignal):
        return os.system("pskill " + str(process) + " > nul 2> nul")

class Process:
    if os.name == "posix":
        processHandler = UNIXProcessHandler()
    else:
        processHandler = WindowsProcessHandler()
    def __init__(self, processId):
        self.processId = processId
    def __repr__(self):
        return self.getName()
    def hasTerminated(self):
        for process in self.findAllProcesses():
            if not self.processHandler.hasTerminated(process.processId):
                return 0
        return 1
    def findAllProcesses(self):
        return [ self ] + self.findChildProcesses()
    def findChildProcesses(self):
        ids = self.processHandler.findChildProcesses(self.processId)
        return [ Process(id) for id in ids ]
    def getName(self):
        return self.processHandler.findProcessName(self.processId)
    def waitForTermination(self):
        while not self.hasTerminated():
            time.sleep(0.1)
    def runExitHandler(self):
        pass
    def killAll(self, killSignal=None):
        processes = self.findAllProcesses()
        # If intent is to kill everything (signal not specified) start with the deepest child process...
        # otherwise notify the process itself first
        if not killSignal:
            processes.reverse()
        for index in range(len(processes)):
            verbose = index == 0
            processes[index].kill(killSignal, verbose)
    def getCpuTime(self):
        return self.processHandler.getCpuTime(self.processId)
    def kill(self, killSignal, verbose=1):
        if killSignal:
            return self.tryKill(killSignal)
        if self.tryKillAndWait(signal.SIGINT, verbose):
            return
        if self.tryKillAndWait(signal.SIGTERM, verbose):
            return
        self.tryKillAndWait(signal.SIGKILL, verbose)
    def tryKill(self, killSignal):
        try:
            self.processHandler.kill(self.processId, killSignal)
        except OSError:
            pass
    def tryKillAndWait(self, killSignal, verbose=0):
        if verbose:
            print "Killed process", self.processId, "with signal", killSignal
        self.tryKill(killSignal)
        for i in range(10):
            time.sleep(0.1)
            if self.processHandler.hasTerminated(self.processId):
                return 1
        return 0
