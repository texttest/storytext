
# Experimental and rather basic support for Tkinter

import guiusecase, os, time, Tkinter, logging, re
from threading import Thread
from usecase import UseCaseScriptError
from ndict import seqdict

origTk = Tkinter.Tk
origToplevel = Tkinter.Toplevel

class WindowIdleManager:
    idle_methods = []
    timeout_methods = []
    handlers = [] 
    def __init__(self):
        self.protocols = {}

    def protocol(self, protocolName, method):
        self.protocols[protocolName] = method

    def setUpHandlers(self):
        self.removeHandlers()
        idleThread = Thread(target=self.addIdleMethods)
        idleThread.run()

    def removeHandlers(self):
        for handler in self.handlers:
            self.after_cancel(handler)
        WindowIdleManager.handlers = []

    def addIdleMethods(self):
        if not self.winfo_ismapped():
            self.wait_visibility()
        for idle_method in self.idle_methods: 
            self.handlers.append(self.after_idle(idle_method))
        for args in self.timeout_methods:
            self.handlers.append(self.after(*args))

    def destroy(self):
        self.event_generate("<Destroy>") # Make sure we can record whatever it was caused this to be called



class Tk(WindowIdleManager, origTk):
    orig_protocol = origTk.protocol
    def __init__(self, *args, **kw):
        WindowIdleManager.__init__(self)
        origTk.__init__(self, *args, **kw)
        # Set up the handlers from the mainloop call, don't want things to happen before we're ready as seems quite possible
        origMainLoop = self.tk.mainloop
        def mainloop(n=0):
            self.setUpHandlers()
            self.tk.mainloop(n)
        def mainloopMethod(w, n=0):
            mainloop(n)
        Tkinter.Misc.mainloop = mainloopMethod
        Tkinter.mainloop = mainloop
                
class Toplevel(WindowIdleManager, origToplevel):
    instances = []
    orig_protocol = origToplevel.protocol
    def __init__(self, *args, **kw):
        WindowIdleManager.__init__(self)
        origToplevel.__init__(self, *args, **kw)
        self.setUpHandlers()
        Toplevel.instances.append(self)

Tkinter.Tk = Tk
Tkinter.Toplevel = Toplevel

origMenu = Tkinter.Menu

class Menu(origMenu):
    def __init__(self, *args, **kw):
        origMenu.__init__(self, *args, **kw)
        self.commands = {}

    def add_command(self, command=None, **kw):
        origMenu.add_command(self, command=command, **kw)
        self.commands[self.index(Tkinter.END)] = command

    def post(self, *args, **kw):
        origMenu.post(self, *args, **kw)
        describer = Describer()
        describer.describePopup(self)

Tkinter.Menu = Menu

origCheckbutton = Tkinter.Checkbutton

class Checkbutton(origCheckbutton):
    def __init__(self, *args, **kw):
        origCheckbutton.__init__(self, *args, **kw)
        self.variable = kw.get("variable")

Tkinter.Checkbutton = Checkbutton


class SignalEvent(guiusecase.GuiEvent):
    def __init__(self, eventName, eventDescriptor, widget, *args):
        guiusecase.GuiEvent.__init__(self, eventName, widget)
        self.eventDescriptors = eventDescriptor.split(",")

    def connectRecord(self, method):
        def handler(event, userEvent=self):
            return method(event, self)

        self.widget.bind(self.eventDescriptors[-1], handler, "+")
    
    def getChangeMethod(self):
        return self.widget.event_generate
    
    def generate(self, *args, **kw):
        for eventDescriptor in self.eventDescriptors:
            self.changeMethod(eventDescriptor, x=0, y=0, **kw) 

    @classmethod
    def getAssociatedSignatures(cls, widget):
        if isinstance(widget, Tkinter.Button):
            return [ "<Enter>,<Button-1>,<ButtonRelease-1>" ]
        else: # Assume anything else just gets clicked on
            return [ "<Button-1>", "<Button-2>", "<Button-3>" ]
    
class CanvasEvent(SignalEvent):
    def outputForScript(self, tkEvent, *args):
        items = self.widget.find_closest(self.widget.canvasx(tkEvent.x), self.widget.canvasy(tkEvent.y))
        tags = self.widget.gettags(items)
        if len(tags) == 0 or (len(tags) == 1 and tags[0] == "current"):
            itemName = str(items[0])
        else:
            itemName = tags[0]
        return self.name + " " + itemName

    def generate(self, tagOrId):
        item = self.findItem(tagOrId)
        x1, y1, x2, y2 = self.widget.bbox(item)
        x = x1 + x2 / 2
        y = y1 + y2 / 2
        self.changeMethod(self.eventDescriptors[0], x=x, y=y)

    def findItem(self, tagOrId):
        # Seems obvious to use find_withtag, but that fails totally when
        # the tag looks like an integer. So we make our own...
        for item in self.widget.find_all():
            if str(item) == tagOrId or tagOrId in self.widget.gettags(item):
                return item
        raise UseCaseScriptError, "Could not find canvas item '" + tagOrId + "'"


class WindowManagerDeleteEvent(guiusecase.GuiEvent):
    def __init__(self, eventName, eventDescriptor, widget, *args):
        guiusecase.GuiEvent.__init__(self, eventName, widget)
        self.recordMethod = None
        
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "WM_DELETE_WINDOW"
    
    def connectRecord(self, method):
        self.recordMethod = method
        self.widget.orig_protocol(self.getAssociatedSignal(self.widget), self.deleteWindow)

    def deleteWindow(self):
        self.recordMethod(self)
        protocolMethod = self.widget.protocols.get(self.getAssociatedSignal(self.widget))
        protocolMethod()
        
    def generate(self, *args, **kw):
        self.deleteWindow()


class ToggleEvent(SignalEvent):
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "<Button-1>.true", "<Button-1>.false" ]

    def __init__(self, eventName, eventDescriptor, widget, stateStr):
        SignalEvent.__init__(self, eventName, eventDescriptor, widget)
        self.enabling = stateStr == "true"

    def isStateChange(self):
        return True

    def shouldRecord(self, *args):
        # Variable hasn't been updated when we get here
        return self.widget.variable.get() != self.enabling


class EntryEvent(SignalEvent):
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "<KeyPress>,<KeyRelease>" ]
    
    def isStateChange(self):
        return True

    def generate(self, argumentString):
        self.widget.focus_force()
        self.widget.delete(0, Tkinter.END)
        self.widget.insert(Tkinter.END, argumentString)
        # Generate a keypress, just to trigger recording
        SignalEvent.generate(self, keysym="Right")

    def outputForScript(self, *args):
        return self.name + " " + self.widget.get()


class MenuEvent(guiusecase.GuiEvent):
    class CommandWithRecord:
        def __init__(self, index, event, command, method):
            self.index = index
            self.event = event
            self.command = command
            self.method = method

        def __call__(self):
            self.method(self.index, self.event)
            self.command()
                
    def __init__(self, eventName, eventDescriptor, widget, *args):
        guiusecase.GuiEvent.__init__(self, eventName, widget)

    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "select item" ]

    def connectRecord(self, method):
        endIndex = self.widget.index(Tkinter.END)
        for i in range(endIndex + 1):
            if self.widget.type(i) == "command":
                command = self.widget.commands[i]
                self.widget.entryconfigure(i, command=self.CommandWithRecord(i, self, command, method))

    def outputForScript(self, index, *args):
        return self.name + " " + self.widget.entrycget(index, "label")

    def findIndex(self, label):
        endIndex = self.widget.index(Tkinter.END)
        for i in range(endIndex + 1):
            if self.widget.type(i) == "command" and self.widget.entrycget(i, "label") == label:
                return i
        raise UseCaseScriptError, "Could not find item '" + label + "' in menu."

    def getChangeMethod(self):
        return self.widget.invoke

    def generate(self, argumentString):
        index = self.findIndex(argumentString)
        self.changeMethod(index)
        try:
            self.widget.unpost()
        except: # pragma: no cover - seems to happen under rather unpredictable circumstances
            # Yes it's ugly, the menu might not have been posted in the first place
            # That seems to throw some unprintable exception: trying to examine it
            # causes the program to exit with error code
            pass

def getWidgetOption(widget, optionName):
    try:
        return widget.cget(optionName)
    except:
        return ""

def getMenuParentOption(widget):
    parentMenuPath = widget.winfo_parent()
    parent = widget.nametowidget(parentMenuPath)
    if parent and isinstance(parent, Tkinter.Menu):
        endIndex = parent.index(Tkinter.END)
        for i in range(endIndex + 1):
            if parent.type(i) == "cascade":
                submenuName = parent.entrycget(i, "menu")
                if submenuName.endswith(widget.winfo_name()):
                    return parent, i
    return parent, -1

def getMenuParentLabel(widget, defaultLabel=""):
    parent, index = getMenuParentOption(widget)
    if index >= 0:
        return parent.entrycget(index, "label")
    elif isinstance(parent, Tkinter.Menubutton):
        return getWidgetOption(parent, "text")
    else:
        return defaultLabel

class UIMap(guiusecase.UIMap):
    def monitorWindow(self, window):
        if window not in self.windows:
            self.windows.append(window)
            self.logger.debug("Monitoring new window with title " + repr(window.title()))
            return self.monitor(window)
        else:
            return False

    def monitorChildren(self, widget, *args, **kw):
        for child in widget.winfo_children():
            self.monitor(child, *args, **kw)

    def findPossibleSectionNames(self, widget):
        return [ "Name=" + widget.winfo_name(), "Title=" + str(self.getTitle(widget)), 
                 "Label=" + self.getLabel(widget) ]
    
    def getTitle(self, widget):
        try:
            return widget.title()
        except AttributeError:
            pass

    def getLabel(self, widget):
        text = getWidgetOption(widget, "text")
        if text:
            return text
        elif isinstance(widget, Tkinter.Menu):
            return getMenuParentLabel(widget)
        return ""

    def isAutoGenerated(self, name):
        return re.match("[0-9]*L?$", name) or name == "tk"

    def getSectionName(self, widget):
        widgetName = widget.winfo_name()
        if not self.isAutoGenerated(widgetName): 
            return "Name=" + widgetName

        title = self.getTitle(widget)
        if title:
            return "Title=" + title
       
        label = self.getLabel(widget)
        if label:
            return "Label=" + label
        return "Type=" + widget.__class__.__name__


class ScriptEngine(guiusecase.ScriptEngine):
    eventTypes = [
        (Tkinter.Button      , [ SignalEvent ]),
        (Tkinter.Checkbutton , [ ToggleEvent ]),
        (Tkinter.Label       , [ SignalEvent ]),
        (Tkinter.Canvas      , [ CanvasEvent ]),
        (Tkinter.Toplevel    , [ WindowManagerDeleteEvent ]),
        (Tkinter.Tk          , [ WindowManagerDeleteEvent ]),
        (Tkinter.Entry       , [ EntryEvent ]),
        (Tkinter.Menu        , [ MenuEvent ])
        ]
    signalDescs = {
        "<Enter>,<Button-1>,<ButtonRelease-1>": "clicked",
        "<KeyPress>,<KeyRelease>": "edited text",
        "<Button-1>.true": "checked",
        "<Button-1>.false": "unchecked",
        "<Button-1>": "left-clicked",
        "<Button-2>": "middle-clicked",
        "<Button-3>": "right-clicked",
        "WM_DELETE_WINDOW": "closed"
        }
    columnSignalDescs = {}
    def createUIMap(self, uiMapFiles):
        return UIMap(self, uiMapFiles)
 
    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)

    def _createSignalEvent(self, eventName, eventDescriptor, widget, argumentParseData):
        for eventClass in self.findEventClassesFor(widget):
            if eventClass is not SignalEvent:
                return eventClass(eventName, eventDescriptor, widget, argumentParseData)
        return SignalEvent(eventName, eventDescriptor, widget)

    def getDescriptionInfo(self):
        return "Tkinter", "Tkinter", "actions", "http://infohost.nmt.edu/tcc/help/pubs/tkinter/"

    def addSignals(self, classes, widgetClass, currEventClasses, module):
        widget = widgetClass()
        signalNames = set()
        for eventClass in currEventClasses:
            signatures = eventClass.getAssociatedSignatures(widget)
            descs = set([ self.signalDescs.get(s, s) for s in signatures ])
            signalNames.update(descs)
        className = self.getClassName(widgetClass, module)
        classes[className] = sorted(signalNames)

    def getSupportedLogWidgets(self):
        return Describer.supportedWidgets


class UseCaseReplayer(guiusecase.UseCaseReplayer):
    def __init__(self, *args, **kw):
        guiusecase.UseCaseReplayer.__init__(self, *args, **kw)
        self.describer = Describer()

    def makeDescribeHandler(self, method):
        return self.makeIdleHandler(method)

    def makeIdleHandler(self, method):
        if Tkinter._default_root:
            return Tkinter._default_root.after_idle(method)
        else:
            Tk.idle_methods.append(method)
            return True # anything to show we've got something

    def findWindowsForMonitoring(self):
        return [ Tkinter._default_root ] + Toplevel.instances

    def handleNewWindows(self):
        self.describer.describeUpdates()
        guiusecase.UseCaseReplayer.handleNewWindows(self)

    def describeNewWindow(self, window):
        self.describer.describe(window)

    def removeHandler(self, handler):
        # Need to do this for real handlers, don't need it yet
        #Tkinter._default_root.after_cancel(handler)
        Tk.idle_methods = []

    def callHandleAgain(self):
        pass
        #self.idleHandler = Tkinter._default_root.after_idle(self.handleNewWindows)

    def makeTimeoutReplayHandler(self, method, milliseconds): 
        if Tkinter._default_root:
            return Tkinter._default_root.after(milliseconds, method)
        else:
            Tk.timeout_methods.append((milliseconds, method))
            return True # anything to show we've got something

    def makeIdleReplayHandler(self, method):
        return self.makeIdleHandler(method)

    def describeAndRun(self):
        Tkinter._default_root.update_idletasks()
        guiusecase.UseCaseReplayer.describeAndRun(self)
        self.enableReplayHandler()


class Describer:
    supportedWidgets = [ Tkinter.Checkbutton, Tkinter.Frame, Tkinter.LabelFrame, Tkinter.Scrollbar, 
                         Tkinter.Button, Tkinter.Label, Tkinter.Canvas, Tkinter.Entry, Tkinter.Menubutton, 
                         Tkinter.Menu, Tkinter.Text, Tkinter.Toplevel, Tkinter.Tk ]
    def __init__(self):
        self.logger = logging.getLogger("gui log")
        self.windows = set()
        self.widgetsWithState = seqdict()
        self.canvasWindows = set()
        self.defaultLabelBackground = None

    def describe(self, window):
        if window in self.windows:
            return
        self.windows.add(window)
        message = "-" * 10 + " Window '" + window.title() + "' " + "-" * 10
        self.logger.info("\n" + message)
        self.logger.info(self.getChildrenDescription(window))
        footerLength = min(len(message), 100) # Don't let footers become too huge, they become ugly...
        self.logger.info("-" * footerLength)

    def describeUpdates(self):
        defunctWidgets = []
        for widget, oldState in self.widgetsWithState.items():
            try:
                state = self.getState(widget)
                if state != oldState:
                    self.logger.info(self.getUpdatePrefix(widget) + self.getDescription(widget))
            except:
                # If the window where it existed has been removed, for example...
                defunctWidgets.append(widget)
        for widget in defunctWidgets:
            del self.widgetsWithState[widget]

    def addToDescription(self, desc, newText):
        if newText:
            if desc:
                desc += "\n"
            desc += newText.rstrip() + "\n"
        return desc

    def getDescription(self, widget):
        desc = ""
        desc = self.addToDescription(desc, self.getWidgetDescription(widget))
        desc = self.addToDescription(desc, self.getChildrenDescription(widget))
        return desc.rstrip()
    
    def getPackSlavesDescription(self, widget, slaves):
        packSlaves = widget.pack_slaves()
        if len(packSlaves) == 0:
            return ""
        sideGroups = {}
        for slave in packSlaves:
            try:
                info = slave.pack_info()
                slaves.add(slave)
                sideGroups.setdefault(self.getSide(slave, info), []).append(self.getDescription(slave))
            except Tkinter.TclError: 
                # Weirdly, sometimes get things in here that then deny they know anything about packing...
                pass

        menuDesc = "\n\n".join(sideGroups.get("Menus", []))
        topDesc = "\n".join(sideGroups.get(Tkinter.TOP, []))
        bottomDesc = "\n".join(list(reversed(sideGroups.get(Tkinter.BOTTOM, []))))
        horizDesc = " , ".join(sideGroups.get(Tkinter.LEFT, []) + list(reversed(sideGroups.get(Tkinter.RIGHT, []))))
        desc = self.addToDescription(topDesc, menuDesc)
        desc = self.addToDescription(desc, horizDesc)
        return self.addToDescription(desc, bottomDesc)

    def getSide(self, slave, info):
        # Always show menu buttons vertically as their menus invariably take vertical space
        if isinstance(slave, Tkinter.Menubutton):
            return "Menus"
        else:
            return info.get("side")

    def getGridSlavesDescription(self, widget, slaves, children):
        row_count = widget.grid_size()[-1]
        gridDesc = ""
        for x in range(row_count):
            rowSlaves = filter(lambda w: w in children, widget.grid_slaves(row=x))
            slaves.update(rowSlaves)
            allDescs = map(self.getDescription, rowSlaves)
            gridDesc += " | ".join(reversed(allDescs)) + "\n"
        return gridDesc

    def isPopupMenu(self, child, parent):
        return isinstance(child, Tkinter.Menu) and not isinstance(parent, (Tkinter.Menu, Tkinter.Menubutton))

    def getChildrenDescription(self, widget):
        slaves = set()
        children = widget.winfo_children()
        desc = ""
        menuChildName = getWidgetOption(widget, "menu")
        if menuChildName:
            menuChild = widget.nametowidget(menuChildName)
            slaves.add(menuChild)
            desc = self.addToDescription(desc, self.getDescription(menuChild))
        gridDesc = self.getGridSlavesDescription(widget, slaves, children)
        packDesc = self.getPackSlavesDescription(widget, slaves)
        childDesc = ""
        for child in children:
            if child not in slaves and not self.isPopupMenu(child, widget) and not child in self.canvasWindows:
                childDesc = self.addToDescription(childDesc, self.getDescription(child))
        
        desc = self.addToDescription(desc, packDesc)
        desc = self.addToDescription(desc, gridDesc)
        desc = self.addToDescription(desc, childDesc)
        return desc.rstrip()

    def getDefaultLabelBackground(self, widget):
        if self.defaultLabelBackground is None:
            self.defaultLabelBackground = Tkinter.Label(widget.master).cget("bg")
        return self.defaultLabelBackground

    def getUpdatePrefix(self, widget):
        if isinstance(widget, Tkinter.Entry):
            return "Updated "
        else:
            return "\n"
    
    def getState(self, widget):
        if isinstance(widget, Tkinter.Entry):
            return self.getEntryState(widget)
        elif isinstance(widget, Tkinter.Text):
            return self.getTextState(widget)
        else:
            return self.getCanvasState(widget)
        
    def getWidgetDescription(self, widget):
        for widgetClass in self.supportedWidgets:
            if isinstance(widget, widgetClass):
                methodName = "get" + widgetClass.__name__ + "Description"
                return getattr(self, methodName)(widget)
        
        return "A widget of type '" + widget.__class__.__name__ + "'" # pragma: no cover - should be unreachable

    def getFrameDescription(self, widget):
        if getWidgetOption(widget, "bd"):
            return ".................."
        else:
            return ""

    def getMenubuttonDescription(self, widget):
        if len(widget.winfo_children()) == 0:
            return getWidgetOption(widget, "text") + " menu (empty)"
        else:
            return ""

    def getLabelFrameDescription(self, widget):
        return "....." + getWidgetOption(widget, "text") + "......"

    def getScrollbarDescription(self, widget):
        return ""

    def getButtonDescription(self, widget):
        text = "Button"
        labelText = getWidgetOption(widget, "text")
        if labelText:
            text += " '" + labelText + "'"
        return text

    def getCheckbuttonDescription(self, widget):
        text = "Check " + self.getButtonDescription(widget)
        if widget.variable.get():
            text += " (checked)"
        return text

    def getLabelDescription(self, widget):
        text = "'" + getWidgetOption(widget, "text") + "'"
        bg = getWidgetOption(widget, "bg")
        if bg and bg != self.getDefaultLabelBackground(widget):
            text += " (" + bg + ")"
        return text

    def getEntryDescription(self, widget):
        text = "Text entry"
        state = self.getEntryState(widget)
        self.widgetsWithState[widget] = state
        if state:
            text += " (set to '" + state + "')"
        return text

    def getEntryState(self, widget):
        text = widget.get()
        showChar = getWidgetOption(widget, "show")
        if showChar:
            return showChar * len(text)
        else:
            return text

    def getMenuDescription(self, widget, rootDesc="Root"):
        endIndex = widget.index(Tkinter.END)
        text = getMenuParentLabel(widget, rootDesc)
        text += " menu:\n"
        for i in range(endIndex + 1):
            text += "  " + self.getMenuItemDescription(widget, i) + "\n"
        return text

    def describePopup(self, menu):
        self.logger.info(self.getMenuDescription(menu, rootDesc="Posting popup").rstrip())

    def getTextDescription(self, widget):
        state = self.getTextState(widget)
        self.widgetsWithState[widget] = state
        return self.headerAndFooter(state, "Text")

    def getTextState(self, widget):
        return widget.get("1.0", Tkinter.END).rstrip()

    def headerAndFooter(self, text, title):
        header = "=" * 10 + " " + title + " " + "=" * 10
        return header + "\n" + text.rstrip() + "\n" + "=" * len(header)

    def getMenuItemDescription(self, widget, index):
        typeName = widget.type(index)
        if typeName in [ "cascade", "command" ]:
            text = widget.entrycget(index, "label")
            if typeName == "cascade":
                text += " (+)"
            return text
        elif typeName == "separator":
            return "---"
        else:
            return ">>>"

    def getCanvasDescription(self, widget):
        state = self.getCanvasState(widget)
        self.widgetsWithState[widget] = state
        return self.headerAndFooter(state, "Canvas")

    def getCanvasState(self, widget):
        items = set()
        allDescs = {}
        for item in widget.find_all():
            if item not in items:
                desc = self.getCanvasItemDescription(widget, item)
                allDescs.setdefault(self.getRow(widget, item, allDescs.keys()), []).append(desc)
                for enclosedItem in self.findEnclosedItems(widget, item):
                    items.add(enclosedItem)
                    desc = "  " + self.getCanvasItemDescription(widget, enclosedItem)
                    allDescs.setdefault(self.getRow(widget, enclosedItem, allDescs.keys()), []).append(desc)
        return self.arrange(allDescs)

    def getRow(self, widget, item, existingRows):
        x1, y1, x2, y2 = widget.bbox(item)
        for attempt in [ y1, y1 - 1, y1 + 1 ]:
            if attempt in existingRows:
                return attempt
        return y1

    def getCanvasItemDescription(self, widget, item):
        itemType = widget.type(item)
        if itemType in ("rectangle", "oval", "polygon"):
            return itemType.capitalize() + " (" + widget.itemcget(item, "fill") + ")"
        elif itemType == "text":
            return "'" + widget.itemcget(item, "text") + "'"
        elif itemType == "window":
            windowWidgetName = widget.itemcget(item, "window")
            windowWidget = widget.nametowidget(windowWidgetName)
            self.canvasWindows.add(windowWidget) # Stop it being described by other means
            return self.getDescription(windowWidget)
        else: # pragma: no cover - not really supposed to happen
            return "A Canvas Item of type '" + itemType + "'"

    def findEnclosedItems(self, widget, item):
        bbox = widget.bbox(item)
        allItems = list(widget.find_enclosed(*bbox))
        if item in allItems:
            allItems.remove(item)
        return allItems

    def padColumns(self, allDescs):
        widths = self.getColumnWidths(allDescs)
        for descList in allDescs.values():
            for col, desc in enumerate(descList):
                if len(desc) < widths[col]:
                    descList[col] = desc.ljust(widths[col])

    def getColumnWidths(self, allDescs):
        widths = []
        for descList in allDescs.values():
            for col, desc in enumerate(descList):
                if col >= len(widths):
                    widths.append(len(desc))
                elif len(desc) >= widths[col]:
                    widths[col] = len(desc)
        return widths

    def arrange(self, allDescs):
        self.padColumns(allDescs)
        text = ""
        for row in sorted(allDescs.keys()):
            text += " , ".join(allDescs[row]) + "\n"
        return text
            
