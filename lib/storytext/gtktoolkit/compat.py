# Just use gtk2 for now
tryGtk3 = False

if tryGtk3:
    try:
        from gi import pygtkcompat
        useGtk3 = True
    except ImportError:
        useGtk3 = False
else:
    useGtk3 = False

if useGtk3:
    pygtkcompat.enable()
    pygtkcompat.enable_gtk(version='3.0')
    import gi
    from gi.repository import Gdk, Gtk, GdkPixbuf
    Gtk.image_new_from_animation = Gtk.Image.new_from_animation
    Gdk.PixbufAnimation = GdkPixbuf.PixbufAnimation
    Gtk.TreeViewColumn.get_cell_renderers = Gtk.TreeViewColumn.get_cells
    Gtk.Window.focus_widget = Gtk.Window.get_focus
    Gtk.TreeView.emit_stop_by_name = Gtk.TreeView.stop_emission_by_name

import gtk

def createEvent(type):
    if useGtk3:
        event = Gdk.Event()
        event.type = getattr(Gdk.EventType, type)
        return event
    else:
        return gtk.gdk.Event(getattr(gtk.gdk, type))

def getFocusWidget(window):
    if useGtk3:
        return window.get_focus()
    else:
        return window.focus_widget
    
def getDefaultWidget(window):
    if useGtk3:
        return window.get_default_widget()
    else:
        return window.default_widget

def set_can_default(widget, default=True):
    if useGtk3:
        widget.set_can_default(default)
    else:
        widget.set_flags(gtk.CAN_DEFAULT)

def createTreeRowReference(model, path):
    if useGtk3:
        return Gtk.TreeRowReference.new(model, path)
    else:
        return gtk.TreeRowReference(model, path)

def createFrame(label):
    if useGtk3:
        return Gtk.Frame.new(label)
    else:
        return gtk.Frame(label)

def createComboBox(model=None):
    if useGtk3:
        if model:
            combo = Gtk.ComboBoxText.new()
            combo.set_model(model)
            return combo
        else:
            return Gtk.ComboBoxText.new()
    else:
        if model:
            return gtk.ComboBox(model)

def popup(menu, event):
    if useGtk3:
        # The fourth parameter here, data,  is the last one in gtk 2
        menu.popup(None, None, None, None, event.button, event.time)
    else:
        menu.popup(None, None, None, event.button, event.time, data=None)

def getAction(widget):
    if useGtk3:
        # Getting action from widget doesn't exist in gtk3. Have to investigate if there is an equivalent
        return None
    else:
        return widget.get_action()

def windowMaximizedInitially(window):
    if useGtk3:
        # Could'n find gtk3 equivalent
        return False
    else:
        return window.maximize_initially
    
def setDialogSeparator(dialog, value):
    if not useGtk3:
        # It has been deprecated in gtk 2.22 and should not be used. There is not gtk3 equivalent
        dialog.set_has_separator(value)