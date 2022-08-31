import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication,
    QPlainTextEdit,
    QTreeView,
)
from PySide6.QtCore import (
    Qt,
    Slot,
)
from PySide6.QtGui import (
    QAction,
)

from datalad import cfg as dlcfg
import datalad.ui as dlui

from .fsview_model import (
    DataladTree,
    DataladTreeModel,
)
from .utils import load_ui
from .datalad_ui import GooeyUI


class GooeyApp:
    # Mapping of key widget names used in the main window to their widget
    # classes.  This mapping is used (and needs to be kept up-to-date) to look
    # up widget (e.g. to connect their signals/slots)
    _main_window_widgets = {
        'actionRun_stuff': QAction,
        'filesystemViewer': QTreeView,
        'logViewer': QPlainTextEdit,
    }

    def __init__(self, path: Path = None):
        # bend datalad to our needs
        # we cannot handle ANSI coloring
        dlcfg.set('datalad.ui.color', 'off', scope='override', force=True)

        # set default path
        if not path:
            path = Path.cwd()

        self._path = path
        self._main_window = None

        # setup UI
        dbrowser = self.get_widget('filesystemViewer')
        dmodel = DataladTreeModel()
        dmodel.set_tree(DataladTree(path))
        dbrowser.setModel(dmodel)
        # established defined sorting order of the tree, and sync it
        # with the widget sorting indicator state
        dbrowser.sortByColumn(1, Qt.AscendingOrder)

        # demo signal/slot connctions
        dbrowser.clicked.connect(clicked)
        dbrowser.doubleClicked.connect(doubleclicked)
        dbrowser.activated.connect(activated)
        dbrowser.pressed.connect(pressed)
        dbrowser.customContextMenuRequested.connect(contextrequest)

        # remember what backend was in use
        self._prev_ui_backend = dlui.ui.backend
        # ask datalad to use our UI
        # looks silly with the uiuiuiuiui, but these are the real names ;-)
        dlui.KNOWN_BACKENDS['gooey'] = GooeyUI
        dlui.ui.set_backend('gooey')
        dlui.ui.ui.set_app(self)

        # demo action to execute things for dev-purposes
        self.get_widget('actionRun_stuff').triggered.connect(self.run_stuff)

    def deinit(self):
        dlui.ui.set_backend(self._prev_ui_backend)

    #@cached_property not available for PY3.7
    @property
    def main_window(self):
        if not self._main_window:
            self._main_window = load_ui('main_window')
        return self._main_window

    def get_widget(self, name):
        wgt_cls = GooeyApp._main_window_widgets.get(name)
        if not wgt_cls:
            raise ValueError(f"Unknown widget {name}")
        wgt = self.main_window.findChild(wgt_cls, name=name)
        if not wgt:
            # if this happens, our internal _widgets is out of sync
            # with the UI declaration
            raise RuntimeError(
                f"Could not locate widget {name} ({wgt_cls.__name__})")
        return wgt

    @Slot(bool)
    def run_stuff(self, *args, **kwargs):
        print('BAMM')

    @property
    def rootpath(self):
        return self._path


def clicked(*args, **kwargs):
    print(f'clicked {args!r} {kwargs!r}')


def doubleclicked(*args, **kwargs):
    print(f'doubleclicked {args!r} {kwargs!r}')


def activated(*args, **kwargs):
    print(f'activated {args!r} {kwargs!r}')


def pressed(*args, **kwargs):
    print(f'pressed {args!r} {kwargs!r}')


def contextrequest(*args, **kwargs):
    print(f'contextrequest {args!r} {kwargs!r}')


import threading

# demo threaded message generator
class MyThread (threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        from time import sleep
        sleep(1)
        print(
            "ANSWER IN THREAD:",
            dlui.ui.question(
                'Long explanation what is the desired input here, really hoping that it would wrap, but it does not seems to be the case here',
                title=f'What do you do?',
                choices=None, default='mydefault', hidden=True,
                repeat=None)
        )
        print(
            "ANSWER IN THREAD:",
            dlui.ui.question(
                'Terse',
                title=f'What do you do?',
                choices=['Peter', 'Paul', 'Mary'],
                #default='Stan',
                hidden=False,
                repeat=None)
        )
        #for i in range(100):
        #    sleep(1)
        #    dlui.ui.message(f'mike{i}\n space\n  more space\n')


def main():
    qtapp = QApplication(sys.argv)
    gooey = GooeyApp()
    gooey.main_window.show()

    # let a command run to have content appear in the console log
    # uncomment for demo
    thread = MyThread().start()

    sys.exit(qtapp.exec())
