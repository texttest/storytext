
# Experimental and rather basic support for wx

import guishared, os, time, wx, logging
from definitions import UseCaseScriptError
from ordereddict import OrderedDict

origApp = wx.App

class App(origApp):
    idle_methods = []
    timeout_methods = []

    def setUpHandlers(self):
        for idle_method in self.idle_methods:
            wx.GetApp().Bind(wx.EVT_IDLE, idle_method)
        for milliseconds, timeout_method in self.timeout_methods:
            wx.CallLater(milliseconds, timeout_method)

    def MainLoop(self):
        self.setUpHandlers()
        origApp.MainLoop(self)

wx.App = App
        
origDialog = wx.Dialog
class DialogHelper:
    def ShowModal(self):
        self.uiMap.scriptEngine.replayer.runMainLoopWithReplay()
        origDialog.ShowModal(self)

class Dialog(DialogHelper, origDialog):
    pass

class WidgetAdapter(guishared.WidgetAdapter):
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

guishared.WidgetAdapter.adapterClass = WidgetAdapter

class SignalEvent(guishared.GuiEvent):
    def connectRecord(self, method):
        def handler(event):
            method(event, self)
            event.Skip()
        self.widget.Bind(self.event, handler)

    @classmethod
    def getAssociatedSignal(cls, widget):
        return cls.signal

class FrameEvent(SignalEvent):
    event = wx.EVT_CLOSE
    signal = 'Close'
            
    def getChangeMethod(self):
        return self.widget.Close

    def generate(self, *args):
        self.changeMethod()


class ButtonEvent(SignalEvent):
    event = wx.EVT_BUTTON
    signal = 'Press'
            
    def generate(self, *args):
        self.widget.Command(wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, self.widget.GetId())) 

class TextCtrlEvent(SignalEvent):
    event = wx.EVT_TEXT
    signal = 'TextEnter'
        
    def isStateChange(self):
        return True

    def getChangeMethod(self):
        return self.widget.SetValue

    def generate(self, argumentString):
        self.changeMethod(argumentString)

    def outputForScript(self, *args):
        text = self.widget.GetValue()
        return ' '.join([self.name, text])

class ListCtrlEvent(SignalEvent):
    event = wx.EVT_LIST_ITEM_SELECTED
    signal = 'ListCtrlSelect'

    def isStateChange(self):
        return True

    def implies(self, prevLine, *args):
        currOutput = self.outputForScript()
        return currOutput.startswith(prevLine)

    def getChangeMethod(self):
        return self.widget.Select

    def generate(self, argumentString):
        index_list = map(self._findIndex, argumentString.split(','))
        self._clearSelection()
        for index in index_list:
            self.changeMethod(index, 1)

    def _clearSelection(self):
        for i in range(self.widget.ItemCount):
            self.changeMethod(i, 0)

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
                

class UIMap(guishared.UIMap):
    def __init__(self, *args):
        guishared.UIMap.__init__(self, *args)
        wx.Dialog = Dialog
        Dialog.uiMap = self

class UseCaseReplayer(guishared.IdleHandlerUseCaseReplayer):
    def __init__(self, *args, **kw):
        guishared.IdleHandlerUseCaseReplayer.__init__(self, *args, **kw)
        self.describer = Describer()

    def makeIdleHandler(self, method):
        if wx.GetApp():
            return wx.CallLater(0, method)
        else:
            wx.App.idle_methods.append(method)
            return True # anything to show we've got something
                
    def findWindowsForMonitoring(self):
        return wx.GetTopLevelWindows()

    def handleNewWindows(self, *args):
        self.describer.describeUpdates()
        guishared.IdleHandlerUseCaseReplayer.handleNewWindows(self)

    def describeNewWindow(self, window):
        self.describer.describe(window)

    def removeHandler(self, handler):
        # Need to do this for real handlers, don't need it yet
        wx.App.idle_methods = []

    def makeTimeoutReplayHandler(self, method, milliseconds):
        if wx.GetApp():
            wx.CallLater(milliseconds, method)
        else:
            wx.App.timeout_methods.append((milliseconds, method))
            return True

    def runMainLoopWithReplay(self):
        # if it's called before App.MainLoop() the handler needs to be set up here.
        app = wx.GetApp()
        if app.IsMainLoopRunning():
            if self.isActive():
                self.enableReplayHandler()
        else:
            app.setUpHandlers()
        
class ScriptEngine(guishared.ScriptEngine):
    eventTypes = [
        (wx.Frame       , [ FrameEvent ]),
        (wx.Button      , [ ButtonEvent ]),
        (wx.TextCtrl    , [ TextCtrlEvent ]),
        (wx.ListCtrl    , [ ListCtrlEvent ]),
        ]
    signalDescs = {
        "<<ListCtrlSelect>>": "select item",
        }
    columnSignalDescs = {} 

    def createUIMap(self, uiMapFiles):
        return UIMap(self, uiMapFiles)

    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)
        
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

class Describer(guishared.Describer):
    statelessWidgets = [ wx.Button, wx.ScrolledWindow, wx.Window ]
    stateWidgets = [ wx.Frame, wx.Dialog, wx.ListCtrl, wx.TextCtrl ]
    def getChildrenDescription(self, widget):
        try:
            children = widget.GetChildren()
        except wx._core.PyDeadObjectError:
            # Gets thrown on Windows intermittently, don't know why
            return ""
        desc = ""
        for child in children:
            desc = self.addToDescription(desc, self.getDescription(child))
        
        return desc.rstrip()

    def widgetTypeDescription(self, typeName): # pragma: no cover - should be unreachable
        if "DeadObject" in typeName: # mystery guests on Windows occasionally
            return ""
        else:
            return "A widget of type '" + typeName + "'" 

    def getWindowString(self):
        return "Frame" # wx has different terminology

    def getWindowClasses(self):
        return wx.Frame, wx.Dialog

    def getTextEntryClass(self):
        return wx.TextCtrl

    def getUpdatePrefix(self, widget, *args):
        if isinstance(widget, wx.ListCtrl):
            return "Updated state\n"
        else:
            return guishared.Describer.getUpdatePrefix(self, widget, *args)

    def getButtonDescription(self, widget):
        text = "Button"
        labelText = widget.GetLabel()
        if labelText:
            text += " '" + labelText + "'"
        return text

    def getScrolledWindowDescription(self, widget):
        return ""

    def getWindowDescription(self, widget):
        return ""

    def getListCtrlState(self, widget):
        text = ".................\n"
        for i in range(widget.ItemCount):
            if widget.IsSelected(i):
                text += "-> " + widget.GetItemText(i) + "   ***\n"
            else:
                text += "-> " + widget.GetItemText(i) + "\n"
        text += ".................\n"
        return text

    def getListCtrlDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return state

    def getTextCtrlDescription(self, widget):
        text = "TextCtrl"
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        if state:
            text += " value '" + state + "'"
        return text

    def getTextCtrlState(self, widget):
        return widget.GetValue()

    def getDialogState(self, widget):
        return widget.GetTitle()

    def getFrameState(self, widget):
        return widget.GetTitle()
