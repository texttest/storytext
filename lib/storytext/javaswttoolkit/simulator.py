
import storytext.guishared, util, logging, os
from storytext.definitions import UseCaseScriptError
from storytext import applicationEvent
from org.eclipse import swt
import org.eclipse.swtbot.swt.finder as swtbot
from org.hamcrest.core import IsAnything
from java.lang import IllegalStateException, IndexOutOfBoundsException, RuntimeException, NullPointerException
from java.text import ParseException
from java.util import ArrayList

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

class WidgetAdapter(storytext.guishared.WidgetAdapter):
    # All the standard message box texts
    dialogTexts = [ "OK", "Cancel", "Yes", "No", "Abort", "Retry", "Ignore" ]
    def getChildWidgets(self):
        return [] # don't use this...
        
    def getWidgetTitle(self):
        return ""
        
    def getLabel(self):
        if isinstance(self.widget, (swtbot.widgets.SWTBotText, swtbot.widgets.SWTBotCombo)) or \
               not hasattr(self.widget.widget, "getText"):
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

    def getNameForAppEvent(self):
        return self.getName() or self.getType().lower()

    def getFromUIThread(self, method, *args):
        try:
            return runOnUIThread(method, *args)
        except:
            return ""
    
    def getContextName(self):
        parent = runOnUIThread(self.widget.widget.getParent)
        if isinstance(parent, swt.widgets.Table):
            return "TableCell"
        else:
            return ""
        

storytext.guishared.WidgetAdapter.adapterClass = WidgetAdapter    
        
class SignalEvent(storytext.guishared.GuiEvent):
    def __init__(self, name, widget, argumentParseData, *args):
        self.generationModifiers = argumentParseData.split(",") if argumentParseData else []
        storytext.guishared.GuiEvent.__init__(self, name, widget, *args)
        
    def connectRecord(self, method):
        class RecordListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e): #@NoSelf
                storytext.guishared.catchAll(method, e, self)

        eventType = getattr(swt.SWT, self.getAssociatedSignal(self.widget))
        try:
            runOnUIThread(self.addListeners, eventType, RecordListener())
        except: # Get 'widget is disposed' sometimes, don't know why...
            pass
        
    def addListeners(self, *args):
        # Three indirections: WidgetAdapter -> SWTBotMenu -> MenuItem
        return self.widget.widget.widget.addListener(*args)

    def generate(self, *args):
        self.checkWidgetStatus()
        try:
            self._generate(*args)
        except (IllegalStateException, IndexOutOfBoundsException), _:
            pass # get these for actions that close the UI. But only after the action is done :)

    def shouldRecord(self, event, *args):
        return DisplayFilter.instance.getEventFromUser(event)

    def delayLevel(self, event, *args):
        # If there are events for other shells, implies we should delay as we're in a dialog
        return DisplayFilter.instance.otherEventCount(event)

    def widgetDisposed(self):
        return self.widget.widget.widget.isDisposed()

    def widgetVisible(self):
        return self.widget.isVisible()

    def widgetSensitive(self):
        return self.widget.isEnabled()

    def describeWidget(self):
        return " of type " + self.widget.getType()

    def isImpliedByCTabClose(self, tab):
        return False
    
    @classmethod
    def getSignalsToFilter(cls):
        return [ getattr(swt.SWT, cls.getAssociatedSignal(None)) ]


class StateChangeEvent(SignalEvent):
    def outputForScript(self, *args):
        return ' '.join([self.name, self.getStateText(*args) ])

    def isStateChange(self, *args):
        return True


class SelectEvent(SignalEvent):    
    def _generate(self, *args):
        self.widget.click()

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Selection"


class LinkSelectEvent(SelectEvent):
    def _generate(self, *args):
        # There is self.widget.click(), but it is very low level, seizes the mouse pointer,
        # and fails utterly under KDE. See https://bugs.eclipse.org/bugs/show_bug.cgi?id=337548
        text = self.widget.getText()
        startPos = text.find(">") + 1
        endPos = text.rfind("<")
        hyperlinkText = text[startPos:endPos]
        self.widget.click(hyperlinkText)
        
        
class RadioSelectEvent(SelectEvent):
    def shouldRecord(self, event, *args):
        return SignalEvent.shouldRecord(self, event, *args) and event.widget.getSelection()
    
    def _generate(self, *args):
        if "3.5" in swt.__file__ and "2.0.4" in swtbot.__file__ and self.widget.isInstanceOf(swtbot.widgets.SWTBotRadio):
            # Workaround for bug in SWTBot 2.0.4 which doesn't handle Eclipse 3.5 radio buttons properly
            method = swtbot.widgets.SWTBotRadio.getDeclaredMethod("otherSelectedButton", None)
            method.setAccessible(True)
            selectedButton = method.invoke(self.widget.widget, None)
            runOnUIThread(selectedButton.widget.setSelection, False)
        SelectEvent._generate(self)
    
class TabSelectEvent(SelectEvent):
    swtbotItemClass = swtbot.widgets.SWTBotTabItem
    def findTabWithText(self, text):
        for item in self.widget.widget.widget.getItems():
            if item.getText() == text:
                return item
        
    def findTab(self, text):
        # Seems we can only get tab item text in the UI thread (?)
        item = runOnUIThread(self.findTabWithText, text)
        if item:
            return item
        else:
            raise UseCaseScriptError, "Could not find tab labelled '" + text + "' in TabFolder."
    
    def _generate(self, argumentString):
        tab = self.findTab(argumentString)
        self.swtbotItemClass(tab).activate()
        
    def outputForScript(self, event, *args):
        # Text may have changed since the application listeners have been applied
        return ' '.join([self.name, event.item.getText()])
    

class CTabSelectEvent(TabSelectEvent):
    swtbotItemClass = swtbot.widgets.SWTBotCTabItem
    def isStateChange(self):
        return True

    def implies(self, *args):
        # State change because it can be implied by CTabCloseEvents
        # But don't amalgamate them together, allow several tabs to be selected in sequence
        return False

    def isImpliedByCTabClose(self, tab):    
        return tab.getParent() is self.widget.widget.widget


class ShellCloseEvent(SignalEvent):    
    def _generate(self, *args):
        # SWTBotShell.close appears to close things twice, just use the ordinary one for now...
        class CloseRunnable(swtbot.results.VoidResult):
            def run(resultSelf): #@NoSelf
                self.widget.widget.widget.close()
                
        swtbot.finders.UIThreadRunnable.asyncExec(CloseRunnable())
        
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Close"
    

class ResizeEvent(StateChangeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Resize"

    def _generate(self, argumentString):
        words = argumentString.split()
        width = int(words[1])
        height = int(words[-1])
        runOnUIThread(self.widget.widget.widget.setSize, width, height)

    def dimensionText(self, dimension):
        return str((dimension / 10) * 10)
        
    def getStateText(self, *args):
        size = self.widget.widget.widget.getSize()
        return "width " + self.dimensionText(size.x) + " and height " + self.dimensionText(size.y)


class CTabCloseEvent(SignalEvent):
    def _generate(self, *args):
        self.widget.close()

    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Dispose"

    def shouldRecord(self, event, *args):
        shell = event.widget.getParent().getShell()
        return DisplayFilter.instance.getEventFromUser(event) and shell not in DisplayFilter.instance.disposedShells

    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return stateChangeEvent.isImpliedByCTabClose(self.widget.widget.widget)
    
class TextEvent(StateChangeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Modify"

    def selectAll(self):
        self.widget.selectAll()

    def _generate(self, argumentString):
        self.widget.setFocus()
        if "typed" in self.generationModifiers and argumentString:
            self.selectAll()
            self.widget.typeText(argumentString)
        else:
            self.widget.setText(argumentString)

    def getStateText(self, *args):
        return self.widget.getText()
    
    def shouldRecord(self, event, *args):
        return (not event.widget.getStyle() & swt.SWT.READ_ONLY) and StateChangeEvent.shouldRecord(self, event, *args)
    
    def implies(self, stateChangeOutput, *args):
        if "typed" in self.generationModifiers:
            currOutput = self.outputForScript(*args)
            return StateChangeEvent.implies(self, stateChangeOutput, *args) and \
                (currOutput.startswith(stateChangeOutput) or \
                 stateChangeOutput.startswith(currOutput))
        else:
            return StateChangeEvent.implies(self, stateChangeOutput, *args)
            
class TextActivateEvent(SignalEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "DefaultSelection"    
    
    def _generate(self, argumentString):
        self.widget.setFocus()
        self.widget.typeText("\n")

class ComboTextEvent(TextEvent):
    def _generate(self, argumentString):
        try:
            TextEvent._generate(self, argumentString)
        except RuntimeException: # if it's readonly...
            try:
                self.widget.setSelection(argumentString)
            except RuntimeException, e:
                raise UseCaseScriptError, e.getMessage()
            
    def selectAll(self):
        # Strangely, there is no selectAll method...
        selectionPoint = swt.graphics.Point(0, len(self.widget.getText()))
        runOnUIThread(self.widget.widget.widget.setSelection, selectionPoint)
    
    def shouldRecord(self, event, *args):
        # Better would be to listen for selection in the readonly case. As it is, can't do what we do on TextEvent
        return StateChangeEvent.shouldRecord(self, event, *args)

class TableSelectEvent(StateChangeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "MouseDown"
    
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "CellSelection" ]
    
    def _generate(self, argumentString):
        indexer = TableIndexer.getIndexer(self.widget.widget.widget)
        row, col = indexer.getViewCellIndices(argumentString)
        self.widget.click(row, col)
        
    def getStateText(self, event, *args):
        row, col = self.findCell(event)
        indexer = TableIndexer.getIndexer(self.widget.widget.widget)
        return indexer.getCellDescription(row, col)
    
    def shouldRecord(self, event, *args):
        row, _ = self.findCell(event)
        return row is not None and StateChangeEvent.shouldRecord(self, event, *args)
    
    def findCell(self, event):
        pt = swt.graphics.Point(event.x, event.y)
        table = event.widget
        firstRow = table.getTopIndex()
        for rowIndex in range(firstRow, firstRow + table.getItemCount()):
            item = table.getItem(rowIndex)
            for col in range(table.getColumnCount()):
                rect = item.getBounds(col)
                if rect.contains(pt):
                    return rowIndex, col
        return None, None
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput == stateChangeOutput
    
    
class TableIndexer(storytext.guishared.TableIndexer):
    def __init__(self, table):
        storytext.guishared.TableIndexer.__init__(self, table)
        self.cachedRowCount = 0
        
    def getRowCount(self):
        return runOnUIThread(self.table.getItemCount)

    def getCellValue(self, row, col):
        return self.table.getItem(row).getText(col)
    
    def getColumnText(self, col):
        return self.table.getColumn(col).getText()
    
    def findColumnIndex(self, columnName):
        return runOnUIThread(storytext.guishared.TableIndexer.findColumnIndex, self, columnName)
    
    def findRowNames(self):
        column, rowNames = runOnUIThread(storytext.guishared.TableIndexer.findRowNames, self)
        self.cachedRowCount = len(rowNames)
        return column, rowNames
    
    def checkNameCache(self):
        if self.getRowCount() != self.cachedRowCount:
            self.primaryKeyColumn, self.rowNames = self.findRowNames()
    
    def getCellDescription(self, *args, **kw):
        self.checkNameCache()
        return storytext.guishared.TableIndexer.getCellDescription(self, *args, **kw)

    def getViewCellIndices(self, *args, **kw):
        self.checkNameCache()
        return storytext.guishared.TableIndexer.getViewCellIndices(self, *args, **kw)
    
    
class TableColumnHeaderEvent(SignalEvent):
    def __init__(self, *args):
        SignalEvent.__init__(self, *args)
        self.columnsFound = set()
    
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Selection"
    
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "ColumnSelection" ]
    
    def addColumnListeners(self, *args):
        for column in self.widget.widget.widget.getColumns():
            if column not in self.columnsFound:
                self.columnsFound.add(column)
                column.addListener(*args)

    def addListeners(self, *args):
        self.addColumnListeners(*args)            
        class PaintListener(swt.widgets.Listener):
            def handleEvent(lself, e): #@NoSelf
                self.addColumnListeners(*args)
        self.widget.widget.widget.addListener(swt.SWT.Paint, PaintListener())
        
    def outputForScript(self, event, *args):
        return " ".join([ self.name, event.widget.getText() ])
    
    def _generate(self, argumentString):
        try:
            column = self.widget.header(argumentString)
            column.click()
        except swtbot.exceptions.WidgetNotFoundException:
            raise UseCaseScriptError, "Could not find column labelled '" + argumentString + "' in table."
    

class TreeEvent(SignalEvent):
    def _generate(self, argumentString):
        if len(argumentString) == 0:
            self.widget.unselect()
        else:
            item = self.findItem(argumentString, self.widget.getAllItems())
            if item:
                self.generateItem(item)
            else:
                raise UseCaseScriptError, "Could not find item labelled '" + argumentString + "' in " + self.getClassDesc() + "."

    def getClassDesc(self):
        return self.widget.widget.widget.__class__.__name__.lower()

    def findItem(self, text, items):
        for item in items:
            if item.getText() == text:
                return item
            if item.isExpanded() and hasattr(item, "getItems"):
                subItem = self.findItem(text, item.getItems())
                if subItem:
                    return subItem
        
    def outputForScript(self, event, *args):
        if event.item is None:
            return self.name
        else:
            # Text may have changed since the application listeners have been applied
            text = DisplayFilter.instance.itemTextCache.pop(event.item, event.item.getText())
            return ' '.join([self.name, text])


class ExpandEvent(TreeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Expand"

    def generateItem(self, item):
        item.expand()


class CollapseEvent(TreeEvent):
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
        return DisplayFilter.instance.getEventFromUser(event) and \
            (event.item is None or event.item in event.widget.getSelection())

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

class ListClickEvent(StateChangeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Selection"
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput.startswith(stateChangeOutput)

    def getStateText(self, *args):
        return ",".join(self.widget.selection())

    def _generate(self, argumentString):
        if len(argumentString) == 0:
            self.widget.unselect()
        else:
            indices = self.getIndices(argumentString)
            self.widget.select(indices)

    def getIndices(self, argumentString):
        indices = []
        for itemText in argumentString.split(","):
            index = self.widget.indexOf(itemText)
            if index >= 0:
                indices.append(index)
            else:
                raise UseCaseScriptError, "Could not find item labelled '" + itemText + "' in list."
        return indices

class DateTimeEvent(StateChangeEvent):
    def __init__(self, *args, **kw):
        StateChangeEvent.__init__(self, *args, **kw)
        self.dateFormat = self.getDateFormat()

    def getDateFormat(self):
        if runOnUIThread(self.widget.widget.widget.getStyle) & swt.SWT.TIME:
            return util.getDateFormat(swt.SWT.TIME)
        else:
            return util.getDateFormat(swt.SWT.DATE)
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Selection"
    
    def getStateText(self, *args):
        return self.dateFormat.format(self.widget.getDate())

    def _generate(self, argumentString):
        try:
            currDate = self.dateFormat.parse(argumentString)
            self.widget.setDate(currDate)
        except ParseException:
            raise UseCaseScriptError, "Could not parse date/time argument '" + argumentString + \
                  "', not of format '" + self.dateFormat.toPattern() + "'."

class DisplayFilter:
    instance = None
    def otherEventCount(self, event):
        if event in self.eventsFromUser:
            return len(self.eventsFromUser) - 1
        else:
            return len(self.eventsFromUser)
        
    def getEventFromUser(self, event):
        if event in self.eventsFromUser:
            return True
        else:
            if len(self.eventsFromUser) == 0:
                self.logger.debug("Rejecting event, it has not yet been seen in the display filter")
            else:
                self.logger.debug("Received event " + event.toString())
                self.logger.debug("Rejecting event, not yet processed " + repr([ e.toString() for e in self.eventsFromUser ]))
            return False
        
    def hasEvents(self):
        return len(self.eventsFromUser) > 0

    def __init__(self, widgetEventTypes):
        self.widgetEventTypes = widgetEventTypes
        self.eventsFromUser = []
        self.disposedShells = []
        self.itemTextCache = {}
        self.logger = logging.getLogger("storytext record")
        DisplayFilter.instance = self
        
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

        return any((self.getShell(event.widget) is currShell for event in self.eventsFromUser))
    
    def hasEventOfType(self, eventType, widget):
        return any((event.type == eventType and event.widget is widget for event in self.eventsFromUser))
        
    def addFilters(self, display, monitorListener):
        class DisplayListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e): #@NoSelf
                storytext.guishared.catchAll(self.handleFilterEvent, e, monitorListener)

        for eventType in self.getAllEventTypes():
            runOnUIThread(display.addFilter, eventType, DisplayListener())
            
        self.addApplicationEventFilter(display)

    def handleFilterEvent(self, e, monitorListener):
        if not self.hasEventOnShell(e.widget) and self.shouldCheckWidget(e.widget, e.type):
            self.logger.debug("Filter for event " + e.toString())
            self.eventsFromUser.append(e)
            class EventFinishedListener(swt.widgets.Listener):
                def handleEvent(listenerSelf, e2): #@NoSelf
                    if e2 is e:
                        self.logger.debug("Filter removed for event " + e.toString())
                        self.eventsFromUser.remove(e)
                    
            runOnUIThread(e.widget.addListener, e.type, EventFinishedListener())
            if e.item:
                # Safe guard against the application changing the text before we can record
                self.itemTextCache[e.item] = e.item.getText()
            # This is basically a failsafe - shouldn't be needed but in case
            # something else goes wrong when recording or widgets appear that for some reason couldn't be found,
            # this is a safeguard against never recording anything again.
            monitorListener.handleEvent(e)
        elif isinstance(e.widget, swt.widgets.Shell) and e.type == swt.SWT.Dispose:
            self.disposedShells.append(e.widget)

    def addApplicationEventFilter(self, display):
        class ApplicationEventListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e): #@NoSelf
                if e.text:
                    storytext.guishared.catchAll(applicationEvent, e.text, "system", delayLevel=len(self.eventsFromUser))
        runOnUIThread(display.addFilter, applicationEventType, ApplicationEventListener())
        
    def shouldCheckWidget(self, widget, eventType):
        if not util.isVisible(widget):
            return False
        for cls, types in self.widgetEventTypes:
            if isinstance(widget, cls) and eventType in types and not self.hasComplexAncestors(widget):
                return True
        return False

    def hasComplexAncestors(self, widget):
        return isinstance(widget.getParent(), swt.widgets.DateTime)

    def getAllEventTypes(self):
        eventTypeSet = set()
        for _, eventTypes in self.widgetEventTypes:
            eventTypeSet.update(eventTypes)
        return eventTypeSet
    
# There is no SWTBot class for these things, so we make our own. We aren't actually going to use it anyway...    
class FakeSWTBotTabFolder(swtbot.widgets.AbstractSWTBot):
    pass

class FakeSWTBotCTabFolder(swtbot.widgets.AbstractSWTBot):
    pass

class BrowserUpdateMonitor(swt.browser.ProgressListener):
    def __init__(self, widget):
        self.widget = widget
        self.urlOrText = self.getUrlOrText()

    def getUrlOrText(self):
        return util.getRealUrl(self.widget) or self.widget.getText()
    
    def changed(self, e):
        pass
    
    def completed(self, e):
        storytext.guishared.catchAll(self.onCompleted, e)
        
    def onCompleted(self, e):
        newText = self.getUrlOrText()
        if newText != self.urlOrText:
            self.urlOrText = newText
            self.sendApplicationEvent(self.widget.getNameForAppEvent() + " to finish loading", "browser")

    def sendApplicationEvent(self, *args):
        applicationEvent(*args)



class WidgetMonitor:
    swtbotMap = { swt.widgets.Button   : (swtbot.widgets.SWTBotButton,
                                         [ (swt.SWT.RADIO, swtbot.widgets.SWTBotRadio),
                                           (swt.SWT.CHECK, swtbot.widgets.SWTBotCheckBox) ]),
                  swt.widgets.MenuItem : (swtbot.widgets.SWTBotMenu, []),
                  swt.widgets.Shell    : (swtbot.widgets.SWTBotShell, []),
                  swt.widgets.ToolItem : ( swtbot.widgets.SWTBotToolbarPushButton,
                                         [ (swt.SWT.DROP_DOWN, swtbot.widgets.SWTBotToolbarDropDownButton),
                                           (swt.SWT.RADIO    , swtbot.widgets.SWTBotToolbarRadioButton),
                                           (swt.SWT.SEPARATOR, swtbot.widgets.SWTBotToolbarSeparatorButton),
                                           (swt.SWT.TOGGLE   , swtbot.widgets.SWTBotToolbarToggleButton) ]),
                  swt.widgets.Text     : (swtbot.widgets.SWTBotText, []),
                  swt.widgets.Link     : (swtbot.widgets.SWTBotLink, []),
                  swt.widgets.List     : (swtbot.widgets.SWTBotList, []),
                  swt.widgets.Combo    : (swtbot.widgets.SWTBotCombo, []),
                  swt.widgets.Table    : (swtbot.widgets.SWTBotTable, []),
                  swt.widgets.TableColumn : (swtbot.widgets.SWTBotTableColumn, []),
                  swt.widgets.Tree     : (swtbot.widgets.SWTBotTree, []),
                  swt.widgets.ExpandBar: (swtbot.widgets.SWTBotExpandBar, []),
                  swt.widgets.DateTime : (swtbot.widgets.SWTBotDateTime, []),
                  swt.widgets.TabFolder: (FakeSWTBotTabFolder, []),
                  swt.custom.CTabFolder: (FakeSWTBotCTabFolder, []),
                  swt.custom.CTabItem  : (swtbot.widgets.SWTBotCTabItem, []),
                  swt.browser.Browser  : (swtbot.widgets.SWTBotBrowser, [])
                  }
    def __init__(self, uiMap):
        self.bot = self.createSwtBot()
        self.widgetsMonitored = set()
        self.uiMap = uiMap
        self.uiMap.scriptEngine.eventTypes = eventTypes
        self.displayFilter = self.getDisplayFilterClass()(self.getWidgetEventTypes())

    def getDisplayFilterClass(self):
        return DisplayFilter

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
            for swtBotClass in [ defaultSwtbotClass] + [ cls for _, cls in styleSwtbotInfo ]:
                for eventClass in eventTypeDict.get(swtBotClass, []):
                    currEventTypes.update(method(eventClass))
            if currEventTypes:
                allEventTypes.append((widgetClass, currEventTypes))
        return allEventTypes
    
    def setUp(self):
        self.forceShellActive()
        self.setUpDisplayFilter()
        allWidgets = self.findAllWidgets()
        newWidgets = set(allWidgets).difference(self.widgetsMonitored)
        self.uiMap.logger.debug("Monitoring all widgets in active shell...")
        self.monitorAllWidgets(self.getActiveShell(), list(newWidgets))
        self.uiMap.logger.debug("Done Monitoring all widgets in active shell.")
        
    def forceShellActive(self):
        if os.pathsep == ":": # os.name == "java", so can't find out that way if we're on UNIX
            # Need to do this for running under Xvfb on UNIX
            # Seems to throw exceptions occasionally on Windows, so don't bother
            runOnUIThread(self.bot.getFinder().getShells()[0].forceActive)

    def getDisplay(self):
        return self.bot.getDisplay()

    def setUpDisplayFilter(self):
        display = self.getDisplay()
        monitorListener = self.addMonitorFilter(display)
        self.displayFilter.addFilters(display, monitorListener)

    def addMonitorFilter(self, display):
        class MonitorListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e): #@NoSelf
                storytext.guishared.catchAll(self.widgetShown, e.widget, e.type)

        monitorListener = MonitorListener()
        runOnUIThread(display.addFilter, swt.SWT.Show, monitorListener)
        runOnUIThread(display.addFilter, swt.SWT.Paint, monitorListener)
        return monitorListener
    
    def widgetShown(self, parent, eventType):
        if parent in self.widgetsMonitored:
            return
        if eventType == swt.SWT.Show:
            self.bot.getFinder().setShouldFindInvisibleControls(True)

        widgets = self.findDescendants(parent)
        if eventType == swt.SWT.Show:
            self.bot.getFinder().setShouldFindInvisibleControls(False)

        self.uiMap.logger.debug("Showing/painting widget of type " +
                                parent.__class__.__name__ + " " + str(id(parent)) + ", monitoring found widgets")
        newWidgets = [ w for w in widgets if w not in self.widgetsMonitored ]
        self.monitorAllWidgets(parent, newWidgets)
        self.uiMap.logger.debug("Done Monitoring all widgets after showing/painting " + 
                                parent.__class__.__name__ + " " + str(id(parent)) + ".")
        
    def findDescendants(self, widget):
        if isinstance(widget, swt.widgets.Menu):
            return ArrayList(self.getMenuItems(widget))
        else:
            matcher = IsAnything()
            return self.bot.widgets(matcher, widget)

    def getMenuItems(self, menu):
        items = []
        for item in menu.getItems():
            submenu = item.getMenu()
            if submenu:
                items += self.getMenuItems(submenu)
            else:
                items.append(item)
        return items

    def monitorAllWidgets(self, parent, widgets):
        widgetsAndMenus = widgets + self.getPopupMenus(widgets)
        self.widgetsMonitored.update(widgetsAndMenus)
        for widget in self.makeAdapters(widgetsAndMenus):
            self.uiMap.monitorWidget(widget)
            self.monitorAsynchronousUpdates(widget)

    def monitorAsynchronousUpdates(self, widget):
        # Browsers load their stuff in the background, must wait for them to finish
        if widget.isInstanceOf(swtbot.widgets.SWTBotBrowser):
            monitor = self.getBrowserUpdateMonitorClass()(widget)
            runOnUIThread(widget.widget.widget.addProgressListener, monitor)
            
    def getBrowserUpdateMonitorClass(self):
        return BrowserUpdateMonitor

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
                menus += filter(lambda m: m not in self.widgetsMonitored, menuFinder.findMenus(IsAnything()))
        return menus

    def findSwtbotClass(self, widget, widgetClass):
        defaultClass, styleClasses = self.swtbotMap.get(widgetClass)
        for currStyle, styleClass in styleClasses:
            if runOnUIThread(widget.getStyle) & currStyle:
                return styleClass
        return defaultClass

    def makeAdapters(self, widgets):
        adapters = []
        for widget in widgets:
            adapter = self.makeAdapter(widget)
            if adapter:
                adapters.append(adapter)
        return adapters

    def makeAdapter(self, widget):
        for widgetClass in self.swtbotMap.keys():
            if isinstance(widget, widgetClass):
                swtbotClass = self.findSwtbotClass(widget, widgetClass)
                try:
                    return WidgetAdapter.adapt(swtbotClass(widget))
                except RuntimeException:
                    # Sometimes widgets are already disposed
                    pass
        
    def getActiveShell(self):
        return self.bot.getFinder().activeShell()

        
eventTypes =  [ (swtbot.widgets.SWTBotButton            , [ SelectEvent ]),
                (swtbot.widgets.SWTBotMenu              , [ SelectEvent ]),
                (swtbot.widgets.SWTBotToolbarPushButton , [ SelectEvent ]),
                (swtbot.widgets.SWTBotToolbarDropDownButton , [ SelectEvent ]),
                (swtbot.widgets.SWTBotToolbarRadioButton, [ RadioSelectEvent ]),
                (swtbot.widgets.SWTBotLink              , [ LinkSelectEvent ]),
                (swtbot.widgets.SWTBotRadio             , [ RadioSelectEvent ]),
                (swtbot.widgets.SWTBotText              , [ TextEvent, TextActivateEvent ]),
                (swtbot.widgets.SWTBotShell             , [ ShellCloseEvent, ResizeEvent ]),
                (swtbot.widgets.SWTBotTable             , [ TableColumnHeaderEvent, TableSelectEvent ]),
                (swtbot.widgets.SWTBotTableColumn       , [ TableColumnHeaderEvent ]),
                (swtbot.widgets.SWTBotTree              , [ ExpandEvent, CollapseEvent,
                                                            TreeClickEvent, TreeDoubleClickEvent ]),
                (swtbot.widgets.SWTBotExpandBar         , [ ExpandEvent, CollapseEvent ]),
                (swtbot.widgets.SWTBotList              , [ ListClickEvent ]),
                (swtbot.widgets.SWTBotCombo             , [ ComboTextEvent ]),
                (FakeSWTBotTabFolder                    , [ TabSelectEvent ]),
                (FakeSWTBotCTabFolder                   , [ CTabSelectEvent ]),
                (swtbot.widgets.SWTBotCTabItem          , [ CTabCloseEvent ]),
                (swtbot.widgets.SWTBotDateTime          , [ DateTimeEvent ]),
                (swtbot.widgets.SWTBotCheckBox          , [ SelectEvent ]) ]
