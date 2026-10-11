"""KilnScheduler daemon: queue of firings, supervision loop and the /status API on port 7410.

Registered as the KilnScheduler task on studio-srv with an unlimited execution time
limit (the task runner default of 72 hours would kill it).
"""
import argparse
import json
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import firing_log
from .controller import ControllerDriver
from .profile_loader import load_profile

STATUS_PORT = 7410


class KilnSchedulerService:
    """Supervises kilns; the controllers execute programs on their own."""

    def __init__(self, db_path: str, drivers: dict[str, ControllerDriver]):
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.drivers = drivers
        self.active: dict[str, dict] = {}
        self.adopted = False

    def start_firing(self, profile_path: str) -> int:
        """Load and validate a profile, send it to the controller and start logging."""
        prof = load_profile(profile_path)
        driver = self.drivers[prof["kiln"]]
        driver.load_program(prof["segments"])
        fid = firing_log.start_firing(self.db, prof["kiln"], prof["name"])
        self.active[prof["kiln"]] = {"firing_id": fid, "profile": prof["name"]}
        return fid

    def adopt_running(self) -> None:
        """After a restart, re-attach to firings that are still running on controllers.

        Used by ``--adopt``; it never reloads a program, so a firing survives a restart.
        """
        for kiln_id, driver in self.drivers.items():
            if driver.is_running():
                row = self.db.execute(
                    "SELECT id, profile FROM firings WHERE kiln_id=? AND ended_utc IS NULL "
                    "ORDER BY id DESC LIMIT 1", (kiln_id,)).fetchone()
                if row:
                    self.active[kiln_id] = {"firing_id": row[0], "profile": row[1]}
                    self.adopted = True

    def status(self) -> dict:
        """Payload for GET /status."""
        return {"ok": True, "firing_active": bool(self.active), "active": self.active,
                "adopted": self.adopted}

    def run_forever(self) -> None:
        """Main supervision loop: log readings, close finished firings."""
        while True:
            for kiln_id, info in list(self.active.items()):
                driver = self.drivers[kiln_id]
                firing_log.log_reading(self.db, info["firing_id"], 1, driver.read_temp())
                if not driver.is_running():
                    firing_log.end_firing(self.db, info["firing_id"], "complete")
                    del self.active[kiln_id]
            time.sleep(60)


def make_handler(service: KilnSchedulerService):
    """Build the HTTP handler class bound to a service instance."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/status":
                self.send_error(404)
                return
            body = json.dumps(service.status()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
    return Handler


def main() -> None:
    """Start the daemon; ``--adopt`` re-attaches to running firings."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--adopt", action="store_true")
    ap.add_argument("--db", default="D:/emberline/data/firings.db")
    args = ap.parse_args()
    drivers = {"k1": ControllerDriver("k1", "COM3"), "k2": ControllerDriver("k2", "COM4"),
               "k3": ControllerDriver("k3", "k3-ctl:502")}
    service = KilnSchedulerService(args.db, drivers)
    if args.adopt:
        service.adopt_running()
    threading.Thread(target=HTTPServer(("0.0.0.0", STATUS_PORT), make_handler(service)).serve_forever,
                     daemon=True).start()
    service.run_forever()


if __name__ == "__main__":
    main()
