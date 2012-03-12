import xml.sax, sys, os
from storytext.gridformatter import GridFormatter
from storytext.guishared import getExceptionString
class BrowserHtmlParser(xml.sax.ContentHandler):
    def __init__(self):
        xml.sax.ContentHandler.__init__(self)
        self.currentTableParsers = []
        self.inBody = False
        self.text = ""

    def parse(self, text):
        try:
            if os.pathsep == ";":
                text = self.fixWinText(text)
            xml.sax.parseString(text, self)
        except xml.sax.SAXException:
            sys.stderr.write("Failed to parse browser text:\n")
            sys.stderr.write(getExceptionString())
        return self.text

    def startElement(self, rawname, attrs):
        name = rawname.lower()
        if name == "table":
            self.currentTableParsers.append(TableParser())
        elif self.currentTableParsers:
            self.currentTableParsers[-1].startElement(name)
        elif name == "body":
            self.inBody = True

    def endElement(self, rawname):
        name = rawname.lower()
        if name == "table":
            parser = self.currentTableParsers.pop()
            currText = parser.getText()
            if self.currentTableParsers:
                self.currentTableParsers[-1].addText(currText)
            else:
                self.text += currText
        elif self.currentTableParsers:
            self.currentTableParsers[-1].endElement(name)

    def characters(self, content):
        if self.currentTableParsers:
            self.currentTableParsers[-1].characters(content)
        elif self.inBody:
            self.text += content.rstrip()

    def fixWinText(self, text):
        # Nested tbody tags doesn't seem to work on window.    
        text = text.replace("<tbody>", "")
        return text.replace("</tbody>", "")

class TableParser:
    def __init__(self):
        self.grid = []
        self.activeElements = set()
        
    def startElement(self, name):
        self.activeElements.add(name)
        if name == "tr":
            self.grid.append([])
        elif name == "td":
            self.grid[-1].append("")
            
    def endElement(self, name):
        self.activeElements.remove(name)
        
    def getText(self):
        formatter = GridFormatter(self.grid, max((len(r) for r in self.grid)), allowOverlap=False)
        return str(formatter)
    
    def characters(self, content):
        if "td" in self.activeElements:
            self.addText(content.rstrip())
            
    def addText(self, text):
        self.grid[-1][-1] += text
        
            
