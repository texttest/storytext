
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
    def __init__(self, method, *args):
        self.method = method
        self.args = args
            
    def run(self):
        # Eclipse uses a different class loader, set Jython's class loader
        # to use the same one, or things won't work
        sys.classLoader = Thread.currentThread().getContextClassLoader()
        self.method(*self.args)

        
class UseCaseReplayer(javaswttoolkit.UseCaseReplayer):
    def tryAddDescribeHandler(self):
        # Set up used for recording
        runner = TestRunner(self.setUpMonitoring)
        recordExitRunner = TestRunner(self.uiMap.scriptEngine.replaceAutoRecordingForUsecase, "javaswt")
        self.setTestRunnables(runner, recordExitRunner)
    
    def enableReading(self):
        runner = TestRunner(self.runReplay)
        self.setTestRunnables(runner)

    def setTestRunnables(self, runner, exitRunner=None):
        from org.eclipse.swtbot.testscript import TestRunnableStore
        TestRunnableStore.setTestRunnables(runner, exitRunner)

    def setUpMonitoring(self):
        from org.eclipse.swtbot.eclipse.finder import SWTWorkbenchBot
        from javaswttoolkit.simulator import WidgetMonitor
        WidgetMonitor.botClass = SWTWorkbenchBot
        return javaswttoolkit.UseCaseReplayer.setUpMonitoring(self)

