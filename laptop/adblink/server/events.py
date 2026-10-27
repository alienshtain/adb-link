"""Event queue the phone long-polls (clipboard / notification pushes)."""
from __future__ import annotations

import threading
import time


# ----------------------------------------------------------------------------- events

class Events:
    def __init__(self):
        self.cond = threading.Condition()
        self.items = []
        self.last = 0

    def add(self, ev: dict):
        with self.cond:
            self.last += 1
            ev["id"] = self.last
            self.items.append(ev)
            self.items = self.items[-200:]
            self.cond.notify_all()

    def wait(self, after: int, wait: float):
        deadline = time.time() + wait
        with self.cond:
            while True:
                if after > self.last:
                    return self.last, []
                new = [e for e in self.items if e["id"] > after]
                left = deadline - time.time()
                if new or left <= 0:
                    return self.last, new
                self.cond.wait(min(1.0, left))


EVENTS = Events()
