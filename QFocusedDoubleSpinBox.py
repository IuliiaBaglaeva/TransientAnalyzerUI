from PyQt5.QtWidgets import QDoubleSpinBox
from PyQt5.QtCore import pyqtSignal

class QFocusedDoubleSpinBox(QDoubleSpinBox):
    focused = pyqtSignal()

    def __init__(self,*args, **kwargs):
        QDoubleSpinBox.__init__(self,*args, **kwargs)

    def focusInEvent(self,evt):
        super().focusInEvent(evt)
        self.focused.emit()