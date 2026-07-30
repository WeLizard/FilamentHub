# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# id = "filamenthub-pr14992-page-lifecycle"
# name = "FilamentHub PR14992 Page Fixture"
# description = "Checks plugin page sizing, SVG icon loading, bridge messaging and lifecycle."
# author = "FilamentHub"
# version = "0.0.1"
# ///

import os

import orca


PAGE = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: #17191d;
      color: #f5f7fa;
      font: 15px system-ui, sans-serif;
    }
    main {
      box-sizing: border-box;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 16px;
      min-height: 100%;
      padding: 24px;
    }
    section {
      align-self: stretch;
      border: 1px solid #3a3f48;
      border-radius: 12px;
      padding: 16px;
    }
    button {
      padding: 8px 14px;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
    }
  </style>
</head>
<body>
  <main>
    <h1>PR #14992 page fixture</h1>
    <section>
      <pre id="status">Waiting for the host bridge…</pre>
    </section>
    <button id="echo" type="button">Test Python round-trip</button>
  </main>
  <iframe id="child" srcdoc="<!doctype html><script>parent.postMessage({source:'fixture-child',ownBridge:typeof window.orca},'*')</script>" hidden></iframe>
  <script>
    const status = document.getElementById("status");
    const state = {
      resizeEvents: 0,
      bridge: typeof window.orca,
      childBridge: "pending",
      webgl: false,
      webgl2: false,
      viewport: ""
    };

    function render() {
      state.viewport = `${window.innerWidth} × ${window.innerHeight}`;
      status.textContent = JSON.stringify(state, null, 2);
    }

    function inspectWebGL() {
      const canvas = document.createElement("canvas");
      state.webgl2 = Boolean(canvas.getContext("webgl2"));
      state.webgl = state.webgl2 || Boolean(canvas.getContext("webgl"));
    }

    window.addEventListener("resize", () => {
      state.resizeEvents += 1;
      render();
    });
    window.addEventListener("message", (event) => {
      if (!event.data || event.data.source !== "fixture-child") return;
      state.childBridge = event.data.ownBridge;
      render();
    });

    inspectWebGL();
    render();

    if (window.orca) {
      window.orca.onMessage((data) => {
        state.pythonReply = data;
        render();
      });
      window.orca.postMessage({
        type: "ready",
        viewport: [window.innerWidth, window.innerHeight]
      });
    }

    document.getElementById("echo").addEventListener("click", () => {
      window.orca.postMessage({type: "echo", value: Date.now()});
    });
  </script>
</body>
</html>
"""

BUMPMESH_PAGE = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    html, body, iframe {
      width: 100%;
      height: 100%;
      margin: 0;
      border: 0;
      overflow: hidden;
    }
  </style>
</head>
<body>
  <iframe
    src="https://bumpmesh.com/"
    title="BumpMesh"
    allow="fullscreen"
    referrerpolicy="strict-origin-when-cross-origin"
  ></iframe>
</body>
</html>
"""


class PageLifecycleFixture(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "PR14992 Page"

    def get_ui(self):
        return PAGE

    def get_icon(self):
        return os.path.join(os.path.dirname(__file__), "fixture_page.svg")

    def on_message(self, message):
        kind = (message or {}).get("type")
        if kind == "ready":
            self.post_message({"type": "ready-ack", "received": message})
        elif kind == "echo":
            self.post_message({"type": "echo-ack", "value": message.get("value")})


class BumpMeshFullscreenFixture(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "BumpMesh Fullscreen"

    def get_ui(self):
        return BUMPMESH_PAGE

    def get_icon(self):
        return os.path.join(os.path.dirname(__file__), "fixture_page.svg")


@orca.plugin
class PageLifecyclePlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(PageLifecycleFixture)
        orca.register_capability(BumpMeshFullscreenFixture)
