from storytext.javaswttoolkit import describer as swtdescriber
from org.eclipse.core.internal.runtime import InternalPlatform
from org.eclipse.ui.forms.widgets import ExpandableComposite
import os
from pprint import pprint

class Describer(swtdescriber.Describer):
    swtdescriber.Describer.stateWidgets = [ ExpandableComposite ] + swtdescriber.Describer.stateWidgets
    swtdescriber.Describer.ignoreChildren = (ExpandableComposite,) + swtdescriber.Describer.ignoreChildren
    def buildImages(self):
        swtdescriber.Describer.buildImages(self)
        self.buildImagesFromBundles()

    def buildImagesFromBundles(self):            
        allImageTypes = [ "gif", "png", "jpg" ]
        allImageTypes += [ i.upper() for i in allImageTypes ]
        
        cacheFile = os.path.join(os.getenv("STORYTEXT_HOME"), "osgi_bundle_image_types")
        cacheExists = os.path.isfile(cacheFile)
        bundleImageTypes = eval(open(cacheFile).read()) if cacheExists else {}
        
        for bundle in InternalPlatform.getDefault().getBundleContext().getBundles():
            usedTypes = []
            name = bundle.getSymbolicName()
            imageTypes = bundleImageTypes.get(name, allImageTypes)
            for imageType in imageTypes:
                self.logger.debug("Searching bundle " + name + " for images of type " + imageType)
                images = bundle.findEntries("/", "*." + imageType, True)
                if images and images.hasMoreElements():
                    self.storeAllImages(images)
                    usedTypes.append(imageType)
            if not cacheExists:
                bundleImageTypes[name] = usedTypes
        if not cacheExists:
            f = open(cacheFile, "w")
            pprint(bundleImageTypes, f)
            f.close()

    def storeAllImages(self, entries):
        while entries.hasMoreElements():
            url = entries.nextElement()
            self.storeImageData(url)
            
    def getUpdatePrefix(self, widget, *args):
        if isinstance(widget, ExpandableComposite):
            return "\nUpdated "
        else:
            return swtdescriber.Describer.getUpdatePrefix(self, widget, *args)
            
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
    