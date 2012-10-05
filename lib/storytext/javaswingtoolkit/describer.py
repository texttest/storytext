import storytext.guishared, logging, util, os, inspect
import java.awt as awt
from javax import swing
from itertools import izip

class Describer(storytext.guishared.Describer):
    ignoreWidgets = [ swing.JSplitPane, swing.CellRendererPane, swing.Box.Filler, swing.JRootPane, swing.JLayeredPane,
                      swing.JPanel, swing.JOptionPane, swing.JViewport, swing.table.JTableHeader, swing.JScrollPane, swing.JFileChooser,
                      swing.JScrollBar, swing.plaf.basic.BasicInternalFrameTitlePane, swing.JInternalFrame.JDesktopIcon ]
    ignoreChildren = (swing.JScrollBar, swing.JMenu, swing.JPopupMenu, swing.JMenuBar, swing.JSpinner, swing.JComboBox,
                      swing.JInternalFrame, swing.plaf.basic.BasicInternalFrameTitlePane)
    statelessWidgets = [ swing.plaf.basic.BasicSplitPaneDivider, swing.JInternalFrame, swing.JSeparator ]
    stateWidgets = [ swing.JButton, swing.JFrame, swing.JMenuBar, swing.JMenu, swing.JMenuItem, swing.JToolBar,
                    swing.JRadioButton, swing.JCheckBox, swing.JToggleButton, swing.JTabbedPane, swing.JDialog, swing.JLabel,
                    swing.JList, swing.JTree, swing.JTable, swing.text.JTextComponent, swing.JPopupMenu,
                     swing.JProgressBar, swing.JSpinner, swing.JComboBox ]
    childrenMethodName = "getComponents"
    visibleMethodName = "isVisible"
    def __init__(self):
        storytext.guishared.Describer.__init__(self)
        self.widgetsAppeared = []
        self.tabsDescribed = set()
        
    def describeWithUpdates(self):
        self.logger.debug("Describing with updates...")
        stateChanges = self.findStateChanges()
        stateChangeWidgets = [ widget for widget, old, new in stateChanges ]
        describedForAppearance = self.describeAppearedWidgets(stateChangeWidgets)
        stateChanges = self.describeStateChangeGroups(stateChangeWidgets, stateChanges)
        self.describeStateChanges(stateChanges, describedForAppearance)
        self.widgetsAppeared = []
        self.logger.debug("Finished describing with updates")

    def shouldCheckForUpdates(self, widget, *args):
        return widget.isShowing()
    
    def widgetShowing(self, widget):
        return widget.isShowing()

    def getWidgetToDescribeForAppearance(self, widget, markedWidgets):
        if util.hasPopupMenu(widget):
            return widget
        else:
            return storytext.guishared.Describer.getWidgetToDescribeForAppearance(self, widget, markedWidgets)

    def getDescriptionForVisibilityChange(self, widget):
        if self.shouldDescribeChildren(widget):
            return self.getChildrenDescription(widget)
        else:
            return self.getDescription(widget)
   
    def setWidgetShown(self, widget):
        if not isinstance(widget, (swing.Popup, swing.JScrollBar, swing.table.TableCellRenderer)) and \
               widget not in self.widgetsAppeared:
            self.logger.debug("Widget shown " + self.getRawData(widget))
            self.widgetsAppeared.append(widget)

    def getJSeparatorDescription(self, separator):
        basic = "-" * 15
        if separator.getOrientation() == swing.SwingConstants.VERTICAL:
            return basic + " (vertical)"
        else:
            return basic

    def getPropertyElements(self, item, selected=False):
        elements = []
        if isinstance(item, swing.JSeparator):
            elements.append("---")
        if hasattr(item, "getToolTipText") and item.getToolTipText():
            elements.append("Tooltip '" + item.getToolTipText() + "'")
        if hasattr(item, "getIcon") and item.getIcon():
            elements.append(self.getImageDescription(item.getIcon()))
        if hasattr(item, "getAccelerator") and item.getAccelerator():
            accel = item.getAccelerator().toString().replace(" pressed ", "+").replace("pressed ", "")
            elements.append("Accelerator '" + accel + "'")
        if hasattr(item, "isEnabled") and not item.isEnabled():
            elements.append("greyed out")
        if hasattr(item, "isEditable") and not item.isEditable():
            elements.append("read only")
        if selected:
            elements.append("selected")
        return elements

    def layoutSortsChildren(self, widget):
        return not isinstance(widget, (swing.JScrollPane, swing.JLayeredPane, swing.JSplitPane)) and \
               not isinstance(widget.getLayout(), awt.BorderLayout)

    def getVerticalDividePositions(self, visibleChildren):
        return [] # for now

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
        if isinstance(layout, (awt.FlowLayout, swing.plaf.basic.BasicOptionPaneUI.ButtonAreaLayout)) or \
               isinstance(widget, swing.JToolBar):
            return childCount
        elif isinstance(layout, swing.BoxLayout):
            return childCount if self.isHorizontalBox(layout) else 1
        elif isinstance(layout, awt.BorderLayout):
            positions = [ [ awt.BorderLayout.WEST, awt.BorderLayout.LINE_START ],
                          [ awt.BorderLayout.CENTER ],
                          [ awt.BorderLayout.EAST, awt.BorderLayout.LINE_END ] ]
            return sum((self.hasBorderLayoutComponent(col, layout, sortedChildren) for col in positions))
        elif isinstance(layout, awt.GridLayout):
            # getColumns may return 0 if it was built that way, in which case it means a horizontal row
            return layout.getColumns() or childCount
        elif isinstance(layout, awt.GridBagLayout):
            return max(self.getRowWidths(layout, sortedChildren))
        return 1

    def getRowWidths(self, layout, sortedChildren):
        widths = [0]
        for child in sortedChildren:
            constraints = layout.getConstraints(child)
            widths[-1] += 1
            if constraints.gridwidth == awt.GridBagConstraints.REMAINDER: # end of line
                widths.append(0)
            
        return widths

    def hasBorderLayoutComponent(self, col, layout, sortedChildren):
        return any((layout.getLayoutComponent(pos) in sortedChildren for pos in col))

    def getHorizontalSpan(self, widget, columnCount):
        if isinstance(widget.getParent(), swing.JScrollPane) and widget is widget.getParent().getColumnHeader():
            return 2
        else:
            layout = widget.getParent().getLayout()
            if isinstance(layout, awt.BorderLayout):
                constraints = layout.getConstraints(widget)
                fullWidth = constraints in [ awt.BorderLayout.NORTH, awt.BorderLayout.SOUTH,
                                             awt.BorderLayout.PAGE_START, awt.BorderLayout.PAGE_END ]
                return columnCount if fullWidth else 1
        return 1

    def tryMakeGrid(self, widget, sortedChildren, childDescriptions):
        layout = widget.getLayout()
        if isinstance(layout, awt.GridBagLayout):
            # Only for grid bags that explicitly identify the location of every child in the grid
            grid, columns = self.tryMakeGridBagGrid(widget, sortedChildren, childDescriptions)
            if grid:
                return grid, columns
        return storytext.guishared.Describer.tryMakeGrid(self, widget, sortedChildren, childDescriptions)

    def tryMakeGridBagGrid(self, widget, sortedChildren, childDescriptions):
        layout = widget.getLayout()
        grid = []
        for child, desc in izip(sortedChildren, childDescriptions):
            constraints = layout.getConstraints(child)
            x = constraints.gridx
            y = constraints.gridy
            if x == awt.GridBagConstraints.RELATIVE or y == awt.GridBagConstraints.RELATIVE:
                return None, 0
            while len(grid) <= y:
                grid.append([ "" ])
            while len(grid[y]) <= x:
                grid[y].append("")
            grid[y][x] = unicode(desc)
        return grid, max((len(r) for r in grid))

    def getHorizontalSpans(self, children, columnCount):
        layout = children[0].getParent().getLayout()
        if isinstance(layout, awt.GridBagLayout):
            # If we get this far, it's the kind of GridBagLayout that does everything relative to everything else
            return self.getGridBagSpans(layout, children, columnCount)
        else:
            return storytext.guishared.Describer.getHorizontalSpans(self, children, columnCount)

    def getGridBagSpans(self, layout, children, columnCount):
        spans = []
        rowWidths = self.getRowWidths(layout, children)
        currentRow = 0
        rowSpan = 0
        for child in children:
            constraints = layout.getConstraints(child)
            if constraints.gridwidth == awt.GridBagConstraints.REMAINDER:
                span = columnCount - rowSpan
                currentRow += 1
                rowSpan = 0
            elif constraints.gridwidth == awt.GridBagConstraints.RELATIVE:
                span = 1 + columnCount - rowWidths[currentRow]
                rowSpan += span
            else:
                span = 1
                rowSpan += span
            spans.append(span)
        return spans

    def getWidgetsInRow(self, layout, children, widget):
        widgetIndex = children.index(widget)
        ix = widgetIndex - 1
        while ix > 0:
            constr = layout.getConstraints(children[ix])
            if constr.gridwidth == awt.GridBagConstraints.REMAINDER: # end of line
                break
            else:
                ix -= 1
        return widgetIndex - ix
        
    def getWindowClasses(self):
        return swing.JFrame, swing.JDialog
    
    def getWindowString(self):
        return "Window"
    
    def getJFrameState(self, window):
        return window.getTitle()

    def getJInternalFrameDescription(self, widget):
        header = "-" * 5 + " Internal Frame '" + widget.getTitle() + "' " + "-" * 5
        return header + "\n" + self.formatChildrenDescription(widget) + "\n" + "-" * len(header) + "\n"
    
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
        return self.getAndStoreState(widget)
    
    def getJRadioButtonState(self, widget):
        text = "Radio button: " + util.ComponentTextFinder(widget, describe=True).getJRadioButtonText()
        return self.combineElements([ text ] + self.getPropertyElements(widget))
    
    def getJCheckBoxDescription(self, widget):
        return self.getAndStoreState(widget)
    
    def getJCheckBoxState(self, widget):
        text = "Check box: " + util.ComponentTextFinder(widget, describe=True).getJCheckBoxText()
        return self.combineElements([ text ] + self.getPropertyElements(widget))

    def getJToggleButtonDescription(self, widget):
        return self.getAndStoreState(widget)
    
    def getJToggleButtonState(self, widget):
        text = "Toggle button: " + util.ComponentTextFinder(widget, describe=True).getJToggleButtonText()
        return self.combineElements([ text ] + self.getPropertyElements(widget))
        
    def getJTabbedPaneDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        self.tabsDescribed.update(self.getVisibleDescendants(widget.getSelectedComponent()))
        if state:
            return "TabFolder with tabs " + state
        else:
            return "TabFolder with no tabs"
        
    def getJTabbedPaneState(self, widget):
        return ", ".join(self.getTabsDescription(widget))

    def getVisibleDescendants(self, widget):
        if widget is not None and widget.isVisible():
            descendants = [ widget ]
            if hasattr(widget, "getComponents"):
                for c in widget.getComponents():
                    descendants += self.getVisibleDescendants(c)
            return descendants
        else:
            return []

    def describeChildrenOnStateChange(self, widget):
        if not isinstance(widget, swing.JTabbedPane):
            return True
        
        descendants = self.getVisibleDescendants(widget.getSelectedComponent())
        return not all((widget in self.tabsDescribed for widget in descendants))

    def getStateChangeDescription(self, widget, oldState, state):
        if self.describeChildrenOnStateChange(widget):
            return storytext.guishared.Describer.getStateChangeDescription(self, widget, oldState, state)
        else:
            return self.getUpdatePrefix(widget, oldState, state) + self.getWidgetDescription(widget)

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
            text = storytext.guishared.removeMarkup(label.getText())
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
        return "Popup menu:\n" + self.getJMenuDescription(widget)
    
    def imagesEqual(self, icon1, icon2):
        if hasattr(icon1, "getImage") and hasattr(icon2, "getImage"):
            return icon1.getImage() == icon2.getImage()
        else:
            return storytext.guishared.Describer.imagesEqual(self, icon1, icon2)
    
    def describeStateChangeGroups(self, widgets, stateChanges):
        for widget in widgets:
            if isinstance(widget, swing.JList) and self.isTableRowHeader(widget):
                scrollPane = widget.getParent().getParent()
                table = scrollPane.getViewport().getView()
                if table in widgets:
                    self.logger.info("Updated...\n" + self.getDescription(scrollPane))
                    return filter(lambda (w, x, y): w is not widget and w is not table, stateChanges)
        return stateChanges
                
    def getJListDescription(self, widget):
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
        return None if self.isTableScrollPane(widget) or self.usesGrid(widget) else \
            storytext.guishared.Describer.getMaxDescriptionWidth(self, widget)

    def usesGrid(self, widget):
        return isinstance(widget.getLayout(), (awt.GridLayout, awt.GridBagLayout))

    def getTextComponentText(self, widget):
        text = widget.getText()
        # Don't use getEchoChar for passwords, the character used depends on the theme
        return "*" * len(text) if isinstance(widget, swing.JPasswordField) else text
    
    def getJTextComponentState(self, widget):
        return storytext.guishared.removeMarkup(self.getTextComponentText(widget)), self.getPropertyElements(widget)

    def getClassDescription(self, cls):
        if cls.__name__.startswith("J"):
            return cls.__name__[1:]

        for baseCls in inspect.getmro(cls)[1:]:
            if baseCls.__name__.startswith("J"):
                return baseCls.__name__[1:]
    
    def getJTextComponentDescription(self, widget):
        contents, properties = self.getJTextComponentState(widget)
        return self.getFieldDescription(widget, contents, properties)

    def getFieldDescription(self, widget, contents, properties):
        self.widgetsWithState[widget] = contents, properties
        header = "=" * 10 + " " + self.getClassDescription(widget.__class__) + " " + "=" * 10
        fullHeader = self.combineElements([ header ] + properties)
        return fullHeader + "\n" + self.fixLineEndings(contents.rstrip()) + "\n" + "=" * len(header)

    def getSpinnerProperties(self, spinner):
        model = spinner.getModel()
        if hasattr(model, "getMaximum"):
            return [ "min=" + str(model.getMinimum()), "max=" + str(model.getMaximum()) ]
        else:
            return []

    def getJSpinnerState(self, spinner):
        props = self.getSpinnerProperties(spinner) + self.getPropertyElements(spinner)
        return str(spinner.getValue()), props
        
    def getJSpinnerDescription(self, widget):
        contents, properties = self.getJSpinnerState(widget)
        return self.getFieldDescription(widget, contents, properties)

    def getJComboBoxState(self, widget):
        if widget.isEditable():
            return self.itemToString(widget.getEditor().getItem()), self.getPropertyElements(widget)
        return self.itemToString(widget.getSelectedItem()), self.getPropertyElements(widget)
        
    def itemToString(self, item):
        if hasattr(item, "getDescription"):
            return item.getDescription()
        else:
            return str(item)
        
    def getJComboBoxDescription(self, widget):
        contents, properties = self.getJComboBoxState(widget)
        return self.getFieldDescription(widget, contents, properties)
    
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
        return "\nUpdated " + self.getFieldPrefix(widget)

    def getFieldPrefix(self, widget):
        if isinstance(widget, swing.text.JTextComponent):
            return (util.getTextLabel(widget) or "Text") +  " Field\n"
        elif isinstance(widget, swing.JSpinner):
            return (util.getTextLabel(widget) or "") +  " Spinner\n"
        elif isinstance(widget, swing.JComboBox):
            return (util.getTextLabel(widget) or "") +  " ComboBox\n"
        else:
            return ""
        
    def shouldDescribeChildren(self, widget):
        # Composites with StackLayout use the topControl rather than the children
        return storytext.guishared.Describer.shouldDescribeChildren(self, widget) and \
               (not isinstance(widget, swing.JToolBar) or not self.isNormalToolbar(widget))

    def getAllItemDescriptions(self, itemBar, indent=0, subItemMethod=None,
                               prefix="", selection=[]):
        descs = []
        for item in filter(lambda c: c.isVisible(), itemBar.getComponents()):
            currPrefix = prefix + " " * indent * 2
            itemDesc = self.getItemDescription(item, currPrefix, item in selection)
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
