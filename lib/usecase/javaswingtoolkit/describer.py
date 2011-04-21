import usecase.guishared, logging, util
import java.awt as awt
from javax import swing
from java.awt import AWTEvent, Toolkit, Component
from java.awt.event import AWTEventListener, ComponentEvent

class Describer(usecase.guishared.Describer):
    statelessWidgets = [swing.JSplitPane]
    stateWidgets = [ swing.JButton, swing.JFrame, swing.JMenuBar, swing.JMenu, swing.JMenuItem, swing.JToolBar,
                    swing.JRadioButton, swing.JCheckBox, swing.JTabbedPane, swing.JPanel]
#    stateWidgets = [ swing.JButton, swing.JCheckBox, swing.JComboBox, swing.JDialog, swing.JFrame, swing.JInternalFrame,
#                     swing.JLabel, swing.JList, swing.JMenu, swing.JMenuBar, swing.JPanel, swing.JPasswordField, swing.JPopupMenu,
#                     swing.JRadioButton, swing.JTable, swing.JTextArea, swing.JTextField, swing.JToggleButton,
#                     swing.JToolBar, swing.JTree, swing.JWindow]
    def __init__(self):
        usecase.guishared.Describer.__init__(self)
        self.widgetsAppeared = []
        self.diag = logging.getLogger("Swing structure")

    def addFilters(self):
        self.filter = Filter(self)
        self.filter.startListening()
     
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
        #elements.append(self.getContextMenuReference(item))
        return elements
    
    def getChildrenDescription(self, widget):
        if not isinstance(widget, awt.Container):
            return ""
        children = widget.getComponents()
        desc = ""
        #print "PARENT", widget, len(children)
        for child in children:            
            #print "CHILD", child
            desc = self.addToDescription(desc, self.getDescription(child))
        
        return desc.rstrip()
        
    def getWindowClasses(self):
        return swing.JFrame, swing.JDialog
    
    def getWindowString(self):
        return "Window"
    
    def getJFrameState(self, window):
        return window.getTitle()
    
    def getJButtonDescription(self, widget):
        return self.getComponentDescription(widget, "JButton")
    
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
    
    def getJPanelDescription(self, panel):
#        if not panel.getName() or len(panel.getName()) == 0:
#            return "P";
        if len(panel.getComponents())== 0:
            pass
        else:
            return "Panel:\n" + self.getItemBarDescription(panel, indent=1)
        
    def getJTabbedPaneDescription(self, tabbedpane):
        return "Tabbed Pane:\n" + self.getTabsDescription(tabbedpane)
    
    def getComponentState(self, widget):
        return self.getPropertyElements(widget, selected=widget.isSelected())
    
    def getComponentDescription(self, widget, name, statemethod=getComponentState, *args):
        if widget.getText():
            name += " '" + widget.getText() + "'"
        properties = statemethod(self, widget, *args)
        self.widgetsWithState[widget] = properties
        elements = [ name ] + properties 
        return self.combineElements(elements)
    
    def getTabsDescription(self, pane):
        descs = []
        for i in range(pane.getTabCount()):
            descs.append(" '" + pane.getTitleAt(i) + "'")
            #comp = pane.getTabComponentAt(i)
            #properties = self.getPropertyElements(comp, selected=False)
            #self.widgetsWithState[comp] = properties
        return "".join(descs)
    
    #To be moved to super class
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
    
class Filter():
    logger = None
    eventListener = None
    def __init__(self, describer):
        self.describer = describer
        Filter.logger = logging.getLogger("usecase record")
        
    def startListening(self):
        eventMask = AWTEvent.COMPONENT_EVENT_MASK
        #| AWTEvent.WINDOW_EVENT_MASK | AWTEvent.COMPONENT_EVENT_MASK | AWTEvent.ACTION_EVENT_MASK
        #| AWTEvent.ITEM_EVENT_MASK | AWTEvent.INPUT_METHOD_EVENT_MASk
        class AllEventListener(AWTEventListener):
            def eventDispatched(listenerSelf, event):
                self.handleEvent(event)
        
        self.eventListener = AllEventListener()
        util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().addAWTEventListener, self.eventListener, eventMask)
    
    @classmethod
    def stopListening(cls):
        util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().removeAWTEventListener, cls.eventListener)
            
    def handleEvent(self, event):
        if isinstance(event.getSource(), Component):
            if isinstance(event, ComponentEvent) and event.getID() == ComponentEvent.COMPONENT_SHOWN:
                self.describer.setWidgetShown(event.getSource)
            
            