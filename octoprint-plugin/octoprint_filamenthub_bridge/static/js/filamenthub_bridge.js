$(function () {
  function FilamentHubBridgeViewModel(parameters) {
    var self = this;
    self.loginState = parameters[0];
    self.paired = ko.observable(false);
    self.serverUrl = ko.observable("https://filamenthub.ru");
    self.pairingCode = ko.observable("");
    self.slots = ko.observableArray([]);
    self.activeSlot = ko.observable(null);
    self.mapToolsToSlots = ko.observable(false);
    self.outboxSize = ko.observable(0);
    self.lastSyncAt = ko.observable(null);
    self.lastError = ko.observable(null);
    self.busy = ko.observable(false);

    self.statusText = ko.pureComputed(function () {
      if (!self.paired()) return "Not connected";
      if (self.lastError()) return "Needs attention";
      return "Connected";
    });
    self.statusClass = ko.pureComputed(function () {
      if (!self.paired()) return "idle";
      return self.lastError() ? "error" : "connected";
    });
    self.lastSyncText = ko.pureComputed(function () {
      if (!self.lastSyncAt()) return "Not synchronized yet";
      return "Last synchronization: " + new Date(self.lastSyncAt()).toLocaleString();
    });

    self.applyState = function (state) {
      state = state || {};
      self.paired(Boolean(state.paired));
      self.serverUrl(state.server_url || self.serverUrl());
      self.slots((state.snapshot && state.snapshot.slots) || []);
      self.activeSlot(state.active_slot === undefined ? null : state.active_slot);
      self.mapToolsToSlots(Boolean(state.map_tools_to_slots));
      self.outboxSize(state.outbox_size || 0);
      self.lastSyncAt(state.last_sync_at || null);
      self.lastError(state.last_error || null);
    };

    self.command = function (payload) {
      self.busy(true);
      return OctoPrint.simpleApiCommand("filamenthub_bridge", payload.command, payload)
        .done(self.applyState)
        .fail(function (xhr) {
          var response = xhr.responseJSON || {};
          self.lastError(response.error || "The Bridge request failed.");
        })
        .always(function () { self.busy(false); });
    };

    self.pair = function () {
      self.command({
        command: "pair",
        server_url: self.serverUrl(),
        pairing_code: self.pairingCode()
      }).done(function () { self.pairingCode(""); });
    };
    self.sync = function () { self.command({ command: "sync" }); };
    self.selectSlot = function (slot) {
      self.command({ command: "select_slot", slot_index: slot.index });
    };
    self.saveMappingMode = function () {
      self.command({
        command: "set_mapping_mode",
        map_tools_to_slots: self.mapToolsToSlots()
      });
      return true;
    };
    self.unpair = function () {
      if (confirm("Disconnect this OctoPrint from FilamentHub? Pending events stay local.")) {
        self.command({ command: "unpair" });
      }
    };
    self.onBeforeBinding = function () {
      OctoPrint.simpleApiGet("filamenthub_bridge").done(self.applyState);
    };
    self.onDataUpdaterPluginMessage = function (plugin, data) {
      if (plugin === "filamenthub_bridge") self.applyState(data);
    };
  }

  OCTOPRINT_VIEWMODELS.push({
    construct: FilamentHubBridgeViewModel,
    dependencies: ["loginStateViewModel"],
    elements: ["#tab_plugin_filamenthub_bridge"]
  });
});
