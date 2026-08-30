from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from filamenthub_edge.config import NodeConfig
from filamenthub_edge.container import _prepare_state, load_container_config
from filamenthub_edge.errors import StateError

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Linux container bootstrap")


def test_bootstrap_reads_private_options_before_dropping_all_root_credentials(tmp_path):
    config = NodeConfig("https://filamenthub.test", tmp_path, ())
    calls = []
    user = SimpleNamespace(pw_uid=100, pw_gid=101)
    with (
        patch(
            "filamenthub_edge.container.NodeConfig.load",
            side_effect=lambda: (calls.append("read_options"), config)[1],
        ),
        patch("pwd.getpwnam", return_value=user),
        patch("os.geteuid", side_effect=[0, 100]),
        patch(
            "filamenthub_edge.container._prepare_state",
            side_effect=lambda *a: calls.append("prepare"),
        ),
        patch("os.setgroups", side_effect=lambda groups: calls.append(("groups", groups))),
        patch("os.setgid", side_effect=lambda gid: calls.append(("gid", gid))),
        patch("os.setuid", side_effect=lambda uid: calls.append(("uid", uid))),
        patch("os.umask"),
        patch.object(sys, "argv", ["edge"]),
        patch.dict(os.environ, {"SUPERVISOR_TOKEN": "private", "HASSIO_TOKEN": "private"}),
    ):
        assert load_container_config() is config
        assert "SUPERVISOR_TOKEN" not in os.environ
        assert "HASSIO_TOKEN" not in os.environ
    assert calls == ["read_options", "prepare", ("groups", []), ("gid", 101), ("uid", 100)]


def test_healthcheck_does_not_repair_or_create_persistent_state(tmp_path):
    config = NodeConfig("https://filamenthub.test", tmp_path, ())
    with (
        patch("filamenthub_edge.container.NodeConfig.load", return_value=config),
        patch("pwd.getpwnam", return_value=SimpleNamespace(pw_uid=100, pw_gid=101)),
        patch("os.geteuid", side_effect=[0, 100]),
        patch("filamenthub_edge.container._prepare_state") as prepare,
        patch("os.setgroups"),
        patch("os.setgid"),
        patch("os.setuid"),
        patch("os.umask"),
        patch.object(sys, "argv", ["edge", "--status"]),
    ):
        load_container_config()
        prepare.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("link_kind", ["symbolic", "hard"])
def test_bootstrap_rejects_links_and_other_directories_before_changing_permissions(
    tmp_path, link_kind
):
    state = tmp_path / "data"
    state.mkdir(mode=0o700)
    outside = tmp_path / "outside.json"
    outside.write_text("private", encoding="utf-8")
    outside.chmod(0o600)
    if link_kind == "symbolic":
        (state / "node.json").symlink_to(outside)
    else:
        os.link(outside, state / "node.json")
    with patch("filamenthub_edge.container.DATA_DIRECTORY", state), patch("os.chown") as chown:
        with pytest.raises(StateError, match="symbolic|unsafe|hard links"):
            _prepare_state(state, os.geteuid(), os.getegid())
        with pytest.raises(StateError, match="dedicated"):
            _prepare_state(tmp_path, os.geteuid(), os.getegid())
        chown.assert_not_called()
    assert outside.read_text(encoding="utf-8") == "private"


def test_bootstrap_preserves_options_and_queued_bytes(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "connections").mkdir()
    options = data / "options.json"
    options.write_text('{"connections":[]}', encoding="utf-8")
    options.chmod(0o600)
    queued = data / "connections/printer.json"
    queued.write_text('{"usage_outbox":[{"sequence":1}]}', encoding="utf-8")
    before = queued.read_bytes()
    options_before = options.stat()
    with patch("filamenthub_edge.container.DATA_DIRECTORY", data), patch("os.chown") as chown:
        _prepare_state(data, os.geteuid(), os.getegid())
    assert queued.read_bytes() == before
    assert options.stat() == options_before
    assert options not in [call.args[0] for call in chown.call_args_list]
    assert queued.stat().st_mode & 0o777 == 0o600
