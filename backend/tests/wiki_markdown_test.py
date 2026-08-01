from app.services.wiki_markdown import derive_wiki_summary


def test_derive_wiki_summary_uses_plain_first_prose_paragraph() -> None:
    content = """# Warping (Коробление) — Полное руководство

## Что такое Warping?

**Warping (коробление)** — это дефект 3D-печати, при котором углы детали
отлипают от платформы и загибаются вверх.

![Пример](https://example.com/warping.png)

## Причины
"""

    summary = derive_wiki_summary(content)

    assert summary == (
        "Warping (коробление) — это дефект 3D-печати, при котором углы детали "
        "отлипают от платформы и загибаются вверх."
    )
    assert "#" not in summary
    assert "**" not in summary
    assert "![" not in summary


def test_derive_wiki_summary_prefers_plain_frontmatter_summary() -> None:
    summary = derive_wiki_summary(
        "# Duplicate title\n\nBody",
        "Read the **practical guide** and [check settings](https://example.com).",
    )

    assert summary == "Read the practical guide and check settings."
