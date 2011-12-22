from storytext.javaswttoolkit import describer as swtdescriber
from org.eclipse.core.runtime import Platform
from org.eclipse.ui.plugin import AbstractUIPlugin
from org.eclipse.jface.resource import ImageDescriptor
from org.eclipse.core.internal.runtime import InternalPlatform

class Describer(swtdescriber.Describer):
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
