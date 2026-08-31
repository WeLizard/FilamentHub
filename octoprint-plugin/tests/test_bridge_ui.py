import shutil
import subprocess
from pathlib import Path

import octoprint
import octoprint_filamenthub_bridge
import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape


PACKAGE = Path(octoprint_filamenthub_bridge.__file__).resolve().parent


@pytest.mark.parametrize("surface", ["tab", "sidebar"])
def test_spool_picker_is_shared_and_renderable(surface):
    templates = Environment(
        loader=FileSystemLoader(PACKAGE / "templates"),
        undefined=StrictUndefined,
        autoescape=select_autoescape(default=True),
    )
    templates.globals["_"] = lambda text: text
    rendered = templates.get_template(
        f"filamenthub_bridge_{surface}.jinja2"
    ).render()

    assert rendered.count('class="fhb-spool-picker"') == 1
    assert f"spoolPickerSurface() === '{surface}'" in rendered
    assert "click: assignSelectedSpool" in rendered
    assert "click: clearSpoolAssignment" in rendered
    assert 'aria-label="Search spools"' in rendered
    assert 'aria-label="Choose a spool"' in rendered
    assert 'role="alert"' in rendered
    assert "hardware state is not changed" in rendered


def test_sidebar_view_model_assignment_flow():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for the browser view-model test")
    knockout = Path(octoprint.__file__).parent / "static/js/lib/knockout.js"
    subprocess.run(
        [
            node,
            str(Path(__file__).with_name("bridge_ui_test.cjs")),
            str(knockout),
            str(PACKAGE / "static/js/filamenthub_bridge.js"),
        ],
        check=True,
        timeout=30,
    )
