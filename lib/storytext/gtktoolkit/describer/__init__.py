
"""
The basic mission of this module is to provide a standard textual output of GTK GUI elements,
to aid in text-based UI testing for GTK
"""

import logging, gtk, gobject, locale, operator

from treeviews import performTreeViewInterceptions, TreeViewDescriber, treeModelSignals
from images import performImageInterceptions, ImageDescriber

# Magic constants, can't really use default priorities because file choosers use them in many GTK versions.
PRIORITY_STORYTEXT_IDLE = gobject.PRIORITY_DEFAULT_IDLE + 20
PRIORITY_STORYTEXT_REPLAY_IDLE = gobject.PRIORITY_DEFAULT_IDLE + 15
PRIORITY_STORYTEXT_LOG_IDLE = gobject.PRIORITY_DEFAULT_IDLE + 10

origEntryCompletion = gtk.EntryCompletion

class EntryCompletion(origEntryCompletion):
    def __init__(self, *args, **kw):
        origEntryCompletion.__init__(self, *args, **kw)
        self.realMatchFunction = None
        self.realMatchFunctionArgs = ()

    def getText(self, iter):
        return self.get_model().get_value(iter, self.get_text_column())

    def matches(self, key, iter):
        if self.realMatchFunction:
            return self.realMatchFunction(self, key, iter, *self.realMatchFunctionArgs)
        else:
            # Default implementation, lifted from PyGTK documentation
            return key and self.getText(iter).startswith(key)

    def getCurrentTexts(self):
        key = self.get_entry().get_text()
        texts = []
        def getTextIfMatching(model, path, iter):
            if self.matches(key, iter):
                texts.append(self.getText(iter))
        self.get_model().foreach(getTextIfMatching)
        return texts

    def set_match_func(self, function, *args):
        self.realMatchFunction = function
        self.realMatchFunctionArgs = args
        origEntryCompletion.set_match_func(self, function)


def performEntryCompletionInterceptions():
    gtk.EntryCompletion = EntryCompletion

def isEnabled():
    return Describer.isEnabled()

def describe(widget, prefix="Showing "):
    if isEnabled():
        setMonitoring()
        describer = describerClass(prefix)
        describer(widget)

def setMonitoring(loggingEnabled=False):
    global idleScheduler
    if not idleScheduler:
        idleScheduler = IdleScheduler(loggingEnabled)
        if loggingEnabled:
            performEntryCompletionInterceptions()
            performTreeViewInterceptions()
            performImageInterceptions()

def describeNewWindow(*args):
    return idleScheduler.describeNewWindow(*args)

class Describer:
    logger = None
    supportedWidgets = [ gtk.Label, gtk.ToggleToolButton, gtk.ToolButton, gtk.SeparatorToolItem,
                         gtk.ToolItem, gtk.ToggleButton, gtk.Button, gtk.Table, gtk.Frame, gtk.FileChooser,
                         gtk.ProgressBar, gtk.Expander, gtk.Notebook, gtk.TreeView, gtk.CellView, gtk.ComboBoxEntry,
                         gtk.ComboBox, gtk.CheckMenuItem, gtk.SeparatorMenuItem, gtk.MenuItem, gtk.SpinButton, 
                         gtk.Entry, gtk.TextView, gtk.MenuBar, gtk.Toolbar, gtk.Container, gtk.Separator, gtk.Image ]
    cachedDescribers = {}
    @classmethod
    def createLogger(cls):
        if not cls.logger:
            cls.logger = logging.getLogger("gui log")

    @classmethod
    def isEnabled(cls):
        cls.createLogger()
        return cls.logger.isEnabledFor(logging.INFO)
    
    def __init__(self, prefix):
        self.prefix = prefix
        self.indent = 0
        
    def __call__(self, widget):
        if self.isEnabled():
            idleScheduler.monitorBasics(widget)
            if isinstance(widget, gtk.Window):
                self.describeWindow(widget)
            else:
                self.logger.info(self.getDescription(widget))

    def getDescription(self, widget):
        baseDesc = self.getBasicDescription(widget)
        propDesc = self.getPropertyDescription(widget)
        if propDesc == "" or not baseDesc.startswith("\n") or baseDesc.count("\n") <= 1: # single line
            return baseDesc + propDesc
        else:
            firstEndline = baseDesc.find("\n", 1) # ignore leading newline
            return baseDesc[:firstEndline] + propDesc + baseDesc[firstEndline:]

    def getPropertyDescription(self, widget):
        properties = []
        # If we're a stock button, don't get the image, which will vary between themes
        if not isinstance(widget, gtk.Button) or not self.isStock(widget):
            imageDescriber = ImageDescriber()
            imageDesc = imageDescriber.getInbuiltImageDescription(widget)
            if imageDesc:
                properties.append(imageDesc)
        if not widget.get_property("sensitive"):
            properties.append("greyed out")

        accelerator = self.getAccelerator(widget)
        if accelerator:
            properties.append("accelerator '" + accelerator + "'")
        tooltip = self.getTooltipText(widget)
        if tooltip:
            properties.append("tooltip '" + tooltip + "'")
        if len(properties):
            return " (" + ", ".join(properties) + ")"
        else:
            return ""

    def getAccelerator(self, widget):
        action = widget.get_action()
        if action:
            accelPath = action.get_accel_path()
            if accelPath:
                keyVal, modifier = gtk.accel_map_lookup_entry(accelPath)
                if keyVal:
                    return gtk.accelerator_get_label(keyVal, modifier)
        return ""

    def getTooltipText(self, widget):
        if isinstance(widget, gtk.ToolButton):
            return self.getTooltipText(widget.get_child())
        else:
            return widget.get_tooltip_text()

    def getSeparator(self, container):
        if isinstance(container, gtk.HBox) or isinstance(container, gtk.HButtonBox) or isinstance(container, gtk.MenuBar):
            return " , "
        elif isinstance(container, gtk.Paned):
            return self.getPanedSeparator(container)
        else:
            return "\n"

    def getPanedSeparator(self, paned):
        panedSeparator = "-" * 30
        name = paned.get_name()
        if name.startswith("Gtk"):
            name = "pane separator"
        if isinstance(paned, gtk.VPaned):
            panedSeparator += " (horizontal " + name + ")"
        else:
            panedSeparator += " (vertical " + name + ")"
        return "\n\n" + panedSeparator + "\n"

    def getVisibleChildren(self, container):
        return filter(lambda c: c.get_property("visible"), container.get_children())
        
    def getContainerDescription(self, container):
        idleScheduler.monitor(container, [ "add", "remove" ], "Updated : ")
        messages = [ self.getDescription(widget) for widget in self.getVisibleChildren(container) ]
        sep = self.getSeparator(container)
        if "\n" in sep:
            return sep.join(messages)
        else:
            # Horizontal, don't allow for extra new lines...
            return sep.join([ m.strip() for m in messages ])

    def getBasicDescription(self, widget):
        for widgetClass in self.supportedWidgets:
            if isinstance(widget, widgetClass):
                methodName = "get" + widgetClass.__name__ + "Description"
                return getattr(self, methodName)(widget)

        return "A widget of type '" + widget.__class__.__name__ + "'" # pragma: no cover - should never happen

    def getLabelDescription(self, widget):
        idleScheduler.monitor(widget, [ "notify::label" ], "\nChanging " + widget.get_name() + " to: ")
        text = "'" + widget.get_label() + "'"
        if "Changing" in self.prefix:
            return self.prefix + text
        else:
            return text

    def getCellViewDescription(self, cellview):
        texts = []
        for renderer in cellview.get_cell_renderers():
            if isinstance(renderer, gtk.CellRendererText):
                texts.append("'" + renderer.get_property("text") + "'")
        return " , ".join(texts)

    def getToggleButtonType(self, button):
        if isinstance(button, gtk.RadioButton):
            return "Radio"
        elif self.isCheckWidget(button):
            return "Check"
        else:
            return "Toggle"

    def getToggleButtonDescription(self, button):
        idleScheduler.monitor(button, [ "toggled" ], "Toggled ")
        text = ""
        if self.prefix != "Showing ":
            text += self.prefix
        text += self.getToggleButtonType(button)
        text += " button '" + button.get_label() + "'" + self.getActivePostfix(button)
        return text

    def isCheckWidget(self, widget):
        return isinstance(widget, gtk.CheckButton) or isinstance(widget, gtk.CheckMenuItem)
               
    def getActivePostfix(self, widget):
        if widget.get_active():
            if self.isCheckWidget(widget):
                return " (checked)"
            else:
                return " (depressed)"
        else:
            return ""

    def getCheckDescription(self, checkWidget, basicDesc, toggleDesc):
        text = ""
        if self.prefix != "Showing ":
            text += "\n" + self.prefix + " "
        idleScheduler.monitor(checkWidget, [ "toggled" ], toggleDesc)
        return text + basicDesc + self.getActivePostfix(checkWidget)

    def getCheckMenuItemDescription(self, menuitem):
        return self.getCheckDescription(menuitem, self.getMenuItemDescription(menuitem), "Toggled Menu Item")

    def getToggleToolButtonDescription(self, toolitem):
        return self.getCheckDescription(toolitem, self.getToolButtonDescription(toolitem), "Toggled Toolbar Item")
        
    def getMenuItemDescription(self, menuitem):
        text = " " * self.indent + self.getBasicDescription(menuitem.get_child())
        if menuitem.get_submenu():
            text += " (+)"
        return text

    def getProgressBarDescription(self, progressBar):
        idleScheduler.monitor(progressBar, [ "notify::text", "notify::fraction" ])
        message = "Progress bar set to fraction " + str(progressBar.get_fraction())
        if progressBar.get_text():
            message += ", text '" + progressBar.get_text() + "'"
        if self.prefix == "Showing ": # initial
            return message
        else:
            return "\n" + message

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
            return True, self.getDescription(labelWidget)
        else:
            return False, ""

    def getExpanderDescription(self, expander):
        labelExisted, label = self.getLabelText(expander)
        text = "Expander: " + label + "\n"
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

    def getSeparatorMenuItemDescription(self, separator):
        return " " * (self.indent + 2) + "-" * 4

    def getSeparatorToolItemDescription(self, separator):
        return self.getSeparatorMenuItemDescription(separator)

    def getSeparatorDescription(self, separator):
        basic = "-" * 15
        if isinstance(separator, gtk.VSeparator):
            return basic + " (vertical)"
        else:
            return basic

    def collectEntries(self, model, path, iter, allEntries):        
        allEntries.append(model.get_value(iter, 0))

    def getDropDownDescription(self, combobox):
        allEntries = []
        model = combobox.get_model()
        if model:
            model.foreach(self.collectEntries, allEntries)
            idleScheduler.monitor(model, treeModelSignals, "Updated drop-down list in ", combobox)
        return " (drop-down list containing " + repr(allEntries) + ")"

    def getComboBoxEntryDescription(self, combobox):
        return self.getDescription(combobox.get_child()) + self.getDropDownDescription(combobox)
    
    def getComboBoxDescription(self, combobox):
        changePrefix = "Changed selection in "
        idleScheduler.monitor(combobox, [ "changed" ], changePrefix)
        text = ""
        if self.prefix != "Showing ":
            text += self.prefix
            name = combobox.get_name()
            if not name.startswith("Gtk"): # auto-generated
                text += "'" + name + "' "
        text += "Combo Box"
        iter = combobox.get_active_iter()
        if iter is not None:
            value = combobox.get_model().get_value(iter, 0)
            if value:
                text += " (selected '" + value + "')"
        if self.prefix != changePrefix:
            text += self.getDropDownDescription(combobox)
        return text

    def getTextViewDescription(self, view):
        describer = self.cachedDescribers.setdefault(view, TextViewDescriber(view))
        return describer.getDescription()

    def getEntryDescription(self, entry):
        idleScheduler.monitor(entry, [ "changed" ], "Edited ")
        text = ""
        if self.prefix != "Showing ":
            text += self.prefix + "'" + entry.get_name() + "' "
        text += self.getTypeDescription(entry)
        entryText = entry.get_text()
        if entryText:
            text += " (set to '" + entryText + "')"
        if self.prefix == "Edited ":
            text += self.getCompletionDescription(entry.get_completion())
        return text

    def getCompletionDescription(self, completion):
        if completion:
            texts = completion.getCurrentTexts()
            if len(texts):
                text = "completions " + repr(texts)
                if completion.get_inline_completion():
                    return " (inline " + text + ")"
                else:
                    return " (" + text + ")"
        return ""

    def getTypeDescription(self, entry):
        if isinstance(entry, gtk.SpinButton):
            return "Spin button entry"
        else:
            return "Text entry"

    def getSpinButtonDescription(self, spinner):
        desc = self.getEntryDescription(spinner)
        if self.prefix == "Showing ":
            adj = spinner.get_adjustment()
            desc += " (min=" + str(adj.lower) + ", max=" + str(adj.upper) + \
                ", step=" + str(adj.step_increment) + ")"
        return desc

    def getFileChooserDescription(self, fileChooser):
        if fileChooser.get_property("action") != gtk.FILE_CHOOSER_ACTION_SAVE:
            idleScheduler.monitor(fileChooser, [ "selection-changed" ], "Updated : ")
        text = "\n" + self.prefix + fileChooser.get_name().replace("Gtk", "")
        currFile = fileChooser.get_filename()
        if currFile:
            text += " (selected '" + currFile.replace("\\", "/") + "')"
        if self.prefix.startswith("Updated"):
            return text
        folders = fileChooser.list_shortcut_folders()
        if len(folders):
            text += "\nShortcut folders (" + repr(len(folders)) + ") :"
            for folder in folders:
                text += "\n- " + folder.replace("\\", "/")
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
        describer = self.cachedDescribers.setdefault(view, TreeViewDescriber(view, idleScheduler))
        return describer.getDescription(self.prefix)

    def getImageDescription(self, image):
        describer = ImageDescriber()
        return describer.getDescription(image)

    def getMenuBarDescription(self, menubar):
        return "\nMenu Bar : " + self.getContainerDescription(menubar)

    def getToolbarDescription(self, toolbar):
        return self.getBarDescription(toolbar, "Tool")

    def getBarDescription(self, bar, name):
        text = "\n" + name + " Bar :\n"
        self.indent += 2
        text += self.getContainerDescription(bar)
        self.indent -= 2
        return text

    def getToolButtonDescription(self, toolButton):
        label = toolButton.get_label()
        if label:
            return " " * self.indent + label
        else:
            return " " * self.indent + "Tool button"

    def getToolItemDescription(self, item):
        return " " * self.indent + self.getDescription(item.get_child())

    def getButtonDescription(self, button):
        if isinstance(button, gtk.LinkButton):
            text = "Link button"
        elif self.isStock(button):
            text = "Stock Button"
        else:
            text = "Button"
        labelText = button.get_label()
        if labelText:
            text += " '" + labelText + "'"
        return text
    
    def isStock(self, button):
        return button.get_use_stock() and gtk.stock_lookup(button.get_label()) is not None

    @classmethod
    def getBriefDescription(cls, widget):
        try:
            label = widget.get_property("label")
            if label:
                return label
        except TypeError:
            pass
        
        return widget.get_name()

    @classmethod
    def getWindowTitle(cls, widgetType, window):
        if window.get_property("type") == gtk.WINDOW_TOPLEVEL:
            return widgetType + " '" + str(window.get_title()) + "'"
        else:
            return "Popup Window"
        
    def describeWindow(self, window):
        updateDesc = "Changing title for"
        widgetType = window.__class__.__name__.capitalize()
        title = self.getWindowTitle(widgetType, window)
        if self.prefix == updateDesc:
            return self.logger.info("\n" + self.prefix + " " + title)

        idleScheduler.monitor(window, [ "notify::title" ], updateDesc, titleOnly=True)
        message = "-" * 10 + " " + title + " " + "-" * 10
        self.logger.info("\n" + message)
        if window.maximize_initially:
            self.logger.info("Window is maximized initially")
        if window.default_widget:
            self.logger.info("Default widget is '" + self.getBriefDescription(window.default_widget) + "'")
        elif window.focus_widget:
            self.logger.info("Focus widget is '" + self.getBriefDescription(window.focus_widget) + "'")
        
        self.logger.info(self.getContainerDescription(window))
        footerLength = min(len(message), 100) # Don't let footers become too huge, they become ugly...
        self.logger.info("-" * footerLength)


class TextViewDescriber:
    def __init__(self, view):
        self.buffer = view.get_buffer()
        idleScheduler.monitor(self.buffer, [ "insert-text" ], "", view)
        self.name = view.get_name()

    def getDescription(self):
        header = "=" * 10 + " " + self.name + " " + "=" * 10        
        return "\n" + header + "\n" + self.getContents().rstrip() + "\n" + "=" * len(header)

    def getContents(self):
        # Assumes it's impossible to get text into the UI that is invalid for the current locale encoding
        unicodeInfo = self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter())
        encoding = locale.getdefaultlocale()[1] or "utf-8"
        return unicodeInfo.encode(encoding, 'replace')


class IdleScheduler:
    def __init__(self, universalLogging=False):
        self.widgetMapping = {}
        self.allWidgets = []
        self.visibleWindows = []
        self.universalLogging = universalLogging
        self.reset()
        
    def reset(self):
        self.idleHandler = None
        self.widgetsForDescribe = {}
        self.disabledWidgets = set()
        self.enabledWidgets = set()
        
    def monitor(self, monitorWidget, signals, prefix="", describeWidget=None, titleOnly=False, priority=1):
        if describeWidget is None:
            describeWidget = monitorWidget
        # So that we can order things correctly
        if not describeWidget in self.allWidgets:
            self.allWidgets.append(describeWidget)
        usePriority = priority + int(titleOnly) * 100
        for signal in signals:
            self.widgetMapping.setdefault(monitorWidget, {})[signal] = describeWidget, prefix, titleOnly, usePriority
            monitorWidget.connect(signal, self.scheduleDescribeCallback, signal)

    def getChildWidgets(self, widget):
        if isinstance(widget, gtk.FileChooser):
            # Don't worry about internals of file chooser, which aren't really relevant
            return []

        if isinstance(widget, gtk.Container):
            return widget.get_children()
        else:
            return []

    def windowHidden(self, window, *args):
        if window in self.visibleWindows:
            self.visibleWindows.remove(window)
           
    def monitorBasics(self, widget):
        if isinstance(widget, gtk.Window):
            self.allWidgets.append(widget)
            # When a window is hidden, start again with monitoring
            widget.connect("hide", self.windowHidden)
            if widget.get_property("type") == gtk.WINDOW_POPUP:
                return # Popup windows can't change visibility or sensitivity, don't monitor them
        else:
            # Don't handle windows this way, showing and hiding them is a bit different
            self._monitorBasics(widget)

        for child in self.getChildWidgets(widget):
            self.monitorBasics(child)
            
    def _monitorBasics(self, widget):
        self.monitor(widget, [ "hide" ], prefix="Hiding")
        self.monitor(widget, [ "show" ], prefix="Showing ")
        
        action = widget.get_action()
        if not action:
            action = widget
        action.connect("notify::sensitive", self.storeSensitivityChange)

    def storeSensitivityChange(self, actionOrWidget, *args):
        desc = Describer.getBriefDescription(actionOrWidget)
        if actionOrWidget.get_property("sensitive"):
            if desc in self.disabledWidgets:
                self.disabledWidgets.remove(desc)
            else:
                self.enabledWidgets.add(desc)
        else:
            if desc in self.enabledWidgets:
                self.enabledWidgets.remove(desc)
            else:
                self.disabledWidgets.add(desc)
        self.tryEnableIdleHandler()
    
    def lookupWidget(self, widget, *args):
        signalMapping = self.widgetMapping.get(widget)
        for arg in args:
            if arg in signalMapping:
                return signalMapping.get(arg)

    def scheduleDescribeCallback(self, widget, *args):
        widgetData = self.lookupWidget(widget, *args)
        self.scheduleDescribe(*widgetData)

    def scheduleDescribe(self, widget, prefix="Showing ", titleOnly=False, priority=1):
        otherPrefix, otherTitleOnly, otherPriority = self.widgetsForDescribe.get(widget, (None, None, None))
        if otherPriority is None or (priority is not None and priority < otherPriority):
            self.widgetsForDescribe[widget] = prefix, titleOnly, priority

        self.tryEnableIdleHandler()
        
    def tryEnableIdleHandler(self):
        if self.idleHandler is None:
            # Low priority, to not get in the way of filechooser updates
            self.idleHandler = gobject.idle_add(self.describeUpdates, priority=PRIORITY_STORYTEXT_LOG_IDLE)

    def shouldDescribeUpdate(self, widget):
        if not widget.get_property("visible"):
            return False

        parent = widget.get_parent()
        if not parent:
            return True
        
        if parent in self.widgetsForDescribe:
            prefix, titleOnly, priority = self.widgetsForDescribe.get(parent)
            # If we're describing the parent in full, and not just its title, we shouldn't redescribe the children
            if not titleOnly:
                return False

        if isinstance(parent, gtk.Notebook):
            currPage = parent.get_nth_page(parent.get_current_page())
            return currPage is widget
        else:
            return self.shouldDescribeUpdate(parent)

    def sorted(self, widgets):
        return sorted(widgets, lambda x,y: cmp(self.allWidgets.index(x), self.allWidgets.index(y)))        

    def describeNewWindow(self, window):
        if window not in self.visibleWindows:
            self.visibleWindows.append(window)
            describe(window)
        
    def describeUpdates(self):
        if len(self.enabledWidgets) or len(self.disabledWidgets):
            Describer.logger.info("")
        if len(self.disabledWidgets):
            Describer.logger.info("Greyed out : " + ", ".join(sorted(self.disabledWidgets)))
        if len(self.enabledWidgets):
            Describer.logger.info("No longer greyed out : " + ", ".join(sorted(self.enabledWidgets)))

        for widget in self.sorted(self.widgetsForDescribe.keys()):
            prefix, titleOnly, priority = self.widgetsForDescribe.get(widget)
            if prefix == "Hiding":
                Describer.logger.info("Hiding the '" + Describer.getBriefDescription(widget) + "' widget")
            elif self.shouldDescribeUpdate(widget):
                describe(widget, prefix=prefix)

        self.reset()
        return False

idleScheduler = None

describerClass = Describer # Will get overridden if hildon is being used
