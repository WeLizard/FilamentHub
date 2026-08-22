$(function () {
  function FilamentHubBridgeViewModel(parameters) {
    var self = this;
    self.loginState = parameters[0];
    self.paired = ko.observable(false);
    self.serverUrl = ko.observable("https://filamenthub.ru");
    self.pairingCode = ko.observable("");
    self.systemName = ko.observable("");
    self.systemKind = ko.observable("");
    self.slots = ko.observableArray([]);
    self.activeSlot = ko.observable(null);
    self.manualSlot = ko.observable(null);
    self.routingMode = ko.observable("manual");
    self.toolMappings = ko.observableArray([]);
    self.useCustomToolMapping = ko.observable(false);
    self.currentTool = ko.observable(null);
    self.unmappedTools = ko.observableArray([]);
    self.printing = ko.observable(false);
    self.outboxSize = ko.observable(0);
    self.lastSyncAt = ko.observable(null);
    self.lastError = ko.observable(null);
    self.busy = ko.observable(false);

    self.mappingRow = function (toolIndex, slotIndex) {
      return {
        toolIndex: ko.observable(String(toolIndex)),
        slotIndex: ko.observable(Number(slotIndex))
      };
    };
    self.automaticMappings = function () {
      return self.slots()
        .slice()
        .sort(function (left, right) { return Number(left.index) - Number(right.index); })
        .map(function (slot, toolIndex) {
          return self.mappingRow(toolIndex, slot.index);
        });
    };
    self.isAutomaticMapping = function (mappings) {
      var automatic = self.automaticMappings();
      if (mappings.length !== automatic.length) return false;
      return automatic.every(function (expected) {
        return mappings.some(function (actual) {
          return Number(ko.unwrap(actual.toolIndex)) === Number(ko.unwrap(expected.toolIndex)) &&
            Number(ko.unwrap(actual.slotIndex)) === Number(ko.unwrap(expected.slotIndex));
        });
      });
    };
    self.slotIdentity = function (slot) {
      if (slot && slot.label) return slot.label;
      var index = slot && Number.isFinite(Number(slot.index)) ? Number(slot.index) : 0;
      return "#" + (index + 1);
    };
    self.slotOptionText = function (slot) {
      var title = self.slotIdentity(slot);
      var spool = self.spoolTitle(slot);
      return spool ? (title + " — " + spool) : (title + " — empty");
    };
    self.spoolTitle = function (slot) {
      var spool = slot && slot.spool;
      if (!spool) return "";
      var title = [spool.brand, spool.name].filter(Boolean).join(" · ");
      return title || (spool.id ? ("#" + spool.id) : "—");
    };
    self.spoolMaterial = function (slot) {
      return slot && slot.spool && slot.spool.material_type
        ? slot.spool.material_type
        : "";
    };
    self.spoolRemaining = function (slot) {
      var remaining = slot && slot.spool
        ? Number(slot.spool.remaining_weight_g)
        : NaN;
      return Number.isFinite(remaining) && remaining >= 0
        ? (Math.round(remaining) + " g")
        : "";
    };
    self.mappedToolsForSlot = function (slot) {
      var slotIndex = Number(slot.index);
      return self.effectiveToolMappings()
        .filter(function (mapping) {
          return Number(ko.unwrap(mapping.slotIndex)) === slotIndex;
        })
        .map(function (mapping) { return "T" + ko.unwrap(mapping.toolIndex); })
        .join(", ");
    };

    self.assignedSlots = ko.pureComputed(function () {
      return self.slots().filter(function (slot) { return Boolean(slot.spool); });
    });
    self.isManualRouting = ko.pureComputed(function () {
      return self.routingMode() === "manual";
    });
    self.isToolRouting = ko.pureComputed(function () {
      return self.routingMode() === "tools";
    });
    self.effectiveToolMappings = ko.pureComputed(function () {
      return self.useCustomToolMapping()
        ? self.toolMappings()
        : self.automaticMappings();
    });
    self.automaticMappingText = ko.pureComputed(function () {
      var mappings = self.automaticMappings();
      if (!mappings.length) return "No FilamentHub slots are available.";
      var labels = mappings.map(function (mapping) {
        var slot = self.slots().find(function (candidate) {
          return Number(candidate.index) === Number(ko.unwrap(mapping.slotIndex));
        });
        return "T" + ko.unwrap(mapping.toolIndex) + " → " + self.slotIdentity(slot);
      });
      if (labels.length <= 4) return labels.join(", ");
      return labels.slice(0, 3).join(", ") + ", …, " + labels[labels.length - 1];
    });
    self.useCustomToolMapping.subscribe(function (enabled) {
      if (enabled && self.toolMappings().length === 0) {
        self.toolMappings(self.automaticMappings());
      }
    });
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
    self.currentToolText = ko.pureComputed(function () {
      if (!self.printing() || self.currentTool() === null) return "";
      return "Printing with T" + self.currentTool();
    });
    self.unmappedToolsText = ko.pureComputed(function () {
      var tools = self.unmappedTools();
      if (!tools.length) return "";
      return tools.map(function (tool) { return "T" + tool; }).join(", ") +
        " has no slot mapping. Its usage is not being assigned to a spool.";
    });

    self.applyState = function (state) {
      state = state || {};
      self.paired(Boolean(state.paired));
      self.serverUrl(state.server_url || self.serverUrl());
      var snapshot = state.snapshot || {};
      var slots = Array.isArray(snapshot.slots) ? snapshot.slots : [];
      self.systemName(snapshot.system_name || "");
      self.systemKind(snapshot.system_kind || "");
      self.slots(slots);
      self.activeSlot(state.active_slot === undefined ? null : state.active_slot);
      self.manualSlot(state.manual_slot === undefined ? null : state.manual_slot);
      self.routingMode(state.routing_mode === "tools" ? "tools" : "manual");
      var mappings = (state.tool_slot_map || []).map(function (mapping) {
        return self.mappingRow(mapping.tool_index, mapping.slot_index);
      });
      self.toolMappings(mappings);
      self.useCustomToolMapping(mappings.length > 0 && !self.isAutomaticMapping(mappings));
      self.currentTool(state.current_tool === undefined ? null : state.current_tool);
      self.unmappedTools(Array.isArray(state.unmapped_tools) ? state.unmapped_tools : []);
      self.printing(Boolean(state.printing));
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
      self.lastError(null);
      self.command({
        command: "pair",
        server_url: self.serverUrl(),
        pairing_code: self.pairingCode().trim().toUpperCase()
      }).done(function () { self.pairingCode(""); });
    };
    self.sync = function () { self.command({ command: "sync" }); };
    self.selectSlot = function (slot) {
      if (!self.isManualRouting()) return;
      self.command({ command: "select_slot", slot_index: slot.index });
    };
    self.addToolMapping = function () {
      if (!self.slots().length) return;
      var used = self.toolMappings().map(function (mapping) {
        return Number(ko.unwrap(mapping.toolIndex));
      });
      var toolIndex = 0;
      while (used.indexOf(toolIndex) !== -1) toolIndex += 1;
      var preferredSlot = self.slots().find(function (slot) {
        return Number(slot.index) === toolIndex;
      }) || self.slots()[0];
      self.toolMappings.push(self.mappingRow(toolIndex, preferredSlot.index));
    };
    self.removeToolMapping = function (mapping) {
      self.toolMappings.remove(mapping);
    };
    self.saveRouting = function () {
      var seen = {};
      var invalid = false;
      var sourceMappings = self.useCustomToolMapping()
        ? self.toolMappings()
        : self.automaticMappings();
      var mappings = sourceMappings.map(function (mapping) {
        var toolIndex = Number(ko.unwrap(mapping.toolIndex));
        var slotIndex = Number(ko.unwrap(mapping.slotIndex));
        if (!Number.isInteger(toolIndex) || toolIndex < 0 || toolIndex > 1023 ||
            !Number.isInteger(slotIndex) || seen[toolIndex]) {
          invalid = true;
        }
        seen[toolIndex] = true;
        return { tool_index: toolIndex, slot_index: slotIndex };
      });
      if (invalid) {
        self.lastError("Each T number must be a unique whole number between 0 and 1023.");
        return;
      }
      self.lastError(null);
      self.command({
        command: "set_routing",
        mode: self.routingMode(),
        tool_slot_map: mappings
      });
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
    elements: [
      "#tab_plugin_filamenthub_bridge",
      "#sidebar_plugin_filamenthub_bridge"
    ]
  });
});
