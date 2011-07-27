import usecase.guishared, logging, util, os, inspect
import java.awt as awt
from javax import swing

class Describer(usecase.guishared.Describer):
    ignoreWidgets = [ swing.JSplitPane, swing.CellRendererPane, swing.Box.Filler, swing.JRootPane, swing.JLayeredPane,
                      swing.JPanel, swing.JOptionPane, swing.JViewport, swing.table.JTableHeader, swing.JScrollPane ]
    statelessWidgets = [swing.JScrollBar, swing.plaf.basic.BasicSplitPaneDivider ]
    stateWidgets = [ swing.JButton, swing.JFrame, swing.JMenuBar, swing.JMenu, swing.JMenuItem, swing.JToolBar,
                    swing.JRadioButton, swing.JCheckBox, swing.JTabbedPane, swing.JDialog, swing.JLabel,
                    swing.JList, swing.JTree, swing.JTable, swing.text.JTextComponent, swing.JPopupMenu, swing.JProgressBar]
    childrenMethodName = "getComponents"
    visibleMethodName = "isVisible"
    def __init__(self):
        usecase.guishared.Describer.__init__(self)
        self.described = set()
        self.widgetsAppeared = []
        
    def describeWithUpdates(self):
        stateChanges = self.findStateChanges()
        stateChangeWidgets = [ widget for widget, old, new in stateChanges ]
        self.describeAppearedWidgets(stateChangeWidgets)
        stateChanges = self.describeStateChangeGroups(stateChangeWidgets, stateChanges)
        self.describeStateChanges(stateChanges)
        self.widgetsAppeared = []

    def shouldCheckForUpdates(self, widget, *args):
        return widget.isShowing()
    
    def describeAppearedWidgets(self, stateChangeWidgets):
        newWindows, commonParents = self.categoriseAppearedWidgets(stateChangeWidgets)
        for window in newWindows:
            self.describe(window)
        descriptions = map(self.getDescriptionForVisibilityChange, commonParents)
        for desc in sorted(descriptions):
            self.logger.info("\nNew widgets have appeared: describing common parent :\n")
            self.logger.info(desc)
    
    def getMarkedAncestor(self, widget, markedWidgets):
        if widget in markedWidgets:
            return widget
        elif widget.getParent():
            return self.getMarkedAncestor(widget.getParent(), markedWidgets)

    def categoriseAppearedWidgets(self, stateChangeWidgets):
        newWindows, commonParents = [], []
        markedWidgets = self.widgetsAppeared + stateChangeWidgets
        for widget in self.widgetsAppeared:
            if not widget.isVisible():
                continue
            elif isinstance(widget, self.getWindowClasses()):
                newWindows.append(widget)
            elif util.hasPopupMenu(widget):
                markedWidgets.append(widget)
                commonParents.append(widget)
            else:
                parent = widget.getParent()
                if parent is not None:
                    markedAncestor = self.getMarkedAncestor(parent, markedWidgets)
                    if markedAncestor:
                        self.clearDescribedStatus(parent, markedAncestor)
                        if self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug("Not describing " + self.getRawData(widget) + " - marked " +
                                              self.getRawData(markedAncestor))
                    else:
                        markedWidgets.append(parent)
                        commonParents.append(parent)
                
        return newWindows, commonParents

    def clearDescribedStatus(self, widget, ancestor):
        if widget in self.described:
            self.described.remove(widget)
        parent = widget.getParent()
        if parent and parent is not ancestor:
            self.clearDescribedStatus(parent, ancestor)

    def getDescriptionForVisibilityChange(self, widget):
        if isinstance(widget, swing.JMenuBar) or \
               (isinstance(widget, swing.JToolBar) and self.isNormalToolbar(widget)):
            return self.getDescription(widget)
        else:
            return self.getChildrenDescription(widget, checkPrevious=False)
   
    def setWidgetShown(self, widget):
        if not isinstance(widget, (swing.Popup, swing.JScrollBar, swing.table.TableCellRenderer)) and \
               widget not in self.widgetsAppeared:
            self.logger.debug("Widget shown " + self.getRawData(widget))
            self.widgetsAppeared.append(widget)
              
    def getPropertyElements(self, item, selected=False):
        elements = []
        if isinstance(item, swing.JSeparator):
            elements.append("---")
        if hasattr(item, "getToolTipText") and item.getToolTipText():
            elements.append("Tooltip '" + item.getToolTipText() + "'")
        if hasattr(item, "getIcon") and item.getIcon():
            elements.append(self.getImageDescription(item.getIcon()))
        if hasattr(item, "getAccelerator") and item.getAccelerator():
            accel = item.getAccelerator().toString().replace(" pressed ", "+")
            elements.append("Accelerator '" + accel + "'")
        if hasattr(item, "isEnabled") and not item.isEnabled():
            elements.append("greyed out")
        if selected:
            elements.append("selected")
        return elements

    def layoutSortsChildren(self, widget):
        return not isinstance(widget, (swing.JScrollPane, swing.JLayeredPane, swing.JSplitPane)) and \
               not isinstance(widget.getLayout(), (awt.BorderLayout))

    def getVerticalDividePositions(self, visibleChildren):
        return [] # for now

    def shouldDescribeChild(self, child, checkPrevious):
        return child.isVisible() and (not checkPrevious or child not in self.described)
    
    def _getChildrenDescription(self, widget, checkPrevious=True):
        if not isinstance(widget, awt.Container):
            return ""

        visibleChildren = filter(lambda c: self.shouldDescribeChild(c, checkPrevious), widget.getComponents())
        self.described.update(visibleChildren)
        return self.formatChildrenDescription(widget, visibleChildren)

    def isHorizontalBox(self, layout):
        # There is no way to ask a layout for its orientation - very strange
        # So we hack around the access priveleges. If you know a better way, please improve this!
        field = layout.getClass().getDeclaredField("axis")
        field.setAccessible(True) 
        return field.get(layout) in [ swing.BoxLayout.X_AXIS, swing.BoxLayout.LINE_AXIS ]

    def getLayoutColumns(self, widget, childCount, sortedChildren):
        if isinstance(widget, swing.JScrollPane) and widget.getRowHeader() is not None:
            return 2
        layout = widget.getLayout()
        if isinstance(layout, awt.FlowLayout) or isinstance(widget, swing.JToolBar):
            return childCount
        elif isinstance(layout, swing.BoxLayout):
            return childCount if self.isHorizontalBox(layout) else 1
        elif isinstance(layout, awt.BorderLayout):
            positions = [ [ awt.BorderLayout.WEST, awt.BorderLayout.LINE_START ],
                          [ awt.BorderLayout.NORTH, awt.BorderLayout.PAGE_START,
                            awt.BorderLayout.CENTER,
                            awt.BorderLayout.SOUTH, awt.BorderLayout.PAGE_END ],
                          [ awt.BorderLayout.EAST, awt.BorderLayout.LINE_END ] ]
            return sum((self.hasBorderLayoutComponent(col, layout, sortedChildren) for col in positions))
        return 1

    def hasBorderLayoutComponent(self, col, layout, sortedChildren):
        return any((layout.getLayoutComponent(pos) in sortedChildren for pos in col))

    def getHorizontalSpan(self, widget, columnCount):
        if isinstance(widget.getParent(), swing.JScrollPane) and widget is widget.getParent().getColumnHeader():
            return 2
        elif isinstance(widget.getParent().getLayout(), awt.BorderLayout):
            constraints = widget.getParent().getLayout().getConstraints(widget)
            fullWidth = constraints in [ awt.BorderLayout.NORTH, awt.BorderLayout.SOUTH,
                                         awt.BorderLayout.PAGE_START, awt.BorderLayout.PAGE_END ]
            return columnCount if fullWidth else 1
        else:
            return 1
        
    def getWindowClasses(self):
        return swing.JFrame, swing.JDialog
    
    def getWindowString(self):
        return "Window"
    
    def getJFrameState(self, window):
        return window.getTitle()
    
    def getJButtonDescription(self, widget):
        return self.getComponentDescription(widget, "Button")

    def getJButtonState(self, button):
        return self.combineElements(self.getComponentState(button))
        
    def getJMenuDescription(self, menu, indent=1):
        return self.getItemBarDescription(menu, indent=indent, subItemMethod=self.getCascadeMenuDescriptions)
    
    def getJMenuBarDescription(self, menubar):
        return "Menu Bar:\n" + self.getJMenuDescription(menubar)

    def isNormalToolbar(self, toolbar):
        return all((isinstance(item, (swing.JButton, swing.JSeparator)) for item in toolbar.getComponents()))
            
    def getJToolBarDescription(self, toolbar, indent=1):
        if self.isNormalToolbar(toolbar):
            return "Tool Bar:\n" + self.getItemBarDescription(toolbar, indent=indent)
        else:
            return ""

    def getBasicSplitPaneDividerDescription(self, divider):
        # Note: orientation of the divider is the opposite of the orientation of the split pane...
        orientation = "Vertical"
        if divider.getParent().getOrientation() == swing.JSplitPane.VERTICAL_SPLIT:
            orientation = "Horizontal"
        return "-" * 15 + " " + orientation + " divider " + "-" * 15
    
    def getJRadioButtonDescription(self, widget):
        return self.getComponentDescription(widget, "RadioButton")
    
    def getJCheckBoxDescription(self, widget):
        return self.getComponentDescription(widget, "CheckBox")
        
    def getJTabbedPaneDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        if state:
            return "TabFolder with tabs " + state
        else:
            return "TabFolder with no tabs"
        
    def getJTabbedPaneState(self, widget):
        return ", ".join(self.getTabsDescription(widget))

    def getComponentState(self, widget):
        return self.getPropertyElements(widget, selected=widget.isSelected())
    
    def getComponentDescription(self, widget, name):
        if widget.getText():
            name += " '" + widget.getText() + "'"
        
        properties = self.getComponentState(widget)
        self.widgetsWithState[widget] = self.combineElements(properties)
        elements = [ name ] + properties 
        return self.combineElements(elements)

    def getTabsDescription(self, pane):        
        result = []
        for i in range(pane.getTabCount()):
            desc = []
            desc.append(pane.getTitleAt(i))
            if pane.getToolTipTextAt(i):
                desc.append(pane.getToolTipTextAt(i))
            if pane.getIconAt(i):
                desc.append(self.getImageDescription(pane.getIconAt(i)))
            if not pane.isEnabledAt(i):
                desc.append("greyed out")
            if pane.getSelectedIndex() == i:
                desc.append("selected")
            result += [self.combineElements(desc)]
        return result

    def getJScrollBarDescription(self, bar):
        self.leaveItemsWithoutDescriptions(bar, bar.getComponents())
    
    def getJDialogState(self, dialog):
        return dialog.getTitle()
    
    def getJLabelDescription(self, widget):
        return self.getAndStoreState(widget)

    def getJTreeDescription(self, widget):
        return self.getAndStoreState(widget)

    def getJTableDescription(self, widget):
        return self.getAndStoreState(widget)

    def getJProgressBarDescription(self, widget):
        return self.getAndStoreState(widget)

    def getJProgressBarState(self, widget):
        return "Progress Bar"

    def getJLabelState(self, label):
        elements = []
        if label.getText():
            text = usecase.guishared.removeMarkup(label.getText())
            if text:
                elements.append("'" + text + "'")
        if label.getIcon():
            elements.append(self.getImageDescription(label.getIcon()))
        return self.combineElements(elements)
    
    def getImageDescription(self, image):
        if hasattr(image, "getDescription") and image.getDescription():
            desc = image.getDescription()
            if "file:" in desc:
                desc = os.path.basename(desc.split("file:")[-1])
            return "Icon '" + desc + "'"
        else:
            return "Image " + self.imageCounter.getId(image)

    def getJPopupMenuDescription(self, widget):
        self.resetDescribedFlags(widget)
        return "Popup menu:\n" + self.getJMenuDescription(widget)
    
    def imagesEqual(self, icon1, icon2):
        if hasattr(icon1, "getImage") and hasattr(icon2, "getImage"):
            return icon1.getImage() == icon2.getImage()
        else:
            return usecase.guishared.Describer.imagesEqual(self, icon1, icon2)

    def resetDescribedFlags(self, widget):
        if widget in self.described:
            self.described.remove(widget)
        for child in widget.getComponents():
            self.resetDescribedFlags(child)
    
    def describeStateChangeGroups(self, widgets, stateChanges):
        for widget in widgets:
            if isinstance(widget, swing.JList) and self.isTableRowHeader(widget):
                scrollPane = widget.getParent().getParent()
                table = scrollPane.getViewport().getView()
                if table in widgets:
                    self.resetDescribedFlags(scrollPane)
                    self.logger.info("Updated...\n" + self.getDescription(scrollPane))
                    return filter(lambda (w, x, y): w is not widget and w is not table, stateChanges)
        return stateChanges
                
    def getJListDescription(self, widget):
        self.leaveItemsWithoutDescriptions(widget, skippedClasses=(swing.CellRendererPane,))
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        if self.isTableRowHeader(widget):
            return state.replace("\n", "\n" * self.getTableHeaderLength(widget), 1) # line it up with the table...
        else:
            return state

    def getTableHeaderLength(self, tableHeader):
        return 4

    def getJListState(self, widget):
        text = self.combineElements([ "List" ] + self.getPropertyElements(widget)) + " :\n"
        for i in range(widget.getModel().getSize()):
            value = util.ComponentTextFinder(widget, describe=True).getJListText(i)
            isSelected = widget.isSelectedIndex(i)
            text += "-> " + value
            if isSelected:
                text += " (selected)"
            text += "\n"
        return text

    def isTableRowHeader(self, widget):
        # viewport, then scroll pane...
        scrollPane = widget.getParent().getParent()
        return isinstance(scrollPane, swing.JScrollPane) and scrollPane.getRowHeader() is not None and \
               scrollPane.getRowHeader().getView() is widget and isinstance(scrollPane.getViewport().getView(), swing.JTable)

    def isTableScrollPane(self, scrollPane):
        return isinstance(scrollPane, swing.JScrollPane) and scrollPane.getRowHeader() is not None and \
               isinstance(scrollPane.getRowHeader().getView(), swing.JList) and \
               isinstance(scrollPane.getViewport().getView(), swing.JTable)

    def getMaxDescriptionWidth(self, widget):
        return None if self.isTableScrollPane(widget) else 130
    
    def getJTextComponentState(self, widget):
        return usecase.guishared.removeMarkup(widget.getText()), self.getPropertyElements(widget)

    def getClassDescription(self, cls):
        if cls.__name__.startswith("J"):
            return cls.__name__[1:]

        for baseCls in inspect.getmro(cls)[1:]:
            if baseCls.__name__.startswith("J"):
                return baseCls.__name__[1:]
    
    def getJTextComponentDescription(self, widget):
        contents, properties = self.getJTextComponentState(widget)
        self.widgetsWithState[widget] = contents, properties
        header = "=" * 10 + " " + self.getClassDescription(widget.__class__) + " " + "=" * 10
        fullHeader = self.combineElements([ header ] + properties)
        return fullHeader + "\n" + self.fixLineEndings(contents.rstrip()) + "\n" + "=" * len(header)

    def getState(self, widget):
        return self.getSpecificState(widget)
        
    def getFullCellText(self, i, j, textFinder, selectedRows, selectedColumns):
        return textFinder.getJTableText(i, j) + self.getSelectionText(i in selectedRows and j in selectedColumns)

    def getSelectionText(self, selected):
        return " (selected)" if selected else ""

    def getTreeRowText(self, i, textFinder, selectedRows):
        return textFinder.getJTreeText(i) + self.getSelectionText(i in selectedRows)

    def getJTableState(self, table):
        selectedRows = table.getSelectedRows()
        selectedColumns = table.getSelectedColumns()
        columnCount = table.getColumnCount()

        textFinder = util.ComponentTextFinder(table, describe=True)
        headerRow = map(textFinder.getJTableHeaderText, range(columnCount))
        args = textFinder, selectedRows, selectedColumns
        rows = [ [ self.getFullCellText(i, j, *args) for j in range(columnCount) ] for i in range(table.getRowCount()) ]

        text = self.combineElements([ "Table" ] + self.getPropertyElements(table)) + " :\n"
        return text + self.formatTable(headerRow, rows, columnCount)

    def getJTreeState(self, tree):
        selectedRows = tree.getSelectionRows() or []
        rowCount = tree.getRowCount()
        textFinder = util.ComponentTextFinder(tree, describe=True)
        rows = [ self.getTreeRowText(i, textFinder, selectedRows)  for i in range(rowCount) ]
        text = self.combineElements([ "Tree" ] + self.getPropertyElements(tree)) + " :\n"
        return text + "\n".join(rows)
    
    def getUpdatePrefix(self, widget, oldState, state):
        if isinstance(widget, swing.text.JTextComponent):
            return "\nUpdated " + (util.getTextLabel(widget) or "Text") +  " Field\n"
        else:
            return "\nUpdated "

    def leaveItemsWithoutDescriptions(self, itemContainer, skippedObjects=[], skippedClasses=()):
        for item in itemContainer.getComponents():
            if item in skippedObjects or isinstance(item, skippedClasses):
                self.described.add(item)

    def getAllItemDescriptions(self, itemBar, indent=0, subItemMethod=None,
                               prefix="", selection=[]):
        descs = []
        for item in filter(lambda c: c.isVisible(), itemBar.getComponents()):
            currPrefix = prefix + " " * indent * 2
            itemDesc = self.getItemDescription(item, currPrefix, item in selection)
            self.described.add(item)
            if itemDesc:
                descs.append(itemDesc)
            if subItemMethod:
                descs += subItemMethod(item, indent, prefix=prefix, selection=selection)
        return descs

    def getCascadeMenuDescriptions(self, item, indent, **kw):
        cascadeMenu = None
        if isinstance(item, swing.JMenu):
            cascadeMenu = item.getPopupMenu()
        if cascadeMenu:
            descs = self.getAllItemDescriptions(cascadeMenu, indent+1, subItemMethod=self.getCascadeMenuDescriptions, **kw)
            if indent == 1:
                self.widgetsWithState[cascadeMenu] = "\n".join(descs)
            return descs
        else:
            return []

    def getRawDataLayoutDetails(self, layout, widget):
        if hasattr(layout, "getConstraints"):
            return [ str(layout.getConstraints(child)) for child in widget.getComponents() ]
        else:
            return []
