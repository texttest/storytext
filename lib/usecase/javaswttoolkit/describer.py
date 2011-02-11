
import usecase.guishared, util, types, os, logging
from itertools import izip
from usecase.definitions import UseCaseScriptError
from org.eclipse import swt
from java.util import Date

class WidgetCounter:
    def __init__(self, equalityMethod=None):
        self.widgetNumbers = []
        self.nextWidgetNumber = 1
        self.customEqualityMethod = equalityMethod

    def widgetsEqual(self, widget1, widget2):
        if self.customEqualityMethod:
            return widget1 is widget2 or self.customEqualityMethod(widget1, widget2)
        else:
            return widget1 is widget2

    def getWidgetNumber(self, widget):
        for currWidget, number in self.widgetNumbers:
            if not currWidget.isDisposed() and self.widgetsEqual(widget, currWidget):
                return number
        return 0

    def getId(self, widget):
        number = self.getWidgetNumber(widget)
        if not number:
            number = self.nextWidgetNumber
            self.widgetNumbers.append((widget, self.nextWidgetNumber))
            self.nextWidgetNumber += 1
        return str(number)
        
        
class Describer(usecase.guishared.Describer):
    styleNames = [ (swt.widgets.CoolItem, []),
                   (swt.widgets.Item    , [ "SEPARATOR", "DROP_DOWN", "CHECK", "CASCADE", "RADIO" ]),
                   (swt.widgets.Button  , [ "CHECK", "RADIO", "TOGGLE", "ARROW", "UP", "DOWN" ]),
                   (swt.widgets.DateTime, [ "DATE", "TIME", "CALENDAR", "SHORT" ]),
                   (swt.widgets.Combo   , [ "READ_ONLY", "SIMPLE" ]), 
                   (swt.widgets.Text    , [ "PASSWORD", "SEARCH", "READ_ONLY" ]) ]
    statelessWidgets = [ swt.widgets.Label, swt.widgets.Sash,
                         swt.widgets.Link, swt.widgets.Menu, types.NoneType ]
    stateWidgets = [ swt.widgets.Shell, swt.widgets.Button, swt.widgets.CoolBar, swt.widgets.ToolBar, swt.widgets.Combo,
                     swt.widgets.ExpandBar, swt.widgets.Text, swt.widgets.List, swt.widgets.Tree, swt.widgets.DateTime,
                     swt.custom.CTabFolder, swt.widgets.Canvas, swt.browser.Browser, swt.widgets.Composite ]
    def __init__(self):
        self.imageCounter = WidgetCounter(self.imagesEqual)
        self.canvasCounter = WidgetCounter()
        self.contextMenuCounter = WidgetCounter(self.contextMenusEqual)
        self.widgetsAppeared = []
        self.structureLogger = logging.getLogger("SWT structure")
        self.clipboardText = None
        usecase.guishared.Describer.__init__(self)

    def storeShowsAndPaints(self, parent, widgets, eventType, seenBefore):
        if eventType == swt.SWT.Paint or \
           (eventType == swt.SWT.Show and not isinstance(parent, (swt.widgets.Menu, swt.widgets.ScrollBar))):
            # Menu show events seem a bit spurious, they aren't really shown at this point:
            # ScrollBar shows are not relevant to anything
            self.widgetsAppeared.append((parent, seenBefore))
            
    def describeWithUpdates(self, shell):
        if self.structureLogger.isEnabledFor(logging.DEBUG) and shell not in self.windows:
            self.describeStructure(shell)
        util.MonitorListener.addCallback(self.storeShowsAndPaints)
        stateChanges = self.findStateChanges()
        self.describeVisibilityChanges(stateChanges)
        self.describeStateChanges(stateChanges)
        self.describeClipboardChanges(shell.getDisplay())
        self.describe(shell)
        self.widgetsAppeared = []

    def parentMarked(self, widget, markedWidgets):
        if widget in markedWidgets:
            return True
        elif widget.getParent():
            return self.parentMarked(widget.getParent(), markedWidgets)
        else:
            return False

    def describeVisibilityChanges(self, stateChanges):
        markedWidgets = [ widget for widget, repaint in self.widgetsAppeared ] + \
                        [ widget for widget, old, new in stateChanges ]
        for widget, repaint in self.widgetsAppeared:
            if not widget.isDisposed() and util.isVisible(widget):
                if isinstance(widget, swt.widgets.Shell):
                    self.describe(widget)
                else:
                    parent = widget.getParent()
                    if not self.parentMarked(parent, markedWidgets):
                        markedWidgets.append(parent)
                        if repaint:
                            self.logger.info("Widgets have been repainted: describing common parent :\n")
                        else:
                            self.logger.info("New widgets have appeared: describing common parent :\n")
                        self.logger.info(self.getChildrenDescription(parent))

    def describeClipboardChanges(self, display):
        from org.eclipse.swt.dnd import Clipboard, TextTransfer
        clipboard = Clipboard(display)
        textTransfer = TextTransfer.getInstance()
        if self.clipboardText is None:
            # Initially. For some reason it doesn't let us set empty strings here
            # clearContents seemed the way to go, but seems not to work on Windows
            self.clipboardText = "dummy text for PyUseCase tests"
            clipboard.setContents([ self.clipboardText ], [ textTransfer ])
        else:
            newText = clipboard.getContents(textTransfer) or ""
            if newText != self.clipboardText:
                self.logger.info("Copied following to clipboard :\n" + newText)
                self.clipboardText = newText
        clipboard.dispose()
        
    def getNoneTypeDescription(self, *args):
        return ""

    def getWindowClasses(self):
        return swt.widgets.Shell, swt.widgets.Dialog

    def getTextEntryClass(self):
        return swt.widgets.Text

    def getWindowString(self):
        return "Shell"

    def getShellState(self, shell):
        return shell.getText()

    def getItemBarDescription(self, *args, **kw):
        return "\n".join(self.getAllItemDescriptions(*args, **kw))

    def getAllItemDescriptions(self, itemBar, indent=0, subItemMethod=None,
                               prefix="", selection=[], columnCount=0):
        descs = []
        for item in itemBar.getItems():
            currPrefix = prefix + " " * indent * 2
            itemDesc = self.getItemDescription(item, currPrefix, item in selection)
            if columnCount:
                row = [ itemDesc ]
                for colIndex in range(1, columnCount):
                    row.append(self.getItemColumnDescription(item, colIndex))
                descs.append(row)
            elif itemDesc:
                descs.append(itemDesc)
            if subItemMethod:
                descs += subItemMethod(item, indent, prefix=prefix, selection=selection, columnCount=columnCount)
        return descs

    def getCascadeMenuDescriptions(self, item, indent, **kw):
        cascadeMenu = item.getMenu()
        if cascadeMenu:
            return self.getAllItemDescriptions(cascadeMenu, indent+1, subItemMethod=self.getCascadeMenuDescriptions, **kw)
        else:
            return []

    def getSubTreeDescriptions(self, item, indent, **kw):
        if item.getExpanded():
            return self.getAllItemDescriptions(item, indent+1, subItemMethod=self.getSubTreeDescriptions, **kw)
        else:
            return []

    def getExpandItemDescriptions(self, item, indent, *args, **kw):
        if item.getExpanded():
            return [ self.getItemControlDescription(item, indent + 1, *args, **kw) ]
        else:
            return []

    def getCoolItemDescriptions(self, item, *args, **kw):
        itemDesc = self.getItemControlDescription(item, *args, **kw)
        if itemDesc:
            return [ itemDesc ] 
        else:
            return []

    def getItemControlDescription(self, item, indent, **kw):
        control = item.getControl()
        if control:
            descLines = self.getDescription(control).splitlines()
            paddedLines = [ " " * indent * 2 + line for line in descLines ]
            return "\n".join(paddedLines) + "\n"
        else:
            return ""

    def getMenuDescription(self, menu, indent=1):
        return self.getItemBarDescription(menu, indent=indent, subItemMethod=self.getCascadeMenuDescriptions)

    def getMenuBarDescription(self, menubar):
        if menubar:
            return "Menu Bar:\n" + self.getMenuDescription(menubar)
        else:
            return ""

    def getExpandBarDescription(self, widget):
        visibleChildren = filter(lambda c: c.getVisible(), widget.getChildren())
        contextMenus = self.getNewChildContextMenus(visibleChildren)
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return "Expand Bar:\n" + self.getItemBarDescription(widget, indent=1, subItemMethod=self.getExpandItemDescriptions) + \
               self.formatContextMenuDescriptions(contextMenus)

    def getExpandBarState(self, expandbar):
        return expandbar.getChildren(), [ item.getExpanded() for item in expandbar.getItems() ] 

    def getToolBarDescription(self, toolbar, indent=1):
        return "Tool Bar:\n" + self.getItemBarDescription(toolbar, indent=indent)
    
    def getCoolBarDescription(self, coolbar):
        return "Cool Bar:\n" + self.getItemBarDescription(coolbar, indent=1,
                                                          subItemMethod=self.getCoolItemDescriptions)

    def contextMenusEqual(self, menu1, menu2):
        return [ item.getText() for item in menu1.getItems() ] == [ item.getText() for item in menu2.getItems() ]

    def imagesEqual(self, image1, image2):
        return image1.getImageData().data == image2.getImageData().data

    def getImageDescription(self, image):
        # Seems difficult to get any sensible image information out, there is
        # basically no query API for this in SWT
        return "Image " + self.imageCounter.getId(image)

    def getCanvasDescription(self, widget):
        return "Canvas " + self.canvasCounter.getId(widget)

    def findStyleList(self, item):
        for widgetClass, styleList in self.styleNames:
            if isinstance(item, widgetClass):
                return styleList
        return []

    def getStyleDescriptions(self, item):
        styleList = self.findStyleList(item)
        style = item.getStyle()
        descs = []
        for tryStyle in styleList:
            if style & getattr(swt.SWT, tryStyle) != 0:
                descs.append(tryStyle.lower().replace("_", " ").replace("separator", "---"))
        return descs
        
    def getItemDescription(self, item, prefix, *args):
        elements = []
        if item.getText():
            elements.append(item.getText())
        elements += self.getPropertyElements(item, *args)
        desc = self.combineElements(elements)
        if desc:
            return prefix + desc

    def getItemColumnDescription(self, item, colIndex):
        elements = [ item.getText(colIndex) ]
        if item.getImage(colIndex):
            elements.append(self.getImageDescription(item.getImage(colIndex)))
        return self.combineElements(elements)

    def getPropertyElements(self, item, selected=False):
        elements = []
        if hasattr(item, "getToolTipText") and item.getToolTipText():
            elements.append("Tooltip '" + item.getToolTipText() + "'")
        elements += self.getStyleDescriptions(item)
        if hasattr(item, "getImage") and item.getImage():
            elements.append(self.getImageDescription(item.getImage()))
        if hasattr(item, "getEnabled") and not item.getEnabled():
            elements.append("greyed out")
        if selected:
            elements.append("selected")
        elements.append(self.getContextMenuReference(item))
        return elements

    def getLabelDescription(self, label):
        if label.getStyle() & swt.SWT.SEPARATOR:
            return "-" * 10
        elements = []
        if label.getText():
            elements.append("'" + label.getText() + "'")
        for fontData in label.getFont().getFontData():
            fontStyle = fontData.getStyle()
            for fontAttr in [ "BOLD", "ITALIC" ]:
                if fontStyle & getattr(swt.SWT, fontAttr):
                    elements.append(fontAttr.lower())
        if label.getImage():
            elements.append(self.getImageDescription(label.getImage()))
        elements.append(self.getContextMenuReference(label))
        return self.combineElements(elements)

    def getButtonDescription(self, widget):
        desc = "Button"
        if widget.getText():
            desc += " '" + widget.getText() + "'"
        properties = self.getButtonState(widget)
        self.widgetsWithState[widget] = properties
        elements = [ desc ] + properties 
        return self.combineElements(elements)

    def getButtonState(self, widget):
        return self.getPropertyElements(widget, selected=widget.getSelection())

    def combineElements(self, elements):
        elements = filter(len, elements)
        if len(elements) <= 1:
            return "".join(elements)
        else:
            return elements[0] + " (" + ", ".join(elements[1:]) + ")"

    def getSashDescription(self, widget):
        orientation = "Horizontal"
        if widget.getStyle() & swt.SWT.VERTICAL:
            orientation = "Vertical"
        return "-" * 15 + " " + orientation + " sash " + "-" * 15

    def getLinkDescription(self, widget):
        return "Link '" + widget.getText() + "'"
        
    def getWindowContentDescription(self, shell):
        desc = ""
        desc = self.addToDescription(desc, self.getMenuBarDescription(shell.getMenuBar()))
        return self.addToDescription(desc, self.getChildrenDescription(shell))

    def getBrowserDescription(self, widget):
        return "Browser browsing '" + widget.getUrl() + "'"

    def fixLineEndings(self, text):
        # Methods return text 'raw' with Windows line endings
        if os.linesep != "\n":
            return text.replace(os.linesep, "\n")
        else:
            return text
    
    def getUpdatePrefix(self, widget, oldState, state):
        if isinstance(widget, self.getTextEntryClass()):
            return "\nUpdated " + (util.getTextLabel(widget) or "Text") +  " Field\n"
        elif isinstance(widget, swt.widgets.Combo):
            return "\nUpdated " + util.getTextLabel(widget) + " Combo Box\n"
        elif util.getTopControl(widget):
            return "\n"
        else:
            return "\nUpdated "

    def getState(self, widget):
        if widget.isDisposed():
            # Will be caught, and the widget cleaned up
            raise UseCaseScriptError, "Widget is Disposed"
        else:
            return self.getSpecificState(widget)

    def getTextState(self, widget):
        return widget.getText(), self.getPropertyElements(widget)

    def getComboState(self, widget):
        return self.getTextState(widget)

    def getTextDescription(self, widget):
        contents, properties = self.getState(widget)
        self.widgetsWithState[widget] = contents, properties
        header = "=" * 10 + " " + widget.__class__.__name__ + " " + "=" * 10
        fullHeader = self.combineElements([ header ] + properties)
        return fullHeader + "\n" + self.fixLineEndings(contents.rstrip()) + "\n" + "=" * len(header)    

    def getComboDescription(self, widget):
        return self.getTextDescription(widget)

    def getAndStoreState(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return state

    def getTreeDescription(self, widget):
        return self.getAndStoreState(widget)

    def getListDescription(self, widget):
        return self.getAndStoreState(widget)

    def getDateTimeDescription(self, widget):
        return self.getAndStoreState(widget)

    def getDateString(self, widget):
        if widget.getStyle() & swt.SWT.TIME:
            widgetDate = Date()
            widgetDate.setHours(widget.getHours())
            widgetDate.setMinutes(widget.getMinutes())
            widgetDate.setSeconds(widget.getSeconds())
            return util.getDateFormat(swt.SWT.TIME).format(widgetDate)
        else:
            widgetDate = Date(widget.getYear() - 1900, widget.getMonth(), widget.getDay())
            return util.getDateFormat(swt.SWT.DATE).format(widgetDate)

    def getDateTimeState(self, widget):
        elements = [ "DateTime" ] + self.getPropertyElements(widget) + [ "showing " + self.getDateString(widget) ]
        return self.combineElements(elements)

    def getListState(self, widget):
        text = self.combineElements([ "List" ] + self.getPropertyElements(widget)) + " :\n"
        selection = widget.getSelection()
        for item in widget.getItems():
            text += "-> " + item
            if item in selection:
                text += " (selected)"
            text += "\n"
        return text

    def getContextMenuReference(self, widget):
        if not isinstance(widget, swt.widgets.MenuItem) and hasattr(widget, "getMenu") and widget.getMenu():
            return "Context Menu " + self.contextMenuCounter.getId(widget.getMenu())
        else:
            return ""

    def getTreeState(self, widget):
        columns = widget.getColumns()
        columnCount = len(columns)
        text = self.combineElements([ "Tree" ] + self.getPropertyElements(widget)) + " :\n"
        rows = self.getAllItemDescriptions(widget, indent=0, subItemMethod=self.getSubTreeDescriptions,
                                           prefix="-> ", selection=widget.getSelection(),
                                           columnCount=columnCount)
        if columnCount > 0:
            rows.insert(0, [ c.getText() for c in columns ])
            colWidths = self.findColumnWidths(rows, columnCount)
            text += self.formatCellsInGrid(rows, colWidths)
        else:
            text += "\n".join(rows)
        return text

    def getCTabFolderDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return "TabFolder with tabs " + state

    def getCTabFolderState(self, widget):
        return " , ".join(self.getAllItemDescriptions(widget, selection=[ widget.getSelection() ]))

    def getCompositeState(self, widget):
        return util.getTopControl(widget)

    def getCompositeDescription(self, widget):
        return self.combineElements([ self.getStateControlDescription(widget), self.getContextMenuReference(widget) ])

    def getStateControlDescription(self, widget):
        stateControl = self.getState(widget)
        if stateControl:
            self.widgetsWithState[widget] = stateControl
            if len(widget.getChildren()) > 1:
                header = "+" * 6 + " Stacked Layout " + "+" * 6
                footer = "+" * len(header)
                return header + "\n" + self.getDescription(stateControl) + "\n" + footer
            else:
                return self.getDescription(stateControl)
        else:
            return ""

    def getVerticalDividePositions(self, children):
        positions = []
        for child in children:
            if self.checkInstance(child, swt.widgets.Sash) and child.getStyle() & swt.SWT.VERTICAL:
                 positions.append(child.getLocation().x)
        return sorted(positions)

    def getDividerIndex(self, pos, dividers):
        for i, dividePos in enumerate(dividers):
            if pos < dividePos:
                return i
        return len(dividers)

    def layoutSortsChildren(self, widget):
        layout = widget.getLayout()
        return layout is not None and not util.checkInstance(layout, swt.layout.FormLayout) and \
               not util.checkInstance(widget, swt.custom.SashForm)

    def getNewChildContextMenus(self, children):
        menus = []
        for child in children:
            menu = child.getMenu()
            if menu and not self.contextMenuCounter.getWidgetNumber(child.getMenu()):
                menus.append(menu)
        return menus

    def sortChildren(self, widget):
        visibleChildren = filter(lambda c: c.getVisible(), widget.getChildren())
        if len(visibleChildren) <= 1 or self.layoutSortsChildren(widget):
            # Trust in the layout, if there is one
            return visibleChildren
        
        xDivides = self.getVerticalDividePositions(visibleChildren)
        # Children don't always come in order, sort them...
        def getChildPosition(child):
            loc = child.getLocation()
            # With a divider, want to make sure everything ends up on the correct side of it
            return self.getDividerIndex(loc.x, xDivides), loc.y, loc.x
            
        visibleChildren.sort(key=getChildPosition)
        return visibleChildren
    
    def getChildrenDescription(self, widget):
        # Coolbars and Expandbars describe their children directly : they have two parallel children structures
        # Composites with StackLayout use the topControl rather than the children
        if not isinstance(widget, swt.widgets.Composite) or \
               isinstance(widget, (swt.widgets.CoolBar, swt.widgets.ExpandBar, swt.widgets.DateTime)) or \
               util.getTopControl(widget):
            return ""

        children = self.sortChildren(widget)
        contextMenus = self.getNewChildContextMenus(children)
        return self.formatChildrenDescriptions(widget, children) + self.formatContextMenuDescriptions(contextMenus)

    def formatContextMenuDescriptions(self, contextMenus):
        text = ""
        for contextMenu in contextMenus:
            text += "\n\nContext Menu " + self.contextMenuCounter.getId(contextMenu) + ":\n" + self.getMenuDescription(contextMenu)
        return text

    def formatChildrenDescriptions(self, widget, children):
        childDescriptions = map(self.getDescription, children)
        columns = self.getLayoutColumns(widget, childDescriptions)
        if columns > 1:
            horizontalSpans = map(self.getHorizontalSpan, children)
            return self.formatInGrid(childDescriptions, columns, horizontalSpans)
        else:
            return self.formatInColumn(childDescriptions)

    def getHorizontalSpan(self, widget):
        layout = widget.getLayoutData()
        if hasattr(layout, "horizontalSpan"):
            return layout.horizontalSpan
        else:
            return 1

    def formatInColumn(self, childDescriptions):
        desc = ""
        for childDesc in childDescriptions:
            desc = self.addToDescription(desc, childDesc)
        
        return desc.rstrip()

    def getLayoutColumns(self, widget, childDescriptions):
        if len(childDescriptions) > 1:
            layout = widget.getLayout()
            if hasattr(layout, "numColumns"):
                return layout.numColumns
            elif hasattr(layout, "type"):
                if layout.type == swt.SWT.HORIZONTAL:
                    return len(childDescriptions)
        return 1

    def getCellWidth(self, row, colNum, numColumns):
        # Don't include rows which span several columns
        if len(row) == numColumns:
            lines = row[colNum].splitlines()
            if lines:
                return max((len(line) for line in lines))
        return 0

    def makeGrid(self, childDescriptions, numColumns, horizontalSpans):
        grid = []
        index = 0
        for childDesc, span in izip(childDescriptions, horizontalSpans):
            if index % numColumns == 0:
                grid.append([])
            grid[-1].append(childDesc)
            index += span
        return grid

    def findColumnWidths(self, grid, numColumns):
        colWidths = []
        for colNum in range(numColumns):
            maxWidth = max((self.getCellWidth(row, colNum, numColumns) for row in grid))
            if colNum == numColumns - 1:
                colWidths.append(maxWidth)
            else:
                # Pad two spaces between each column
                colWidths.append(maxWidth + 2)
        return colWidths
    
    def formatInGrid(self, childDescriptions, numColumns, horizontalSpans):
        grid = self.makeGrid(childDescriptions, numColumns, horizontalSpans)
        colWidths = self.findColumnWidths(grid, numColumns)
        totalWidth = sum(colWidths)
        if totalWidth > 130: # After a while, excessively wide grids just get too hard to read
            header = "." * 6 + " " + str(numColumns) + "-Column Layout " + "." * 6
            desc = self.formatColumnsInGrid(grid, numColumns)
            footer = "." * len(header)
            return header + "\n" + desc + "\n" + footer
        else:
            return self.formatCellsInGrid(grid, colWidths)

    def formatCellsInGrid(self, grid, colWidths):
        desc = ""
        for row in grid:
            rowLines = max((desc.count("\n") + 1 for desc in row))
            for rowLine in range(rowLines):
                for colNum, childDesc in enumerate(row):
                    cellLines = childDesc.splitlines()
                    if rowLine < len(cellLines):
                        cellRow = cellLines[rowLine]
                    else:
                        cellRow = ""
                    desc += cellRow.ljust(colWidths[colNum])
                desc = desc.rstrip(" ") + "\n" # don't leave trailing spaces        
        return desc.rstrip()

    def formatColumnsInGrid(self, grid, numColumns):
        desc = ""
        for colNum in range(numColumns):
            for row in grid:
                if colNum < len(row):
                    desc += row[colNum] + "\n"
            desc += "\n"
        return desc.rstrip()

    def checkInstance(self, *args):
        return util.checkInstance(*args)

    ##Debug code
    def getRawData(self, widget):
        basic = widget.__class__.__name__ + " " + str(id(widget))
        if hasattr(widget, "getLayout"):
            layout = widget.getLayout()
            if layout is not None:
                basic += " (" + layout.__class__.__name__ + ")"
        return basic
        
    def describeStructure(self, widget, indent=0):
        self.structureLogger.info("-" * 2 * indent + self.getRawData(widget))
        if hasattr(widget, "getChildren"):
            for child in widget.getChildren():
                self.describeStructure(child, indent+1)
