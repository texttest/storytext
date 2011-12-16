
""" Simulation stuff specific to using Eclipse RCP. For example View IDs and Editor IDs etc."""

import sys
from storytext.javaswttoolkit import simulator as swtsimulator
import storytext.guishared
import org.eclipse.swtbot.eclipse.finder as swtbot
from org.eclipse.ui import IPartListener

# If classes get mentioned for the first time in the event dispatch thread, they will get the wrong classloader
# So we load everything we'll ever need here, once, where we know what the classloader is
from org.eclipse.swt.widgets import *
from org.eclipse.swt.custom import *
from org.eclipse.swt.dnd import *
from org.eclipse.swt.layout import *
from org.eclipse.swtbot.swt.finder.finders import *

class WidgetAdapter(swtsimulator.WidgetAdapter):
    widgetViewIds = {}
    def getUIMapIdentifier(self):
        orig = swtsimulator.WidgetAdapter.getUIMapIdentifier(self)
        if orig.startswith("Type="):
            return self.addViewId(self.widget.widget, orig)
        else:
            return orig

    def findPossibleUIMapIdentifiers(self):
        orig = swtsimulator.WidgetAdapter.findPossibleUIMapIdentifiers(self)
        orig[-1] = self.addViewId(self.widget.widget, orig[-1])
        return orig

    def addViewId(self, widget, text):
        viewId = self.widgetViewIds.get(widget)
        if viewId:
            return "View=" + viewId + "," + text
        else:
            return text

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
    def storeIdWithChildren(cls, widget, viewId):
        cls.widgetViewIds[widget] = viewId
        if hasattr(widget, "getChildren"):
            for child in widget.getChildren():
                cls.storeIdWithChildren(child, viewId)


class WidgetMonitor(swtsimulator.WidgetMonitor):
    def __init__(self, *args, **kw):
        self.allViews = set()
        swtsimulator.WidgetMonitor.__init__(self, *args, **kw)
        # Do this here, when things will be loaded with the right classloader 
        self.uiMap.scriptEngine.importCustomEventTypesFromSimulator()
        
    def createSwtBot(self):
        return swtbot.SWTWorkbenchBot()
    
    def monitorAllWidgets(self, *args, **kw):
        self.setWidgetAdapter()
        swtsimulator.runOnUIThread(self.cacheAndMonitorViews)
        swtsimulator.WidgetMonitor.monitorAllWidgets(self, *args, **kw)
        
    def cacheAndMonitorViews(self):
        for swtbotView in self.bot.views():
            ref = swtbotView.getViewReference()
            if ref not in self.allViews:
                self.allViews.add(ref)
                viewparent = ref.getPane().getControl()
                if viewparent:
                    self.uiMap.logger.debug("Caching View with ID " + ref.getId())
                    WidgetAdapter.storeIdWithChildren(viewparent, ref.getId())
                adapter = ViewAdapter(swtbotView)
                self.uiMap.monitorWidget(adapter)

    def setWidgetAdapter(self):
        WidgetAdapter.setAdapterClass(WidgetAdapter)
        
class ViewAdapter(swtsimulator.WidgetAdapter):
    def getUIMapIdentifier(self):
        viewId = self.widget.getViewReference().getId()
        return self.encodeToLocale("View=" + viewId)

    def findPossibleUIMapIdentifiers(self):
        return [ self.getUIMapIdentifier() ]
    
    def getType(self):
        return "View"

class PartActivateEvent(storytext.guishared.GuiEvent):
    def connectRecord(self, method):
        class RecordListener(IPartListener):
            def partActivated(listenerSelf, part):#@NoSelf
                storytext.guishared.catchAll(method, part, self)
        page = self.widget.getViewReference().getPage()
        swtsimulator.runOnUIThread(page.addPartListener, RecordListener())

    def generate(self, *args):
        # The idea is to just do this, but it seems to cause strange things to happen
        #internally. So we do it outside SWTBot instead.
        #self.widget.setFocus()
        page = self.widget.getViewReference().getPage()
        view = self.widget.getViewReference().getView(False)
        swtsimulator.runOnUIThread(page.activate, view)

    def shouldRecord(self, part, *args):
        # TODO: Need to check no other events are waiting in DisplayFilter 
        return self.widget.getViewReference().getId() == part.getSite().getId() and not swtsimulator.DisplayFilter.instance.hasEvents()

    def delayLevel(self):
        # If there are events for other shells, implies we should delay as we're in a dialog
        return len(swtsimulator.DisplayFilter.instance.eventsFromUser)

    def isStateChange(self):
        return True
    
    def isImpliedByCTabClose(self, tab):
        return True
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, PartActivateEvent)
    
    @classmethod
    def getSignalsToFilter(cls):
        return []

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "ActivatePart"

swtsimulator.eventTypes.append((swtbot.widgets.SWTBotView, [ PartActivateEvent ]))

