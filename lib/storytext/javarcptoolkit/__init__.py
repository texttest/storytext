
""" Don't load any Eclipse stuff at global scope, needs to be importable previous to Eclipse starting """

import sys, threading, logging
from storytext import javaswttoolkit
from java.lang import Runnable, Thread

class ScriptEngine(javaswttoolkit.ScriptEngine):
    def createReplayer(self, universalLogging=False, **kw):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder, **kw)

    def runSystemUnderTest(self, args):
        import org.eclipse.equinox.launcher as launcher
        cmdArgs = [ "-application", self.testscriptPlugin + ".application",
                    "-testApplication" ] + args
        logging.getLogger().debug("Starting application with args : " + " ".join(cmdArgs))
        launcher.Main.main(cmdArgs)
        

    def getDefaultTestscriptPluginName(self):
        return "org.eclipse.swtbot.testscript"

    def importCustomEventTypes(self):
        pass # Otherwise they get loaded too early and hence get the wrong classloader

    def importCustomEventTypesFromSimulator(self):
        javaswttoolkit.ScriptEngine.importCustomEventTypes(self) # Our hook to do it for real...
        
    def handleAdditionalOptions(self, options):
        if options.testscriptpluginid:
            self.testscriptPlugin = options.testscriptpluginid
        else:
            self.testscriptPlugin = self.getDefaultTestscriptPluginName()
        javaswttoolkit.ScriptEngine.handleAdditionalOptions(self, options)


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
        else: # pragma: no cover - cannot test with replayer disabled
            methods = [ self.setUpMonitoring, self.enableJobListener, self.runOnRecordExit ]

        runners = map(TestRunner, methods)
        try:
            from org.eclipse.swtbot.testscript import TestRunnableStore
            TestRunnableStore.setTestRunnables(*runners)
        except ImportError:
            sys.stderr.write("ERROR: Could not find SWTBot testscript plugin. Please install it as described at :\n" +
                             "http://www.texttest.org/index.php?page=ui_testing&n=storytext_and_swt\n")
            sys.exit(1)

    def runOnRecordExit(self): # pragma: no cover - cannot test with replayer disabled
        self.uiMap.scriptEngine.replaceAutoRecordingForUsecase("javaswt", exitHook=True)
        self.tryTerminateCoverage()

    def enableJobListener(self):
        from jobsynchroniser import JobListener
        JobListener.enable()

    def tryTerminateCoverage(self):
        # Eclipse doesn't return control to the python interpreter
        # So we terminate coverage manually at this point if we're measuring it
        try:
            import coverage #@UnresolvedImport
            coverage.process_shutdown()
        except: # pragma: no cover - Obviously can't measure coverage here!
            pass
        
    def shouldReraise(self, e, clsName):
        msg = str(e).strip()
        allowedMessages = [ "No module named customwidgetevents",
                            "cannot import name " + clsName ]
        return msg not in allowedMessages

    def getDescriberClass(self):
        try:
            from customwidgetevents import Describer
        except ImportError, e:
            if self.shouldReraise(e, "Describer"):
                raise
            try:
                from draw2ddescriber import Describer
                return Describer
            except ImportError:
                from describer import Describer
        return Describer
    
    def getMonitorClass(self):
        try:
            from customwidgetevents import WidgetMonitor
        except ImportError, e:
            if self.shouldReraise(e, "WidgetMonitor"):
                raise
            from simulator import WidgetMonitor
        return WidgetMonitor
