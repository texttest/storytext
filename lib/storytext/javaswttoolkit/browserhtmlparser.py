
import sys, os
from HTMLParser import HTMLParser, HTMLParseError
from storytext.gridformatter import GridFormatter, GridFormatterWithHeader
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
        except:
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
        elif name == "br":
            self.text += "\n"

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
            
    def handle_entityref(self, name):
        if self.currentTableParsers:
            self.currentTableParsers[-1].entityRef(name)
        elif name == "nbsp":
            self.text += " "


class TableParser:
    def __init__(self):
        self.headerRow = []
        self.currentRow = None
        self.currentRowIsHeader = True
        self.grid = []
        self.activeElements = {}

    def isCell(self, name):
        return name in ["td", "th"]

    def startElement(self, name, attrs):
        self.activeElements[name] = attrs
        if name == "tr":
            self.currentRow = []
        elif self.isCell(name):
            self.currentRow.append("")
            if name == "td":
                self.currentRowIsHeader = False

    def getRow(self, name):
        if name == "td":
            return self.grid[-1]
        elif name == "th":
            return self.headerRow
        
    def getActiveRow(self):
        if "td" in self.activeElements:
            return self.grid[-1]
        elif "th" in self.activeElements:
            return self.headerRow
            
    def endElement(self, name):
        if name in self.activeElements:  # Don't fail on duplicated end tags
            if self.currentRow is not None and self.isCell(name):
                colspan = get_attr_value(self.activeElements[name], "colspan")
                if colspan:
                    for _ in range(int(colspan) - 1):
                        self.currentRow.append("")
            del self.activeElements[name]
            if name == "tr":
                if self.currentRowIsHeader:
                    self.headerRow = self.currentRow
                else:
                    self.grid.append(self.currentRow)
                self.currentRow = None
        
    def getText(self):
        if len(self.grid) == 0:
            return ""
        
        columnCount = max((len(r) for r in self.grid))
        if self.headerRow:
            formatter = GridFormatterWithHeader([ self.headerRow ], self.grid, columnCount)
        else:
            formatter = GridFormatter(self.grid, columnCount)
        return str(formatter)
    
    def characters(self, content):
        if content.strip():
            self.addText(content.rstrip("\t\r\n"))
            
    def addText(self, text):
        if self.currentRow is not None:
            self.currentRow[-1] += text
            
    def entityRef(self, name):
        if name == "nbsp":
            self.addText(" ")
              
