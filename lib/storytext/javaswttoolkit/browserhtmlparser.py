
import sys, os
from HTMLParser import HTMLParser, HTMLParseError
from storytext.gridformatter import GridFormatter
from storytext.guishared import getExceptionString

def get_attr_value(attrs, name):
    for attr, val in attrs:
        if attr == name:
            return val

class BrowserHtmlParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.currentTableParsers = []
        self.inBody = False
        self.inScript = False
        self.text = ""

    def parse(self, text):
        try:
            self.feed(text)
        except HTMLParseError:
            sys.stderr.write("Failed to parse browser text:\n")
            sys.stderr.write(getExceptionString())
            sys.stderr.write("Original text follows:\n")
            sys.stderr.write(text + "\n")
        return self.text

    def handle_starttag(self, rawname, attrs):
        name = rawname.lower()
        if name == "table":
            self.currentTableParsers.append(TableParser())
        elif name == "img":
            self.handle_data("Image '" + os.path.basename(get_attr_value(attrs, "src")) + "'")
        elif self.currentTableParsers:
            self.currentTableParsers[-1].startElement(name, attrs)
        elif name == "body":
            self.inBody = True
        elif name == "script":
            self.inScript = True

    def handle_endtag(self, rawname):
        name = rawname.lower()
        if name == "table":
            parser = self.currentTableParsers.pop()
            currText = parser.getText()
            if self.currentTableParsers:
                self.currentTableParsers[-1].addText(currText)
            else:
                self.text += currText
        elif self.currentTableParsers and name != "img":
            self.currentTableParsers[-1].endElement(name)

    def handle_data(self, content):
        if self.currentTableParsers:
            self.currentTableParsers[-1].characters(content)
        elif self.inBody and not self.inScript:
            self.text += content.rstrip()


class TableParser:
    def __init__(self):
        self.grid = []
        self.activeElements = {}
        
    def startElement(self, name, attrs):
        self.activeElements[name] = attrs
        if name == "tr":
            self.grid.append([])
        elif name == "td":
            self.grid[-1].append("")
            
    def endElement(self, name):
        if name == "td":
            colspan = get_attr_value(self.activeElements[name], "colspan")
            if colspan:
                for _ in range(int(colspan) - 1):
                    self.grid[-1].append("")
        del self.activeElements[name]
        
    def getText(self):
        if len(self.grid) == 0:
            return ""
        formatter = GridFormatter(self.grid, max((len(r) for r in self.grid)))
        return str(formatter)
    
    def characters(self, content):
        if "td" in self.activeElements:
            self.addText(content.rstrip("\t\n"))
            
    def addText(self, text):
        self.grid[-1][-1] += text
        
            
