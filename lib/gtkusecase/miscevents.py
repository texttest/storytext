
""" All the remaining widget events that didn't fit anywhere else """

from baseevents import StateChangeEvent, SignalEvent
from usecase import UseCaseScriptError
import gtk, types

origToggleAction = gtk.ToggleAction
origRadioAction = gtk.RadioAction

def performInterceptions():
    gtk.ToggleAction = ToggleAction
    gtk.RadioAction = RadioAction

toggleActionProxies = {}

class ToggleAction(origToggleAction):
    def create_menu_item(self):
        item = origToggleAction.create_menu_item(self)
        toggleActionProxies[item] = self
        return item
    
    def create_tool_item(self):
        item = origToggleAction.create_tool_item(self)
        toggleActionProxies[item] = self
        return item


class RadioAction(origRadioAction):
    def create_menu_item(self):
        item = origRadioAction.create_menu_item(self)
        toggleActionProxies[item] = self
        return item
    
    def create_tool_item(self):
        item = origRadioAction.create_tool_item(self)
        toggleActionProxies[item] = self
        return item    

    
class ActivateEvent(StateChangeEvent):
    signalName = "toggled"
    widgetsBlocked = set()
    def __init__(self, name, widget, relevantState):
        StateChangeEvent.__init__(self, name, widget)
        self.relevantState = relevantState == "true"

    def eventIsRelevant(self):
        if self.widget.get_active() != self.relevantState:
            return False
        if self.widget in self.widgetsBlocked:
            self.widgetsBlocked.remove(self.widget)
            return False

        action = toggleActionProxies.get(self.widget)
        if action:
            for proxy in action.get_proxies():
                if proxy is not self.widget:
                    self.widgetsBlocked.add(proxy)
        return True

    def _outputForScript(self, *args):
        return self.name

    def getStateChangeArgument(self, argumentString):
        return self.relevantState

    def getChangeMethod(self):
        return self.widget.set_active

    def getProgrammaticChangeMethods(self):
        try:
            return [ self.widget.toggled ]
        except AttributeError:
            return [] # gtk.ToggleToolButton doesn't have this
    
    @classmethod 
    def isRadio(cls, widget):
        if isinstance(widget, gtk.RadioButton) or isinstance(widget, gtk.RadioToolButton) or \
            isinstance(widget, gtk.RadioMenuItem):
            return True
        action = toggleActionProxies.get(widget)
        return action and isinstance(action, gtk.RadioAction)

    @classmethod
    def getAssociatedSignatures(cls, widget):
        # Radio buttons can't be unchecked directly
        if cls.isRadio(widget):
            return [ cls.signalName + ".true" ]
        else:
            return [ cls.signalName + ".true", cls.signalName + ".false" ]


class MenuActivateEvent(ActivateEvent):
    def generate(self, *args):
        self.checkWidgetStatus()
        self.widget.emit("activate-item")


# Confusingly different signals used in different circumstances here.
class MenuItemSignalEvent(SignalEvent):
    signalName = "activate"
    def getGenerationArguments(self, *args):
        return [ "activate-item" ]        


class EntryEvent(StateChangeEvent):
    def getStateDescription(self, *args):
        return self.widget.get_text()

    def getChangeMethod(self):
        return self.widget.set_text


class TextViewEvent(StateChangeEvent):
    def getStateDescription(self, *args):
        buffer = self.widget.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter())

    def getChangeMethod(self):
        return self.widget.get_buffer().set_text

    def connectRecord(self, method):
        self._connectRecord(self.widget.get_buffer(), method)

    def getProgrammaticChangeMethods(self):
        buffer = self.widget.get_buffer()
        return [ buffer.insert, buffer.insert_at_cursor, buffer.insert_interactive,
                 buffer.insert_interactive_at_cursor, buffer.insert_range, buffer.insert_range_interactive,
                 buffer.insert_with_tags, buffer.insert_with_tags_by_name, buffer.insert_pixbuf,
                 buffer.insert_child_anchor, buffer.delete, buffer.delete_interactive ]


class ComboBoxEvent(StateChangeEvent):
    def getStateDescription(self, *args):
        # Hardcode 0, seems to work for the most part...
        return self.widget.get_model().get_value(self.widget.get_active_iter(), 0)

    def getChangeMethod(self):
        return self.widget.set_active_iter
    
    def getProgrammaticChangeMethods(self):
        return [ self.widget.set_active ]

    def generate(self, argumentString):
        self.widget.get_model().foreach(self.setMatchingIter, argumentString)

    def setMatchingIter(self, model, path, iter, argumentString):
        if model.get_value(iter, 0) == argumentString:
            self.changeMethod(iter)
            return True


class NotebookPageChangeEvent(StateChangeEvent):
    signalName = "switch-page"
    def getChangeMethod(self):
        return self.widget.set_current_page
    def eventIsRelevant(self):
        # Don't record if there aren't any pages
        return self.widget.get_current_page() != -1
    def getStateDescription(self, ptr, pageNum, *args):
        newPage = self.widget.get_nth_page(pageNum)
        return self.widget.get_tab_label_text(newPage)
    def getStateChangeArgument(self, argumentString):
        for i in range(len(self.widget.get_children())):
            page = self.widget.get_nth_page(i)
            if self.widget.get_tab_label_text(page) == argumentString:
                return i
        raise UseCaseScriptError, "'" + self.name + "' failed : Could not find page '" + \
            argumentString + "' in the " + self.widget.get_name().replace("Gtk", "") + "." 


class PaneDragEvent(StateChangeEvent):
    signalName = "notify::position"
    def __init__(self, name, widget, *args):
        StateChangeEvent.__init__(self, name, widget, *args)
        widget.connect("notify::max-position", self.changeMaxMin)
        widget.connect("notify::min-position", self.changeMaxMin)
        self.prevState = ""

    def setProgrammaticChange(self, val, *args, **kwargs):
        if val:
            self.programmaticChange = val

    def changeMaxMin(self, *args):
        if self.totalSpace() > 0:
            self.prevState = self.getStateDescription()

    def shouldRecord(self, *args):
        ret = StateChangeEvent.shouldRecord(self, *args)
        self.programmaticChange = False
        return ret

    def eventIsRelevant(self):
        newState = self.getStateDescription()
        if newState != self.prevState:
            self.prevState = newState
            return True
        else:
            return False

    def totalSpace(self):
        return self.widget.get_property("max-position") - self.widget.get_property("min-position")

    def getStatePercentage(self):
        return float(100 * (self.widget.get_position() - self.widget.get_property("min-position"))) / self.totalSpace()

    def getStateDescription(self, *args):
        return str(int(self.getStatePercentage() + 0.5)) + "% of the space"

    def getStateChangeArgument(self, argumentString):
        percentage = int(argumentString.split()[0][:-1])
        return int(float(self.totalSpace() * percentage) / 100 + 0.5) + self.widget.get_property("min-position")

    def getProgrammaticChangeMethods(self):
        return [ self.widget.check_resize ]

    def getChangeMethod(self):
        return self.widget.set_position
