
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
        log = logging.getLogger("gui log")
        log.debug("Starting application with args : " + " ".join(cmdArgs))
        launcher.Main.main(cmdArgs)
        

    def getDefaultTestscriptPluginName(self):
        return "org.eclipse.swtbot.testscript"
        
    def handleAdditionalOptions(self, options):
        self.replayer.disable_usecase_names = options.disable_usecase_names
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
        # Load all necessary classes
        self.initEclipsePackages()
        self.method()

    def initEclipsePackages(self):
        # Importing one class per package loads all classes in the package 
        from org.eclipse.swt.widgets import Widget
        from org.eclipse.swt.layout import GridLayout
        from org.eclipse.swt.custom import CLabel
        from org.eclipse.swt.browser import Browser
        from org.eclipse.swt.events import ExpandEvent
        from org.eclipse.swt.graphics import Drawable
        from org.eclipse.swt.dnd import Clipboard, TextTransfer
        from org.eclipse.jface.bindings.keys import KeyStroke
        from org.eclipse.swtbot.swt.finder import SWTBot
        from org.eclipse.swtbot.swt.finder.widgets import SWTBotButton
        from org.eclipse.swtbot.swt.finder.results import Result
        from org.eclipse.swtbot.swt.finder.finders import UIThreadRunnable
        from org.eclipse.swtbot.swt.finder.keyboard import Keyboard
        from org.eclipse.swtbot.eclipse.finder import SWTWorkbenchBot
        from org.eclipse.swtbot.eclipse.finder.widgets import SWTBotView
        
        
class UseCaseReplayer(javaswttoolkit.UseCaseReplayer):
    def __init__(self, *args, **kw):
        javaswttoolkit.UseCaseReplayer.__init__(self, *args, **kw)
        self.disable_usecase_names = False
        
    def setThreadCallbacks(self):
        mainMethod = self.runReplay if self.isActive() else self.setUpMonitoring
        methods = [ mainMethod, self.enableJobListener, self.runOnRecordExit ]
        runners = map(self.getTestRunnerClass(), methods)
        try:
            from org.eclipse.swtbot.testscript import TestRunnableStore
            TestRunnableStore.setTestRunnables(*runners)
        except ImportError:
            sys.stderr.write("ERROR: Could not find SWTBot testscript plugin. Please install it as described at :\n" +
                             "http://www.texttest.org/index.php?page=ui_testing&n=storytext_and_swt\n")
            sys.exit(1)

    def getTestRunnerClass(self):
        return TestRunner

    def runOnRecordExit(self): # pragma: no cover - cannot test with replayer disabled
        if not self.disable_usecase_names:
            self.uiMap.scriptEngine.replaceAutoRecordingForUsecase("javaswt", exitHook=True)
        
        # Eclipse doesn't return control to the python interpreter
        # So we terminate coverage manually at this point if we're measuring it
        self.uiMap.scriptEngine.tryTerminateCoverage()

    def enableJobListener(self):
        from jobsynchroniser import JobListener
        JobListener.enable()
