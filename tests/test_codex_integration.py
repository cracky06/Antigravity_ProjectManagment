import json
import zipfile
from pathlib import Path

import pytest
from codex_loader import CodexConv, export_codex_conversation_to_path


@pytest.fixture
def codex_conv(tmp_path):
    path = tmp_path / 'session.jsonl'
    path.write_text(json.dumps({'type': 'event_msg', 'timestamp': '2026-09-19T10:00:00Z',
        'payload': {'type': 'item_completed', 'item': {'type': 'UserMessage', 'id': 'u',
        'content': [{'type': 'text', 'text': 'Bonjour recherche café'}]}}}) + '\n', encoding='utf8')
    return CodexConv('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 'Demo', path, title='Test', project_root=tmp_path)


def test_search_modes_scope_and_content_refresh(tmp_path, monkeypatch, codex_conv):
    import codex_search_index as index
    index.close_thread_connection()
    monkeypatch.setattr(index, 'get_index_path', lambda: tmp_path / 'index.db')
    try:
        assert index.sync_index([codex_conv]) == (1, 0)
        assert index.sync_index([codex_conv]) == (0, 0)
        for query, mode in [('bonjour', 'substring'), ('cafe', 'words'), ('Bon.*caf', 'regex')]:
            assert index.search(query, mode, {codex_conv.conv_id}) == {codex_conv.conv_id}
            assert index.search(query, mode, set()) == set()
        with pytest.raises(Exception): index.search('[', 'regex')
        with codex_conv.path.open('a', encoding='utf8') as stream:
            stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'item_completed',
                'item': {'type': 'AgentMessage', 'text': 'Nouveau résultat'}}}) + '\n')
        assert index.touch_conversation(codex_conv)
        assert index.search('Nouveau') == {codex_conv.conv_id}
        codex_conv.title = 'Renamed'
        assert index.sync_index([codex_conv]) == (1, 0)
        assert index.sync_index([]) == (0, 1)
    finally:
        index.close_thread_connection()


def test_markdown_archive_incremental_and_retention(tmp_path, codex_conv):
    from codex_archive import archive_codex_conversations
    path = tmp_path / 'export.md'
    assert export_codex_conversation_to_path(codex_conv, path)[0]
    assert 'Bonjour recherche café' in path.read_text(encoding='utf8')
    dest = tmp_path / 'archive'
    source_before = codex_conv.path.read_bytes()
    assert archive_codex_conversations([codex_conv], dest) == (1, 0)
    assert archive_codex_conversations([codex_conv], dest) == (0, 0)
    assert archive_codex_conversations([], dest) == (0, 0)
    assert codex_conv.path.read_bytes() == source_before
    with zipfile.ZipFile(dest / 'conversations.zip') as archive:
        assert any(n.endswith('conversation.md') for n in archive.namelist())
        assert any(n.endswith('rollout.jsonl') for n in archive.namelist())
        assert not any('auth' in n for n in archive.namelist())


def test_pdf_routes_codex_messages(tmp_path, monkeypatch, codex_conv):
    import pdf_export_html as pdf
    monkeypatch.setattr(pdf, '_find_cover_image', lambda *args: None)
    html, count = pdf._build_codex_full_html('Demo', [codex_conv], '2026-09-19')
    assert count == 1 and 'Bonjour recherche café' in html
    assert 'Claude' not in html
    monkeypatch.setattr(pdf, '_find_browser', lambda: 'test-browser')
    def render(html_path, pdf_path, browser):
        assert 'Bonjour recherche café' in html_path.read_text(encoding='utf8')
        pdf_path.write_bytes(b'%PDF-test')
        return True, str(pdf_path)
    monkeypatch.setattr(pdf, '_html_to_pdf', render)
    assert pdf.export_codex_project_to_pdf('Demo', [codex_conv], tmp_path / 'out.pdf')[0]


def test_codex_ui_source_filter_search_live_and_settings(qapp, tmp_path, monkeypatch, codex_conv):
    import antigravity_manager as app
    import codex_ui
    import config
    monkeypatch.setattr(config, 'CONFIG_FILE', tmp_path / 'config.json')
    monkeypatch.setattr(app, 'build_project_map', lambda: ({}, []))
    monkeypatch.setattr(codex_ui, 'build_codex_project_map', lambda: {'Demo': [codex_conv]})
    monkeypatch.setattr(codex_ui.CodexSourceMixin, '_kick_off_codex_index_sync', lambda *a, **kw: None)
    window = app.AntigravityManagerWindow()
    try:
        window.source_combo.setCurrentIndex(window.source_combo.findData('codex'))
        assert window._active_source == 'codex'
        window.project_filter_combo.setCurrentIndex(window.project_filter_combo.findData('Demo'))
        project = window.tree.topLevelItem(0).child(0)
        window._on_item_clicked(project.child(0), 0)
        assert window.selected_codex_conv.conv_id == codex_conv.conv_id
        assert 'Bonjour recherche café' in window.chat_browser.toPlainText()
        assert codex_conv.path in window._current_watch_paths()
        window._show_find_bar('café')
        assert not window.find_bar.isHidden()
        window._populate_tree_search_results({'Demo': [codex_conv]}, 'Bonjour')
        assert window.tree.topLevelItem(1).child(0).data(0, app.Qt.ItemDataRole.UserRole)[0] == 'codex_conv'
        old_generation = window._search_generation
        window.source_combo.setCurrentIndex(window.source_combo.findData('antigravity'))
        assert window.selected_codex_conv is None
        assert window._search_generation > old_generation
        settings = app.SettingsDialog(window)
        assert hasattr(settings, 'codex_edit')
        settings.close()
    finally:
        window.close()
