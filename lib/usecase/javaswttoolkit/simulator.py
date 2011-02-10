
import usecase.guishared, util, logging, os
from usecase.definitions import UseCaseScriptError
from usecase import applicationEvent
from org.eclipse import swt
import org.eclipse.swtbot.swt.finder as swtbot
from org.hamcrest.core import IsAnything
from java.lang import IllegalStateException, IndexOutOfBoundsException, RuntimeException, NullPointerException

applicationEventType = 1234 # anything really, just don't conflict with the real SWT events


def runOnUIThread(method, *args):
    class PythonResult(swtbot.results.Result):
        def run(self):
            return method(*args)

    try:
        return swtbot.finders.UIThreadRunnable.syncExec(PythonResult())
    except NullPointerException, e:
        # Temporary code to try to find intermittent Windows error
        print "Caught intermittent Windows NullPointerException!"
        e.printStackTrace()
        raise

class WidgetAdapter(usecase.guishared.WidgetAdapter):
    # All the standard message box texts
    dialogTexts = [ "OK", "Cancel", "Yes", "No", "Abort", "Retry", "Ignore" ]
    def getChildWidgets(self):
        return [] # don't use this...
        
    def getWidgetTitle(self):
        return ""
        
    def getLabel(self):
        if isinstance(self.widget, (swtbot.widgets.SWTBotText, swtbot.widgets.SWTBotCombo)):
            return self.getFromUIThread(util.getTextLabel, self.widget.widget)
        try:
            text = self.widget.getText()
        except:
            return ""
        text = text.replace("&", "").split("\t")[0]
        if text in self.dialogTexts:
            dialogTitle = self.getDialogTitle()
            if dialogTitle:
                return text + ",Dialog=" + dialogTitle
        return text

    def getDialogTitle(self):
        return self.widget.widget.getShell().getText()

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
        return self.widget.getId() or ""

    def getFromUIThread(self, method, *args):
        try:
            return runOnUIThread(method, *args)
        except:
            return ""

usecase.guishared.WidgetAdapter.adapterClass = WidgetAdapter    
        
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
        except (IllegalStateException, IndexOutOfBoundsException), e:
            pass # get these for actions that close the UI. But only after the action is done :)

    def shouldRecord(self, event, *args):
        return DisplayFilter.getEventFromUser(event)

    def delayLevel(self):
        # If there are events for other shells, implies we should delay as we're in a dialog
        return len(DisplayFilter.eventsFromUser)

    @classmethod
    def getSignalsToFilter(cls):
        return [ getattr(swt.SWT, cls.getAssociatedSignal(None)) ]


class SelectEvent(SignalEvent):    
    def _generate(self, *args):
        self.widget.click()

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Selection"


class RadioSelectEvent(SelectEvent):
    def shouldRecord(self, event, *args):
        return SignalEvent.shouldRecord(self, event, *args) and event.widget.getSelection()


class ShellCloseEvent(SignalEvent):    
    def _generate(self, *args):
        # SWTBotShell.close appears to close things twice, just use the ordinary one for now...
        class CloseRunnable(swtbot.results.VoidResult):
            def run(resultSelf):
                self.widget.widget.widget.close()
                
        swtbot.finders.UIThreadRunnable.asyncExec(CloseRunnable())
        
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Close"
    

class ResizeEvent(SignalEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Resize"

    def isStateChange(self, *args):
        return True

    def _generate(self, argumentString):
        words = argumentString.split()
        width = int(words[1])
        height = int(words[-1])
        runOnUIThread(self.widget.widget.widget.setSize, width, height)

    def dimensionText(self, dimension):
        return str((dimension / 10) * 10)
        
    def outputForScript(self, *args):
        size = self.widget.widget.widget.getSize()
        sizeDesc = "width " + self.dimensionText(size.x) + " and height " + self.dimensionText(size.y)
        return ' '.join([self.name, sizeDesc ])


class TabCloseEvent(SignalEvent):
    def _generate(self, *args):
        self.widget.close()

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Dispose"

    def shouldRecord(self, event, *args):
        shell = event.widget.getParent().getShell()
        return DisplayFilter.getEventFromUser(event) and shell not in DisplayFilter.disposedShells


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


class ComboTextEvent(TextEvent):
    def _generate(self, argumentString):
        try:
            self.widget.setText(argumentString)
        except RuntimeException: # if it's readonly...
            try:
                self.widget.setSelection(argumentString)
            except RuntimeException, e:
                raise UseCaseScriptError, e.getMessage()

class TreeEvent(SignalEvent):
    def _generate(self, argumentString):
        item = self.findItem(argumentString, self.widget.getAllItems())
        if item:
            self.generateItem(item)
        else:
            raise UseCaseScriptError, "Could not find item labelled '" + argumentString + "' in tree."

    def findItem(self, text, items):
        for item in items:
            if item.getText() == text:
                return item
            if item.isExpanded():
                subItem = self.findItem(text, item.getItems())
                if subItem:
                    return subItem
        
    def outputForScript(self, event, *args):
        text = event.item.getText()
        return ' '.join([self.name, text])


class TreeExpandEvent(TreeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Expand"

    def generateItem(self, item):
        item.expand()


class TreeCollapseEvent(TreeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Collapse"

    def generateItem(self, item):
        item.collapse()


class TreeClickEvent(TreeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Selection"

    def shouldRecord(self, event, *args):
        # Seem to get selection events even when nothing has been selected...
        return DisplayFilter.getEventFromUser(event) and event.item in event.widget.getSelection()

    def generateItem(self, item):
        item.select()

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

class ListClickEvent(SignalEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Selection"
    
    def isStateChange(self):
        return True

    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput.startswith(stateChangeOutput)

    def outputForScript(self, event, *args):
        text = ",".join(self.widget.selection())
        return ' '.join([self.name, text])

    def _generate(self, argumentString):
        index = self.widget.indexOf(argumentString)
        if index >= 0:
            self.widget.select(index)
        else:
            raise UseCaseScriptError, "Could not find item labelled '" + argumentString + "' in list."


class DisplayFilter:
    eventsFromUser = []
    disposedShells = []    
    logger = None
    @classmethod
    def getEventFromUser(cls, event):
        if event in cls.eventsFromUser:
            cls.eventsFromUser.remove(event)
            return True
        else:
            if len(cls.eventsFromUser) == 0:
                cls.logger.debug("Rejecting event, it has not yet been seen in the display filter")
            else:
                cls.logger.debug("Received event " + event.toString())
                cls.logger.debug("Rejecting event, not yet processed " + repr([ e.toString() for e in cls.eventsFromUser ]))
            return False

    def __init__(self, widgetEventTypes):
        DisplayFilter.logger = logging.getLogger("usecase record")
        self.widgetEventTypes = widgetEventTypes

    def getShell(self, widget):
        # Note : widget might be an Item rather than a widget!
        if widget is not None and not widget.isDisposed():
            if hasattr(widget, "getShell"):
                return widget.getShell()
            elif hasattr(widget, "getParent"):
                return self.getShell(widget.getParent())

    def hasEventOnShell(self, widget):
        currShell = self.getShell(widget)
        if not currShell:
            return False

        for event in self.eventsFromUser:
            if self.getShell(event.widget) is currShell:
                return True
        return False
        
    def addFilters(self, display, monitorListener):
        class DisplayListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e):
                if not self.hasEventOnShell(e.widget) and self.shouldCheckWidget(e.widget, e.type):
                    self.logger.debug("Filter for event " + e.toString())
                    DisplayFilter.eventsFromUser.append(e)
                    # This is basically a failsafe - shouldn't be needed but in case
                    # something else goes wrong when recording or widgets appear that for some reason couldn't be found,
                    # this is a safeguard against never recording anything again.
                    monitorListener.recordableEvent(e)
                elif isinstance(e.widget, swt.widgets.Shell) and e.type == swt.SWT.Dispose:
                    self.disposedShells.append(e.widget)
        for eventType in self.getAllEventTypes():
            runOnUIThread(display.addFilter, eventType, DisplayListener())
        class ApplicationEventListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e):
                applicationEvent(e.text)
        runOnUIThread(display.addFilter, applicationEventType, ApplicationEventListener())
        
    def shouldCheckWidget(self, widget, eventType):
        if not util.isVisible(widget):
            return False
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
    swtbotMap = { swt.widgets.Button   : (swtbot.widgets.SWTBotButton,
                                         [ (swt.SWT.RADIO, swtbot.widgets.SWTBotRadio) ]),
                  swt.widgets.MenuItem : (swtbot.widgets.SWTBotMenu, []),
                  swt.widgets.Shell    : (swtbot.widgets.SWTBotShell, []),
                  swt.widgets.ToolItem : ( swtbot.widgets.SWTBotToolbarPushButton,
                                         [ (swt.SWT.DROP_DOWN, swtbot.widgets.SWTBotToolbarDropDownButton),
                                           (swt.SWT.RADIO    , swtbot.widgets.SWTBotToolbarRadioButton),
                                           (swt.SWT.SEPARATOR, swtbot.widgets.SWTBotToolbarSeparatorButton),
                                           (swt.SWT.TOGGLE   , swtbot.widgets.SWTBotToolbarToggleButton) ]),
                  swt.widgets.Text     : (swtbot.widgets.SWTBotText, []),
                  swt.widgets.List     : (swtbot.widgets.SWTBotList, []),
                  swt.widgets.Combo    : (swtbot.widgets.SWTBotCombo, []),
                  swt.widgets.Tree     : (swtbot.widgets.SWTBotTree, []),
                  swt.custom.CTabItem  : (swtbot.widgets.SWTBotCTabItem, []) }
    def __init__(self, uiMap):
        self.bot = self.createSwtBot()
        self.uiMap = uiMap
        self.uiMap.scriptEngine.eventTypes = eventTypes
        self.displayFilter = DisplayFilter(self.getWidgetEventTypes())

    def createSwtBot(self):
        return swtbot.SWTBot()
    
    @classmethod
    def getWidgetEventTypes(cls):
        return cls.getWidgetEventInfo(lambda eventClass: eventClass.getSignalsToFilter())

    @classmethod
    def getWidgetEventTypeNames(cls):
        return cls.getWidgetEventInfo(lambda eventClass: [ eventClass.getAssociatedSignal(None) ])

    @classmethod
    def getWidgetEventInfo(cls, method):
        allEventTypes = []
        eventTypeDict = dict(eventTypes)
        for widgetClass, (defaultSwtbotClass, styleSwtbotInfo) in cls.swtbotMap.items():
            currEventTypes = set()
            for swtBotClass in [ defaultSwtbotClass] + [ cls for x, cls in styleSwtbotInfo ]:
                for eventClass in eventTypeDict.get(swtBotClass, []):
                    currEventTypes.update(method(eventClass))
            allEventTypes.append((widgetClass, currEventTypes))
        return allEventTypes
    
    def setUp(self):
        self.forceShellActive()
        monitorListener = self.setUpDisplayFilter()
        allWidgets = self.findAllWidgets()
        monitorListener.addToCache(allWidgets)
        self.monitorAllWidgets(self.bot.getFinder().activeShell(), allWidgets)
        
    def forceShellActive(self):
        if os.pathsep == ":": # os.name == "java", so can't find out that way if we're on UNIX
            # Need to do this for running under Xvfb on UNIX
            # Seems to throw exceptions occasionally on Windows, so don't bother
            runOnUIThread(self.bot.getFinder().getShells()[0].forceActive)

    def setUpDisplayFilter(self):
        display = self.bot.getDisplay()
        monitorListener = self.addMonitorFilter(display)
        self.displayFilter.addFilters(display, monitorListener)
        return monitorListener

    def addMonitorFilter(self, display):
        monitorListener = util.MonitorListener(self.bot, IsAnything())
        monitorListener.addCallback(self.monitorAllWidgets)
        runOnUIThread(display.addFilter, swt.SWT.Show, monitorListener)
        runOnUIThread(display.addFilter, swt.SWT.Paint, monitorListener)
        return monitorListener

    def monitorAllWidgets(self, parent, widgets, eventType=None, seenBefore=False):
        if not seenBefore:
            self.uiMap.logger.debug("Showing/painting widget of type " +
                                    parent.__class__.__name__ + ", monitoring found widgets")
            for widget in self.makeAdapters(widgets):
                self.uiMap.monitorWidget(widget)

    def findAllWidgets(self):
        matcher = IsAnything()
        widgets = self.bot.widgets(matcher)
        menus = self.bot.getFinder().findMenus(matcher)
        widgets.addAll(menus)
        return widgets

    def getPopupMenus(self, widgets):
        menus = []
        for widget in widgets:
            if isinstance(widget, swt.widgets.Control):
                menuFinder = swtbot.finders.ContextMenuFinder(widget)
                menus += menuFinder.findMenus(IsAnything())
        return menus

    def findSwtbotClass(self, widget, widgetClass):
        defaultClass, styleClasses = self.swtbotMap.get(widgetClass)
        for currStyle, styleClass in styleClasses:
            if runOnUIThread(widget.getStyle) & currStyle:
                return styleClass
        return defaultClass

    def makeAdapters(self, widgets):
        adapters = []
        for widget in widgets + self.getPopupMenus(widgets):
            for widgetClass in self.swtbotMap.keys():
                if util.checkInstance(widget, widgetClass):
                    swtbotClass = self.findSwtbotClass(widget, widgetClass)
                    try:
                        adapters.append(WidgetAdapter.adapt(swtbotClass(widget)))
                        break
                    except RuntimeException:
                        # Sometimes widgets are already disposed
                        pass
        return adapters

    def describe(self, describer):
        activeShell = self.bot.getFinder().activeShell()
        runOnUIThread(describer.describeWithUpdates, activeShell)
        
eventTypes =  [ (swtbot.widgets.SWTBotButton            , [ SelectEvent ]),
                (swtbot.widgets.SWTBotRadio             , [ RadioSelectEvent ]),
                (swtbot.widgets.SWTBotMenu              , [ SelectEvent ]),
                (swtbot.widgets.SWTBotShell             , [ ShellCloseEvent, ResizeEvent ]),
                (swtbot.widgets.SWTBotToolbarPushButton , [ SelectEvent ]),
                (swtbot.widgets.SWTBotText              , [ TextEvent ]),
                (swtbot.widgets.SWTBotTree              , [ TreeExpandEvent, TreeCollapseEvent,
                                                            TreeClickEvent, TreeDoubleClickEvent ]),
                (swtbot.widgets.SWTBotList              , [ ListClickEvent ]),
                (swtbot.widgets.SWTBotCombo             , [ ComboTextEvent ]),
                (swtbot.widgets.SWTBotCTabItem          , [ TabCloseEvent ])]
