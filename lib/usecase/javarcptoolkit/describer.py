
import usecase.guishared
from org.eclipse import swt
        
class Describer(usecase.guishared.Describer):
    def __init__(self):
        self.statelessWidgets = [ swt.widgets.Menu, swt.widgets.Label ]
        self.stateWidgets = [ swt.widgets.Shell ]
        usecase.guishared.Describer.__init__(self)

    def getWindowString(self):
        return "Shell"

    def getShellState(self, shell):
        return shell.getText()

    def isSeparator(self, menuItem):
        return menuItem.getStyle() & swt.SWT.SEPARATOR != 0

    def getMenuDescription(self, menu, indent=0):
        desc = ""
        for item in menu.getItems():
            desc += " " * indent * 2
            if self.isSeparator(item):
                desc += "---"
            else:
                desc += item.getText()
                cascadeMenu = item.getMenu()
                if cascadeMenu is not None:
                    desc += " Menu :\n" + self.getMenuDescription(cascadeMenu, indent + 1).rstrip()
            desc += "\n"
        return desc

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

