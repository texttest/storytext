#!/usr/bin/env python

""" Small GTK GUI to allow the user to enter domain names for user actions.
    Tkinter users still need GTK for TextTest to work... """

import gtktoolkit, gtk, os, sys, logging, shutil
from optparse import OptionParser

from ordereddict import OrderedDict
from guishared import UIMapFileHandler
from definitions import __version__

class UseCaseNameChooser:
    title = "Enter Usecase names for auto-recorded actions"
    def __init__(self, fileName, interface, mapFiles):
        self.fileName = fileName
        self.interface = interface
        self.uiMapFileHandler = UIMapFileHandler(mapFiles)
        self.scriptEngine = gtktoolkit.ScriptEngine(uiMapFiles=[])
        self.allEntries = OrderedDict()

    def collectNames(self):
        commands = [ line.strip() for line in open(self.fileName) ]
        autoGenerated = self.getAutoGenerated(commands)
        if len(autoGenerated) == 0:
            return

        autoGeneratedInfo = self.parseAutoGenerated(autoGenerated)
        dialog = self.createDialog(autoGeneratedInfo, commands)
        dialog.run()
        newNames = [ entry.get_text() for entry in self.allEntries.values() ]
        dialog.destroy()
        self.replaceInFile(self.fileName, zip(autoGenerated, newNames))
        toStore = zip(autoGeneratedInfo, newNames)
        for ((command, widgetType, widgetDescription, signalName), eventName) in toStore:
            self.uiMapFileHandler.storeInfo(widgetDescription, signalName, eventName)
        self.uiMapFileHandler.write()
 
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
        autoGenerated = []
        for command in commands:
            parts = command[5:].split("'")
            initialPart = parts[0][:-1]
            widgetType, signalName = initialPart.split(".", 1)
            widgetDescription = parts[1]
            autoGenerated.append((command, widgetType, widgetDescription, signalName))
        return autoGenerated

    def replaceInFile(self, fileName, replacements):
        newFileName = fileName + ".tmp"
        newFile = open(newFileName, "w")
        for line in open(fileName):
            newLine = self.makeReplacement(line, replacements)
            if newLine:
                newFile.write(newLine)
        newFile.close()
        shutil.move(newFileName, fileName)

    def makeReplacement(self, command, replacements):
        for origName, newName in replacements:
            if command.startswith(origName):
                if newName:
                    return command.replace(origName, newName)
                else:
                    return
        return command

    def createDialog(self, autoGenerated, commands):
        dialog = gtk.Dialog(self.title, flags=gtk.DIALOG_MODAL)
        dialog.set_name("Name Entry Window")
        contents = self.createTable(autoGenerated, dialog)
        dialog.vbox.pack_start(contents, expand=True, fill=True)
        preview = self.createPreview(commands)
        dialog.vbox.pack_start(gtk.HSeparator())
        dialog.vbox.pack_start(preview, expand=True, fill=True)
        yesButton = dialog.add_button(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)
        dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        self.scriptEngine.monitorSignal("finish name entry editing", "clicked", yesButton)
        dialog.show_all()
        return dialog
        
    def createMarkupLabel(self, markup):
        label = gtk.Label()
        label.set_markup(markup)
        return label

    def activateEntry(self, entry, dialog, *args):
        dialog.response(gtk.RESPONSE_ACCEPT)

    def getActionDescription(self, signalName, widgetType):
        exec "from " + self.interface + "toolkit import ScriptEngine"
        desc = ScriptEngine.getDisplayName(signalName)
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
        return ScriptEngine.getColumnDisplayName(remaining) + " '" + columnName + "'"
        
    def splitAutoCommand(self, command):
        for cmd in self.allEntries.keys():
            if command.startswith(cmd):
                arg = command.replace(cmd, "")
                return cmd, arg
        return None, None

    def updatePreview(self, entry, data):
        buffer, lineNo, arg = data
        text = entry.get_text()
        toUse = "?"
        if text:
            toUse = text + arg 
        start = buffer.get_iter_at_line(lineNo)
        end = buffer.get_iter_at_line(lineNo + 1)
        buffer.delete(start, end)
        buffer.insert(start, toUse + "\n")

    def createPreview(self, commands):
        frame = gtk.Frame("Current Usecase Preview")
        view = gtk.TextView()
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_wrap_mode(gtk.WRAP_WORD)
        buffer = view.get_buffer()
        for ix, command in enumerate(commands):
            autoCmdName, autoArg = self.splitAutoCommand(command)
            if autoCmdName:
                buffer.insert(buffer.get_end_iter(), "?\n")
                entry = self.allEntries.get(autoCmdName)
                entry.connect("changed", self.updatePreview, (buffer, ix, autoArg))
            else:                
                buffer.insert(buffer.get_end_iter(), command + "\n")
        frame.add(view)
        return frame

    def createTable(self, autoGenerated, dialog):
        table = gtk.Table(rows=len(autoGenerated) + 1, columns=4)
        table.set_col_spacings(20)
        headers = [ "Widget Type", "Identified By", "Action Performed", "Usecase Name" ]
        for col, header in enumerate(headers):
            table.attach(self.createMarkupLabel("<b><u>" + header + "</u></b>"), 
                         col, col + 1, 0, 1, xoptions=gtk.FILL)
        for rowIndex, (command, widgetType, widgetDesc, signalName) in enumerate(autoGenerated):
            table.attach(gtk.Label(widgetType), 0, 1, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL)
            actionDesc = self.getActionDescription(signalName, widgetType)
            table.attach(gtk.Label(widgetDesc), 1, 2, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL)
            table.attach(gtk.Label(actionDesc), 2, 3, rowIndex + 1, rowIndex + 2, xoptions=gtk.FILL)
            entry = gtk.Entry()
            scriptName = "enter usecase name for signal '" + signalName + "' on " + widgetType + " '" + widgetDesc + "' ="
            self.scriptEngine.monitorSignal(scriptName, "changed", entry)
            entry.connect("activate", self.activateEntry, dialog)
            self.scriptEngine.monitorSignal("finish name entry editing by pressing <enter>", "activate", entry)
            self.allEntries[command] = entry
            table.attach(entry, 3, 4, rowIndex + 1, rowIndex + 2)
        frame = gtk.Frame("Previously unseen actions: provide names for the interesting ones")
        frame.add(table)
        return frame

def main():
    usage = """usage: %prog [options]  ...

The "Usecase Name Chooser" is a small PyGTK program that allows PyUseCase users to enter
domain-specific names for the actions they record in their GUI tests. The aim is therefore to
produce a complete usecase script if some actions had no names, and to update the UI map file 
accordingly."""

    parser = OptionParser(usage, version="%prog " + __version__)
    parser.add_option("-i", "--interface", metavar="INTERFACE",
                      help="type of interface used by application, should be 'gtk' or 'tkinter' ('gtk' is default)", 
                      default="gtk")
    parser.add_option("-l", "--loglevel", default="WARNING", 
                      help="produce logging at level LEVEL, should be a valid Python logging level such as 'info' or 'debug'. Basically useful for debugging and testing", metavar="LEVEL")
    parser.add_option("-m", "--mapfiles", default=os.path.join(gtktoolkit.ScriptEngine.usecaseHome, "ui_map.conf"),
                      help="Update the UI map file(s) at FILE1,... If not set PyUseCase will read and write such a file at the its own default location ($USECASE_HOME/ui_map.conf). If multiple files are provided, the last in the list will be used for writing.", metavar="FILE1,...")
    parser.add_option("-r", "--record", help="Update the recorded script at FILE", metavar="FILE")
    
    options, args = parser.parse_args()
    if os.path.isfile(options.record):
        uiMapFiles = options.mapfiles.split(",")
        level = eval("logging." + options.loglevel.upper())
        logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s")
        chooser = UseCaseNameChooser(options.record, options.interface, uiMapFiles)
        chooser.collectNames()
