
from usecase.javaswttoolkit import describer as swtdescriber
from usecase import guishared, gridformatter
import org.eclipse.draw2d as draw2d
from org.eclipse import swt
import sys

class ColorNameFinder:
    abbrevations = [ ("dark", "+"), ("dull", "#"), ("very", "+"),
                     ("light", "-"), ("normal", ""), ("bright", "*") ]
    def __init__(self):
        self.names = {}
        self.addColors(draw2d.ColorConstants)
    
    def shortenColorName(self, name):
        ret = name.lower()
        for text, repl in self.abbrevations:
            ret = ret.replace(text, repl)
        return ret

    def addColors(self, cls):
        for name in sorted(cls.__dict__):
            if not name.startswith("__"):
                color = getattr(cls, name)
                if hasattr(color, "getRed"):
                    self.names[self.getRGB(color)] = self.shortenColorName(name)

    def getRGB(self, color):
        return color.getRed(), color.getGreen(), color.getBlue()

    def getName(self, color):
        return self.names.get(self.getRGB(color), "unknown")
        
colorNameFinder = ColorNameFinder()


class Describer(swtdescriber.Describer):
    def describeStructure(self, widget, indent=0, **kw):
        swtdescriber.Describer.describeStructure(self, widget, indent, **kw)
        if self.hasFigureCanvasAPI(widget):
            self.describeStructure(widget.getContents(), indent+1,
                                   visibleMethodNameOverride="isVisible", layoutMethodNameOverride="getLayoutManager")

    def hasFigureCanvasAPI(self, widget):
        # Could just check for FigureCanvas, but sometimes basic Canvases are used with the Figure mechanisms there also
        # (usually when scrolling not desired to disable mouse-wheel usage)
        return isinstance(widget, swt.widgets.Canvas) and hasattr(widget, "getContents")

    def getCanvasDescription(self, widget):
        if hasattr(widget, "getContents"): # FigureCanvas and others sharing its API
            return self.getAndStoreState(widget)
        else:
            return swtdescriber.Describer.getCanvasDescription(self, widget)

    def getCanvasState(self, widget):
        return FigureCanvasDescriber().getDescription(widget.getContents())
            
    def getUpdatePrefix(self, widget, *args):
        if self.hasFigureCanvasAPI(widget):
            return "\nUpdated Canvas :\n"
        else:
            return swtdescriber.Describer.getUpdatePrefix(self, widget, *args)

class AttrRecorder:
    def __init__(self, name, recorder):
        self.name = name
        self.recorder = recorder
        
    def __call__(self, *args):
        self.recorder.calls.setdefault(self.name, []).append(args)

        
class RecorderGraphics(draw2d.Graphics, object):
    def __init__(self, font, methodNames):
        self.calls = {}
        self.currFont = font
        self.methodNames = methodNames
        
    def __getattribute__(self, name):
        if name in object.__getattribute__(self, "methodNames"):
            return AttrRecorder(name, self)
        else:
            return object.__getattribute__(self, name)

    def drawRectangle(self, *args):
        pass # Overloaded, causes loop above. Don't want to draw this stuff anyway...

    def fillRectangle(self, *args):
        pass # Overloaded, causes loop above. Don't want to draw this stuff anyway...

    def setLineAttributes(self, *args):
        pass # throws NotImplemented by default

    def getFont(self):
        return self.currFont

    def setFont(self, font):
        self.currFont = font

class FigureCanvasDescriber(guishared.Describer):
    childrenMethodName = "getChildren"
    visibleMethodName = "isVisible"
    statelessWidgets = [ draw2d.RectangleFigure, draw2d.Label, draw2d.PolylineShape ]
    stateWidgets = []
    ignoreWidgets = [ draw2d.Figure ] # Not interested in anything except what we list
    ignoreChildren = ()
    defaultColor = "white"
    def getLabelDescription(self, figure):
        return figure.getText()
    
    def getRectangleFigureDescription(self, figure):
        graphics = RecorderGraphics(figure.getFont(), [ "drawString" ])
        figure.paintFigure(graphics)
        calls = graphics.calls.get("drawString", [])
        calls.sort(key=lambda (t, x, y): (y, x))
        colorText = colorNameFinder.getName(figure.getBackgroundColor())
        return self.formatFigure(figure, calls, colorText)

    def formatFigure(self, figure, calls, colorText):
        desc = self.arrangeText(calls)
        if colorText != self.defaultColor:
            desc += "(" + colorText + ")"
        return self.addBorder(figure, desc)

    def addBorder(self, figure, desc):
        if figure.getBorder():
            return "[ " + desc + " ]"
        else:
            return desc

    def arrangeText(self, calls):
        if len(calls) == 0:
            return ""
        elif len(calls) == 1:
            return calls[0][0]
        else:
            grid = self.makeTextGrid(calls)
            numColumns = max((len(r) for r in grid))
            formatter = gridformatter.GridFormatter(grid, numColumns)
            return str(formatter)

    def usesGrid(self, figure):
        return isinstance(figure, draw2d.RectangleFigure)

    def makeTextGrid(self, calls):
        grid = []
        prevX, prevLineX, prevY = None, None, None
        for text, x, y in calls:
            if y != prevY:
                prevLineX = prevX
                grid.append([])
            if x < prevLineX:
                grid[-2].insert(0, "")
            grid[-1].append(text)
            prevX = x
            prevY = y
        return grid

    def tryMakeGrid(self, figure, sortedChildren, childDescriptions):
        calls = [ (desc, child.getLocation().x, child.getLocation().y) for desc, child in zip(childDescriptions, sortedChildren) ]
        grid = self.makeTextGrid(calls)
        if len(grid) > 0:
            return grid, max((len(r) for r in grid))
        else:
            return None, 0
            
    def layoutSortsChildren(self, widget):
        return False
    
    def getVerticalDividePositions(self, visibleChildren):
        return []
