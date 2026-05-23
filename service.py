"""Windows service wrapper for TaskPlanner.

Usage (run as Administrator):
    python service.py install
    python service.py start
    python service.py stop
    python service.py remove
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
os.chdir(APP_DIR)
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "service.log"

_file_logger = logging.getLogger("taskplanner.service")
_file_logger.setLevel(logging.DEBUG)
_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_file_logger.addHandler(_handler)

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
except ImportError:
    print("pywin32 is required for Windows service support.")
    print("Install it with: pip install pywin32")
    sys.exit(1)


class TaskPlannerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "TaskPlanner"
    _svc_display_name_ = "TaskPlanner Scheduling Service"
    _svc_description_ = "Manages scheduled tasks and notifications for TaskPlanner."

    def __init__(self, args: list) -> None:
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._server_thread: threading.Thread | None = None

    def _log(self, msg: str, error: bool = False) -> None:
        if error:
            _file_logger.error(msg)
            servicemanager.LogErrorMsg(f"TaskPlanner: {msg}")
        else:
            _file_logger.info(msg)
            servicemanager.LogInfoMsg(f"TaskPlanner: {msg}")

    def SvcStop(self) -> None:
        self._log("Service stop requested")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self) -> None:
        self._log("Service starting")
        self._log(f"Working directory: {APP_DIR}")
        self._log(f"Python executable: {sys.executable}")
        self._log(f"Python version: {sys.version}")

        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )

        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()

        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
        self._log("Service stopped")

    def _run_server(self) -> None:
        try:
            if sys.stdout is None:
                sys.stdout = open(os.devnull, "w")
            if sys.stderr is None:
                sys.stderr = open(os.devnull, "w")

            self._log("Loading application...")
            from tp.main import app

            self._log("Starting uvicorn on 0.0.0.0:8200")

            import uvicorn
            uvicorn.run(
                "tp.main:app",
                host="0.0.0.0",
                port=8200,
                log_level="info",
            )
        except Exception:
            tb = traceback.format_exc()
            self._log(f"Server failed to start:\n{tb}", error=True)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(TaskPlannerService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(TaskPlannerService)
