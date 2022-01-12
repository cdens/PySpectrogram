# ==================================================================================================================
#     Code: AudioProcessor.py
#     Author: Casey R. Densmore
#     
#     Purpose: Handles all signal processing functions related to accessing microphones + converting PCM data to spectra
#
#   General Functions:
#       o freq,fftdata = dofft(pcmdata,fs,alpha): Runs fft on pcmdata with sampling frequency
#           fs using cosine taper (Tukey) defined by alpha
#   AudioProcessor Functions:
#       o __init__(datasource)
#       o Run(): A separate function called from main.py immediately after initializing the thread to start data 
#           collection. Here, the callback function which updates the audio stream for WiNRADIO threads is declared
#           and the stream is directed to this callback function. This also contains the primary thread loop which 
#           updates data from either the WiNRADIO or audio file continuously using dofft() and the conversion eqns.
#       o abort(): Aborts the thread, sends final data to the event loop and notifies the event loop that the
#           thread has been terminated
#       o terminate(errortype): terminates thread due to internal issue
#
#   ThreadProcessorSignals:
#       o iterated(ctabnum,ctemp, cdepth, cfreq, sigstrength, ctime, i): Passes information collected on the current
#           iteration of the thread loop back to the main program, in order to update the corresponding tab. "i" is
#           the iteration number- plots and tables are updated in the main loop every N iterations, with N specified
#           independently for plots/tables in main.py
#       o terminated(ctabnum): Notifies the main loop that the thread has been terminated/aborted
#       o terminated(flag): Notifies the main loop that an error (corresponding to the value of flag) occured, causing an
#           error message to be posted in the GUI
#       o updateprogress(ctabnum, progress): **For audio files only** updates the main loop with the progress 
#           (displayed in progress bar) for the current thread
#
# ==================================================================================================================

import numpy as np
from scipy.io import wavfile as sciwavfile #for wav file reading
from scipy.signal import tukey #taper generation

import wave #WAV file writing

from PyQt5.QtCore import pyqtSlot, pyqtSignal, QObject
from PyQt5.Qt import QRunnable

import time as timemodule
import datetime as dt

from traceback import print_exc as trace_error

from shutil import copy as shcopy
from os.path import exists
from sys import platform

import pyaudio


def listaudiodevices():
    miclist = []
    indices = []
    
    p = pyaudio.PyAudio()
    for i in range(p.get_device_count()):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            miclist.append(p.get_device_info_by_index(i).get('name'))
            indices.append(i)
            #cdict = p.get_device_info_by_index(i)
            #for ckey in cdict:
            #    print(f"{ckey}: {cdict[ckey]}\n")
    
    return miclist,indices,p
            

    
    
    

# =============================================================================
#  READ SIGNAL FROM WINRADIO, OUTPUT TO PLOT, TABLE, AND DATA
# =============================================================================


class AudioProcessor(QRunnable): 

    #initializing current thread (saving variables, reading audio data or contacting/configuring receiver)
    def __init__(self, p, datasource, savedir, slash, tabID, starttime, fftwindow, dt, alpha, *args,**kwargs):
        super(AudioProcessor, self).__init__()

        self.p = p #PyAudio instance if calling from mic
        
        self.slash = slash
        
        # UI inputs
        self.tabID = tabID
        self.starttime = starttime
        self.fftwindow = fftwindow
        self.dt = dt
        self.alpha = alpha
        
        #initializing inner workings
        self.isrunning = False  #set to true while running
        self.signals = ThreadProcessorSignals() # signal connections
        
        self.reason = 0
        
        #output audio (WAV) file name- saving in temporary folder passed from event loop
        self.wavfilename = savedir + self.slash +  "tempwav_" + str(self.tabID) + '.WAV'

        # identifying whether source is from file or mic
        self.fromAudio = False
        self.isfrommic = False
        if datasource[:3] == 'AAA':
            self.fromAudio = True
            
            chnum = int(datasource[4:9])
            self.audiofile = datasource[10:]
            if not exists(self.audiofile):
                self.terminate(1) #check that file is real, terminate if it isn't
            
            shcopy(self.audiofile, self.wavfilename) #copying audio file if datasource = from file
            self.fs, snd = sciwavfile.read(self.audiofile) #reading file
            
            if chnum > 0:
                self.audiostream = snd[:, chnum-1]
            else:
                self.audiostream = snd
            
            self.lensignal = len(self.audiostream)
                
                
        elif datasource[:3] == 'MMM':
            self.fromAudio = False
            self.audiosourceindex = int(datasource[4:])
            
            self.fs = int(np.round(p.get_device_info_by_index(self.audiosourceindex)['defaultSampleRate'])) #get sampling frequency
            self.sampwidth = 2 #2 bytes per sample corresponds to 16-bit integer
            self.frametype = pyaudio.paInt16
            self.audiostream = [0]*100000
            
            #setup WAV file to write (if audio or test, source file is copied instead)
            self.wavfile = wave.open(self.wavfilename,'wb')
            wave.Wave_write.setnchannels(self.wavfile,1) #single channel output
            wave.Wave_write.setsampwidth(self.wavfile,2) #sample size configured as int16
            wave.Wave_write.setframerate(self.wavfile,self.fs)
            
        else:
            self.terminate(1) #terminate before starting: invalid datasource
        
        self.isrunning = True
        
        

    @pyqtSlot()
    def run(self):
        
        #barrier to prevent signal processor loop from starting before __init__ finishes
        counts = 0
        while not self.isrunning:
            counts += 1
            if self.reason:
                return
            elif counts > 100:
                self.terminate(3)
                return
                
            timemodule.sleep(0.1)
            
        if self.reason: #just in case timing issues allow the while loop to terminate and then the reason is changed
            return
        #if the Run() method gets this far, __init__ has completed successfully (and set self.startthread = 100)
        
        
        #storing FFT settings (this can't happen in __init__ because it might emit updated settings before the slot is connected)
        self.changethresholds(self.fftwindow,self.dt,self.alpha)
        
        if self.fromAudio: #if source is an audio file 
            self.sampletimes = np.arange(0,self.lensignal/self.fs,self.dt) #sets times to sample from file
            self.maxnum = len(self.sampletimes)
            
        else: #using live mic for data source
            self.maxnum = 0 #TODO: ADD INITIALIZATION STUFF HERE
            try:
                
                #CALLBACK FUNCTION HERE
                def updateaudiobuffer(bufferdata, nframes, time_info, status):
                    try:
                        if self.isrunning:
                            self.audiostream.extend(bufferdata[:]) #append data to end
                            del self.audiostream[:nframes] #remove data from start
                            wave.Wave_write.writeframes(self.wavfile, bytearray(bufferdata))
                            returntype = pyaudio.paContinue
                        else:
                            returntype = pyaudio.paAbort
                    except Exception:
                        trace_error()  
                        self.terminate(5)
                        returntype = pyaudio.paAbort
                    finally:
                        return (None, returntype)
                    #end of callback function
                    
                #initializing and starting (start=True) pyaudio device input stream to callback function
                if platform.lower() == "darwin": #MacOS specific stream info input
                    self.stream = pyaudio.Stream(self.p, self.fs, 1, self.frametype, input=True, output=False, input_device_index=self.audiosourceindex, start=True, stream_callback=updateaudiobuffer, input_host_api_specific_stream_info=pyaudio.PaMacCoreStreamInfo())
                else: #windows or linux
                    self.stream = pyaudio.Stream(self.p, self.fs, 1, self.frametype, input=True, output=False, input_device_index=self.audiosourceindex, start=True, stream_callback=updateaudiobuffer)
                    
            except Exception:
                trace_error()
                self.terminate(2)
        
                
                
        try:
            # setting up thread while loop- terminates when user clicks "STOP" or audio file finishes processing
            i = -1

            while self.isrunning:
                i += 1

                # finds time from processor start in seconds
                curtime = dt.datetime.utcnow()  # current time
                deltat = curtime - self.starttime

                #pulling PCM data segment
                if self.fromAudio:
                    
                    if i < self.maxnum:
                        ctime = self.sampletimes[i] #center time for current sample
                    else:
                        self.terminate(0)
                        return
                        
                    ctrind = int(np.round(ctime*self.fs))
                    pmind = int(self.N/2)
                    
                    if ctrind - pmind >= 0 and ctrind + pmind < self.lensignal:       
                        pcmdata = self.audiostream[ctrind-pmind:ctrind+pmind]
                    else:
                        pcmdata = None
                        

                else:
                    ctime = deltat.total_seconds()
                    pcmdata = np.array(self.audiostream[-self.N:])
                
                if pcmdata is not None:
                    spectra = self.dofft(pcmdata)
                    self.signals.iterated.emit(i,self.maxnum,self.tabID,ctime,spectra) #sends current PSD/frequency, along with progress, back to event loop
                        
                if self.fromAudio:
                    timemodule.sleep(0.08)  # tiny pause to free resources
                    
                else: #wait for time threshold before getting next point
                    while (dt.datetime.utcnow() - curtime).total_seconds() < self.dt:
                        timemodule.sleep(0.1)  
                    

        except Exception: #if the thread encounters an error, terminate
            self.isrunning = False
            self.terminate(4)
            
            trace_error()  # if there is an error, terminates processing
            
    
            
            
    #function to run fft here
    def dofft(self, pcmdata): 
        
        if self.alpha > 0: #applying Tukey taper if necessary
            if pcmdata.shape[0] == self.taperlen: 
                ctaper = self.taper
            else:
                self.taper = tukey(pcmdata.shape[0], alpha=self.alpha)
            pcmdata = pcmdata*self.taper
        
        # conducting fft, calculating PSD
        spectra = np.abs(np.fft.fft(pcmdata)**2)/self.df #PSD = |X(f)^2| / df
        spectra[np.isinf(spectra)] = 1.0E-8 #replacing negative inf values (spectra power=0) with -1
    
        #limiting data to positive/real frequencies only (and convert to dB)
        spectra = np.log10(spectra[self.keepind])
        
        return spectra
            
    
        
        
    def calc_settings(self):
        
        self.N = int(np.round(self.fs*self.fftwindow))
        if self.N%2: #N must be even
            self.N += 1
            
            
        #define taper if nonzero alpha
        if self.alpha > 0:
            self.taper = tukey(self.N, alpha=self.alpha)
            self.taperlen = len(self.taper)
        else:
            self.taperlen = 0
        
        self.df = self.fs/self.N
        self.freqs_all = np.array([self.df * n if n < self.N / 2 else self.df * (n - self.N) for n in range(self.N)])
        self.keepind = np.greater_equal(self.freqs_all,0)
        self.freqs = self.freqs_all[self.keepind]
                
        self.signals.statsupdated.emit(self.tabID,self.fs,self.df,self.N,self.freqs)
        
        
        
        
        
    @pyqtSlot(float,float,float)
    def changethresholds_slot(self,fftwindow,dt,alpha): #update data thresholds for FFT
        self.changethresholds(fftwindow,dt,alpha)
        
        
    
    def changethresholds(self,fftwindow,dt,alpha): #update data thresholds for FFT
        if fftwindow <= 1:
            self.fftwindow = fftwindow
        else:
            self.fftwindow = 1
            
        self.dt = dt
        
        if alpha > 1:
            self.alpha = 1
        elif alpha < 0:
            self.alpha = 0
        else:
            self.alpha = alpha
            
        self.calc_settings()
        
        
        
        
    @pyqtSlot()
    def abort(self): #executed when user selects "Stop" button
        self.terminate(0) #terminates with exit code 0 (no error because user initiated quit)
        return
        
        
    def terminate(self,reason):
        self.reason = reason
        self.isrunning = False #guarantees that event loop ends
        
        #close audio file, terminate mic buffer
        if not self.fromAudio:
            wave.Wave_write.close(self.wavfile)
            self.stream.stop_stream()
            self.stream.close()
        
        #signal that tab indicated by curtabnum was closed due to reason indicated by variable 'reason'
        self.signals.terminated.emit(self.tabID,reason) #notify event loop that processor has stopped
        
        
        
        
        
#TODO: CONFIGURE THESE
#initializing signals for data to be passed back to main loop
class ThreadProcessorSignals(QObject): 
    iterated = pyqtSignal(int,int,int,float,np.ndarray) #signal to add another entry to raw data arrays
    statsupdated = pyqtSignal(int,int,float,int,np.ndarray)
    terminated = pyqtSignal(int,int) #signal that the loop has been terminated (by user input or program error)
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
