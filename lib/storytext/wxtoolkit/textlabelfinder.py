import wx

import storytext.guishared


class TextLabelFinder(storytext.guishared.TextLabelFinder):
    def find(self):
        sizer = self.findSizer(self.widget)
        return self.findInSizer(sizer) if sizer is not None else ""

    def findInSizer(self, sizer):
        sizers, widgets = self.findSizerChildren(sizer)
        if self.widget in widgets:
            return self.findPrecedingLabel(widgets)
        for subsizer in sizers:
            label = self.findInSizer(subsizer)
            if label is not None:
                return label
            
    def getLabelClass(self):
        return wx.StaticText
    
    def getLabelText(self, label):
        return label.GetLabel()

    def findSizerChildren(self, sizer):
        sizers, widgets = [], []
        for item in sizer.GetChildren():
            if item.GetWindow():
                widgets.append(item.GetWindow())
            if item.GetSizer():
                sizers.append(item.GetSizer())
        return sizers, widgets
        
    def findSizer(self, widget):
        if widget.GetSizer():
            return widget.GetSizer()
        if widget.GetParent():
            return self.findSizer(widget.GetParent())
