

from usecase.javarcptoolkit import simulator as rcpsimulator
import org.eclipse.swtbot.eclipse.gef.finder as gefbot
from org.eclipse.swtbot.swt.finder.exceptions import WidgetNotFoundException
# Force classloading in the test thread where it works...
from org.eclipse.draw2d import *
from org.eclipse.gef import *
from usecase.guishared import GuiEvent
from org.eclipse import swt

class WidgetAdapter(rcpsimulator.WidgetAdapter):
    def getType(self):
        if self.isGefWidget():
            return self.widget.part().__class__.__name__
        else:
            return rcpsimulator.WidgetAdapter.getType(self)
    
    def getName(self):
        if self.isGefWidget():
            model = self.widget.part().getModel()
            name = str(model)
            if hasattr(model, "getName"):
                name = model.getName()
            return name
        else:
            return rcpsimulator.WidgetAdapter.getName(self)
    
    def getUIMapIdentifier(self):
        if self.isGefWidget():
            return self.getIdentifier()
        else:
            return rcpsimulator.WidgetAdapter.getUIMapIdentifier(self)
    
    def findPossibleUIMapIdentifiers(self):
        if self.isGefWidget():
            return [ self.getIdentifier()]
        else:
            return rcpsimulator.WidgetAdapter.findPossibleUIMapIdentifiers(self)
    
    def getIdentifier(self):
        return "Name=" + self.getName() + "," + "Type=" + self.getType()
    
    def isGefWidget(self):
        return isinstance(self.widget, gefbot.widgets.SWTBotGefEditPart)
    
class WidgetMonitor(rcpsimulator.WidgetMonitor):
    def __init__(self, *args, **kw):
        self.allPartRefs = set()
        rcpsimulator.swtsimulator.WidgetMonitor.swtbotMap[EditPart] = (gefbot.widgets.SWTBotGefEditPart, [])
        rcpsimulator.WidgetMonitor.__init__(self, *args, **kw)

    def createSwtBot(self):
        return gefbot.SWTGefBot()

    def monitorAllWidgets(self, parent, widgets):
        rcpsimulator.WidgetMonitor.monitorAllWidgets(self, parent, widgets)
        self.monitorGefWidgets()

    def monitorGefWidgets(self):
        for view in self.bot.views():
            if view.getViewReference() not in self.allPartRefs:
                for viewer in  self.getViewers(view):
                    self.addEditParts(viewer.rootEditPart())
                self.allPartRefs.add(view.getViewReference())
        for editor in self.bot.editors():
            if editor.getReference() not in self.allPartRefs:
                for viewer in  self.getViewers(editor):
                    self.addEditParts(viewer.rootEditPart())
                self.allPartRefs.add(editor.getReference())

    def getViewers(self, part):
        # Default implementation returns only one viewer.
        viewers = []
        viewer = self.getViewer(part.getTitle())
        if viewer:
            viewers.append(viewer)
        return viewers
            
    def getViewer(self, name):
        viewer = None
        try:
            viewer = self.bot.gefViewer(name)
        except WidgetNotFoundException:
            pass
        return viewer

    def addEditParts(self, root):
        # Skip the root
        for editPart in root.children():
            self.addEditPart(editPart)

    def addEditPart(self, botPart):
        self.monitorEditParts(botPart)
        self.addEditPartChildren(botPart)

    def addEditPartChildren(self, part):        
        for child in part.children():
            self.addEditPart(child)
    
    def monitorEditParts(self, botPart):
        adapter = WidgetAdapter.adapt(botPart)
        self.uiMap.monitorWidget(adapter)
    
    def setWidgetAdapter(self):
        WidgetAdapter.setAdapterClass(WidgetAdapter)

class EditPartSelectEvent(GuiEvent): 
    def connectRecord(self, method):
        class RecordListener(EditPartListener.Stub):                
            def selectedStateChanged(lself, editPart):
                if editPart.getSelected() == EditPart.SELECTED_PRIMARY:
                    method(editPart, self)
                
        rcpsimulator.swtsimulator.runOnUIThread( self.widget.widget.part().addEditPartListener, RecordListener())   
    
    def generate(self, *args):
        self.widget.click()
        
    @classmethod
    def getSignalsToFilter(cls):
        return []

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Select"
       
rcpsimulator.swtsimulator.eventTypes.append((gefbot.widgets.SWTBotGefEditPart, [ EditPartSelectEvent ]))