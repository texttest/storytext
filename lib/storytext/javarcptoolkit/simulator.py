
""" Simulation stuff specific to using Eclipse RCP. For example View IDs and Editor IDs etc."""

from storytext.javaswttoolkit import simulator as swtsimulator
from storytext.javaswttoolkit import util
import storytext.guishared
from storytext.definitions import UseCaseScriptError

from java.lang import NullPointerException, Integer, IllegalArgumentException

from org.eclipse.jface.bindings.keys import KeyStroke 
from org.eclipse.swt import SWT
from org.eclipse.swt.custom import CTabItem
from org.eclipse.swt.widgets import Event, Listener, MenuItem, Text
from org.eclipse.ui import PlatformUI, IPartListener, IPropertyListener, IWorkbenchPartConstants
from org.eclipse.ui.dialogs import FilteredTree
from org.eclipse.ui.forms.widgets import ExpandableComposite
from org.eclipse.ui.forms.events import ExpansionAdapter

from org.eclipse.swtbot.swt.finder.widgets import AbstractSWTBotControl
from org.eclipse.swtbot.eclipse.finder import SWTWorkbenchBot
from org.eclipse.swtbot.eclipse.finder.widgets import SWTBotView
 
class WidgetAdapter(swtsimulator.WidgetAdapter):
    widgetViewIds = {}    
    swtsimulator.WidgetAdapter.secondaryIdentifiers.append("View")
    def getViewWidget(self):
        widget = self.widget.widget
        if isinstance(widget, MenuItem):
            return swtsimulator.runOnUIThread(util.getRootMenu, widget)
        else:
            return widget

    def findPossibleUIMapIdentifiers(self):
        orig = swtsimulator.WidgetAdapter.findPossibleUIMapIdentifiers(self)
        viewWidget = self.getViewWidget()
        if viewWidget in self.widgetViewIds:
            orig.append("View=" + self.widgetViewIds.get(viewWidget))
        return orig

    def getNameForAppEvent(self):
        name = self.getName()
        if name:
            return name
        viewId = self.widgetViewIds.get(self.widget.widget)
        if viewId:
            return viewId.lower().split(".")[-1]
        else:
            return self.getType().lower()
        
    @classmethod
    def storeId(cls, widget, viewId):
        cls.widgetViewIds[widget] = viewId
        
    @classmethod
    def storeIdWithChildren(cls, widget, viewId):
        cls.storeId(widget, viewId)
        if hasattr(widget, "getChildren"):
            for child in widget.getChildren():
                cls.storeIdWithChildren(child, viewId)
        if hasattr(widget, "getMenu") and widget.getMenu():
            cls.storeId(widget.getMenu(), viewId)
        
    def isPreferred(self):
        viewWidget = self.getViewWidget()
        if viewWidget in self.widgetViewIds:
            viewId = self.widgetViewIds.get(viewWidget)
            activeViewId = swtsimulator.runOnUIThread(self.getActiveViewId)
            return viewId == activeViewId
        else:
            return False
        
    @staticmethod
    def getActiveViewId():
        try:
            return PlatformUI.getWorkbench().getActiveWorkbenchWindow().getActivePage().getActivePartReference().getId()
        except AttributeError, e:
            if "NoneType" not in str(e):
                raise
        
class DisplayFilter(swtsimulator.DisplayFilter):
    def hasComplexAncestors(self, widget):
        return self.isFilterTreeText(widget) or swtsimulator.DisplayFilter.hasComplexAncestors(self, widget)
    
    def isFilterTreeText(self, widget):
        # This field changes its contents the whole time depending on which window is in focus
        # causing trouble for the recorder.
        # It's part of the Eclipse platform so testing it is usually not interesting.
        return isinstance(widget, Text) and widget.getParent() is not None and \
            isinstance(widget.getParent().getParent(), FilteredTree)

class KeyBindingListener(Listener):
    def __init__(self, noBindingCallback):
        self.bindings = {}
        self.listening = False
        self.noBindingCallback = noBindingCallback
    
    def mapKeyBinding(self, keyStroke, method, display, event):
        if not self.listening:
            self.listening = True
            self.addInitialFilter(display)
        self.bindings[(keyStroke.getModifierKeys(), keyStroke.getNaturalKey())] = method, event
            
    def addInitialFilter(self, display):
        # Have to push to the front of the queue (cheating as we do!) because Eclipse's own listener swallows the event
        filterTable = util.getPrivateField(display, "filterTable")
        existingListeners = util.callPrivateMethod(filterTable, "getListeners", [ SWT.KeyDown ], [ Integer.TYPE ])
        for existingListener in existingListeners:
            display.removeFilter(SWT.KeyDown, existingListener)
        display.addFilter(SWT.KeyDown, self)
        for existingListener in existingListeners:
            display.addFilter(SWT.KeyDown, existingListener)

    def recordBinding(self, e, binding):
        method, event = self.bindings[binding]
        storytext.guishared.catchAll(method, e, event)

    def handleEvent(self, e): #@NoSelf
        binding = e.stateMask, e.keyCode
        if binding in self.bindings:
            self.recordBinding(e, binding)
        elif e.stateMask or (e.keyCode >= SWT.F1 and e.keyCode <= SWT.F12):
            # Don't do this for every keypress, just likely key bindings. Recheck the popup menus to see if anything new has appeared
            self.noBindingCallback()
            if binding in self.bindings:
                self.recordBinding(e, binding)


class WidgetMonitor(swtsimulator.WidgetMonitor):
    bindingListener = None
    def __init__(self, *args, **kw):
        self.allViews = set()
        self.swtbotMap[ExpandableComposite] = (SWTBotExpandableComposite, [])
        swtsimulator.WidgetMonitor.__init__(self, *args, **kw)
        WidgetMonitor.bindingListener = KeyBindingListener(self.recheckPopupMenus)
            
    def createSwtBot(self):
        return SWTWorkbenchBot()
    
    def getDisplayFilterClass(self):
        return DisplayFilter
    
    def monitorAllWidgets(self, *args, **kw):
        self.setWidgetAdapter()
        swtsimulator.runOnUIThread(self.cacheAndMonitorViews)
        swtsimulator.WidgetMonitor.monitorAllWidgets(self, *args, **kw)

    def getViews(self):
        # Working around bug in SWTBot that crashes in some circumstances here...
        try:
            return self.bot.views()
        except NullPointerException:
            return []
        
    def cacheAndMonitorViews(self):
        for swtbotView in self.getViews():
            ref = swtbotView.getViewReference()
            if ref not in self.allViews:
                self.allViews.add(ref)
                pane = ref.getPane()
                viewparent = pane.getControl()
                if viewparent:
                    self.uiMap.logger.debug("Caching View with ID " + ref.getId())
                    WidgetAdapter.storeIdWithChildren(viewparent, ref.getId())
                toolbar = pane.getToolBar()
                if toolbar:
                    for item in toolbar.getItems():
                        WidgetAdapter.storeId(item, ref.getId())
                adapter = ViewAdapter(swtbotView)
                self.uiMap.monitorWidget(adapter)
                self.monitorMenus(swtbotView)
                self.addTitleChangedListener(swtbotView)
                self.addActivePartListener(swtbotView)
                
    def addActivePartListener(self, swtbotView):
        class RecordListener(IPartListener):
            def partActivated(listenerSelf, part):#@NoSelf
                self.monitorMenus(swtbotView)
        page = swtbotView.getViewReference().getPage()
        swtsimulator.runOnUIThread(page.addPartListener, RecordListener())
                
    def recheckPopupMenus(self):
        for swtbotView in self.getViews():
            self.uiMap.logger.debug("Menu item disposed - remonitoring menu in view " + swtbotView.getViewReference().getId())
            self.monitorMenus(swtbotView)
        swtsimulator.WidgetMonitor.recheckPopupMenus(self)
                
    def setWidgetAdapter(self):
        WidgetAdapter.setAdapterClass(WidgetAdapter)
    
    def propertyChanged(self, propertyId, botView):
        if propertyId == IWorkbenchPartConstants.PROP_PART_NAME or propertyId == IWorkbenchPartConstants.PROP_TITLE:
            self.monitorMenus(botView)
    
    def addTitleChangedListener(self, botView):
        class PropertyListener(IPropertyListener):
            def propertyChanged(lself, source, propertyId):#@NoSelf
                storytext.guishared.catchAll(self.propertyChanged, propertyId, botView)

        view = botView.getViewReference().getView(False)
        if view is not None:
            view.addPropertyListener(PropertyListener())

    def monitorMenus(self, botView):
        self.monitorViewMenus(botView)
        self.monitorViewContentsMenus(botView)
        
    def sendShowEvent(self, menu):
        try:
            menu.notifyListeners(SWT.Show, Event())
        except NullPointerException:
            self.uiMap.logger.debug("Caught a NullPointerException when a menu tried to notify its listeners")
            return
        
    def monitorViewMenus(self, botView):
        ref = botView.getViewReference()
        pane = ref.getPane()
        if pane.hasViewMenu():            
            menuManager = pane.getMenuManager()
            if pane.getControl():
                menu = menuManager.createContextMenu(pane.getControl().getParent())
                menuManager.updateAll(True)
                WidgetAdapter.storeId(menu, ref.getId())
                self.sendShowEvent(menu)
            
    def monitorViewContentsMenus(self, botView):
        pass
    

class RCPSelectEvent(swtsimulator.SelectEvent):
    def connectRecord(self, method):
        swtsimulator.SelectEvent.connectRecord(self, method)
        widget = self.widget.widget.widget
        if hasattr(widget, "getAccelerator"):
            swtsimulator.runOnUIThread(self.connectRecordKeyBinding, widget, method)
            
    def connectRecordKeyBinding(self, widget, method):
        text = self.widget.getText()
        # Aim is to handle Eclipse RCP key binding mechanism, not SWT accelerators which work anyway
        if "\t" in text and widget.getAccelerator() == 0:
            keyBinding = text.split("\t")[-1].lower()
            try:
                keyStroke = KeyStroke.getInstance(keyBinding)
                WidgetMonitor.bindingListener.mapKeyBinding(keyStroke, method, widget.getDisplay(), self)
            except IllegalArgumentException:
                pass # Tab characters don't have to imply an accelerator, a menu item label can contain these anyway
            
    def shouldRecord(self, event, *args):
        if event.type == SWT.KeyDown:
            # Accelerators aren't active in dialogs
            return not self.widgetDisposed() and event.widget.getShell() is self.widget.widget.widget.getParent().getShell()
        else:
            return swtsimulator.SelectEvent.shouldRecord(self, event, *args)

class ViewAdapter(swtsimulator.WidgetAdapter):
    def findPossibleUIMapIdentifiers(self):
        return [ "Type=View", "View=" + self.widget.getViewReference().getId() ]

    def getType(self):
        return "View"

    
class PartActivateEvent(swtsimulator.TabSelectEvent):
    allInstances = []
    def __init__(self, *args, **kw):
        swtsimulator.TabSelectEvent.__init__(self, *args, **kw)
        self.allInstances.append(self)
        
    def connectRecord(self, method):
        class RecordListener(IPartListener):
            def partActivated(listenerSelf, part):#@NoSelf
                if part is self.widget.getViewReference().getView(False):
                    storytext.guishared.catchAll(method, part, self)
        page = self.widget.getViewReference().getPage()
        swtsimulator.runOnUIThread(page.addPartListener, RecordListener())
                
    def generate(self, *args):
        # The idea is to just do this, but it seems to cause strange things to happen
        #internally. So we do it outside SWTBot instead.
        #self.widget.setFocus()
        if self.actuallyClick():
            swtsimulator.runOnUIThread(self.clickMatchingTab, *args)
        else:
            page = self.widget.getViewReference().getPage()
            view = self.widget.getViewReference().getView(False)
            swtsimulator.runOnUIThread(page.activate, view)
 
    def getTabFolder(self):
        for tab in self.widget.getViewReference().getPane().getTabList():
            if hasattr(tab, "getItems"):
                return tab
            
    def clickMatchingTab(self, argumentString):
        item = self.findTabWithText(argumentString)
        self.clickItem(item, self.getTabFolder())
                
    def parseArguments(self, argumentString):
        # The idea is to just do this, but it seems to cause strange things to happen
        #internally. So we do it outside SWTBot instead.
        #self.widget.setFocus()
        if self.getTitleArgument() == argumentString:
            return argumentString
        else:
            raise UseCaseScriptError, "Could not find View named '" + argumentString + "' to activate.\n" + \
                "Views are named " + repr([ str(i.getTitleArgument()) for i in self.allInstances ])

    def getTitle(self):
        return self.widget.getViewReference().getPartName()

    def shouldRecord(self, part, *args):
        if not self.hasMultipleViews():
            return False
        
        if self.actuallyClick():
            return swtsimulator.DisplayFilter.instance.hasEventOfType(self.getSignalsToFilter(), self.getTabFolder())
        else:
            return not swtsimulator.DisplayFilter.instance.hasEvents()
        
    def hasMultipleViews(self):
        # If there is only one view, don't try to record if it's activated, it's probably just been created...
        return sum((i.isActivatable() for i in self.allInstances)) > 1

    def isActivatable(self):
        return self.getControl() is not None

    def delayLevel(self, part, *args):
        # If there are events for other shells, implies we should delay as we're in a dialog
        return swtsimulator.DisplayFilter.instance.otherEventCount(part, self.isTriggeringEvent)
    
    def isTriggeringEvent(self, event):
        return event.widget is self.getTabFolder() and event.type in [ SWT.MouseDown, SWT.Selection ]
    
    def widgetDisposed(self):
        control = self.getControl()
        return control is None or swtsimulator.runOnUIThread(control.isDisposed)
    
    def widgetVisible(self):
        return True
        
    def widgetSensitive(self):
        return True

    def describeWidget(self):
        control = self.getControl()
        return "of type " + control.__class__.__name__
    
    def getControl(self):
        return self.widget.getViewReference().getPane().getControl()
    
    def getTitleArgument(self):
        # Handle multiple parts with the same title...
        title = self.getTitle()
        index = 1
        for otherInstance in self.allInstances:
            if otherInstance is self:
                break
            if otherInstance.getTitle() == title and otherInstance.getControl() is not None:
                index += 1
                
        if index > 1:
            title += " (" + str(index) + ")"
        return title
    
    def outputForScript(self, *args):
        return ' '.join([self.name, self.getTitleArgument() ])

    def isStateChange(self):
        return True
        
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, PartActivateEvent) and stateChangeOutput.startswith(self.name)
    
    @classmethod
    def getSignalsToFilter(cls):
        return [ SWT.MouseDown ]

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "ActivatePart"
    
    
    
class PartCloseEvent(storytext.guishared.GuiEvent):
    def connectRecord(self, method):
        class RecordListener(IPartListener):
            def partClosed(listenerSelf, part): #@NoSelf
                if part is self.widget.getViewReference().getView(False):
                    storytext.guishared.catchAll(method, part, self)
        page = self.widget.getViewReference().getPage()
        swtsimulator.runOnUIThread(page.addPartListener, RecordListener())
        
    def shouldRecord(self, *args):
        return False # Only point of this is to prevent false Activate Events from being recorded
        
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, (PartActivateEvent, swtsimulator.CTabSelectEvent))
    
    def checkPreviousWhenRejected(self):
        return True
    
    @classmethod
    def getSignalsToFilter(cls):
        return []
    
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "ClosePart"
    
class RCPCTabSelectEvent(swtsimulator.CTabSelectEvent):
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, PartActivateEvent) or swtsimulator.CTabSelectEvent.implies(self, stateChangeOutput, stateChangeEvent, *args)
        
    @classmethod
    def getSignalsToFilter(cls):
        return [ SWT.Selection, SWT.MouseDown ] # Actually so PartActivateEvent works properly


    
# Removing the last tab in a view folder causes the entire folder to be disposed
# To record the correct things we need to cache their names before they are disposed.
class RCPCTabCloseEvent(swtsimulator.CTabCloseEvent):
    disposedTabs = {}
    disposeFilter = None
    def connectRecord(self, method):
        swtsimulator.CTabCloseEvent.connectRecord(self, method)
        class DisposeFilter(Listener):
            def handleEvent(listenerSelf, e): #@NoSelf
                if isinstance(e.widget, CTabItem):
                    self.disposedTabs[e.widget] = e.widget.getText()
                    
        if not self.disposeFilter:
            RCPCTabCloseEvent.disposeFilter = DisposeFilter()
            swtsimulator.runOnUIThread(self.widget.widget.widget.getDisplay().addFilter, SWT.Dispose, self.disposeFilter)

    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, PartActivateEvent) or swtsimulator.CTabCloseEvent.implies(self, stateChangeOutput, stateChangeEvent, *args)
    
    def getItemText(self, item):
        if item.isDisposed():
            return self.disposedTabs.get(item)
        else:
            return item.getText()

    
class SWTBotExpandableComposite(AbstractSWTBotControl):
    def clickOnCenter(self):
        # click(True) will move the mouse pointer
        # Can't find any other way to do this.
        # We can at least move it back again when we're done to avoid other bad effects
        eventPoster = swtsimulator.EventPoster(self.widget.getDisplay())
        eventPoster.performAndReturn(self.clickOnFirstChild)
        
    def clickOnFirstChild(self):        
        firstChild = self.widget.getChildren()[0]
        SWTBotExpandableComposite(firstChild).click(True)
        
        
class ExpandableCompositeEvent(swtsimulator.SelectEvent):
    def shouldRecord(self, *args):
        # To do this properly, we need to check MouseDown events
        # on all the children of the ExpandableComposite
        return not swtsimulator.DisplayFilter.instance.hasEvents()
    
    def generate(self, *args):
        swtsimulator.runOnUIThread(self.widget.clickOnCenter)

    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "ToggleExpand" ]
    
    def connectRecord(self, method):
        class RecordListener(ExpansionAdapter):
            def expansionStateChanged(listenerSelf, e): #@NoSelf
                storytext.guishared.catchAll(method, e, self)

        swtsimulator.runOnUIThread(self.widget.widget.widget.addExpansionListener, RecordListener())
            
swtsimulator.eventTypes.append((SWTBotView, [ PartActivateEvent, PartCloseEvent ]))
swtsimulator.eventTypes.append((SWTBotExpandableComposite, [ ExpandableCompositeEvent ]))

replacements = [(swtsimulator.SelectEvent, RCPSelectEvent),
                (swtsimulator.CTabCloseEvent, RCPCTabCloseEvent),
                (swtsimulator.CTabSelectEvent, RCPCTabSelectEvent)]

for swtbotClass, eventClasses in swtsimulator.eventTypes:
    for oldClass, newClass in replacements:
        if oldClass in eventClasses:
            eventClasses[eventClasses.index(oldClass)] = newClass
