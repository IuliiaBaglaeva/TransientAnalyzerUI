# -*- coding: utf-8 -*-
#pyinstaller packages

import tensorflow_probability.python.experimental
import keras
from PlotWidgetwDblClick import PlotWidgetwDblClick
from QFocusedDoubleSpinBox import QFocusedDoubleSpinBox

from PyQt5 import QtWidgets, uic, QtCore
from PyQt5.QtCore import QRunnable, pyqtSignal, QThreadPool, QAbstractTableModel, QObject
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import qApp, QFileDialog, QErrorMessage, QDoubleSpinBox, QSpinBox, QMessageBox
import sys
import os
import numpy as np
from TransientAnalyzer import TransientAnalyzer
import pyqtgraph as pg
import pandas as pd


class WorkerSignals(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal()

class Worker(QRunnable):

    def __init__(self, analyzer):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.Analyzer = analyzer
        self.n_transients = self.Analyzer.t0s_est.shape[0]
        self.Signals = WorkerSignals()

    def run(self):
        for i in range(self.n_transients):
            self.Analyzer._FitSingleTransient(i)
            self.Signals.progress.emit((i + 1) * 100 / self.n_transients)
        self.Signals.finished.emit()

class pandasModel(QAbstractTableModel):

    def __init__(self, data):
        QAbstractTableModel.__init__(self)
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1] + 1

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if index.isValid():
            if role == QtCore.Qt.DisplayRole:
                if index.column() == 0:
                    return str(index.row() + 1)
                else:
                    return f"{self._data.iloc[index.row(), index.column() - 1]:.3f}"
        return None

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            if col == 0:
                return "Index"
            else:
                return self._data.columns[col - 1]
        return None
    
class ApplicationWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(ApplicationWindow, self).__init__()
        uic.loadUi('TransientAnalyzer.ui', self)
        self.path = ""
        self.name = None
        self.Time = None #array of time signal
        self.Sig = None #array of calcium signal
        self.Analyzer = None
        self.threadpool = QThreadPool()
        self.added_transients = []
        self.stimulus = None
        self.xlabel = 'time'
        self.ylabel = 'Signal'
        self.setEnd = False
        self.cur_x_mouse = None
        self.PlotWidget.doubleclicked.connect(self.SetTime)
        #parameters of plot
        self.PlotWidget.setBackground('w')
        font = QFont("Calibri",12)
        self.PlotWidget.getAxis('left').setTickFont(font)
        self.PlotWidget.getAxis('left').setTextPen("black")
        self.PlotWidget.getAxis('bottom').setTickFont(font)
        self.PlotWidget.getAxis('bottom').setTextPen("black")
        self.PlotWidget.getAxis('bottom').setPen(color ='black', width = 2)
        self.PlotWidget.getAxis('left').setPen(color ='black', width = 2)
        self.SetPlotLabels()
        #Buttons
        self.DetectButton.clicked.connect(self.DetectSignals)
        self.StartButton.clicked.connect(self.WorkWithTransients)
        #Menu bar
        self.actionExit.triggered.connect(qApp.quit)
        self.actionOpen_File.triggered.connect(self.OpenFile)
        self.actionSave_Data.triggered.connect(self.SaveData)
        self.actionAdd_Stimulation_File.triggered.connect(self.SetStimulations)
        self.actionAbout.triggered.connect(self.ShowAboutWindow)
        self.AboutWindow = QMessageBox()
        self.AboutWindow.setWindowTitle("About")
        self.AboutWindow.setText("<b>TransientAnalyzer - Gaussian process regression-based analysis of noisy transient signals.</b>")
        self.AboutWindow.setInformativeText("Version 0.2. <br>"
                                "Created by Iuliia Baglaeva (<a href='"'mailto:iuliia.baglaeva@savba.sk'"'>iuliia.baglaeva@savba.sk</a>), Bogdan Iaparov, Ivan Zahradník and Alexandra Zahradníková. <br>"
                                "Biomedical Research Center of the Slovak Academy of Sciences. "
                                "© 2022 <br>"
                                "This software is licensed under the GNU General Public License 3.0. <br>"
                                "List of used Python libraries:"
                                "<ul>"
                                "<li> PyQt5 </li>"
                                "<li> GPFlow </li>"
                                "<li> Pyqtgraph </li>"
                                "<li> NumPy </li>"
                                "<li> SciPy </li>"
                                "<li> Pandas </li>"
                                "</ul>")
        self.AboutWindow.setStyleSheet("QLabel{min-width: 1000px; font-size: 24px;}")
        spinboxes = self.findChildren(QDoubleSpinBox)
        spinboxes.extend(self.findChildren(QSpinBox))
        for s in spinboxes:
            s.valueChanged.connect(self.FreezeButton)
        self.StartTimeBox.focused.connect(self.SetTimeToChange)
        self.EndTimeBox.focused.connect(self.SetTimeToChange)
        self.computation_goes = False

    def ShowAboutWindow(self):
        self.AboutWindow.exec()

    def FreezeButton(self):
        self.StartButton.setEnabled(False)

    def SetPlotLabels(self):
        self.labelStyle = {'font-size': "14pt", "color": "black", 'font-family': "Calibri","font-weight": "bold"}
        self.PlotWidget.getAxis('left').setLabel(text = self.ylabel, **self.labelStyle)
        self.PlotWidget.getAxis('bottom').setLabel(text = self.xlabel, **self.labelStyle)

    def SetTime(self):
        if self.setEnd:
            self.EndTimeBox.setValue(self.cur_x_mouse)
        else:
            self.StartTimeBox.setValue(self.cur_x_mouse)

    def SetTimeToChange(self):
        if self.sender().objectName() == "StartTimeBox":
            self.setEnd = False
        else:
            self.setEnd = True

    def MouseMovedonPlot(self, evt):
        if self.PlotWidget.plotItem.vb.mapSceneToView(evt):
            point = self.PlotWidget.plotItem.vb.mapSceneToView(evt)
            self.CoordinatesLabel.setText(f"x: {point.x():.3f}, y: {point.y():.3f}")
            self.cur_x_mouse = point.x()

    def SetStimulations(self):
        if not self.computation_goes:
            filename = QFileDialog.getOpenFileName(self,"Open Stimulations File",self.path,"Data files (*.txt *.csv *.xlsx)") [0]
            if filename != "":
                self.path, name = os.path.split(os.path.abspath(filename))
                name, ext = os.path.splitext(filename)
                if ext == ".txt":
                    data = np.loadtxt(filename)
                elif ext == ".csv":
                    data = pd.read_csv(filename)
                    data = data.to_numpy()
                else:
                    data = pd.read_excel(filename)
                    data = data.to_numpy()
                if data.shape[1] > 2:
                    error_dialog = QErrorMessage()
                    error_dialog.showMessage("The file must contain one or two columns.")
                    error_dialog.exec_()
                    self.Log.setText("Stimulation setup failed.")
                    return
                if data.shape[1] == 2:
                    self.stimulus = data[data[:,1] > 0, 0]
                else:
                    self.stimulus = data[:,0]
                self.Log.setText(f"Stimulation setup successful.")

    def OpenFile(self):
        if not self.computation_goes:
            filename = QFileDialog.getOpenFileName(self,"Open File",self.path,"Data files (*.txt *.csv *.xlsx)") [0]
            if filename != "":
                self.path, name = os.path.split(os.path.abspath(filename))
                name, ext = os.path.splitext(filename)
                self.name = name
                if ext == ".txt":
                    data = np.loadtxt(filename)
                elif ext == ".csv":
                    data = pd.read_csv(filename)
                    self.xlabel = data.columns[0]
                    self.ylabel = data.columns[1]
                    self.SetPlotLabels()
                    data = data.to_numpy()
                else:
                    data = pd.read_excel(filename)
                    self.xlabel = data.columns[0]
                    self.ylabel = data.columns[1]
                    self.SetPlotLabels()
                    data = data.to_numpy()
                if data.shape[1] != 2:
                    error_dialog = QErrorMessage()
                    error_dialog.showMessage("The file must contain only two columns")
                    error_dialog.exec_()
                    self.Log.setText("File opening failed.")
                    return
                self.Time = data[:,0]
                self.Sig = data[:,1]
                self.DetectButton.setEnabled(True)
                self.StartButton.setEnabled(False)
                self.StartTimeBox.setMaximum(self.Time[-1])
                self.EndTimeBox.setMaximum(self.Time[-1])
                self.EndTimeBox.setValue(self.Time[-1])
                self.plot(self.Time, self.Sig)
                self.stimulus = None
                self.Log.setText(f"{name}. Data loaded succesfully.")
                self.setWindowTitle(f"TransientAnalyzer ({name})")
                self.progressBar.setValue(0)

    def plot(self, t, ca):
        self.PlotWidget.clear()
        pen = pg.mkPen(color = (105,105,105), width = 2)
        self.PlotWidget.plot(t, ca, pen=pen)
        self.setMouseTracking(True)
        self.PlotWidget.scene().sigMouseMoved.connect(self.MouseMovedonPlot)
        self.PlotWidget.autoRange()

    def _ClearApproximatedTransients(self):
        for l in self.added_transients:
            self.PlotWidget.removeItem(l)

    def DrawLines(self, points):
        list_children = self.PlotWidget.allChildItems()
        for l in list_children:
            if isinstance(l,pg.InfiniteLine):
                self.PlotWidget.removeItem(l)
        pen = pg.mkPen(style=QtCore.Qt.DotLine, color = 'black', width = 2)
        for p in points:
            self.PlotWidget.addItem(pg.InfiniteLine(pos=p, angle=90, pen=pen))

    def DetectSignals(self):
        if not self.computation_goes:
            mint = self.StartTimeBox.value()
            maxt = self.EndTimeBox.value()
            cond = (self.Time > mint) & (self.Time <= maxt)
            t = self.Time[cond]
            sig = self.Sig[cond]
            self.Analyzer = TransientAnalyzer.TransientAnalyzer(t,sig,
                                              window_size = self.WindowBox.value(),
                                              prominence = self.ProminenceBox.value(),
                                              quantile1 = self.Q1Box.value(),
                                              quantile2 = self.Q2Box.value(),
                                              t_stim = self.stimulus
                                              )
            self.DrawLines(self.Analyzer.t0s_est)
            self.StartButton.setEnabled(True)
            self.Log.setText(f"Detection of transients is completed. A total of {len(self.Analyzer.t0s_est)} transients.")

    def ShowProgress(self,value):
        self.progressBar.setValue(value)

    def ComputationisFinished(self):
        df = self.Analyzer.GetParametersTable(self.xlabel,self.ylabel)
        parameters = pandasModel(df)
        self.ParsTable.setModel(parameters)
        self.ParsTable.setMinimumWidth(300)
        self._ClearApproximatedTransients()
        pen = pg.mkPen(color=(255,0,0), width = 4)
        for i in range(len(self.Analyzer.t0s)):
            T, CA = self.Analyzer.GetApproxTransient(i,self.Analyzer.dt * 0.3)
            l = self.PlotWidget.plot(T, CA, pen=pen)
            self.added_transients.append(l)
        self.DrawLines(self.Analyzer.t0s)
        self.computation_goes = False
        self.Log.setText("Parameters estimation is completed.")

    def SaveData(self):
        if not self.computation_goes:
            save_filename = QFileDialog.getSaveFileName(self,"Save File",self.path,"Excel file (*.xlsx)") [0]
            if save_filename != "":
                writer = pd.ExcelWriter(save_filename, engine='xlsxwriter')
                df = self.Analyzer.GetParametersTable(self.xlabel,self.ylabel)
                df.to_excel(writer,sheet_name="Parameters")
                df = self.Analyzer.GetTransientsTable(self.xlabel,self.ylabel)
                df.to_excel(writer,sheet_name="Transients")
                try:
                    writer.save()
                except Exception as e:
                    error_dialog = QErrorMessage()
                    error_dialog.showMessage(str(e))
                    error_dialog.exec_()


    def WorkWithTransients(self):
        self.progressBar.setValue(0)
        self.Log.setText("Parameters estimation is in progress.")
        worker = Worker(self.Analyzer)  # Any other args, kwargs are passed to the run function
        worker.Signals.progress.connect(self.ShowProgress)
        worker.Signals.finished.connect(self.ComputationisFinished)
        self.threadpool.start(worker)
        self.computation_goes = True
        self._ClearApproximatedTransients()

def main():
    app = QtWidgets.QApplication(sys.argv)
    application = ApplicationWindow()
    application.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()