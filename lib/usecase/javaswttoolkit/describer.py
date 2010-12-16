
import usecase.guishared, util, types, os
from usecase.definitions import UseCaseScriptError
from org.eclipse import swt
        
class Describer(usecase.guishared.Describer):
    styleNames = [ "PUSH", "SEPARATOR", "DROP_DOWN", "CHECK", "CASCADE", "RADIO" ]
    def __init__(self):
        self.statelessWidgets = [ swt.widgets.Label, swt.widgets.CoolBar,
                                  swt.widgets.ToolBar, swt.widgets.Sash, swt.widgets.Link, swt.browser.Browser,
                                  swt.widgets.Composite, types.NoneType ]
        self.stateWidgets = [ swt.widgets.Shell, swt.widgets.Text, swt.widgets.Tree, swt.custom.CTabFolder ]
        self.imageNumbers = []
        self.nextImageNumber = 1
        self.displays = []
        self.widgetsBecomeVisible = []
        usecase.guishared.Describer.__init__(self)

    def addVisibilityFilter(self, display):
        if display not in self.displays:
            self.displays.append(display)
            class StoreListener(swt.widgets.Listener):
                def handleEvent(listenerSelf, e):
                    if not isinstance(e.widget, swt.widgets.Menu): # ignore these for now, they aren't really shown at this point
                        self.widgetsBecomeVisible.append(e.widget)
            display.addFilter(swt.SWT.Show, StoreListener())
            
    def describeWithUpdates(self, shell):
        self.addVisibilityFilter(shell.getDisplay())
        stateChanges = self.findStateChanges()
        self.describeNewlyShown(stateChanges)
        self.describeStateChanges(stateChanges)
        self.describe(shell)

    def parentMarked(self, widget, stateChangeWidgets):
        if widget in self.widgetsBecomeVisible or widget in stateChangeWidgets:
            return True
        elif widget.getParent():
            return self.parentMarked(widget.getParent(), stateChangeWidgets)
        else:
            return False

    def describeNewlyShown(self, stateChanges):
        stateChangeWidgets = [ widget for widget, old, new in stateChanges ]
        for widget in self.widgetsBecomeVisible:
            if not widget.isDisposed():
                parent = widget.getParent()
                if not self.parentMarked(parent, stateChangeWidgets):
                    self.logger.info("New widgets have become visible: describing common parent :\n")
                    self.logger.info(self.getChildrenDescription(parent))
        self.widgetsBecomeVisible = []
        
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

    def getItemBarDescription(self, itemBar, indent=0, subItemMethod=None, prefix="", separator="\n"):
        desc = ""
        for item in itemBar.getItems():
            desc += prefix + " " * indent * 2 + self.getItemDescription(item)
            if subItemMethod:
                desc += subItemMethod(item, indent, prefix)
            desc += separator
        return desc

    def getCascadeMenuDescription(self, item, indent, prefix=""):
        cascadeMenu = item.getMenu()
        if cascadeMenu:
            return " :\n" + self.getMenuDescription(cascadeMenu, indent + 1).rstrip()
        else:
            return ""

    def getSubTreeDescription(self, item, indent, prefix):
        subDesc = self.getItemBarDescription(item, indent+1, subItemMethod=self.getSubTreeDescription, prefix=prefix)
        if subDesc:
            return "\n" + subDesc.rstrip()
        else:
            return ""

    def getCoolItemDescription(self, item, indent, prefix):
        control = item.getControl()
        if control:
            descLines = self.getDescription(control).splitlines()
            paddedLines = [ "  " + line for line in descLines ]
            return " " + "\n".join(paddedLines).strip() + "\n"
        else:
            return ""

    def getMenuDescription(self, menu, indent=1):
        return self.getItemBarDescription(menu, indent=indent, subItemMethod=self.getCascadeMenuDescription)

    def getMenuBarDescription(self, menubar):
        if menubar:
            return "Menu Bar:\n" + self.getMenuDescription(menubar)
        else:
            return ""

    def getToolBarDescription(self, toolbar, indent=1):
        return "Tool Bar:\n" + self.getItemBarDescription(toolbar, indent=indent)

    def getCoolBarDescription(self, coolbar):
        return "Cool Bar:\n" + self.getItemBarDescription(coolbar, indent=1, subItemMethod=self.getCoolItemDescription)

    def getImageNumber(self, image):
        for currImage, number in self.imageNumbers:
            if not currImage.isDisposed() and image.getImageData().data == currImage.getImageData().data:
                return number
        return 0

    def getImageDescription(self, image):
        # Seems difficult to get any sensible image information out, there is
        # basically no query API for this in SWT
        number = self.getImageNumber(image)
        if not number:
            number = self.nextImageNumber
            self.imageNumbers.append((image, self.nextImageNumber))
            self.nextImageNumber += 1
        return "Image " + str(number)

    def getStyleDescription(self, style):
        for tryStyle in self.styleNames:
            if style & getattr(swt.SWT, tryStyle) != 0:
                return tryStyle.lower().replace("_", " ").replace("push", "").replace("separator", "---")
        
    def getItemDescription(self, item):
        elements = []
        if item.getText():
            elements.append(item.getText())
        if hasattr(item, "getToolTipText") and item.getToolTipText():
            elements.append("Tooltip '" + item.getToolTipText() + "'")
        styleDesc = self.getStyleDescription(item.getStyle())
        if styleDesc:
            elements.append(styleDesc)
        if item.getImage():
            elements.append(self.getImageDescription(item.getImage()))
        if hasattr(item, "getEnabled") and not item.getEnabled():
            elements.append("greyed out")
        return self.combineElements(elements)

    def combineElements(self, elements):
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
        
    def getLabelDescription(self, label):
        elements = [ "'" + label.getText() + "'" ]
        for fontData in label.getFont().getFontData():
            fontStyle = fontData.getStyle()
            for fontAttr in [ "BOLD", "ITALIC" ]:
                if fontStyle & getattr(swt.SWT, fontAttr):
                    elements.append(fontAttr.lower())
        return self.combineElements(elements)
    
    def getWindowContentDescription(self, shell):
        desc = ""
        desc = self.addToDescription(desc, self.getMenuBarDescription(shell.getMenuBar()))
        return self.addToDescription(desc, self.getChildrenDescription(shell))

    def getCompositeDescription(self, widget):
        return ""

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
        else:
            return "\nUpdated "

    def getState(self, widget):
        if widget.isDisposed():
            # Will be caught, and the widget cleaned up
            raise UseCaseScriptError, "Widget is Disposed"
        else:
            return usecase.guishared.Describer.getState(self, widget)
    
    def getTextState(self, widget):
        return widget.getText()

    def getTextDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        header = "=" * 10 + " Text " + "=" * 10        
        return header + "\n" + self.fixLineEndings(state.rstrip()) + "\n" + "=" * len(header)    

    def getTreeDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return state

    def getTreeState(self, widget):
        columns = widget.getColumns()
        text = "Tree with " + str(len(columns)) + " columns : "
        text += " , ".join((c.getText() for c in columns)) + "\n"
        text += self.getItemBarDescription(widget, indent=0, subItemMethod=self.getSubTreeDescription, prefix="-> ")
        return text

    def getCTabFolderDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return "TabFolder with tabs " + state

    def getCTabFolderState(self, widget):
        return self.getItemBarDescription(widget, separator=" , ")

    def getVerticalDividePosition(self, children):
        for child in children:
            if self.checkInstance(child, swt.widgets.Sash) and child.getStyle() & swt.SWT.VERTICAL:
                 return child.getLocation().x
		
    def sortChildren(self, widget):
        visibleChildren = filter(lambda c: c.getVisible(), widget.getChildren())
        if len(visibleChildren) <= 1 or widget.getLayout() is not None:
            # Trust in the layout, if there is one
            return visibleChildren
        
        xDivide = self.getVerticalDividePosition(visibleChildren)
        # Children don't always come in order, sort them...
        def getChildPosition(child):
            loc = child.getLocation()
            if xDivide:
                # With a divider, want to make sure everything ends up on the correct side of it
                return int(loc.x >= xDivide), loc.y, loc.x
            else:
                return loc.y, loc.x # Reverse the order, we want to go left-to-right and then top-to-bottom

        visibleChildren.sort(key=getChildPosition)
        return visibleChildren
    
    def getChildrenDescription(self, widget):
        # Coolbars describe their children directly : they have two parallel children structures
        if not isinstance(widget, swt.widgets.Composite) or isinstance(widget, swt.widgets.CoolBar):
            return ""

        childDescriptions = map(self.getDescription, self.sortChildren(widget))
        columns = self.getLayoutColumns(widget)
        if columns > 1 and len(childDescriptions) > 1:
            return self.formatInGrid(childDescriptions, widget.getLayout().numColumns)
        else:
            return self.formatInColumn(childDescriptions)

    def formatInColumn(self, childDescriptions):
        desc = ""
        for childDesc in childDescriptions:
            desc = self.addToDescription(desc, childDesc)
        
        return desc.rstrip()

    def getLayoutColumns(self, widget):
        try:
            return widget.getLayout().numColumns
        except AttributeError:
            return 1

    def getCellWidth(self, row, colNum):
        if len(row) > colNum:
            return len(row[colNum])
        else:
            return 0

    def formatInGrid(self, childDescriptions, numColumns):
        desc = ""
        grid = []
        for i, childDesc in enumerate(childDescriptions):
            if i % numColumns == 0:
                grid.append([])
            grid[-1].append(childDesc)

        colWidths = []
        for colNum in range(numColumns):
            maxWidth = max((self.getCellWidth(row, colNum) for row in grid))
            colWidths.append(maxWidth + 2)

        for row in grid:
            for colNum, childDesc in enumerate(row):
                cellDesc = childDesc.ljust(colWidths[colNum])
                if "\n" in childDesc and colNum > 0:
                    indent = sum((colWidths[i] for i in range(colNum)))
                    cellDesc = cellDesc.strip().replace("\n", "\n" + " " * indent)
                desc += cellDesc
            desc += "\n"        
        return desc.rstrip()

    def checkInstance(self, *args):
        return util.checkInstance(*args)

    ### Debug code
    ## def getRawData(self, widget):
    ##     return widget.__class__.__name__ + " " + str(id(widget)) + self.getData(widget)

    ## def getData(self, widget):
    ##     if widget.getData():
    ##         try:
    ##             return " " + widget.getData().getBundleId() + " " + widget.getData().getElementType() + " " + repr(widget.getData().getConfigurationElement())
    ##         except:
    ##             return " " + widget.getData().toString()
    ##     else:
    ##         return ""
        
