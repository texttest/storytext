
# Experimental and rather basic support for Tkinter

import guiusecase, os, time, Tkinter, logging, re
from threading import Thread
from usecase import UseCaseScriptError

origTk = Tkinter.Tk
origToplevel = Tkinter.Toplevel

class WindowIdleManager:
    idle_methods = []
    timeout_methods = []
    handlers = []
    def __init__(self):
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
    def __init__(self, *args, **kw):
        origTk.__init__(self, *args, **kw)
        WindowIdleManager.__init__(self)
                
class Toplevel(WindowIdleManager, origToplevel):
    instances = []
    def __init__(self, *args, **kw):
        origToplevel.__init__(self, *args, **kw)
        WindowIdleManager.__init__(self)
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
    
class DestroyEvent(SignalEvent):
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "<Destroy>" ]

    def shouldRecord(self, event, *args):
        return SignalEvent.shouldRecord(self, event, *args) and event.widget is self.widget
    
    def setProgrammaticChange(self, val, *args, **kwargs):
        if val: # If we've been programmatically destroyed, we should stay that way...
            self.programmaticChange = val

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
        (Tkinter.Toplevel , [ DestroyEvent ]),
        (Tkinter.Entry    , [ EntryEvent ]),
        (Tkinter.Menu     , [ MenuEvent ])
        ]
    if os.name == "posix":
        eventTypes.append((Tkinter.Tk       , [ DestroyEvent ]))
    def createUIMap(self, uiMapFiles):
        return UIMap(self, uiMapFiles)
 
    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)

    def _createSignalEvent(self, eventName, eventDescriptor, widget, argumentParseData):
        for eventClass in self.findEventClassesFor(widget):
            if eventClass is not SignalEvent:
                return eventClass(eventName, eventDescriptor, widget)
        return SignalEvent(eventName, eventDescriptor, widget)


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
    def __init__(self):
        self.logger = logging.getLogger("gui log")
        self.windows = set()
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

    def getWidgetDescription(self, widget):
        if isinstance(widget, (Tkinter.Frame, Tkinter.Scrollbar)):
            return ""
        if isinstance(widget, Tkinter.Button):
            text = "Button"
            labelText = getWidgetOption(widget, "text")
            if labelText:
                text += " '" + labelText + "'"
            return text
        elif isinstance(widget, Tkinter.Label):
            text = "'" + getWidgetOption(widget, "text") + "'"
            bg = getWidgetOption(widget, "bg")
            if bg and bg != self.getDefaultLabelBackground(widget):
                text += " (" + bg + ")"
            return text
        elif isinstance(widget, Tkinter.Entry):
            text = "Text entry"
            entryText = widget.get()
            if entryText:
                text += " (set to '" + entryText + "')"
            return text
        elif isinstance(widget, Tkinter.Menu):
            endIndex = widget.index(Tkinter.END)
            text = "Menu:\n"
            for i in range(endIndex + 1):
                text += "  " + self.getMenuItemDescription(widget, i) + "\n"
            return text
        elif isinstance(widget, Tkinter.Text):
            header = "=" * 10 + " Text " + "=" * 10        
            return header + "\n" + widget.get("1.0", Tkinter.END).rstrip() + "\n" + "=" * len(header)
        else:
            return "A widget of type '" + widget.__class__.__name__ + "'" # pragma: no cover - should be unreachable

    def getMenuItemDescription(self, widget, index):
        typeName = widget.type(index)
        if typeName in [ "cascade", "command" ]:
            return widget.entrycget(index, "label")
        elif typeName == "separator":
            return "---"
        else:
            return ">>>"
