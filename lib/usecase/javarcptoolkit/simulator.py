
""" Simulation stuff specific to using Eclipse RCP. For example View IDs and Editor IDs etc."""

import sys
from usecase.javaswttoolkit import simulator as swtsimulator
from usecase.javaswttoolkit import describer as swtdescriber
from usecase import applicationEvent
from org.eclipse.swtbot.eclipse.finder import SWTWorkbenchBot
from org.eclipse.core.runtime.jobs import Job, JobChangeAdapter

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

    @classmethod
    def storeIdWithChildren(cls, widget, viewId):
        cls.widgetViewIds[widget] = viewId
        if hasattr(widget, "getChildren"):
            for child in widget.getChildren():
                cls.storeIdWithChildren(child, viewId)

class JobListener(JobChangeAdapter):
    def done(self, e):
        if e.getJob().isUser():
            jobName = e.getJob().getName()
            applicationEvent("completion of " + jobName.lower())


class WidgetMonitor(swtsimulator.WidgetMonitor):
    def __init__(self, *args, **kw):
        self.allViews = set()
        swtsimulator.WidgetMonitor.__init__(self, *args, **kw)
        
    def createSwtBot(self):
        return SWTWorkbenchBot()
    
    def monitorAllWidgets(self, *args, **kw):
        WidgetAdapter.setAdapterClass(WidgetAdapter)
        swtsimulator.runOnUIThread(self.cacheViewIds)
        swtsimulator.WidgetMonitor.monitorAllWidgets(self, *args, **kw)
        # Eclipse RCP has its own mechanism for background processing
        # Hook application events directly into that for synchronisation
        Job.getJobManager().addJobChangeListener(JobListener())

    def cacheViewIds(self):
        for swtbotView in self.bot.views():
            ref = swtbotView.getViewReference()
            if ref not in self.allViews:
                self.allViews.add(ref)
                viewparent = ref.getPane().getControl()
                if viewparent:
                    self.uiMap.logger.debug("Caching View with ID " + ref.getId())
                    WidgetAdapter.storeIdWithChildren(viewparent, ref.getId())

class Describer(swtdescriber.Describer):
    def describeClipboardChanges(self, display):
        # Unfortunately we have classloader problems here
        # Temporarily set and reset the classloader so we can get the information
        currClassLoader = sys.classLoader
        sys.classLoader = display.getClass().getClassLoader()
        try:
            swtdescriber.Describer.describeClipboardChanges(self, display)
        finally:
            sys.classLoader = currClassLoader
