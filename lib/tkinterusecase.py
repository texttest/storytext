
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
        self.setUpHandlers()
                
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

Tkinter.Menu = Menu

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


class EntryEvent(SignalEvent):
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "<KeyPress>,<KeyRelease>" ]
    
    def isStateChange(self):
        return True

    def generate(self, argumentString):
        self.widget.focus_force()
        self.widget.delete(0, Tkinter.END)
        for char in argumentString:
            SignalEvent.generate(self, keysym=char)

    def outputForScript(self, *args):
        return self.name + " " + self.widget.get()


class MenuEvent(guiusecase.GuiEvent):
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
                def commandWithRecord():
                    method(i, self)
                    command()

                self.widget.entryconfigure(i, command=commandWithRecord)

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
    return None, None

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
            parent, index = getMenuParentOption(widget)
            if parent:
                return parent.entrycget(index, "label")
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
        (Tkinter.Button   , [ SignalEvent ]),
        (Tkinter.Label    , [ SignalEvent ]),
        (Tkinter.Toplevel , [ WindowManagerDeleteEvent ]),
        (Tkinter.Tk       , [ WindowManagerDeleteEvent ]),
        (Tkinter.Entry    , [ EntryEvent ]),
        (Tkinter.Menu     , [ MenuEvent ])
        ]
    signalDescs = {
        "<Enter>,<Button-1>,<ButtonRelease-1>": "clicked",
        "<KeyPress>,<KeyRelease>": "edited text",
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
                return eventClass(eventName, eventDescriptor, widget)
        return SignalEvent(eventName, eventDescriptor, widget)

    def getDescriptionInfo(self):
        return "Tkinter", "Tkinter", "actions", "http://infohost.nmt.edu/tcc/help/pubs/tkinter/"

    def addSignals(self, classes, widgetClass, currEventClasses, module):
        try:
            widget = widgetClass()
        except:
            widget = None
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
    supportedWidgets = [ Tkinter.Frame, Tkinter.Scrollbar, Tkinter.Button, Tkinter.Label, 
                         Tkinter.Entry, Tkinter.Menu, Tkinter.Text, Tkinter.Toplevel, Tkinter.Tk ]
    def __init__(self):
        self.logger = logging.getLogger("gui log")
        self.windows = set()
        self.widgetsWithState = seqdict()
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
        for widget, oldState in self.widgetsWithState.items():
            state = self.getState(widget)
            if state != oldState:
                self.logger.info(self.getUpdatePrefix(widget) + self.getDescription(widget))

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
                sideGroups.setdefault(info.get("side"), []).append(self.getDescription(slave))
            except Tkinter.TclError: 
                # Weirdly, sometimes get things in here that then deny they know anything about packing...
                pass

        vertDesc = "\n".join(sideGroups.get(Tkinter.TOP, []) + list(reversed(sideGroups.get(Tkinter.BOTTOM, []))))
        horizDesc = " , ".join(sideGroups.get(Tkinter.LEFT, []) + list(reversed(sideGroups.get(Tkinter.RIGHT, []))))
        return self.addToDescription(vertDesc, horizDesc)

    def getGridSlavesDescription(self, widget, slaves, children):
        row_count = widget.grid_size()[-1]
        gridDesc = ""
        for x in range(row_count):
            rowSlaves = filter(lambda w: w in children, widget.grid_slaves(row=x))
            slaves.update(rowSlaves)
            allDescs = map(self.getDescription, rowSlaves)
            gridDesc += " | ".join(reversed(allDescs)) + "\n"
        return gridDesc

    def getChildrenDescription(self, widget):
        slaves = set()
        children = widget.winfo_children()
        gridDesc = self.getGridSlavesDescription(widget, slaves, children)
        packDesc = self.getPackSlavesDescription(widget, slaves)
        childDesc = ""
        for child in children:
            if child not in slaves:
                childDesc = self.addToDescription(childDesc, self.getDescription(child))
        
        desc = ""
        desc = self.addToDescription(desc, childDesc)
        desc = self.addToDescription(desc, packDesc)
        desc = self.addToDescription(desc, gridDesc)
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
            text = widget.get()
            showChar = getWidgetOption(widget, "show")
            if showChar:
                return showChar * len(text)
            else:
                return text
        else:
            return widget.get("1.0", Tkinter.END).rstrip()

    def getWidgetDescription(self, widget):
        for widgetClass in self.supportedWidgets:
            if isinstance(widget, widgetClass):
                methodName = "get" + widgetClass.__name__ + "Description"
                return getattr(self, methodName)(widget)
        
        return "A widget of type '" + widget.__class__.__name__ + "'" # pragma: no cover - should be unreachable

    def getFrameDescription(self, widget):
        return ""

    def getScrollbarDescription(self, widget):
        return ""

    def getButtonDescription(self, widget):
        text = "Button"
        labelText = getWidgetOption(widget, "text")
        if labelText:
            text += " '" + labelText + "'"
        return text

    def getLabelDescription(self, widget):
        text = "'" + getWidgetOption(widget, "text") + "'"
        bg = getWidgetOption(widget, "bg")
        if bg and bg != self.getDefaultLabelBackground(widget):
            text += " (" + bg + ")"
        return text

    def getEntryDescription(self, widget):
        text = "Text entry"
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        if state:
            text += " (set to '" + state + "')"
        return text

    def getMenuDescription(self, widget):
        endIndex = widget.index(Tkinter.END)
        parent, index = getMenuParentOption(widget)
        if parent:
            text = parent.entrycget(index, "label")
        else:
            text = "Root"
        text += " menu:\n"
        for i in range(endIndex + 1):
            text += "  " + self.getMenuItemDescription(widget, i) + "\n"
        return text

    def getTextDescription(self, widget):
        header = "=" * 10 + " Text " + "=" * 10
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return header + "\n" + state + "\n" + "=" * len(header)

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
