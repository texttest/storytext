
import usecase.guishared, types
from org.eclipse import swt
        
class Describer(usecase.guishared.Describer):
    styleNames = [ "PUSH", "SEPARATOR", "DROP_DOWN", "CHECK", "CASCADE", "RADIO" ]
    imageTypeNames = filter(lambda x: x.startswith("IMAGE_"), dir(swt.SWT))
    def __init__(self):
        self.statelessWidgets = [ swt.widgets.Menu, swt.widgets.Label,
                                  swt.widgets.ToolBar, types.NoneType ]
        self.stateWidgets = [ swt.widgets.Shell ]
        usecase.guishared.Describer.__init__(self)

    def getNoneTypeDescription(self, *args):
        return ""

    def getWindowString(self):
        return "Shell"

    def getShellState(self, shell):
        return shell.getText()

    def getMenuDescription(self, menu, indent=0):
        return self.getItemBarDescription(menu, indent=indent, subItemMethod=self.getCascadeMenuDescription)

    def getItemBarDescription(self, itemBar, indent=0, subItemMethod=None):
        desc = ""
        for item in itemBar.getItems():
            desc += " " * indent * 2 + self.getItemDescription(item)
            if subItemMethod:
                desc += subItemMethod(item, indent)
            desc += "\n"
        return desc

    def getCascadeMenuDescription(self, item, indent):
        cascadeMenu = item.getMenu()
        if cascadeMenu:
            return " :\n" + self.getMenuDescription(cascadeMenu, indent + 1).rstrip()
        else:
            return ""

    def getToolBarDescription(self, toolbar):
        return "Tool Bar:\n" + self.getItemBarDescription(toolbar, indent=1)

    def getImageDescription(self, image):
        imageType = image.getImageData().type
        for tryType in self.imageTypeNames:
            if imageType == getattr(swt.SWT, tryType):
                return tryType.lower().replace("image_", "") + " image"
        return "unknown image type (" + str(imageType) + ")" # pragma: no cover - for completeness and robustness only

    def getStyleDescription(self, style):
        for tryStyle in self.styleNames:
            if style & getattr(swt.SWT, tryStyle) != 0:
                return tryStyle.lower().replace("_", " ").replace("push", "").replace("separator", "---")
        
    def getItemDescription(self, item):
        elements = []
        if item.getText():
            elements.append(item.getText())
        if hasattr(item, "getToolTipText") and item.getToolTipText():
            elements.append("Tooltip " + repr(item.getToolTipText()))
        styleDesc = self.getStyleDescription(item.getStyle())
        if styleDesc:
            elements.append(styleDesc)
        if item.getImage():
            elements.append(self.getImageDescription(item.getImage()))
        if len(elements) <= 1:
            return "".join(elements)
        else:
            return elements[0] + " (" + ", ".join(elements[1:]) + ")"

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

