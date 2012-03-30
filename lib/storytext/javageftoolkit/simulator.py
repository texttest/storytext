

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

    def clickOnCenter(self, editPart, keyModifiers=0):
        bounds = self.getBoundsInternal(editPart)
        visibleBounds = self.getFigureCanvas().getIntersection(bounds)
        centreX = visibleBounds.x + visibleBounds.width / 2
        centreY = visibleBounds.y + visibleBounds.height / 2
        # x and y should be public fields, and are sometimes. In our tests, they are methods, for some unknown reason
        self.getFigureCanvas().mouseMoveLeftClick(centreX, centreY, keyModifiers)

    def getBoundsInternal(self, editPart):
        # getAbsoluteBounds method has private access modifier
        declaredMethod = self.getClass().getSuperclass().getDeclaredMethod("getAbsoluteBounds", [gefbot.widgets.SWTBotGefEditPart])
        declaredMethod.setAccessible(True)
        return declaredMethod.invoke(self, [editPart])

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

    # toX and toY should be in display coordinates
    def drag(self, editPart, toX, toY, keyModifiers=0):
        bounds = self.getBoundsInternal(editPart)
        # Hard coded offset found in swtbot.
        offset = 7/2 + 1
        self.getFigureCanvas().mouseDrag(getInt(bounds.x) + offset, getInt(bounds.y) + offset, toX, toY, keyModifiers)

class StoryTextSWTBotGefFigureCanvas(gefbot.widgets.SWTBotGefFigureCanvas):    
    def mouseDrag(self, fromX, fromY, toX, toY, keyModifiers=0):
        self._mouseDrag( fromX, fromY, toX, toY, keyModifiers)

    def _mouseDrag(self, fromX, fromY, toX, toY, keyModifiers=0):
        fromConverted = rcpsimulator.swtsimulator.runOnUIThread(self.toDisplayLocation, fromX, fromY)
        fromX = fromConverted.x
        fromY = fromConverted.y
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseMove, fromX, fromY)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.waitForCursor, fromX, fromY)
        
        
        counterX, counterY = self.getCounters(fromX, toX, fromY, toY)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.checkAndPostKeyPressed, keyModifiers)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.startDrag, fromX, toX, fromY, toY, counterX*10, counterY*10)
        self.moveDragged(fromX, toX, fromY, toY)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseUp)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.checkAndPostKeyReleased, keyModifiers)

    def startDrag(self, fromX, toX, fromY, toY, offsetX, offsetY):
        self.postMouseDown()
        self.postMouseMove( fromX + offsetX, fromY + offsetY)
       
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
            rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseMove, startX, fromY)
            rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.waitForCursor, startX, fromY)
        while startY != toY:
            startY += counterY
            rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseMove, startX, startY)
            rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.waitForCursor, startX, startY)

    def getIntersection(self, bounds):
        # SWT and draw2d have their own rectangle class, with the same methods, but they aren't the same...
        swtBounds = swt.graphics.Rectangle(getInt(bounds.x), getInt(bounds.y), getInt(bounds.width), getInt(bounds.height))
        canvasBounds = rcpsimulator.swtsimulator.runOnUIThread(self.widget.getBounds)
        return canvasBounds.intersection(swtBounds)

    def mouseMoveLeftClick(self, x, y, keyModifiers=0):
        displayLoc = rcpsimulator.swtsimulator.runOnUIThread(self.toDisplayLocation, x, y)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseMove, displayLoc.x, displayLoc.y)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.waitForCursor, displayLoc.x, displayLoc.y)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.checkAndPostKeyPressed, keyModifiers)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseDown)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.postMouseUp)
        rcpsimulator.swtsimulator.runOnUIThread(storytext.guishared.catchAll, self.checkAndPostKeyReleased, keyModifiers)
       
    def postMouseMove(self, x ,y):
        event = swt.widgets.Event()
        event.type = swt.SWT.MouseMove
        event.x = x
        event.y = y
        self.display.post(event)

    def postMouseDown(self, button=1):
        event = swt.widgets.Event()
        event.type = swt.SWT.MouseDown
        event.button = button
        self.display.post(event)

    def postMouseUp(self, button=1):
        event = swt.widgets.Event()
        event.type = swt.SWT.MouseUp
        event.button = button
        self.display.post(event)
        
    def checkAndPostKeyPressed(self, keyModifiers):
        if keyModifiers & swt.SWT.CTRL != 0:
            self.postKeyPressed(swt.SWT.CTRL, '\0')
            
    def checkAndPostKeyReleased(self, keyModifiers):
        if keyModifiers & swt.SWT.CTRL != 0:
            self.postKeyReleased(swt.SWT.CTRL, '\0')
            
    def postKeyPressed(self, code, character):
        event = swt.widgets.Event()
        event.type = swt.SWT.KeyDown
        event.keyCode = code
        event.character = character
        self.display.post(event)
        
    def postKeyReleased(self, code, character):
        event = swt.widgets.Event()
        event.type = swt.SWT.KeyUp
        event.keyCode = code
        event.character = character
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

    def monitorAllWidgets(self, parent, widgets):
        rcpsimulator.WidgetMonitor.monitorAllWidgets(self, parent, widgets)
        self.monitorGefWidgets()

    def monitorViewContentsMenus(self, botView):
        for viewer in self.getViewers(botView):
            menu = viewer.getViewer().getControl().getMenu()
            if menu:
                self.monitorMenu(menu)
    
    def monitorMenu(self, menu):
        if menu.getItemCount() == 0:
            # The menu is a Contribution defined in plugin.xml. We have to send an extra
            # SHOW event to instantiate it.
            menu.notifyListeners(swt.SWT.Show, swt.widgets.Event())
        menu.notifyListeners(swt.SWT.Show, swt.widgets.Event())
        for item in menu.getItems():
            submenu = item.getMenu()
            if submenu:
                self.monitorMenu(submenu)

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

    def shouldRecord(self, *args):
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

        if len(parts) > 0:
            self.widget.clickOnCenter(parts[0])
            for part in parts[1:]:
                self.widget.clickOnCenter(part, keyModifiers=swt.SWT.CTRL)
        else:
            raise UseCaseScriptError, "Could not find any objects in viewer matching description " + repr(description)

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Select"

    def shouldRecord(self, part, *args):
        if self.isMainEditPart(part):
            return ViewerEvent.shouldRecord(self, part, *args)
        else:
            hasMouseDown = DisplayFilter.instance.hasEventOfType(swt.SWT.MouseDown, self.getGefViewer().getControl())
            if len(self.widget.selectedEditParts()) == 1:
                return hasMouseDown 
            else:
                return len(self.getStateDescription(part, *args)) > 0 and (hasMouseDown or ViewerEvent.shouldRecord(self, part, *args))


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
        if len(self.widget.selectedEditParts()) > 0 and  self.shouldDrag(event):
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
        displayLocation = rcpsimulator.swtsimulator.runOnUIThread(self.widget.getFigureCanvas().toDisplayLocation, int(xDesc), int(yDesc))
        editPart = self.findEditPart(self.widget.rootEditPart(), sourceDesc)
        return editPart, displayLocation.x, displayLocation.y
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, ViewerSelectEvent)
    
    def shouldDrag(self, *args):
        return True

rcpsimulator.swtsimulator.eventTypes.append((StoryTextSWTBotGefViewer, [ ViewerSelectEvent, ViewerDragAndDropEvent ]))
