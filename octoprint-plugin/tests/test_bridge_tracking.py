import logging

from octoprint.events import Events

from octoprint_filamenthub_bridge import FilamentHubBridgePlugin


class FakeSettings:
    def __init__(self):
        self.values = {
            "snapshot": {
                "slots": [
                    {
                        "index": 0,
                        "spool": {"id": 41},
                    }
                ]
            },
            "active_slot": 0,
            "map_tools_to_slots": False,
            "outbox": [],
        }

    def get(self, path):
        return self.values.get(path[0])

    def get_boolean(self, path):
        return bool(self.get(path))

    def set(self, path, value):
        self.values[path[0]] = value

    def save(self):
        return None


class FakePrinter:
    def get_current_job(self):
        return {"file": {"name": "short.gcode", "path": "short.gcode"}}


class PrintingComm:
    def isPrinting(self):
        return True


def test_sent_gcode_starts_tracking_before_delayed_print_started_event():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._printer = FakePrinter()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    comm = PrintingComm()

    plugin.on_gcode_sent(comm, "sent", "M82", None, "M82")
    plugin.on_gcode_sent(comm, "sent", "G92 E0", None, "G92")
    plugin.on_gcode_sent(comm, "sent", "G1 X1 E200", None, "G1")

    assert plugin._tracker.used_length_by_slot == {0: 200.0}

    # OctoPrint dispatches PrintStarted asynchronously. It must not erase the
    # commands already observed by the synchronous sent-G-code hook.
    plugin._begin_print({"name": "short.gcode"})
    assert plugin._tracker.used_length_by_slot == {0: 200.0}

    plugin._finish_print("completed", {"time": 1.0})
    outbox = plugin._settings.get(["outbox"])
    assert len(outbox) == 1
    assert outbox[0]["items"] == [
        {"slot_index": 0, "spool_id": 41, "used_length_mm": 200.0}
    ]


def test_print_cancelled_queues_usage_as_cancelled():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._printer = FakePrinter()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    comm = PrintingComm()

    plugin.on_gcode_sent(comm, "sent", "M83", None, "M83")
    plugin.on_gcode_sent(comm, "sent", "G1 E12", None, "G1")
    plugin.on_event(Events.PRINT_CANCELLED, {"time": 3.0})

    outbox = plugin._settings.get(["outbox"])
    assert len(outbox) == 1
    assert outbox[0]["outcome"] == "cancelled"
    assert outbox[0]["items"][0]["used_length_mm"] == 12.0


def test_outbox_flush_preserves_event_appended_during_request():
    plugin = FilamentHubBridgePlugin()
    plugin._settings = FakeSettings()
    plugin._logger = logging.getLogger("filamenthub-bridge-test")
    first = {"event_id": "first", "items": [{"spool_id": 41}]}
    second = {"event_id": "second", "items": [{"spool_id": 42}]}
    plugin._settings.set(["outbox"], [first])
    sent = []

    def request(method, path, payload):
        sent.append(payload)
        if payload == first:
            plugin._settings.set(["outbox"], [first, second])
        return 200, {}, {"accepted": True}

    plugin._request = request
    plugin._flush_outbox()

    assert sent == [first, second]
    assert plugin._settings.get(["outbox"]) == []
