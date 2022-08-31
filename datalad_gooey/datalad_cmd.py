from concurrent.futures import ThreadPoolExecutor
import threading
from typing import (
    Dict,
    Tuple,
)

from PySide6.QtCore import (
    QObject,
    Signal,
    Slot,
)
# lazy import
dlapi = None


class GooeyDataladCmdExec(QObject):
    """Non-blocking execution of DataLad API commands

    and Qt-signal result reporting
    """
    # thread_id, cmdname, cmdargs/kwargs
    execution_started = Signal(str, str, tuple, dict)
    execution_finished = Signal(str, str, tuple, dict)
    result_received = Signal(dict)

    def __init__(self):
        super().__init__()

        self._threadpool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix='gooey_datalad_cmdexec',
            # some callable to start at each thread execution
            #initializer=self.
            #initargs=
        )
        self._futures = set()

    @Slot(str, tuple, dict)
    def execute(self, cmd: str,
                args: Tuple or None = None,
                kwargs: Dict or None = None):
        if args is None:
            args = tuple()
        if kwargs is None:
            kwargs = dict()

        global dlapi
        if dlapi is None:
            from datalad import api as dl
            dlapi = dl
        # right now, we have no use for the returned future, because result
        # communication and thread finishing are handled by emitting Qt signals
        self._threadpool.submit(
            self._cmdexec_thread,
            cmd,
            *args,
            **kwargs
        )

    def _cmdexec_thread(self, cmd, *args, **kwargs):
        """The code is executed in a worker thread"""
        print('EXECINTHREAD', cmd, args, kwargs)
        # get_ident() is an int, but in the future we might want to move
        # to PY3.8+ native thread IDs, so let's go with a string identifier
        # right away
        thread_id = str(threading.get_ident())
        self.execution_started.emit(
            thread_id,
            cmd,
            args,
            kwargs,
        )
        # get functor to execute, resolve name against full API
        cmd = getattr(dlapi, cmd)

        # enforce return_type='generator' to get the most responsive
        # any command could be
        kwargs['return_type'] = 'generator'
        for res in cmd(*args, **kwargs):
            self.result_received.emit(res)

        self.execution_finished.emit(
            thread_id,
            cmd,
            args,
            kwargs,
        )


