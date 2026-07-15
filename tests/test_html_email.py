from gmail_codex_bridge.html_email import markdown_to_html


def test_markdown_report_is_rendered_as_safe_html():
    rendered = markdown_to_html("# Rapport\n\n- **Statut** : OK\n- [Lien](https://example.com)\n\n`<script>`")

    assert "<h1>Rapport</h1>" in rendered
    assert "<ul><li><strong>Statut</strong> : OK</li>" in rendered
    assert '<a href="https://example.com">Lien</a>' in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered
