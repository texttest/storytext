
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
    
    def initEclipsePackages(self):
        javarcptoolkit.UseCaseReplayer.initEclipsePackages(self)
        from org.eclipse.swtbot.eclipse.gef.finder import SWTGefBot
        from org.eclipse.swtbot.eclipse.gef.finder.widgets import SWTBotGefViewer
        from org.eclipse.draw2d import FigureCanvas
        from org.eclipse.draw2d.geometry import Rectangle
        from org.eclipse.gef import EditPart
