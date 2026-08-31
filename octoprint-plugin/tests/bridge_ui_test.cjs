const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const requests = [];
const context = vm.createContext({
  setTimeout, clearTimeout,
  gettext: text => text,
  $: callback => callback(),
  OCTOPRINT_VIEWMODELS: [],
  OctoPrint: {
    simpleApiCommand(plugin, command, payload) {
      assert.equal(plugin, "filamenthub_bridge");
      const callbacks = { done: [], fail: [], always: [] };
      const deferred = {};
      for (const kind of Object.keys(callbacks)) {
        deferred[kind] = callback => { callbacks[kind].push(callback); return deferred; };
      }
      requests.push({
        command, payload,
        resolve(state) { callbacks.done.forEach(fn => fn(state)); callbacks.always.forEach(fn => fn()); },
        reject(error) { callbacks.fail.forEach(fn => fn({ responseJSON: error })); callbacks.always.forEach(fn => fn()); }
      });
      return deferred;
    }
  }
});
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), context);
vm.runInContext(fs.readFileSync(process.argv[3], "utf8"), context);
const model = new context.OCTOPRINT_VIEWMODELS[0].construct([{}]);
const assigned = { index: 0, material_slot_id: 17, spool: { id: 41 } };
const empty = { index: 1, material_slot_id: 18, spool: null };
const state = (slots, mode = "manual") => ({
  paired: true, active_slot: 0, manual_slot: 0, routing_mode: mode, snapshot: { slots }
});
model.applyState(state([assigned, empty]));
assert.equal(model.sidebarSlots().length, 1);
assert.equal(model.emptySlotCount(), 1);
model.showEmptySlots(true);
assert.equal(model.sidebarSlots().length, 2);
model.showEmptySlots(false);

// Opening or cancelling the editor must not select a slot or write an assignment.
model.openSidebarSpoolPicker(assigned);
assert.equal(model.spoolPickerSurface(), "sidebar");
assert.equal(model.editingSlotId(), 17);
assert.equal(requests.length, 1);
assert.equal(requests[0].command, "search_spools");
model.selectSlot(empty);
model.openSpoolPicker(empty);
assert.equal(requests.length, 1, "busy editor blocks competing slot actions");
requests[0].resolve({ ...state([assigned, empty]), spool_options: { items: [{ id: 42 }], next_offset: 1 } });
assert.equal(model.spoolOptions().length, 1);
assert.equal(model.nextSpoolOffset(), 1);
model.cancelSpoolPicker();
assert.equal(model.spoolPickerSurface(), null);
assert.equal(model.editingSlot(), null);
assert.equal(requests.length, 1);

// Enter uses the current input even before Knockout's deferred text update.
model.openSidebarSpoolPicker(assigned);
requests.at(-1).resolve({ ...state([assigned, empty]), spool_options: { items: [] } });
let prevented = false;
model.onSpoolSearchKeydown(null, {
  key: "Enter", target: { value: "Violet" },
  preventDefault() { prevented = true; }
});
assert.equal(prevented, true);
assert.equal(requests.at(-1).payload.query, "Violet");
assert.equal(requests.at(-1).payload.offset, 0);
requests.at(-1).resolve({ ...state([assigned, empty]), spool_options: { items: [{ id: 42 }] } });
assert.equal(model.onSpoolSearchKeydown(null, { key: "a" }), true);
model.cancelSpoolPicker();

// Both surfaces share one editor, including pagination and conflict/retry handling.
model.openSpoolPicker(empty);
requests.at(-1).resolve({ ...state([assigned, empty]), spool_options: { items: [{ id: 42 }], next_offset: 1 } });
assert.equal(model.spoolPickerSurface(), "tab");
model.searchSpools(false);
assert.equal(requests.at(-1).payload.offset, 1);
requests.at(-1).resolve({ ...state([assigned, empty]), spool_options: { items: [{ id: 43 }], next_offset: null } });
assert.equal(model.spoolOptions().length, 2);
model.openSidebarSpoolPicker(empty);
requests.at(-1).resolve({ ...state([assigned, empty]), spool_options: { items: [{ id: 42 }] } });
model.selectedSpoolId(42);
model.assignSelectedSpool();
assert.equal(requests.at(-1).command, "assign_spool");
assert.equal(requests.at(-1).payload.material_slot_id, 18);
assert.equal(requests.at(-1).payload.spool_id, 42);
requests.at(-1).reject({ error: "Assignment changed. Try again.", state: state([assigned, empty]) });
assert.equal(model.spoolPickerSurface(), "sidebar");
assert.equal(model.busy(), false);
assert.equal(model.lastError(), "Assignment changed. Try again.");
model.assignSelectedSpool();
requests.at(-1).resolve(state([assigned, { ...empty, spool: { id: 42 } }]));
assert.equal(model.editingSlot(), null);
assert.equal(model.sidebarSlots().length, 2);
assert.equal(model.activeSlot(), 0);

// Removing the last spool leaves empty slots reachable without changing routing.
model.applyState(state([assigned], "tools"));
model.openSidebarSpoolPicker(assigned);
requests.at(-1).resolve({ ...state([assigned], "tools"), spool_options: { items: [] } });
model.clearSpoolAssignment();
assert.equal(requests.at(-1).payload.spool_id, null);
requests.at(-1).resolve(state([{ ...assigned, spool: null }], "tools"));
assert.equal(model.sidebarSlots().length, 1);
assert.equal(model.sidebarSlots()[0].spool, null);
assert.equal(model.isToolRouting(), true);
const beforeSelect = requests.length;
model.selectSlot(model.sidebarSlots()[0]);
assert.equal(requests.length, beforeSelect);
model.openSidebarSpoolPicker(model.sidebarSlots()[0]);
assert.equal(requests.at(-1).command, "search_spools");
requests.at(-1).resolve(state([], "tools"));
assert.equal(model.editingSlot(), null);
assert.equal(model.spoolPickerSurface(), null);
console.log("Bridge sidebar view-model checks passed");
