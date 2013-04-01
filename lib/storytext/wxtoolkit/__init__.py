
# Experimental and rather basic support for wx

import storytext.guishared, os, time, wx, logging, inspect
from storytext.definitions import UseCaseScriptError
from ordereddict import OrderedDict
from monkeypatch.functions.messagebox import wrap_message_box
from monkeypatch.functions.messagebox import MessageBoxWidget
from monkeypatch.functions.messagebox import MessageBoxEvent
from monkeypatch.functions.dirselector import wrapDirSelector
from monkeypatch.functions.dirselector import DirSelectorWidget
from monkeypatch.functions.dirselector import DirSelectorEvent
from monkeypatch.functions.fileselector import wrapFileSelector
from monkeypatch.functions.fileselector import FileSelectorWidget
from monkeypatch.functions.fileselector import FileSelectorEvent
from monkeypatch.functions.getcolourfromuser import wrapGetColourFromUser
from monkeypatch.functions.getcolourfromuser import GetColourFromUserEvent
from monkeypatch.functions.getcolourfromuser import GetColourFromUserWidget
from signalevent import SignalEvent
from widgetadapter import WidgetAdapter
from textlabelfinder import TextLabelFinder
from monkeypatch.dialogs.filedialog import FileDialog
from monkeypatch.dialogs.filedialog import FileDialogEvent
from monkeypatch.dialogs.dirdialog import DirDialog
from monkeypatch.dialogs.dirdialog import DirDialogEvent


origApp = wx.App
origPySimpleApp = wx.PySimpleApp

class AppHelper:
    idle_methods = []
    timeout_methods = []

    def setUpHandlers(self):
        for idle_method in self.idle_methods:
            wx.GetApp().Bind(wx.EVT_IDLE, idle_method)
        for milliseconds, timeout_method in self.timeout_methods:
            wx.CallLater(milliseconds, timeout_method)


class App(AppHelper, origApp):
    def MainLoop(self):
        self.setUpHandlers()
        return origApp.MainLoop(self)

class PySimpleApp(AppHelper, origPySimpleApp):
    def MainLoop(self):
        self.setUpHandlers()
        return origPySimpleApp.MainLoop(self)

wx.App = App
wx.PySimpleApp = PySimpleApp
        
origDialog = wx.Dialog
class DialogHelper:
    def ShowModal(self):
        self.uiMap.scriptEngine.replayer.runMainLoopWithReplay()
        return origDialog.ShowModal(self)

class Dialog(DialogHelper, origDialog):
    pass

class FrameEvent(SignalEvent):
    event = wx.EVT_CLOSE
    signal = "Close"
            
    def getChangeMethod(self):
        return self.widget.Close

    def generate(self, *args):
        self.changeMethod()


class ButtonEvent(SignalEvent):
    event = wx.EVT_BUTTON
    signal = "Press"

    def generate(self, *args):
        command = self.makeCommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED)
        self.widget.Command(command) 
        
class ChoiceEvent(SignalEvent):
    event = wx.EVT_CHOICE
    signal = "Choose"

    def isStateChange(self):
        return True

    def getValue(self):
        return self.widget.GetSelection()

    def getChangeMethod(self):
        return self.widget.SetSelection

    def generate(self, argumentString):
        selection = self.widget.FindString(argumentString)
        self.changeMethod(selection)
        command = self.makeCommandEvent(wx.wxEVT_COMMAND_CHOICE_SELECTED)
        command.SetInt(selection)
        self.widget.Command(command) 

    def outputForScript(self, *args):
        text = self.widget.GetStringSelection() or "NO SELECTION"
        return " ".join([self.name, text])

    def implies(self, *args):
        return False

class TextCtrlEvent(SignalEvent):
    event = wx.EVT_TEXT
    signal = "TextEnter"
        
    def isStateChange(self):
        return True

    def getChangeMethod(self):
        return self.widget.SetValue

    def generate(self, argumentString):
        self.changeMethod(argumentString.replace("\\n", "\n"))

    def outputForScript(self, *args):
        text = self.widget.GetValue()
        return " ".join([self.name, text.replace("\n", "\\n")])

    def implies(self, prevOutput, prevEvent, *args):
        return self.widget is prevEvent.widget

class CheckBoxEvent(SignalEvent):
    event = wx.EVT_CHECKBOX
        
    def isStateChange(self):
        return True

    def shouldRecord(self, *args):
        return self.getValue() == self.valueToSet

    def getValue(self):
        return self.widget.Get3StateValue() if self.widget.Is3State() else self.widget.GetValue()

    def getChangeMethod(self):
        return self.widget.Set3StateValue if self.widget.Is3State() else self.widget.SetValue

    def generate(self, argumentString):
        # This line is necessary for things to work on Linux...
        self.changeMethod(self.valueToSet)
        command = self.makeCommandEvent(wx.wxEVT_COMMAND_CHECKBOX_CLICKED)
        # And this line is necessary for things to work on Windows.
        self.setStateToSwitchTo(command)
        self.widget.Command(command)

    def setStateToSwitchTo(self, command):
        command.SetInt(self.valueToSet)

    def implies(self, *args):
        return False

class CheckEvent(CheckBoxEvent):
    signal = "Check"
    valueToSet = 1
    
class UncheckEvent(CheckBoxEvent):
    signal = "Uncheck"
    valueToSet = 0

class CheckThirdStateEvent(CheckBoxEvent):
    signal = "CheckThirdState"
    valueToSet = 2

class ListCtrlEvent(SignalEvent):
    event = wx.EVT_LIST_ITEM_SELECTED
    signal = "ListCtrlSelect"

    def isStateChange(self):
        return True

    def implies(self, prevLine, *args):
        currOutput = self.outputForScript()
        return currOutput.startswith(prevLine)

    def getChangeMethod(self):
        return self.widget.Select

    def generate(self, argumentString):
        index_list = map(self._findIndex, argumentString.split(","))
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

class MenuEvent(SignalEvent):
    event = wx.EVT_MENU
    signal = "Menu"
    separator = "~~~"
 
    # getIdFromLabel
    #   Search menu recursively for an item matching compound_label.
    #   A compound label is of the form menuA~~~submenuB~~~item with 
    #      one or more occurrences of the separator ~~~.
    #   Return a pair (bool found, int menuitem id).

    def shouldRecord(self, event, *args):
        ret = self.getLabelText(event) is not None
        if not ret:
            event.Skip()
        return ret

    def getIdFromLabel(self, menu, menu_label, compound_label):
        if menu_label is not None:
            menuname, _, tail = compound_label.partition(MenuEvent.separator)
        else:
            menuname, tail = None, compound_label
        if menuname != menu_label:
            return False, 0

        for item in menu.GetMenuItems():
            submenu = item.GetSubMenu()
            if submenu != None:
                found, id = self.getIdFromLabel(submenu, item.GetItemLabelText(), tail)
                if found:
                    return True, id
                continue
            label = item.GetItemLabelText()
            if label == tail:
                return True, item.GetId()
        return False, 0
 
    def generate(self, argumentString):
        for menu, label in self.getMenusWithLabels():
            found, id = self.getIdFromLabel(menu, label, argumentString)
            if found:
                return self.generateMenuItemEvent(id)
        raise UseCaseScriptError, "Could not find menu item '" + argumentString + "'."

    def generateMenuItemEvent(self, id):
        self.widget.ProcessCommand(id)

    # getLabelFromId
    #   Search menu recursively for an item matching the input id.
    #   Return a bool which, if true, means an item with id was found,
    #   and label_list contains all the labels from menu down to the 
    #   item, perhaps with one or more submenu labels in between.

    def getLabelFromId(self, menu, menuLabel, id, label_list):
        if menuLabel is not None:
            label_list.append(menuLabel)
        for item in menu.GetMenuItems():
            submenu = item.GetSubMenu()
            if submenu != None:
                if self.getLabelFromId(submenu, item.GetItemLabelText(), id, label_list):
                    return True
                continue
            if id == item.GetId():
                label_list.append(item.GetItemLabelText())
                return True
        if menuLabel is not None:
            label_list.pop()
        return False

    def getLabelText(self, event):
        evtId = event.GetId()
        label = str(evtId)
        for menu, menuLabel in self.getMenusWithLabels():
            label_list = []
            if self.getLabelFromId(menu, menuLabel, evtId, label_list):
                return MenuEvent.separator.join(label_list)
        
    def outputForScript(self, event, *args):
        return ' '.join([self.name, self.getLabelText(event)])

    def getMenusWithLabels(self):
        if self.widget.isInstanceOf(wx.Frame) and self.widget.GetMenuBar() is not None:
            return self.widget.GetMenuBar().GetMenus()
        else:
            return []

class ContextMenuEvent(MenuEvent):
    signal = "ContextMenu"
    def __init__(self, *args):
        SignalEvent.__init__(self, *args)
        self.origPopupMenu = self.widget.widget.PopupMenu
        self.widget.widget.PopupMenu = self.PopupMenu
        self.menu = None
        self.menuArg = None

    def PopupMenu(self, menu, *args):
        self.menu = menu
        if self.menuArg is None:
            self.origPopupMenu(menu, *args)
        else:
            MenuEvent.generate(self, self.menuArg)
        self.menu = None
        self.menuArg = None

    def getMenusWithLabels(self):
        return [ (self.menu, None) ]

    def generate(self, argumentString):
        self.menuArg = argumentString
        self.generateRightClick()

    def generateRightClick(self):
        try:
            id = self.widget.widget.GetId()
            handler = self.widget.widget.GetEventHandler()
        except:
            raise UseCaseScriptError, "Widget is no longer active"
        cm_event = wx.ContextMenuEvent(type=wx.wxEVT_CONTEXT_MENU, winid=id) #, pt=pos)
        cm_event.SetEventObject(self.widget.widget)
        handler.ProcessEvent(cm_event)

    def generateMenuItemEvent(self, id):
        menu_event = wx.CommandEvent(wx.wxEVT_COMMAND_MENU_SELECTED, id)
        menu_event.SetEventObject(self.widget.widget)
        handler = self.widget.widget.GetEventHandler()
        handler.ProcessEvent(menu_event)
        

class UIMap(storytext.guishared.UIMap):
    def __init__(self, *args):
        storytext.guishared.UIMap.__init__(self, *args)
        wx.Dialog = Dialog
        Dialog.uiMap = self
        FileDialog.wrap(self)
        DirDialog.wrap(self)
        wrap_message_box(self)
        wrapDirSelector(self)
        wrapFileSelector(self)
        wrapGetColourFromUser(self)
        
    def replaying(self):
        return self.scriptEngine.replayer.isActive()

    def getReplies(self, event):
        parser = self.fileHandler.readParser
        replies = []
        for section in parser.sections():
            if parser.has_option(section, event.getSignal()):
                cmdName = parser.get(section, event.getSignal())
                replies.append((cmdName, section))
        return replies
        
    def monitorAndDescribe(self, window, *args, **kw):
        self.monitorAndStoreWindow(window)
        window.describe(self.logger)

    def monitorAndStoreWindow(self, window):
        self.monitorWindow(WidgetAdapter(window)) # handle self.windows below instead
    
    def monitor(self, widget, *args):
        if widget.widget not in self.windows:
            self.windows.append(widget.widget)
            storytext.guishared.UIMap.monitor(self, widget, *args)
            if hasattr(widget, "Bind"):
                def OnPaint(event):
                    self.monitorChildren(widget)
                    event.Skip()
                widget.Bind(wx.EVT_PAINT, OnPaint)


class UseCaseReplayer(storytext.guishared.IdleHandlerUseCaseReplayer):
    def __init__(self, *args, **kw):
        storytext.guishared.IdleHandlerUseCaseReplayer.__init__(self, *args, **kw)
        self.describer = Describer()
        self.cacheReplies()

    def cacheReplies(self):
        proxies = (
            (MessageBoxWidget,        MessageBoxEvent),
            (GetColourFromUserWidget, GetColourFromUserEvent),
            (DirSelectorWidget,       DirSelectorEvent),
            (FileSelectorWidget,      FileSelectorEvent),
            (FileDialog,              FileDialogEvent),
            (DirDialog,               DirDialogEvent),
        )
        for proxy in proxies:
            self.cacheProxyReplies(proxy[0], proxy[1])

    def cacheProxyReplies(self, widgetClass, eventClass):
        replies = self.uiMap.getReplies(eventClass)
        for script, _ in self.scripts:
            for cmd in script.commands:
                for dialogCmd, identifier in replies:
                    if cmd.startswith(dialogCmd + " ") or cmd == dialogCmd:
                        argument = cmd.replace(dialogCmd, "")
                        argument = argument.strip()
                        widgetClass.cacheReplies(identifier, argument)
                if cmd.startswith(widgetClass.getAutoPrefix()):
                    parts = cmd.split("'")
                    identifier = parts[1]
                    argument = parts[-1].strip()
                    widgetClass.cacheReplies(identifier, argument)
        
    def makeIdleHandler(self, method):
        if wx.GetApp():
            return wx.CallLater(0, method)
        else:
            AppHelper.idle_methods.append(method)
            return True # anything to show we've got something
                
    def findWindowsForMonitoring(self):
        return wx.GetTopLevelWindows()

    def handleNewWindows(self, *args):
        self.describer.describeUpdates()
        storytext.guishared.IdleHandlerUseCaseReplayer.handleNewWindows(self)

    def describeNewWindow(self, window):
        self.describer.describe(window)

    def removeHandler(self, handler):
        # Need to do this for real handlers, don't need it yet
        AppHelper.idle_methods = []

    def callReplayHandlerAgain(self, *args):
        if len(args) > 0:
            # IdleEvent, make use of it and request more of them...
            args[0].RequestMore()
            return True
        else:
            return storytext.guishared.IdleHandlerUseCaseReplayer.callReplayHandlerAgain(self, *args)

    def makeTimeoutReplayHandler(self, method, milliseconds):
        if wx.GetApp():
            wx.CallLater(milliseconds, method)
        else:
            AppHelper.timeout_methods.append((milliseconds, method))
            return True

    def runMainLoopWithReplay(self):
        # if it's called before App.MainLoop() the handler needs to be 
        # set up here.
        app = wx.GetApp()
        if app.IsMainLoopRunning():
            if self.isActive():
                self.enableReplayHandler()
        else:
            app.setUpHandlers()

class ScriptEngine(storytext.guishared.ScriptEngine):
    eventTypes = [
        (wx.Window,               [ContextMenuEvent]),
        (wx.Frame,                [FrameEvent, MenuEvent]),
        (wx.Button,               [ButtonEvent]),
        (wx.Choice,               [ChoiceEvent]),
        (wx.TextCtrl,             [TextCtrlEvent]),
        (wx.CheckBox,             [CheckEvent, UncheckEvent, CheckThirdStateEvent]),
        (wx.ListCtrl,             [ListCtrlEvent]),
        (wx.FileDialog,           [FileDialogEvent]),
        (wx.DirDialog,            [DirDialogEvent]),
        (MessageBoxWidget,        [MessageBoxEvent]),
        (DirSelectorWidget,       [DirSelectorEvent]),
        (FileSelectorWidget,      [FileSelectorEvent]),
        (GetColourFromUserWidget, [GetColourFromUserEvent]),
        ]
    signalDescs = {
        "<<ListCtrlSelect>>": "select item",
        }
    columnSignalDescs = {} 

    def createUIMap(self, uiMapFiles):
        return UIMap(self, uiMapFiles)

    def createReplayer(self, universalLogging=False, **kw):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder, 
                                                                    **kw)
        
    def getDescriptionInfo(self):
        return "wxPython", "wx", "actions", "http://www.wxpython.org/docs/api/"

    def getDocName(self, className):
        return className + "-class"

    def getSupportedLogWidgets(self):
        return Describer.statelessWidgets + Describer.stateWidgets

class Describer(storytext.guishared.Describer):
    ignoreWidgets = [ wx.ScrolledWindow, wx.Window, wx.Dialog, wx.Sizer ]
    statelessWidgets = [ wx.Button, wx.MenuBar, wx.Menu, wx.MenuItem ]
    stateWidgets = [ wx.Frame, wx.Dialog, wx.ListCtrl, wx.TextCtrl, wx.StaticText,
                     wx.CheckBox, wx.Choice]
    visibleMethodName = "IsShown"
    def getWidgetChildren(self, widgetOrSizer):
        # Involve the Sizers, otherwise we have no chance of describing 
        #     things properly
        # ordinary children structure is not sorted.
        try:
            if isinstance(widgetOrSizer, wx.Sizer):
                children = []
                for item in widgetOrSizer.GetChildren():
                    if item.GetWindow():
                        children.append(item.GetWindow())
                    elif item.GetSizer():
                        children.append(item.GetSizer())
                return children
            elif widgetOrSizer.GetSizer():
                return [ widgetOrSizer.GetSizer() ]
            else:
                return filter(lambda c: not isinstance(c, wx.Dialog), 
                                            widgetOrSizer.GetChildren())
        except wx._core.PyDeadObjectError:
            # Gets thrown on Windows intermittently, don't know why
            return []

    def isVisible(self, widget, *args):
        return widget.IsShown() if isinstance(widget, wx.Window) else True

    def shouldDescribeChildren(self, widget):
        return True # no hindrances right now...

    def getLayoutColumns(self, widget, *args):
        return widget.GetCols() if isinstance(widget, wx.GridSizer) else 1

    def widgetTypeDescription(self, typeName): # pragma: no cover - should be unreachable
        if "DeadObject" in typeName: # mystery guests on Windows occasionally
            return ""
        else:
            return "A widget of type '" + typeName + "'" 

    def getWindowString(self):
        return "Frame" # wx has different terminology

    def getDialogDescription(self, *args):
        return "" # don't describe it as a child of the main window
        
    def getWindowClasses(self):
        return wx.Frame, wx.Dialog

    def getTextEntryClass(self):
        return wx.TextCtrl

    def getUpdatePrefix(self, widget, *args):
        if isinstance(widget, self.getTextEntryClass()):
            return "\nUpdated " + (TextLabelFinder(widget).find() or 
                                                    "Text") + " Field\n"
        else:
            return "\nUpdated "
        
    def getStaticTextDescription(self, widget):
        return self.getAndStoreState(widget)

    def getStaticTextState(self, widget):
        return "'" + widget.GetLabel() + "'"

    def getButtonDescription(self, widget):
        text = "Button"
        labelText = widget.GetLabel()
        if labelText:
            text += " '" + labelText + "'"
        return text

    def getChoiceDescription(self, widget):
        contents = self.getState(widget)
        self.widgetsWithState[widget] = contents
        text = "Choice"
        labelText = TextLabelFinder(widget).find() or widget.GetName()
        if labelText:
            text += " '" + labelText + "'"
        text += ": " + ", ".join(widget.GetItems())
        return text + " " + contents

    def getChoiceState(self, widget):
        value = widget.GetStringSelection() or "NO SELECTION"
        return "(" + value + ")"

    def getListCtrlState(self, widget):
        text = "List :\n"
        for i in range(widget.ItemCount):
            if widget.IsSelected(i):
                text += "-> " + widget.GetItemText(i) + "   ***\n"
            else:
                text += "-> " + widget.GetItemText(i) + "\n"
        return text

    def getListCtrlDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return state

    def getTextCtrlDescription(self, widget):
        contents = self.getState(widget)
        self.widgetsWithState[widget] = contents
        return self.addHeaderAndFooter(widget, contents)

    def getTextCtrlState(self, widget):
        value = widget.GetValue()
        return "*" * len(value) if widget.GetWindowStyle() == wx.TE_PASSWORD else value

    def getCheckBoxDescription(self, widget):
        contents = self.getState(widget)
        self.widgetsWithState[widget] = contents
        return "CheckBox '" + widget.GetLabel() + "' " + contents

    def getCheckBoxState(self, widget):
        if widget.Is3State():
            value = str(widget.Get3StateValue())
        else:
            value = "(checked)" if widget.GetValue() else "(unchecked)"
        return value

    def getDialogState(self, widget):
        return widget.GetTitle()

    def getFrameState(self, widget):
        return widget.GetTitle()
    
# Example menu structure as output by getMenuBarDescription, showing radio
# items, checked items, submenus, and separators:
#
#    Root menu:
#      >>>
#      File (+)
#      Edit (+)
#      Some (+)
#    
#    File menu:
#      Open
#      Save
#    ------
#      Exit
#    
#    Edit menu:
#      Cut
#      Copy
#      Paste
#    
#    Some menu
#      Normal One
#    o Radio 1  (unchecked)
#    . Radio 2  (checked)
#    o Radio 3  (unchecked)
#    - Check A  (unchecked)
#    x Check B  (checked)
#    x Check C  (checked)
#    - Check D  (unchecked)
#      Normal Two
#    ------
#      Submenu
#        Item
#      o Radio
#      - Check
#      x Check
#        Normal
#      Normal Three

    INDENT = 4  # Indentation increment -- must be positive

    def getWindowContentDescription(self, frame):
        if hasattr(frame, "GetMenuBar") and frame.GetMenuBar():
            desc = ""
            desc = self.addToDescription(desc, self.getMenuBarDescription(
                                                    frame.GetMenuBar()))
            desc = self.addToDescription(desc, self.getChildrenDescription(frame))
            return desc
        else:
            return self.getChildrenDescription(frame)

    def getMenuBarDescription(self, menubar, indent=INDENT):
        if menubar is None:
            return "" 
        spaces = " " * indent
        text = "\nMenubar:\n"
        text += spaces + ">>>\n"
        for menu, label in menubar.GetMenus():
            text += spaces + label + " (+)\n"
        for menu, label in menubar.GetMenus():
            text += "\n"
            text += self.getMenuDescription(menu, label, indent)
        return text

    def getMenuDescription(self, menu, label, indent=0, disabled=""):
        spaces = " " * indent
        text = spaces + label.replace("_", "") + " menu" + disabled + "\n"
        for item in menu.GetMenuItems():
            text += self.getMenuItemDescription(item, 
                                                indent=indent+self.INDENT)
        return text

    def getMenuItemDescription(self, menuitem, indent=0):
        spaces       = " " * indent
        less_spaces  = " " * (indent-self.INDENT) if indent >= self.INDENT else ""
        short_spaces = " " * (self.INDENT-1)

        kind = menuitem.GetKind()

        if kind == wx.ITEM_SEPARATOR:
            return less_spaces + "-"*20 + "\n"

        disabled = "" if menuitem.IsEnabled() else " (disabled)"

        submenu = menuitem.GetSubMenu()
        if submenu != None:
            return self.getMenuDescription(submenu, menuitem.GetItemLabelText(),
                            indent=indent+self.INDENT, disabled=disabled)

        label = menuitem.GetItemLabelText() + disabled

        if kind == wx.ITEM_CHECK:
            check = "x" if menuitem.IsChecked() else "-"
            return less_spaces + check + short_spaces + label + "\n"

        if kind == wx.ITEM_RADIO:
            radio = "." if menuitem.IsChecked() else "o"
            return less_spaces + radio + short_spaces + label + "\n"

        return spaces + label + "\n"   # ITEM_NORMAL


    def shouldCheckForUpdates(self, widget, *args):
        # Hack. How to trace the fact that objects in wxPython can change class?!
        return "Dead" not in widget.__class__.__name__

# end wxtoolkit.py
