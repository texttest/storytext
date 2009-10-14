
"""
Module for handling image logging
"""

import gtk, os

orig_pixbuf_new_from_file = gtk.gdk.pixbuf_new_from_file
orig_pixbuf_new_from_xpm_data = gtk.gdk.pixbuf_new_from_xpm_data

def pixbuf_new_from_file(filename):
    pixbuf = orig_pixbuf_new_from_file(filename)
    ImageDescriber.pixbufs[pixbuf] = os.path.basename(filename)
    return pixbuf

def pixbuf_new_from_xpm_data(data):
    pixbuf = orig_pixbuf_new_from_xpm_data(data)
    ImageDescriber.add_xpm(pixbuf, data)
    return pixbuf

def performInterceptions():
    gtk.gdk.pixbuf_new_from_file = pixbuf_new_from_file
    gtk.gdk.pixbuf_new_from_xpm_data = pixbuf_new_from_xpm_data

class ImageDescriber:
    xpmNumber = 1
    pixbufs = {}

    @classmethod
    def add_xpm(cls, pixbuf, data):
        cls.pixbufs[pixbuf] = "XPM " + str(cls.xpmNumber)
        cls.xpmNumber += 1

    def getDescription(self, image):
        try:
            stock, size = image.get_stock()
            if stock:
                return self.getStockDescription(stock)

            if image.get_storage_type() == gtk.IMAGE_EMPTY:
                return ""
        except ValueError:
            pass

        pixbuf = image.get_property("pixbuf")
        return self.getPixbufDescription(pixbuf)

    def getStockDescription(self, stock):
        return "Stock image '" + stock + "'"

    def getInbuiltImageDescription(self, widget):
        if hasattr(widget, "get_stock_id"):
            stockId = widget.get_stock_id()
            if stockId:
                return self.getStockDescription(stockId)
        if hasattr(widget, "get_image"):
            try:
                image = widget.get_image()
                if image and image.get_property("visible"):
                    return self.getDescription(image)
            except ValueError:
                return ""
        return ""

    def getPixbufDescription(self, pixbuf):
        if pixbuf:
            name = self.getPixbufName(pixbuf)
            return "Image '" + name + "'"
        else:
            return ""

    def getPixbufName(self, pixbuf):
        fromData = pixbuf.get_data("name")
        if fromData:
            return fromData
        else:
            return self.pixbufs.get(pixbuf, "Unknown")
    
