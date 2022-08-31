import pyqtgraph as pg
from PyQt5.QtCore import pyqtSignal

class PlotWidgetwDblClick(pg.PlotWidget):
    doubleclicked = pyqtSignal()

    def __init__(self,*args, **kwargs):
        pg.PlotWidget.__init__(self,*args, **kwargs)
        
    def mouseDoubleClickEvent(self, evt):
        super().mouseDoubleClickEvent(evt)
        self.doubleclicked.emit()
