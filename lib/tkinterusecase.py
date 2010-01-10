
# Experimental and rather basic support for Tkinter

import guiusecase, os, time, Tkinter, logging
from threading import Thread

origTk = Tkinter.Tk

class Tk(origTk):
    idle_methods = []
    timeout_methods = []
    def mainloop(self):
        idleThread = Thread(target=self.addIdleMethods)
        idleThread.run()
        origTk.mainloop(self)

    def addIdleMethods(self):
        self.wait_visibility()
        for idle_method in self.idle_methods: 
            self.after_idle(idle_method)
        for args in self.timeout_methods:
            self.after(*args)
        
        
Tkinter.Tk = Tk

class SignalEvent(guiusecase.GuiEvent):
    def __init__(self, eventName, eventDescriptor, widget, *args):
        guiusecase.GuiEvent.__init__(self, eventName, widget)
        self.eventDescriptors = eventDescriptor.split(",")

    def connectRecord(self, method):
        def handler(event, userEvent=self):
            return method(event, self)

        self.widget.bind(self.eventDescriptors[-1], handler, "+")

    def generate(self, argumentString):
        for eventDescriptor in self.eventDescriptors:
            self.widget.event_generate(eventDescriptor, x=0, y=0) 

def getWidgetOption(widget, optionName):
    try:
        return widget.cget(optionName)
    except:
        return ""


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
        return [ "Name=" + getWidgetOption(widget, "name"), "Title=" + str(self.getTitle(widget)), 
                 "Label=" + getWidgetOption(widget, "text") ]
    
    def getTitle(self, widget):
        try:
            return widget.title()
        except AttributeError:
            pass

    def getSectionName(self, widget):
        widgetName = getWidgetOption(widget, "name")
        if widgetName: 
            return "Name=" + widgetName

        title = self.getTitle(widget)
        if title:
            return "Title=" + title
       
        label = getWidgetOption(widget, "text")
        if label:
            return "Label=" + label
        return "Type=" + widget.__class__.__name__


class ScriptEngine(guiusecase.ScriptEngine):
    eventTypes = []
    def createUIMap(self, uiMapFiles):
        return UIMap(self, uiMapFiles)
 
    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)

    def _createSignalEvent(self, *args):
        return SignalEvent(*args)

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
        return [ Tkinter._default_root ]

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

    def describe(self, window):
        if window in self.windows:
            return
        self.windows.add(window)
        message = "-" * 10 + " Window '" + window.title() + "' " + "-" * 10
        self.logger.info("\n" + message)
        self.logger.info(self.getChildrenDescription(window))
        footerLength = min(len(message), 100) # Don't let footers become too huge, they become ugly...
        self.logger.info("-" * footerLength)

    def getChildrenDescription(self, widget):
        desc = ""
        for child in widget.winfo_children():
            widgetDesc = self.getWidgetDescription(child)
            if widgetDesc:
                desc += widgetDesc + "\n"
            desc += self.getChildrenDescription(child)
        return desc.rstrip()

    def getWidgetDescription(self, widget):
        if isinstance(widget, Tkinter.Frame):
            return ""
        if isinstance(widget, Tkinter.Button):
            text = "Button"
            labelText = getWidgetOption(widget, "text")
            if labelText:
                text += " '" + labelText + "'"
            return text
        else:
            return "A widget of type '" + widget.__class__.__name__ + "'" # pragma: no cover - should be unreachable
