
""" Don't load any Eclipse stuff at global scope, needs to be importable previous to Eclipse starting """

import sys, threading
from usecase import javaswttoolkit
from java.lang import Runnable, Thread

class ScriptEngine(javaswttoolkit.ScriptEngine):
    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)

    def run_python_file(self, args):
        import org.eclipse.equinox.launcher as launcher
        cmdArgs = [ "-application", "org.eclipse.swtbot.testscript.application",
                    "-testApplication" ] + args
        launcher.Main.main(cmdArgs)


class TestRunner(Runnable):
    def __init__(self, method):
        self.method = method
            
    def run(self):
        # If we have a threading trace, it won't have been set on this thread which was created
        # by Java. So set it here
        if hasattr(threading, "_trace_hook") and threading._trace_hook:
            sys.settrace(threading._trace_hook)
        # Eclipse uses a different class loader, set Jython's class loader
        # to use the same one, or things won't work
        sys.classLoader = Thread.currentThread().getContextClassLoader()
        self.method()

        
class UseCaseReplayer(javaswttoolkit.UseCaseReplayer):
    def setThreadCallbacks(self):
        if self.isActive():
            methods = [ self.runReplay, self.enableJobListener, self.tryTerminateCoverage ]
        else:
            methods = [ self.setUpMonitoring, self.enableJobListener, self.runOnRecordExit ]

        runners = map(TestRunner, methods)
        try:
            from org.eclipse.swtbot.testscript import TestRunnableStore
            TestRunnableStore.setTestRunnables(*runners)
        except ImportError:
            sys.stderr.write("ERROR: Could not find SWTBot testscript plugin. Please install it as described at :\n" +
                             "http://www.texttest.org/index.php?page=ui_testing&n=pyusecase_and_swt\n")
            sys.exit(1)

    def runOnRecordExit(self):
        self.uiMap.scriptEngine.replaceAutoRecordingForUsecase("javaswt")
        self.tryTerminateCoverage()

    def enableJobListener(self):
        from jobsynchroniser import JobListener
        JobListener.enable()

    def tryTerminateCoverage(self):
        # Eclipse doesn't return control to the python interpreter
        # So we terminate coverage manually at this point if we're measuring it
        try:
            import coverage
            coverage.process_shutdown()
        except: # pragma: no cover - Obviously can't measure coverage here!
            pass
    
    def getMonitorClass(self):
        from simulator import WidgetMonitor
        return WidgetMonitor

    def getDescriberClass(self):
        from simulator import Describer
        return Describer
