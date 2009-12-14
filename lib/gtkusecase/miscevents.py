
""" All the remaining widget events that didn't fit anywhere else """

from baseevents import StateChangeEvent, SignalEvent
from usecase import UseCaseScriptError
import gtk, types


class EntryEvent(StateChangeEvent):
    def getStateDescription(self, *args):
        return self.widget.get_text()

    def getChangeMethod(self):
        return self.widget.set_text


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

    
class ActivateEvent(StateChangeEvent):
    signalName = "toggled"
    def __init__(self, name, widget, relevantState):
        StateChangeEvent.__init__(self, name, widget)
        self.relevantState = self.parseState(relevantState)

    def parseState(self, relevantState):
        if type(relevantState) == types.StringType:
            return relevantState == "true"
        else:
            return relevantState

    def eventIsRelevant(self):
        return self.widget.get_active() == self.relevantState

    def _outputForScript(self, *args):
        return self.name

    def getStateChangeArgument(self, argumentString):
        return self.relevantState

    def getChangeMethod(self):
        return self.widget.set_active

    def getProgrammaticChangeMethods(self):
        return [ self.widget.toggled ]
    
    def getUiMapSignature(self):
        return self.getRecordSignal() + "." + repr(self.relevantState)

    @classmethod
    def getAssociatedSignatures(cls, widget):
        # Radio buttons can't be unchecked directly
        if isinstance(widget, gtk.RadioButton):
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
        if self.totalSpace() == 0:
            return False
        
        newState = self.getStateDescription()
        if newState != self.prevState:
            self.prevPos = newState
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
