
import usecase.guishared, types
from org.eclipse import swt
        
class Describer(usecase.guishared.Describer):
    styleNames = [ "PUSH", "SEPARATOR", "DROP_DOWN", "CHECK", "CASCADE", "RADIO" ]
    def __init__(self):
        self.statelessWidgets = [ swt.widgets.Label, swt.widgets.Text, swt.widgets.Tree,
                                  swt.widgets.ToolBar, swt.widgets.Sash, swt.widgets.Link, swt.custom.CTabFolder, 
                                  swt.widgets.Composite, types.NoneType ]
        self.stateWidgets = [ swt.widgets.Shell ]
        self.imageNumbers = {}
        self.nextImageNumber = 1
        usecase.guishared.Describer.__init__(self)

    def getNoneTypeDescription(self, *args):
        return ""

    def getWindowString(self):
        return "Shell"

    def getShellState(self, shell):
        return shell.getText()

    def getItemBarDescription(self, itemBar, indent=0, subItemMethod=None, prefix="", separator="\n"):
        desc = ""
        for item in itemBar.getItems():
            desc += prefix + " " * indent * 2 + self.getItemDescription(item)
            if subItemMethod:
                desc += subItemMethod(item, indent, prefix)
            desc += separator
        return desc

    def getCascadeMenuDescription(self, item, indent, prefix=""):
        cascadeMenu = item.getMenu()
        if cascadeMenu:
            return " :\n" + self.getMenuDescription(cascadeMenu, indent + 1).rstrip()
        else:
            return ""

    def getSubTreeDescription(self, item, indent, prefix):
        subDesc = self.getItemBarDescription(item, indent+1, subItemMethod=self.getSubTreeDescription, prefix=prefix)
        if subDesc:
            return "\n" + subDesc.rstrip()
        else:
            return ""

    def getMenuDescription(self, menu, indent=1):
        return self.getItemBarDescription(menu, indent=indent, subItemMethod=self.getCascadeMenuDescription)

    def getMenuBarDescription(self, menubar):
        if menubar:
            return "Menu Bar:\n" + self.getMenuDescription(menubar)
        else:
            return ""

    def getToolBarDescription(self, toolbar):
        return "Tool Bar:\n" + self.getItemBarDescription(toolbar, indent=1)

    def getImageDescription(self, image):
        # Seems difficult to get any sensible image information out, there is
        # basically no query API for this in SWT
        number = self.imageNumbers.get(image)
        if not number:
            number = self.nextImageNumber
            self.imageNumbers[image] = self.nextImageNumber
            self.nextImageNumber += 1
        return "Image " + str(number)

    def getStyleDescription(self, style):
        for tryStyle in self.styleNames:
            if style & getattr(swt.SWT, tryStyle) != 0:
                return tryStyle.lower().replace("_", " ").replace("push", "").replace("separator", "---")
        
    def getItemDescription(self, item):
        elements = []
        if item.getText():
            elements.append(item.getText())
        if hasattr(item, "getToolTipText") and item.getToolTipText():
            elements.append("Tooltip '" + item.getToolTipText() + "'")
        styleDesc = self.getStyleDescription(item.getStyle())
        if styleDesc:
            elements.append(styleDesc)
        if item.getImage():
            elements.append(self.getImageDescription(item.getImage()))
        if len(elements) <= 1:
            return "".join(elements)
        else:
            return elements[0] + " (" + ", ".join(elements[1:]) + ")"

    def getSashDescription(self, widget):
        orientation = "Horizontal"
        if widget.getStyle() & swt.SWT.VERTICAL:
            orientation = "Vertical"
        return "-" * 15 + " " + orientation + " sash " + "-" * 15

    def getLinkDescription(self, widget):
        return "Link '" + widget.getText() + "'"
        
    def getLabelDescription(self, label):
        return "'" + label.getText() + "'"
    
    def getWindowContentDescription(self, shell):
        desc = ""
        desc = self.addToDescription(desc, self.getMenuBarDescription(shell.getMenuBar()))
        return self.addToDescription(desc, self.getChildrenDescription(shell))

    def getCompositeDescription(self, widget):
        return ""
        
    def getTextDescription(self, widget):
        header = "=" * 10 + " Text " + "=" * 10        
        return "\n" + header + "\n" + widget.getText().rstrip() + "\n" + "=" * len(header)    

    def getTreeDescription(self, widget):
        columns = widget.getColumns()
        text = "Tree with " + str(len(columns)) + " columns : "
        text += " , ".join((c.getText() for c in columns)) + "\n"
        text += self.getItemBarDescription(widget, indent=0, subItemMethod=self.getSubTreeDescription, prefix="-> ")
        return text

    def getCTabFolderDescription(self, widget):
        return "TabFolder with tabs " + self.getItemBarDescription(widget, separator=" , ")

    def sortChildren(self, widget):
        tabList = filter(lambda c: c.getVisible(), widget.getTabList())
        nonTabList = filter(lambda c: c.getVisible() and c not in tabList, widget.getChildren())
        if len(tabList):
            # Hack for "RCP composite, based on observation only :)
            nonTabList.reverse()
            return tabList + nonTabList
        else:
            return nonTabList
    
    def getChildrenDescription(self, widget):
        if not isinstance(widget, swt.widgets.Composite):
            return ""
        
        desc = ""
        for child in self.sortChildren(widget):
            desc = self.addToDescription(desc, self.getDescription(child))
        
        return desc.rstrip()

    def checkInstance(self, widget, widgetClass):
        # Classloader problems with the custom module ?
        return isinstance(widget, widgetClass) or widget.__class__.__name__ == widgetClass.__name__

    ### Debug code
    ## def getRawData(self, widget):
    ##     return widget.__class__.__name__ + " " + str(id(widget)) + self.getData(widget)

    ## def getData(self, widget):
    ##     if widget.getData():
    ##         try:
    ##             return " " + widget.getData().getBundleId() + " " + widget.getData().getElementType() + " " + repr(widget.getData().getConfigurationElement())
    ##         except:
    ##             return " " + widget.getData().toString()
    ##     else:
    ##         return ""
        
