
import usecase.guishared
from org.eclipse import swt
import org.eclipse.swtbot.swt.finder as swtbot
from org.hamcrest.core import IsAnything
from java.lang import IndexOutOfBoundsException, IllegalStateException

class WidgetAdapter(usecase.guishared.WidgetAdapter):
    def getChildWidgets(self):
        return [] # don't use this...
        
    def getWidgetTitle(self):
        return ""
        
    def getLabel(self):
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
        except AttributeError:
            return ""

    def getName(self):
        class NameResult(swtbot.results.StringResult):
            def run(*args):
                return self.widget.widget.getData("org.eclipse.swtbot.widget.key") or ""
        return swtbot.finders.UIThreadRunnable.syncExec(NameResult())

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

class TextEvent(SignalEvent):
    def isStateChange(self, *args):
        return True

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Modify"

    def _generate(self, argumentString):
        self.widget.setText("")
        self.widget.typeText(argumentString)

    def outputForScript(self, *args):
        text = self.widget.getText()
        return ' '.join([self.name, text])


class DisplayFilter:
    eventFromUser = None
    @classmethod
    def getEventFromUser(cls, event):
        if event is cls.eventFromUser:
            cls.eventFromUser = None
            return True
        else:
            return False
        
    def addFilters(self, display):
        class DisplayListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e):
                if DisplayFilter.eventFromUser is None:
                    DisplayFilter.eventFromUser = e
        for eventType in self.getAllEventTypes():
            runOnUIThread(display.addFilter, eventType, DisplayListener())

    def getAllEventTypes(self):
        eventTypeSet = set()
        for swtbotClass, eventClasses in eventTypes:
            for eventClass in eventClasses:
                eventTypeSet.add(getattr(swt.SWT, eventClass.getAssociatedSignal(None)))
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
                  swt.widgets.Text     : [ swtbot.widgets.SWTBotText ]}
    def __init__(self):
        self.bot = self.botClass()
        self.displayFilter = DisplayFilter()
        
    def forceShellActive(self):
        runOnUIThread(self.bot.getFinder().getShells()[0].forceActive)

    def setUpDisplayFilter(self):
        self.displayFilter.addFilters(self.bot.getDisplay())

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
                if isinstance(widget, widgetClass):
                    for swtbotClass in self.swtbotMap.get(widgetClass):
                        try:
                            adapters.append(WidgetAdapter(swtbotClass(widget)))
                            break
                        except (swtbot.exceptions.AssertionFailedException, swtbot.exceptions.WidgetNotFoundException), e:
                            # Sometimes widgets are already disposed, sometimes they aren't the right type
                            pass
        return adapters

    def describe(self, describer):
        try:
            activeShell = self.bot.getFinder().activeShell()
            runOnUIThread(describer.describeWithUpdates, activeShell)
        except IndexOutOfBoundsException:
            pass # probably we have already exited, don't bother with a description


eventTypes =  [ (swtbot.widgets.SWTBotMenu              , [ ItemEvent ]),
                (swtbot.widgets.SWTBotShell             , [ ShellCloseEvent ]),
                (swtbot.widgets.SWTBotToolbarPushButton , [ ItemEvent ]),
                (swtbot.widgets.SWTBotText              , [ TextEvent ])]
