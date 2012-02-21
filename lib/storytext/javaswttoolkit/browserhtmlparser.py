import xml.sax
from storytext.gridformatter import GridFormatter

class BrowserHtmlParser(xml.sax.ContentHandler):
    def __init__(self):
        xml.sax.ContentHandler.__init__(self)
        self.currentTableParsers = []
        self.inBody = False
        self.text = ""
        
    def parse(self, text):
        xml.sax.parseString(text, self)
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
        
            
