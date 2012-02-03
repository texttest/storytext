

from storytext.javarcptoolkit import simulator as rcpsimulator
from storytext.javaswttoolkit import simulator as swtsimulator
from storytext.definitions import UseCaseScriptError
import org.eclipse.swtbot.eclipse.gef.finder as gefbot
from org.eclipse.swtbot.swt.finder.exceptions import WidgetNotFoundException
from org.eclipse.jface.viewers import ISelectionChangedListener
from org.eclipse.ui.internal import EditorReference
# Force classloading in the test thread where it works...
from org.eclipse.draw2d import * #@UnusedWildImport
from org.eclipse.gef import *
import storytext.guishared
from org.eclipse import swt

def getGefViewer(botViewer):
    viewerField = botViewer.getClass().getDeclaredField("graphicalViewer")
    viewerField.setAccessible(True)
    return viewerField.get(botViewer)

class WidgetMonitor(rcpsimulator.WidgetMonitor):
    def __init__(self, *args, **kw):
        self.allPartRefs = set()
        self.swtbotMap[GraphicalViewer] = (gefbot.widgets.SWTBotGefViewer, [])
        rcpsimulator.WidgetMonitor.__init__(self, *args, **kw)

    def createSwtBot(self):
        return gefbot.SWTGefBot()

    def widgetShown(self, parent, eventType):
        if isinstance(parent, FigureCanvas):
            self.monitorGefMenus(parent)
        rcpsimulator.WidgetMonitor.widgetShown(self, parent, eventType)
    
    def monitorAllWidgets(self, parent, widgets):
        rcpsimulator.WidgetMonitor.monitorAllWidgets(self, parent, widgets)
        self.monitorGefWidgets()

    def monitorGefMenus(self, parent):
        self.uiMap.logger.debug("Showing FigureCanvas " + str(id(parent)) + ", monitoring GEF menus")
        for view in self.bot.views():
            for viewer in self.getViewers(view):
                menu = getGefViewer(viewer).getControl().getMenu()
                if menu is not None:
                    for item in self.getMenuItems(menu):
                        if item not in self.widgetsMonitored:
                            adapter = self.makeAdapter(item)
                            self.uiMap.monitorWidget(adapter)
                            self.widgetsMonitored.add(item)
        self.uiMap.logger.debug("Done Monitoring GEF menus for FigureCanvas " + str(id(parent)))
        
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

class ViewerEvent(storytext.guishared.GuiEvent):
    def __init__(self, *args, **kw):
        storytext.guishared.GuiEvent.__init__(self, *args, **kw)
        self.allDescriptions = {}
        self.allParts = {}

    def outputForScript(self, *args):
        return ' '.join([self.name, self.getStateDescription(*args) ])

    def getStateDescription(self, part, *args):
        if self.isMainEditPart(part):
            return self.storeObjectDescription(part)
        descs = [self.storeObjectDescription(editPart.part()) for editPart in self.widget.selectedEditParts()]
        return ','.join(descs)

    def addSuffix(self, desc):
        if desc.endswith(")"):
            startPos = desc.rfind("(") + 1
            intVal = desc[startPos:-1]
            if intVal.isdigit():
                val = int(intVal)
                return desc[:startPos] + str(val + 1) + ")"
        return desc + " (2)"

    def storeObjectDescription(self, part, checkParent=True):
        if part in self.allDescriptions:
            return self.allDescriptions.get(part)
        
        if checkParent:
            parent = part.getParent() 
            if parent and parent not in self.allDescriptions:
                self.storeObjectDescription(parent)
                for child in parent.getChildren():
                    self.storeObjectDescription(child, checkParent=False)
                return self.allDescriptions.get(part)
        desc = self.getObjectDescription(part)
        while desc and desc in self.allParts:
            if self.allParts[desc].isActive():
                desc = self.addSuffix(desc)
            else:
                break
        self.allDescriptions[part] = desc
        self.allParts[desc] = part
        return desc

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
        currDesc = self.storeObjectDescription(editPart.part(), checkParent=False)
        if currDesc == description:
            return editPart
        else:
            return self.findEditPartChildren(editPart, description)

    def findEditPartChildren(self, editPart, description):        
        for child in editPart.children():
            found = self.findEditPart(child, description) 
            if found:
                return found

    def shouldRecord(self, part, *args):
        return not swtsimulator.DisplayFilter.instance.hasEvents()

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
            def selectionChanged(lself, event): #@NoSelf
                storytext.guishared.catchAll(lself._selectionChanged, event)
                
            def _selectionChanged(lself, event): #@NoSelf
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
        else:
            raise UseCaseScriptError, "Could not find any objects in viewer matching description " + repr(description)

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Select"

    def shouldRecord(self, part, *args):
        return len(self.getStateDescription(*args)) > 0 and ViewerEvent.shouldRecord(self, part, *args)

    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput == stateChangeOutput or currOutput.startswith(stateChangeOutput + ",")
    
    def isStateChange(self, *args):
        return True
    
rcpsimulator.swtsimulator.eventTypes.append((gefbot.widgets.SWTBotGefViewer, [ ViewerSelectEvent ]))
