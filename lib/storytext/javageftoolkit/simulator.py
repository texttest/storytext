import time, logging
import storytext.guishared

from storytext.javarcptoolkit import simulator as rcpsimulator
from storytext.javaswttoolkit import simulator as swtsimulator
from storytext.javaswttoolkit.util import getInt
from storytext.definitions import UseCaseScriptError

from org.eclipse.draw2d import FigureCanvas
from org.eclipse.draw2d.geometry import Insets
from org.eclipse.gef import GraphicalViewer
from org.eclipse.jface.viewers import ISelectionChangedListener
from org.eclipse.swt import SWT
from org.eclipse.swt.events import DragDetectListener, MouseAdapter
from org.eclipse.ui.internal import EditorReference

from org.eclipse.swtbot.eclipse.gef.finder import SWTGefBot
from org.eclipse.swtbot.eclipse.gef.finder.widgets import SWTBotGefFigureCanvas, SWTBotGefEditPart, SWTBotGefViewer
from org.eclipse.swtbot.swt.finder.exceptions import WidgetNotFoundException

class StoryTextSWTBotGefViewer(SWTBotGefViewer):
    widgetMonitor = None
    def __init__(self, botOrGefViewer):
        gefViewer = self._getViewer(botOrGefViewer) if isinstance(botOrGefViewer, SWTBotGefViewer) else botOrGefViewer
        SWTBotGefViewer.__init__(self, gefViewer)
        self.logger = logging.getLogger("Centre finding")

    def findOverlap(self, overlaps, centre):
        for overlap in overlaps:
            if overlap.contains(centre):
                return overlap

    def getCenter(self, editPart):
        bounds = self.getBoundsInternal(editPart)
        self.logger.debug("Object bounds at " + repr(bounds))
        viewportBounds = self.getFigureCanvas().getViewportBounds()
        self.logger.debug("Canvas viewport bounds at " + repr(viewportBounds))
        visibleBounds = viewportBounds.getIntersection(bounds)
        if getInt(visibleBounds.height) == 0 or getInt(visibleBounds.width) == 0:
            self.logger.debug("No intersection with viewport, scrolling until there is")
            self.ensureInViewport(bounds, viewportBounds)
            visibleBounds = self.getBoundsInternal(editPart)

        self.logger.debug("Found bounds at " + repr(visibleBounds))
        overlaps = self.findOverlapRegions(editPart, visibleBounds)
        return self.findNonOverlappingCentre(visibleBounds, overlaps)

    def getEdges(self, bounds):
        topEdge = getInt(bounds.y)
        bottomEdge = topEdge + getInt(bounds.height)
        leftEdge = getInt(bounds.x)
        rightEdge = leftEdge + getInt(bounds.width)
        return topEdge, leftEdge, bottomEdge, rightEdge

    def ensureInViewport(self, bounds, viewportBounds):
        viewTop, viewLeft, viewBottom, viewRight = self.getEdges(viewportBounds)
        top, left, bottom, right = self.getEdges(bounds)
        canvas = self.getFigureCanvas()
        if bottom <= viewTop:
            canvas.scrollYOffset(top - viewTop)
        elif top >= viewBottom:
            canvas.scrollYOffset(bottom - viewBottom)
        if right <= viewLeft:
            canvas.scrollXOffset(left - viewLeft)
        elif left >= viewRight:
            canvas.scrollXOffset(right - viewRight)
            
    def findNonOverlappingCentre(self, bounds, overlaps):
        centre = bounds.getCenter()
        self.logger.debug("Found centre at " + repr(centre))
        overlap = self.findOverlap(overlaps, centre)
        if overlap:
            self.logger.debug("Centre overlaps rectangle at " + repr(overlap))
            for rect in self.findOutsideRectangles(bounds, overlap):
                self.logger.debug("Trying outside rectangle " + repr(rect))
                newOverlaps = []
                for otherOverlap in overlaps:
                    if otherOverlap is not overlap:
                        intersection = rect.getIntersection(otherOverlap)
                        if getInt(intersection.height) and getInt(intersection.width) and intersection not in newOverlaps:    
                            self.logger.debug("Found new overlap " + repr(intersection))
                            newOverlaps.append(intersection)
                if rect not in newOverlaps:
                    centre = self.findNonOverlappingCentre(rect, newOverlaps)
                    if centre:
                        return centre
        return getInt(centre.x), getInt(centre.y)
    
    def findOutsideRectangles(self, rect, innerRect):
        top, left, bottom, right = self.getEdges(rect)
        innertop, innerleft, innerbottom, innerright = self.getEdges(innerRect)
        insets = [ Insets(innerbottom - top, 0, 0, 0), 
                   Insets(0, innerright - left, 0, 0),
                   Insets(0, 0, bottom - innertop, 0),
                   Insets(0, 0, 0, right - innerleft) ]
        rects = [ rect.getCropped(i) for i in insets ]
        rects = filter(lambda r: getInt(r.height) and getInt(r.width), rects)
        return sorted(rects, key=lambda r: -getInt(r.height) * getInt(r.width))
            
    def findRoot(self, editPart):
        parent = editPart.parent()
        if parent.part() is None:
            return editPart
        else:
            return self.findRoot(parent)

    def findOverlapRegions(self, editPart, bounds):
        rootEditPart = self.findRoot(editPart)
        return self.findOverlapRegionsUnder(rootEditPart, editPart, bounds)
    
    def findOverlapRegionsUnder(self, editPart, ignoreEditPart, bounds):
        return self.findOverlapRegionsFor(editPart.children(), ignoreEditPart, bounds) + \
            self.findOverlapRegionsFor(editPart.sourceConnections(), ignoreEditPart, bounds)
    
    def findOverlapRegionsFor(self, editParts, ignoreEditPart, bounds):
        overlaps = []
        for otherPart in editParts:
            if otherPart is not ignoreEditPart and otherPart.part().isSelectable():
                otherBounds = self.getBoundsInternal(otherPart)
                intersection = bounds.getIntersection(otherBounds)
                if getInt(intersection.height) and getInt(intersection.width) and intersection != bounds and intersection not in overlaps:
                    overlaps.append(intersection)
                    self.logger.debug("Overlap found at " + repr(intersection))
            overlaps += self.findOverlapRegionsUnder(otherPart, ignoreEditPart, bounds)
        # Handle the largest overlaps first, likely to give the best effect. Need to sort somehow to prevent indeterminism
        overlaps.sort(key=self.getArea, reverse=True)
        return overlaps

    def getArea(self, rect):
        return getInt(rect.height) * getInt(rect.width)

    def clickOnCenter(self, editPart, keyModifiers=0):
        if self.widgetMonitor:
            # To do actual clicking, must make sure the shell is active... doesn't happen automatically in Xvfb
            self.widgetMonitor.forceShellActive()
        centreX, centreY = self.getCenter(editPart)
        # x and y should be public fields, and are sometimes. In our tests, they are methods, for some unknown reason
        self.getFigureCanvas().mouseMoveLeftClick(centreX, centreY, keyModifiers)

    def getBoundsInternal(self, editPart):
        # getAbsoluteBounds method has private access modifier
        declaredMethod = self.getClass().getSuperclass().getDeclaredMethod("getAbsoluteBounds", [SWTBotGefEditPart])
        declaredMethod.setAccessible(True)
        return declaredMethod.invoke(self, [editPart])
        
    def getViewer(self):
        return self._getViewer(self)
    
    @staticmethod
    def _getViewer(obj):
        viewerField = SWTBotGefViewer.getDeclaredField("graphicalViewer")
        viewerField.setAccessible(True)
        return viewerField.get(obj)
    
    def getFigureCanvas(self):
        return self.getCanvas()
    
    def setFigureCanvas(self, figureCanvas):
        # canvas instance variable has protected access modifier. It is read only in Jython.
        viewerField = self.getClass().getSuperclass().getDeclaredField("canvas")
        viewerField.setAccessible(True)
        viewerField.set(self, figureCanvas)

    # toX and toY should be in display coordinates. Widget coordinates don't work as we may be dragging from one widget to another
    def drag(self, editPart, toX, toY, keyModifiers=0):
        widgetCentreX, widgetCentreY = self.getCenter(editPart)
        displayCentre = swtsimulator.runOnUIThread(self.getFigureCanvas().toDisplayLocation, widgetCentreX, widgetCentreY)
        centreX = displayCentre.x
        centreY = displayCentre.y
        self.logger.debug("Dragging " + repr((centreX, centreY)) + " to " + repr((toX, toY)))
        self.getFigureCanvas().mouseDrag(centreX, centreY, toX, toY, keyModifiers)
 

class StoryTextSWTBotGefFigureCanvas(SWTBotGefFigureCanvas):
    def __init__(self, *args, **kw):
        SWTBotGefFigureCanvas.__init__(self, *args, **kw)
        self.eventPoster = swtsimulator.EventPoster(self.display)
        
    def mouseDrag(self, *args):
        self.eventPoster.mouseDrag(*args)
            
    def getViewportBounds(self):
        return rcpsimulator.swtsimulator.runOnUIThread(self.widget.getViewport().getBounds)
    
    def scrollXOffset(self, offset):
        def doScroll():
            currPos = getInt(self.widget.getViewport().getViewLocation().x)
            self.widget.scrollToX(currPos + offset)
        rcpsimulator.swtsimulator.runOnUIThread(doScroll)
        
    def scrollYOffset(self, offset):
        def doScroll():
            currPos = getInt(self.widget.getViewport().getViewLocation().y)
            self.widget.scrollToY(currPos + offset)
        rcpsimulator.swtsimulator.runOnUIThread(doScroll)
        
    def mouseMoveLeftClick(self, x, y, keyModifiers=0):
        displayLoc = swtsimulator.runOnUIThread(self.toDisplayLocation, x, y)
        self.eventPoster.moveClickAndReturn(displayLoc.x, displayLoc.y, keyModifiers)
                
    def toDisplayLocation(self, x, y):
        return self.widget.getDisplay().map(self.widget, None, x, y)

    def isDisposed(self):
        return self.widget.isDisposed()

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
        self.logger = logging.getLogger("storytext record")
        rcpsimulator.WidgetMonitor.__init__(self, *args, **kw)
        StoryTextSWTBotGefViewer.widgetMonitor = self

    def createSwtBot(self):
        return SWTGefBot()

    def monitorAllWidgets(self, widgets):
        rcpsimulator.WidgetMonitor.monitorAllWidgets(self, widgets)
        self.monitorGefWidgets()

    def monitorViewContentsMenus(self, botView):
        for viewer in self.getViewers(botView):
            menu = viewer.getViewer().getControl().getMenu()
            if menu:
                rcpsimulator.WidgetAdapter.storeId(menu, botView.getViewReference().getId())
                self.monitorMenu(menu)
                    
    def monitorMenu(self, menu):
        if menu.getItemCount() == 0:
            # The menu is a Contribution defined in plugin.xml. We have to send an extra
            # SHOW event to instantiate it.
            self.sendShowEvent(menu)

        self.sendShowEvent(menu)
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

    def findPossibleUIMapIdentifiers(self):
        partId = self.partReference.getId()
        return [ "Type=" + self.getType(), "View=" + partId ]
    
    def getType(self):
        return "Viewer"
    
    def getPartName(self):
        return self.partReference.getPartName()
    
    def isPreferred(self):
        # Ensure we replay for the one in the active view, if this is possible
        # Same object (identifier) may exist in several views
        page = self.partReference.getPage()
        return page.getActivePart() == self.partReference.getPart(False)

class ViewerEvent(storytext.guishared.GuiEvent):
    def __init__(self, *args, **kw):
        storytext.guishared.GuiEvent.__init__(self, *args, **kw)
        self.allDescriptions = {}
        self.allParts = {}

    def outputForScript(self, *args):
        return ' '.join([self.name, self.getStateDescription(*args) ])

    def getStateDescription(self, parts, *args):
        descs = map(self.storeObjectDescription, parts)
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
            oldDesc = self.allDescriptions.get(part)
            newDesc = self.getObjectDescription(part)
            if oldDesc == newDesc:
                return self.allDescriptions.get(part)
            elif oldDesc.startswith(newDesc) and oldDesc.endswith(")"):
                startPos = oldDesc.rfind("(") - 1
                self.allDescriptions[part] = newDesc + oldDesc[startPos:]
            else:
                self.allDescriptions[part] = newDesc
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
        for child in sorted(editPart.children(), cmp=self.getEditPartComparator()):
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
    
    def getEditPartComparator(self):
        return None

    def getControl(self):
        return self.getGefViewer().getControl()

    def widgetDisposed(self):
        return self.widget.getFigureCanvas().isDisposed()
    
    def describeWidget(self):
        return "of type " + self.widget.getType()

class ViewerSelectEvent(ViewerEvent):
    # Allow customwidgetsevents to set this
    pauseBetweenSelections = 0
    def connectRecord(self, method):
        class SelectionListener(ISelectionChangedListener):
            def selectionChanged(lself, event): #@NoSelf
                storytext.guishared.catchAll(self.applyToSelected, event, method)
                
        rcpsimulator.swtsimulator.runOnUIThread(self.getGefViewer().addSelectionChangedListener, SelectionListener())

    def applyToSelected(self, event, method):
        method(event.getSelection().toList(), self)

    def parseArguments(self, description):
        parts = []
        notfound = []
        allParts = description.split(",")
        for part in allParts:
            editPart = self.findEditPart(self.widget.rootEditPart(), part)
            if editPart:
                parts.append(editPart)
            else:
                notfound.append(part)
        if len(parts) > 0:
            if len(notfound) > 0:
                return self.makePartialParseFailure(parts, ",".join(notfound), allParts[0] not in notfound)
            else:
                return parts
        elif len(allParts) > 1 and len(notfound) > 0:
            editPart = self.findEditPart(self.widget.rootEditPart(), description)
            if editPart:
                return [ editPart ]
        raise UseCaseScriptError, "could not find any objects in viewer matching description '"  + description + "'"
        
    def generate(self, parts, partial=False):
        if not partial:
            rcpsimulator.swtsimulator.runOnUIThread(self.getGefViewer().deselectAll)
        if len(parts) == 1 and not partial:
            self.widget.clickOnCenter(parts[0])
        else:
            for i, part in enumerate(parts):
                if i > 0 and self.pauseBetweenSelections:
                    time.sleep(self.pauseBetweenSelections)
                self.widget.clickOnCenter(part, SWT.CTRL)
                
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Select"
    
    @classmethod
    def getSignalsToFilter(cls):
        return [ SWT.MouseDown, SWT.MouseUp ]

    def shouldRecord(self, parts, *args):
        types = self.getSignalsToFilter()
        hasMouseEvent = DisplayFilter.instance.hasEventOfType(types, self.getControl())
        return hasMouseEvent and len(parts) > 0

    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput == stateChangeOutput or currOutput.startswith(stateChangeOutput + ",")
    
    def isStateChange(self, *args):
        return True

class DragHolder():
    draggedParts = []
    sourceEvent = None
    sourceSwtEvent = None
    @classmethod
    def reset(cls):
        cls.draggedParts = []
        cls.sourceEvent = None
        cls.sourceSwtEvent = None
    
class ViewerDragAndDropEvent(ViewerEvent):
    allInstances = {}
    def connectRecord(self, method):
        class DDListener(DragDetectListener):
            def dragDetected(lself, event):#@NoSelf
                storytext.guishared.catchAll(self.applyToDragged, event, method)

        rcpsimulator.swtsimulator.runOnUIThread(self.getControl().addDragDetectListener, DDListener())
        self.addDropListener(method)

    def applyToDragged(self, event, method):
        if len(self.widget.selectedEditParts()) > 0 and self.shouldDrag(event):
            DragHolder.draggedParts = [ e.part() for e in self.widget.selectedEditParts() ]#self.getGefViewer().findObjectAt(p)
            DragHolder.sourceEvent = self
            DragHolder.sourceSwtEvent = event

    def addDropListener(self, method):
        class MListener(MouseAdapter):
            def mouseUp(lself, event):#@NoSelf
                storytext.guishared.catchAll(self.handleDrop, event, method)

        self.allInstances.setdefault(self.__class__, []).append(self)
        rcpsimulator.swtsimulator.runOnUIThread(self.getControl().addMouseListener, MListener())

    def handleDrop(self, event, method):
        if DragHolder.sourceEvent is not None and self.__class__ is DragHolder.sourceEvent.__class__:
            try:
                for instance in self.allInstances.get(self.__class__, []):
                    # No guarantee MouseUp appers on same widget
                    dropX, dropY = instance.getDropPosition(event)
                    if instance.isValidDragAndDrop(instance.getControl(), dropX, dropY):
                        method(DragHolder.draggedParts, dropX, dropY, instance, DragHolder.sourceEvent)
                        break
            finally:
                DragHolder.reset()

    def isValidDragAndDrop(self, dropWidget, dropX, dropY):
        if dropX is None or not dropWidget.isVisible():
            return False
        
        dragEvent = DragHolder.sourceSwtEvent
        return dragEvent.widget is not dropWidget or dragEvent.x != dropX or dragEvent.y != dropY

    def getDropPosition(self, event):
        return event.x, event.y

    def getStateDescription(self, parts, *args):
        partDesc = ",".join(map(self.storeObjectDescription, parts))
        targetDesc = self.getTargetDescription(parts, *args)
        return partDesc + " to " + targetDesc

    def getTargetDescription(self, parts, x, y, *args):
        return str(x) + ":" + str(y)

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "DragAndDrop"
    
    @classmethod
    def getSignalsToFilter(cls):
        return [ SWT.MouseUp ]
    
    def shouldRecord(self, parts, x, y, *events):
        controls = []
        for event in events:
            if hasattr(event, "getControl"):
                controls.append(event.getControl())
        types = self.getSignalsToFilter()
        return any((DisplayFilter.instance.hasEventOfType(types, ctrl) for ctrl in controls))

    def generate(self, args, **kw):
        parts, x, y = args
        if len(parts) > 1:
            for part in parts[:-1]:
                self.widget.clickOnCenter(part, SWT.CTRL)
                if ViewerSelectEvent.pauseBetweenSelections:
                    time.sleep(ViewerSelectEvent.pauseBetweenSelections)
        self.widget.drag(parts[-1], x, y, **kw)
        
    def parseArguments(self, description):
        sourceDesc, dest = description.split(" to ", 1)
        allParts = sourceDesc.split(",")
        editParts = []
        for partDesc in allParts:
            editPart = self.findEditPart(self.widget.rootEditPart(), partDesc)
            if not editPart:
                raise UseCaseScriptError, "could not find any objects in viewer matching description '" + sourceDesc + "'"
            editParts.append(editPart)
        displayLocation = self.parseDestination(dest)
        return editParts, displayLocation.x, displayLocation.y
    
    def parseDestination(self, dest):
        if ":" not in dest:
            raise UseCaseScriptError, "drag destination must be in the form <xpos>:<ypos>"
        xDesc, yDesc = dest.split(":", 1)
        if not xDesc.isdigit() or not yDesc.isdigit():
            raise UseCaseScriptError, "drag destination must have numeric values"
        return rcpsimulator.swtsimulator.runOnUIThread(self.widget.getFigureCanvas().toDisplayLocation, int(xDesc), int(yDesc))
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, ViewerSelectEvent)
    
    def shouldDrag(self, *args):
        return True

rcpsimulator.swtsimulator.eventTypes.append((StoryTextSWTBotGefViewer, [ ViewerSelectEvent, ViewerDragAndDropEvent ]))
