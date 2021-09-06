#!/usr/bin/env python3
# =============================================================================
#     Code: mainprogram.py
#     Author: Casey R. Densmore, 25JUN2019
#     
#     Purpose: Creates QMainWindow class with basic functions for a GUI with
#        	multiple tabs. Requires PyQt5 module (pip instal PyQt5) 
#
#   General functions within main.py "RunProgram" class of QMainWindow:
#       o __init__: Calls functions to initialize GUI
#       o initUI: Builds GUI window
#		o makenewtab: Creates a new tab window (make all widgets/buttons here)
#       o whatTab: gets identifier for open tab
#       o renametab: renames open tab
#       o setnewtabcolor: sets the background color pattern for new tabs
#       o closecurrenttab: closes open tab
#       o savedataincurtab: saves data in open tab (saved file types depend on tab type and user preferences)
#       o postwarning: posts a warning box specified message
#       o posterror: posts an error box with a specified message
#       o postwarning_option: posts a warning box with Okay/Cancel options
#       o closeEvent: pre-existing function that closes the GUI- function modified to prompt user with an "are you sure" box
#
# =============================================================================


# =============================================================================
#   CALL NECESSARY MODULES HERE
# =============================================================================
from sys import argv, exit
from platform import system as cursys
from struct import calcsize
from os import remove, path, listdir
import shutil
from traceback import print_exc as trace_error
from datetime import datetime

if cursys() == 'Windows':
    from ctypes import windll

from shutil import copy as shcopy
from tempfile import gettempdir

from PyQt5.QtWidgets import (QMainWindow, QAction, QApplication, QMenu, QLineEdit, QLabel, QSpinBox, QCheckBox,
    QPushButton, QMessageBox, QWidget, QFileDialog, QComboBox, QTextEdit, QTabWidget, QVBoxLayout, QInputDialog, 
    QGridLayout, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QDesktopWidget, 
    QStyle, QStyleOptionTitleBar, QSlider)
from PyQt5.QtCore import QObjectCleanupHandler, Qt, pyqtSlot, pyqtSignal, QObject
from PyQt5.QtGui import QIcon, QColor, QPalette, QBrush, QLinearGradient, QFont
from PyQt5.Qt import QThreadPool

from scipy.io import wavfile as sciwavfile
import wave

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.colors import ListedColormap, Normalize
from matplotlib import cm

import AudioProcessor as AP





#   DEFINE CLASS FOR PROGRAM (TO BE CALLED IN MAIN)
class RunProgram(QMainWindow):
    
    
# =============================================================================
#   INITIALIZE WINDOW, INTERFACE
# =============================================================================
    def __init__(self):
        super().__init__()
        
        try:
            self.initUI() #creates GUI window
            self.buildmenu() #Creates interactive menu, options to create tabs and start autoQC
            self.makenewtab() #Opens first tab

        except Exception:
            trace_error()
            self.posterror("Failed to initialize the program.")
        
    def initUI(self):

        #setting window size
        cursize = QDesktopWidget().availableGeometry(self).size()
        titleBarHeight = self.style().pixelMetric(QStyle.PM_TitleBarHeight, QStyleOptionTitleBar(), self)
        self.resize(cursize.width(), cursize.height()-titleBarHeight)

        # setting title/icon, background color
        self.setWindowTitle('PyRealtimeSpectrogram')
        #self.setWindowIcon(QIcon('pathway_to_icon_here.png')) #TODO: Create/include icon
        p = self.palette()
        p.setColor(self.backgroundRole(), QColor(255,255,255)) #white background
        self.setPalette(p)

        #sets app ID to ensure that any additional windows appear under the same tab
        if cursys() == 'Windows':
            myappid = 'PyRealtimeSpectrogram'  # arbitrary string
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        #changing font size
        font = QFont()
        font.setPointSize(11)
        font.setFamily("Arial")
        self.setFont(font)

        # prepping to include tabs
        mainWidget = QWidget()
        self.setCentralWidget(mainWidget)
        mainLayout = QVBoxLayout()
        mainWidget.setLayout(mainLayout)
        self.tabWidget = QTabWidget()
        mainLayout.addWidget(self.tabWidget)
        self.myBoxLayout = QVBoxLayout()
        self.tabWidget.setLayout(self.myBoxLayout)
        self.show()

        #setting slash dependent on OS- for file naming and handling
        if cursys() == 'Windows':
            self.slash = '\\'
        else:
            self.slash = '/'

        #setting up dictionary to store data for each tab
        self.alltabdata = []

        #tab tracking
        self.totaltabs = 0
        self.tabnumbers = []
        
        #getting temporary directory for files
        self.tempdir = gettempdir()
        self.cleantempfiles()
        
        #default directory
        defaultpath = path.expanduser("~")
        if path.exists(path.join(defaultpath,"Documents")): #default to Documents directory if it exists, otherwise home directory
            defaultpath = path.join(defaultpath,"Documents")
        self.defaultfiledir = defaultpath
        
        #setting up file dialog options
        self.fileoptions = QFileDialog.Options()
        self.fileoptions |= QFileDialog.DontUseNativeDialog
        
        #identifying connected devices
        self.audiosources,self.audiosourceIDs,self.PyAudioObject = AP.listaudiodevices()
        
        self.audioWindowOpened = False
        
        # creating threadpool
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(7)
        
        self.maxNfreqs = 200 #max number of frequency datapoints to plot
            
        
        
        
# =============================================================================
#    BUILD MENU, GENERAL SETTINGS
# =============================================================================

    #builds file menu for GUI
    def buildmenu(self):
        #setting up primary menu bar
        menubar = self.menuBar()
        FileMenu = menubar.addMenu('Options')
        
        #File>New Tab
        newptab = QAction('&New Tab',self)
        newptab.setShortcut('Ctrl+N')
        newptab.triggered.connect(self.makenewtab)
        FileMenu.addAction(newptab)
        
        #File>Rename Current Tab
        renametab = QAction('&Rename Current Tab',self)
        renametab.setShortcut('Ctrl+R')
        renametab.triggered.connect(self.renametab)
        FileMenu.addAction(renametab)
        
        #File>Close Current Tab
        closetab = QAction('&Close Current Tab',self)
        closetab.setShortcut('Ctrl+X')
        closetab.triggered.connect(self.closecurrenttab)
        FileMenu.addAction(closetab)
        
        


# =============================================================================
#     SIGNAL PROCESSOR TAB AND INPUTS HERE
# =============================================================================
    def makenewtab(self):     
        try:

            curtabnum = self.addnewtab()
    
            #creates dictionary entry for current tab- you can add additional key/value combinations for the opened tab at any point after the dictionary has been initialized
            initstats = {"updated":False,"fs":None,"freqs":[], "N":None, "df":None, "timerange":3, "fftlen":0.3, "crange":[5,11], "reprate":0.3, "alpha":0.25, "frange":[100,2500]}
            
            self.alltabdata.append({ "tab":QWidget(), "tablayout":QGridLayout(), "mainLayout":QGridLayout(), 
                    "tabtype":"newtab", "tabwidget":QTabWidget(), "mainsettingswidget":QWidget(), "plotsavewidget":QWidget(),  "signalmaskwidget":QWidget(), "stats":initstats, "isprocessing":False, "Processor":None, "datasource":None,     "data":{"ctime":0, "maxtime":0, "times":np.array([]), "freqs":np.array([]), "spectra":np.array([[]]), "isplotted":[]}   })

            self.setnewtabcolor(self.alltabdata[curtabnum]["tab"])
            
            self.alltabdata[curtabnum]["tablayout"].setSpacing(10)
    
            #creating new tab, assigning basic info
            self.tabWidget.addTab(self.alltabdata[curtabnum]["tab"],'New Tab') 
            self.tabWidget.setCurrentIndex(curtabnum)
            self.tabWidget.setTabText(curtabnum, "New Tab #" + str(self.totaltabs))
            _,self.alltabdata[curtabnum]["tabnum"] = self.whatTab() #assigning unique, unchanging number to current tab
            self.alltabdata[curtabnum]["tablayout"].setSpacing(10)
            self.alltabdata[curtabnum]["mainLayout"].setSpacing(10)
            
            #and add new buttons and other widgets
            self.alltabdata[curtabnum]["tabwidgets"] = {}
            
            #creating plot
            self.alltabdata[curtabnum]["SpectroFig"] = plt.figure()
            self.alltabdata[curtabnum]["SpectroCanvas"] = FigureCanvas(self.alltabdata[curtabnum]["SpectroFig"])
            self.alltabdata[curtabnum]["SpectroAxes"] = plt.axes()
            self.alltabdata[curtabnum]["SpectroAxes"].set_xlabel('Time (s)')
            ctime = self.alltabdata[curtabnum]["data"]["ctime"]
            timerange = self.alltabdata[curtabnum]["stats"]["timerange"]
            self.alltabdata[curtabnum]["SpectroAxes"].set_xlim(ctime-timerange,ctime)
            self.alltabdata[curtabnum]["SpectroAxes"].set_ylabel('Frequency (Hz)')
            self.alltabdata[curtabnum]["SpectroCanvas"].setStyleSheet("background-color:transparent;")
            self.alltabdata[curtabnum]["SpectroFig"].patch.set_facecolor("None")
            self.alltabdata[curtabnum]["colorbar"] = self.gencolorbar(curtabnum,initstats["crange"])
            

            #creating tab widget
            self.alltabdata[curtabnum]["tabwidget"].setLayout(self.alltabdata[curtabnum]["tablayout"])
            self.alltabdata[curtabnum]["tabwidget"].addTab(self.alltabdata[curtabnum]["mainsettingswidget"],"Spectrogram Settings")
            self.alltabdata[curtabnum]["tabwidget"].addTab(self.alltabdata[curtabnum]["plotsavewidget"],"Save Spectrogram/Audio")
            self.alltabdata[curtabnum]["mainsettingslayout"] = QGridLayout()
            self.alltabdata[curtabnum]["plotsavelayout"] = QGridLayout()
            self.alltabdata[curtabnum]["mainsettingswidget"].setLayout(self.alltabdata[curtabnum]["mainsettingslayout"])
            self.alltabdata[curtabnum]["plotsavewidget"].setLayout(self.alltabdata[curtabnum]["plotsavelayout"])
            self.alltabdata[curtabnum]["tabwidget"].setTabEnabled(1,False)
            
            #adding widgets to main layout
            self.alltabdata[curtabnum]["timelabel"] = QLabel("Center Time: 0/0 seconds")
            self.alltabdata[curtabnum]["timelabel"].setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["mainLayout"].addWidget(self.alltabdata[curtabnum]["SpectroCanvas"],1,0,1,3) # set dimensions
            self.alltabdata[curtabnum]["mainLayout"].addWidget(self.alltabdata[curtabnum]["tabwidget"],2,1,1,1)
            rowstretches = [1,30,9,1]
            for (r,s) in zip(range(len(rowstretches)),rowstretches):
                self.alltabdata[curtabnum]["mainLayout"].setRowStretch(r,s) #stretching out row with plot axes
                
            colstretches = [2,4,2]
            for (c,s) in zip(range(len(colstretches)),colstretches):
                self.alltabdata[curtabnum]["mainLayout"].setColumnStretch(c,s) #stretching out row with plot axes

            
            #making widgets for settings tab
            self.alltabdata[curtabnum]["tabwidgets"]["start"] = QPushButton('Start') 
            self.alltabdata[curtabnum]["tabwidgets"]["start"].clicked.connect(self.startprocessor)
            self.alltabdata[curtabnum]["tabwidgets"]["stop"] = QPushButton('Stop')
            self.alltabdata[curtabnum]["tabwidgets"]["stop"].clicked.connect(self.stopprocessor)
            self.alltabdata[curtabnum]["tabwidgets"]["sourcetitle"] = QLabel("Data Source: ")
            self.alltabdata[curtabnum]["tabwidgets"]["datasource"] = QComboBox() 
            for source in self.audiosources:
                self.alltabdata[curtabnum]["tabwidgets"]["datasource"].addItem(source)
            self.alltabdata[curtabnum]["tabwidgets"]["datasource"].addItem('WAV File')
                
            
            self.alltabdata[curtabnum]["tabwidgets"]["ctimetitle"] = QLabel("Spectrogram Time: ")
            self.alltabdata[curtabnum]["tabwidgets"]["ctimetitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["ctime"] = QDoubleSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["ctime"].setRange(0, 0)
            self.alltabdata[curtabnum]["tabwidgets"]["ctime"].setSingleStep(0.05)
            self.alltabdata[curtabnum]["tabwidgets"]["ctime"].setDecimals(2)
            self.alltabdata[curtabnum]["tabwidgets"]["ctime"].setValue(0)
            
            self.alltabdata[curtabnum]["tabwidgets"]["timerangetitle"] = QLabel("Time Range: ")
            self.alltabdata[curtabnum]["tabwidgets"]["timerangetitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["timerange"] = QDoubleSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["timerange"].setRange(0.25, 30)
            self.alltabdata[curtabnum]["tabwidgets"]["timerange"].setSingleStep(0.25)
            self.alltabdata[curtabnum]["tabwidgets"]["timerange"].setDecimals(2)
            self.alltabdata[curtabnum]["tabwidgets"]["timerange"].setValue(10)
            
            self.alltabdata[curtabnum]["tabwidgets"]["cmintitle"] = QLabel("Color Minimum: ")
            self.alltabdata[curtabnum]["tabwidgets"]["cmintitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["cmaxtitle"] = QLabel("Color Maximum: ")
            self.alltabdata[curtabnum]["tabwidgets"]["cmaxtitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["cmin"] = QDoubleSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["cmin"].setRange(0.0, 299.9)
            self.alltabdata[curtabnum]["tabwidgets"]["cmin"].setSingleStep(0.1)
            self.alltabdata[curtabnum]["tabwidgets"]["cmin"].setDecimals(1)
            self.alltabdata[curtabnum]["tabwidgets"]["cmin"].setValue(initstats["crange"][0])
            self.alltabdata[curtabnum]["tabwidgets"]["cmax"] = QDoubleSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["cmax"].setRange(0.1, 300)
            self.alltabdata[curtabnum]["tabwidgets"]["cmax"].setSingleStep(0.1)
            self.alltabdata[curtabnum]["tabwidgets"]["cmax"].setDecimals(1)
            self.alltabdata[curtabnum]["tabwidgets"]["cmax"].setValue(initstats["crange"][1])
            
            self.alltabdata[curtabnum]["tabwidgets"]["fftlentitle"] = QLabel("FFT Window Length (s): ")
            self.alltabdata[curtabnum]["tabwidgets"]["fftlentitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["fftlen"] = QDoubleSpinBox()
            self.alltabdata[curtabnum]["tabwidgets"]["fftlen"].setRange(0.05, 3)
            self.alltabdata[curtabnum]["tabwidgets"]["fftlen"].setSingleStep(0.05)
            self.alltabdata[curtabnum]["tabwidgets"]["fftlen"].setDecimals(2)
            self.alltabdata[curtabnum]["tabwidgets"]["fftlen"].setValue(0.3)
            
            self.alltabdata[curtabnum]["tabwidgets"]["repratetitle"] = QLabel("Repitition Rate (s): ")
            self.alltabdata[curtabnum]["tabwidgets"]["repratetitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["reprate"] = QDoubleSpinBox()
            self.alltabdata[curtabnum]["tabwidgets"]["reprate"].setRange(0.05, 1)
            self.alltabdata[curtabnum]["tabwidgets"]["reprate"].setSingleStep(0.05)
            self.alltabdata[curtabnum]["tabwidgets"]["reprate"].setDecimals(2)
            self.alltabdata[curtabnum]["tabwidgets"]["reprate"].setValue(0.1)
            
            self.alltabdata[curtabnum]["tabwidgets"]["alphatitle"] = QLabel("Taper Alpha Value: ")
            self.alltabdata[curtabnum]["tabwidgets"]["alphatitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["alpha"] = QDoubleSpinBox()
            self.alltabdata[curtabnum]["tabwidgets"]["alpha"].setRange(0, 1)
            self.alltabdata[curtabnum]["tabwidgets"]["alpha"].setSingleStep(0.01)
            self.alltabdata[curtabnum]["tabwidgets"]["alpha"].setDecimals(2)
            self.alltabdata[curtabnum]["tabwidgets"]["alpha"].setValue(0.25)
            
            
            self.alltabdata[curtabnum]["tabwidgets"]["fmintitle"] = QLabel("Frequency Min (Hz): ")
            self.alltabdata[curtabnum]["tabwidgets"]["fmintitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["fmaxtitle"] = QLabel("Frequency Max (Hz): ")
            self.alltabdata[curtabnum]["tabwidgets"]["fmaxtitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["fmin"] = QSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["fmin"].setRange(0, 49999)
            self.alltabdata[curtabnum]["tabwidgets"]["fmin"].setSingleStep(1)
            self.alltabdata[curtabnum]["tabwidgets"]["fmin"].setValue(initstats["frange"][0])
            self.alltabdata[curtabnum]["tabwidgets"]["fmax"] = QSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["fmax"].setRange(0, 50000)
            self.alltabdata[curtabnum]["tabwidgets"]["fmax"].setSingleStep(1)
            self.alltabdata[curtabnum]["tabwidgets"]["fmax"].setValue(initstats["frange"][1])
            
            
            self.alltabdata[curtabnum]["tabwidgets"]["updatesettings"] = QPushButton('Update Settings')
            self.alltabdata[curtabnum]["tabwidgets"]["updatesettings"].clicked.connect(self.updatecurtabsettings)
            
            ctext = self.getspecs()
            self.alltabdata[curtabnum]["tabwidgets"]["specs"] = QLabel(ctext)
            
            
            #should be 19 entries 
            widgetorder = ["start", "stop", "sourcetitle", "datasource", "ctimetitle", "ctime", "timerangetitle", "timerange", "cmintitle", "cmin", "cmaxtitle", "cmax", "fftlentitle", "fftlen", "repratetitle", "reprate", "alphatitle", "alpha", "updatesettings", "specs", "fmintitle", "fmin", "fmaxtitle", "fmax"]
            wrows     = [1,1,2,3, 5,5, 1,1, 2,2,3,3, 4,4,5,5,6,6,1,2, 5,5,6,6]
            wcols     = [1,2,1,1, 1,2, 3,4, 3,4,3,4, 3,4,3,4,3,4,5,5, 5,6,5,6]
            wrext     = [1,1,1,1, 1,1, 1,1, 1,1,1,1, 1,1,1,1,1,1,1,3, 1,1,1,1]
            wcolext   = [1,1,2,2, 1,1, 1,1, 1,1,1,1, 1,1,1,1,1,1,2,2, 1,1,1,1]
    
            #adding user inputs
            for i,r,c,re,ce in zip(widgetorder,wrows,wcols,wrext,wcolext):
                self.alltabdata[curtabnum]["mainsettingslayout"].addWidget(self.alltabdata[curtabnum]["tabwidgets"][i],r,c,re,ce)
    
            #adjusting stretch factors for all rows/columns
            colstretch = [0,1,1,1,1,1,1,0]
            for col,cstr in zip(range(0,len(colstretch)),colstretch):
                self.alltabdata[curtabnum]["mainsettingslayout"].setColumnStretch(col,cstr)
            rowstretch = [2,1,1,1,1,1,1,4]
            for row,rstr in zip(range(0,len(rowstretch)),rowstretch):
                self.alltabdata[curtabnum]["mainsettingslayout"].setRowStretch(row,rstr)
                
                
            #making widgets for file saving tab
            self.alltabdata[curtabnum]["tabwidgets"]["savetitle"] = QLabel("Save: ")
            self.alltabdata[curtabnum]["tabwidgets"]["saveaudio"] = QCheckBox('Save audio (WAV) file')
            self.alltabdata[curtabnum]["tabwidgets"]["saveaudio"].setChecked(True)
            self.alltabdata[curtabnum]["tabwidgets"]["savespectro"] = QCheckBox('Save spectrogram')  
            self.alltabdata[curtabnum]["tabwidgets"]["savespectro"].clicked.connect(self.updatesavespectrobox)
            self.alltabdata[curtabnum]["tabwidgets"]["savefile"] = QPushButton('Save File(s)') 
            self.alltabdata[curtabnum]["tabwidgets"]["savefile"].clicked.connect(self.savefiles)
            
            
            self.alltabdata[curtabnum]["tabwidgets"]["timerangetitle"] = QLabel("Time range to save:")
            self.alltabdata[curtabnum]["tabwidgets"]["savesubset"] = QCheckBox('Save subset')
            self.alltabdata[curtabnum]["tabwidgets"]["savesubset"].clicked.connect(self.updatesavesubsetbox)
            
            self.alltabdata[curtabnum]["tabwidgets"]["starttimetitle"] = QLabel("Start Time: ")
            self.alltabdata[curtabnum]["tabwidgets"]["starttimetitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["starttime"] = QDoubleSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["starttime"].setRange(0, 0)
            self.alltabdata[curtabnum]["tabwidgets"]["starttime"].setSingleStep(0.05)
            self.alltabdata[curtabnum]["tabwidgets"]["starttime"].setDecimals(2)
            self.alltabdata[curtabnum]["tabwidgets"]["starttime"].setValue(0)
            self.alltabdata[curtabnum]["tabwidgets"]["endtimetitle"] = QLabel("End Time: ")
            self.alltabdata[curtabnum]["tabwidgets"]["endtimetitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["endtime"] = QDoubleSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["endtime"].setRange(0, 0)
            self.alltabdata[curtabnum]["tabwidgets"]["endtime"].setSingleStep(0.05)
            self.alltabdata[curtabnum]["tabwidgets"]["endtime"].setDecimals(2)
            self.alltabdata[curtabnum]["tabwidgets"]["endtime"].setValue(0)
            
            
            self.alltabdata[curtabnum]["tabwidgets"]["spectrosettingstitle"] = QLabel("Spectrogram Settings: ")
            self.alltabdata[curtabnum]["tabwidgets"]["savecmintitle"] = QLabel("Color Min: ")
            self.alltabdata[curtabnum]["tabwidgets"]["savecmintitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["savecmaxtitle"] = QLabel("Color Max: ")
            self.alltabdata[curtabnum]["tabwidgets"]["savecmaxtitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["savecmin"] = QDoubleSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["savecmin"].setRange(0.0, 299.9)
            self.alltabdata[curtabnum]["tabwidgets"]["savecmin"].setSingleStep(0.1)
            self.alltabdata[curtabnum]["tabwidgets"]["savecmin"].setDecimals(1)
            self.alltabdata[curtabnum]["tabwidgets"]["savecmin"].setValue(initstats["crange"][0])
            self.alltabdata[curtabnum]["tabwidgets"]["savecmax"] = QDoubleSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["savecmax"].setRange(0.1, 300)
            self.alltabdata[curtabnum]["tabwidgets"]["savecmax"].setSingleStep(0.1)
            self.alltabdata[curtabnum]["tabwidgets"]["savecmax"].setDecimals(1)
            self.alltabdata[curtabnum]["tabwidgets"]["savecmax"].setValue(initstats["crange"][1])
            
            
            self.alltabdata[curtabnum]["tabwidgets"]["savefmintitle"] = QLabel("Frequency Min (Hz): ")
            self.alltabdata[curtabnum]["tabwidgets"]["savefmintitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["savefmaxtitle"] = QLabel("Frequency Max (Hz): ")
            self.alltabdata[curtabnum]["tabwidgets"]["savefmaxtitle"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.alltabdata[curtabnum]["tabwidgets"]["savefmin"] = QSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["savefmin"].setRange(0, 49999)
            self.alltabdata[curtabnum]["tabwidgets"]["savefmin"].setSingleStep(1)
            self.alltabdata[curtabnum]["tabwidgets"]["savefmin"].setValue(initstats["frange"][0])
            self.alltabdata[curtabnum]["tabwidgets"]["savefmax"] = QSpinBox() 
            self.alltabdata[curtabnum]["tabwidgets"]["savefmax"].setRange(0, 50000)
            self.alltabdata[curtabnum]["tabwidgets"]["savefmax"].setSingleStep(1)
            self.alltabdata[curtabnum]["tabwidgets"]["savefmax"].setValue(initstats["frange"][1])
            
            
            self.alltabdata[curtabnum]["tabwidgets"]["savespectro"].setChecked(True)
            self.updatesavespectrobox(True)
            self.alltabdata[curtabnum]["tabwidgets"]["savesubset"].setChecked(False)
            self.updatesavesubsetbox(False)
            
            
            
            widgetorder = ["savetitle", "saveaudio", "savespectro", "savefile",     "timerangetitle", "savesubset", "starttimetitle", "starttime", "endtimetitle", "endtime",     "spectrosettingstitle", "savecmintitle", "savecmin", "savecmaxtitle", "savecmax", "savefmintitle", "savefmin", "savefmaxtitle", "savefmax",]
            wrows     = [1,2,3,4,  1,2,3,3,4,4,  1,2,2,3,3,4,4,5,5]
            wcols     = [1,1,1,1,  3,3,3,4,3,4,  6,6,7,6,7,6,7,6,7]
            wrext     = [1,1,1,1,  1,1,1,1,1,1,  1,1,1,1,1,1,1,1,1]
            wcolext   = [1,1,1,1,  2,2,1,1,1,1,  2,1,1,1,1,1,1,1,1]
    
            #adding user inputs
            for i,r,c,re,ce in zip(widgetorder,wrows,wcols,wrext,wcolext):
                self.alltabdata[curtabnum]["plotsavelayout"].addWidget(self.alltabdata[curtabnum]["tabwidgets"][i],r,c,re,ce)
    
            #adjusting stretch factors for all rows/columns
            colstretch = [6,4,1,2,2,1,2,2,6]
            for col,cstr in zip(range(0,len(colstretch)),colstretch):
                self.alltabdata[curtabnum]["plotsavelayout"].setColumnStretch(col,cstr)
            rowstretch = [3,1,1,1,1,1,5]
            for row,rstr in zip(range(0,len(rowstretch)),rowstretch):
                self.alltabdata[curtabnum]["plotsavelayout"].setRowStretch(row,rstr)
                
            

            ##making the current layout for the tab
            self.alltabdata[curtabnum]["tab"].setLayout(self.alltabdata[curtabnum]["mainLayout"])

        except Exception: #if something breaks
            trace_error()
            self.posterror("Failed to build new tab")
        
            
    
            

# =============================================================================
#       Plot update and control, signal processor interactions
# =============================================================================

    def getspecs(self):
        curtabnum,_ = self.whatTab()
        stats = self.alltabdata[curtabnum]["stats"]
        
        fsnunits = "Hz"
        
        if stats["updated"]:
            fs = stats["fs"]
            nfft = stats["N"]
            df = np.round(stats["df"],4)
            
            if fs > 1000:
                fsnunits = "kHz"
                fs /= 1000
                
            fn = fs/2
                
        else:
            fs = fn = df = nfft = "TBD"
            
        text = f"Specifications: \nSampling Frequency {fs} {fsnunits}\nNyquist Frequency {fn} {fsnunits}\nNFFT: {nfft}\nFrequency Resolution: {df} Hz"
        return text
        
        

    def updatecurtabsettings(self):
        curtabnum,_ = self.whatTab()
        self.pullsettings(curtabnum,True)
        
        
        
    def pullsettings(self,curtabnum, updateProcessor):        
        oldrange = self.alltabdata[curtabnum]["stats"]["timerange"]
        self.alltabdata[curtabnum]["stats"]["timerange"] = self.alltabdata[curtabnum]["tabwidgets"]["timerange"].value()
        
        oldcrange = self.alltabdata[curtabnum]["stats"]["crange"]
        self.alltabdata[curtabnum]["stats"]["crange"] = [self.alltabdata[curtabnum]["tabwidgets"]["cmin"].value(), self.alltabdata[curtabnum]["tabwidgets"]["cmax"].value()]
        if self.alltabdata[curtabnum]["stats"]["crange"][1] <= self.alltabdata[curtabnum]["stats"]["crange"][0]:
            self.alltabdata[curtabnum]["stats"]["crange"] = oldcrange
            self.alltabdata[curtabnum]["tabwidgets"]["cmin"].setValue(oldcrange[0])
            self.alltabdata[curtabnum]["tabwidgets"]["cmax"].setValue(oldcrange[1])
            self.postwarning("Maximum color range must exceed minimum value!")
            
        oldfrange = self.alltabdata[curtabnum]["stats"]["frange"]
        self.alltabdata[curtabnum]["stats"]["frange"] = [self.alltabdata[curtabnum]["tabwidgets"]["fmin"].value(), self.alltabdata[curtabnum]["tabwidgets"]["fmax"].value()]
        if self.alltabdata[curtabnum]["stats"]["frange"][1] <= self.alltabdata[curtabnum]["stats"]["frange"][0]:
            self.alltabdata[curtabnum]["stats"]["frange"] = oldcrange
            self.alltabdata[curtabnum]["tabwidgets"]["fmin"].setValue(oldfrange[0])
            self.alltabdata[curtabnum]["tabwidgets"]["fmax"].setValue(oldfrange[1])
            self.postwarning("Maximum frequency range must exceed minimum value!")
        
        self.alltabdata[curtabnum]["stats"]["reprate"] = self.alltabdata[curtabnum]["tabwidgets"]["reprate"].value()
        self.alltabdata[curtabnum]["stats"]["fftwindow"] = self.alltabdata[curtabnum]["tabwidgets"]["fftlen"].value()
        self.alltabdata[curtabnum]["stats"]["alpha"] = self.alltabdata[curtabnum]["tabwidgets"]["alpha"].value()
                
        self.updateAxesLimits(curtabnum)
        self.updatecolorbar(curtabnum,self.alltabdata[curtabnum]["stats"]["crange"])
            
        if self.alltabdata[curtabnum]["isprocessing"] and updateProcessor:
            self.alltabdata[curtabnum]["Processor"].changethresholds_slot(self.alltabdata[curtabnum]["stats"]["fftwindow"], self.alltabdata[curtabnum]["stats"]["reprate"], self.alltabdata[curtabnum]["stats"]["alpha"])
            
        #updating QLabel with signal processing specs
        ctext = self.getspecs()
        self.alltabdata[curtabnum]["tabwidgets"]["specs"].setText(ctext)
        
        #updating color and frequency ranges on save plot
        self.alltabdata[curtabnum]["tabwidgets"]["savecmin"].setValue(self.alltabdata[curtabnum]["stats"]["crange"][0])
        self.alltabdata[curtabnum]["tabwidgets"]["savecmax"].setValue(self.alltabdata[curtabnum]["stats"]["crange"][1])
        self.alltabdata[curtabnum]["tabwidgets"]["savefmin"].setValue(self.alltabdata[curtabnum]["stats"]["frange"][0])
        self.alltabdata[curtabnum]["tabwidgets"]["savefmax"].setValue(self.alltabdata[curtabnum]["stats"]["frange"][1])
        
        
        
    @pyqtSlot(int,int,float,int,np.ndarray)
    def updatesettingsfromprocessor(self,tabID,fs,df,N,freqs): #TODO: SORT OUT FMIN AND FMAX STUFF + FREQUENCY TRIMMING!!!
        curtabnum = self.tabnumbers.index(tabID)
        self.alltabdata[curtabnum]["stats"]["updated"] = True
        self.alltabdata[curtabnum]["stats"]["fs"] = fs
        self.alltabdata[curtabnum]["stats"]["N"] = N
        self.alltabdata[curtabnum]["stats"]["df"] = df
        self.alltabdata[curtabnum]["stats"]["freqs"] = freqs
        self.alltabdata[curtabnum]["data"]["freqs"] = freqs
        
        maxF = int(np.ceil(fs/2))
        self.alltabdata[curtabnum]["tabwidgets"]["fmin"].setRange(0, maxF-1)
        self.alltabdata[curtabnum]["tabwidgets"]["fmax"].setRange(0, maxF)
        self.alltabdata[curtabnum]["tabwidgets"]["savefmin"].setRange(0, maxF-1)
        self.alltabdata[curtabnum]["tabwidgets"]["savefmax"].setRange(0, maxF)
        if self.alltabdata[curtabnum]["stats"]["frange"][0] >= maxF:
            self.alltabdata[curtabnum]["stats"]["frange"][0] = 0
            self.alltabdata[curtabnum]["tabwidgets"]["fmin"].setValue(0)
        if self.alltabdata[curtabnum]["stats"]["frange"][1] > maxF:
            self.alltabdata[curtabnum]["stats"]["frange"][1] = maxF
            self.alltabdata[curtabnum]["tabwidgets"]["fmax"].setValue(maxF)
        cfrange = self.alltabdata[curtabnum]["stats"]["frange"]
        
        keepvals = np.all((np.greater_equal(freqs,cfrange[0]),np.less_equal(freqs,cfrange[1])),axis=0)
        freqs = freqs[keepvals]
        inds = np.argwhere(keepvals)
        fscale = int(np.ceil(len(freqs)/self.maxNfreqs))
        self.alltabdata[curtabnum]["stats"]["fscale"]  = fscale
        relplotindices = range(int(np.floor(fscale/2)),len(freqs),fscale)
        self.alltabdata[curtabnum]["stats"]["plotindices"] = [inds[i] for i in relplotindices]
        self.alltabdata[curtabnum]["data"]["plotfreqs"] = [freqs[i] for i in relplotindices]
        
        self.pullsettings(curtabnum, False) #dont update processor to prevent recursion
        
        
        
        
    def gencolorbar(self,curtabnum,crange):
        
        self.cdata = np.genfromtxt('spectralcolors.txt',delimiter=',')
        self.npoints = self.cdata.shape[0] #number of colors
        self.spectralmap = ListedColormap(np.append(self.cdata, np.ones((np.shape(self.cdata)[0], 1)), axis=1))
        cbar_cm_object = self.buildspectrogramcolorbar(self.spectralmap, crange, self.alltabdata[curtabnum]["SpectroFig"], self.alltabdata[curtabnum]["SpectroAxes"])
        self.alltabdata[curtabnum]["SpectroCanvas"].draw()
        self.levels = np.linspace(crange[0],crange[1],self.npoints)
        
        return cbar_cm_object
        
        
        
    def updatecolorbar(self,curtabnum,crange):
        self.alltabdata[curtabnum]["colorbar"].set_clim(crange[0],crange[1])
        self.levels = np.linspace(crange[0],crange[1],self.npoints)
        self.alltabdata[curtabnum]["SpectroCanvas"].draw()
        
        
        

    def updateAxesLimits(self,curtabnum):
        timerange = self.alltabdata[curtabnum]["stats"]["timerange"]
        curlimit = self.alltabdata[curtabnum]["tabwidgets"]["ctime"].value()
        frange = self.alltabdata[curtabnum]["stats"]["frange"]
        self.alltabdata[curtabnum]["SpectroAxes"].set_xlim(curlimit - timerange,curlimit)
        self.alltabdata[curtabnum]["SpectroAxes"].set_ylim(frange[0], frange[1])
        self.alltabdata[curtabnum]["SpectroCanvas"].draw()
        
        
        
        
    def startprocessor(self):
        
        if self.threadpool.activeThreadCount() + 1 > self.threadpool.maxThreadCount():
            self.postwarning("The maximum number of simultaneous processing threads has been exceeded. This processor will automatically begin collecting data when STOP is selected on another tab.")
            
        else:
            curtabnum, tabID = self.whatTab()
            self.pullsettings(curtabnum, False) #don't need to update processor because it hasn't been initialized yet
            
            datasource = self.alltabdata[curtabnum]["tabwidgets"]["datasource"].currentText()
            
            if datasource.lower() == "wav file": #AUDIO FILE            
                # getting filename
                fname, ok = QFileDialog.getOpenFileName(self, 'Open file',self.defaultfiledir,"Source Data Files (*.WAV *.Wav *.wav *PCM *Pcm *pcm)","",self.fileoptions)
                if not ok or fname == "":
                    self.alltabdata[curtabnum]["isprocessing"] = False
                    return
                else:
                    splitpath = path.split(fname)
                    self.defaultfiledir = splitpath[0]
                    
                self.alltabdata[curtabnum]["fromAudio"] = True
                    
                #determining which channel to use
                #selec-2=no box opened, -1 = box opened, 0 = box closed w/t selection, > 0 = selected channel
                try:
                    file_info = wave.open(fname)
                except:
                    self.postwarning("Unable to read audio file")
                    return 
                    
                nchannels = file_info.getnchannels()
                if nchannels == 1:
                    datasource = f"AAA-00000-{fname}"
                    self.initiate_processor(tabID, datasource)
                else:
                    if self.audioWindowOpened: #active tab already opened 
                        self.postwarning("An audio channel selector dialog box has already been opened in another tab. Please close that box before processing an audio file with multiple channels in this tab.")
                        
                    else:
                        self.audioWindowOpened = True
                        self.audioChannelSelector = AudioWindow(nchannels, tabID, fname) #creating and connecting window
                        self.audioChannelSelector.signals.closed.connect(self.audioWindowClosed)
                        self.audioChannelSelector.show() #bring window to front
                        self.audioChannelSelector.raise_()
                        self.audioChannelSelector.activateWindow()
                        
                        
            else: #SPEAKER STREAM
                dataindex = self.audiosourceIDs[self.alltabdata[curtabnum]["tabwidgets"]["datasource"].currentIndex()]
                datasource = f"MMM-{dataindex}"
                self.alltabdata[curtabnum]["fromAudio"] = False
                self.initiate_processor(tabID, datasource)
                        
            
            
    #slot in main program to close window (only one channel selector window can be open at a time)
    @pyqtSlot(int, int, str)
    def audioWindowClosed(self, wasGood, tabID, datasource):
        if wasGood:
            self.audioWindowOpened = False
            self.initiate_processor(tabID, datasource)
        
                        
        
    def initiate_processor(self, tabID, datasource):
        
        curtabnum = self.tabnumbers.index(tabID)
        
        #making datasource QComboBox un-selectable so source can't be changed after processing initiated
        self.alltabdata[curtabnum]["tabwidgets"]["datasource"].setEnabled(False)
        self.alltabdata[curtabnum]["tabwidgets"]["ctime"].setEnabled(False)
        self.alltabdata[curtabnum]["tabwidgets"]["fftlen"].setEnabled(False)
        self.alltabdata[curtabnum]["tabwidgets"]["ctime"].setEnabled(False)
        
        #data relevant for thread
        starttime = datetime.utcnow()
        fftwindow = self.alltabdata[curtabnum]["stats"]["fftwindow"]
        dt = self.alltabdata[curtabnum]["stats"]["reprate"]
        alpha = self.alltabdata[curtabnum]["stats"]["alpha"]
        
        self.alltabdata[curtabnum]["stats"]["updateint"] = int(np.ceil(1/dt)) #updates visual once every second for live audio
        
        #saving datasource
        self.alltabdata[curtabnum]["datasource"] = datasource
        
        #setting up progress bar for audio
        if datasource[:3].lower() == "aaa":
            self.alltabdata[curtabnum]["tabwidgets"]["audioprogressbar"] = QProgressBar()
            self.alltabdata[curtabnum]["mainLayout"].addWidget(
                self.alltabdata[curtabnum]["tabwidgets"]["audioprogressbar"], 0,1,1,1)
            self.alltabdata[curtabnum]["tabwidgets"]["audioprogressbar"].setValue(0)
            QApplication.processEvents()
        
        #initializing and starting thread
        self.alltabdata[curtabnum]["Processor"] = AP.AudioProcessor(self.PyAudioObject, datasource, self.tempdir, self.slash, tabID, starttime, fftwindow, dt, alpha)
        self.threadpool.start(self.alltabdata[curtabnum]["Processor"])
        
        #connecting slots
        self.alltabdata[curtabnum]["Processor"].signals.iterated.connect(self.updateUIinfo)
        self.alltabdata[curtabnum]["Processor"].signals.statsupdated.connect(self.updatesettingsfromprocessor)
        self.alltabdata[curtabnum]["Processor"].signals.terminated.connect(self.updateUIfinal)
        self.alltabdata[curtabnum]["isprocessing"] = True
        self.alltabdata[curtabnum]["tabwidgets"]["start"].setEnabled(False)
        
        
    def stopprocessor(self):
        curtabnum,_ = self.whatTab()
        if self.alltabdata[curtabnum]["isprocessing"]:
            self.alltabdata[curtabnum]["Processor"].abort()
            self.alltabdata[curtabnum]["isprocessing"] = False   
            
        
    def append_spectral_data(self, mainspectra, newspectra, trimData, fsc, inds):
        
        #trimming new spectra
        if trimData:
            lenspec = len(newspectra)
            newspectra_cut = np.array([])
            for i in inds:
                sind = int(np.max([0, i-fsc]))
                eind = int(np.min([lenspec, i+fsc]))
                newspectra_cut = np.append(newspectra_cut, np.max(newspectra[sind:eind]))
        else:
            newspectra_cut = newspectra
        
        if mainspectra.shape == (1,0):
            output = np.rot90(np.array([newspectra_cut]),1)
        else:
            output = np.append(mainspectra,np.rot90(np.array([newspectra_cut]),1),axis=1)
        return output
        
        
        
    @pyqtSlot(int,int,int,float,np.ndarray)
    def updateUIinfo(self,i,maxnum,tabID,ctime,spectra): #TODO: configure PyQtSlot to receive data from processor thread and update spectrogram
        curtabnum = self.tabnumbers.index(tabID)
        if self.alltabdata[curtabnum]["fromAudio"]: #from audio file
            self.alltabdata[curtabnum]["tabwidgets"]["audioprogressbar"].setValue(int(np.round(100*i/maxnum)))
        
        #saving data
        self.alltabdata[curtabnum]["data"]["maxtime"] = ctime
        self.alltabdata[curtabnum]["data"]["ctime"] = ctime
        self.alltabdata[curtabnum]["data"]["spectra"] = self.append_spectral_data(self.alltabdata[curtabnum]["data"]["spectra"], spectra, False, None, None)
        self.alltabdata[curtabnum]["data"]["times"] = np.append(self.alltabdata[curtabnum]["data"]["times"], ctime)
        self.alltabdata[curtabnum]["data"]["isplotted"].append(False)
        
        #update spectrogram every 5 points for realtime or 50 points for audio (should be every 1 sec for a 10Hz reprate)
        if (maxnum == 0 and i%self.alltabdata[curtabnum]["stats"]["updateint"]==0) or (maxnum > 0 and i%10==0):
            self.updateplot(curtabnum)
    
            
    
    
    def updateplot(self,curtabnum):
        if self.alltabdata[curtabnum]["data"]["isplotted"].count(False) >= 3:
            
            whatplot = [not x for x in self.alltabdata[curtabnum]["data"]["isplotted"]] #indices to plot
            crange = self.alltabdata[curtabnum]["stats"]["crange"]
            
            freqs = self.alltabdata[curtabnum]["data"]["plotfreqs"] #pulling data to plot
            fsc = int(np.ceil(self.alltabdata[curtabnum]["stats"]["fscale"]/2))
            inds = self.alltabdata[curtabnum]["stats"]["plotindices"]
            times = np.array([])
            plotspectra = np.array([[]])
            plotted = []
            for (i,needsplotted) in enumerate(whatplot):
                if needsplotted:
                    plotspectra = self.append_spectral_data(plotspectra, self.alltabdata[curtabnum]["data"]["spectra"][:,i], True, fsc, inds)
                    times = np.append(times,self.alltabdata[curtabnum]["data"]["times"][i])
                    plotted.append(i)
                    
            del plotted[-1] #last point needs replotted to ensure no gaps in the spectrogram
            
            dy = self.alltabdata[curtabnum]["stats"]["df"]/2
            dx = self.alltabdata[curtabnum]["stats"]["reprate"]/2
            extent = [times[0]-dx, times[-1]+dx, freqs[0]-dy, freqs[-1]+dy]
            self.alltabdata[curtabnum]["SpectroAxes"].imshow(plotspectra, aspect="auto", cmap=self.spectralmap, vmin=crange[0], vmax=crange[1], extent=extent)
            self.alltabdata[curtabnum]["SpectroAxes"].set_ylim(freqs[0],freqs[-1])
            ctime = self.alltabdata[curtabnum]["data"]["ctime"]
            timerange = self.alltabdata[curtabnum]["stats"]["timerange"]
            self.alltabdata[curtabnum]["SpectroAxes"].set_xlim(ctime-timerange,ctime)
            self.alltabdata[curtabnum]["SpectroCanvas"].draw()
            
            for i in plotted:
                self.alltabdata[curtabnum]["data"]["isplotted"][i] = True
            
                
        
    
    @pyqtSlot(int,int)
    def updateUIfinal(self,tabID,reason): #TODO: final plot update (error codes, etc)
        curtabnum = self.tabnumbers.index(tabID)
        curtabname = self.tabWidget.tabText(curtabnum)
        
        self.alltabdata[curtabnum]["isprocessing"] = False
        self.updateplot(curtabnum)
        
        maxval = np.round(self.alltabdata[curtabnum]["data"]["maxtime"]*20)/20
        
        self.alltabdata[curtabnum]["tabwidgets"]["ctime"].setEnabled(True)
        self.alltabdata[curtabnum]["data"]["ctime"] = self.alltabdata[curtabnum]["data"]["maxtime"]
        self.alltabdata[curtabnum]["tabwidgets"]["ctime"].setRange(0, maxval)
        self.alltabdata[curtabnum]["tabwidgets"]["ctime"].setValue(maxval)
        
        self.alltabdata[curtabnum]["tabwidget"].setTabEnabled(1,True)
        self.alltabdata[curtabnum]["tabwidgets"]["starttime"].setRange(0, maxval-0.5)
        self.alltabdata[curtabnum]["tabwidgets"]["starttime"].setValue(0)
        self.alltabdata[curtabnum]["tabwidgets"]["endtime"].setRange(0, maxval)
        self.alltabdata[curtabnum]["tabwidgets"]["endtime"].setValue(maxval)
        
        
        if self.alltabdata[curtabnum]["fromAudio"]:
            self.alltabdata[curtabnum]["tabwidgets"]["audioprogressbar"].deleteLater()
        
        if reason:
            if reason == 1:
                issue = "Unable to find selected audio file!"
            elif reason == 2:
                issue = "Unable to access selected audio device!"
            elif reason == 3:
                issue = "Failed to initialize AudioProcessor thread (timeout)"
            elif reason == 4:
                issue = "Unidentified error during AudioProcessor event loop"
            elif reason == 5:
                issue = "Error raised during audio stream callback function!"
            errorMessage = f"Error with tab {curtabname} (tab #{curtabnum}): {issue}"
            self.posterror(errorMessage)
        
            
            
            
    
# =============================================================================
#       PLOTTING STUFF (TODO: consolidate plotting functions from realtime and spectrogram saving functions here)
# =============================================================================                
    
    def buildspectrogramcolorbar(self, spectralmap, crange, fig, ax):
        cbar_cm_object = cm.ScalarMappable(norm=Normalize(vmin=crange[0], vmax=crange[1]), cmap=spectralmap)
        cbar = fig.colorbar(cbar_cm_object, ax=ax)
        cbar.set_label('Sound Level (dB re 1 bit$^2$ Hz$^{-1}$)')
        return cbar_cm_object

            
# =============================================================================
#       FILE SAVING STUFF
# =============================================================================      
        
    def updatesavespectrobox(self,isChecked): 
        curtabnum,_ = self.whatTab()
        self.alltabdata[curtabnum]["tabwidgets"]["savecmin"].setEnabled(isChecked)
        self.alltabdata[curtabnum]["tabwidgets"]["savecmax"].setEnabled(isChecked)
        self.alltabdata[curtabnum]["tabwidgets"]["savefmin"].setEnabled(isChecked)
        self.alltabdata[curtabnum]["tabwidgets"]["savefmax"].setEnabled(isChecked)
        
    def updatesavesubsetbox(self, isChecked):
        curtabnum,_ = self.whatTab()
        self.alltabdata[curtabnum]["tabwidgets"]["starttime"].setEnabled(isChecked)
        self.alltabdata[curtabnum]["tabwidgets"]["endtime"].setEnabled(isChecked)  
        
        
        
    def savefiles(self):
        
        curtabnum,tabID = self.whatTab()
        
        #getting data
        saveAudio = self.alltabdata[curtabnum]["tabwidgets"]["saveaudio"].isChecked()
        saveSpectro = self.alltabdata[curtabnum]["tabwidgets"]["savespectro"].isChecked()
        
        savesubset = self.alltabdata[curtabnum]["tabwidgets"]["savesubset"].isChecked()
        if savesubset:
            timerange = [self.alltabdata[curtabnum]["tabwidgets"]["starttime"].value(), self.alltabdata[curtabnum]["tabwidgets"]["endtime"].value()]
        else:
            timerange = [0, self.alltabdata[curtabnum]["data"]["maxtime"]]
        
        colorrange = [self.alltabdata[curtabnum]["tabwidgets"]["savecmin"].value(), self.alltabdata[curtabnum]["tabwidgets"]["savecmax"].value()]
        freqrange = [self.alltabdata[curtabnum]["tabwidgets"]["savefmin"].value(), self.alltabdata[curtabnum]["tabwidgets"]["savefmax"].value()]
        
        if saveAudio:
            #file dialog box to save wav file
            audiofilename = self.getFileSaveSelection("WAV (audio)","Raw Audio (*.wav)")
            
        if saveSpectro:
            #file dialog box to save spectrogram
            spectrofilename = self.getFileSaveSelection("Spectrogram (PNG)","Image (*.png)")
            
        
        #saving files (sets spinning cursor while saving)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        if saveAudio and audiofilename:
            self.saveAudioFile(audiofilename,curtabnum,tabID,savesubset,timerange) 
        if saveSpectro and spectrofilename:
            self.saveSpectroFile(spectrofilename,curtabnum,timerange,freqrange,colorrange) 
        QApplication.restoreOverrideCursor()
        
        
        
        
    def saveAudioFile(self,filename,curtabnum,tabID,savesubset,timerange):
        if filename[-4:].lower() != ".wav":
            filename += ".wav"
        
        origfilename = self.tempdir + self.slash +  "tempwav_" + str(tabID) + '.WAV'
                
        if savesubset: #only saving a subset of the file- 
            fs, snd = sciwavfile.read(origfilename) #reading file
            
            #pulling pcm data for correct channel number (if datasource was audio)
            cdatasource = self.alltabdata[curtabnum]["datasource"]
            if cdatasource[:3].lower() == "aaa":
                chnum = int(cdatasource[4:9])
                if chnum > 0:
                    audiostream = snd[:, chnum-1]
                else:
                    audiostream = snd
            else:
                audiostream = snd
            
            #configuring wav file
            wavfile = wave.open(filename,'wb')
            wave.Wave_write.setnchannels(wavfile,1) #single channel output
            wave.Wave_write.setsampwidth(wavfile,2) #sample size configured as int16
            wave.Wave_write.setframerate(wavfile,fs)
            
            #trimming audiostream to only necessary data
            sind = int(np.round(fs*timerange[0]))
            eind = int(np.round(fs*timerange[1]))
            
            #writing pcm data to new wav file, closing
            wave.Wave_write.writeframes(wavfile, bytearray(audiostream[sind:eind]))
            wave.Wave_write.close(wavfile)
            
            
        else: #saving the whole file- just copy the tempfile to specified directory
            shutil.copy(origfilename, filename)
            #if savesubset == True, open temp wave file, trim data, resave to correct location
        
        
        
        
        
        
        
    def saveSpectroFile(self,filename,curtabnum,timerange,freqrange,colorrange):
        if filename[-4:].lower() != ".png":
            filename += ".png"
            
        freqs = self.alltabdata[curtabnum]["data"]["freqs"] #pulling data to plot
        times = self.alltabdata[curtabnum]["data"]["times"]
        spectra = self.alltabdata[curtabnum]["data"]["spectra"]
        
        #trimming data
        keepfreqs = np.all((np.greater_equal(freqs,freqrange[0]),np.less_equal(freqs,freqrange[1])),axis=0)
        keeptimes = np.all((np.greater_equal(times,timerange[0]),np.less_equal(times,timerange[1])),axis=0)
        freqs = freqs[keepfreqs]
        times = times[keeptimes]
        spectra = spectra[np.ix_(keepfreqs, keeptimes)]
                
        #calculating pixel extent for plt.imshow()
        dy = self.alltabdata[curtabnum]["stats"]["df"]/2
        dx = self.alltabdata[curtabnum]["stats"]["reprate"]/2
        extent = [times[0]-dx, times[-1]+dx, freqs[0]-dy, freqs[-1]+dy]
        
        #making figure
        fig = plt.figure()
        fig.clear()
        fig.set_size_inches(8,4)
        ax = fig.add_axes([0.1,0.15,0.9,0.80])
        
        #adding colorbar to plot
        self.buildspectrogramcolorbar(self.spectralmap, colorrange, fig, ax)
        
        #adding data to plot
        # ax.imshow(spectra, aspect="auto", cmap=self.spectralmap, vmin=colorrange[0], vmax=colorrange[1], extent=extent)
        ax.contourf(times, freqs, spectra, cmap=self.spectralmap, vmin=colorrange[0], vmax=colorrange[1])
        
        #formatting
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Frequency (Hz)')
        ax.set_ylim(freqrange[0], freqrange[1])
        ax.set_xlim(timerange[0], timerange[1])
                
        #saving figure
        fig.savefig(filename, format='png', dpi=300)
        
        
        
        
        
        
    
    def getFileSaveSelection(self,filekind,fileext):
        try:
            savefile = str(QFileDialog.getSaveFileName(self, f"Select {filekind} filename to save", self.defaultfiledir, fileext, options=QFileDialog.DontUseNativeDialog))
            #checking directory validity
            if savefile == '':
                return False
            else:
                return savefile.replace('(',',').replace(')',',').split(',')[1][1:-1] #returning just the selected filename
                                
        except:
            trace_error()
            self.posterror("Error raised in directory selection")
            return False
            
            
            
            
        
# =============================================================================
#     TAB MANIPULATION OPTIONS, OTHER GENERAL FUNCTIONS
# =============================================================================

    #handles tab indexing
    def addnewtab(self):
        #creating numeric ID for newly opened tab
        self.totaltabs += 1
        self.tabnumbers.append(self.totaltabs)
        newtabnum = self.tabWidget.count()
        return newtabnum

    #gets index of open tab in GUI
    def whatTab(self):
        curtabnum = self.tabWidget.currentIndex()
        return curtabnum, self.tabnumbers[curtabnum]
    
    #renames tab (only user-visible name, not self.alltabdata dict key)
    def renametab(self):
        try:
            curtabnum,_ = self.whatTab()
            name, ok = QInputDialog.getText(self, 'Rename Current Tab', 'Enter new tab name:',QLineEdit.Normal,str(self.tabWidget.tabText(curtabnum)))
            if ok:
                self.tabWidget.setTabText(curtabnum,name)
        except Exception:
            trace_error()
            self.posterror("Failed to rename the current tab")
    
    #sets default color scheme for tabs
    def setnewtabcolor(self,tab):
        p = QPalette()
        gradient = QLinearGradient(0, 0, 0, 400)
        gradient.setColorAt(0.0, QColor(255,253,253))
        #gradient.setColorAt(1.0, QColor(248, 248, 255))
        gradient.setColorAt(1.0, QColor(255, 225, 225))
        p.setBrush(QPalette.Window, QBrush(gradient))
        tab.setAutoFillBackground(True)
        tab.setPalette(p)
            
        
    #closes a tab
    def closecurrenttab(self):
        try:
            reply = QMessageBox.question(self, 'Message',
                "Are you sure to close the current tab?", QMessageBox.Yes | 
                QMessageBox.No, QMessageBox.No)

            if reply == QMessageBox.Yes:

                #getting tab to close
                curtabnum,_ = self.whatTab()
                
                #add any additional necessary commands (stop threads, prevent memory leaks, etc) here
                
                #closing tab
                self.tabWidget.removeTab(curtabnum)

                #removing current tab data from the self.alltabdata dict, correcting tabnumbers variable
                self.alltabdata.pop(curtabnum)
                self.tabnumbers.pop(curtabnum)

        except Exception:
            trace_error()
            self.posterror("Failed to close the current tab")
                
    def cleantempfiles(self):
        # delete all temporary files
        allfilesanddirs = listdir(self.tempdir)
        for cfile in allfilesanddirs:
            if len(cfile) >= 5:
                cfilestart = cfile[:4]
                cfileext = cfile[-3:]
                if (cfilestart.lower() == 'temp' and cfileext.lower() == 'wav'):
                    remove(self.tempdir + self.slash + cfile)
        
    #warning message
    def postwarning(self,warningtext):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setText(warningtext)
        msg.setWindowTitle("Warning")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()
        
    #error message
    def posterror(self,errortext):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setText(errortext)
        msg.setWindowTitle("Error")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()
    
    #warning message with options (Okay or Cancel)
    def postwarning_option(self,warningtext):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setText(warningtext)
        msg.setWindowTitle("Warning")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        outval = msg.exec_()
        option = 'unknown'
        if outval == 1024:
            option = 'okay'
        elif outval == 4194304:
            option = 'cancel'
        return option
    
    #add warning message before closing GUI
    def closeEvent(self, event):
        reply = QMessageBox.question(self, 'Message',
            "Are you sure to close the application? \n All unsaved work will be lost!", QMessageBox.Yes | 
            QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:

            #explicitly closing figures to clean up memory (should be redundant here but just in case)
            for tab in self.alltabdata:
                plt.close(tab["SpectroFig"])

                #aborting all threads
                if tab["isprocessing"]:
                    tab["Processor"].abort()
            self.cleantempfiles()
            event.accept()
        else:
            event.ignore() 
            
            
            
    

# =============================================================================
#        POPUP WINDOW FOR AUDIO CHANNEL SELECTION
# =============================================================================

class AudioWindow(QWidget):
    
    def __init__(self, nchannels, tabID, fname):
        super(AudioWindow, self).__init__()
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        self.selectedChannel = 1
        self.wasClosed = False
        self.nchannels = nchannels
        self.fname = fname
        self.tabID = tabID
        
        self.signals = AudioWindowSignals()
        
        self.title = QLabel("Select channel to read\n(for 2-channel WAV files,\nCh1 = left and Ch2 = right):")
        self.spinbox = QSpinBox()
        self.spinbox.setMinimum(1)
        self.spinbox.setMaximum(self.nchannels)
        self.spinbox.setSingleStep(1)
        self.spinbox.setValue(self.selectedChannel)
        self.finish = QPushButton("Select Channel")
        self.finish.clicked.connect(self.selectChannel)
        
        self.layout.addWidget(self.title)
        self.layout.addWidget(self.spinbox)
        self.layout.addWidget(self.finish)
        
        self.show()
                
        
    def selectChannel(self):
        self.selectedChannel = self.spinbox.value()
        
        #format is Audio<channel#><filename> e.g. Audio0002/My/File.WAV
        #allowing for 5-digit channels since WAV file channel is a 16-bit integer, can go to 65,536
        self.datasource = f"AAA-{self.selectedChannel:05d}-{self.fname}" 
        
        #emit signal
        self.signals.closed.emit(True, self.tabID, self.datasource)
        
        #close dialogue box
        self.wasClosed = True
        self.close()
        
        
    # add warning message on exit
    def closeEvent(self, event):
        event.accept()
        if not self.wasClosed:
            self.signals.closed.emit(False, "No", "No")
            self.wasClosed = True
            
#initializing signals for data to be passed back to main loop
class AudioWindowSignals(QObject): 
    closed = pyqtSignal(int, int, str)
        
        
        
        

    
# =============================================================================
# EXECUTE PROGRAM
# =============================================================================
if __name__ == '__main__':  
    app = QApplication(argv)
    ex = RunProgram()
    exit(app.exec_())
    
    
