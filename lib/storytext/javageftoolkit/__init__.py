
""" Don't load any Eclipse stuff at global scope, needs to be importable previous to Eclipse starting """

from storytext import javarcptoolkit
import sys

class ScriptEngine(javarcptoolkit.ScriptEngine):
    def createReplayer(self, universalLogging=False, **kw):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder, **kw)

    def getDefaultTestscriptPluginName(self):
        return "org.eclipse.swtbot.gef.testscript"

class UseCaseReplayer(javarcptoolkit.UseCaseReplayer):
    def getDescriberPackage(self):
        return javarcptoolkit.UseCaseReplayer.__module__
