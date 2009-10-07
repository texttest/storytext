
"""
Logging TreeViews is complicated because there are several ways to set them up
and little direct support for extracting information from them. So they get their own module.
"""

import gtk, logging, types

# Really a utility, but not worth its own module
def getStockDescription(stock):
    return "Stock image '" + stock + "'"

origTreeViewColumn = gtk.TreeViewColumn

# Will overwrite gtk.TreeViewColumn when/if the logging is enabled.
class InterceptTreeViewColumn(origTreeViewColumn):
    def set_cell_data_func(self, cell_renderer, func, func_data=None):
        origTreeViewColumn.set_cell_data_func(self, cell_renderer, self.collect_cell_data, (func, func_data))

    def collect_cell_data(self, column, cell, model, iter, user_data):
        orig_func, orig_func_data = user_data
        orig_set_property = cell.set_property
        cell.set_property = PropertySetter(cell, model, iter, orig_set_property)
        # We assume that this function calls set_property on the cell with its results
        # seems to be the point of this kind of set-up
        if orig_func_data is not None:
            orig_func(column, cell, model, iter, orig_func_data)
        else:
            orig_func(column, cell, model, iter)
        cell.set_property = orig_set_property

cellRendererHistory = {}

class PropertySetter:
    def __init__(self, cell, model, iter, orig_set_property):
        self.cell = cell
        self.orig_set_property = orig_set_property
        self.rowRef = gtk.TreeRowReference(model, model.get_path(iter))
        
    def __call__(self, property, value):
        self.orig_set_property(property, value)
        cellRendererHistory.setdefault(self.cell, {}).setdefault(property, []).append((value, self.rowRef))


class ModelExtractor:
    def __init__(self, model, index):
        self.index = index
        self.model = model

    def getValue(self, iter):
        val = self.model.get_value(iter, self.index)
        if val is None:
            return ""
        else:
            return val

class HistoryExtractor:
    def __init__(self, model, history):
        self.model = model
        self.history = history

    def getValue(self, iter):
        toRemove = []
        retVal = None
        for value, rowRef in self.history:
            path = rowRef.get_path()
            model = rowRef.get_model()
            if path is None or model is not self.model:
                toRemove.append((value, rowRef))
            elif model.get_path(iter) == path:
                retVal = value
                break
        for entry in toRemove:
            self.history.remove(entry)
        return retVal


class ColumnTextIndexStore:
    def __init__(self, extractors):
        self.extractors = extractors

    def description(self, iter):
        textDesc = str(self.extractors[0].getValue(iter))
        extraInfo = []
        for extractor in self.extractors[1:]:
            desc = str(extractor.getValue(iter))
            if desc:
                extraInfo.append(desc)

        if len(extraInfo):
            if textDesc:
                textDesc += " "
            textDesc += "(" + ",".join(extraInfo) + ")"
        return textDesc


class ColumnToggleIndexStore:
    def __init__(self, extractor):
        self.extractor = extractor
        
    def description(self, iter):
        textDesc = "Check box"
        active = self.extractor.getValue(iter)
        if active:
            textDesc += " (checked)"
        return textDesc


class ColumnStockIconIndexStore:
    def __init__(self, extractor):
        self.extractor = extractor

    def description(self, iter):
        stockId = self.extractor.getValue(iter)
        if stockId:
            return getStockDescription(stockId)
        else:
            return ""

class ColumnPixbufIndexStore:
    def __init__(self, extractor):
        self.extractor = extractor
        self.numberForNew = 1
        self.pixbufs = {}

    def getPixbufName(self, pixbuf):
        fromData = pixbuf.get_data("name")
        if fromData:
            return fromData
        else:
            number = self.getPixbufNumber(pixbuf)
            return "Number " + str(number)

    def getPixbufNumber(self, pixbuf):
        storedNum = self.pixbufs.get(pixbuf)
        if storedNum:
            return storedNum

        self.pixbufs[pixbuf] = self.numberForNew
        self.numberForNew += 1
        return self.pixbufs.get(pixbuf)

    def description(self, iter):
        pixbuf = self.extractor.getValue(iter)
        if pixbuf:
            name = self.getPixbufName(pixbuf)
            return "Image '" + name + "'"
        else:
            return ""


# Complicated enough to need its own class...
class TreeViewDescriber:
    def __init__(self, view, idleScheduler):
        self.view = view
        self.orig_view_set_model = self.view.set_model
        self.view.set_model = self.set_model_on_view
        self.model = view.get_model()
        self.logger = logging.getLogger("TreeViewDescriber")
        self.modelIndices = []
        self.indicesOK = False
        self.idleScheduler = idleScheduler
        idleScheduler.monitor(self.model, [ "row-inserted", "row-deleted", "row-changed", "rows-reordered" ], "Updated : ", self.view)
        idleScheduler.monitor(self.view, [ "row-expanded" ], "Expanded row in ")
        idleScheduler.monitor(self.view, [ "row-collapsed" ], "Collapsed row in ")
        for column in self.view.get_columns():
            idleScheduler.monitor(column, [ "notify::title" ], "Column titles changed in ", self.view, titleOnly=True)
            
    def set_model_on_view(self, model):
        self.orig_view_set_model(model)
        self.model = model
        self.modelIndices = []
        self.indicesOK = False
        self.idleScheduler.scheduleDescribe(self.view)

    def getDescription(self, prefix):
        columns = self.view.get_columns()
        titles = " , ".join([ column.get_title() for column in columns ])
        message = "\n" + prefix + self.view.get_name() + " with columns: " + titles + "\n"
        if "Column titles" not in prefix:
            if not self.indicesOK:
                self.modelIndices = self.getModelIndices()
            message += self.getSubTreeDescription(self.model.get_iter_root(), 0)
        return message.rstrip()
    
    def getSubTreeDescription(self, iter, indent):
        if iter is not None and len(self.modelIndices) == 0:
            return "ERROR: Could not find the relevant column IDs, so cannot describe tree view!"
        message = ""
        while iter is not None:
            colDescriptions = [ col.description(iter) for col in self.modelIndices ]
            while not colDescriptions[-1]:
                colDescriptions.pop()
            data = " | ".join(colDescriptions) 
            message += "-> " + " " * 2 * indent + data + "\n"
            if self.view.row_expanded(self.model.get_path(iter)):
                message += self.getSubTreeDescription(self.model.iter_children(iter), indent + 1)
            iter = self.model.iter_next(iter)
        return message

    def getModelIndices(self):
        # There is no good way to do this unfortunately. It seems deliberately
        # made that way out of some perverse desire to separate "view" from "model".
        # The following detective work has been shown to work so far but is
        # far from foolproof...

        # The renderers will be on some row or other... (seems hard to assume where)
        # so we compare their values. Text values should differ.
        texts, renderers = self.getTextInRenderers()
        self.logger.debug("Trying to establish model indices, found texts " + repr(texts))
        rowData = [ {}, None ]
        self.model.foreach(self.matchTextsWithIter, (texts, rowData))
        indexStores = self.getIndexStoresFromRow(rowData[1], renderers, rowData[0]) 
        # Should find an indexstore for every renderer
        self.logger.debug(repr(len(indexStores)) + " index mappings created for " + 
                          repr(len(renderers)) + " renderers.")
        self.indicesOK = len(indexStores) == len(renderers)
        return indexStores

    def getTextInRenderers(self):
        texts, renderers = [], []
        for column in self.view.get_columns():
            for renderer in column.get_cell_renderers():
                renderers.append(renderer)
                if isinstance(renderer, gtk.CellRendererText):
                    text = renderer.get_property("text")
                    if text is not None:
                        texts.append(text)
        return texts, renderers

    def makeExtractor(self, index, history, property, text):
        if index is not None:
            self.logger.debug(repr(property) + " index for '" + text + "' found as " + repr(index))
            return ModelExtractor(self.model, index)
        else:
            prop_history = history.get(property)
            if prop_history:
                self.logger.debug(repr(property) + " info for '" + text + "' found via stored property history")
                return HistoryExtractor(self.model, prop_history)

    def findIndicesForTexts(self, model, path, iter, texts):
        currIndices = {}
        for text in texts:
            index = self.getTextIndex(model, iter, text)
            if index is None:
                self.logger.debug("Could not find index for '" + text + "' using path " + repr(path))
                continue
            elif index not in currIndices:
                self.logger.debug("Index for '" + text + "' found as " + repr(index) + " using path " + repr(path))
                currIndices[text] = index
        return currIndices

    def matchTextsWithIter(self, model, path, iter, userdata):
        texts, rowdata = userdata
        currIndices = self.findIndicesForTexts(model, path, iter, texts)
        if len(currIndices) > len(rowdata[0]):
            rowdata[0] = currIndices
            rowdata[1] = iter
        if len(currIndices) == len(texts):
            return True # terminate, we've found the perfect match

    def getIndexStoresFromRow(self, iter, renderers, textIndices):
        # We've found matching texts, try to match the colours and fonts as best we can
        colourIndices = set()
        fontIndices = set()
        toggleIndices = set()
        pixbufIndices = set()
        knownIndices = set(textIndices.values())
        indexStores = []
        for renderer in renderers:
            history = cellRendererHistory.get(renderer, {})
            if isinstance(renderer, gtk.CellRendererText):
                text = renderer.get_property("text")
                if text is None:
                    return indexStores
                extractors = []
                textIndex = textIndices.get(text)
                extractor = self.makeExtractor(textIndex, history, "text", text)
                if extractor:    
                    extractors.append(extractor)
                else:
                    return indexStores
                
                colour = renderer.get_property("background-gdk")
                colourIndex = self.findMatchingIndex(iter, colour, knownIndices, 
                                                     colourIndices, self.colourMatches)
                if colourIndex is not None:
                    colourIndices.add(colourIndex)
                    knownIndices.add(colourIndex)
                extractor = self.makeExtractor(colourIndex, history, "background-gdk", text)
                if extractor:    
                    extractors.append(extractor)
                    
                font = renderer.get_property("font")
                fontIndex = self.findMatchingIndex(iter, font, knownIndices, fontIndices, 
                                                   self.textMatches)
                if fontIndex is not None:
                    fontIndices.add(fontIndex)
                    knownIndices.add(fontIndex) 
                extractor = self.makeExtractor(fontIndex, history, "font", text)
                if extractor:    
                    extractors.append(extractor)
                                      
                indexStores.append(ColumnTextIndexStore(extractors))
            elif isinstance(renderer, gtk.CellRendererToggle):
                active = renderer.get_property("active")
                activeIndex = self.findMatchingIndex(iter, active, knownIndices, 
                                                     toggleIndices, self.boolMatches)
                if activeIndex is not None:
                    toggleIndices.add(activeIndex)
                    knownIndices.add(activeIndex)
                extractor = self.makeExtractor(activeIndex, history, "active", "CellRendererToggle")
                if extractor:
                    indexStores.append(ColumnToggleIndexStore(extractor))
            elif isinstance(renderer, gtk.CellRendererPixbuf):
                stockId = renderer.get_property("stock-id")
                stockIndex = None
                if stockId is not None:
                    stockIndex = self.findMatchingIndex(iter, stockId, knownIndices, 
                                                        pixbufIndices, self.textMatches)
                if stockIndex is not None:
                    pixbufIndices.add(stockIndex)
                    knownIndices.add(stockIndex)
                extractor = self.makeExtractor(stockIndex, history, "stock-id", stockId)
                if extractor:
                    indexStores.append(ColumnStockIconIndexStore(extractor))
                else:
                    pixbuf = renderer.get_property("pixbuf")
                    pixbufIndex = self.findMatchingIndex(iter, pixbuf, knownIndices, 
                                                         pixbufIndices, self.identityMatches)
                    if pixbufIndex is not None:
                        pixbufIndices.add(pixbufIndex)
                        knownIndices.add(pixbufIndex)
                    extractor = self.makeExtractor(pixbufIndex, history, "pixbuf", "CellRendererPixbuf")
                    if extractor:
                        indexStores.append(ColumnPixbufIndexStore(extractor))

        return indexStores

    def getTextIndex(self, model, iter, text):
        # May have markup involved, in which case "text" will have it stripped out
        textMarkupStr = ">" + text + "<"
        for index in range(model.get_n_columns()):
            givenText = str(model.get_value(iter, index))
            if givenText == text or (type(givenText) == types.StringType and textMarkupStr in givenText):
                return index        

    def findMatchingIndex(self, iter, info, knownIndices, prevIndices, matchMethod):
        for index in range(self.model.get_n_columns()):
            if index not in knownIndices and matchMethod(iter, index, info):
                return index

        # If we can't find a unique column, assume we're tied to a previous one
        for index in prevIndices:
            if matchMethod(iter, index, info):
                return index

    def identityMatches(self, iter, index, obj):
        givenObj = self.model.get_value(iter, index)
        return givenObj is obj

    def textMatches(self, iter, index, text):
        givenText = self.model.get_value(iter, index)
        return type(givenText) == types.StringType and givenText.lower() == text.lower()

    def boolMatches(self, iter, index, value):
        givenValue = self.model.get_value(iter, index)
        return type(givenValue) == types.BooleanType and givenValue == value

    def colourMatches(self, iter, index, colour):
        givenText = self.model.get_value(iter, index)
        if type(givenText) != types.StringType:
            return False
        try:
            givenColour = gtk.gdk.color_parse(givenText)
            return self.coloursIdentical(colour, givenColour)
        except ValueError:
            return False

    def coloursIdentical(self, col1, col2):
        return col1.red == col2.red and col1.green == col2.green and col1.blue == col2.blue
