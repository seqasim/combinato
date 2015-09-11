#!/usr/bin/env python
"""
this file contains the code for the spike sorting GUI
"""
from __future__ import print_function, division, absolute_import
import sys
import os
from getpass import getuser
from time import strftime

from PyQt4.QtCore import *
from PyQt4.QtGui import *


from .ui_sorter import Ui_MainWindow

from .sort_widgets import  AllGroupsFigure, ComparisonFigure, GroupOverviewFigure
from .backend import Backend
from .load_joblist import PickJobList, GotoJob
from .picksession import PickSessionDialog
from .group_list_model import ClusterDelegate
from .basics import spikeDist

import numpy as np

from .. import options, TYPE_ART, TYPE_MU, TYPE_SU, TYPE_NO

imageSize = 260
stylesheet = 'QListView:focus { background-color: rgb(240, 255, 255)}'
DEBUG = options['Debug']
LOGFILENAME = 'css_gui_log.txt'


class SpikeSorter(QMainWindow, Ui_MainWindow):
    """
    main class
    """
    def __init__(self, parent=None, arg=None):
        super(SpikeSorter, self).__init__(parent)

        self.setupUi(self)
        self.backend = None
        self.groupOverviewFigure = GroupOverviewFigure(self.centralwidget)
        self.allGroupsFigureDirty = True

        self.oneGroupLayout.addWidget(self.groupOverviewFigure)

        self.allGroupsFigure = AllGroupsFigure(self.centralwidget)
        self.allGroupsFigure.fig.canvas.mpl_connect('button_press_event',
                                                    self.onclick)
        self.allGroupsLayout.addWidget(self.allGroupsFigure)
        self.groupsComparisonFigure = ComparisonFigure(self.centralwidget)
        self.compareFigureLayout.addWidget(self.groupsComparisonFigure)
        view = self.listView
        view.setViewMode(QListView.IconMode)
        view.setResizeMode(QListView.Adjust)
        view.setItemDelegate(ClusterDelegate(self))
        view.setStyleSheet(stylesheet)
        view.addAction(self.actionMakeArtifact)
        view.addAction(self.actionMarkCluster)

        self.allGroupsTab.addAction(self.actionAutoassign)

        for action in (self.actionMakeArtifact,
                       self.actionMarkCluster):

            action.setShortcutContext(Qt.WidgetShortcut)
        self.groupComboBox.addAction(self.actionNextGroup)
        self.actionNewGroup.triggered.connect(self.actionNewGroup_triggered)
        self.pushButtonSave.clicked.connect(self.save_one_group)

        self.groupComboBox.currentIndexChanged.\
            connect(self.updateListView)
        self.tabWidget.currentChanged.\
            connect(self.updateActiveTab)

        self.autoassignPushButton.clicked.\
            connect(self.on_actionAutoassign_triggered)

        self.multiRadioButton.toggled.connect(self.saveTypeMU)
        self.singleRadioButton.toggled.connect(self.saveTypeSU)
        self.artifactRadioButton.toggled.connect(self.saveTypeArti)

        self.actionOpen.triggered.connect(self.actionOpen_triggered)
        self.comparePlotpushButton.clicked.connect(self.compare_groups)

        self.actionOpenJobs.triggered.connect(self.actionOpenJobs_triggered)
        self.actionNextJob.triggered.connect(self.actionNextJob_triggered)
        self.actionMergeAll.triggered.connect(self.actionMergeAll_triggered)
        self.actionGotoJob.triggered.connect(self.actionGotoJob_triggered)

        if len(arg) > 1:
            self.basedir = os.path.dirname(arg)
        else:
            self.basedir = os.getcwd()

        self.logfid = open(LOGFILENAME, 'a')
        self.user = getuser()

    def save_one_group(self):
        """
        save a plot of one group
        """
        fout = QFileDialog.getSaveFileName(self,
                                           'Save as Image',
                                           os.getcwd(),
                                           'Images (*.jpg *.pdf *.png)')
        self.groupOverviewFigure.save_as_file(str(fout), dpi=200)

    def on_actionAutoassign_triggered(self):

        if self.backend is None:
            return
        elif self.backend.sessions is None:
            return

        groupName = str(self.groupComboBox.currentText())
        group = self.backend.sessions.groupsByName[groupName]
        print('Auto-assigning group {}'.format(group))

        if group == '':
            return

        indices = self.listView.selectedIndexes()
        if len(indices) == 0:
            return
        index = indices[0].row()

        selectedMean = group.clusters[index].meanspike
        means = dict()

        for name, group in self.backend.sessions.groupsByName.iteritems():
            if name not in ['Unassigned', 'Artifacts']:
                means[name] = np.array(group.meandata).mean(0)

        dist = np.inf
        minimizer = None

        for name, mean in means.iteritems():
            if name != groupName:
                d = spikeDist(mean, selectedMean)
                if d < dist:
                    dist = d
                    minimizer = name

        print('Moving to ' + minimizer + ', distance {:2f}'.format(dist))
        self.move(self.backend.sessions.groupsByName[minimizer])
        self.updateActiveTab()
        l = self.backend.sessions.groupsByName[minimizer].assignAxis.get_lines()
        l[-1].set_color('r')
        self.allGroupsFigure.draw()

    def onclick(self, event):

        if (event.inaxes is not None) and\
           (self.backend is not None) and\
           (self.backend.sessions is not None):
            num = int(event.inaxes.get_label())
            src = self.listView
            dst = self.backend.sessions.groupsById[num]
            self.move(dst, src)
            self.updateActiveTab()

    def actionOpen_triggered(self, checked, filename=None):
        if self.backend is not None:
            if self.backend.sessions is not None:
                if self.backend.sessions.dirty:
                    self.actionSave.trigger()

                    del self.backend
                    self.backend = None

        dialog = PickSessionDialog(self.basedir, self)

        if dialog.exec_():
            item = str(dialog.sessionList.selectedItems()[0].text()).split()
            folder = item[0]
            datafile = item[1]
            sortingfile = item[2]
            item = str(dialog.timesList.selectedItems()[0].text()).split()
            try:
                start_time_ms = int(item[1])/1000
                stop_time_ms = int(item[2])/1000
            except IndexError:
                start_time_ms = 0
                stop_time_ms = np.inf

            print('Opening {} {} {} ({} ms to {} ms)'.
                  format(folder, datafile, sortingfile,
                         start_time_ms, stop_time_ms))

            datapath = os.path.join(folder, datafile)
            sessionpath = os.path.join(folder, sortingfile)

            self.backend = Backend(datapath, sessionpath,
                                   start_time_ms, stop_time_ms)

            self.status_string = 'Datafile: {} Sorting: {}'.format(datafile,
                                                                   sortingfile)
            self.folderLabel.setText(self.status_string)
        else:
            return

        self.update_after_open()

    def open_job(self, job_to_open):
        """
        open a job from the list
        """
        if self.backend is not None:
            if self.backend.sessions is not None:
                if self.backend.sessions.dirty:
                    self.actionSave.trigger()

                    del self.backend
                    self.backend = None

        job = self.job_names[job_to_open]

        datapath = os.path.join(self.basedir, job)
        sessionpath = os.path.join(self.basedir, os.path.dirname(job),
                                   self.job_label)

        self.backend = Backend(datapath, sessionpath,
                               self.job_start_time_ms, self.job_stop_time_ms)
        self.current_job = job_to_open
        self.status_string = 'Job: {}/{} Datafile: {}\
             Sorting: {}'.format(self.current_job + 1,
                                 len(self.job_names),
                                 job, self.job_label)

        self.folderLabel.setText(self.status_string)
        self.update_after_open()

    def update_after_open(self):
        self.allGroupsFigureDirty = True
        self.actionNewGroup.setEnabled(True)

        sps = self.backend.sorting_manager.\
            get_samples_per_spike()

        t = (self.backend.sessions.start_time,
             self.backend.sessions.stop_time)

        thresholds = self.backend.get_thresholds()
        self.groupOverviewFigure.setOptions((0, sps),
                                            t,
                                            self.backend.sign,
                                            thresholds)

        self.updateGroupsList()
        self.updateActiveTab()

    def actionNextJob_triggered(self):
        """
        go to the next job
        """
        cj = self.current_job
        if cj + 1 < len(self.job_names):
            self.open_job(cj + 1)
        else:
            print('Last job open')
            return

    def actionGotoJob_triggered(self):
        if self.backend is not None:
            if self.backend.sessions is not None:
                if self.backend.sessions.dirty:
                    self.actionSave.trigger()

                    del self.backend
                    self.backend = None

        dialog = GotoJob(self.job_names, self)

        if dialog.exec_():
            item = str(dialog.joblist.selectedItems()[0].text())
            print(item)
            jobid = int(item.split()[0])
            print(jobid)
            self.open_job(jobid)

    def actionOpenJobs_triggered(self):
        """
        open a job list
        """
        if self.backend is not None:
            if self.backend.sessions is not None:
                if self.backend.sessions.dirty:
                    self.actionSave.trigger()

                    del self.backend
                    self.backend = None

        dialog = PickJobList(self.basedir, self)

        if dialog.exec_():
            jobfile = str(dialog.jobfileList.selectedItems()[0].text())
            with open(jobfile, 'r') as fid:
                jobs = [line.strip() for line in fid.readlines()]
            fid.close()

            label = str(dialog.labelList.selectedItems()[0].text())

            item = str(dialog.timesList.selectedItems()[0].text()).split()
            try:
                start_time_ms = int(item[1])/1000
                stop_time_ms = int(item[2])/1000
            except IndexError:
                start_time_ms = 0
                stop_time_ms = np.inf

            # store info for later loading
            self.job_names = jobs
            self.job_label = label
            self.job_start_time_ms = start_time_ms
            self.job_stop_time_ms = stop_time_ms
            job_to_open = 0

            print('Loaded {} jobs from {} {} ({} ms to {} ms)'.
                  format(len(jobs), self.basedir, jobfile,
                         start_time_ms, stop_time_ms))

            self.open_job(job_to_open)

    def actionNewGroup_triggered(self):
        if self.backend.sessions is None:
            return

        self.backend.sessions.newGroup()
        oldtext = self.groupComboBox.currentText()
        self.updateGroupsList(oldtext)
        self.allGroupsFigureDirty = True
        self.updateActiveTab()

    def actionSetTime_triggered(self, checked):
        if self.backend is None:
            return

        dialog = PickTimeDialog(self)

        if dialog.exec_():
            item = [str(item.text()) for
                    item in dialog.widget.selectedItems()][0]
            start, _, stop, fname = item.split()
            print(start, stop, fname[1:-2])
            start, stop = [int(x)/1000 for x in (start, stop)]
            self.backend.set_sign_start_stop('pos', start, stop)

    def actionSelectSession_triggered(self, checked):

        if self.backend is None:
            return

        if self.backend.sessions is not None:
            if self.backend.sessions.dirty:
                self.actionSave.trigger()

        dialog = PickSessionDialog(self)

        if dialog.exec_():
            item = [str(item.text()) for
                    item in dialog.widget.selectedItems()][0]
            # print('Opening ' + item)
            self.backend.open_sessions(item)

        else:
            return

        # self.sessionLabel.setText(text)

        self.allGroupsFigureDirty = True
        self.actionNewGroup.setEnabled(True)
        x = self.backend.sorting_manager.\
            get_samples_per_spike()
        # total time in seconds
        t = (self.backend.sessions.start_time,
             self.backend.sessions.stop_time)

        # wrong place, should be executed only once!
        self.groupOverviewFigure.setOptions((0, x), t,
                                            self.backend.sign)

        self.updateGroupsList()
        self.updateActiveTab()

    def actionMergeAll_triggered(self):
        """
        move all clusters to the first group
        """
        groups = self.backend.sessions.groupsByName
        names = sorted(groups.keys())
        if len(names) <= 3:
            print('Nothing to move, only groups: {}'.format(names))
            return

        target = names[0]
        print('Moving everything to group {}'.format(target))

        for name in names[1:]:
            try:
                int(name)
                self.merge_groups(name, target)
            except ValueError:
                print('not moving {}'.format(name))

    def merge_groups(self, src, tgt):
        """
        merge two groups
        """
        groups = self.backend.sessions.groupsByName
        clusters = groups[src].removeClusters()
        groups[tgt].addClusters(clusters)
        self.backend.sessions.dirty = True
        self.listView.reset()
        self.updateActiveTab()

    def compare_groups(self):
        group1name = str(self.groupOnecomboBox.currentText())
        group2name = str(self.groupTwoComboBox.currentText())

        group1 = self.backend.sessions.groupsByName[group1name]
        group2 = self.backend.sessions.groupsByName[group2name]

        self.groupsComparisonFigure.xcorr(group1, group2)

    @pyqtSignature("")
    def on_actionSave_triggered(self):
        msgBox = QMessageBox()
        msgBox.setText("Save changes to current session?")
        msgBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msgBox.setDefaultButton(QMessageBox.Yes)
        ret = msgBox.exec_()
        if ret == QMessageBox.Yes:
            self.backend.sessions.save()
            now = strftime('%Y-%m-%d_%H-%M-%S')
            self.logfid.write('{} {} saved {}\n'.format(now, self.user,
                                                        self.status_string))
            self.backend.sessions.dirty = False

    @pyqtSignature("")
    def on_actionMarkCluster_triggered(self):

        name = self.tabWidget.currentWidget().objectName()
        indexes = self.listView.selectedIndexes()
        if len(indexes) == 0:
            return
        index = indexes[0].row()

        groupName = str(self.groupComboBox.currentText())
        if groupName == '':
            return

        if name == 'oneGroupTab':
            group = self.backend.sessions.groupsByName[groupName]
            clusterdata = np.diff(group.clusters[index].times)
            clusterdata = clusterdata[clusterdata <
                                      options['compute_isi_upto_ms']]
            self.groupOverviewFigure.mark(index, clusterdata)

        elif name == 'allGroupsTab':
            self.allGroupsFigure.mark(groupName, index)

    @pyqtSignature("")
    def on_actionMakeArtifact_triggered(self):
        self.move(self.backend.sessions.groupsByName['Artifacts'])
        self.updateGroupInfo()
        self.updateActiveTab()

    @pyqtSignature("")
    def on_actionNextGroup_triggered(self):
        """
        rotate through groups
        """
        ngroups = len(self.backend.sessions.groupsByName)
        if self.backend is not None:
            index = self.groupComboBox.currentIndex()
            if index + 1 < ngroups:
                self.groupComboBox.setCurrentIndex(index + 1)
            elif index + 1 == ngroups:
                self.groupComboBox.setCurrentIndex(0)

    def updateListView(self, e):
        index = str(self.groupComboBox.currentText())
        if index == '':
            return
        model = self.backend.sessions.groupsByName[index]
        self.listView.setModel(model)
        self.listView.selectionModel().currentChanged.\
            connect(self.on_actionMarkCluster_triggered)
        self.setRadioButtons(index)
        self.updateActiveTab()

    def setRadioButtons(self, index):
        model = self.backend.sessions.groupsByName[index]
        group_type = model.group_type
        if group_type == TYPE_MU:
            button = self.multiRadioButton
        elif group_type in (TYPE_ART, TYPE_NO):
            button = self.artifactRadioButton
        elif group_type == TYPE_SU:
            button = self.singleRadioButton
        else:
            raise Warning('Type not defined')

        button.setChecked(True)

    def save_type(self, new_type):
        index = str(self.groupComboBox.currentText())
        model = self.backend.sessions.groupsByName[index]
        model.group_type = new_type
        self.backend.sessions.dirty = True
        self.allGroupsFigureDirty = True
        self.updateActiveTab()

    def saveTypeMU(self, checked):
        """
        dispatch
        """
        if checked:
            self.save_type(TYPE_MU)

    def saveTypeSU(self, checked):
        """
        dispatch
        """
        if checked:
            self.save_type(TYPE_SU)

    def saveTypeArti(self, checked):
        """
        dispatch
        """
        if checked:
            self.save_type(TYPE_ART)

    def move(self, dst, src=None):
        self.backend.sessions.dirty = True
        if src is None:
            src = self.listView
        indexes = src.selectedIndexes()

        for index in indexes:
            cl = src.model().popCluster(index.row())
            dst.addCluster(cl)

        for obj in (src, dst):
            obj.reset()

        self.updateGroupInfo()

    def updateGroupsList(self, oldtext=None):
        groupsById = self.backend.sessions.groupsById
        box = self.groupComboBox
        box.clear()
        index = 0
        setindex = None
        for group in sorted(groupsById.keys()):
            name = groupsById[group].name
            box.addItem(name)
            if name == oldtext:
                setindex = index
            index += 1

        if setindex is not None:
            box.setCurrentIndex(setindex)

        box.setEnabled(True)

    def updateActiveTab(self):

        current = self.tabWidget.currentWidget().objectName()

        if current == 'allGroupsTab':
            self.updateAssignPlot()

        elif current == 'oneGroupTab':
            self.updateGroupInfo()

        elif current == 'compareTab':
            self.updateCompareTab()

    def updateCompareTab(self):
        groupsById = self.backend.sessions.groupsById
        box1 = self.groupOnecomboBox
        box2 = self.groupTwoComboBox
        boxes = (box1, box2)
        for box in boxes:
            box.clear()

        for group in sorted(groupsById.keys()):
            for box in boxes:
                name = groupsById[group].name
                box.addItem(name)
                box.setEnabled(True)

    def updateGroupInfo(self):

        groupName = str(self.groupComboBox.currentText())
        if groupName == '':
            return
        group = self.backend.sessions.groupsByName[groupName]
        self.groupOverviewFigure.updateInfo(group)

    def updateAssignPlot(self):
        """
        make sure plot with all mean spikes is up-to-date
        """

        # The speed could still be improved in this function
        if (self.backend is None) or\
           (self.backend.sessions is None):
            return

        session = self.backend.sessions

        index = []

        for name, group in session.groupsById.items():
            if group.group_type not in [TYPE_ART, TYPE_NO]:
                index.append(name)

        index.sort()
        print(index)

        if self.allGroupsFigureDirty:
            self.allGroupsFigure.\
                addAxes(self.backend.x, session, index)
            self.allGroupsFigureDirty = False
        else:
            self.allGroupsFigure.updateInfo(index)


def main():
    """
    start the qt app
    """
    app = QApplication(sys.argv)
    app.setStyle('gtk')
    win = SpikeSorter(parent=None, arg=sys.argv)
    win.setWindowTitle('Combinato Spike Sorter')
    win.showMaximized()
    app.exec_()