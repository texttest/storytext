

from storytext.javarcptoolkit import simulator as rcpsimulator
import org.eclipse.swtbot.eclipse.gef.finder as gefbot
from org.eclipse.swtbot.swt.finder.exceptions import WidgetNotFoundException
from org.eclipse.jface.viewers import ISelectionChangedListener
from org.eclipse.ui.internal import EditorReference
# Force classloading in the test thread where it works...
from org.eclipse.draw2d import *
from org.eclipse.gef import *
from storytext.guishared import GuiEvent
from org.eclipse import swt

class WidgetMonitor(rcpsimulator.WidgetMonitor):
    def __init__(self, *args, **kw):
        self.allPartRefs = set()
        rcpsimulator.swtsimulator.WidgetMonitor.swtbotMap[GraphicalViewer] = (gefbot.widgets.SWTBotGefViewer, [])
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
                    adapter = GefViewerAdapter(viewer, view.getViewReference())
                    self.uiMap.monitorWidget(adapter)
                self.allPartRefs.add(view.getViewReference())
        for editor in self.bot.editors():
            if editor.getReference() not in self.allPartRefs:
                for viewer in  self.getViewers(editor):
                    adapter = GefViewerAdapter(viewer, editor.getReference())
                    self.uiMap.monitorWidget(adapter)
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


class GefViewerAdapter(rcpsimulator.WidgetAdapter):
    def __init__(self, widget, partRef):
        self.partReference = partRef
        rcpsimulator.WidgetAdapter.__init__(self, widget)

    def getUIMapIdentifier(self):
        partId = self.partReference.getId()
        if isinstance(self.partReference, EditorReference):
            return self.encodeToLocale("Editor=" + partId + ", " +"Viewer")
        else:
            return self.encodeToLocale("View=" + partId + ", " +"Viewer")

    def findPossibleUIMapIdentifiers(self):
        return [ self.getUIMapIdentifier() ]
    
    def getType(self):
        return "Viewer"

class ViewerEvent(GuiEvent):
    def outputForScript(self, *args):
        return ' '.join([self.name, self.getStateDescription(*args) ])

    def getStateDescription(self, part, *args):
        if self.isMainEditPart(part):
            return self.getObjectDescription(part)
        descs = [self.getObjectDescription(editPart.part()) for editPart in self.widget.selectedEditParts()]
        return ','.join(descs)

    def getObjectDescription(self, editPart):
        # Default implementation
        model = editPart.getModel()
        name = str(model)
        if hasattr(model, "getName"):
            name = model.getName()
        return name

    def isMainEditPart(self, editPart):
        return self.widget.mainEditPart().part() == editPart

    def isInSelection(self, part):
        for editPart in self.widget.selectedEditParts():
            if editPart.part() == part:
                return True
        return False

    def findEditPart(self, editPart, description):
        if self.getObjectDescription(editPart.part()) == description:
            return editPart
        else:
            return self.findEditPartChildren(editPart, description)

    def findEditPartChildren(self, editPart, description):        
        for child in editPart.children():
            finded = self.findEditPart(child, description) 
            if finded:
                return self.findEditPart(child, description)

    def shouldRecord(self, part, *args):
        return not rcpsimulator.swtsimulator.DisplayFilter.hasEvents()

    @classmethod
    def getSignalsToFilter(cls):
        return []
    
    def getBotViewer(self):
        viewerField = self.widget.widget.getClass().getDeclaredField("graphicalViewer")
        viewerField.setAccessible(True)
        return viewerField.get(self.widget.widget)

class ViewerSelectEvent(ViewerEvent):
    def connectRecord(self, method):
        class SelectionListener(ISelectionChangedListener):
            def selectionChanged(lself, event):
                selection = event.getSelection()
                for editPart in selection.toList():
                    method(editPart, self)

        rcpsimulator.swtsimulator.runOnUIThread(self.getBotViewer().addSelectionChangedListener, SelectionListener())

    def generate(self, description, *args):
        parts = []
        for part in description.split(","):
            editPart = self.findEditPart(self.widget.rootEditPart(), part)
            if editPart == self.widget.mainEditPart():
                return self.widget.click(editPart)
            if editPart:
                parts.append(editPart)
        if len(parts) > 0:
            self.widget.select(parts)

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Select"

    def shouldRecord(self, part, *args):
        return len(self.getStateDescription(*args)) > 0 and ViewerEvent.shouldRecord(self, part, *args)

    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput.startswith(stateChangeOutput)
    
    def isStateChange(self, *args):
        return True
    
rcpsimulator.swtsimulator.eventTypes.append((gefbot.widgets.SWTBotGefViewer, [ ViewerSelectEvent ]))
