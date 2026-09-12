---
layout: plugin

id: filamenthub_bridge
title: FilamentHub Bridge
description: Connect OctoPrint to FilamentHub spool assignments and replay-safe material usage tracking.
authors:
- FilamentHub
license: AGPL-3.0-or-later
date: 2026-09-12

homepage: https://filamenthub.ru
source: https://github.com/WeLizard/FilamentHub/tree/main/octoprint-plugin
archive: https://github.com/WeLizard/FilamentHub/releases/download/octoprint-v0.1.5/octoprint_filamenthubbridge-0.1.5.tar.gz
privacypolicy: https://filamenthub.ru/privacy-policy

tags:
- filament
- inventory
- cloud

compatibility:
  python: ">=3.9,<4"

attributes:
- cloud
- commercial
- free-tier
---

FilamentHub Bridge connects an OctoPrint material system to the physical spool
inventory in the user's FilamentHub account. The Bridge shows assigned spools in
OctoPrint, lets the user explicitly replace or remove an assignment, and tracks
measured extrusion against the selected spool. Pending usage checkpoints stay in
a local outbox until FilamentHub acknowledges them, including across temporary
network failures and OctoPrint restarts.

The plugin requires a free FilamentHub account and an internet connection for
synchronization. It makes outbound HTTPS requests to the FilamentHub service;
it does not expose the OctoPrint instance to the public internet. If the service
is unavailable, OctoPrint continues to operate and the Bridge retains pending
usage locally for a later retry.

After the user enters a short-lived pairing code, the plugin sends the plugin
and OctoPrint versions, declared material routing, explicit spool assignment
operations, print lifecycle identifiers, print file names and measured material
usage. It does not upload G-code. The long-lived Bridge credential is stored in
OctoPrint's restricted plugin settings and is not returned through the settings
API. See the [FilamentHub Privacy Policy](https://filamenthub.ru/privacy-policy)
for information about data processing.

Source, installation notes and release checksums are available in the
[FilamentHub repository](https://github.com/WeLizard/FilamentHub/tree/main/octoprint-plugin).
