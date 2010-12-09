
""" Don't load any Eclipse stuff at global scope, needs to be importable previous to Eclipse starting """

import javaswttoolkit, sys
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
        # Eclipse uses a different class loader, set Jython's class loader
        # to use the same one, or things won't work
        sys.classLoader = Thread.currentThread().getContextClassLoader()
        self.method()

        
class UseCaseReplayer(javaswttoolkit.UseCaseReplayer):
    def tryAddDescribeHandler(self):
        # Set up used for recording
        runner = TestRunner(self.setUpMonitoring)
        recordExitRunner = TestRunner(self.runOnRecordExit)
        self.setTestRunnables(runner, recordExitRunner)

    def runOnRecordExit(self):
        self.uiMap.scriptEngine.replaceAutoRecordingForUsecase("javaswt")
        self.tryTerminateCoverage()

    def tryTerminateCoverage(self):
        # Eclipse doesn't return control to the python interpreter
        # So we terminate coverage manually at this point if we're measuring it
        try:
            import coverage
            coverage.process_shutdown()
        except: # pragma: no cover - Obviously can't measure coverage here!
            pass
    
    def enableReading(self):
        runner = TestRunner(self.runReplay)
        replayExitRunner = TestRunner(self.tryTerminateCoverage)
        self.setTestRunnables(runner, replayExitRunner)

    def setTestRunnables(self, runner, exitRunner):
        from org.eclipse.swtbot.testscript import TestRunnableStore
        TestRunnableStore.setTestRunnables(runner, exitRunner)

    def setUpMonitoring(self):
        from org.eclipse.swtbot.eclipse.finder import SWTWorkbenchBot
        from javaswttoolkit.simulator import WidgetMonitor
        WidgetMonitor.botClass = SWTWorkbenchBot
        return javaswttoolkit.UseCaseReplayer.setUpMonitoring(self)

