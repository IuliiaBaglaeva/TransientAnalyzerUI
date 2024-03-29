# -*- coding: utf-8 -*-
#pyinstaller packages

from itertools import filterfalse
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
from copy import deepcopy

class WorkerSignals(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(int)

class Worker(QRunnable):

    def __init__(self, analyzer):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.computation_must_finish = False
        self.Analyzer = analyzer
        self.n_transients = self.Analyzer.t0s_est.shape[0]
        self.Signals = WorkerSignals()

    def run(self):
        return_code = 1
        for i in range(self.n_transients):
            if not self.computation_must_finish:
                self.Analyzer._FitSingleTransient(i)
                self.Signals.progress.emit(int((i + 1) * 100 / self.n_transients))
            else:
                return_code = -1
                break
        self.Signals.finished.emit(return_code)

    def ComputationMustFinish(self):
        self.computation_must_finish = True

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
    
def isfloat(num):
    try:
        float(num)
        return True
    except ValueError:
        return False

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
        self.ncol_data = None
        self.xlabel = 'time'
        self.ylabel = 'Signal'
        self.setEnd = False
        self.cur_x_mouse = None
        self.fname = None
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
        self.setMouseTracking(True)
        self.PlotWidget.scene().sigMouseMoved.connect(self.MouseMovedonPlot)
        #Buttons
        self.DetectButton.clicked.connect(self.DetectSignals)
        self.StartButton.clicked.connect(self.WorkWithTransients)
        #Menu bar
        self.actionExit.triggered.connect(self.closeEvent)
        self.actionOpen_File.triggered.connect(self.OpenFile)
        self.actionSave_Data.triggered.connect(self.SaveData)
        self.actionAdd_Stimulation_File.triggered.connect(self.SetStimulations)
        self.actionAbout.triggered.connect(self.ShowAboutWindow)
        self.AboutWindow = QMessageBox()
        self.AboutWindow.setWindowTitle("About")
        self.AboutWindow.setText("<b>TransientAnalyzer - Gaussian process regression-based analysis of noisy transient signals.</b>")
        self.AboutWindow.setInformativeText("Version 1.1.3 <br>"
                                "Created by Iuliia&nbsp;Baglaeva (<a href='"'mailto:iuliia.baglaeva@savba.sk'"'>iuliia.baglaeva@savba.sk</a>), Bogdan&nbsp;Iaparov, Ivan&nbsp;Zahradník and Alexandra&nbsp;Zahradníková. <br>"
                                "Biomedical Research Center of the Slovak Academy of Sciences. "
                                "© 2022-2023 <br>"
                                "This software is licensed under the GNU General Public License 3.0. <br>"
                                "List of used Python libraries:"
                                "<ul>"
                                "<li> PyQt5 </li>"
                                "<li> GPFlow </li>"
                                "<li> Pyqtgraph </li>"
                                "<li> NumPy </li>"
                                "<li> SciPy </li>"
                                "<li> Pandas </li>"
                                "<li> Pybaselines </li>"
                                "</ul>")
        self.AboutWindow.setStyleSheet("QLabel{min-width: 900px; font-size: 24px;}")
        spinboxes = self.findChildren(QDoubleSpinBox)
        spinboxes.extend(self.findChildren(QSpinBox))
        for s in spinboxes:
            s.valueChanged.connect(self.FreezeButton)
        self.KernelcomboBox.currentTextChanged.connect(self.FreezeButton)
        self.StartTimeBox.focused.connect(self.SetTimeToChange)
        self.EndTimeBox.focused.connect(self.SetTimeToChange)
        self.computation_goes = False
        self.data_issaved = True

    def closeEvent(self,event):
        if not (not self.computation_goes and self.data_issaved):
            if self.computation_goes:
                extra_msg = "There is an ongoing computation.".replace(" ", "&nbsp;") + "<br>"
            else:
                extra_msg = "There are unsaved results.".replace(" ", "&nbsp;") + "<br>"
            exit_msg = "Are you sure you want to exit?"
            msg_box = QMessageBox()
            msg_box.setWindowTitle("Exit warning")
            msg_box.setText(f"{extra_msg}{exit_msg}")
            msg_box.setTextFormat(QtCore.Qt.RichText)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
            resp = msg_box.exec()
            if resp == QMessageBox.Yes:
                if self.computation_goes:
                    self.worker.ComputationMustFinish()
                    event.ignore()
                else:
                    self.close()
            else:
                event.ignore()
        else:
            self.close()

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
                    data = np.loadtxt(filename,ndmin = 2)
                elif ext == ".csv":
                    data = pd.read_csv(filename)
                    data = data.to_numpy()
                else:
                    data = pd.read_excel(filename,engine="openpyxl")
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

    def CheckLabels(self,data):
        if not isfloat(data.columns[0].replace(',', '.')):
            self.xlabel = data.columns[0]
        else:
            self.xlabel = "Time"
        if not isfloat(data.columns[1].replace(',', '.')):
            self.ylabel = data.columns[1]
        else:
            self.ylabel = "Signal"

    def ResetParameters(self):
        self.DetrendBox.setChecked(False)
        self.WindowBox.setValue(20)
        self.Window2Box.setValue(0)
        self.Q1Box.setValue(10)
        self.Q2Box.setValue(20)
        self.ShiftBox.setValue(0)
        self.BetaBox.setValue(0.25)
        self.ProminenceBox.setValue(1.0)

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
                    self.CheckLabels(data)
                    self.SetPlotLabels()
                    data = data.to_numpy()
                else:
                    data = pd.read_excel(filename,engine="openpyxl")
                    self.CheckLabels(data)
                    self.SetPlotLabels()
                    data = data.to_numpy()
                if data.shape[1] != 2:
                    error_dialog = QErrorMessage()
                    error_dialog.showMessage("The file must contain only two columns")
                    error_dialog.exec_()
                    self.Log.setText("File opening failed.")
                    return
                self.Time = data[:,0]
                self.GradientBox.setValue(2*np.min(np.diff(self.Time)))
                self.Sig = data[:,1]
                self.DetectButton.setEnabled(True)
                self.StartButton.setEnabled(False)
                self.StartTimeBox.setMaximum(self.Time[-1])
                self.StartTimeBox.setValue(0)
                self.EndTimeBox.setMaximum(self.Time[-1])
                self.EndTimeBox.setValue(self.Time[-1])
                self.plot(self.Time, self.Sig)
                self.stimulus = None
                _, self.fname = os.path.split(name)
                self.Log.setText(f"{name}. Data loaded succesfully.")
                self.setWindowTitle(f"TransientAnalyzer ({name})")
                self.progressBar.setValue(0)
                self.HideTable()
                self.ResetParameters()
                self.data_issaved = False

    def HideTable(self):
        if self.ncol_data is None:
            return
        for i in range(self.ncol_data):
            self.ParsTable.hideColumn(i)

    def ShowTable(self):
        if self.ncol_data is None:
            return
        for i in range(self.ncol_data):
            self.ParsTable.showColumn(i)

    def plot(self, t, ca,change_range = True):
        self.PlotWidget.clear()
        pen = pg.mkPen(color = (105,105,105), width = 2)
        self.PlotWidget.plot(t, ca, pen=pen)
        if change_range:
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
            cond = (self.Time >= mint) & (self.Time <= maxt)
            t = self.Time[cond]
            sig = self.Sig[cond]
            stim = None
            if self.stimulus is not None:
                stim = self.stimulus[(self.stimulus >= mint) & (self.stimulus <= maxt)]
            if self.SignComboBox.currentText() == "Automatic":
                isFall = None
            elif self.SignComboBox.currentText() == "Positive":
                isFall = False
            else:
                isFall = True
            self.Analyzer = TransientAnalyzer.TransientAnalyzer(t,sig,
                                              window_size = self.WindowBox.value(),
                                              prominence = self.ProminenceBox.value(),
                                              window_size2 = self.Window2Box.value(),
                                              detrend = self.DetrendBox.isChecked(),
                                              shift = self.ShiftBox.value(),
                                              alpha_mult = self.AlphaBox.value(),
                                              beta = self.BetaBox.value(),
                                              start_gradient = self.GradientBox.value(),
                                              quantile1 = self.Q1Box.value() * 0.01,
                                              quantile2 = self.Q2Box.value() * 0.01,
                                              t_stim = stim,
                                              kernel=self.KernelcomboBox.currentText(),
                                              is_fall = isFall
                                              )
            if self.DetrendBox.isChecked():
                sig = deepcopy(self.Sig)
                sig[cond] = self.Analyzer.Sig
                self.plot(self.Time, sig,False)
            else:
                self.plot(self.Time,self.Sig,False)
            self.DrawLines(self.Analyzer.t0s_est)
            self.StartButton.setEnabled(True)
            self.HideTable()
            self.Log.setText(f"Detection of transients is completed. A total of {len(self.Analyzer.t0s_est)} transients.")

    def ShowProgress(self,value):
        self.progressBar.setValue(value)

    def ComputationisFinished(self,return_code):
        if return_code == -1:
            qApp.quit()
            return
        df = self.Analyzer.GetParametersTable(self.xlabel,self.ylabel)
        parameters = pandasModel(df)
        self.ncol_data = parameters.columnCount()
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
        self.ShowTable()
        self.Log.setText("Parameters estimation is completed.")

    def _GetAnalyzerParameters(self, SNR):
        data_out = {'Parameter': ["Boxcar 1","Boxcar 2","Prominence","Shift","Alpha multiplier","Beta","Start Gradient","Q1", "Q2","Kernel", "SNR"],
                'Value': [self.Analyzer._window_size, self.Analyzer._window_size2, self.Analyzer._prominence,self.Analyzer._shift, self.Analyzer._alpha_mult,
                          self.Analyzer._beta, self.Analyzer._start_gradient, self.Analyzer.quantile1,self.Analyzer.quantile2,self.Analyzer._kernel.__class__.__name__, SNR]}
        return pd.DataFrame.from_dict(data_out)

    def _GetSNR(self, pars, tr):     
        sigma = np.std(tr[:,1] - tr[:,2]) # True signal - GPR approximation
        A = np.mean(pars[:,1]) # Amplitude transients
        return np.abs(A / (3 * sigma))

    def SaveData(self):
        if not self.computation_goes:
            save_filename, save_filename_ext = QFileDialog.getSaveFileName(self,"Save File",f"{self.path}/{self.fname}_analysis","Excel file (*.xlsx);;Comma separated values (*.csv)")
            if save_filename != "":
                if save_filename_ext == "Comma separated values (*.csv)":
                    save_filename, save_filename_ext = os.path.splitext(save_filename)
                    df_par = self.Analyzer.GetParametersTable(self.xlabel,self.ylabel)
                    df_par.to_csv(save_filename + "_parameters.csv")
                    df_tr = self.Analyzer.GetTransientsTable(self.xlabel,self.ylabel)
                    df_tr.to_csv(save_filename + "_transients.csv")
                    df = self._GetAnalyzerParameters(self._GetSNR(df_par.to_numpy(), df_tr.to_numpy()))
                    df.to_csv(save_filename + "_analysis_parameters.csv")
                else:
                    try:
                        writer = pd.ExcelWriter(save_filename, engine='xlsxwriter')
                        df_par = self.Analyzer.GetParametersTable(self.xlabel,self.ylabel)
                        df_par.to_excel(writer,sheet_name="Parameters")
                        df_tr = self.Analyzer.GetTransientsTable(self.xlabel,self.ylabel)
                        df_tr.to_excel(writer,sheet_name="Transients")
                        df = self._GetAnalyzerParameters(self._GetSNR(df_par.to_numpy(), df_tr.to_numpy()))
                        df.to_excel(writer,sheet_name="Analysis Parameters")
                        writer.close()
                        self.data_issaved = True
                        msg_box = QMessageBox()
                        msg_box.setWindowTitle("Success")
                        msg_box.setText(f"Results were successfully saved")
                        msg_box.setTextFormat(QtCore.Qt.RichText)
                        msg_box.setIcon(QMessageBox.Information)
                        resp = msg_box.exec()
                    except Exception as e:
                        error_dialog = QErrorMessage()
                        error_dialog.showMessage(str(e))
                        error_dialog.exec_()


    def WorkWithTransients(self):
        if not self.computation_goes:
            self.progressBar.setValue(0)
            self.Log.setText("Parameters estimation is in progress.")
            self.worker = Worker(self.Analyzer)  # Any other args, kwargs are passed to the run function
            self.worker.Signals.progress.connect(self.ShowProgress)
            self.worker.Signals.finished.connect(self.ComputationisFinished)
            self.threadpool.start(self.worker)
            self.computation_goes = True
            self._ClearApproximatedTransients()

def main():
    app = QtWidgets.QApplication(sys.argv)
    application = ApplicationWindow()
    application.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()