
"""
Module for handling image logging
"""

import gtk

class ImageDescriber:
    def __init__(self):
        self.numberForNew = 1
        self.pixbufs = {}

    def getDescription(self, image):
        try:
            stock, size = image.get_stock()
            if stock:
                return self.getStockDescription(stock)

            if image.get_storage_type() == gtk.IMAGE_EMPTY:
                return ""
        except ValueError:
            pass
        return "Non-stock image"

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
            number = self.getPixbufNumber(pixbuf)
            return "Number " + str(number)

    def getPixbufNumber(self, pixbuf):
        storedNum = self.pixbufs.get(pixbuf)
        if storedNum:
            return storedNum

        self.pixbufs[pixbuf] = self.numberForNew
        self.numberForNew += 1
        return self.pixbufs.get(pixbuf)

    
