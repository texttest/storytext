
# Module which more or less handles a group of processes as a job:

# - find all the child processes of a random process (on UNIX via ps, on Windows there aren't any) 
# - kill them all (hack for lack of os.kill on Windows)
# - pretty print names for them (on UNIX) based on whatever ps says

# We try to make the JobProcess class look as much like subprocess.Popen objects as possible
# so we can if necessary treat them interchangeably.

import signal, os, time, subprocess

class UNIXProcessHandler:
    def findProcessName(self, pid):
        pslines = os.popen("ps -l -p " + str(pid) + " 2> /dev/null").readlines()
        if len(pslines) > 1:
            return pslines[-1].split()[-1]
        else:
            return "" # process couldn't be found
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
    def kill(self, process, killSignal):
        try:
            os.kill(process, killSignal)
            return True
        except OSError:
            return False
    def poll(self, processId):
        lines = os.popen("ps -p " + str(processId) + " 2> /dev/null").readlines()
        if len(lines) < 2 or lines[-1].strip().endswith("<defunct>"):
            return "returncode" # should return return code but can't be bothered, don't use it currently
    
class WindowsProcessHandler:
    def findProcessName(self, pid):
        return "Process " + str(pid) # for want of anything better...
    def findChildProcesses(self, processId):
        return [] # you what?
    def kill(self, process, killSignal):
        # Why isn't something like this in os.kill ???
        try:
            return self.tryKill("tskill", process)
        except OSError:
            try:
                return self.tryKill("pskill", process)
            except OSError:
                print "WARNING - neither tskill nor pskill found, not able to kill processes"
                # We don't propagate the exception or nothing at all might work...
                return True
    def tryKill(self, tool, process):
        cmdArgs = [ tool, str(process) ]
        return subprocess.call(cmdArgs, stdout=open(os.devnull, "w"), stderr=subprocess.STDOUT) == 0
    def poll(self, pid):
        return True # We assume tskill always works, we have no way of checking otherwise...

class JobProcess:
    if os.name == "posix":
        processHandler = UNIXProcessHandler()
    else:
        processHandler = WindowsProcessHandler()
    def __init__(self, pid):
        self.pid = pid
        self.name = None
    def __repr__(self):
        return self.getName()
    def findAllProcesses(self):
        return [ self ] + self.findChildProcesses()
    def findChildProcesses(self):
        ids = self.processHandler.findChildProcesses(self.pid)
        return [ JobProcess(id) for id in ids ]
    def getName(self):
        if self.name is None:
            self.name = self.processHandler.findProcessName(self.pid)
        return self.name
    def killAll(self, killSignal=None):
        processes = self.findAllProcesses()
        # If intent is to kill everything (signal not specified) start with the deepest child process...
        # otherwise notify the process itself first
        if not killSignal:
            processes.reverse()
        killedSomething = False
        for index in range(len(processes)):
            killedSomething |= processes[index].kill(killSignal)
        return killedSomething
    def kill(self, killSignal):
        if killSignal:
            return self.processHandler.kill(self.pid, killSignal)
        if self.tryKillAndWait(signal.SIGINT):
            return True
        if self.tryKillAndWait(signal.SIGTERM):
            return True
        return self.tryKillAndWait(signal.SIGKILL)
    def tryKillAndWait(self, killSignal):
        if not self.processHandler.kill(self.pid, killSignal):
            return False
        for i in range(10):
            time.sleep(0.1)
            if self.poll() is not None:
                return True
        return False
    def poll(self):
        return self.processHandler.poll(self.pid)
