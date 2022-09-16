from pathlib import Path
from typing import Dict

from PySide6.QtCore import (
    Qt,
)
from PySide6.QtWidgets import (
    QTreeWidgetItem,
)

from .resource_provider import gooey_resources


class FSBrowserItem(QTreeWidgetItem):
    PathObjRole = Qt.UserRole + 765

    def __init__(self, path, parent=None):
        # DO NOT USE DIRECTLY, GO THROUGH from_lsdir_result()
        super().__init__(
            parent,
            type=QTreeWidgetItem.UserType + 145,
        )
        self.setData(0, FSBrowserItem.PathObjRole, path)
        self._child_lookup = None

    def __str__(self):
        return f'FSBrowserItem<{self.pathobj}>'

    @property
    def pathobj(self):
        p = self.data(0, FSBrowserItem.PathObjRole)
        if p is None:
            raise RuntimeError('TreeWidgetItem has no path set')
        return p

    @property
    def datalad_type(self):
        return self.data(1, Qt.EditRole)

    def data(self, column: int, role: int):
        if column == 0 and role in (Qt.DisplayRole, Qt.EditRole):
            # for now, we do not distinguish the two, maybe never will
            # but the default implementation also does this, so we match
            # behavior explicitly until we know better
            return self.pathobj.name
        # fall back on default implementation
        return super().data(column, role)

    def __getitem__(self, name: str):
        if self._child_lookup is None:
            self._child_lookup = {
                child.data(0, Qt.EditRole): child
                for child in self.children_()
            }
        return self._child_lookup.get(name)

    def _register_child(self, name, item):
        if self._child_lookup is None:
            self._child_lookup = {}
        self._child_lookup[name] = item

    def removeChild(self, item):
        super().removeChild(item)
        del self._child_lookup[item.pathobj.name]

    def children_(self):
        # get all pointers to children at once, other wise removing
        # one from the parent while the generator is running invalidates
        # the indices
        for c in [self.child(ci) for ci in range(self.childCount())]:
            yield c

    def update_from_status_result(self, res: Dict):
        state = res.get('state')
        if res.get('status') == 'error' and 'message' in res and state is None:
            # something went wrong, we got no state info, but we have a message
            state = res['message']

        state_icon = 'file-annex'
        if res.get('key'):
            state_icon = 'file-git'

        if state:
            self.setData(2, Qt.EditRole, state)
            icon = self._getIcon(state)
            if icon:
                self.setIcon(2, self._getIcon(state))

        type_ = res.get('type')
        if type_ == 'file':
            # get the right icon, fall back on 'file'
            self.setIcon(0, self._getIcon(state_icon))

        if type_:
            self.setData(1, Qt.EditRole, type_)

    def update_from_lsdir_result(self, res: Dict):
        # This sets
        # - type column
        # - child indicator
        # - icons TODO check which and how
        # - disabled-mode
        #
        # Resets
        # - state column for directories
        path_type = res['type']
        self.setData(1, Qt.EditRole, path_type)
        self._setItemIcons(res)
        if res.get('status') == 'error' \
                and res.get('message') == 'Permissions denied':
            # we cannot get info on it, reflect in UI
            self.setDisabled(True)
            # also prevent expansion if there are no children yet
            if not self.childCount():
                self.setChildIndicatorPolicy(
                    FSBrowserItem.DontShowIndicator)
            # END HERE
            return

        # ensure we are on
        self.setDisabled(False)

        if path_type in ('directory', 'dataset'):
            # show an expansion indiciator, even when we do not have
            # children in the item yet
            self.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

        if path_type == 'directory':
            # a regular directory with proper permissions has no state
            self.setData(2, Qt.EditRole, '')

    @classmethod
    def from_lsdir_result(cls, res: Dict, parent=None):
        path = Path(res['path'])
        item = FSBrowserItem(path, parent=parent)
        if hasattr(parent, '_register_child'):
            parent._register_child(path.name, item)
        item.update_from_lsdir_result(res)
        return item

    def _setItemIcons(self, res):
        # Set 'type' icon
        item_type = res['type']
        if item_type != 'file':
            icon = self._getIcon(item_type)
            if icon:
                self.setIcon(0, icon)
        # Set other icon types: TODO

    def _getIcon(self, item_type):
        """Gets icon associated with item type"""
        icon_mapping = {
            'dataset': 'dataset-closed',
            'directory': 'directory-closed',
            'file': 'file',
            'file-annex': 'file-annex',
            'file-git': 'file-git',
            # opportunistic guess?
            'symlink': 'file-annex',
            'untracked': 'untracked',
            'clean': 'clean',
            'modified': 'modified',
            'deleted': 'untracked',
            'unknown': 'untracked',
            'added': 'modified',
        }
        # TODO have a fallback icon, when we do not know a specific type
        # rather than crashing. Maybe a ?, maybe something blank?
        icon_name = icon_mapping.get(item_type, None)
        if icon_name:
            return gooey_resources.get_icon(icon_name)
