import os
from storytext.javaswttoolkit import describer as swtdescriber
from pprint import pprint

from org.eclipse.core.internal.runtime import InternalPlatform
from org.eclipse.ui.forms.widgets import ExpandableComposite
from org.eclipse.ui.internal import WorkbenchImages, IWorkbenchGraphicConstants

class Describer(swtdescriber.Describer):
    swtdescriber.Describer.stateWidgets = [ ExpandableComposite ] + swtdescriber.Describer.stateWidgets
    swtdescriber.Describer.ignoreChildren = (ExpandableComposite,) + swtdescriber.Describer.ignoreChildren
    def buildImages(self):
        swtdescriber.Describer.buildImages(self)
        self.buildImagesFromBundles()
        self.addRenderedImages()

    def buildImagesFromBundles(self):            
        allImageTypes = [ "gif", "png", "jpg" ]
        allImageTypes += [ i.upper() for i in allImageTypes ]
        
        cacheFile = os.path.join(os.getenv("STORYTEXT_HOME"), "osgi_bundle_image_types")
        cacheExists = os.path.isfile(cacheFile)
        bundleImageTypes = eval(open(cacheFile).read()) if cacheExists else {}
        writeCache = not cacheExists or "STORYTEXT_WRITE_CACHE" in os.environ
        
        for bundle in InternalPlatform.getDefault().getBundleContext().getBundles():
            usedTypes = []
            name = bundle.getSymbolicName()
            imageTypes = bundleImageTypes.get(name, allImageTypes)
            if name not in bundleImageTypes:
                self.logger.debug("Bundle " + name + " not cached, trying all image types!")
            for imageType in imageTypes:
                self.logger.debug("Searching bundle " + name + " for images of type " + imageType)
                images = bundle.findEntries("/", "*." + imageType, True)
                if images and images.hasMoreElements():
                    self.storeAllImages(images)
                    usedTypes.append(imageType)
            if writeCache:
                bundleImageTypes[name] = usedTypes
        if writeCache:
            f = open(cacheFile, "w")
            pprint(bundleImageTypes, f)
            f.close()

    def storeAllImages(self, entries):
        while entries.hasMoreElements():
            url = entries.nextElement()
            self.logger.debug("Storing image data for file " + str(url) + " from bundles.")
            self.imageDescriber.storeImageData(url)
                        
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
    
    def addRenderedImages(self):
        image = WorkbenchImages.getImage(IWorkbenchGraphicConstants.IMG_LCL_RENDERED_VIEW_MENU)
        if image:
            self.imageDescriber.addRenderedImage(image, "view_menu")
