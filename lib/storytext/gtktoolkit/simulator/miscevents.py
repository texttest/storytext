
""" All the remaining widget events that didn't fit anywhere else """

from baseevents import StateChangeEvent, SignalEvent
from storytext.definitions import UseCaseScriptError
import gtk, types

origToggleAction = gtk.ToggleAction
origRadioAction = gtk.RadioAction

def performInterceptions():
    gtk.ToggleAction = ToggleAction
    gtk.RadioAction = RadioAction
    return {}

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
        if widget.isInstanceOf(gtk.RadioButton) or widget.isInstanceOf(gtk.RadioToolButton) or \
           widget.isInstanceOf(gtk.RadioMenuItem):
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
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter()).replace("\n", "\\n")

    @staticmethod
    def widgetHasSignal(widget, signalName):
        return widget.isInstanceOf(gtk.TextView) # exists on the buffer

    def getChangeMethod(self):
        return self.widget.get_buffer().set_text

    def getGenerationArguments(self, text):
        return [ text.replace("\\n", "\n") ]

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
