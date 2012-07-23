from storytext.javaswttoolkit import describer as swtdescriber
from org.eclipse.core.internal.runtime import InternalPlatform
from org.eclipse.ui.forms.widgets import ExpandableComposite

class Describer(swtdescriber.Describer):
    swtdescriber.Describer.stateWidgets = [ ExpandableComposite ] + swtdescriber.Describer.stateWidgets
    swtdescriber.Describer.ignoreChildren = (ExpandableComposite,) + swtdescriber.Describer.ignoreChildren
    def buildImages(self):
        swtdescriber.Describer.buildImages(self)
        self.buildImagesFromBundles()

    def buildImagesFromBundles(self):            
        patterns = [ "*.gif", "*.GIF", "*.png", "*.PNG", "*.jpg", "*.JPG" ]
        for bundle in InternalPlatform.getDefault().getBundleContext().getBundles():
            for pattern in patterns:
                images = bundle.findEntries("/", pattern, True)
                if images:
                    self.storeAllImages(images)

    def storeAllImages(self, entries):
        while entries.hasMoreElements():
            url = entries.nextElement()
            self.storeImageData(url)
            
    def getExpandableCompositeState(self, widget):
        return widget.isExpanded()
    
    def getExpandableCompositeDescription(self, widget):
        state = self.getExpandableCompositeState(widget)
        self.widgetsWithState[widget] = state
        desc = "Expandable '" + widget.getText() + "' "
        desc += "(expanded)" if state else "(collapsed)"
        if state:
            clientDesc = self.getDescription(widget.getClient())
            desc += "\n  " + clientDesc.replace("\n", "\n  ")
        return desc
    