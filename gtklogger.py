
"""
The basic mission of this module is to provide a standard textual output of GTK GUI elements,
to aid in text-based UI testing for GTK
"""

import logging, gtk, locale, operator, types

def describe(widget, customDescribers={}):
    describer = Describer(customDescribers)
    describer(widget)

class Describer:
    logger = None
    supportedWidgets = [ gtk.Label, gtk.CheckButton, gtk.Button, gtk.Table, gtk.Frame, gtk.Expander, gtk.Notebook,
                         gtk.TreeView, gtk.ComboBoxEntry, gtk.Entry, gtk.TextView, gtk.Container, gtk.Separator, gtk.Image ]
    cachedDescribers = {}    
    def __init__(self, customDescribers):
        if not Describer.logger:
            Describer.logger = logging.getLogger("gui log")
        self.customDescribers = customDescribers
        
    def __call__(self, widget):
        if self.logger.isEnabledFor(logging.INFO):
            if isinstance(widget, gtk.Window):
                self.describeWindow(widget)
            else:
                self.logger.info(self.getDescription(widget))

    def getDescription(self, widget):
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
            panedSeparator = "-" * 30
            if isinstance(container, gtk.VPaned):
                panedSeparator += " (horizontal pane separator)"
            else:
                panedSeparator += " (vertical pane separator)"
            return "\n\n" + panedSeparator + "\n"
        else:
            return "\n"
        
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
        try:
            return container.get_label_widget().get_text()
        except AttributeError:
            return container.get_label_widget().get_child().get_text()

    def getExpanderDescription(self, expander):
        label = self.getLabelText(expander)
        text = "Expander '" + label + "':\n"
        # Last child is the label :)
        for child in expander.get_children()[:-1]:
            text += "-> " + self.getDescription(child) + "\n"
        return text.rstrip()
    
    def getFrameDescription(self, frame):
        label = self.getLabelText(frame)
        frameText = "....." + label + "......\n"
        # Frame's last child is the label :)
        for child in frame.get_children()[:-1]:
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
        text = entry.get_text()
        if text:
            return "Text entry (set to '" + text + "')"
        else:
            return "Text entry"

    def getNotebookDescription(self, notebook):
        tabNames = []
        notebook.connect("switch-page", self.describeNotebookPage)
        message = ""
        for child in notebook.get_children():
            if child.get_property("visible"):
                name = notebook.get_tab_label_text(child)
                tabNames.append(name)
                              
        index = notebook.get_current_page()
        return "Tabs showing : " + ", ".join(tabNames) + "\n" + self.getCurrentNotebookPageDescription(notebook, index)

    def getCurrentNotebookPageDescription(self, notebook, index):
        page = notebook.get_nth_page(index)
        tabName = notebook.get_tab_label_text(page)
        return "\nViewing notebook page for '" + tabName + "'\n" + self.getDescription(page)

    def describeNotebookPage(self, notebook, ptr, pageNum, *args):
        self.logger.info(self.getCurrentNotebookPageDescription(notebook, pageNum))
        
    def getTreeViewDescription(self, view):
        describer = self.cachedDescribers.setdefault(view, TreeViewDescriber(view))
        return describer.getDescription()
                    
    def getCheckButtonDescription(self, button):
        group = "Check"
        if isinstance(button, gtk.RadioButton):
            group = "Radio"
        text = group + " button '" + button.get_label() + "'"
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
        self.buffer.connect_after("insert-text", self.describeChange)
        self.name = view.get_name()

    def getDescription(self):
        header = "=" * 10 + " " + self.name + " " + "=" * 10        
        return "\n" + header + "\n" + self.getContents().strip() + "\n" + "=" * len(header)

    def describeChange(self, *args):
        Describer.logger.info(self.getDescription())

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


# Complicated enough to need its own class...
class TreeViewDescriber:
    def __init__(self, view):
        self.view = view
        self.model = view.get_model()
        self.modelIndices = []
        baseModel = self.getBaseModel()
        baseModel.connect_after("row-inserted", self.describeInsertion)
        baseModel.connect_after("row-deleted", self.describeDeletion)
        self.renderHandler = None
        self.changeHandler = None

    def getBaseModel(self):
        # Don't react to visibility changes with TreeModelFilter
        try:
            return self.model.get_model()
        except AttributeError:
            return self.model

    def getDescription(self, context="Showing"):
        columns = self.view.get_columns()
        titles = " , ".join([ column.get_title() for column in columns ])
        message = "\n" + context + " " + self.view.get_name() + " with columns: " + titles + "\n"
        if len(self.modelIndices) == 0:
            self.modelIndices = self.getModelIndices()
        return message + self.getSubTreeDescription(self.model.get_iter_root(), 0).rstrip()
    
    def getSubTreeDescription(self, iter, indent):
        if iter is not None and len(self.modelIndices) == 0:
            return "ERROR: Could not find the relevant column IDs, so cannot describe tree view!"
        message = ""
        while iter is not None:
            data = " | ".join([ self.model.get_value(iter, col) for col in self.modelIndices ]) 
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
        texts = self.getTextInRenderers()
        indices = []
        if len(texts) > 0:
            self.model.foreach(self.addIndicesFromIter, (texts, indices))
        return indices

    def getTextInRenderers(self):
        texts = []
        for column in self.view.get_columns():
            for renderer in column.get_cell_renderers():
                text = renderer.get_property("text")
                if text:
                    texts.append(text)
        return texts

    def addIndicesFromIter(self, model, path, iter, userdata):
        texts, indices = userdata
        currIndices = []
        for text in texts:
            index = self.getMatchingIndex(model, iter, text)
            if index is None:
                return False
            elif index not in currIndices:
                currIndices.append(index)

        indices += currIndices
        return True # Causes foreach to exit

    def getMatchingIndex(self, model, iter, text):
        # May have markup involved, in which case "text" will have it stripped out
        textMarkupStr = ">" + text + "<"
        for index in range(model.get_n_columns()):
            givenText = model.get_value(iter, index)
            if givenText == text or (type(givenText) == types.StringType and textMarkupStr in givenText):
                return index        

    def describeInsertion(self, model, *args):
        # Row is blank when inserted, describe it after the next change
        self.changeHandler = model.connect_after("row-changed", self.describeChange)

    def describeChange(self, model, *args):
        self.describeUpdate("After insertion :")
        model.disconnect(self.changeHandler)

    def describeDeletion(self, *args):
        self.describeUpdate("After deletion :")
        
    def describeUpdate(self, context):
        if len(self.modelIndices) > 0:
            Describer.logger.info(self.getDescription(context))
        else:
            # If we didn't have them before, we still won't have them, because the view isn't updated yet
            renderer = self.view.get_columns()[-1].get_cell_renderers()[-1]
            self.renderHandler = renderer.connect("notify::text", self.describeRendererChange, context)        

    def describeRendererChange(self, renderer, paramSpec, context):
        self.modelIndices = self.getModelIndices()
        renderer.disconnect(self.renderHandler)
        self.describeUpdate(context)

