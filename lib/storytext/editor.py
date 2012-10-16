#!/usr/bin/env python

""" Small GTK GUI to allow the user to enter domain names for user actions.
    Also allow hierarchical viewing of usecases.
    Tkinter users still need GTK for TextTest to work... """

import gtktoolkit, gtk, os, sys, logging, shutil
from optparse import OptionParser
from locale import getdefaultlocale

from ordereddict import OrderedDict
from guishared import UIMapFileHandler
from replayer import ShortcutManager, ReplayScript
from definitions import __version__, waitCommandName
from xml.sax.saxutils import escape
from copy import copy

class UseCaseEditor:
    enterTitle = "Enter Usecase names for auto-recorded actions"
    def __init__(self, fileName, interface, mapFiles):
        self.fileName = fileName
        self.editTitle = self.fileName
        if os.getenv("TEXTTEST_HOME"):
            self.editTitle = self.fileName.replace(os.getenv("TEXTTEST_HOME") + "/", "")
        self.interface = interface
        self.uiMapFileHandler = UIMapFileHandler(mapFiles)
        self.scriptEngine = gtktoolkit.ScriptEngine(uiMapFiles=[])
        self.initShortcutManager()
        self.allEntries = OrderedDict()
        self.popupSensitivities = {}

    def initShortcutManager(self):
        self.shortcutManager = ShortcutManager()
        for shortcut in self.scriptEngine.getShortcuts():
            self.shortcutManager.add(shortcut)

    def run(self):
        commands = [ line.strip() for line in open(self.fileName) ]
        autoGenerated = self.getAutoGenerated(commands)
        autoGeneratedInfo = self.parseAutoGenerated(autoGenerated)
        dialog = self.createDialog(autoGeneratedInfo, commands)
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT or len(autoGenerated) == 0:
            newNames = [ entry.get_text() for entry in self.allEntries.values() ]
            dialog.destroy()
            if len(autoGenerated) > 0:
                self.replaceInFile(self.fileName, self.makeReplacement, zip(autoGenerated, newNames))
                toStore = zip(autoGeneratedInfo.values(), newNames)
                for ((_, widgetDescription, signalName), eventName) in toStore:
                    self.uiMapFileHandler.storeInfo(widgetDescription, signalName, eventName)
                self.uiMapFileHandler.write()
        else:
            # Don't leave a half generated filename behind, if we didn't fill in the dialog properly
            # we should remove it so nobody saves it...
            os.remove(self.fileName)
            dialog.destroy()
 
    def getAutoGenerated(self, commands):
        # Find the auto-generated commands and strip them of their arguments
        autoGenerated = []
        for command in commands:
            if command.startswith("Auto."):
                pos = command.rfind("'")
                commandWithoutArg = command[:pos + 1]
                if not commandWithoutArg in autoGenerated:
                    autoGenerated.append(commandWithoutArg)
        return autoGenerated

    def parseAutoGenerated(self, commands):
        autoGenerated = OrderedDict()
        for command in commands:
            parts = command[5:].split("'")
            initialPart = parts[0][:-1]
            widgetType, signalName = initialPart.split(".", 1)
            widgetDescription = self.uiMapFileHandler.unescape(parts[1])
            autoGenerated[command] = widgetType, widgetDescription, signalName
        return autoGenerated

    def replaceInFile(self, fileName, replaceMethod, *args):
        newFileName = fileName + ".tmp"
        newFile = open(newFileName, "w")
        for i, line in enumerate(open(fileName)):
            newLine = replaceMethod(line, i, *args)
            if newLine:
                newFile.write(newLine)
        newFile.close()
        shutil.move(newFileName, fileName)

    def makeReplacement(self, command, position, replacements):
        for origName, newName in replacements:
            if command.startswith(origName):
                if newName:
                    return command.replace(origName, newName)
                else:
                    return
        return command

    def createDialog(self, autoGenerated, commands):
        title = self.enterTitle if len(autoGenerated) > 0 else self.editTitle
        dialog = gtk.Dialog(title, flags=gtk.DIALOG_MODAL)
        dialog.set_name("Name Entry Window")
        height = int(gtk.gdk.screen_height() * 0.6)
        if len(autoGenerated) > 0:
            contents = self.createTable(autoGenerated, dialog)
            dialog.vbox.pack_start(contents, expand=True, fill=True)
            dialog.vbox.pack_start(gtk.HSeparator(), expand=False, fill=False)
            dialog.set_default_size(-1, height)
        else:
            width = min(int(gtk.gdk.screen_width() * 0.2), 500)
            dialog.set_default_size(width, height)
        
        preview = self.createPreview(commands, autoGenerated)
        dialog.vbox.pack_start(preview, expand=True, fill=True)
        yesButton = dialog.add_button(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
        self.scriptEngine.monitorSignal("finish name entry editing", "clicked", yesButton)
        self.scriptEngine.monitorSignal("close editor window", "delete-event", dialog)
        if len(autoGenerated) > 0:
            cancelButton = dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
            self.scriptEngine.monitorSignal("cancel name entry editing", "clicked", cancelButton)
        dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        dialog.show_all()
        return dialog
    
    def addScrollBar(self, widget, viewport=False): 
        window = gtk.ScrolledWindow()
        window.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        if viewport:
            window.add_with_viewport(widget)
        else:
            window.add(widget)
        return window
        
    def createMarkupLabel(self, markup):
        label = gtk.Label()
        label.set_markup(markup)
        return label

    def activateEntry(self, entry, dialog, *args):
        dialog.response(gtk.RESPONSE_ACCEPT)

    def getActionDescription(self, signalName, widgetType):
        try:
            exec "from " + self.interface + "toolkit import ScriptEngine"
        except ImportError:
            # If we haven't even got any such interface, don't worry about this mechanism
            return signalName
        desc = ScriptEngine.getDisplayName(signalName) #@UndefinedVariable
        if desc:
            return desc
        if signalName == "activate":
            if "Entry" in widgetType:
                return "pressed Enter"
            else:
                return "selected"
        elif signalName == "changed":
            if "Entry" in widgetType:
                return "edited text"
            else:
                return "selected item"

        parts = signalName.split(".")
        if len(parts) == 1:
            return signalName.replace("-", " ")

        if parts[0] == "response":
            text = parts[1]
            if "--" in text:
                return text.replace("--", "='") + "'"
            else:
                return text

        columnName = parts[1]
        remaining = parts[0]
        if remaining == "toggled":
            remaining = ".".join([ remaining, parts[-1] ])
        return ScriptEngine.getColumnDisplayName(remaining) + " '" + columnName + "'" #@UndefinedVariable
        
    def splitAutoCommand(self, command, autoGenerated):
        for cmd in autoGenerated.keys():
            if command.startswith(cmd):
                arg = command.replace(cmd, "").strip()
                return cmd, arg
        return None, None

    def addArgumentMarkup(self, arg):
        return "<i>" + escape(arg) + "</i>" if arg else ""

    def updatePreview(self, entry, data):
        model, iter = data
        text = entry.get_text() or "?"
        args = model.get_value(iter, 2)
        arg = " " + args[0] if args else ""
        markupFullText = self.convertToMarkup(text + self.addArgumentMarkup(arg))
        fullText = text + arg
        model.set_value(iter, 0, markupFullText)
        model.set_value(iter, 1, fullText)
        
    def addText(self, model, rootIter, text, originalText, arguments, followIter=None):
        return model.insert_before(rootIter, followIter, [self.convertToMarkup(text), originalText, arguments])

    def addCommandToModel(self, command, model, rootIter=None):
        shortcut, args = self.shortcutManager.findShortcut(command)
        if shortcut:
            self.addShortcutCommandToModel(shortcut, args, model, rootIter)
        else:
            self.addBasicCommandToModel(command, model, rootIter)
            
    def addShortcutCommandToModel(self, shortcut, args, model, rootIter, followIter=None):
        italicArgs = [ "<i>" + escape(arg) + "</i>" for arg in args ]
        text = "<b>" + shortcut.getShortcutNameWithArgs(italicArgs) + "</b>"
        iter = self.addText(model, rootIter, text, shortcut.getShortcutNameWithArgs(args), args, followIter)
        if not followIter:
            for step in shortcut.commands:
                self.addCommandToModel(shortcut.replaceArgs(step, args), model, iter)
        return iter
            
    def extractArgsAddMarkup(self, text, cmd):
        markup = text.replace(cmd, cmd + "<i>") + "</i>"
        arg = text.replace(cmd, "").strip()
        args = [ arg ] if arg else []
        return markup, args

    def addBasicCommandToModel(self, command, model, rootIter):
        args = []
        if command.startswith(waitCommandName):
            markup, _ = self.extractArgsAddMarkup(escape(command), waitCommandName)
            # Ignore args for wait commands, they don't have anything in common
            text = '<span foreground="#826200">' + markup + "</span>"
            widgetDesc = None
        else:
            widgetDesc, signalName = self.uiMapFileHandler.findSectionAndOption(command)
            text = escape(command)
            if widgetDesc:
                cmd = self.uiMapFileHandler.get(widgetDesc, signalName)
                if cmd != text:
                    text, args = self.extractArgsAddMarkup(text, cmd)
            else:
                text = '<span foreground="red">' + text + "</span>"
        iter = self.addText(model, rootIter, text, command, args)
        if widgetDesc:
            msg = "Perform " + repr(signalName) + " on widget identified by " + repr(escape(widgetDesc))
            self.addText(model, iter, msg, None, [])

    def createPreview(self, commands, autoGenerated):
        self.treeModel = gtk.TreeStore(str, str, object)
        view = gtk.TreeView(self.treeModel)
        view.set_headers_visible(False)
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn("", cell, markup=0)
        view.append_column(column)
        view.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.popup = self.createPopupMenu(view)
        for command in commands:
            autoCmdName, autoArg = self.splitAutoCommand(command, autoGenerated)
            if autoCmdName:
                args = [ autoArg ] if autoArg else []
                autoArgMarkup = self.addArgumentMarkup(autoArg)
                text = "? " + autoArgMarkup if autoArgMarkup else "?"
                iter = self.addText(self.treeModel, None, text, None, args)
                entry = self.allEntries.get(autoCmdName)
                entry.connect("changed", self.updatePreview, (self.treeModel, iter))
                widgetType, widgetDesc, signalName = autoGenerated.get(autoCmdName)
                msg = "Perform " + repr(signalName) + " on widget of type " + repr(widgetType) + " identified by '" + widgetDesc + "'"
                self.addText(self.treeModel, iter, msg, msg, [])
            else:
                self.addCommandToModel(command, self.treeModel)

        view.connect("button-press-event", self.showPopupMenu)
        self.scriptEngine.monitorSignal("expand preview node", "row-expanded", view)
        self.scriptEngine.monitorSignal("select preview node", "changed", view)
        self.scriptEngine.monitorSignal("show preview node options for", "button-press-event", view)
        scrolled = self.addScrollBar(view)
        if len(autoGenerated) > 0:
            frame = gtk.Frame("Current Usecase Preview")
            frame.add(scrolled)
            return frame
        else:
            return scrolled

    def convertToUtf8(self, text):
        return self.convertEncoding(text, 'utf-8', 'replace')
    
    def convertToMarkup(self, text):
        return self.convertEncoding(text, 'ascii', 'xmlcharrefreplace')
    
    def convertEncoding(self, text, targetEncoding, replaceMethod):
        try:
            localeEncoding = getdefaultlocale()[1]
            if localeEncoding:
                return unicode(text, localeEncoding, errors="replace").encode(targetEncoding, replaceMethod)
        except ValueError:
            pass
        return text

    def createTable(self, autoGenerated, dialog):
        table = gtk.Table(rows=len(autoGenerated) + 1, columns=4)
        table.set_col_spacings(20)
        headers = [ "Widget Type", "Identified By", "Action Performed", "Usecase Name" ]
        for col, header in enumerate(headers):
            table.attach(self.createMarkupLabel("<b><u>" + header + "</u></b>"), 
                         col, col + 1, 0, 1, xoptions=gtk.FILL, yoptions=gtk.FILL)
        for rowIndex, (command, (widgetType, widgetDesc, signalName)) in enumerate(autoGenerated.items()):
            table.attach(gtk.Label(widgetType), 0, 1, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL, yoptions=gtk.FILL)
            actionDesc = self.getActionDescription(signalName, widgetType)
            widgetDescUtf8 = self.convertToUtf8(widgetDesc)
            table.attach(gtk.Label(widgetDescUtf8), 1, 2, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL, yoptions=gtk.FILL)
            table.attach(gtk.Label(actionDesc), 2, 3, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL, yoptions=gtk.FILL)
            entry = gtk.Entry()
            scriptName = "enter usecase name for signal '" + signalName + "' on " + widgetType + " '" + widgetDesc + "' ="
            self.scriptEngine.monitorSignal(scriptName, "changed", entry)
            entry.connect("activate", self.activateEntry, dialog)
            self.scriptEngine.monitorSignal("finish name entry editing by pressing <enter>", "activate", entry)
            self.allEntries[command] = entry
            table.attach(entry, 3, 4, rowIndex + 1, rowIndex + 2, yoptions=gtk.FILL)
        table.show_all()
        frame = gtk.Frame("Previously unseen actions: provide names for the interesting ones")
        frame.add(self.addScrollBar(table, viewport=True))
        return frame

    def createPopupMenu(self, widget):
        menu = gtk.Menu()
        item = gtk.MenuItem("Create shortcut")
        menu.append(item)
        item.connect("activate", self.createShortcut, widget)
        self.popupSensitivities[item] = self.setCreateShortcutSensitivity
        self.scriptEngine.monitorSignal("create a new shortcut", "activate", item)
        item.show()
        return menu
    
    def applySensitivities(self, selection):
        for item, method in self.popupSensitivities.items():
            method(item, selection)

    def setCreateShortcutSensitivity(self, item, selection):
        # Check selection has at least 2 elements and is consecutive
        if selection.count_selected_rows() > 1 and self.isConsecutive(selection) and \
        not self.shortcutsSelected(selection):
            item.set_sensitive(True)
        else:
            item.set_sensitive(False)

    def showPopupMenu(self, treeView, event):
        if event.button == 3:
            time = event.time
            pathInfo = treeView.get_path_at_pos(int(event.x), int(event.y))
            selection = treeView.get_selection()
            selectedRows = selection.get_selected_rows()
            self.applySensitivities(selection)
            # If they didnt right click on a currently selected
            # row, change the selection
            if pathInfo is not None:
                if pathInfo[0] not in selectedRows[1]:
                    selection.unselect_all()
                    selection.select_path(pathInfo[0])
                treeView.grab_focus()
                self.popup.popup(None, None, None, event.button, time)
                treeView.emit_stop_by_name("button-press-event")

    def createShortcut(self, widget, view):
        selection = view.get_selection()
        lines, arguments, positions = self.selectionToModel(selection)
        self.createShortcutFromLines(lines, arguments, positions, selection)
    
    def selectionToModel(self, selection):
        lines, positions = [], []
        allArguments = []
        def addSelected(treemodel, path, iter, *args):
            line = treemodel.get_value(iter, 1)
            currArgs = treemodel.get_value(iter, 2)
            lines.append(line)
            for arg in currArgs:
                allArguments.append(arg)
            positions.append(path[0])

        selection.selected_foreach(addSelected)
        return lines, allArguments, positions
        
    def createShortcutFromLines(self, lines, arguments, positionsInUsecase, selection):
        dialog = gtk.Dialog("New Shortcut", flags=gtk.DIALOG_MODAL)
        dialog.set_name("New Shortcut Window")
        label = gtk.Label("New name for shortcut:")
        entry = gtk.Entry()
        entry.set_name("New Name")
        if arguments:
            defaultText = "Do something with " + " and ".join(arguments)
            entry.set_text(defaultText)

        dialog.vbox.set_spacing(10)
        dialog.vbox.pack_start(label, expand=False, fill=False)
        dialog.vbox.pack_start(entry, expand=True, fill=True)
        dialog.vbox.pack_start(gtk.HSeparator(), expand=False, fill=False)
        self.scriptEngine.monitorSignal("enter new shortcut name", "changed", entry)
        shortcutView = self.createShortcutPreview(lines, arguments, entry)
        frame = gtk.Frame("")
        frame.get_label_widget().set_use_markup(True)
        self.updateShortcutName(entry, frame, arguments)
        frame.add(shortcutView)
        entry.connect("changed", self.updateShortcutName, frame, arguments)
        dialog.vbox.pack_end(frame, expand=True, fill=True)
        yesButton = dialog.add_button(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
        self.scriptEngine.monitorSignal("accept new shortcut name", "clicked", yesButton)
        cancelButton = dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        self.scriptEngine.monitorSignal("cancel new shortcut name", "clicked", cancelButton)
        dialog.connect("response", self.respond, entry, frame, shortcutView, arguments, positionsInUsecase, selection)
        dialog.show_all()
        
    def updateShortcutName(self, textEntry, frame, arguments):
        newName = textEntry.get_text()
        for arg in arguments:
            newName = newName.replace(arg, "$")
        markup = "<b><i>" + newName.lower().replace(" ", "_") + ".shortcut" + "</i></b>"
        frame.get_label_widget().set_label(markup)

    def copyRow(self, iter, shortcutIter):
        row = list(self.treeModel.get(iter, 0, 1, 2))
        return self.treeModel.append(shortcutIter, row)

    def addShortcutToPreview(self, shortcut, arguments, selection):
        iters = []
        def addSelected(model, path, iter, *args):
            iters.append(iter)
        selection.selected_foreach(addSelected)
        shortcutIter = self.addShortcutCommandToModel(shortcut, arguments, self.treeModel, None, iters[0])
        for iter in iters:
            newShortcutIter = self.copyRow(iter, shortcutIter)
            subIter = self.treeModel.iter_children(iter)
            if subIter is not None:
                self.copyRow(subIter, newShortcutIter)
            self.treeModel.remove(iter)

    def getNameAndArguments(self, givenText, arguments):
        name = givenText.lower()
        usedArguments = []
        for arg in arguments:
            pos = name.find(arg.lower())
            while pos != -1:
                if pos == 0 or name[pos - 1] == " ":
                    endPos = pos + len(arg)
                    if endPos == len(name) or name[endPos] == " ":
                        name = name[:pos] + arg + name[endPos:]
                        usedArguments.append(arg)
                pos = name.find(arg.lower(), pos + 1)
        return name, usedArguments

    def respond(self, dialog, responseId, entry, frame, shortcutView, arguments, positions, selection):
        if responseId == gtk.RESPONSE_ACCEPT:
            newNameForUseCase, usedArguments = self.getNameAndArguments(entry.get_text(), arguments)
            if self.checkShortcutName(dialog, newNameForUseCase):
                dialog.hide()
                shortcut = self.saveShortcut(frame.get_label(), self.getShortcutLines(shortcutView))
                self.replaceInFile(self.fileName, self.makeShortcutReplacement, positions, newNameForUseCase)
                self.shortcutManager.add(shortcut)
                self.addShortcutToPreview(shortcut, usedArguments, selection)
        else:
            dialog.hide()
            
    def getShortcutLines(self, shortcutView):
        model = shortcutView.get_model()
        lines = []
        def addSelected(model, path, iter, *args):
            lines.append(model.get_value(iter, 0))
        model.foreach(addSelected)
        return lines
    
    def checkShortcutName(self, parent, name):
        if not name:
            self.showErrorDialog(parent, "The shortcut name can't be empty.")
            return False
        elif self.isInUIMap(name):
            self.showErrorDialog(parent, "The shortcut name already exists in the UI map file.")
            return False
        elif self.isInShortcuts(name):
            self.showErrorDialog(parent, "The shortcut name is already being used for another shortcut.")
            return False
        return True
    
    def isInUIMap(self, name):
        _,option = self.uiMapFileHandler.findSectionAndOption(name)
        return option is not None
    
    def isInShortcuts(self, name):
        return any(shortcut.getShortcutName() == name for shortcut in self.scriptEngine.getShortcuts())
        
    def saveShortcut(self, name, lines):
        storytextDir = os.environ["STORYTEXT_HOME"]
        if not os.path.isdir(storytextDir):
            os.makedirs(storytextDir)
        fileName = os.path.join(storytextDir, name)
        with open(fileName, "w") as f:
            for line in lines:
                f.write(line + "\n")
        return ReplayScript(fileName)
    
    def shortcutsSelected(self, selection):
        shortcuts = []
        def addSelected(treemodel, path, iter, *args):
            shortcuts.append("<b>" in treemodel.get_value(iter, 0))

        selection.selected_foreach(addSelected)
        return any(shortcuts)
    
    def isConsecutive(self, selection):
        paths = []
        def addSelected(treemodel, path, *args):
            paths.append(path)

        selection.selected_foreach(addSelected)
        prevIx = None
        for path in paths:
            if len(path) > 1:
                return False # Can't make shortcuts out of lines further down the hierarchy
            ix = path[0]
            if prevIx is not None and ix - prevIx > 1:
                return False
            prevIx = ix
        return True
        
    def makeShortcutReplacement(self, line, position, positions, shortcutName):
        if position in positions:
            return shortcutName + "\n" if position == positions[0] else None
        return line
        
    def showErrorDialog(self, parent, message):
        self.showErrorWarningDialog(parent, message, gtk.MESSAGE_ERROR, "Error")

    def showWarningDialog(self, parent, message):
        self.showErrorWarningDialog(parent, message, gtk.MESSAGE_WARNING, "Warning")

    def showErrorWarningDialog(self, parent, message, stockIcon, alarmLevel):
        dialog = self.createMessageDialog(parent, message, stockIcon, alarmLevel)
        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.connect("response", self._cleanDialog)
        dialog.show_all()

    def _cleanDialog(self, dialog, *args):
        dialog.hide()

    def createMessageDialog(self, parent, message, stockIcon, alarmLevel):
        dialogTitle = "StoryText " + alarmLevel
        dialog = gtk.MessageDialog(parent, gtk.DIALOG_MODAL, stockIcon, gtk.BUTTONS_OK, None)
        # Would like to use dialog.get_widget_for_response(gtk.RESPONSE_OK), introduced in gtk 2.22 instead
        okButton = dialog.action_area.get_children()[0]
        self.scriptEngine.monitorSignal("accept message", "clicked", okButton)
        dialog.set_title(dialogTitle)        
        dialog.set_markup(message)
        return dialog
    
    def createShortcutPreview(self, commands, arguments, textEntry):
        listModel = gtk.ListStore(str, str, str)
        view = gtk.TreeView(listModel)
        view.set_headers_visible(False)
        cmdRenderer = gtk.CellRendererText()
        cmdColumn = gtk.TreeViewColumn("", cmdRenderer, text=0)
        view.append_column(cmdColumn)
        view.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        argumentIndex = 0
        for command in commands:
            arg = arguments[argumentIndex] if argumentIndex < len(arguments) else ""
            text, argument = self.replaceArguments(command, arg)
            iter1 = listModel.append([text, command, argument])
            if argument:
                argumentIndex = argumentIndex + 1 % len(arguments)
                textEntry.connect("changed", self.handleArguments, (listModel, iter1))

        self.scriptEngine.monitorSignal("select preview node", "changed", view)
        self.scriptEngine.monitorSignal("show preview node options for", "button-press-event", view)
        return view

    def replaceArguments(self, command, argument):
        if argument and command.endswith(argument):
            return command.replace(argument, "$"), argument
        else:
            return command, ""
            
    def handleArguments(self, widget, data):
        model, iter = data
        newName = widget.get_text()
        originalValue = model.get_value(iter, 1)
        currentValue = model.get_value(iter, 0)
        arg = model.get_value(iter, 2)
        if newName.find(" " + arg + " ") >= 0 or newName.startswith(arg + " ") or newName.endswith(" " + arg):
            if originalValue == currentValue:
                model.set_value(iter, 0, currentValue.replace(arg, "$"))
        else:
            model.set_value(iter, 0, originalValue)
        
def main():
    usage = """usage: %prog [options] [FILE] ...

The "StoryText Editor" is a small PyGTK program that allows StoryText users to enter
domain-specific names for the actions they record in their GUI tests. The aim is therefore to
produce a complete usecase script if some actions had no names, and to update the UI map file 
accordingly.

It also acts as a hierchical viewer to be able to easily see shortcuts, UI map references etc"""

    parser = OptionParser(usage, version="%prog " + __version__)
    parser.add_option("-i", "--interface", metavar="INTERFACE",
                      help="type of interface used by application, should be 'gtk' or 'tkinter' ('gtk' is default)", 
                      default="gtk")
    parser.add_option("-l", "--loglevel", default="WARNING", 
                      help="produce logging at level LEVEL, should be a valid Python logging level such as 'info' or 'debug'. Basically useful for debugging and testing", metavar="LEVEL")
    parser.add_option("-m", "--mapfiles", default=os.path.join(gtktoolkit.ScriptEngine.storytextHome, "ui_map.conf"),
                      help="Update the UI map file(s) at FILE1,... If not set StoryText will read and write such a file at the its own default location ($STORYTEXT_HOME/ui_map.conf). If multiple files are provided, the last in the list will be used for writing.", metavar="FILE1,...")
    
    options, args = parser.parse_args()
    if os.path.isfile(args[0]):
        uiMapFiles = options.mapfiles.split(",")
        level = eval("logging." + options.loglevel.upper())
        logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s")
        editor = UseCaseEditor(args[0], options.interface, uiMapFiles)
        editor.run()
