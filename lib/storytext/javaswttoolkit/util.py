
""" SWT utilities """
import storytext.guishared

from java.lang import NoSuchMethodException, NoSuchFieldException
from java.text import SimpleDateFormat

from org.eclipse.swt import SWT
from org.eclipse.swt.custom import CLabel, StackLayout
from org.eclipse.swt.layout import GridLayout
from org.eclipse.swt.widgets import Label, Table, Tree

cellParentData = { Table : ("TableCell", "Table"), 
                   Tree  : ("TreeCell", "Tree") }
ignoreLabels = []

def getContextNameForWidget(widget):
    for className, data in cellParentData.items():
        if isinstance(widget, className):
            return data[0]
    return ""

def getRealUrl(browser):
    url = browser.getUrl()
    return url if url != "about:blank" else ""

class TextLabelFinder(storytext.guishared.TextLabelFinder):
    def getLabelClass(self):
        return Label, CLabel
    
    def getContextParentClasses(self):
        # Don't look for labels outside these if they are parent classes
        return tuple(cellParentData.keys())
    
    def getOutputClassName(self, widget):
        for cls, data in cellParentData.items():
            if isinstance(widget, cls):
                return data[1]
    
    def getChildren(self, widget):
        return widget.getChildren() if hasattr(widget, "getChildren") else []
    
    def getEarliestRelevantIndex(self, widgetPos, children, parent):
        layout = parent.getLayout()
        if isinstance(layout, StackLayout):
            return widgetPos # No text is relevant: stack layout will hide it
        
        if not isinstance(layout, GridLayout):
            return 0
        
        numColumns = layout.numColumns
        if numColumns == 1: # If there's only one column, don't worry about it...
            return 0
        
        currIndex = 0
        rows = {}
        for ix, child in enumerate(children):
            span = min(child.getLayoutData().horizontalSpan, numColumns)
            row = currIndex / numColumns
            rows.setdefault(row, []).append(ix)
            if ix == widgetPos:
                return rows[row][0]
            else:
                currIndex += span

    def numRows(self, children, parent):
        layout = parent.getLayout()
        if not isinstance(layout, GridLayout):
            return 0
        numColumns = layout.numColumns
        currIndex = 0
        rows = -1
        for child in children:
            span = min(child.getLayoutData().horizontalSpan, numColumns)
            rows = int(currIndex / numColumns)
            currIndex += span
        return rows + 1

def getTextLabel(widget, **kw):
    return TextLabelFinder(widget, ignoreLabels).find(**kw)

def getInt(intOrMethod):
    return intOrMethod if isinstance(intOrMethod, int) else intOrMethod()

class CanvasDescriber(storytext.guishared.Describer):
    def __init__(self, canvas, *args, **kw):
        storytext.guishared.Describer.__init__(self, *args, **kw)
        self.canvas = canvas
        
    def describeCanvasStructure(self, indent):
        pass
    
    @classmethod
    def canDescribe(cls, widget):
        return False
    
    def getCanvasDescription(self, *args):
        pass
    
    def getUpdatePrefix(self, *args):
        return "\nUpdated "

def getDateFormat(dateType):
    if dateType == SWT.TIME:
        # Default format is locale-dependent, no reason to make tests fail in different locales
        return SimpleDateFormat("kk:mm:ss")
    else:
        # Seems to be default format for SWT.DATE, should be locale-independent
        return SimpleDateFormat("M/d/yyyy") 

# For some reason StackLayout does not affect visible properties, so things that are hidden get marked as visible
# Workaround these things
def getTopControl(widget):
    if hasattr(widget, "getLayout"):
        layout = widget.getLayout()
        if hasattr(layout, "topControl"):
            return layout.topControl

def isVisible(widget):
    if not hasattr(widget, "getVisible"):
        return True
    
    if not widget.getVisible():
        return False

    parent = widget.getParent()
    if not parent:
        return True
    
    topControl = getTopControl(parent)
    if topControl and topControl is not widget:
        return False
    else:
        return isVisible(parent) and not (hasattr(parent, "isExpanded") and not parent.isExpanded())
    
def getRootMenu(menuItem):
    menu = menuItem.getParent()
    while menu.getParentMenu() is not None:
        menu = menu.getParentMenu()
    return menu

def getItemText(text):
    return text.replace("&", "").split("\t")[0]

def getPrivateField(obj, fieldName):
    cls = obj.getClass()
    while cls is not None:
        try:
            declaredField = cls.getDeclaredField(fieldName)
            declaredField.setAccessible(True)
            return declaredField.get(obj)
        except NoSuchFieldException:
            cls = cls.getSuperclass()
            
def callPrivateMethod(obj, methodName, argList=[], argTypeList=[]):
    cls = obj.getClass()
    argTypeList = argTypeList if argTypeList or not argList else [ arg.getClass() for arg in argList ] 
    while True:
        try:
            declaredMethod = cls.getDeclaredMethod(methodName, argTypeList)
            declaredMethod.setAccessible(True)
            return declaredMethod.invoke(obj, argList)
        except NoSuchMethodException:
            cls = cls.getSuperclass()
            if cls is None:
                raise
            
def getEnclosingInstance(listener):
    cls = listener.getClass()
    for field in cls.getDeclaredFields():
        if field.getName().startswith("this"):
            field.setAccessible(True)
            return field.get(listener)
            
def hasPrivateMethod(obj, methodName, includeBases):
    cls = obj.getClass()
    while cls is not None:
        if any((method.getName() == methodName for method in cls.getDeclaredMethods())):
            return True
        elif not includeBases:
            return False
        cls = cls.getSuperclass()
        
def getJfaceTooltip(item):
    for listener in item.getListeners(SWT.MouseHover):
        tooltip = getEnclosingInstance(listener)
        if tooltip and hasPrivateMethod(tooltip, "createToolTipContentArea", includeBases=True):
            return tooltip


                        
