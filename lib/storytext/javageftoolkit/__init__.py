
""" Don't load any Eclipse stuff at global scope, needs to be importable previous to Eclipse starting """

from storytext import javarcptoolkit
import sys

class ScriptEngine(javarcptoolkit.ScriptEngine):
    def createReplayer(self, universalLogging=False, **kw):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder, **kw)

    def getDefaultTestscriptPluginName(self):
        return "org.eclipse.swtbot.gef.testscript"

class UseCaseReplayer(javarcptoolkit.UseCaseReplayer):
    def getDescriberClass(self):
        try:
            from customwidgetevents import Describer
        except ImportError, e:
            if self.shouldReraise(e, "Describer"):
                raise
            from storytext.javaswttoolkit.draw2ddescriber import Describer
        return Describer
    
    def getMonitorClass(self):
        try:
            from customwidgetevents import WidgetMonitor
        except ImportError, e:
            if self.shouldReraise(e, "WidgetMonitor"):
                raise
            from simulator import WidgetMonitor
        return WidgetMonitor
    
