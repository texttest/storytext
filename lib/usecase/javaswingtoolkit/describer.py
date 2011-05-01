import usecase.guishared, logging
import java.awt as awt
from javax import swing

class Describer(usecase.guishared.Describer):
    statelessWidgets = [swing.JSplitPane, swing.JRootPane, swing.JLayeredPane, swing.JPanel, swing.JOptionPane]
    stateWidgets = [ swing.JButton, swing.JFrame, swing.JMenuBar, swing.JMenu, swing.JMenuItem, swing.JToolBar,
                    swing.JRadioButton, swing.JCheckBox, swing.JTabbedPane, swing.JDialog, swing.JLabel, swing.JPopupMenu]
# Just as a remainder for all J-widgets we may describe:
#    stateWidgets = [ swing.JButton, swing.JCheckBox, swing.JComboBox, swing.JDialog, swing.JFrame, swing.JInternalFrame,
#                     swing.JLabel, swing.JList, swing.JMenu, swing.JMenuBar, swing.JPanel, swing.JPasswordField, swing.JPopupMenu,
#                     swing.JRadioButton, swing.JTable, swing.JTextArea, swing.JTextField, swing.JToggleButton,
#                     swing.JToolBar, swing.JTree, swing.JWindow]
    def __init__(self):
        usecase.guishared.Describer.__init__(self)
        self.widgetsAppeared = []
        self.described = []
        self.diag = logging.getLogger("Swing structure")
     
    def setWidgetShown(self, widget):
        if widget not in self.widgetsAppeared:
            self.widgetsAppeared.append(widget)
      
    def getPropertyElements(self, item, selected=False):
        elements = []
        if hasattr(item, "getToolTipText") and item.getToolTipText():
            elements.append("Tooltip '" + item.getToolTipText() + "'")
        #elements += self.getStyleDescriptions(item)
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
        res = self.getComponentDescription(widget, "JButton")
        return res
    
    def getJButtonState(self, button):
        return self.combineElements(self.getComponentState(button))
        
    def getJMenuDescription(self, menu, indent=1):
        return self.getItemBarDescription(menu, indent=indent, subItemMethod=self.getCascadeMenuDescriptions)
    
    def getJMenuState(self, menu):
        return self.getJMenuDescription(menu, indent=2)
    
    def getJMenuBarDescription(self, menubar):
        if menubar:
            return "Menu Bar:\n" + self.getJMenuDescription(menubar)
        else:
            return ""
    
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
    
    def getJPopupMenuDescription(self, menu):
        return None
    
    def getJPopupMenuState(self, menu):
        return None
    
    def getJDialogState(self, dialog):
        return dialog.getTitle()
    
    def getJLabelDescription(self, label):
        return self.getComponentDescription(label, "JLabel", statemethod=self.getPropertyElements)
    
    def getJLabelState(self, label):
        return self.getComponentState(label)
    
    def getImageDescription(self, image):
        #TODO: describe the image
        return "Image"
    
    def getTextEntryClass(self):
        return awt.TextComponent
    
    def getUpdatePrefix(self, widget, oldState, state):
        return "\nUpdated "
     
    def widgetTypeDescription(self, typeName):
        #skipping java inner classes 
        if typeName.find("$") >= 0:
            return ""
        return "A widget of type '" + typeName + "'" 
    
    #To be moved to super class. TODO: refactoring
    def combineElements(self, elements):
        elements = filter(len, elements)
        if len(elements) <= 1:
            return "".join(elements)
        else:
            return elements[0] + " (" + ", ".join(elements[1:]) + ")"
    
    def getItemDescription(self, item, prefix, *args):
        elements = []
        text = ""
        if hasattr(item, "getText"):
            text = item.getText()
        elif hasattr(item, "getLabel"):
            if item.getLabel():
                text = item.getLabel()
        elements.append(text)
        elements += self.getPropertyElements(item, *args)
        desc = self.combineElements(elements)
        if desc:
            return prefix + desc
        
    def getItemBarDescription(self, *args, **kw):
        return "\n".join(self.getAllItemDescriptions(*args, **kw))

    def getAllItemDescriptions(self, itemBar, indent=0, subItemMethod=None,
                               prefix="", selection=[], columnCount=0):
        descs = []
        items = []
        if hasattr(itemBar, "getItems"):
            items = itemBar.getItems()
        elif hasattr(itemBar, "getSubElements"):
            items = itemBar.getSubElements()
        elif hasattr(itemBar, "getComponents"):
            items = itemBar.getComponents()
            
        for item in items:
            currPrefix = prefix + " " * indent * 2
            itemDesc = self.getItemDescription(item, currPrefix, item in selection)
            self.described.append(item)
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
    