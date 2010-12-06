
import usecase.guishared, types
from org.eclipse import swt
        
class Describer(usecase.guishared.Describer):
    def __init__(self):
        self.statelessWidgets = [ swt.widgets.Menu, swt.widgets.Label, swt.widgets.ToolBar, swt.widgets.ToolItem, types.NoneType ]
        self.stateWidgets = [ swt.widgets.Shell ]
        usecase.guishared.Describer.__init__(self)

    def getNoneTypeDescription(self, *args):
        return ""

    def getWindowString(self):
        return "Shell"

    def getShellState(self, shell):
        return shell.getText()

    def isSeparator(self, menuItem):
        return menuItem.getStyle() & swt.SWT.SEPARATOR != 0

    def getMenuDescription(self, menu, indent=0):
        return self.getItemBarDescription(menu, indent=indent, subItemMethod=self.getCascadeMenuDescription)

    def getItemBarDescription(self, itemBar, indent=0, subItemMethod=None):
        desc = ""
        for item in itemBar.getItems():
            desc += " " * indent * 2
            if self.isSeparator(item):
                desc += "---"
            else:
                desc += item.getText()
                if subItemMethod:
                    desc += subItemMethod(item, indent)
            desc += "\n"
        return desc

    def getCascadeMenuDescription(self, item, indent):
        cascadeMenu = item.getMenu()
        if cascadeMenu:
            return " Menu :\n" + self.getMenuDescription(cascadeMenu, indent + 1).rstrip()
        else:
            return ""

    def getToolBarDescription(self, toolbar):
        return "Tool Bar:\n" + self.getItemBarDescription(toolbar, indent=1)

    def getToolItemDescription(self, item):
        return item.getText()

    def getLabelDescription(self, label):
        return "'" + label.getText() + "'"
    
    def getWindowContentDescription(self, shell):
        desc = ""
        desc = self.addToDescription(desc, self.getDescription(shell.getMenuBar()))
        return self.addToDescription(desc, self.getChildrenDescription(shell))

    def getChildrenDescription(self, widget, indent=0):
        if not hasattr(widget, "getChildren"):
            return ""
        
        desc = ""
        for child in widget.getChildren():
            desc = self.addToDescription(desc, " " * indent * 2 + self.getDescription(child, indent=indent+1))
        
        return desc.rstrip()

