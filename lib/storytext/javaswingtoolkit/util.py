from java.lang import Runnable, IndexOutOfBoundsException
from javax import swing
import storytext.guishared

def runOnEventDispatchThread(method, *args):
    class EDTRunnable(Runnable):
        def run(self):
            method(*args)
    
    if swing.SwingUtilities.isEventDispatchThread():
        method(*args)
    else:
        swing.SwingUtilities.invokeAndWait(EDTRunnable())
        
class TextLabelFinder(storytext.guishared.TextLabelFinder):
    def getLabelClass(self):
        return swing.JLabel

    def getChildren(self, widget):
        return widget.getComponents()
    
def getTextLabel(widget):
    return TextLabelFinder(widget).find()

       
def getMenuPathString(widget):
    result = [ widget.getText() ]    
    parent = widget.getParent()
    while isinstance(parent, swing.JMenu) or isinstance(parent, swing.JPopupMenu):
        invoker=  parent.getInvoker()
        if isinstance(invoker, swing.JMenu):
            result.append(invoker.getText())
            parent = invoker.getParent()
        else:
            parent = None

    return "|".join(reversed(result)) 

class ComponentTextFinder:
    classesHandled = [ swing.JCheckBox, swing.JTree, swing.JTable, swing.JList, swing.JComboBox, swing.JRadioButton ]
    def __init__(self, widget, describe):
        self.widget = widget
        self.describe = describe
        
    def getComponentTextElements(self, component, index=None):
        for cls in self.classesHandled:
            if isinstance(component, cls):
                textFinder = ComponentTextFinder(component, self.describe)
                return [ getattr(textFinder, "get" + cls.__name__ + "Text")(index) ]
        
        elements = []
        if hasattr(component, "getText"):
            elements.append(component.getText())
        for child in component.getComponents():
            elements += self.getComponentTextElements(child, index)
        return elements    

    def getComponentText(self, *args):
        elements = self.getComponentTextElements(*args)
        if self.describe:
            return "\n".join(elements)
        else:
            return elements[0] if elements else ""

    def getSelectionText(self, selText, unselText):
        text = self.widget.getText()
        if self.describe:
            desc = selText if self.widget.isSelected() else unselText
            return desc + " "  + text if text else desc
        return text

    def getJRadioButtonText(self, *args):
        return self.getSelectionText("(*)", "( )")
    
    def getJCheckBoxText(self, *args):
        return self.getSelectionText("[x]", "[ ]")
    
    def getJToggleButtonText(self, *args):
        text = self.widget.getText()
        if self.describe:
            desc = " (depressed)" if self.widget.isSelected() else ""
            text += desc
        return text

    def getJComboBoxText(self, index):
        value = self.widget.getModel().getElementAt(index) or ""
        renderer = self.widget.getRenderer()
        # Don't check isinstance, any subclasses might be doing all sorts of stuff
        if renderer.__class__ is swing.plaf.basic.BasicComboBoxRenderer.UIResource:
            return value
        # Don't support custom renderer at the moment
        return value
    
    def getJListText(self, index):
        value = self.widget.getModel().getElementAt(index) or ""
        renderer = self.widget.getCellRenderer()
        # Don't check isinstance, any subclasses might be doing all sorts of stuff
        if renderer.__class__ is swing.DefaultListCellRenderer:
            return value

        isSelected = self.widget.isSelectedIndex(index)
        component = renderer.getListCellRendererComponent(self.widget, value, index, isSelected, False)
        return self.getComponentText(component, index)

    def getJTreeTextFromRenderer(self, renderer, rowObj, row):
        if renderer.__class__ is swing.tree.DefaultTreeCellRenderer:
            return str(rowObj)
        
        selected = self.widget.isRowSelected(row)
        expanded = self.widget.isExpanded(row)
        component = renderer.getTreeCellRendererComponent(self.widget, rowObj, selected, expanded, False, row, False)
        return self.getComponentText(component)

    def getJTreeText(self, row):
        path = self.widget.getPathForRow(row)
        if path is None:
            return ""

        rowObj = path.getLastPathComponent()
        renderer = self.widget.getCellRenderer()
        text = self.getJTreeTextFromRenderer(renderer, rowObj, row)
        if self.describe:
            return "-> " + "  " * (path.getPathCount() - 1) + text
        else:
            return text

    def getJTableTextFromRenderer(self, renderer, value, row, col):
        if renderer is None:
            return str(value)

        component = renderer.getTableCellRendererComponent(self.widget, value, False, False, row, col)
        return self.getComponentText(component, row)

    def getJTableText(self, row, col):
        renderer = self.widget.getCellRenderer(row, col)
        try:
            value = self.widget.getValueAt(row, col)
        except IndexOutOfBoundsException:
            # Don't fail here, sometimes row count and column count are inconsistent with what will work here
            return "<unset>"
        return self.getJTableTextFromRenderer(renderer, value, row, col)

    def getJTableHeaderText(self, col):
        column = self.widget.getColumnModel().getColumn(col)
        renderer = column.getHeaderRenderer()
        value = column.getHeaderValue()
        return self.getJTableTextFromRenderer(renderer, value, 0, col)


# Designed to filter out buttons etc which are details of other widgets, such as calendars, scrollbars, tables etc
def hasComplexAncestors(widget):
    if any((swing.SwingUtilities.getAncestorOfClass(widgetClass, widget) is not None
            for widgetClass in [ swing.JTable, swing.JScrollBar, swing.JComboBox, swing.JSpinner ])):
        return True
    
    # If we're in a popup menu that's attached to something with complex ancestors, that's clearly even more complex :)
    popup = swing.SwingUtilities.getAncestorOfClass(swing.JPopupMenu, widget)
    if popup and isinstance(popup.getInvoker(), swing.JComboBox):
        return True
    return popup is not None and hasComplexAncestors(popup.getInvoker())

def belongsMenubar(menuItem):
    parent = menuItem.getParent() if menuItem else None
    while parent is not None:
        if isinstance(parent, swing.JMenuBar):
            return True
        if hasattr(parent, "getInvoker") and parent.getInvoker() is not None:
            if isinstance(parent.getInvoker(), swing.JMenu):
                parent = parent.getInvoker().getParent()
            else:
                parent = parent.getInvoker()
        else:
            parent = None
    return False


def hasPopupMenu(widget):
    return any((isinstance(item, (swing.JPopupMenu)) for item in widget.getComponents()))
