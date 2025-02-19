import logging
from pathlib import Path

from PySide6.QtCore import (
    QFileSystemWatcher,
    QObject,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QMenu,
    QTreeWidget,
)

from datalad.utils import get_dataset_root

from .dataset_actions import add_dataset_actions_to_menu
from .fsbrowser_item import FSBrowserItem

lgr = logging.getLogger('datalad.gooey.fsbrowser')


class GooeyFilesystemBrowser(QObject):
    # TODO Establish ENUM for columns

    # FSBrowserItem
    item_requires_annotation = Signal(FSBrowserItem)
    # what is annotated, and the properties
    item_annotation_available = Signal(FSBrowserItem, dict)

    # DONE
    def __init__(self, app, path: Path, treewidget: QTreeWidget):
        super().__init__()

        tw = treewidget
        # TODO must setColumnNumber()

        self._app = app
        self._fswatcher = QFileSystemWatcher(parent=app)
        self.item_requires_annotation.connect(
            self._queue_item_for_annotation)
        # and connect the receiver for an annotation of an item in the
        # model
        # TODO
        self.item_annotation_available.connect(self._annotate_item)

        tw.setHeaderLabels(['Name', 'Type', 'State'])
        # established defined sorting order of the tree
        tw.sortItems(1, Qt.AscendingOrder)

        # establish the root item
        root = FSBrowserItem.from_path(path, children=False, parent=tw)
        # set the tooltip to the full path, otherwise only names are shown
        root.setToolTip(0, str(path))
        tw.addTopLevelItem(root)
        self._root_item = root

        tw.customContextMenuRequested.connect(
            self._custom_context_menu)

        self._tree = tw

        # whenever a treeview node is expanded, add the path to the fswatcher
        tw.itemExpanded.connect(self._watch_dir)
        # and also populate it with items for contained paths
        tw.itemExpanded.connect(self._populate_item)
        tw.itemCollapsed.connect(self._unwatch_dir)
        self._fswatcher.directoryChanged.connect(self._inspect_changed_dir)

        # items of directories to be annotated, populated by
        # _queue_item_for_annotation()
        self._annotation_queue = set()
        # msec
        self._annotation_timer_interval = 3000
        self._annotation_timer = QTimer(self)
        self._annotation_timer.timeout.connect(
            self._process_item_annotation_queue)
        self._annotation_timer.start(self._annotation_timer_interval)

    # DONE
    def _populate_item(self, item):
        if not item.childCount():
            # only parse, if there are no children yet
            FSBrowserItem.from_path(
                item.pathobj, root=False, children=True, include_files=True,
                parent=item)
            self._queue_item_for_annotation(item)

    # TODO consider @lru_cache
    # DONE
    def _get_item_from_path(self, path: Path):
        item = self._root_item
        if path == item.pathobj:
            return item
        # otherwise look for the item with the right name at the
        # respective level
        for p in path.relative_to(item.pathobj).parts:
            found = False
            for ci in range(item.childCount()):
                child = item.child(ci)
                if p == child.data(0, Qt.EditRole):
                    item = child
                    found = True
                    break
            if not found:
                raise ValueError(f'Cannot find item for {path}')
        return item

    def _queue_item_for_annotation(self, item):
        """This is not thread-safe"""
        self._annotation_queue.add(item)
        print('QUEUEDIR', item)

    def _process_item_annotation_queue(self):
        if not self._annotation_queue:
            return
        # there is stuff to annotate, make sure we do not trigger more
        # annotations while this one is running
        self._annotation_timer.stop()
        print("ANNOTATE!", len(self._annotation_queue))
        # TODO stuff could be optimized here: collapsing multiple
        # directories belonging to the same dataset into a single `status`
        # call...
        while self._annotation_queue:
            # process the queue in reverse order, assuming a user would be
            # interested in the last triggered directory first
            # (i.e., assumption is: expanding tree nodes one after
            # another, attention would be on the last expanded one, not the
            # first)
            item = self._annotation_queue.pop()
            ipath = item.pathobj
            dsroot = get_dataset_root(ipath)
            if dsroot is None:
                # no containing dataset, by definition everything is untracked
                for child in item.children_():
                    # get type, only annotate non-directory items
                    if child.datalad_type != 'directory':
                        self.item_annotation_available.emit(
                            child, dict(state='untracked'))
            else:
                # with have a containing dataset, run a datalad-status.
                # attach to the execution handler's result received signal
                # to route them this our own receiver
                self._app._cmdexec.result_received.connect(
                    self._status_result_receiver)
                # attach the handler that disconnects from the result signal
                self._app._cmdexec.execution_finished.connect(
                    self._disconnect_status_result_receiver)
                # trigger datalad-status execution
                # giving the target directory as a `path` argument should
                # avoid undesired recursion into subDIRECTORIES
                paths_to_investigate = [
                    c.pathobj.relative_to(dsroot)
                    for c in item.children_()
                    if c.datalad_type != 'directory'
                ]
                if paths_to_investigate:
                    # do not run, if there are no relevant paths to inspect
                    self._app.execute_dataladcmd.emit(
                        'status',
                        dict(dataset=dsroot, path=paths_to_investigate)
                    )

        # restart annotation watcher
        self._annotation_timer.start(self._annotation_timer_interval)

    def _status_result_receiver(self, res):
        if res.get('action') != 'status':
            # no what we are looking for
            return
        path = res.get('path')
        if path is None:
            # nothing that we could handle
            return
        state = res.get('state')
        if state is None:
            # nothing to show for
            return
        self.item_annotation_available.emit(
            self._get_item_from_path(Path(path)),
            dict(state=state),
        )

    def _annotate_item(self, item, props):
        if 'state' in props:
            state = props['state']
            prev_state = item.data(2, Qt.EditRole)
            if state != prev_state:
                item.setData(2, Qt.EditRole, state)
                item.emitDataChanged()

    # DONE
    def _disconnect_status_result_receiver(self, thread, cmdname, args):
        if cmdname != 'status':
            # no what we are looking for
            return
        # TODO come up with some kind of counter to verify when it is safe
        # to disconnect the result receiver
        # some status processes could be running close to forever
        print("DISCONNECT?", cmdname)

    # DONE
    def _watch_dir(self, item):
        path = str(item.pathobj)
        lgr.log(
            9,
            "GooeyFilesystemBrowser._watch_dir(%r) -> %r",
            path,
            self._fswatcher.addPath(path),
        )

    # DONE
    # https://github.com/datalad/datalad-gooey/issues/50
    def _unwatch_dir(self, item):
        path = str(item.pathobj)
        lgr.log(
            9,
            "GooeyFilesystemBrowser._unwatch_dir(%r) -> %r",
            path,
            self._fswatcher.removePath(path),
        )

    # DONE
    def _inspect_changed_dir(self, path: str):
        pathobj = Path(path)
        lgr.log(9, "GooeyFilesystemBrowser._inspect_changed_dir(%r)", pathobj)
        # we need to know the item in the tree corresponding
        # to the changed directory
        try:
            item = self._get_item_from_path(pathobj)
        except ValueError:
            # the changed dir has no (longer) a matching entry in the
            # tree model. make sure to take it off the watch list
            self._fswatcher.removePath(path)
            lgr.log(9, "_inspect_changed_dir() -> not in view (anymore), "
                       "removed from watcher")
            return

        parent = item.parent()
        if not pathobj.exists():
            if parent is None:
                # TODO we could have lost the root dir -> special action
                raise NotImplementedError
            parent.removeChild(item)
            lgr.log(8, "-> _inspect_changed_dir() -> item removed")

        # the modification is not a deletion of the watched dir itself.
        # get a new item with its immediate children, in order
        # to than compare the present to the new one(s): remove/add
        # as needed, update the existing node instances for the rest
        newitem = FSBrowserItem.from_path(
            pathobj, root=True, children=True, include_files=True,
            parent=None)

        item.update_from(newitem)
        lgr.log(9, "_inspect_changed_dir() -> updated tree items")

    # DONE
    def _custom_context_menu(self, onpoint):
        """Present a context menu for the item click in the directory browser
        """
        # get the tree item for the coordinate that received the
        # context menu request
        item = self._tree.itemAt(onpoint)
        if not item:
            # prevent context menus when the request did not actually
            # land on an item
            return
        # what kind of path is this item representing
        path_type = item.data(1, Qt.EditRole)
        if path_type is None:
            # we don't know what to do with this (but it also is not expected
            # to happen)
            return
        context = QMenu(parent=self._tree)
        if path_type == 'dataset':
            # we are not reusing the generic dataset actions menu
            #context.addMenu(self.get_widget('menuDataset'))
            # instead we generic a new one, with actions prepopulated
            # with the specific dataset path argument
            dsmenu = context.addMenu('Dataset commands')
            add_dataset_actions_to_menu(
                self._tree, self._app._cmdui.configure, dsmenu,
                dataset=item.pathobj)

        if not context.isEmpty():
            # present the menu at the clicked point
            context.exec(self._tree.viewport().mapToGlobal(onpoint))
