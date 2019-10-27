from PyQt5.QtWidgets import (QApplication,
                             QWidget,
                             QGridLayout,
                             QHBoxLayout,
                             QVBoxLayout,
                             QPushButton,
                             QLabel,
                             QLineEdit,
                             QCheckBox,
                             QFileDialog,
                             QMessageBox,
                             QComboBox,
                             QInputDialog,
                             QTabWidget)
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from SerialPortReader import *
from SerialPortWriter import *
from ConsoleWidget import ConsoleWidget
from SettingsWidget import SettingsWidget
from OutLog import OutLog

import sys
import numpy as np
import pyqtgraph as pg

from BreathingRateCounter import breath_rate_counter
from COMReader import serial_ports
from datetime import datetime


class RascanWorker(QObject):
    dataProcessed = pyqtSignal(float, float,
                               np.ndarray, np.ndarray, np.ndarray, np.ndarray,
                               np.ndarray, np.ndarray, np.ndarray, np.ndarray)

    def __init__(self, parent=None):
        super(self.__class__, self).__init__(parent)

    @QtCore.pyqtSlot(list, list, int, tuple)
    def doWork(self, a_ch0, a_ch1, t_interval, settings):

        a_ch0 = np.array(a_ch0) / 8000
        a_ch1 = np.array(a_ch1) / 8000
        lhf, hhf, lbf, hbf = settings

        try:
            hr, br, sig_hf1, sig_hf2, peaks_hf1, peaks_hf2, \
            sig_bf1, sig_bf2, peaks_bf1, peaks_bf2 = \
                breath_rate_counter(a_ch0, a_ch1, t_interval, lhf, hhf, lbf, hbf)
        except:
            hr, br, sig_hf1, sig_hf2, peaks_hf1, peaks_hf2, \
            sig_bf1, sig_bf2, peaks_bf1, peaks_bf2 = \
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0

        sig_hf1 = sig_hf1[::5]
        sig_hf2 = sig_hf2[::5]
        sig_bf1 = sig_bf1[::5]
        sig_bf2 = sig_bf2[::5]
        peaks_hf1 = peaks_hf1 / 5
        peaks_hf2 = peaks_hf2 / 5
        peaks_bf1 = peaks_bf1 / 5
        peaks_bf2 = peaks_bf2 / 5

        self.dataProcessed.emit(hr, br, sig_hf1, sig_hf2, peaks_hf1, peaks_hf2,
                                sig_bf1, sig_bf2, peaks_bf1, peaks_bf2)


class MyAxis(pg.AxisItem):
    def __init__(self, delta, orientation):
        super().__init__(orientation)
        self.delta = delta

    def setDelta(self, delta):
        self.delta = delta

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            vs = v * scale * self.delta / 1000
            str_val = str(round(vs, 1))
            strings.append(str_val)
        return strings


class PlotWidget(pg.GraphicsWindow):
    def __init__(self, maxX, deltaX, plotCount):
        super(self.__class__, self).__init__(None)

        self.initPlots(deltaX, plotCount)
        self.dataSize = maxX

        font = QFont('righteous')
        self.plot.getAxis("bottom").tickFont = font
        self.plot.getAxis("bottom").setStyle(tickTextOffset=30)
        self.plot.getAxis("left").tickFont = font
        self.plot.getAxis("left").setStyle(tickTextOffset=30)

    def setDelta(self, delta):
        self.my_axis.setDelta(delta)

    def initPlots(self, deltaX, plotCount):
        self.my_axis = MyAxis(deltaX, orientation='bottom')
        self.plot = self.addPlot(axisItems={'bottom': self.my_axis})

        self.pens = []
        self.pens.append(pg.mkPen(QColor('#5961FF'), width=2))
        self.pens.append(pg.mkPen(QColor('#FF1776'), width=2))

        self.plotCount = plotCount
        self.curves = []
        self.datas = []
        self.ptrs = []
        self.hides = []

        for i in range(plotCount):
            self.curves.append([pg.PlotCurveItem(pen=self.pens[i]),
                                pg.ScatterPlotItem(pen=self.pens[i])])
            self.plot.addItem(self.curves[i][0])
            self.plot.addItem(self.curves[i][1])
            self.datas.append([[], []])
            self.ptrs.append(0)
            self.hides.append(False)

    def hideCurve(self, curveNumber, hide):
        if hide:
            self.hides[curveNumber] = True
            self.curves[curveNumber][0].setData([0])
            self.curves[curveNumber][0].setData([])
        else:
            self.hides[curveNumber] = False
            self.curves[curveNumber][0].setData(self.datas[curveNumber][0])
            self.curves[curveNumber][0].setPos(self.ptrs[curveNumber], 0)

    def appendPoint(self, curveNumber, value):
        if len(self.datas[curveNumber][0]) < self.dataSize:
            self.datas[curveNumber][0].append(value)
        else:
            self.datas[curveNumber][0][:-1] = self.datas[curveNumber][0][1:]
            self.datas[curveNumber][0][-1] = value
            self.ptrs[curveNumber] += 1
        if not self.hides[curveNumber]:
            self.curves[curveNumber][0].setData(self.datas[curveNumber][0])
        self.curves[curveNumber][0].setPos(self.ptrs[curveNumber], 0)

    def appendData(self, curveNumber, data, peaks=None):
        if peaks is None:
            peaks = []
        delta = self.dataSize - (len(data) + len(self.datas[curveNumber][0]))

        if delta < 0:
            self.datas[curveNumber][0][:delta] = self.datas[curveNumber][0][-delta:]
            self.datas[curveNumber][0][delta:] = data
            self.ptrs[curveNumber] += -delta
        else:
            self.datas[curveNumber][0] += data
        if not self.hides[curveNumber]:
            self.curves[curveNumber][0].setData(self.datas[curveNumber][0])
        self.curves[curveNumber][0].setPos(self.ptrs[curveNumber], 0)
        self.appendPeaks(curveNumber, data, peaks)

    def appendPeaks(self, curveNumber, data, peaks):
        self.datas[curveNumber][1][:] = \
            [x for x in self.datas[curveNumber][1]
             if x['pos'][0] >= self.ptrs[curveNumber]]
        dataBegin = len(self.datas[curveNumber][0]) - len(data) + self.ptrs[curveNumber]

        for index, item in enumerate(peaks):
            roundedItem = int(item + 0.5)
            roundedItem = min(roundedItem, len(data) - 1)
            self.datas[curveNumber][1].append({'pos': (dataBegin + roundedItem, data[roundedItem])})
        self.curves[curveNumber][1].setData(self.datas[curveNumber][1])

    def resetOne(self, curveNumber):
        self.datas[curveNumber][0] = [0]
        self.ptrs[curveNumber] = 0
        self.curves[curveNumber][0].setData(self.datas[curveNumber][0])
        self.curves[curveNumber][0].setPos(self.ptrs[curveNumber], 0)
        self.datas[curveNumber][0] = []
        self.ptrs[curveNumber] = 0
        self.curves[curveNumber][0].setData(self.datas[curveNumber][0])
        self.curves[curveNumber][0].setPos(self.ptrs[curveNumber], 0)
        self.datas[curveNumber][1] = []
        self.curves[curveNumber][1].clear()

    def reset(self):
        for i in range(self.plotCount):
            self.resetOne(i)


class ExperimentData():
    def __init__(self, parent):
        self.parent = parent
        self.reset()

    def appendData(self, a_ch0, a_ch1, T_meas):
        self.a_ch0 += a_ch0
        self.a_ch1 += a_ch1
        self.T_meas += T_meas
        self.needToSave = True

    def appendDataToTxt(self, a_ch0, a_ch1, T_meas, fileName):
        with open(str(fileName + '.txt'), 'a') as file:
            for i in range(0, len(a_ch0)):
                file.write(str(a_ch0[i]) + ' ' + str(a_ch1[i])
                           + ' ' + str(T_meas[i]) + '\n')
        self.needToSave = False

    def reset(self):
        self.a_ch0 = []
        self.a_ch1 = []
        self.T_meas = []
        self.needToSave = False

    def saveIfNeeded(self):
        if self.needToSave:
            answer = QMessageBox.question(self.parent, "Message",
                                          "Unsaved data exist, do you want to save?",
                                          QMessageBox.Yes, QMessageBox.No)
            if answer == QMessageBox.Yes:
                self.saveToFile()

    def saveToFile(self):
        if len(self.T_meas) != 0:
            fileName = QFileDialog.getSaveFileName(None,
                                                   "Save unsaved data to file",
                                                   QDir(".").canonicalPath(),
                                                   "NPZ(*.npz)")
            np.savez_compressed(fileName[0], ch0=self.a_ch0, ch1=self.a_ch1,
                                T=self.T_meas)
            self.needToSave = False


class MyIntValidator(QIntValidator):
    def __init__(self, min, max):
        super(self.__class__, self).__init__(min, max)
        self.min = min

    def fixup(self, s):
        print("Input data is out of range")
        return str(self.min)


class MainWindow(QWidget):
    processData = pyqtSignal(list, list, int, tuple)

    def __init__(self):
        super(self.__class__, self).__init__(None)

        self.reader = SerialPortReader()
        self.experimentData = ExperimentData(self)
        self.initGUI()

        sys.stdout = OutLog(self.console, sys.stdout)
        sys.stderr = OutLog(self.console, sys.stderr, QColor(255, 0, 0))

        self.createWorkerThread()
        self.reader.timeUpdate.connect(self.onTimeUpdate)
        self.reader.dataReady.connect(self.onDataReady)
        self.reader.locatorPacket.connect(self.onLocatorPacket)
        self.loadSettings()

    @QtCore.pyqtSlot(list, list, list)
    def onDataReady(self, a_ch0, a_ch1, T_meas):
        if self.experimentLength < 5:
            self.experimentData.appendData(a_ch0, a_ch1, T_meas)
        else:
            self.experimentData.appendDataToTxt(a_ch0, a_ch1,
                                                T_meas, self.txtFileName)
        self.processData.emit(a_ch0, a_ch1,
                              self.intervalLength,
                              self.settingsWidget.getValues())

    @QtCore.pyqtSlot(float, float)
    def onLocatorPacket(self, val1, val2):
        self.locatorPlotWidget.appendPoint(0, val1)
        self.locatorPlotWidget.appendPoint(1, val2)

    @QtCore.pyqtSlot(int)
    def onTimeUpdate(self, time):
        time = self.experimentLength * 60 * 1000 - time
        qtTime = QTime.fromMSecsSinceStartOfDay(time)
        self.timeLabel.setText(qtTime.toString())

        if time == 0:
            self.startStopButton.toggle()

    def createWorkerThread(self):
        self.rascanWorker = RascanWorker()
        self.workerThread = QThread()
        self.rascanWorker.moveToThread(self.workerThread)
        self.workerThread.start()

        self.processData.connect(self.rascanWorker.doWork)
        self.rascanWorker.dataProcessed.connect(self.onRascanDataProcessed)

    def initGUI(self):
        self.setWindowTitle('Rythm')
        self.setWindowIcon(QIcon('icon.png'))
        self.settingsWidget = SettingsWidget(self)
        mainLayout = QGridLayout()
        self.setLayout(mainLayout)

        leftLayout = QVBoxLayout()
        leftLayout.setSpacing(20)
        mainLayout.addLayout(leftLayout, 1, 1, Qt.AlignCenter)

        tabWidget = QTabWidget()
        mainLayout.addWidget(tabWidget, 1, 3, Qt.AlignCenter)

        mainLayout.setRowStretch(0, 2)  # empty space above ui
        mainLayout.setRowStretch(1, 1)  # ui
        mainLayout.setRowStretch(2, 2)  # console
        mainLayout.setRowStretch(3, 2)  # empty space below ui
        mainLayout.setColumnStretch(0, 2)  # empty space to the right from ui
        mainLayout.setColumnStretch(2, 1)  # empty space between left layout and right layout
        mainLayout.setColumnStretch(4, 2)  # empty space to the left from ui

        # console output
        self.console = ConsoleWidget(self)
        self.console.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.console.setReadOnly(True)
        mainLayout.addWidget(self.console, 2, 1, 1, 3)

        # settings layout
        settingsLayout = QGridLayout()
        leftLayout.addLayout(settingsLayout)

        lengthSettingsText = QLabel('Recording duration')
        self.lengthSettingsEdit = QLineEdit('10')
        self.lengthSettingsEdit.setValidator(MyIntValidator(1, 30))
        lmin = QLabel('min')
        lmin.setObjectName("secondary")

        settingsLayout.addWidget(lengthSettingsText, 0, 0)
        settingsLayout.addWidget(self.lengthSettingsEdit, 0, 2)
        settingsLayout.addWidget(lmin, 0, 3)
        settingsLayout.setColumnMinimumWidth(1, 30)

        intervalLayoutText = QLabel('Calculation interval')
        self.intervalLayoutEdit = QLineEdit('60')
        self.intervalLayoutEdit.setValidator(MyIntValidator(10, 300))
        imin = QLabel('sec')
        imin.setObjectName("secondary")
        settingsLayout.addWidget(intervalLayoutText, 1, 0)
        settingsLayout.addWidget(self.intervalLayoutEdit, 1, 2)
        settingsLayout.addWidget(imin, 1, 3)

        self.comBox = QComboBox(self)
        COMLayoutText = QLabel('Choose COM-port')
        COM_list = serial_ports()
        self.comBox.addItems(COM_list)
        settingsLayout.addWidget(COMLayoutText, 2, 0)
        settingsLayout.addWidget(self.comBox, 2, 2)

        # back to main layout
        settingsLayout.setRowMinimumHeight(3, 20)  # add some space vertically

        self.saveCheckBox = QCheckBox('Save remainder')
        settingsLayout.addWidget(self.saveCheckBox, 5, 0)

        self.timeLabel = QLabel('00:00:00')
        self.timeLabel.setObjectName('timeLabel')
        leftLayout.addWidget(self.timeLabel)
        leftLayout.setAlignment(self.timeLabel, Qt.AlignHCenter)

        infoLayout = QHBoxLayout()
        infoLayout.setSpacing(20)
        leftLayout.addLayout(infoLayout)
        infoLayout.addStretch()

        chss = QLabel('HBR')
        chss.setObjectName('leftBar')
        infoLayout.addWidget(chss)

        self.heartRateText = QLabel('0')
        self.heartRateText.setObjectName('primary')
        self.heartRateText.setAlignment(Qt.AlignRight)
        infoLayout.addWidget(self.heartRateText)

        udm = QLabel('HB/min')
        udm.setObjectName('secondary')
        infoLayout.addWidget(udm)
        infoLayout.addSpacing(40)

        chd = QLabel('Breathing\nrate')
        chd.setObjectName('leftBar')
        infoLayout.addWidget(chd)

        self.breathRateText = QLabel('0')
        self.breathRateText.setObjectName('primary')
        self.breathRateText.setAlignment(Qt.AlignRight)
        infoLayout.addWidget(self.breathRateText)

        vdm = QLabel('breath/min')
        vdm.setObjectName('secondary')
        infoLayout.addWidget(vdm)
        infoLayout.addStretch()

        buttonLayout = QHBoxLayout()
        leftLayout.addLayout(buttonLayout)
        self.startStopButton = QPushButton('Start')
        self.startStopButton.setCheckable(True)
        saveButton = QPushButton('Save')
        saveButton.clicked.connect(self.onSaveButtonClicked)
        buttonLayout.addWidget(self.startStopButton)
        buttonLayout.addSpacing(20)
        buttonLayout.addWidget(saveButton)
        self.startStopButton.toggled.connect(self.onButtonClick)

        # first tab
        tabOneWidget = QWidget()
        tabOneLayout = QVBoxLayout()
        tabOneLayout.setContentsMargins(0, 0, 0, 0)
        tabOneWidget.setLayout(tabOneLayout)
        tabWidget.addTab(tabOneWidget, "HBR/BR")

        self.heartRatePlotWidget = PlotWidget(30, 10000, 1)
        self.breathRatePlotWidget = PlotWidget(30, 10000, 1)
        tabOneLayout.addWidget(self.heartRatePlotWidget)
        tabOneLayout.addWidget(self.breathRatePlotWidget)

        # second tab
        tabTwoWidget = QWidget()
        tabTwoLayout = QVBoxLayout()
        tabTwoWidget.setLayout(tabTwoLayout)
        tabWidget.addTab(tabTwoWidget, "Locator signal")

        self.locatorPlotWidget = PlotWidget(300, 20, 2)
        tabTwoLayout.addWidget(self.locatorPlotWidget)

        tabOneButtonsLayout = QGridLayout()
        tabTwoLayout.addLayout(tabOneButtonsLayout)
        locatorLeftCheckBox = QCheckBox('Signal')
        tabOneButtonsLayout.addWidget(locatorLeftCheckBox, 0, 3)
        locatorRightCheckBox = QCheckBox('Signal + pi / 2')
        tabOneButtonsLayout.addWidget(locatorRightCheckBox, 1, 3)
        locatorLeftCheckBox.setChecked(True)
        locatorRightCheckBox.setChecked(True)
        locatorLeftCheckBox.stateChanged. \
            connect(lambda state:
                    self.locatorPlotWidget.
                    hideCurve(0, False if state == 1 or state == 2 else True))
        locatorRightCheckBox.stateChanged. \
            connect(lambda state:
                    self.locatorPlotWidget.
                    hideCurve(1, False if state == 1 or state == 2 else True))

        # third tab
        tabThreeWidget = QWidget()
        tabThreeLayout = QVBoxLayout()
        tabThreeWidget.setLayout(tabThreeLayout)
        tabWidget.addTab(tabThreeWidget, "Filtered data")

        self.heartFilteredPlotWidget = PlotWidget(300, 100, 2)
        self.breathFilteredPlotWidget = PlotWidget(300, 100, 2)
        tabThreeLayout.addWidget(self.heartFilteredPlotWidget)
        tabThreeLayout.addWidget(self.breathFilteredPlotWidget)

    @QtCore.pyqtSlot(bool)
    def onButtonClick(self, toggled):
        if toggled:
            portName = self.comBox.currentText()
            if portName == '':
                print("Device is not connected")
                self.startStopButton.blockSignals(True)
                self.startStopButton.setChecked(False)
                self.startStopButton.blockSignals(False)
                return
            if self.saveCheckBox.isChecked():
                self.experimentData.saveIfNeeded()
            self.experimentData.reset()
            self.startStopButton.setText('Stop')
            self.intervalLength = int(self.intervalLayoutEdit.text())
            self.experimentLength = int(self.lengthSettingsEdit.text())
            if self.experimentLength < self.intervalLength / 60:
                print("Error: calculation interval  more than experiment duration")
                self.startStopButton.setChecked(False)
                self.startStopButton.setText('Start')
                return
            if self.experimentLength >= 5:
                self.txtFileName = str(datetime.today()).split('.')[0].replace(' ', '-').replace(':', '-')[:-3]

            print("Be patient, the program is running...")
            self.reader.startListen(self.intervalLength, portName)
            self.heartRatePlotWidget.reset()
            self.breathRatePlotWidget.reset()
            self.breathFilteredPlotWidget.reset()
            self.heartFilteredPlotWidget.reset()
            self.locatorPlotWidget.reset()
            self.heartRatePlotWidget.setDelta(self.intervalLength * 1000)
            self.breathRatePlotWidget.setDelta(self.intervalLength * 1000)
            self.heartRatePlotWidget.appendPoint(0, 0)
            self.breathRatePlotWidget.appendPoint(0, 0)
        else:
            self.startStopButton.setText('Start')
            self.reader.stopListen()

    @QtCore.pyqtSlot()
    def onSaveButtonClicked(self):
        self.experimentData.saveToFile()

    @QtCore.pyqtSlot(float, float, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray,
                     np.ndarray)
    def onRascanDataProcessed(self, chss, chd, sig_hf1, sig_hf2, peaks_hf1, peaks_hf2, sig_bf1, sig_bf2, peaks_bf1,
                              peaks_bf2):
        self.heartRateText.setText(str(int(chss)))
        self.breathRateText.setText(str(int(chd)))
        self.heartRatePlotWidget.appendPoint(0, chss)
        self.breathRatePlotWidget.appendPoint(0, chd)
        self.heartFilteredPlotWidget.appendData(0, sig_hf1.tolist(), peaks_hf1.tolist())
        self.heartFilteredPlotWidget.appendData(1, sig_hf2.tolist(), peaks_hf2.tolist())
        self.breathFilteredPlotWidget.appendData(0, sig_bf1.tolist(), peaks_bf1.tolist())
        self.breathFilteredPlotWidget.appendData(1, sig_bf2.tolist(), peaks_bf2.tolist())

    def closeEvent(self, event):
        if self.saveCheckBox.isChecked():
            self.experimentData.saveIfNeeded()
        self.saveSettings()
        event.accept()

    def saveSettings(self):
        settings = QSettings("rythm_settings.ini", QSettings.IniFormat)

        if not self.isMaximized():
            settings.setValue("geometry", self.geometry())

        settings.setValue("maximized", self.isMaximized())
        settings.setValue("length", self.lengthSettingsEdit.text())
        settings.setValue("interval", self.intervalLayoutEdit.text())
        settings.setValue("save", self.saveCheckBox.isChecked())
        settings.setValue("port", self.comBox.currentText())

        lhf, hhf, lbf, hbf = self.settingsWidget.getValues()
        settings.setValue("lhf", lhf)
        settings.setValue("hhf", hhf)
        settings.setValue("lbf", lbf)
        settings.setValue("hbf", hbf)

    def loadSettings(self):
        settings = QSettings("rythm_settings.ini",
                             QSettings.IniFormat)

        screenRect = QApplication.desktop().screenGeometry()
        defaultWindowRect = \
            QRect(screenRect.width() / 8,
                  screenRect.height() * 1.5 / 8,
                  screenRect.width() * 6 / 8,
                  screenRect.height() * 5 / 8)

        self.setGeometry(settings.value("geometry", defaultWindowRect))
        if settings.value("maximized", False) == "true":
            self.setWindowState(self.windowState() ^ Qt.WindowMaximized)

        self.lengthSettingsEdit.setText(settings.value("length", "1"))
        self.intervalLayoutEdit.setText(settings.value("interval", "10"))

        if settings.value("save", True) == "true":
            self.saveCheckBox.setChecked(True)

        portName = settings.value("port", "")
        itemIndex = self.comBox.findText(portName)
        if itemIndex != -1:
            self.comBox.setCurrentIndex(itemIndex)

        lhf = settings.value("lhf", 0.7)
        hhf = settings.value("hhf", 2.5)
        lbf = settings.value("lbf", 0.01)
        hbf = settings.value("hbf", 0.4)

        self.settingsWidget.setValues(float(lhf), float(hhf), float(lbf), float(hbf))


app = QApplication([])

font_db = QFontDatabase()
font_db.addApplicationFont("/.fonts/righteous.ttf")

font = QFont('righteous')
font.setPixelSize(20)
app.setFont(font)

# apply Qt stylesheet
stylesheet = open("stylesheet.qss").read()
app.setStyleSheet(stylesheet)

pg.setConfigOption('background', 'w')
pg.setConfigOptions(antialias=True)

mainWindow = MainWindow()
mainWindow.show()

app.exec_()
