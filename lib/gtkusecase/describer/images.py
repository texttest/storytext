
"""
Module for handling image logging
"""

import gtk, os

orig_pixbuf_new_from_file = gtk.gdk.pixbuf_new_from_file
orig_pixbuf_new_from_xpm_data = gtk.gdk.pixbuf_new_from_xpm_data
origImage = gtk.Image
origAnimation = gtk.gdk.PixbufAnimation

def pixbuf_new_from_file(filename):
    pixbuf = orig_pixbuf_new_from_file(filename)
    ImageDescriber.pixbufs[pixbuf] = os.path.basename(filename)
    return pixbuf

def pixbuf_new_from_xpm_data(data):
    pixbuf = orig_pixbuf_new_from_xpm_data(data)
    ImageDescriber.add_xpm(pixbuf, data)
    return pixbuf

class Image(origImage):
    def set_from_file(self, filename):
        origImage.set_from_file(self, filename)
        pixbuf = self.get_property("pixbuf")
        ImageDescriber.pixbufs[pixbuf] = os.path.basename(filename)

class PixbufAnimation(origAnimation):
    def __init__(self, filename):
        origAnimation.__init__(self, filename)
        ImageDescriber.pixbufs[self] = os.path.basename(filename)

def performImageInterceptions():
    gtk.gdk.pixbuf_new_from_file = pixbuf_new_from_file
    gtk.gdk.pixbuf_new_from_xpm_data = pixbuf_new_from_xpm_data
    gtk.Image = Image
    gtk.gdk.PixbufAnimation = PixbufAnimation

class ImageDescriber:
    xpmNumber = 1
    pixbufs = {}

    @classmethod
    def add_xpm(cls, pixbuf, data):
        cls.pixbufs[pixbuf] = "XPM " + str(cls.xpmNumber)
        cls.xpmNumber += 1

    def getDescription(self, image):
        try:
            if hasattr(image, "get_stock"):
                stock, size = image.get_stock()
                if stock:
                    return self.getStockDescription(stock)
            else:
                return "" # it's not really an image type, it's just been put there...

            if image.get_storage_type() == gtk.IMAGE_EMPTY:
                return ""
        except ValueError:
            pass

        pixbuf = image.get_property("pixbuf")
        if pixbuf:
            return self.getPixbufDescription(pixbuf)

        animation = image.get_property("pixbuf-animation")
        return self.getPixbufDescription(animation, "Animation")
        
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
                if not image and isinstance(widget.get_child(), gtk.Image):
                    image = widget.get_child()
                if image and image.get_property("visible"):
                    return self.getDescription(image)
            except ValueError:
                return ""
        if hasattr(widget, "get_icon_widget"):
            image = widget.get_icon_widget()
            if image:
                return self.getDescription(image)
        return ""

    def getPixbufDescription(self, pixbuf, header="Image"):
        if pixbuf:
            return header + " '" + self.getPixbufName(pixbuf) + "'"
        else:
            return ""
        
    def getPixbufName(self, pixbuf):
        fromData = pixbuf.get_data("name")
        if fromData:
            return fromData
        else:
            return self.pixbufs.get(pixbuf, "Unknown")
    
