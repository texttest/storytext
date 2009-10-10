
"""
Logging TreeViews is complicated because there are several ways to set them up
and little direct support for extracting information from them. So they get their own module.
"""

import gtkloggerimage, gtk, logging, types, operator

origTreeViewColumn = gtk.TreeViewColumn
origCellRendererText = gtk.CellRendererText
origCellRendererPixbuf = gtk.CellRendererPixbuf
origCellRendererToggle = gtk.CellRendererToggle

def performInterceptions():
    gtk.TreeViewColumn = TreeViewColumn
    gtk.CellRendererText = CellRendererText
    gtk.CellRendererPixbuf = CellRendererPixbuf
    gtk.CellRendererToggle = CellRendererToggle

class CellRendererText(origCellRendererText):
    orig_set_property = origCellRendererText.set_property
    def set_property(self, property, value):
        self.orig_set_property(property, value)
        cellRendererExtractors.setdefault(self, {})[property] = ConstantExtractor(value)

class CellRendererToggle(origCellRendererToggle):
    orig_set_property = origCellRendererToggle.set_property
    def set_property(self, property, value):
        self.orig_set_property(property, value)
        cellRendererExtractors.setdefault(self, {})[property] = ConstantExtractor(value)

class CellRendererPixbuf(origCellRendererPixbuf):
    orig_set_property = origCellRendererPixbuf.set_property
    def set_property(self, property, value):
        self.orig_set_property(property, value)
        cellRendererExtractors.setdefault(self, {})[property] = ConstantExtractor(value)

# Will overwrite gtk.TreeViewColumn when/if the logging is enabled.
# Yes this is monkey-patching and a bit backwards, but I can't find a better way...
# Alternative is trying to infer the model indices from the state of the CellRenderers
# afterwards, but that seems very error-prone.
class TreeViewColumn(origTreeViewColumn):
    def __init__(self, title=None, cell_renderer=None, **kwargs):
        origTreeViewColumn.__init__(self, title, cell_renderer, **kwargs)
        self.add_model_extractors(cell_renderer, **kwargs)

    def add_model_extractors(self, cell_renderer, **kwargs):
        for attribute, column in kwargs.items():
            self.add_model_extractor(cell_renderer, attribute, column)

    def add_model_extractor(self, cell_renderer, attribute, column):
        std_attribute = attribute.replace("_", "-")
        cellRendererExtractors.setdefault(cell_renderer, {})[std_attribute] = ModelExtractor(column)

    def add_attribute(self, cell_renderer, attribute, column):
        origTreeViewColumn.add_attribute(self, cell_renderer, attribute, column)
        self.add_model_extractor(cell_renderer, attribute, column)

    def set_attributes(self, cell_renderer, **kwargs):
        origTreeViewColumn.set_attributes(self, cell_renderer, **kwargs)
        self.add_model_extractors(cell_renderer, **kwargs)

    def clear_attributes(self, cell_renderer):
        origTreeViewColumn.clear_attributes(self, cell_renderer)
        if cellRendererExtractors.has_key(cell_renderer):
            del cellRendererExtractors[cell_renderer]

    def set_cell_data_func(self, cell_renderer, func, func_data=None):
        origTreeViewColumn.set_cell_data_func(self, cell_renderer, self.collect_cell_data, (func, func_data))

    def collect_cell_data(self, column, cell, model, iter, user_data):
        orig_func, orig_func_data = user_data
        orig_set_property = cell.set_property
        cell.set_property = PropertySetter(cell, model, iter)
        # We assume that this function calls set_property on the cell with its results
        # seems to be the point of this kind of set-up
        if orig_func_data is not None:
            orig_func(column, cell, model, iter, orig_func_data)
        else:
            orig_func(column, cell, model, iter)
        cell.set_property = orig_set_property

cellRendererExtractors = {}

class PropertySetter:
    def __init__(self, cell, model, iter):
        self.cell = cell
        self.rowRef = gtk.TreeRowReference(model, model.get_path(iter))
        
    def __call__(self, property, value):
        self.cell.orig_set_property(property, value)
        cellRendererExtractors.setdefault(self.cell, {}).setdefault(property, HistoryExtractor()).add(value, self.rowRef)


class ConstantExtractor:
    def __init__(self, value):
        self.value = value

    def getValue(self, *args):
        return self.value

class ModelExtractor:
    def __init__(self, index):
        self.index = index

    def getValue(self, model, iter):
        val = model.get_value(iter, self.index)
        if val is None:
            return ""
        else:
            return val

class HistoryExtractor:
    def __init__(self):
        self.history = []
        
    def add(self, value, rowRef):
        self.history.append((value, rowRef))

    def getValue(self, model, iter):
        toRemove = []
        retVal = None
        for value, rowRef in self.history:
            path = rowRef.get_path()
            currModel = rowRef.get_model()
            if path is None or currModel is not model:
                toRemove.append((value, rowRef))
            elif currModel.get_path(iter) == path:
                retVal = value
                break
        for entry in toRemove:
            self.history.remove(entry)
        return retVal


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
        for property in self.getColourProperties():
            set_property = self.getValue(property + "-set", *args)
            if set_property is not False: # Only if it's been explicitly set to False do we care
                value = self.getValue(property, *args)
                if value:
                    return value

    def getColourProperties(self):
        return [ "cell-background" ]

    def getAdditionalProperties(self):
        return []

    def propertyOutput(self, desc):
        return desc


class CellRendererTextDescriber(CellRendererDescriber):    
    def getBasicDescription(self, *args):
        markupDesc = self.getValue("markup", *args)
        if markupDesc:
            return markupDesc
        else:
            textDesc = self.getValue("text", *args)
            if textDesc is not None:
                return str(textDesc)
            else:
                return ""

    def getColourProperties(self):
        return [ "background", "cell-background" ]

    def getAdditionalProperties(self):
        return [ "font" ]

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
        self.imageDescriber = gtkloggerimage.ImageDescriber()

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
        idleScheduler.monitor(self.model, [ "row-inserted", "row-deleted", "row-changed", "rows-reordered" ], "Updated : ", self.view)
        idleScheduler.monitor(self.view, [ "row-expanded" ], "Expanded row in ")
        idleScheduler.monitor(self.view, [ "row-collapsed" ], "Collapsed row in ")
        for column in self.view.get_columns():
            idleScheduler.monitor(column, [ "notify::title" ], "Column titles changed in ", self.view, titleOnly=True)
            
    def set_model_on_view(self, model):
        self.orig_view_set_model(model)
        self.model = model
        self.rendererDescribers = []
        self.describersOK = False
        self.idleScheduler.scheduleDescribe(self.view)

    def getDescription(self, prefix):
        columns = self.view.get_columns()
        titles = " , ".join([ column.get_title() for column in columns ])
        message = "\n" + prefix + self.view.get_name() + " with columns: " + titles + "\n"
        if "Column titles" not in prefix:
            if not self.describersOK:
                self.rendererDescribers = self.getRendererDescribers()
            message += self.getSubTreeDescription(self.model.get_iter_root(), 0)
        return message.rstrip()
    
    def getSubTreeDescription(self, iter, indent):
        if iter is not None and len(self.rendererDescribers) == 0:
            return "ERROR: Could not find the relevant column IDs, so cannot describe tree view!"
        message = ""
        while iter is not None:
            colDescriptions = [ d.getDescription(self.model, iter) for d in self.rendererDescribers ]
            while not colDescriptions[-1]:
                colDescriptions.pop()
            data = " | ".join(colDescriptions) 
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
                extractors = cellRendererExtractors.get(renderer, {})
                className = renderer.__class__.__name__ + "Describer"
                describers.append(eval(className + "(extractors)"))
                if not extractors:
                    self.describersOK = False
        return describers

