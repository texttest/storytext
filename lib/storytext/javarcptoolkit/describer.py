from storytext.javaswttoolkit import describer as swtdescriber
from org.eclipse.core.internal.runtime import InternalPlatform
from org.eclipse.ui.forms.widgets import ExpandableComposite

class Describer(swtdescriber.Describer):
    swtdescriber.Describer.stateWidgets = [ ExpandableComposite ] + swtdescriber.Describer.stateWidgets
    swtdescriber.Describer.ignoreChildren = (ExpandableComposite,) + swtdescriber.Describer.ignoreChildren
    def __init__(self):
        swtdescriber.Describer.__init__(self)
        self.buildImagesFromBundles()

    def buildImages(self):
        swtdescriber.Describer.buildImages(self)
        self.buildImagesFromBundles()

    def buildImagesFromBundles(self):            
        for bundle in InternalPlatform.getDefault().getBundleContext().getBundles():
            gifs = bundle.findEntries("/", "*.gif", True)
            pngs = bundle.findEntries("/", "*.png", True)
            jpgs = bundle.findEntries("/", "*.jpg", True)
            if gifs:
                self.makeImageDescriptors(gifs)
            if pngs:
                self.makeImageDescriptors(pngs)
            if jpgs:
                self.makeImageDescriptors(jpgs)

    def makeImageDescriptors(self, entries):
        while entries.hasMoreElements():
            url = entries.nextElement()
            self.makeImageDescriptor(url)
            
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
    