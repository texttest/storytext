
"""
The basic mission of this module is to provide a standard textual output of GTK GUI elements,
to aid in text-based UI testing for GTK
"""

import logging, gtk, gobject, locale, operator, types

def describe(widget, customDescribers={}, prefix="Showing "):
    describer = Describer(customDescribers, prefix)
    describer(widget)

class Describer:
    logger = None
    supportedWidgets = [ gtk.Label, gtk.CheckButton, gtk.Button, gtk.Table, gtk.Frame, 
                         gtk.Expander, gtk.Notebook, gtk.TreeView, gtk.ComboBoxEntry, gtk.MenuItem,
                         gtk.Entry, gtk.TextView, gtk.Container, gtk.Separator, gtk.Image ]
    cachedDescribers = {}    
    def __init__(self, customDescribers, prefix):
        if not Describer.logger:
            Describer.logger = logging.getLogger("gui log")
        self.customDescribers = customDescribers
        self.prefix = prefix
        
    def __call__(self, widget):
        if self.logger.isEnabledFor(logging.INFO):
            if isinstance(widget, gtk.Window):
                self.describeWindow(widget)
            else:
                self.logger.info(self.getDescription(widget))

    def getDescription(self, widget):
        idleScheduler.register(widget)
        baseDescription = self.getBasicDescription(widget)
        if not widget.get_property("sensitive"):
            baseDescription += " (greyed out)"
        tooltip = self.getTooltipText(widget)
        if tooltip:
            baseDescription += " (tooltip '" + tooltip + "')"
        return baseDescription

    def getTooltipText(self, widget):
        try:
            # New 3.12 method...
            return widget.get_tooltip_text()
        except AttributeError:
            data = gtk.tooltips_data_get(widget)
            if data:
                return data[2]

    def getSeparator(self, container):
        if isinstance(container, gtk.HBox):
            return " , "
        elif isinstance(container, gtk.Paned):
            return self.getPanedSeparator(container)
        else:
            return "\n"

    def getPanedSeparator(self, paned):
        panedSeparator = "-" * 30
        proportion = float(paned.get_position()) / paned.get_property("max-position")
        roundedProportion = str(int(round(100 * proportion, 0)))
        name = paned.get_name()
        if name.startswith("Gtk"):
            name = "pane separator"
        if isinstance(paned, gtk.VPaned):
            panedSeparator += " (horizontal " + name + ", " + roundedProportion + "% from the top)"
        else:
            panedSeparator += " (vertical " + name + ", " + roundedProportion + "% from the left edge)"
        return "\n\n" + panedSeparator + "\n"
        
    def getContainerDescription(self, container):
        messages = [ self.getDescription(widget) for widget in container.get_children() ]
        sep = self.getSeparator(container)
        if "\n" in sep:
            return sep.join(messages)
        else:
            # Horizontal, don't allow for extra new lines...
            return sep.join([ m.strip() for m in messages ])

    def getBasicDescription(self, widget):
        for widgetClass, describer in self.customDescribers.items():
            if isinstance(widget, widgetClass):
                return describer.getBasicDescription(widget)
        for widgetClass in self.supportedWidgets:
            if isinstance(widget, widgetClass):
                methodName = "get" + widgetClass.__name__ + "Description"
                return getattr(self, methodName)(widget)

        return "A widget of type '" + widget.__class__.__name__ + "'"

    def getLabelDescription(self, widget):
        return "'" + widget.get_text() + "'"
    
    def getMenuItemText(self, menuitem):
        text = self.getLabelDescription(menuitem.get_child())
        if menuitem.get_submenu():
            return text + " Menu"
        else:
            return text

    def getMenuItemDescription(self, menuitem):
        return "\n".join(self.getMenuItemLines(menuitem, indent=0))

    def getMenuItemLines(self, menuitem, indent):
        headerLine = " " * indent + self.getMenuItemText(menuitem) + " :"
        submenu = menuitem.get_submenu()
        if submenu:
            return [ headerLine ] + self.getMenuLines(submenu, indent+2)
        else:
            return [ headerLine ]

    def getMenuLines(self, menu, indent):
        items = menu.get_children()
        texts = map(self.getMenuItemText, items)
        lines = [ " " * indent + ", ".join(texts) ]
        for item in items:
            submenu = item.get_submenu()
            if submenu:
                lines += self.getMenuItemLines(item, indent)
        return lines

    def getTableRowDescription(self, columnMap, columnCount):
        cellWidgets = [ columnMap.get(column, []) for column in range(columnCount) ]
        rowWidgets = reduce(operator.add, cellWidgets, [])
        rowMessages = map(self.getDescription, rowWidgets)
        return " | ".join(rowMessages)

    def getTableLayoutMap(self, table):
        layoutMap = {}
        for child in table.get_children():
            childRow = table.child_get_property(child, "top-attach")
            childColumn = table.child_get_property(child, "left-attach")
            layoutMap.setdefault(childRow, {}).setdefault(childColumn, []).append(child)
        return layoutMap
    
    def getTableDescription(self, table):
        childMap = self.getTableLayoutMap(table)
        columnCount = table.get_property("n-columns")
        rowCount = table.get_property("n-rows")
        text = "Viewing table with " + str(rowCount) + " rows and " + str(columnCount) + " columns.\n"
        text += "\n".join([ self.getTableRowDescription(childMap.get(row, {}), columnCount) for row in range(rowCount) ])
        return text

    def getLabelText(self, container):
        labelWidget = container.get_label_widget()
        if labelWidget:
            try:
                return True, labelWidget.get_text()
            except AttributeError:
                return True, labelWidget.get_child().get_text()
        else:
            return False, ""

    def getExpanderDescription(self, expander):
        labelExisted, label = self.getLabelText(expander)
        text = "Expander '" + label + "':\n"
        # Last child is the label :)
        for child in expander.get_children()[:-1]:
            text += "-> " + self.getDescription(child) + "\n"
        return text.rstrip()
    
    def getFrameDescription(self, frame):
        labelExisted, label = self.getLabelText(frame)
        frameText = "....." + label + "......\n"
        if labelExisted:
            # Frame's last child is the label :)
            children = frame.get_children()[:-1]
        else:
            children = frame.get_children()
        for child in children:
            frameText += self.getDescription(child) + "\n"
        return frameText.rstrip()

    def getSeparatorDescription(self, separator):
        basic = "-" * 15
        if isinstance(separator, gtk.VSeparator):
            return basic + " (vertical)"
        else:
            return basic

    def getComboBoxEntryDescription(self, combobox):
        entryDescription = self.getDescription(combobox.get_child())
        model = combobox.get_model()
        allEntries = []
        iter = model.get_iter_root()
        while iter:
            allEntries.append(model.get_value(iter, 0))
            iter = model.iter_next(iter)
        dropDownDescription = " (drop-down list containing " + repr(allEntries) + ")"
        return entryDescription + dropDownDescription

    def getTextViewDescription(self, view):
        describer = self.cachedDescribers.setdefault(view, TextViewDescriber(view))
        return describer.getDescription()

    def getEntryDescription(self, entry):
        idleScheduler.monitor(entry, [ "changed" ], "Edited ")
        text = ""
        if self.prefix != "Showing ":
            text += self.prefix + "'" + entry.get_name() + "' "
        text += "Text entry"
        entryText = entry.get_text()
        if entryText:
            text += " (set to '" + entryText + "')"
        return text

    def getNotebookDescription(self, notebook):
        tabNames = []
        idleScheduler.monitor(notebook, [ "switch-page", "page-added" ], "Current page changed in ")
        message = ""
        for child in notebook.get_children():
            idleScheduler.monitor(child, [ "hide", "show" ], "Child visibility changed in ", notebook, titleOnly=True)
            if child.get_property("visible"):
                name = notebook.get_tab_label_text(child)
                tabNames.append(name)
                              
        desc = "\n" + self.prefix + "Notebook with tabs: " + " , ".join(tabNames)
        tabsOnly = "visibility" in self.prefix
        self.prefix = "Showing " # In case of tree views etc. further down
        if not tabsOnly:
            desc += "\n" + self.getCurrentNotebookPageDescription(notebook)
        return desc

    def getCurrentNotebookPageDescription(self, notebook):
        index = notebook.get_current_page()
        page = notebook.get_nth_page(index)
        tabName = notebook.get_tab_label_text(page)
        return "Viewing page '" + tabName + "'\n" + self.getDescription(page)
    
    def getTreeViewDescription(self, view):
        describer = self.cachedDescribers.setdefault(view, TreeViewDescriber(view))
        return describer.getDescription(self.prefix)
                    
    def getCheckButtonDescription(self, button):
        idleScheduler.monitor(button, [ "toggled" ], "Toggled ")
        text = ""
        if self.prefix != "Showing ":
            text += self.prefix
        if isinstance(button, gtk.RadioButton):
            text += "Radio"
        else:
            text += "Check"
        text += " button '" + button.get_label() + "'"
        if button.get_active():
            text += " (checked)"
        return text

    def getImageDescription(self, image):
        try:
            stock, size = image.get_stock()
            if stock:
                return "Stock image '" + stock + "'"
        except ValueError:
            pass
        return "Non-stock image"
        
    def getButtonDescription(self, button):
        labelText = button.get_label()
        if labelText:
            text = "Button '" + labelText + "'"
        else:
            text = "Button"
        if button.get_image():
            text += ", " + self.getImageDescription(button.get_image()).lower()
        return text
        
    def describeWindow(self, window):
        widgetType = window.__class__.__name__.capitalize()
        message = "-" * 10 + " " + widgetType + " '" + window.get_title() + "' " + "-" * 10
        self.logger.info(message)
        defaultWidget = window.default_widget
        if defaultWidget:
            try:
                self.logger.info("Default action is labelled '" + defaultWidget.get_label() + "'")
            except AttributeError: #pragma : no cover, should probably never happen...
                self.logger.info("Default widget unlabelled, type " + str(defaultWidget.__class__))
        # One blank line at the end
        self.logger.info(self.getContainerDescription(window))
        self.logger.info("-" * len(message))


class TextViewDescriber:
    def __init__(self, view):
        self.buffer = view.get_buffer()
        idleScheduler.monitor(self.buffer, [ "insert-text" ], "", view)
        self.name = view.get_name()

    def getDescription(self):
        header = "=" * 10 + " " + self.name + " " + "=" * 10        
        return "\n" + header + "\n" + self.getContents().strip() + "\n" + "=" * len(header)

    def getContents(self):
        unicodeInfo = self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter())
        localeEncoding = locale.getdefaultlocale()[1]
        warning = ""
        if localeEncoding:
            try:
                return unicodeInfo.encode(localeEncoding, 'strict')
            except:
                warning = "WARNING: Failed to encode Unicode string '" + unicodeInfo + \
                          "' using strict '" + localeEncoding + "' encoding.\nReverting to non-strict UTF-8 " + \
                          "encoding but replacing problematic\ncharacters with the Unicode replacement character, U+FFFD.\n"
        return warning + unicodeInfo.encode('utf-8', 'replace')

class ColumnTextIndexStore:
    def __init__(self, model, textIndex, colourIndex, fontIndex):
        self.textIndex = textIndex
        self.model = model
        self.colourIndex = colourIndex
        self.fontIndex = fontIndex

    def getCellText(self, iter, index):
        val = self.model.get_value(iter, index)
        if val is None:
            return ""
        else:
            return str(val)

    def description(self, iter):
        textDesc = self.getCellText(iter, self.textIndex)
        extraInfo = []
        if self.colourIndex is not None:
            colourDesc = self.getCellText(iter, self.colourIndex)
            if colourDesc:
                extraInfo.append(colourDesc)
        if self.fontIndex is not None:
            font = self.model.get_value(iter, self.fontIndex)
            if font:
                extraInfo.append(font)
        if len(extraInfo):
            if textDesc:
                textDesc += " "
            textDesc += "(" + ",".join(extraInfo) + ")"
        return textDesc


class ColumnToggleIndexStore:
    def __init__(self, model, index):
        self.index = index
        self.model = model

    def description(self, iter):
        textDesc = "Check box"
        active = self.model.get_value(iter, self.index)
        if active:
            textDesc += " (checked)"
        return textDesc

class ColumnPixbufIndexStore:
    def __init__(self, model, index):
        self.index = index
        self.model = model

    def description(self, iter):
        stockId = self.model.get_value(iter, self.index)
        if stockId:
            return "Stock image '" + stockId + "'"
        else:
            return ""

# Complicated enough to need its own class...
class TreeViewDescriber:
    def __init__(self, view):
        self.view = view
        self.model = view.get_model()
        self.modelIndices = []
        self.indicesOK = False
        idleScheduler.monitor(self.model, [ "row-inserted", "row-deleted", "row-changed", "rows-reordered" ], "Updated : ", self.view)
        idleScheduler.monitor(self.view, [ "row-expanded" ], "Expanded row in ")
        for column in self.view.get_columns():
            idleScheduler.monitor(column, [ "notify::title" ], "Column titles changed in ", self.view, titleOnly=True)
        
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
        indices = []
        if len(texts) > 0:
            self.model.foreach(self.addIndicesFromIter, (texts, renderers, indices))
        # Should find an index for every renderer
        self.indicesOK = len(indices) == len(renderers)
        return indices

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

    def addIndicesFromIter(self, model, path, iter, userdata):
        texts, renderers, indices = userdata
        currIndices = {}
        for text in texts:
            index = self.getTextIndex(model, iter, text)
            if index is None:
                return False
            elif index not in currIndices:
                currIndices[text] = index

        # We've found matching texts, try to match the colours and fonts as best we can
        colourIndices = set()
        fontIndices = set()
        toggleIndices = set()
        pixbufIndices = set()
        knownIndices = set(currIndices.values())
        for renderer in renderers:
            if isinstance(renderer, gtk.CellRendererText):
                text = renderer.get_property("text")
                if text is None:
                    continue
                textIndex = currIndices.get(text)
                if textIndex is None:
                    continue
                
                colour = renderer.get_property("background-gdk")
                colourIndex = self.findMatchingIndex(model, iter, colour, 
                                                     knownIndices, colourIndices, self.colourMatches)
                if colourIndex is not None:
                    colourIndices.add(colourIndex)
                    knownIndices.add(colourIndex)
                    
                font = renderer.get_property("font")
                fontIndex = self.findMatchingIndex(model, iter, font, 
                                                       knownIndices, fontIndices, self.textMatches)
                if fontIndex is not None:
                    fontIndices.add(fontIndex)
                    knownIndices.add(fontIndex)
                indices.append(ColumnTextIndexStore(model, textIndex, colourIndex, fontIndex))
            elif isinstance(renderer, gtk.CellRendererToggle):
                active = renderer.get_active()
                activeIndex = self.findMatchingIndex(model, iter, active, 
                                                     knownIndices, toggleIndices, self.boolMatches)
                if activeIndex is not None:
                    toggleIndices.add(activeIndex)
                    knownIndices.add(activeIndex)
                    indices.append(ColumnToggleIndexStore(model, activeIndex))
            elif isinstance(renderer, gtk.CellRendererPixbuf):
                stockId = renderer.get_property("stock-id")
                stockIndex = self.findMatchingIndex(model, iter, stockId, knownIndices, 
                                                    pixbufIndices, self.textMatches)
                if stockIndex is not None:
                    pixbufIndices.add(stockIndex)
                    knownIndices.add(stockIndex)
                    indices.append(ColumnPixbufIndexStore(model, stockIndex))

        return True # Causes foreach to exit

    def getTextIndex(self, model, iter, text):
        # May have markup involved, in which case "text" will have it stripped out
        textMarkupStr = ">" + text + "<"
        for index in range(model.get_n_columns()):
            givenText = str(model.get_value(iter, index))
            if givenText == text or (type(givenText) == types.StringType and textMarkupStr in givenText):
                return index        

    def findMatchingIndex(self, model, iter, info, knownIndices, prevIndices, matchMethod):
        for index in range(model.get_n_columns()):
            if index not in knownIndices and matchMethod(model, iter, index, info):
                return index

        # If we can't find a unique column, assume we're tied to a previous one
        for index in prevIndices:
            if matchMethod(model, iter, index, info):
                return index

    def textMatches(self, model, iter, index, text):
        givenText = model.get_value(iter, index)
        return type(givenText) == types.StringType and givenText.lower() == text.lower()

    def boolMatches(self, model, iter, index, value):
        givenValue = model.get_value(iter, index)
        return type(givenValue) == types.BooleanType and givenValue == value

    def colourMatches(self, model, iter, index, colour):
        givenText = model.get_value(iter, index)
        if type(givenText) != types.StringType:
            return False
        try:
            givenColour = gtk.gdk.color_parse(givenText)
            return self.coloursIdentical(colour, givenColour)
        except ValueError:
            return False

    def coloursIdentical(self, col1, col2):
        return col1.red == col2.red and col1.green == col2.green and col1.blue == col2.blue


class IdleScheduler:
    def __init__(self):
        self.idleHandler = None
        self.widgetMapping = {}
        self.widgetsForDescribe = {}
        self.allWidgets = []
        
    def register(self, widget):
        # So that we can order things correctly
        if not widget in self.allWidgets:
            self.allWidgets.append(widget)

    def monitor(self, monitorWidget, signals, prefix="", describeWidget=None, titleOnly=False):
        if describeWidget is None:
            describeWidget = monitorWidget
        for signal in signals:
            self.widgetMapping.setdefault(monitorWidget, {})[signal] = describeWidget, prefix, titleOnly
            monitorWidget.connect(signal, self.scheduleDescribeCallback, signal)
    
    def lookupWidget(self, widget, *args):
        signalMapping = self.widgetMapping.get(widget)
        for arg in args:
            if arg in signalMapping:
                return signalMapping.get(arg)

    def scheduleDescribeCallback(self, widget, *args):
        describeWidget, prefix, titleOnly = self.lookupWidget(widget, *args)
        self.scheduleDescribe(describeWidget, prefix, titleOnly)

    def scheduleDescribe(self, describeWidget, prefix="Showing ", titleOnly=False):
        otherPrefix, otherTitleOnly = self.widgetsForDescribe.get(describeWidget, (None, None))
        if otherTitleOnly is None or (otherTitleOnly and not titleOnly):
            self.widgetsForDescribe[describeWidget] = prefix, titleOnly
 
        if self.idleHandler is None:
            # Want it to have higher priority than e.g. PyUseCase replaying
            self.idleHandler = gobject.idle_add(self.describeUpdate, priority=gobject.PRIORITY_DEFAULT_IDLE - 1)

    def shouldDescribe(self, widget):
        if not widget.get_property("visible"):
            return False

        parent = widget.get_parent()
        if not parent:
            return True
        
        if parent in self.widgetsForDescribe:
            prefix, titleOnly = self.widgetsForDescribe.get(parent)
            # If we're describing the parent in full, and not just its title, we shouldn't redescribe the children
            if not titleOnly:
                return False

        if isinstance(parent, gtk.Notebook):
            currPage = parent.get_nth_page(parent.get_current_page())
            return currPage is widget
        else:
            return self.shouldDescribe(parent)
        
    def describeUpdate(self):
        for widget in sorted(self.widgetsForDescribe.keys(), lambda x,y: cmp(self.allWidgets.index(x), self.allWidgets.index(y))):
            prefix, titleOnly = self.widgetsForDescribe.get(widget)
            if self.shouldDescribe(widget):
                describe(widget, prefix=prefix)
        self.idleHandler = None
        self.widgetsForDescribe = {}
        return False

idleScheduler = IdleScheduler()
