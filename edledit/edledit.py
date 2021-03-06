#!/usr/bin/python
# -*- coding: utf-8 -*-

# This file is part of edledit.
# Copyright (C) 2010 Stephane Bidoul
#
# edledit is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# edledit is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with edledit.  If not, see <http://www.gnu.org/licenses/>.

__version__ = "0.9"

import mimetypes
import os
from datetime import timedelta

from PyQt4 import QtCore, QtGui
from PyQt4.phonon import Phonon

import pyedl

from edledit_ui import Ui_MainWindow
from edledit_about_ui import Ui_AboutDialog
from edledit_license_ui import Ui_LicenseDialog

# initialize mimetypes database
mimetypes.init()


def tr(s):
    return unicode(QtGui.QApplication.translate("@default", s))


def timedelta2ms(td):
    return td.days*86400000 + td.seconds*1000 + td.microseconds//1000


def ms2timedelta(ms):
    return timedelta(milliseconds=ms)


class MainWindow(QtGui.QMainWindow):

    steps = [
        (40, tr("4 msec")),
        (200, tr("20 msec")),
        (500, tr("0.5 sec")),
        (2000, tr("2 sec")),
        (5000, tr("5 sec")),
        (20000, tr("20 sec")),
        (60000, tr("1 min")),
        (300000, tr("5 min")),
        (600000, tr("10 min")),
    ]

    defaultStepIndex = 7

    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.settings = QtCore.QSettings("bidoul.net", "edledit")

        # initialize media components
        self.mediaObject = self.ui.player.mediaObject()
        self.mediaObject.setTickInterval(200)
        self.mediaObject.stateChanged.connect(self.stateChanged)
        self.mediaObject.tick.connect(self.tick)
        self.ui.edlWidget.seek.connect(self.ui.player.seek)

        # add steps combo box and position widget to toolbar
        # (this apparently can't be done in the designer)
        self.ui.stepCombobox = QtGui.QComboBox(self.ui.toolBar)
        self.ui.stepLabel = QtGui.QLabel(tr(" Step : "), self.ui.toolBar)
        self.ui.timeEditCurrentTime = QtGui.QTimeEdit(self.ui.toolBar)
        self.ui.timeEditCurrentTime.setReadOnly(True)
        self.ui.timeEditCurrentTime.setButtonSymbols(
            QtGui.QAbstractSpinBox.NoButtons)
        self.ui.posLabel = QtGui.QLabel(tr(" Position : "), self.ui.toolBar)
        self.ui.timeEditCurrentTime.setDisplayFormat("HH:mm:ss.zzz")
        self.ui.toolBar.addWidget(self.ui.stepLabel)
        self.ui.toolBar.addWidget(self.ui.stepCombobox)
        self.ui.toolBar.addSeparator()
        self.ui.toolBar.addWidget(self.ui.posLabel)
        self.ui.toolBar.addWidget(self.ui.timeEditCurrentTime)

        # populate steps combo box
        for stepMs, stepText in self.steps:
            self.ui.stepCombobox.addItem(stepText)

        # initialize attributes
        self.loading = False
        self.movieFileName = None
        self.edlFileName = None
        self.edl = None
        self.edlDirty = False
        self.setStep(self.defaultStepIndex)

    # logic

    def loadEDL(self):
        assert self.movieFileName
        self.edlFileName = os.path.splitext(self.movieFileName)[0] + ".edl"
        if os.path.exists(self.edlFileName):
            self.edl = pyedl.load(open(self.edlFileName))
        else:
            self.edl = pyedl.EDL()
        self.edlDirty = False
        self.ui.edlWidget.setEDL(self.edl, self.ui.player.totalTime())
        self.ui.actionSaveEDL.setEnabled(True)
        self.ui.actionStartCut.setEnabled(True)
        self.ui.actionStopCut.setEnabled(True)
        self.ui.actionDeleteCut.setEnabled(True)
        self.refreshTitle()

    def saveEDL(self):
        assert self.edlFileName
        assert self.edl is not None
        self.edl.normalize(timedelta(milliseconds=self.ui.player.totalTime()))
        pyedl.dump(self.edl, open(self.edlFileName, "w"))
        self.edlChanged(dirty=False)

    def closeEDL(self):
        self.ui.actionPreviousCutBoundary.setEnabled(False)
        self.ui.actionNextCutBoundary.setEnabled(False)
        self.edlFileName = None
        self.edl = None
        self.edlDirty = False
        self.ui.edlWidget.resetEDL()
        self.ui.actionSaveEDL.setEnabled(False)
        self.ui.actionStartCut.setEnabled(False)
        self.ui.actionStopCut.setEnabled(False)
        self.ui.actionDeleteCut.setEnabled(False)
        self.refreshTitle()

    def play(self):
        if not self.ui.player.isPlaying():
            self.ui.player.play()
            self.ui.actionPlayPause.setChecked(True)

    def pause(self):
        if self.ui.player.isPlaying():
            self.ui.player.pause()
            self.ui.actionPlayPause.setChecked(False)
            self.tick()

    def getStep(self):
        stepIndex = self.ui.stepCombobox.currentIndex()
        return self.steps[stepIndex][0]

    def setStep(self, stepIndex):
        stepIndex = max(stepIndex, 0)
        stepIndex = min(stepIndex, len(self.steps)-1)
        self.ui.stepCombobox.setCurrentIndex(stepIndex)
        self.ui.actionDecreaseStep.setEnabled(stepIndex != 0)
        self.ui.actionIncreaseStep.setEnabled(stepIndex != len(self.steps)-1)

    def stepDown(self):
        stepIndex = self.ui.stepCombobox.currentIndex()
        self.setStep(stepIndex - 1)

    def stepUp(self):
        stepIndex = self.ui.stepCombobox.currentIndex()
        self.setStep(stepIndex + 1)

    def loadMovie(self, fileName):
        self.closeEDL()
        self.loading = True
        self.movieFileName = fileName
        self.ui.player.load(Phonon.MediaSource(self.movieFileName))

    def seekTo(self, pos):
        pos = max(pos, 0)
        pos = min(pos, self.ui.player.totalTime())
        self.ui.player.seek(pos)
        if not self.ui.player.isPlaying():
            self.tick()

    def seekStep(self, step):
        pos = self.ui.player.currentTime() + step
        self.seekTo(pos)

    def edlChanged(self, dirty):
        self.edlDirty = dirty
        self.ui.edlWidget.setEDL(self.edl, self.ui.player.totalTime())
        self.refreshTitle()

    def refreshTitle(self):
        if self.edlFileName:
            if self.edlDirty:
                star = "*"
            else:
                star = ""
            head, tail = os.path.split(os.path.abspath(self.edlFileName))
            self.setWindowTitle("%s%s (%s) - edledit" % (star, tail, head))
        else:
            self.setWindowTitle("edledit")

    # slots

    def closeEvent(self, event):
        if self.askSave():
            event.accept()
        else:
            event.ignore()

    def askSave(self):
        """ If needed, ask the user to save the current EDL

        return True is we can proceed, False is the user selected Cancel.
        """
        if not self.edlDirty:
            return True
        msgBox = QtGui.QMessageBox(self)
        msgBox.setIcon(QtGui.QMessageBox.Question)
        msgBox.setText(tr("The current EDL has been modified."))
        msgBox.setInformativeText(tr("Do you want to save your changes?"))
        msgBox.setStandardButtons(
            QtGui.QMessageBox.Save |
            QtGui.QMessageBox.Discard | QtGui.QMessageBox.Cancel)
        msgBox.setDefaultButton(QtGui.QMessageBox.Save)
        ret = msgBox.exec_()
        if ret == QtGui.QMessageBox.Save:
            self.saveEDL()
            return True
        elif ret == QtGui.QMessageBox.Discard:
            return True
        else:
            return False

    def stateChanged(self, newState, oldState):
        seekable = self.mediaObject.hasVideo() and self.mediaObject.isSeekable()
        self.ui.actionPlayPause.setEnabled(seekable)
        self.ui.actionNextCutBoundary.setEnabled(seekable)
        self.ui.actionPreviousCutBoundary.setEnabled(seekable)
        self.ui.actionSkipBackwards.setEnabled(seekable)
        self.ui.actionSkipForward.setEnabled(seekable)
        if newState == Phonon.StoppedState:
            if self.loading and oldState != Phonon.ErrorState:
                self.play()
        elif newState == Phonon.PlayingState:
            if self.loading:
                self.loading = False
                self.loadEDL()  # TODO quid if error while loading EDL
        elif newState == Phonon.ErrorState:
            if self.loading:
                QtGui.QMessageBox.critical(
                    self,
                    tr("Error loading movie file"),
                    self.mediaObject.errorString())
                self.loading = False
                self.mediaObject.stop()

    def tick(self, timeMs=None):
        if timeMs is None:
            if self.mediaObject.hasVideo():
                timeMs = self.ui.player.currentTime()
            else:
                timeMs = 0
        self.ui.timeEditCurrentTime.setTime(QtCore.QTime(0, 0).addMSecs(timeMs))
        self.ui.edlWidget.tick(timeMs)
        if self.edl:
            block = self.edl.findBlock(ms2timedelta(timeMs))
        else:
            block = None
        if block:
            self.ui.actionDeleteCut.setEnabled(True)
            self.ui.actionCutSetActionSkip.setEnabled(
                block.action != pyedl.ACTION_SKIP)
            self.ui.actionCutSetActionMute.setEnabled(
                block.action != pyedl.ACTION_MUTE)
        else:
            self.ui.actionDeleteCut.setEnabled(False)
            self.ui.actionCutSetActionSkip.setEnabled(False)
            self.ui.actionCutSetActionMute.setEnabled(False)

    def smartSeekBackwards(self):
        self.stepDown()
        if self.getStep() <= 5000:
            self.pause()
        self.seekStep(-self.getStep())

    def smartSeekForward(self):
        self.stepDown()
        if self.getStep() <= 5000:
            self.pause()
        self.seekStep(self.getStep())

    def seekForward(self):
        self.seekStep(self.getStep())

    def seekBackwards(self):
        self.seekStep(-self.getStep())

    def seekNextBoundary(self):
        # self.pause()
        t = ms2timedelta(self.ui.player.currentTime())
        t = self.edl.getNextBoundary(t)
        if t:
            self.seekTo(timedelta2ms(t))
        else:
            self.seekTo(self.ui.player.totalTime())

    def seekPrevBoundary(self):
        # self.pause()
        t = ms2timedelta(self.ui.player.currentTime())
        t = self.edl.getPrevBoundary(t)
        if t:
            self.seekTo(timedelta2ms(t))
        else:
            self.seekTo(0)

    def togglePlayPause(self):
        if not self.ui.player.isPlaying():
            self.play()
        else:
            self.pause()

    def cutStart(self):
        t = timedelta(milliseconds=self.ui.player.currentTime())
        self.edl.cutStart(t)
        self.edlChanged(dirty=True)

    def cutStop(self):
        t = timedelta(milliseconds=self.ui.player.currentTime())
        self.edl.cutStop(t)
        self.edlChanged(dirty=True)

    def cutDelete(self):
        t = timedelta(milliseconds=self.ui.player.currentTime())
        self.edl.deleteBlock(t)
        self.edlChanged(dirty=True)

    def cutSetAction(self, action):
        block = self.edl.findBlock(ms2timedelta(self.ui.player.currentTime()))
        if block is not None:
            block.action = action
            self.edlChanged(dirty=True)

    def cutSetActionSkip(self):
        self.cutSetAction(pyedl.ACTION_SKIP)

    def cutSetActionMute(self):
        self.cutSetAction(pyedl.ACTION_MUTE)

    def actionFileOpen(self):
        if not self.askSave():
            return
        # get video file extensions from mime types database
        exts = ["*" + ext for (ext, mt) in mimetypes.types_map.items()
                if mt.startswith("video/")]
        exts = " ".join(exts)
        lastFolder = self.settings.value("last-folder").toString()
        fileName = QtGui.QFileDialog.getOpenFileName(
            self, tr("Select movie file to open"), lastFolder,
            tr("All Movie Files (%s);;All Files (*.*)") % exts)
        if fileName:
            # unicode() to convert from QString
            fileName = unicode(fileName)
            # save directory so next getOpenFileName will be in same dir
            self.settings.setValue("last-folder", os.path.split(fileName)[0])
            self.loadMovie(fileName)

    def actionFileSaveEDL(self):
        self.saveEDL()

    def actionHelpAbout(self):
        AboutDialog(self).exec_()


class AboutDialog(QtGui.QDialog):

    def __init__(self, *args, **kwargs):
        QtGui.QDialog.__init__(self, *args, **kwargs)
        self.ui = Ui_AboutDialog()
        self.ui.setupUi(self)
        self.ui.labelNameVersion.setText("edledit %s" % __version__)

    def license(self):
        dlg = QtGui.QDialog(self)
        ui = Ui_LicenseDialog()
        ui.setupUi(dlg)
        dlg.exec_()


def run():
    import sys
    app = QtGui.QApplication(sys.argv)
    app.setApplicationName("edledit")

    # initialize QT translations
    qtTranslator = QtCore.QTranslator()
    qtTranslator.load(
        "qt_" + QtCore.QLocale.system().name(),
        QtCore.QLibraryInfo.location(QtCore.QLibraryInfo.TranslationsPath))
    app.installTranslator(qtTranslator)
    # initialize edledit translations from resource file
    edleditTranslator = QtCore.QTranslator()
    trPath = os.path.join(
        os.path.dirname(__file__),
        "translations", "edledit_")
    trPath = trPath + QtCore.QLocale.system().name()
    edleditTranslator.load(trPath)
    app.installTranslator(edleditTranslator)

    mainWindow = MainWindow()
    mainWindow.show()
    if len(sys.argv) == 2:
        fileName = sys.argv[1].decode(sys.getfilesystemencoding())
        mainWindow.loadMovie(fileName)

    sys.exit(app.exec_())

if __name__ == "__main__":
    run()
