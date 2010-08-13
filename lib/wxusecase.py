import pdb

# Experimental and rather basic support for wx

import guiusecase, os, time, wx, logging
from usecase import UseCaseScriptError
#from ndict import seqdict

origApp = wx.App

class App(origApp):
    idle_methods = []
    def setUpHandlers(self):
        for idle_method in self.idle_methods:
            self.GetTopWindow().Bind(wx.EVT_IDLE, idle_method)

    def MainLoop(self):
        self.setUpHandlers()
        origApp.MainLoop(self)

wx.App = App
        
class WidgetAdapter(guiusecase.WidgetAdapter):
    def getChildWidgets(self):
        return self.widget.GetChildren()
        
    def getWidgetTitle(self):
        return self.widget.GetTitle()
        
    def getLabel(self):
        return self.widget.GetLabel()

    def isAutoGenerated(self, name):
        return self.widget.__class__.__name__.lower() == name

    def getName(self):
        return self.widget.GetName()

guiusecase.WidgetAdapter.adapterClass = WidgetAdapter

class FrameEvent(guiusecase.GuiEvent):
    def connectRecord(self, method):
        def handler(event):
            method(event, self)
            event.Skip()
        self.widget.Bind(wx.EVT_CLOSE, handler)
            
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Close"

    def generate(self, *args):
        self.widget.Close()

class ButtonEvent(guiusecase.GuiEvent):
    def connectRecord(self, method):
        def handler(event):
            method(event, self)
            event.Skip()
        self.widget.Bind(wx.EVT_BUTTON, handler)
            
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Press"

    def generate(self, *args):
        self.widget.Command(wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, self.widget.GetId())) 
        
class ListCtrlEvent(guiusecase.GuiEvent):
    def connectRecord(self, method):
        def handler(event):
            method(event, self)
            event.Skip()
        self.widget.Bind(wx.EVT_LIST_ITEM_SELECTED, handler)

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "ListCtrlSelect"

    def generate(self, argumentString):
        self._clearSelection()
        label_list = argumentString.split(',')
        for label in label_list:
            index = self._findIndex(label)
            self.widget.Select(index, 1)

    def _clearSelection(self):
        for i in range(self.widget.ItemCount):
            self.widget.Select(i, 0)

    def _findIndex(self, label):
        for i in range(self.widget.ItemCount):
            if self.widget.GetItemText(i) == label:
                return i
        raise UseCaseScriptError, "Could not find item '" + label + "' in ListCtrl."

    def outputForScript(self, *args):
        texts = []
        i = -1
        while True:
            i = self.widget.GetNextSelected(i)
            if i == -1:
                break
            else:
                texts.append(self.widget.GetItemText(i))
        return self.name + " " + ",".join(texts)
                

class UseCaseReplayer(guiusecase.UseCaseReplayer):
    def __init__(self, *args, **kw):
        guiusecase.UseCaseReplayer.__init__(self, *args, **kw)
        self.describer = Describer()

    def makeIdleHandler(self, method):
        if wx.GetApp():
            return wx.GetApp().Bind(wx.EVT_IDLE, method)
        else:
            wx.App.idle_methods.append(method)
            return True # anything to show we've got something
                
    def findWindowsForMonitoring(self):
        return wx.GetTopLevelWindows()

    def handleNewWindows(self, *args):
        #self.describer.describeUpdates()
        guiusecase.UseCaseReplayer.handleNewWindows(self)

    def describeNewWindow(self, window):
        self.describer.describe(window)

    def removeHandler(self, handler):
        # Need to do this for real handlers, don't need it yet
        wx.App.idle_methods = []


class ScriptEngine(guiusecase.ScriptEngine):
    eventTypes = [
        (wx.Frame       , [ FrameEvent ]),
        (wx.Button      , [ ButtonEvent ]),
        (wx.ListCtrl    , [ ListCtrlEvent ]),
        ]
    signalDescs = {
        "<<ListCtrlSelect>>": "select item",
        }
    columnSignalDescs = {} 
    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)

    def _createSignalEvent(self, eventName, eventDescriptor, widget, argumentParseData):
        for eventClass in self.findEventClassesFor(widget):
            if eventDescriptor in eventClass.getAssociatedSignatures(widget):
                return eventClass(eventName, widget, argumentParseData)
        
    def getDescriptionInfo(self):
        return "wxPython", "wx", "actions", "http://www.wxpython.org/docs/api/"

    def getDocName(self, className):
        return className + "-class"

    def addSignals(self, classes, widgetClass, currEventClasses, module):
        signalNames = set()
        for eventClass in currEventClasses:
            signatures = eventClass.getAssociatedSignatures(None)
            signalNames.update(signatures)
        className = self.getClassName(widgetClass, module)
        classes[className] = sorted(signalNames)

    def getSupportedLogWidgets(self):
        return Describer.statelessWidgets + Describer.stateWidgets

class Describer:
    statelessWidgets = [ wx.Button ]
    stateWidgets = []
    def __init__(self):
        self.logger = logging.getLogger("gui log")
        self.windows = set()

    def describe(self, window):
        if window in self.windows:
            return
        self.windows.add(window)
        message = "-" * 10 + " Window '" + window.GetTitle() + "' " + "-" * 10
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
    
    def getChildrenDescription(self, widget):
        slaves = set()
        children = widget.GetChildren()
        desc = ""
        for child in children:
            desc = self.addToDescription(desc, self.getDescription(child))
        
        return desc.rstrip()

    def getWidgetDescription(self, widget):
        for widgetClass in self.statelessWidgets + self.stateWidgets:
            if isinstance(widget, widgetClass):
                methodName = "get" + widgetClass.__name__ + "Description"
                return getattr(self, methodName)(widget)
        
        return "A widget of type '" + widget.__class__.__name__ + "'" # pragma: no cover - should be unreachable

    def getButtonDescription(self, widget):
        text = "Button"
        labelText = widget.GetLabel()
        if labelText:
            text += " '" + labelText + "'"
        return text
