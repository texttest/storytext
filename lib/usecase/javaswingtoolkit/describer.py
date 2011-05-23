import usecase.guishared, logging, util
import java.awt as awt
from javax import swing

class Describer(usecase.guishared.Describer):
    statelessWidgets = [swing.JSplitPane, swing.JRootPane, swing.JLayeredPane, swing.JPanel, swing.JOptionPane, swing.JScrollPane,
                        swing.JViewport, swing.table.JTableHeader, swing.CellRendererPane]
    stateWidgets = [ swing.JButton, swing.JFrame, swing.JMenuBar, swing.JMenu, swing.JMenuItem, swing.JToolBar,
                    swing.JRadioButton, swing.JCheckBox, swing.JTabbedPane, swing.JDialog, swing.JLabel, swing.JPopupMenu,
                    swing.JList, swing.JTable]
# Just as a remainder for all J-widgets we may describe:
#    stateWidgets = [ swing.JButton, swing.JCheckBox, swing.JComboBox, swing.JDialog, swing.JFrame, swing.JInternalFrame,
#                     swing.JLabel, swing.JList, swing.JMenu, swing.JMenuBar, swing.JPanel, swing.JPasswordField, swing.JPopupMenu,
#                     swing.JRadioButton, swing.JTable, swing.JTextArea, swing.JTextField, swing.JToggleButton,
#                     swing.JToolBar, swing.JTree, swing.JWindow]
    def __init__(self):
        usecase.guishared.Describer.__init__(self)
        self.described = []
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
            if not self.parentMarked(parent, markedWidgets):
                markedWidgets.append(parent)
                self.logger.info(header)
                self.logger.info(self.getChildrenDescription(parent))
            elif self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("Not describing " + self.getRawData(widget) + " - marked " + \
                                    repr(map(self.getRawData, markedWidgets)))
   
    def setWidgetShown(self, widget):
        if not isinstance(widget, (swing.Popup, swing.JMenuItem, swing.JScrollBar)) and widget not in self.widgetsAppeared:
            self.widgetsAppeared.append(widget)
              
    def getPropertyElements(self, item, selected=False):
        elements = []
#        Will be used when adding tooltip tests
#        if hasattr(item, "getToolTipText") and item.getToolTipText():
#            elements.append("Tooltip '" + item.getToolTipText() + "'")
        if hasattr(item, "getIcon") and item.getIcon():
            elements.append(self.getImageDescription(item.getIcon()))
        if hasattr(item, "isEnabled") and not item.isEnabled():
            elements.append("greyed out")
        if selected:
            elements.append("selected")
        return elements
    
    def getChildrenDescription(self, widget):
        if not isinstance(widget, awt.Container):
            return ""
        children = widget.getComponents()
        desc = ""
        for child in children:            
            if child not in self.described:
                desc = self.addToDescription(desc, self.getDescription(child))
                self.described.append(child)       
        return desc.rstrip()
        
    def getWindowClasses(self):
        return swing.JFrame, swing.JDialog
    
    def getWindowString(self):
        return "Window"
    
    def getJFrameState(self, window):
        return window.getTitle()
    
    def getJButtonDescription(self, widget):
        if widget.getText() and widget.getText().startswith("ApplicationEvent"):
            return ""
        else:
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
        
    def getJTabbedPaneDescription(self, tabbedpane):
        return "Tabbed Pane:\n" + self.getTabsDescription(tabbedpane)
    
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
        descs = []
        for i in range(pane.getTabCount()):
            descs.append(" '" + pane.getTitleAt(i) + "'")
        return "".join(descs)
    
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
        #TODO: describe the image
        return "Image"
    
    def getJListDescription(self, list):
        self.leaveItemsWithoutDescriptions(list, None, (swing.CellRendererPane,))
        return self.getAndStoreState(list)

    def getJListState(self, widget):
        text = self.combineElements([ "List" ] + self.getPropertyElements(widget)) + " :\n"
        selection = widget.getSelectedValues()
        for i in range(widget.getModel().getSize()):
            item = widget.getModel().getElementAt(i)
            if not item:
                item = ""
            text += "-> " + item
            if item in selection:
                text += " (selected)"
            text += "\n"
        return text    
    
    def getJTableDescription(self, widget):
        return self.getAndStoreState(widget)

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
            self.described.append(item)

    def getAllItemDescriptions(self, itemBar, indent=0, subItemMethod=None,
                               prefix="", selection=[]):
        descs = []
        items = []
        if hasattr(itemBar, "getSubElements"):
            items = itemBar.getSubElements()
        elif hasattr(itemBar, "getComponents"):
            items = itemBar.getComponents()
            
        for item in items:
            currPrefix = prefix + " " * indent * 2
            itemDesc = self.getItemDescription(item, currPrefix, item in selection)
            self.described.append(item)
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
    
    
