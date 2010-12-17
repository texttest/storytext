
import usecase.guishared, util, logging
from org.eclipse import swt
import org.eclipse.swtbot.swt.finder as swtbot
from org.hamcrest.core import IsAnything
from java.lang import IllegalStateException

class WidgetAdapter(usecase.guishared.WidgetAdapter):
    def getChildWidgets(self):
        return [] # don't use this...
        
    def getWidgetTitle(self):
        return ""
        
    def getLabel(self):
        if isinstance(self.widget, swtbot.widgets.SWTBotText):
            return self.getFromUIThread(util.getTextLabel, self.widget.widget)
        try:
            return self.widget.getText().replace("&", "").split("\t")[0]
        except:
            return ""

    def getType(self):
        # SWT name, not the SWTBot name
        return self.widget.widget.__class__.__name__
        
    def isAutoGenerated(self, name):
        return len(name) == 0

    def getTooltip(self):
        try:
            return self.widget.getToolTipText()
        except:
            return ""

    def getName(self):
        return self.getFromUIThread(self.widget.widget.getData, "org.eclipse.swtbot.widget.key") or ""

    def getFromUIThread(self, method, *args):
        try:
            class StringResult(swtbot.results.StringResult):
                def run(resultSelf):
                    return method(*args)
            return swtbot.finders.UIThreadRunnable.syncExec(StringResult())
        except:
            return ""

usecase.guishared.WidgetAdapter.adapterClass = WidgetAdapter    

def runOnUIThread(method, *args):
    class PythonVoidResult(swtbot.results.VoidResult):
        def run(self):
            method(*args)

    swtbot.finders.UIThreadRunnable.syncExec(PythonVoidResult())

class SignalEvent(usecase.guishared.GuiEvent):
    def connectRecord(self, method):
        class RecordListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e):
                method(e, self)

        eventType = getattr(swt.SWT, self.getAssociatedSignal(self.widget))
        try:
            # Three indirections: WidgetAdapter -> SWTBotMenu -> MenuItem
            runOnUIThread(self.widget.widget.widget.addListener, eventType, RecordListener())
        except: # Get 'widget is disposed' sometimes, don't know why...
            pass

    def generate(self, *args):
        try:
            self._generate(*args)
        except IllegalStateException:
            pass # get this on Windows for actions that close the UI. But only after the action is done :)

    def shouldRecord(self, event, *args):
        return DisplayFilter.getEventFromUser(event)

    @classmethod
    def getSignalsToFilter(cls):
        return [ getattr(swt.SWT, cls.getAssociatedSignal(None)) ]


class ItemEvent(SignalEvent):    
    def _generate(self, *args):
        self.widget.click()

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Selection"


class ShellCloseEvent(SignalEvent):    
    def _generate(self, *args):
        # SWTBotShell.close appears to close things twice, just use the ordinary one for now...
        runOnUIThread(self.widget.widget.widget.close)
        
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Close"
    
    @classmethod
    def getSignalsToFilter(cls):
        return [ swt.SWT.Close, swt.SWT.Dispose ]


class TabCloseEvent(SignalEvent):
    def _generate(self, *args):
        self.widget.close()

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Dispose"
    

class TextEvent(SignalEvent):
    def isStateChange(self, *args):
        return True

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Modify"

    def _generate(self, argumentString):
        self.widget.setText(argumentString)

    def outputForScript(self, *args):
        text = self.widget.getText()
        return ' '.join([self.name, text])


class TreeEvent(SignalEvent):
    def _generate(self, argumentString):
        item = self.widget.getTreeItem(argumentString)
        self.generateItem(item)
        
    def outputForScript(self, event, *args):
        text = event.item.getText()
        return ' '.join([self.name, text])


class TreeClickEvent(TreeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Selection"

    def generateItem(self, item):
        item.click()

    def isStateChange(self):
        return True

    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput.startswith(stateChangeOutput)


class TreeDoubleClickEvent(TreeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "DefaultSelection"

    def generateItem(self, item):
        item.doubleClick()

    def implies(self, stateChangeLine, stateChangeEvent, swtEvent, *args):
        return isinstance(stateChangeEvent, TreeClickEvent) and \
               stateChangeLine == stateChangeEvent.name + " " + swtEvent.item.getText()


class DisplayFilter:
    eventFromUser = None
    logger = None
    @classmethod
    def getEventFromUser(cls, event):
        if event is cls.eventFromUser:
            cls.eventFromUser = None
            return True
        else:
            if cls.eventFromUser is None:
                cls.logger.debug("Rejecting event, it has not yet been seen in the display filter")
            else:
                cls.logger.debug("Rejecting event, not yet processed " + cls.eventFromUser.toString())
            return False

    def __init__(self, widgetEventTypes):
        DisplayFilter.logger = logging.getLogger("usecase record")
        self.widgetEventTypes = widgetEventTypes
        
    def addFilters(self, display):
        class DisplayListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e):
                if DisplayFilter.eventFromUser is None and self.shouldCheckWidget(e.widget, e.type):
                    DisplayFilter.eventFromUser = e
        for eventType in self.getAllEventTypes():
            runOnUIThread(display.addFilter, eventType, DisplayListener())

    def shouldCheckWidget(self, widget, eventType):
        for cls, types in self.widgetEventTypes:
            if util.checkInstance(widget, cls) and eventType in types:
                return True
        return False

    def getAllEventTypes(self):
        eventTypeSet = set()
        for swtbotClass, eventTypes in self.widgetEventTypes:
            eventTypeSet.update(eventTypes)
        return eventTypeSet
        


class WidgetMonitor:
    botClass = swtbot.SWTBot
    swtbotMap = { swt.widgets.MenuItem : [ swtbot.widgets.SWTBotMenu ],
                  swt.widgets.Shell    : [ swtbot.widgets.SWTBotShell ],
                  swt.widgets.ToolItem : [ swtbot.widgets.SWTBotToolbarPushButton,
                                           swtbot.widgets.SWTBotToolbarDropDownButton,
                                           swtbot.widgets.SWTBotToolbarRadioButton,
                                           swtbot.widgets.SWTBotToolbarSeparatorButton,
                                           swtbot.widgets.SWTBotToolbarToggleButton ],
                  swt.widgets.Text     : [ swtbot.widgets.SWTBotText ],
                  swt.widgets.Tree     : [ swtbot.widgets.SWTBotTree ],
                  swt.custom.CTabItem  : [ swtbot.widgets.SWTBotCTabItem ]}
    def __init__(self, uiMap):
        self.bot = self.botClass()
        self.uiMap = uiMap
        self.uiMap.scriptEngine.eventTypes = eventTypes
        self.displayFilter = DisplayFilter(self.getWidgetEventTypes())
        self.widgetsShown = set()

    def getWidgetEventTypes(self):
        allEventTypes = []
        eventTypeDict = dict(eventTypes)
        for widgetClass, swtBotClasses in self.swtbotMap.items():
            currEventTypes = set()
            for swtBotClass in swtBotClasses:
                for eventClass in eventTypeDict.get(swtBotClass, []):
                    currEventTypes.update(eventClass.getSignalsToFilter())
            allEventTypes.append((widgetClass, currEventTypes))
        return allEventTypes
    
    def setUp(self):
        self.forceShellActive()
        self.setUpDisplayFilter()
        for widget in self.findAllWidgets():
            self.uiMap.monitorWidget(widget)
        
    def forceShellActive(self):
        runOnUIThread(self.bot.getFinder().getShells()[0].forceActive)

    def setUpDisplayFilter(self):
        display = self.bot.getDisplay()
        self.displayFilter.addFilters(display)
        self.addMonitorFilter(display)

    def addMonitorFilter(self, display):
        class MonitorListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e):
                self.bot.getFinder().setShouldFindInvisibleControls(True)
                widgets = [ e.widget ] + self.bot.widgets(IsAnything(), e.widget)
                self.widgetsShown.update(widgets)
                for widget in self.makeAdapters(widgets):
                    self.uiMap.monitorWidget(widget)
                
        runOnUIThread(display.addFilter, swt.SWT.Show, MonitorListener())

    def findAllWidgets(self):
        matcher = IsAnything()
        widgets = self.bot.widgets(matcher)
        menus = self.bot.getFinder().findMenus(matcher)
        widgets.addAll(menus)
        return self.makeAdapters(widgets)

    def makeAdapters(self, widgets):
        adapters = []
        for widget in widgets:
            for widgetClass in self.swtbotMap.keys():
                if util.checkInstance(widget, widgetClass):
                    for swtbotClass in self.swtbotMap.get(widgetClass):
                        try:
                            adapters.append(WidgetAdapter(swtbotClass(widget)))
                            break
                        except (swtbot.exceptions.AssertionFailedException, swtbot.exceptions.WidgetNotFoundException), e:
                            # Sometimes widgets are already disposed, sometimes they aren't the right type
                            pass
        return adapters

    def describe(self, describer):
        activeShell = self.bot.getFinder().activeShell()
        runOnUIThread(describer.describeWithUpdates, activeShell)
        

eventTypes =  [ (swtbot.widgets.SWTBotMenu              , [ ItemEvent ]),
                (swtbot.widgets.SWTBotShell             , [ ShellCloseEvent ]),
                (swtbot.widgets.SWTBotToolbarPushButton , [ ItemEvent ]),
                (swtbot.widgets.SWTBotText              , [ TextEvent ]),
                (swtbot.widgets.SWTBotTree              , [ TreeClickEvent, TreeDoubleClickEvent ]),
                (swtbot.widgets.SWTBotCTabItem          , [ TabCloseEvent ])]