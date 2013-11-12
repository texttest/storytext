
from storytext.javaswttoolkit import describer as swtdescriber
from storytext import guishared, gridformatter
from util import getInt
import org.eclipse.draw2d as draw2d
from org.eclipse import swt

def addColors(cls):
    swtdescriber.colorNameFinder.addColors(cls, 
                                           modifiers=[ (draw2d.FigureUtilities.darker, "D"), (draw2d.FigureUtilities.lighter, "L")],
                                           abbreviations=[ ("dark", "+"), ("dull", "#"), ("very", "+"), 
                                                           ("light", "-"), ("normal", ""), ("bright", "*") ])

# Add swt colors
addColors(draw2d.ColorConstants)
            

class AttrRecorder:
    def __init__(self, name, recorder):
        self.name = name
        self.recorder = recorder
        
    def __call__(self, *args):
        self.recorder.registerCall(self.name, args)

        
class RecorderGraphics(draw2d.Graphics, object):
    def __init__(self, canvas, font, methodNames):
        self.calls = []
        self.currFont = font
        self.parentCanvas = canvas
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

    def fillPolygon(self, *args):
        pass # Overloaded, causes loop above. Don't want to draw this stuff anyway...

    def setLineAttributes(self, *args):
        pass # throws NotImplemented by default
    
    def setAlpha(self, *args):
        pass # throws NotImplemented by default

    def getAlpha(self, *args):
        return 0 # throws NotImplemented by default
    
    def getAntialias(self, *args):
        return swt.SWT.DEFAULT # throws NotImplemented by default
    
    def setAntialias(self, *args):
        pass # throws NotImplemented by default

    def getFont(self):
        return self.currFont
    
    def getFontMetrics(self):
        gc = swt.graphics.GC(self.parentCanvas)
        metrics = gc.getFontMetrics()
        gc.dispose()
        return metrics

    def setFont(self, font):
        self.currFont = font

    def registerCall(self, methodName, args):
        self.calls.append((methodName, args))

    def getCallArgs(self, methodName):
        return [ c[1] for c in self.calls if c[0] == methodName ]

    def getCallGroups(self, methodNames):
        result = []
        prevIx = len(methodNames)
        for methodName, args in self.calls:
            if methodName in methodNames:
                ix = methodNames.index(methodName)
                if ix <= prevIx:
                    result.append([ None ] * len(methodNames))
                result[-1][ix] = args
                prevIx = ix
        return result


class CanvasDescriber(guishared.Describer):
    childrenMethodName = "getChildren"
    visibleMethodName = "isVisible"
    statelessWidgets = [ draw2d.RectangleFigure, draw2d.Label, draw2d.PolylineShape ]
    stateWidgets = []
    ignoreWidgets = [ draw2d.Figure ] # Not interested in anything except what we list
    ignoreChildren = ()
    pixelTolerance = 2
    @classmethod
    def canDescribe(cls, widget):
        # Could just check for FigureCanvas, but sometimes basic Canvases are used with the Figure mechanisms there also
        # (usually when scrolling not desired to disable mouse-wheel usage)
        return hasattr(widget, "getContents")
    
    def __init__(self, canvas, *args, **kw):
        guishared.Describer.__init__(self, *args, **kw)
        self.canvas = canvas
        
    def getCanvasDescription(self, *args):
        return self.getDescription(self.canvas.getContents())
        
    def getLabelDescription(self, figure):
        return figure.getText()

    def getBackgroundColor(self, figure, *args):
        # So derived classes can reinterpret this if needed, e.g. if the whole area is covered by some other colour
        return figure.getBackgroundColor()

    def paintFigure(self, figure, graphics):
        # So derived classes can reinterpret this if needed, e.g. adding customization to how this is called
        return figure.paintFigure(graphics)
    
    def describeCanvasStructure(self, indent):
        self.describeStructure(self.canvas.getContents(), indent,
                               visibleMethodNameOverride="isVisible", layoutMethodNameOverride="getLayoutManager")

    def getRectangleFigureDescription(self, figure):
        font = figure.getFont()
        graphics = RecorderGraphics(self.canvas, font, [ "drawString", "setBackgroundColor", "fillRectangle", "setAlpha" ])
        self.paintFigure(figure, graphics)
        calls = graphics.getCallArgs("drawString")
        callGroups = graphics.getCallGroups([ "setBackgroundColor", "fillRectangle" ])
        color = self.getBackgroundColor(figure, callGroups)
        filledRectangles = []
        bounds = figure.getBounds()
        fontSize = font.getFontData()[0].getHeight()
        for colorArgs, rectArgs in callGroups:
            if rectArgs is None: # Colour was set, but no rectangles were made...
                continue
            
            rect = draw2d.geometry.Rectangle(*rectArgs)
            filledRectangles.append(rect)
            colorText = ""
            if colorArgs is not None:
                rectColor = colorArgs[0]
                if rectColor != color:
                    colorText = "(" + swtdescriber.colorNameFinder.getName(rectColor) + ")"
                if rect != bounds and colorText:
                    self.addColouredRectangle(calls, colorText, rect, fontSize)
        calls.sort(cmp=self.compareCalls)
        colorText = swtdescriber.colorNameFinder.getName(color) if self.changedColor(color, figure) else ""
        if len(graphics.getCallArgs("setAlpha")) > 0:
            colorText = "~" + colorText + "~"
        return self.formatFigure(figure, calls, colorText, filledRectangles)

    def compareCalls(self, call1, call2):
        _, x1, y1 = call1
        _, x2, y2 = call2
        if abs(y1 - y2) > self.pixelTolerance:
            return cmp(y1, y2)
        elif abs(x1 - x2) > self.pixelTolerance:
            return cmp(x1, x2)
        else:
            return 0

    def addColouredRectangle(self, calls, colorText, rect, fontSize):
        # Find some text to apply it to, if we can
        for i, (text, x, y) in enumerate(calls):
            # Adding pixels to "user space units". Is this always allowed?
            if rect.contains(x, y) or rect.contains(x, y + fontSize):
                calls[i] = text + colorText, x, y
                return
        calls.append((colorText, getInt(rect.x), getInt(rect.y)))

    def changedColor(self, color, figure):
        return color != figure.getParent().getBackgroundColor()

    def formatFigure(self, figure, calls, colorText, filledRectangles):
        desc = self.arrangeText(calls)
        if colorText and not isinstance(desc, gridformatter.GridFormatter):
            desc += "(" + colorText + ")"
        return self.addBorder(figure, desc)

    def addBorder(self, figure, desc):
        # don't describe transparent borders!
        if figure.getBorder() and figure.getBorder().isOpaque():
            if isinstance(desc, gridformatter.GridFormatter):
                self.addBorderToGrid(desc)
                return desc
            else:   
                return "[ " + desc + " ]"
        else:
            return desc
        
    def addBorderToGrid(self, formatter):
        colWidths = formatter.findColumnWidths()
        for row in formatter.grid:
            row[0] = "[ " + row[0]
            while len(row) < formatter.numColumns:
                row.append("")
            row[-1] = row[-1].ljust(colWidths[-1]) + " ]"

    def arrangeText(self, calls):
        if len(calls) == 0:
            return ""
        elif len(calls) == 1:
            return calls[0][0]
        else:
            grid, numColumns = self.makeTextGrid(calls)
            return self.formatGrid(grid, numColumns)

    def formatGrid(self, grid, numColumns):
        return gridformatter.GridFormatter(grid, numColumns)

    def usesGrid(self, figure):
        return isinstance(figure, draw2d.RectangleFigure)

    def makeTextGrid(self, calls):
        grid = []
        prevY = None
        xColumns = []
        hasSubGrids = False
        for _, (text, x, y) in enumerate(calls):
            if hasSubGrids:
                grid.append([ "" ])
            if isinstance(text, gridformatter.GridFormatter):
                grid += text.grid
                prevY = y
                hasSubGrids = True
                xColumns.append(x)
                continue

            if prevY is None or abs(y - prevY) > self.pixelTolerance: # some pixel forgiveness...
                grid.append([])
            index = self.findExistingColumn(x, xColumns)
            if index is None:
                if len(grid) == 1:
                    index = len(xColumns)
                    xColumns.append(x)
                else:
                    index = self.findIndex(x, xColumns)
                    xColumns.insert(index, x)
                    for row in range(len(grid) - 1):
                        if index < len(grid[row]):
                            grid[row].insert(index, "")
            while len(grid[-1]) < index:
                grid[-1].append("")
            grid[-1].append(text)
            prevY = y

        if len(grid) > 0:
            return grid, max((len(r) for r in grid))
        else:
            return None, 0

    def findExistingColumn(self, x, xColumns): # more pixel forgiveness
        for attempt in xrange(x - self.pixelTolerance, x + self.pixelTolerance + 1):
            if attempt in xColumns:
                return xColumns.index(attempt)    

    def findIndex(self, x, xColumns):
        # linear search, replace with bisect?
        for ix, currX in enumerate(xColumns):
            if x < currX:
                return ix
        return len(xColumns)

    def tryMakeGrid(self, figure, sortedChildren, childDescriptions):
        calls = [ self.makeCall(desc, child) for desc, child in zip(childDescriptions, sortedChildren) ]
        calls.sort(cmp=self.compareCalls)
        return self.makeTextGrid(calls)

    def makeCall(self, desc, child):
        loc = child.getLocation()            
        # x and y should be public fields, and are sometimes. In our tests, they are methods, for some unknown reason
        return desc, getInt(loc.x), getInt(loc.y)
            
    def layoutSortsChildren(self, widget):
        return False
    
    def getVerticalDividePositions(self, visibleChildren):
        return []

    def handleGridFormatter(self, formatter):
        return formatter # It's not a horizontal row, but we want to be able to combine grids with each other
    
    def getPolylineShapeDescription(self, widget):
        pass
