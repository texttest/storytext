
""" 
Module that makes it possible to extract information from a treeview
without having information about the treemodel, as we may not from inside PyUsecase
"""

import gtk

# This is the important information, used by other classes
cellRendererExtractors = {}

def getAllExtractors(renderer):
    return cellRendererExtractors.get(renderer, {})

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

# Will overwrite gtk.TreeViewColumn when/if the logging or UI map is enabled.
# Yes this is monkey-patching and a bit backwards, but I can't find a better way...
# Alternative is trying to infer the model indices from the state of the CellRenderers
# afterwards, but that seems very error-prone (having done it this way for a bit).
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
