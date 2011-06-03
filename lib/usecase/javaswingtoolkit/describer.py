import usecase.guishared, logging, util, os
import java.awt as awt
from javax import swing

class Describer(usecase.guishared.Describer):
    statelessWidgets = [swing.JSplitPane, swing.JRootPane, swing.JLayeredPane, swing.JPanel, swing.JOptionPane, swing.JScrollPane,
                        swing.JViewport, swing.table.JTableHeader, swing.CellRendererPane, swing.Box.Filler ]
    stateWidgets = [ swing.JButton, swing.JFrame, swing.JMenuBar, swing.JMenu, swing.JMenuItem, swing.JToolBar,
                    swing.JRadioButton, swing.JCheckBox, swing.JTabbedPane, swing.JDialog, swing.JLabel, swing.JPopupMenu,
                    swing.JList, swing.JTable, swing.text.JTextComponent]
# Just as a remainder for all J-widgets we may describe:
#    stateWidgets = [ swing.JButton, swing.JCheckBox, swing.JComboBox, swing.JDialog, swing.JFrame, swing.JInternalFrame,
#                     swing.JLabel, swing.JList, swing.JMenu, swing.JMenuBar, swing.JPanel, swing.JPasswordField, swing.JPopupMenu,
#                     swing.JRadioButton, swing.JTable, swing.JTextArea, swing.JTextComponent, swing.JToggleButton,
#                     swing.JToolBar, swing.JTree, swing.JWindow]
    def __init__(self):
        usecase.guishared.Describer.__init__(self)
        self.described = set()
        self.widgetsAppeared = []
    
    def describe(self, window):
        if self.structureLogger.isEnabledFor(logging.DEBUG) and window not in self.windows:
            self.describeStructure(window)
        usecase.guishared.Describer.describe(self, window)
    
    def describeWithUpdates(self):
        stateChanges = self.findStateChanges()
        stateChangeWidgets = [ widget for widget, old, new in stateChanges ]
        self.describeAppearedWidgets(stateChangeWidgets)
        self.describeStateChanges(stateChanges)
        self.widgetsAppeared = []

    def shouldCheckForUpdates(self, widget, *args):
        return widget.isShowing()
    
    def describeAppearedWidgets(self, stateChangeWidgets):
        markedWidgets = self.widgetsAppeared + stateChangeWidgets
        for widget in self.widgetsAppeared:
            self.describeVisibilityChange(widget, markedWidgets, "New widgets have appeared: describing common parent :\n")
    
    def parentMarked(self, widget, markedWidgets):
        if widget in markedWidgets:
            return True
        elif isinstance(widget, awt.Component) and widget.getParent():
            return self.parentMarked(widget.getParent(), markedWidgets)
        else:
            return False

    def describeVisibilityChange(self, widget, markedWidgets, header):
        if hasattr(widget, "isVisible") and not widget.isVisible():
            return
        if isinstance(widget, (swing.JFrame, swing.JDialog)):
            self.describe(widget)
        else:
            parent = widget.getParent()
            if parent is not None and not self.parentMarked(parent, markedWidgets):
                markedWidgets.append(parent)
                self.logger.info("\n" + header)
                self.logger.info(self.getDescriptionForVisibilityChange(parent))
            elif self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("Not describing " + self.getRawData(widget) + " - marked " + \
                                    repr(map(self.getRawData, markedWidgets)))

    def getDescriptionForVisibilityChange(self, widget):
        if isinstance(widget, (swing.JToolBar, swing.JMenuBar)):
            return self.getDescription(widget)
        else:
            return self.getChildrenDescription(widget)
   
    def setWidgetShown(self, widget):
        if not isinstance(widget, (swing.Popup, swing.JScrollBar)) and widget not in self.widgetsAppeared:
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
        return not isinstance(widget, (swing.JScrollPane, swing.JLayeredPane)) and \
               not isinstance(widget.getLayout(), (awt.BorderLayout))

    def getVerticalDividePositions(self, visibleChildren):
        return [] # for now
    
    def getChildrenDescription(self, widget):
        if not isinstance(widget, awt.Container):
            return ""

        visibleChildren = filter(lambda c: c.isVisible() and c not in self.described, widget.getComponents())
        self.described.update(visibleChildren)
        return self.formatChildrenDescription(widget, visibleChildren)

    def hasDescriptionForChild(self, child, childDescriptions, sortedChildren):
        return child is not None and len(childDescriptions[sortedChildren.index(child)]) > 0

    def getLayoutColumns(self, widget, childDescriptions, sortedChildren):
        if len(childDescriptions) > 1:
            if isinstance(widget, swing.JScrollPane) and widget.getRowHeader() is not None:
                return 2
            layout = widget.getLayout()
            if isinstance(layout, awt.FlowLayout):
                return len(childDescriptions)
            elif isinstance(layout, awt.BorderLayout):
                columns = 1
                for pos in [ awt.BorderLayout.WEST, awt.BorderLayout.EAST,
                             awt.BorderLayout.LINE_START, awt.BorderLayout.LINE_END ]:
                    child = layout.getLayoutComponent(pos)
                    if self.hasDescriptionForChild(child, childDescriptions, sortedChildren):
                        columns += 1
                return columns
        return 1

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
        return self.getComponentDescription(widget, "JButton")

    def getJButtonState(self, button):
        return self.combineElements(self.getComponentState(button))
        
    def getJMenuDescription(self, menu, indent=1):
        return self.getItemBarDescription(menu, indent=indent, subItemMethod=self.getCascadeMenuDescriptions)
    
    def getJMenuBarDescription(self, menubar):
        return "Menu Bar:\n" + self.getJMenuDescription(menubar)
    
    def getJToolBarDescription(self, toolbar, indent=1):
        return "Tool Bar:\n" + self.getItemBarDescription(toolbar, indent=indent)
    
    def getJRadioButtonDescription(self, widget):
        return self.getComponentDescription(widget, "JRadioButton")
    
    def getJCheckBoxDescription(self, widget):
        return self.getComponentDescription(widget, "JCheckBox")
        
    def getJTabbedPaneDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        if state:
            return "TabFolder with tabs " + state
        else:
            return "TabFolder with no tabs"
        
        #return "Tabbed Pane:\n" + self.getTabsDescription(tabbedpane)
    
    def getJTabbedPaneState(self, widget):
        #return self.getTabsDescription(widget)
        return ", ".join(self.getTabsDescription(widget))

    def getComponentState(self, widget):
        return self.getPropertyElements(widget, selected=widget.isSelected())
    
    def getComponentDescription(self, widget, name, statemethod=None, *args):
        if widget.getText():
            name += " '" + widget.getText() + "'"
        
        if statemethod:
            properties = statemethod(widget, *args)
        else:
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
            if pane.getSelectedIndex() == i:
                desc.append("selected")
            result += [self.combineElements(desc)]
        return result

    def getBoxFillerDescription(self, filler):
        return None
    
    def getJRootPaneDescription(self, pane):
        return None
    
    def getJLayeredPaneDescription(self, pane):
        return None
    
    def getJPanelDescription(self, panel):
        return None
    
    def getJOptionPaneDescription(self, pane):
        return None
    
    def getJPopupMenuState(self, menu):
        return None
    
    def getJScrollPaneDescription(self, pane):
        self.leaveItemsWithoutDescriptions(pane, [pane.getVerticalScrollBar(), pane.getHorizontalScrollBar()])
        return None
    
    def getJViewportDescription(self, viewport):
        return None
    
    def getJTableHeaderDescription(self, widget):
        return None
    
    def getCellRendererPaneDescription(self, widget):
        return None

    def getJDialogState(self, dialog):
        return dialog.getTitle()
    
    def getJLabelDescription(self, label):
        return self.getAndStoreState(label)

    def getJLabelState(self, label):
        elements = []
        if label.getText() and len(label.getText()) > 0:
            elements.append("'" + label.getText() + "'")
        else:
            elements.append("JLabel")
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

    def imagesEqual(self, icon1, icon2):
        if hasattr(icon1, "getImage") and hasattr(icon2, "getImage"):
            return icon1.getImage() == icon2.getImage()
        else:
            return usecase.guishared.Describer.imagesEqual(self, icon1, icon2)
        
    def getJListDescription(self, list):
        self.leaveItemsWithoutDescriptions(list, None, (swing.CellRendererPane,))
        return self.getAndStoreState(list)

    def isTableRowHeader(self, widget):
        # viewport, then scroll pane...
        scrollPane = widget.getParent().getParent()
        return isinstance(scrollPane, swing.JScrollPane) and scrollPane.getRowHeader() is not None and \
               scrollPane.getRowHeader().getView() is widget and isinstance(scrollPane.getViewport().getView(), swing.JTable)

    def getJListState(self, widget):
        text = self.combineElements([ "List" ] + self.getPropertyElements(widget)) + " :\n"
        if self.isTableRowHeader(widget):
            text += "\n\n\n" # line it up with the table...
        for i in range(widget.getModel().getSize()):
            value = util.getJListText(widget, i)
            isSelected = widget.isSelectedIndex(i)
            text += "-> " + value
            if isSelected:
                text += " (selected)"
            text += "\n"
        return text    
    
    def getJTableDescription(self, widget):
        return self.getAndStoreState(widget)
    
    def getJTextComponentState(self, widget):
        return usecase.guishared.removeMarkup(widget.getText()), self.getPropertyElements(widget)
    
    def getJTextComponentDescription(self, widget):
        contents, properties = self.getJTextComponentState(widget)
        self.widgetsWithState[widget] = contents, properties
        header = "=" * 10 + " " + widget.__class__.__name__ + " " + "=" * 10
        fullHeader = self.combineElements([ header ] + properties)
        return fullHeader + "\n" + self.fixLineEndings(contents.rstrip()) + "\n" + "=" * len(header)

    def getState(self, widget):
        return self.getSpecificState(widget)
        
    def getCellText(self, i, j, table, selectedRows, selectedColumns):
        if i < 0:
            return table.getColumnName(j)
        
        cellText = str(table.getValueAt(i, j))
        if i in selectedRows and j in selectedColumns:
            cellText += " (selected)"
        return cellText

    def getJTableState(self, table):
        selectedRows = table.getSelectedRows()
        selectedColumns = table.getSelectedColumns()
        columnCount = table.getColumnCount()

        args = table, selectedRows, selectedColumns
        rows = [ [ self.getCellText(i, j, *args) for j in range(columnCount) ] for i in range(-1, table.getRowCount()) ]

        text = self.combineElements([ "Table" ] + self.getPropertyElements(table)) + " :\n"
        return text + self.formatTable(rows, columnCount)

    def getUpdatePrefix(self, widget, oldState, state):
        if isinstance(widget, swing.text.JTextComponent):
            return "\nUpdated " + (util.getTextLabel(widget) or "Text") +  " Field\n"
        else:
            return "\nUpdated "

    def leaveItemsWithoutDescriptions(self, itemContainer, skippedObjects=[], skippedClasses=()):
        items = []
        if hasattr(itemContainer, "getSubElements"):
            items = itemContainer.getSubElements()
        elif hasattr(itemContainer, "getComponents"):
            items = itemContainer.getComponents()
        
        for item in items:
            if skippedObjects and not item in skippedObjects or \
            skippedClasses and not isinstance(item, skippedClasses):
                continue
            self.described.add(item)

    def getAllItemDescriptions(self, itemBar, indent=0, subItemMethod=None,
                               prefix="", selection=[]):
        descs = []
        items = []
        if hasattr(itemBar, "getMenuComponents"):
            items = itemBar.getMenuComponents()
        elif hasattr(itemBar, "getComponents"):
            items = itemBar.getComponents()

        for item in filter(lambda c: c.isVisible(), items):
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
    
    def getTabComponentsDescriptions(self, component, indent=0, **kw):
        return self.getAllItemDescriptions(component, indent+1, subItemMethod=self.getTabComponentsDescriptions, **kw)
    
