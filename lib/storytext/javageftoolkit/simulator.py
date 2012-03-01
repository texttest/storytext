

from storytext.javarcptoolkit import simulator as rcpsimulator
from storytext.javaswttoolkit import simulator as swtsimulator
from storytext.javaswttoolkit.util import getInt
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
import time

class StoryTextSWTBotGefViewer(gefbot.widgets.SWTBotGefViewer):
    def __init__(self, botOrGefViewer):
        gefViewer = self._getViewer(botOrGefViewer) if isinstance(botOrGefViewer, gefbot.widgets.SWTBotGefViewer) else botOrGefViewer
        gefbot.widgets.SWTBotGefViewer.__init__(self, gefViewer)

    def clickOnCenter(self, editPart):
        # getAbsoluteBounds method has private access modifier
        declaredMethod = self.getClass().getSuperclass().getDeclaredMethod("getAbsoluteBounds", [gefbot.widgets.SWTBotGefEditPart])
        declaredMethod.setAccessible(True)
        bounds = declaredMethod.invoke(self, [editPart])
        center = bounds.getCenter()
        # x and y should be public fields, and are sometimes. In our tests, they are methods, for some unknown reason
        self.click(getInt(center.x), getInt(center.y))
        
    def getViewer(self):
        return self._getViewer(self)
    
    @staticmethod
    def _getViewer(obj):
        viewerField = gefbot.widgets.SWTBotGefViewer.getDeclaredField("graphicalViewer")
        viewerField.setAccessible(True)
        return viewerField.get(obj)
    
    def getFigureCanvas(self):
        return self.getCanvas()
    
    def setFigureCanvas(self, figureCanvas):
        # canvas instance variable has protected access modifier. It is read only in Jython.
        viewerField = self.getClass().getSuperclass().getDeclaredField("canvas")
        viewerField.setAccessible(True)
        viewerField.set(self, figureCanvas)

class StoryTextSWTBotGefFigureCanvas(gefbot.widgets.SWTBotGefFigureCanvas):    
    def mouseDrag(self, fromX, fromY, toX, toY):
        # Hard coded offset found in swtbot. It's wrongly added to destination location, so we have to remove it
        offset = 7/2 + 1
        self._mouseDrag( fromX, fromY, toX - offset, toY - offset)

    def _mouseDrag(self, fromX, fromY, toX, toY):
        fromConverted = rcpsimulator.swtsimulator.runOnUIThread(self.toDisplayLocation, fromX, fromY)
        toConverted = rcpsimulator.swtsimulator.runOnUIThread(self.toDisplayLocation, toX, toY)
        fromX = fromConverted.x
        fromY = fromConverted.y
        toX = toConverted.x
        toY = toConverted.y
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseMove, fromX, fromY, 0)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.waitForCursor, fromX, fromY)
        
        
        counterX, counterY = self.getCounters(fromX, toX, fromY, toY)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.startDrag, fromX, toX, fromY, toY, counterX*10, counterY*10)
        self.moveDragged(fromX, toX, fromY, toY)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseUp)

    def startDrag(self, fromX, toX, fromY, toY, offsetX, offsetY):
        self.postMouseDown()
        self.postMouseMove( fromX + offsetX, fromY + offsetY, 0)
       
    def getCounters(self, x1, x2, y1, y2):
        counterX = 1 if x1 < x2 else -1
        counterY = 1 if y1 < y2 else -1
        return counterX, counterY
    
    def moveDragged(self, fromX, toX, fromY, toY):
        counterX, counterY = self.getCounters(fromX, toX, fromY, toY)
        startX = fromX
        startY = fromY
        while startX != toX:
            startX += counterX
            rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseMove, startX, fromY, 0)
            rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.waitForCursor, startX, fromY)
        while startY != toY:
            startY += counterY
            rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseMove, startX, startY, 0)
            rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.waitForCursor, startX, startY)

    def mouseMoveLeftClick(self, x, y):
        displayLoc = rcpsimulator.swtsimulator.runOnUIThread(self.toDisplayLocation, x, y)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseMove, displayLoc.x, displayLoc.y, 0)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.waitForCursor, displayLoc.x, displayLoc.y)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseDown)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseUp)
       
    def postMouseMove(self, x ,y, button):
        event = swt.widgets.Event()
        event.type = swt.SWT.MouseMove
        event.x = x
        event.y = y
        self.display.post(event)

    def postMouseDown(self):
        event = swt.widgets.Event()
        event.type = swt.SWT.MouseDown
        event.button = 1
        self.display.post(event)

    def postMouseUp(self):
        event = swt.widgets.Event()
        event.type = swt.SWT.MouseUp
        event.button = 1
        self.display.post(event)

    def toDisplayLocation(self, x, y):
        return self.widget.getDisplay().map(self.widget, None, x, y)

    def waitForCursor(self, x, y):
        while self.widget.getDisplay().getCursorLocation().x != x and self.widget.getDisplay().getCursorLocation().y != y:
            time.sleep(0.1)

class DisplayFilter(rcpsimulator.DisplayFilter):
    def shouldCheckWidget(self, widget, eventType):
        if isinstance(widget, FigureCanvas):
            return True
        else:
            return rcpsimulator.DisplayFilter.shouldCheckWidget(self, widget, eventType)


class WidgetMonitor(rcpsimulator.WidgetMonitor):
    def __init__(self, *args, **kw):
        self.allPartRefs = set()
        self.swtbotMap[GraphicalViewer] = (StoryTextSWTBotGefViewer, [])
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
                menu = viewer.getViewer().getControl().getMenu()
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
        viewer = self.getViewer(part.getTitle())
        return [ viewer ] if viewer else []
                
    def getViewer(self, name):
        viewer = None
        try:
            botViewer = self.bot.gefViewer(name)
            viewer = StoryTextSWTBotGefViewer(botViewer)
            self.setFigureCanvas(viewer)
        except WidgetNotFoundException:
            pass
        return viewer
        
    def setFigureCanvas(self, viewer):
        gefControl = viewer.getViewer().getControl()
        viewer.setFigureCanvas(StoryTextSWTBotGefFigureCanvas(gefControl))

    def getDisplayFilterClass(self):
        return DisplayFilter

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
    
    def getPartName(self):
        return self.partReference.getPartName()

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
        return not DisplayFilter.instance.hasEvents()

    @classmethod
    def getSignalsToFilter(cls):
        return []
    
    def getGefViewer(self):
        return self.widget.getViewer()

class ViewerSelectEvent(ViewerEvent):
    def connectRecord(self, method):
        class SelectionListener(ISelectionChangedListener):
            def selectionChanged(lself, event): #@NoSelf
                storytext.guishared.catchAll(self.applyToSelected, event, method)
                
        rcpsimulator.swtsimulator.runOnUIThread(self.getGefViewer().addSelectionChangedListener, SelectionListener())

    def applyToSelected(self, event, method):
        selection = event.getSelection()
        for editPart in selection.toList():
            method(editPart, self)

    def generate(self, description, *args):
        parts = []
        for part in description.split(","):
            editPart = self.findEditPart(self.widget.rootEditPart(), part)
            if editPart == self.widget.mainEditPart():
                return self.widget.click(editPart)
            if editPart:
                parts.append(editPart)

        if len(parts) == 1:
            self.widget.clickOnCenter(parts[0])
        elif len(parts) > 1:
            self.widget.select(parts)
        else:
            raise UseCaseScriptError, "Could not find any objects in viewer matching description " + repr(description)

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Select"

    def shouldRecord(self, part, *args):
        if self.isMainEditPart(part):
            return ViewerEvent.shouldRecord(self, part, *args)
        elif len(self.widget.selectedEditParts()) == 1:
            return DisplayFilter.instance.hasEventOfType(swt.SWT.MouseDown, self.getGefViewer().getControl())
        else:
            return len(self.getStateDescription(part, *args)) > 0 and ViewerEvent.shouldRecord(self, part, *args)

    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput == stateChangeOutput or currOutput.startswith(stateChangeOutput + ",")
    
    def isStateChange(self, *args):
        return True

class DragHolder():
    draggedPart = None
    sourceEvent = None
    @classmethod
    def reset(self):
        self.draggedPart = None
        self.sourceEvent = None
    
class ViewerDragAndDropEvent(ViewerEvent):
    def connectRecord(self, method):
        class DDListener(swt.events.DragDetectListener):
            def dragDetected(lself, event):#@NoSelf
                storytext.guishared.catchAll(self.applyToDragged, event, method)

        rcpsimulator.swtsimulator.runOnUIThread(self.getGefViewer().getControl().addDragDetectListener, DDListener())
        self.addDropListener(method)

    def applyToDragged(self, event, method):
        if len(self.widget.selectedEditParts()) > 0:
            DragHolder.draggedPart = self.widget.selectedEditParts()[0].part()#self.getGefViewer().findObjectAt(p)
            DragHolder.sourceEvent = self

    def addDropListener(self, method):
        class MListener(swt.events.MouseAdapter):
            def mouseUp(lself, event):#@NoSelf
                if DragHolder.sourceEvent is not None:
                    storytext.guishared.catchAll(method, DragHolder.draggedPart, event.x, event.y, DragHolder.sourceEvent)
                    DragHolder.reset()

        rcpsimulator.swtsimulator.runOnUIThread(self.getGefViewer().getControl().addMouseListener, MListener())

    def getStateDescription(self, part, *args):
        partDesc = self.storeObjectDescription(part)
        targetDesc = self.getTargetDescription(part, *args)
        return partDesc + " to " + targetDesc

    def getTargetDescription(self, part, x, y, *args):
        return str(x) + ":" + str(y)

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "DragAndDrop"

    def generate(self, description, *args):
        editPart, xPos, yPos = self.parseDescription(description)
        if editPart:
            self.widget.drag(editPart, xPos, yPos)
        else:
            raise UseCaseScriptError, "Could not find any edit part in viewer matching description " + repr(description)
        
    def parseDescription(self, description):
        sourceDesc, dest = description.split(" to ", 1)
        xDesc, yDesc = dest.split(":", 1)
        editPart = self.findEditPart(self.widget.rootEditPart(), sourceDesc)
        return editPart, int(xDesc), int(yDesc)
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, ViewerSelectEvent)

rcpsimulator.swtsimulator.eventTypes.append((StoryTextSWTBotGefViewer, [ ViewerSelectEvent, ViewerDragAndDropEvent ]))
