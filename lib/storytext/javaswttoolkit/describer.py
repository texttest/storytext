
import storytext.guishared, util, types, logging, sys, os
from storytext.definitions import UseCaseScriptError
from storytext.gridformatter import GridFormatter
from org.eclipse import swt
from browserhtmlparser import BrowserHtmlParser
from java.util import Date
from java.io import File, FilenameFilter
from org.eclipse.jface.resource import ImageDescriptor
from array import array
from ordereddict import OrderedDict

class Describer(storytext.guishared.Describer):
    styleNames = [ (swt.widgets.CoolItem, []),
                   (swt.widgets.Item    , [ "SEPARATOR", "DROP_DOWN", "CHECK", "CASCADE", "RADIO" ]),
                   (swt.widgets.Button  , [ "CHECK", "RADIO", "TOGGLE", "ARROW", "UP", "DOWN" ]),
                   (swt.widgets.DateTime, [ "DATE", "TIME", "CALENDAR", "SHORT" ]),
                   (swt.widgets.Combo   , [ "READ_ONLY", "SIMPLE" ]),
                   (swt.custom.CCombo   , [ "READ_ONLY", "FLAT", "BORDER" ]), 
                   (swt.widgets.Text    , [ "PASSWORD", "SEARCH", "READ_ONLY" ]) ]
    ignoreWidgets = [ types.NoneType ]
    # DateTime children are an implementation detail
    # Coolbars and Expandbars describe their children directly : they have two parallel children structures
    ignoreChildren = (swt.widgets.CoolBar, swt.widgets.ExpandBar, swt.widgets.DateTime)
    statelessWidgets = [ swt.widgets.Sash ]
    stateWidgets = [ swt.widgets.Shell, swt.widgets.Button, swt.widgets.Menu, swt.widgets.Link,
                     swt.widgets.CoolBar, swt.widgets.ToolBar, swt.widgets.Label, swt.custom.CLabel,
                     swt.widgets.Combo, swt.widgets.ExpandBar, swt.widgets.Text, swt.widgets.List,
                     swt.widgets.Tree, swt.widgets.DateTime, swt.widgets.TabFolder, swt.widgets.Table, 
                     swt.custom.CTabFolder, swt.widgets.Canvas, swt.browser.Browser, swt.custom.CCombo,
                     swt.widgets.Composite ]
    childrenMethodName = "getChildren"
    visibleMethodName = "getVisible"
    def __init__(self):
        self.canvasCounter = storytext.guishared.WidgetCounter()
        self.contextMenuCounter = storytext.guishared.WidgetCounter(self.contextMenusEqual)
        self.widgetsAppeared = []
        self.widgetsDescribed = set()
        self.browserStates = {}
        self.clipboardText = None
        self.storedImages = {}
        self.imageToName = {}
        self.handleImages()
        storytext.guishared.Describer.__init__(self)

    def setWidgetPainted(self, widget):
        if widget not in self.widgetsDescribed and widget not in self.windows and widget not in self.widgetsAppeared:
            self.logger.debug("Widget painted " + self.getRawData(widget))
            self.widgetsAppeared.append(widget)

    def setWidgetShown(self, widget):
        # Menu show events seem a bit spurious, they aren't really shown at this point:
        # ScrollBar shows are not relevant to anything
        if not isinstance(widget, (swt.widgets.Menu, swt.widgets.ScrollBar)) and widget not in self.widgetsAppeared:
            self.logger.debug("Widget shown " + self.getRawData(widget))
            self.widgetsAppeared.append(widget)

    def addFilters(self, display):
        class ShowListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e):
                storytext.guishared.catchAll(self.setWidgetShown, e.widget)

        class PaintListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e):
                storytext.guishared.catchAll(self.setWidgetPainted, e.widget)

        display.addFilter(swt.SWT.Show, ShowListener())
        display.addFilter(swt.SWT.Paint, PaintListener())

    def describeWithUpdates(self, shellMethod):
        shell = shellMethod()
        if shell in self.windows:
            stateChanges = self.findStateChanges(shell)
            stateChangeWidgets = [ widget for widget, old, new in stateChanges ]
            if self.structureLogger.isEnabledFor(logging.DEBUG):
                for widget in stateChangeWidgets:
                    self.describeStructure(widget)
            describedForAppearance = self.describeAppearedWidgets(stateChangeWidgets)
            self.describeStateChanges(stateChanges, describedForAppearance)
        if shell is not None:
            self.describeClipboardChanges(shell.getDisplay())
            self.describe(shell)
        self.widgetsAppeared = []
        
    def shouldCheckForUpdates(self, widget, shell):
        return not isinstance(widget, self.getMenuClasses()) or (not widget.isDisposed() and widget.getShell() == shell)
    
    def getMenuClasses(self):
        return swt.widgets.Menu

    def widgetShowing(self, widget):
        return not widget.isDisposed() and util.isVisible(widget)

    def describeClipboardChanges(self, display):
        clipboard = swt.dnd.Clipboard(display)
        textTransfer = swt.dnd.TextTransfer.getInstance()
        if self.clipboardText is None:
            # Initially. For some reason it doesn't let us set empty strings here
            # clearContents seemed the way to go, but seems not to work on Windows
            self.clipboardText = "dummy text for StoryText tests"
            clipboard.setContents([ self.clipboardText ], [ textTransfer ])
        else:
            newText = clipboard.getContents(textTransfer) or ""
            if newText != self.clipboardText:
                self.logger.info("Copied following to clipboard :\n" + newText)
                self.clipboardText = newText
        clipboard.dispose()
        
    def getWindowClasses(self):
        return swt.widgets.Shell, swt.widgets.Dialog

    def getTextEntryClass(self):
        return swt.widgets.Text

    def getWindowString(self):
        return "Shell"

    def getShellState(self, shell):
        return shell.getText()

    def getAllItemDescriptions(self, itemBar, indent=0, subItemMethod=None,
                               prefix="", selection=[], columnCount=0, **kw):
        descs = []
        for item in itemBar.getItems():
            currPrefix = prefix + " " * indent * 2
            selected = item in selection
            if columnCount:
                row = [ self.getItemColumnDescription(item, i, currPrefix, selected) for i in range(columnCount) ]
                descs.append(row)
            else:
                itemDesc = self.getItemDescription(item, currPrefix, selected)
                if itemDesc:
                    descs.append(itemDesc)
            if subItemMethod:
                descs += subItemMethod(item, indent, prefix=prefix, selection=selection, columnCount=columnCount, **kw)
        return descs

    def getCascadeMenuDescriptions(self, item, indent, storeStatesForSubMenus=False, **kw):
        cascadeMenu = item.getMenu()
        if cascadeMenu:
            descs = self.getAllItemDescriptions(cascadeMenu, indent+1, subItemMethod=self.getCascadeMenuDescriptions, 
                                                storeStatesForSubMenus=storeStatesForSubMenus, **kw)
            if indent == 1 and storeStatesForSubMenus:
                self.widgetsWithState[cascadeMenu] = "\n".join(descs)
            return descs
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

    def getMenuDescription(self, menu, indent=1, **kw):
        return self.getItemBarDescription(menu, indent=indent, subItemMethod=self.getCascadeMenuDescriptions, **kw)
    
    def getMenuState(self, menu):
        return self.getMenuDescription(menu, indent=2)
    
    def getMenuBarDescription(self, menubar):
        if menubar and "Menu" not in self.excludeClassNames:
            return "Menu Bar:\n" + self.getMenuDescription(menubar, storeStatesForSubMenus=True)
        else:
            return ""

    def getExpandBarDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return "Expand Bar:\n" + self.getItemBarDescription(widget, indent=1, subItemMethod=self.getExpandItemDescriptions) 

    def getExpandBarState(self, expandbar):
        return expandbar.getChildren(), [ item.getExpanded() for item in expandbar.getItems() ] 

    def getToolBarDescription(self, toolbar):
        return self.getAndStoreState(toolbar)

    def getToolBarState(self, toolbar):
        return "Tool Bar:\n" + self.getItemBarDescription(toolbar, indent=1)
    
    def getCoolBarDescription(self, coolbar):
        return "Cool Bar:\n" + self.getItemBarDescription(coolbar, indent=1,
                                                          subItemMethod=self.getCoolItemDescriptions)

    def contextMenusEqual(self, menu1, menu2):
        return [ (item.getText(), item.getEnabled()) for item in menu1.getItems() ] == \
               [ (item.getText(), item.getEnabled()) for item in menu2.getItems() ]

    def imagesEqual(self, image1, image2):
        return image1.getImageData().data == image2.getImageData().data

    def getImageDescription(self, image):
        # Seems difficult to get any sensible image information out, there is
        # basically no query API for this in SWT
        if self.imageDescriptionType == "name":
            return self.getImageNameDescription(image)
        else:
            return self.getDefaultImageDescription(image)
        
    def getImageNameDescription(self, image):
        desc = self.getImageName(image)
        if desc is not None:
            return "Icon '" + desc + "'"
        else:
            return "Unknown Image"

    def getDefaultImageDescription(self, image):
        name = "Image"
        if self.imageDescriptionType == "number":
            name += " " + self.imageCounter.getId(image)
        return name
    
    def getPixels(self, data):
        pixels = array('i', (0, ) * data.width * data.height)
        data.getPixels(0, 0, data.width * data.height, pixels, 0)
        return pixels

    def imageDataMatches(self, data, data2, hasExcessData):
        if hasExcessData:
            return self.getPixels(data) == self.getPixels(data2)
        else:
            return data.data == data2.data

    def getImageName(self, image):
        name = self.imageToName.get(image)
        if name is not None:
            return name

        data = image.getImageData()
        hasExcessData = data.width * data.depth / 8 < data.bytesPerLine
        imageDict = self.storedImages.get((data.width, data.height), {})
        for name, imgData in imageDict.items():
            if self.imageDataMatches(data, imgData, hasExcessData):
                baseName = os.path.basename(name)
                self.imageToName[image] = baseName             
                return baseName
       
    def storeImageData(self, url):
        imgDesc = ImageDescriptor.createFromURL(url)
        name = url.getFile()
        if imgDesc is not None:
            newImage = imgDesc.createImage()
            data = newImage.getImageData()
            imageDict = self.storedImages.setdefault((data.width, data.height), OrderedDict())
            if name not in imageDict:
                imageDict[name] = data
            newImage.dispose()

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

    def getItemColumnDescription(self, item, colIndex, prefix, *args):
        elements = [ item.getText(colIndex) ]
        if colIndex:
            if item.getImage(colIndex):
                elements.append(self.getImageDescription(item.getImage(colIndex)))
        else:
            elements += self.getPropertyElements(item, *args)
        
        desc = self.combineElements(elements)
        if desc and colIndex == 0:
            return prefix + desc
        else:
            return desc

    def getControlDecoration(self, item):
        listener = self.getControlDecorationListener(item)
        if listener:
            return self.getEnclosingInstance(listener)

    def getControlDecorationListener(self, item):
        for typedListener in item.getListeners(swt.SWT.FocusIn):
            if hasattr(typedListener, "getEventListener"):
                focusListener = typedListener.getEventListener() 
                if "ControlDecoration" in focusListener.__class__.__name__:
                    return focusListener

    def getEnclosingInstance(self, listener):
        cls = listener.getClass()
        for field in cls.getDeclaredFields():
            if field.getName().startswith("this"):
                field.setAccessible(True)
                return field.get(listener)
       
    def getControlDecorationDescription(self, item):
        deco = self.getControlDecoration(item)
        if deco:
            image = deco.getImage()
            imgDesc = self.getImageDescription(deco.getImage()) if image is not None else ""
        if deco and self.decorationVisible(deco): 
            text = "Decoration " + imgDesc
            desc = deco.getDescriptionText()
            if desc:
                text += "\n'" + desc + "'"
            return text

    def decorationVisible(self, deco):
        if hasattr(deco, "isVisible"): # added in 3.6
            return deco.isVisible()

        # Workaround for reflection bug in Jython 2.5.1
        args = (None,) if sys.version_info[:3] <= (2, 5, 1) else ()
        method = deco.getClass().getDeclaredMethod("shouldShowDecoration", *args)
        method.setAccessible(True)
        return method.invoke(deco, *args)

    def getPropertyElements(self, item, selected=False):
        elements = []
        decoText = self.getControlDecorationDescription(item)
        if decoText:
            elements.append(decoText)
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
        if hasattr(item, "getItemCount") and hasattr(item, "getExpanded") and item.getItemCount() > 0 and not item.getExpanded():
            elements.append("+")
        return elements

    def getLabelState(self, label):
        if label.getStyle() & swt.SWT.SEPARATOR:
            if label.getStyle() & swt.SWT.VERTICAL:
                return "-" * 5 + "vertical" + "-" * 5
            else:
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

    def getLabelDescription(self, label):
        return self.getAndStoreState(label)
    
    getCLabelDescription = getLabelDescription
    getCLabelState = getLabelState

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

    def getSashDescription(self, widget):
        orientation = "Horizontal"
        if widget.getStyle() & swt.SWT.VERTICAL:
            orientation = "Vertical"
        return "-" * 15 + " " + orientation + " sash " + "-" * 15

    def getLinkDescription(self, widget):
        return self.getAndStoreState(widget)

    def getLinkState(self, widget):
        return "Link '" + widget.getText() + "'"

    def getBrowserDescription(self, widget):
        state = self.getBrowserState(widget)
        self.widgetsWithState[widget] = state
        return self.addHeaderAndFooter(widget, state)

    def getBrowserState(self, widget):
        url = util.getRealUrl(widget)
        # Ignore non-breaking spaces, they are invisible anyway
        # Webkit returns them in invalid format without the semicolons... handle that too.
        rawText = widget.getText().replace(u"\xa0", " ").replace("&nbsp;", " ").replace("&nbsp", " ")
        text = storytext.guishared.encodeToLocale(rawText)
        return url or BrowserHtmlParser().parse(text)
        
    def getUpdatePrefix(self, widget, oldState, state):
        if isinstance(widget, (self.getTextEntryClass(), swt.browser.Browser)):
            return "\nUpdated " + (util.getTextLabel(widget) or "Text") +  " Field\n"
        elif isinstance(widget, swt.widgets.Combo):
            return "\nUpdated " + util.getTextLabel(widget) + " Combo Box\n"
        elif util.getTopControl(widget):
            return "\n"
        elif isinstance(widget, swt.widgets.Menu):
            parentItem = widget.getParentItem()
            menuName = parentItem.getText() if parentItem else "Context"
            return "\nUpdated " + menuName + " Menu:\n"
        elif isinstance(widget, (swt.widgets.Label, swt.custom.CLabel)) and len(state) == 0:
            return "\nLabel now empty, previously " + oldState
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
        desc = self.addHeaderAndFooter(widget, contents)
        return self.combineElements([ desc ] + properties)

    def getComboDescription(self, widget):
        return self.getTextDescription(widget)

    getCComboDescription = getComboDescription
    getCComboState = getComboState

    def getTreeDescription(self, widget):
        return self.getAndStoreState(widget)

    def getTableDescription(self, widget):
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
        if "Menu" not in self.excludeClassNames and not isinstance(widget, swt.widgets.MenuItem) and hasattr(widget, "getMenu") and widget.getMenu():
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
            text += str(GridFormatter(rows, columnCount))
        else:
            text += "\n".join(rows)
        return text

    def getTableState(self, widget):
        columns = widget.getColumns()
        columnCount = len(columns)
        text = self.combineElements([ "Table" ] + self.getPropertyElements(widget)) + " :\n"
        rows = self.getAllTableItemDescriptions(widget, indent=0, 
                                           selection=widget.getSelection(),
                                           columnCount=columnCount)
        headerRow = [ c.getText() for c in columns if c.getWidth() > 0] # Don't show hidden columns
        return text + self.formatTable(headerRow, rows, columnCount)

    def getAllTableItemDescriptions(self, widget, indent=0,
                               prefix="", selection=[], columnCount=0, **kw):
        descs = []
        for item in widget.getItems():
            currPrefix = prefix + " " * indent * 2
            selected = item in selection
            if columnCount:
                row = [ self.getItemColumnDescription(item, i, currPrefix, selected) for i in range(columnCount) if widget.getColumn(i).getWidth() > 0]
                descs.append(row)
        return descs

    def getTabFolderDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        if state:
            return "TabFolder with tabs " + state
        else:
            return "TabFolder with no tabs"

    def getTabFolderState(self, widget):
        return " , ".join(self.getAllItemDescriptions(widget, selection=widget.getSelection()))

    def getCTabFolderState(self, widget):
        return " , ".join(self.getAllItemDescriptions(widget, selection=[ widget.getSelection() ]))

    getCTabFolderDescription = getTabFolderDescription

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
            if isinstance(child, swt.widgets.Sash) and child.getStyle() & swt.SWT.VERTICAL:
                positions.append(child.getLocation().x)
        return sorted(positions)

    def layoutSortsChildren(self, widget):
        layout = widget.getLayout()
        return layout is not None and isinstance(layout, (swt.layout.GridLayout, swt.layout.FillLayout,
                                                          swt.layout.RowLayout, swt.custom.StackLayout))

    def _getDescription(self, widget):
        self.widgetsDescribed.add(widget)
        desc = storytext.guishared.Describer._getDescription(self, widget)
        if desc and isinstance(widget, (swt.widgets.ExpandBar, swt.widgets.Tree, swt.widgets.List)):
            desc = str(desc) + self.formatContextMenuDescriptions()
        return desc

    def getWindowContentDescription(self, shell):
        desc = ""
        desc = self.addToDescription(desc, self.getMenuBarDescription(shell.getMenuBar()))
        desc = self.addToDescription(desc, self.getChildrenDescription(shell))
        desc += self.formatContextMenuDescriptions()
        return desc
    
    def shouldDescribeChildren(self, widget):
        # Composites with StackLayout use the topControl rather than the children
        return storytext.guishared.Describer.shouldDescribeChildren(self, widget) and not util.getTopControl(widget)

    def _getChildrenDescription(self, widget):
        if self.shouldDescribeChildren(widget):
            return self.formatChildrenDescription(widget)
        else:
            self.markDescendantsDescribed(widget)
            return ""

    def markDescendantsDescribed(self, widget):
        if hasattr(widget, self.childrenMethodName):
            self.logger.debug("Mark descendants for " + self.getRawData(widget))
            children = getattr(widget, self.childrenMethodName)()
            self.widgetsDescribed.update(children)
            for child in children:
                self.markDescendantsDescribed(child)
        
    def formatContextMenuDescriptions(self):
        text = ""
        if "Menu" not in self.excludeClassNames:
            for contextMenu, menuId in self.contextMenuCounter.getWidgetsForDescribe():
                menuDesc = self.getMenuDescription(contextMenu)
                text += "\n\nContext Menu " + str(menuId) + ":\n" + menuDesc
                self.widgetsWithState[contextMenu] = self.getMenuState(contextMenu) 
        return text

    def getHorizontalSpan(self, widget, columns):
        layout = widget.getLayoutData()
        if hasattr(layout, "horizontalSpan"):
            return min(layout.horizontalSpan, columns)
        else:
            return 1

    def usesGrid(self, widget):
        return isinstance(widget.getLayout(), swt.layout.GridLayout)

    def getLayoutColumns(self, widget, childCount, *args):
        layout = widget.getLayout()
        if hasattr(layout, "numColumns"):
            return layout.numColumns
        elif hasattr(layout, "type"):
            if layout.type == swt.SWT.HORIZONTAL:
                return childCount
        return 1

    def getRawDataLayoutDetails(self, layout, *args):
        return [ str(layout.numColumns) + " columns" ] if hasattr(layout, "numColumns") else []

    def handleImages(self):
        if self.imageDescriptionType:
            self.buildImages()
    
    def buildImages(self):
        self.buildImagesFromPaths()

    def buildImagesFromPaths(self):
        for path in self.imagePaths:
            self.findFiles(File(path))

    def getImageFiles(self, path):
        d = File(path)
        class Filter(FilenameFilter):
            def accept(lself, d, fileName):#@NoSelf
                return fileName.endswith(".gif") or fileName.endswith(".png") or fileName.endswith(".jpg")

        return d.listFiles(Filter())
    
    def findFiles(self, pathAsFile):
        if pathAsFile.isFile() and self.isImageType(pathAsFile.getName()):
            self.storeImageData(pathAsFile.toURI().toURL())
        elif pathAsFile.isDirectory():
            for f in pathAsFile.listFiles():
                if f is not None:
                    self.findFiles(f)

    def isImageType(self, fileName):
        return fileName.endswith(".gif") or fileName.endswith(".png") or fileName.endswith(".jpg")

    def checkWindow(self, window):
        # Don't describe tooltips
        return (window.getStyle() & swt.SWT.TOOL) == 0
    
    def getStateChangeDescription(self, widget, oldState, state):
        if isinstance(widget, (swt.widgets.Menu, swt.widgets.ToolBar)):
            old = oldState.split("\n")
            new = state.split("\n")
            if len(old) == len(new):
                return self.getDiffedDescription(widget, old, new)
        return storytext.guishared.Describer.getStateChangeDescription(self, widget, oldState, state)

