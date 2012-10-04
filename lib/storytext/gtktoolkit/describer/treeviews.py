
"""
Logging TreeViews is complicated because there are several ways to set them up
and little direct support for extracting information from them. So they get their own module.
"""

import gtk, logging
from images import ImageDescriber
from ..treeviewextract import getAllExtractors

class ColourSpecMap(dict):
    def __setitem__(self, colour, spec):
        dict.__setitem__(self, self.getKey(colour), spec)

    def getKey(self, colour):
        if hasattr(colour, "to_string"):
            # PyGTK 2.12 or later
            return colour.to_string()
        else:
            # Doesn't work from PyGTK 2.14
            return colour 

    def get(self, colour):
        return dict.get(self, self.getKey(colour))
        

orig_color_parse = gtk.gdk.color_parse
all_colours = ColourSpecMap()

def color_parse(spec):
    colour = orig_color_parse(spec)
    all_colours[colour] = spec
    return colour

def performTreeViewInterceptions():
    gtk.gdk.color_parse = color_parse

# Things that need to be updated for monitoring gtk.TreeModel objects for logging
treeModelSignals = [ "row-inserted", "row-deleted", "row-changed", "rows-reordered" ]

class CellRendererDescriber:
    def __init__(self, extractors):
        self.extractors = extractors

    def getValue(self, property, *args):
        extractor = self.extractors.get(property)
        if extractor:
            return extractor.getValue(*args)

    def getDescription(self, *args):
        textDesc = self.getBasicDescription(*args)
        detailInfo = self.getDetailDescriptions(*args)
        if len(detailInfo):
            if textDesc:
                textDesc += " " 
            textDesc += "(" + ",".join(detailInfo) + ")"
        return textDesc

    def getDetailDescriptions(self, *args):
        extraInfo = []
        colourDesc = self.getColourDescription(*args)
        if colourDesc:
            extraInfo.append(colourDesc)

        for property in self.getAdditionalProperties():
            desc = self.getValue(property, *args)
            if desc:
                extraInfo.append(self.propertyOutput(desc))

        return extraInfo

    def getColourDescription(self, *args):
        colourDescs = []
        for prop in self.getColourProperties():
            desc = self.getColourPropertyDescription(prop, *args)
            if desc:
                colourDescs.append(desc)
        return "/".join(colourDescs)

    def getColourPropertyDescription(self, prop, *args):
        set_property = self.getValue(prop + "-set", *args)
        if set_property is not False: # Only if it's been explicitly set to False do we care
            value = self.getValue(prop, *args)
            if value:
                return value
            gdkValue = self.getValue(prop + "-gdk", *args)
            colour = all_colours.get(gdkValue)
            if colour:
                return colour

    def getColourProperties(self):
        return [ "cell-background" ]

    def getAdditionalProperties(self):
        return []

    def propertyOutput(self, desc):
        return str(desc)


class CellRendererTextDescriber(CellRendererDescriber):    
    def getBasicDescription(self, *args):
        markupDesc = self.getValue("markup", *args)
        if markupDesc:
            return markupDesc
        else:
            textDesc = self.getValue("text", *args)
            if textDesc is not None:
                if not isinstance(textDesc, (str, unicode)):
                    textDesc = unicode(textDesc)
                return textDesc
            else:
                return ""

    def getColourProperties(self):
        return [ "foreground", "background", "cell-background" ]

    def getAdditionalProperties(self):
        return [ "font", "weight" ]

class CellRendererToggleDescriber(CellRendererDescriber):        
    def getBasicDescription(self, *args):
        return "Check box"

    def getAdditionalProperties(self):
        return [ "active" ]

    def propertyOutput(self, *args):
        return "checked"


class CellRendererPixbufDescriber(CellRendererDescriber):
    def __init__(self, extractors):
        CellRendererDescriber.__init__(self, extractors)
        self.imageDescriber = ImageDescriber()

    def getBasicDescription(self, *args):
        stockId = self.getValue("stock-id", *args)
        if stockId:
            return self.imageDescriber.getStockDescription(stockId)
        else:
            pixbuf = self.getValue("pixbuf", *args)
            return self.imageDescriber.getPixbufDescription(pixbuf)


# Complicated enough to need its own class...
class TreeViewDescriber: 
    def __init__(self, view, idleScheduler):
        self.view = view
        self.orig_view_set_model = self.view.set_model
        self.view.set_model = self.set_model_on_view
        self.model = view.get_model()
        self.logger = logging.getLogger("TreeViewDescriber")
        self.rendererDescribers = []
        self.describersOK = False
        self.idleScheduler = idleScheduler
        if self.model:
            idleScheduler.monitor(self.model, treeModelSignals, "Updated : ", self.view, priority=2)
        idleScheduler.monitor(self.view, [ "row-expanded" ], "Expanded row in ", priority=3)
        idleScheduler.monitor(self.view, [ "row-collapsed" ], "Collapsed row in ", priority=3)
        idleScheduler.monitor(self.view.get_selection(), [ "changed" ], "Changed selection in ", self.view, priority=4)
        for column in self.view.get_columns():
            idleScheduler.monitor(column, [ "notify::title" ], "Column titles changed in ", self.view, titleOnly=True)
            
    def set_model_on_view(self, model):
        self.orig_view_set_model(model)
        self.model = model
        self.rendererDescribers = []
        self.describersOK = False
        self.idleScheduler.scheduleDescribe(self.view, prefix="Recreated ")

    def getDescription(self, prefix):
        columns = self.view.get_columns()
        titles = " , ".join([ column.get_title() or "" for column in columns ])
        message = "\n" + prefix + self.view.get_name() + " with columns: " + titles + "\n"
        if "Column titles" not in prefix and self.model:
            if not self.describersOK:
                self.rendererDescribers = self.getRendererDescribers()
            message += self.getSubTreeDescription(self.model.get_iter_root(), 0)
        return message.rstrip()
    
    def getSubTreeDescription(self, iter, indent):
        if iter is not None and len(self.rendererDescribers) == 0: # pragma: no cover - for robustness only
            return "ERROR: Could not find the relevant column IDs, so cannot describe tree view!"
        message = ""
        while iter is not None:
            colDescriptions = [ d.getDescription(self.model, iter) for d in self.rendererDescribers ]
            while not colDescriptions[-1]:
                colDescriptions.pop()
            data = " | ".join(colDescriptions)
            if self.view.get_selection().iter_is_selected(iter):
                data += "   ***"
            message += "-> " + " " * 2 * indent + data + "\n"
            if self.view.row_expanded(self.model.get_path(iter)):
                message += self.getSubTreeDescription(self.model.iter_children(iter), indent + 1)
            iter = self.model.iter_next(iter)
        return message

    def getRendererDescribers(self):
        describers = []
        self.describersOK = True
        for column in self.view.get_columns():
            for renderer in column.get_cell_renderers():
                extractors = getAllExtractors(column, renderer)
                if extractors:
                    className = renderer.__class__.__name__ + "Describer"
                    describers.append(eval(className + "(extractors)"))
                else:
                    self.describersOK = False
        return describers

