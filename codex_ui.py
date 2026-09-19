"""Intégration UI de la source Codex, indépendante des lecteurs existants."""
from __future__ import annotations
import os
import re
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QTreeWidgetItem, QMenu
try:
    import markdown
except ImportError:
    markdown = None
from config import get_active_theme, get_codex_root
from codex_loader import (
    build_codex_project_map, load_codex_messages, codex_watch_paths,
    default_codex_export_filename, export_codex_conversation_to_project,
    export_codex_conversation_to_path, export_codex_project_conversations,
)

class _SearchSignals(QObject):
    finished = pyqtSignal(int, set)
    failed = pyqtSignal(int, str)

class _IndexSyncSignals(QObject):
    finished = pyqtSignal(int, int, bool, str)

class _CodexSearchRunnable(QRunnable):
    """Équivalent de `_SearchRunnable` pour la source Codex
    (v2.5) — module d'index séparé (`codex_search_index`), jamais mélangé
    avec la recherche Antigravity. Classe distincte plutôt que généraliser
    `_SearchRunnable` : évite tout risque de régression sur la recherche
    Antigravity existante en la laissant intacte."""

    def __init__(self, generation: int, query: str, mode: str, scope, index_ready: bool):
        """`scope` : set[str] (ids) si `index_ready`, sinon dict {id: CodexConv}
        (le repli sans index a besoin du .path de chaque session)."""
        super().__init__()
        self.signals = _SearchSignals()
        self._generation = generation
        self._query = query
        self._mode = mode
        self._scope_ids = scope
        self._index_ready = index_ready

    def run(self) -> None:  # type: ignore[override]
        import codex_search_index

        try:
            if self._index_ready:
                found = codex_search_index.search(
                    self._query, mode=self._mode, conv_ids=self._scope_ids
                )
            else:
                found = _fallback_codex_search(self._query, self._mode, self._scope_ids)
        except re.error as exc:
            self.signals.failed.emit(self._generation, f"Regex invalide : {exc}")
            return
        except Exception as exc:  # pragma: no cover - garde-fou
            self.signals.failed.emit(self._generation, f"Échec de la recherche : {exc}")
            return
        finally:
            codex_search_index.close_thread_connection()
        self.signals.finished.emit(self._generation, found)


def _fallback_codex_search(query: str, mode: str, scope: dict | None) -> set[str]:
    """Recherche sans index pour la source Codex : `scope` est un
    mapping {conv_id: CodexConv} (il faut le `.path` de chaque session, pas
    juste son id, pour relire le transcript)."""
    if not scope:
        return set()
    rx = re.compile(query, re.IGNORECASE | re.MULTILINE) if mode == "regex" else None
    needle = query.lower()
    out: set[str] = set()
    for cid, conv in scope.items():
        body = "\n".join(m.get("text", "") for m in load_codex_messages(conv) if m.get("text"))
        if rx is not None:
            if rx.search(body):
                out.add(cid)
        elif needle in body.lower():
            out.add(cid)
    return out


class _CodexIndexSyncRunnable(QRunnable):
    """Équivalent de `_IndexSyncRunnable` pour la source Codex (v2.5)."""

    def __init__(self, convs: list, rebuild: bool = False):
        super().__init__()
        self.signals = _IndexSyncSignals()
        self._convs = convs
        self._rebuild = rebuild

    def run(self) -> None:  # type: ignore[override]
        import codex_search_index

        try:
            if self._rebuild and codex_search_index.check_status().corrupt:
                codex_search_index.drop_index()
            fn = codex_search_index.rebuild_index if self._rebuild else codex_search_index.sync_index
            updated, deleted = fn(self._convs)
            status = codex_search_index.check_status()
            self.signals.finished.emit(updated, deleted, status.ok, status.message)
        except Exception as exc:  # pragma: no cover - garde-fou
            self.signals.finished.emit(0, 0, False, f"Échec de l'indexation : {exc}")
        finally:
            codex_search_index.close_thread_connection()


class _CodexTouchIndexRunnable(QRunnable):
    """Indexe UNE conversation Codex au fil de l'eau (consultation)."""

    def __init__(self, conv):
        super().__init__()
        self._conv = conv

    def run(self) -> None:  # type: ignore[override]
        import codex_search_index

        try:
            codex_search_index.touch_conversation(self._conv)
        except Exception:  # pragma: no cover - ne doit jamais gêner l'affichage
            pass
        finally:
            codex_search_index.close_thread_connection()



class _CodexArchiveRunnable(QRunnable):
    def __init__(self, convs):
        super().__init__()
        self.convs = convs
        self.signals = _IndexSyncSignals()

    def run(self):
        from codex_archive import archive_codex_conversations
        try:
            copied, failures = archive_codex_conversations(self.convs)
            self.signals.finished.emit(copied, failures, not failures,
                f"Codex : {copied} conversation(s) archivée(s), {failures} échec(s).")
        except Exception as exc:
            self.signals.finished.emit(0, 1, False, f"Échec de l'archivage Codex : {exc}")


class CodexSourceMixin:

    def _load_codex_source(self):
        self._search_generation += 1
        self._search_timer.stop()
        self.codex_project_map = build_codex_project_map()
        if self.selected_codex_conv:
            refreshed = next((c for cs in self.codex_project_map.values() for c in cs
                              if c.conv_id == self.selected_codex_conv.conv_id), None)
            if refreshed:
                self.display_codex_chat(refreshed)
            else:
                self._clear_chat()
        self._refresh_codex_filter()
        self._populate_codex_tree()
        count = sum(len(cs) for cs in self.codex_project_map.values())
        self.status_bar.showMessage(f"◉ Codex : {count} conversation(s)", 6000)
        self._kick_off_codex_index_sync()
        self._maybe_archive_codex()

    def _refresh_codex_filter(self):
        combo = self.project_filter_combo
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        total = sum(len(cs) for cs in self.codex_project_map.values())
        combo.addItem(f"Tous les projets ({total} conversations)", "ALL")
        combo.addItem(f"Sans projet ({len(self.codex_project_map.get('', []))})", "NONE")
        for name in sorted(n for n in self.codex_project_map if n):
            combo.addItem(f"{name} ({len(self.codex_project_map[name])})", name)
        idx = combo.findData(previous)
        combo.setCurrentIndex(max(idx, 0))
        combo.blockSignals(False)

    def _populate_codex_tree(self):
        self.tree.clear()
        color = QColor("#a1a1aa" if get_active_theme() == "dark" else "#64748b")
        def heading(text):
            item = QTreeWidgetItem([text])
            item.setForeground(0, color)
            font = item.font(0); font.setBold(True); item.setFont(0, font)
            self.tree.addTopLevelItem(item)
            item.setExpanded(True)
            return item
        def add_conv(parent, conv):
            label = (conv.title or conv.conv_id)[:65]
            if conv.archived:
                label += " • Archivée"
            item = QTreeWidgetItem([f"◉ {label}"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("codex_conv", conv))
            date = conv.last_dt.strftime("%d/%m/%Y %H:%M") if conv.last_dt else ""
            item.setToolTip(0, f"{conv.title}\n{conv.project or 'Sans projet'} • {date}\n{conv.conv_id}")
            parent.addChild(item)
        choice = self.project_filter_combo.currentData() or "ALL"
        if not self.codex_project_map:
            heading("Aucune conversation Codex trouvée")
            heading(f"Dossier : {get_codex_root()}")
            return
        if choice == "NONE":
            orphan = heading("CONVERSATIONS HORS PROJET")
            for conv in self.codex_project_map.get("", []): add_conv(orphan, conv)
            return
        projects = heading("PROJETS")
        for name, convs in sorted(self.codex_project_map.items()):
            if not name or (choice != "ALL" and choice != name): continue
            item = QTreeWidgetItem([f"📁 {name} ({len(convs)})"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("codex_project", name, convs))
            projects.addChild(item)
            for conv in convs: add_conv(item, conv)
            item.setExpanded(choice != "ALL")
        if choice == "ALL":
            orphan = heading(f"CONVERSATIONS HORS PROJET ({len(self.codex_project_map.get('', []))})")
            for conv in self.codex_project_map.get("", []): add_conv(orphan, conv)
            recent = heading("CONVERSATIONS RÉCENTES")
            convs = sorted((c for cs in self.codex_project_map.values() for c in cs),
                           key=lambda c: c.last_dt or datetime.min, reverse=True)[:40]
            for conv in convs: add_conv(recent, conv)
            recent.setExpanded(False)

    def _search_codex(self):
        query = self.search_input.text().strip()
        if not query: return
        self._search_scope_by_id = {c.conv_id: c for c in self._get_codex_search_scope()}
        self._search_generation += 1
        self._set_query_error(False)
        mode = self._current_search_mode()
        if mode == "words" and not self._codex_index_ready: mode = "substring"
        scope = set(self._search_scope_by_id) if self._codex_index_ready else dict(self._search_scope_by_id)
        runnable = _CodexSearchRunnable(self._search_generation, query, mode, scope, self._codex_index_ready)
        self._active_runnables.add(runnable)
        runnable.signals.finished.connect(self._on_search_finished)
        runnable.signals.failed.connect(self._on_search_failed)
        runnable.signals.finished.connect(lambda *_: self._active_runnables.discard(runnable))
        runnable.signals.failed.connect(lambda *_: self._active_runnables.discard(runnable))
        self._thread_pool.start(runnable)

    def _maybe_archive_codex(self, on_launch=False):
        from config import get_archive_frequency
        from codex_archive import codex_archive_due
        if os.environ.get("ANTIGRAVITY_MANAGER_NO_ARCHIVE") == "1":
            return
        if get_archive_frequency() == "launch" and not on_launch:
            return
        if codex_archive_due():
            if on_launch:
                self.codex_project_map = build_codex_project_map()
            self._archive_codex()

    def _archive_codex(self):
        if self._codex_archiving:
            self.status_bar.showMessage("Archivage Codex déjà en cours…", 3000)
            return
        convs = [c for cs in self.codex_project_map.values() for c in cs]
        if not convs:
            self.status_bar.showMessage("Aucune conversation Codex à archiver.", 3000)
            return
        self._codex_archiving = True
        worker = _CodexArchiveRunnable(convs)
        self._active_runnables.add(worker)
        worker.signals.finished.connect(self._on_codex_archive_finished)
        worker.signals.finished.connect(lambda *_: self._active_runnables.discard(worker))
        self._archive_pool.start(worker)

    def _on_codex_archive_finished(self, copied, failures, ok, message):
        self._codex_archiving = False
        if ok:
            import time
            from config import load_config, save_config
            cfg = load_config()
            cfg["last_codex_archive_ts"] = time.time()
            save_config(cfg)
        if not self._shutting_down:
            self.status_bar.showMessage(message, 8000)

    def _kick_off_codex_index_sync(self, rebuild: bool = False):
        all_convs = [c for convs in self.codex_project_map.values() for c in convs]
        if self._codex_index_syncing:
            self._codex_resync_requested = True
            return
        import codex_search_index

        status = codex_search_index.check_status()
        if status.corrupt and not rebuild:
            self.status_bar.showMessage(
                f"⚠️ {status.message} — reconstruction automatique de l'index Codex…", 6000
            )
            rebuild = True

        self._codex_index_syncing = True
        self._codex_index_ready = False
        runnable = _CodexIndexSyncRunnable(all_convs, rebuild=rebuild)
        self._active_runnables.add(runnable)
        runnable.signals.finished.connect(self._on_codex_index_sync_finished)
        runnable.signals.finished.connect(lambda *_: self._active_runnables.discard(runnable))
        self._thread_pool.start(runnable)

    def _on_codex_index_sync_finished(self, updated: int, deleted: int, ok: bool, message: str):
        if self._shutting_down:
            return
        self._codex_index_syncing = False
        self._codex_index_ready = ok
        if getattr(self, "_codex_resync_requested", False):
            self._codex_resync_requested = False
            self._kick_off_codex_index_sync()
            return
        if ok:
            if self._active_source == "codex" and self.search_input.text().strip():
                self._do_search()
        else:
            self.status_bar.showMessage(
                f"⚠️ Index Codex indisponible : {message} — recherche en mode dégradé.", 8000
            )

    def _get_codex_search_scope(self) -> list:
        """Équivalent de `_get_search_scope` pour la source Codex."""
        all_convs = [c for convs in self.codex_project_map.values() for c in convs]
        if not hasattr(self, "project_filter_combo"):
            return all_convs
        filter_val = self.project_filter_combo.currentData() or "ALL"
        if filter_val == "ALL":
            return all_convs
        if filter_val == "NONE":
            return self.codex_project_map.get("", [])
        return self.codex_project_map.get(filter_val, [])

    def display_codex_chat(self, conv):
        """Affiche une conversation Codex (v2.5, lecture seule).

        Rendu volontairement plus simple que `display_chat` (pas d'historique
        de navigation, pas de mode source brut) — cf. portée v1 documentée
        dans codex_loader.py. L'indexation FTS (v2.5) est au fil de
        l'eau comme côté Antigravity : `_CodexTouchIndexRunnable`.
        """
        if self.selected_codex_conv is None or self.selected_codex_conv.conv_id != conv.conv_id:
            self._reset_live_follow_ui()

        self.selected_conv = None
        self.selected_claude_conv = None
        self._file_view_active = False
        self.selected_codex_conv = conv
        self.btn_back.setVisible(False)
        self.chat_title.setText(conv.title or "Conversation sans titre")
        date_str = conv.last_dt.strftime("%d/%m/%Y à %H:%M") if conv.last_dt else "Date inconnue"
        origin = f" • {conv.origin_label}" if conv.origin_label else ""
        meta_text = f"📁 {conv.project}   •   {date_str}{origin}   •   ID: {conv.conv_id}"
        if conv.archived:
            meta_text += "   •   Archivée dans Codex"
        self.chat_meta.setText(meta_text)
        self.btn_open_folder.setVisible(False)
        self.btn_toggle_raw.setVisible(False)
        self.btn_find_toggle.setVisible(True)
        self.btn_refresh_chat.setVisible(True)
        self.btn_live_follow.setVisible(True)

        if not self._shutting_down and self._codex_index_ready and not self._codex_index_syncing:
            r = _CodexTouchIndexRunnable(conv)
            self._thread_pool.start(r)

        messages = load_codex_messages(conv)
        is_dark = get_active_theme() == "dark"

        if not messages:
            info_col = "#a1a1aa" if is_dark else "#475569"
            sub_col = "#71717a" if is_dark else "#64748b"
            self._set_chat_html(f"""
            <div style="text-align: center; margin-top: 60px; font-family: sans-serif;">
                <p style="font-size: 24px;">ℹ️</p>
                <p style="font-size: 14px; font-weight: bold; color: {info_col};">Aucun message textuel dans cette session.</p>
                <p style="font-size: 12px; color: {sub_col};">Session probablement technique (queue/bridge) sans dialogue.</p>
            </div>
            """)
            return

        if is_dark:
            body_bg, body_col = "#18181b", "#e4e4e7"
            user_bg, user_border, user_title_col, user_text_col = "#27272a", "#3f3f46", "#60a5fa", "#ffffff"
            model_bg, model_border, model_title_col, model_text_col = "#18181b", "#8b5cf6", "#a78bfa", "#e4e4e7"
            pre_bg, pre_border, pre_col = "#121215", "#27272a", "#38bdf8"
            code_bg, code_col = "#27272a", "#38bdf8"
            hr_col, time_col = "#27272a", "#71717a"
        else:
            body_bg, body_col = "#ffffff", "#0f172a"
            user_bg, user_border, user_title_col, user_text_col = "#f0f9ff", "#bae6fd", "#0284c7", "#0f172a"
            model_bg, model_border, model_title_col, model_text_col = "#ffffff", "#7c3aed", "#6d28d9", "#1e293b"
            pre_bg, pre_border, pre_col = "#f8fafc", "#e2e8f0", "#0369a1"
            code_bg, code_col = "#f1f5f9", "#0369a1"
            hr_col, time_col = "#e2e8f0", "#64748b"

        html_parts = [f"""<!DOCTYPE html><html><head><style>
            body {{ background-color: {body_bg}; color: {body_col};
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    font-size: 13px; line-height: 1.45; margin: 0; padding: 10px; }}
            .msg-container {{ margin-bottom: 14px; }}
            .user-box {{ background-color: {user_bg}; border: 1px solid {user_border};
                         border-radius: 8px; padding: 8px 14px; margin-bottom: 8px; }}
            .user-header {{ font-weight: bold; color: {user_title_col}; font-size: 12px; margin: 0 0 1px 0; }}
            .model-box {{ background-color: {model_bg}; border-left: 3px solid {model_border};
                          padding: 2px 14px; margin-bottom: 10px; }}
            .model-header {{ font-weight: bold; color: {model_title_col}; font-size: 12px; margin: 0 0 1px 0; }}
            .msg-body {{ line-height: 1.4; }}
            .time-tag {{ color: {time_col}; font-weight: normal; font-size: 11px; float: right; }}
            h1, h2, h3, h4 {{ margin-top: 10px; margin-bottom: 4px; color: {model_title_col}; }}
            h1 {{ font-size: 16px; border-bottom: 1px solid {hr_col}; padding-bottom: 3px; }}
            h2 {{ font-size: 15px; border-bottom: 1px solid {hr_col}; padding-bottom: 2px; }}
            h3 {{ font-size: 14px; }} h4 {{ font-size: 13px; }}
            p {{ margin: 2px 0; }} ul, ol {{ margin: 2px 0; padding-left: 20px; }} li {{ margin-bottom: 1px; }}
            strong {{ font-weight: bold; }}
            blockquote {{ border-left: 3px solid {model_border}; margin: 6px 0; padding: 4px 10px; color: {time_col}; }}
            table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
            th, td {{ border: 1px solid {hr_col}; padding: 5px 8px; text-align: left; }}
            th {{ background-color: {pre_bg}; font-weight: bold; }}
            pre {{ background-color: {pre_bg}; border: 1px solid {pre_border}; border-radius: 6px;
                   padding: 10px; font-family: 'Consolas', 'Fira Code', monospace; font-size: 12px;
                   color: {pre_col}; white-space: pre-wrap; word-wrap: break-word; }}
            code {{ background-color: {code_bg}; padding: 2px 4px; border-radius: 4px;
                    font-family: 'Consolas', monospace; font-size: 12px; color: {code_col};
                    white-space: pre-wrap; word-wrap: break-word; }}
            a {{ color: {model_title_col}; word-wrap: break-word; }}
        </style></head><body>"""]

        for msg in messages:
            role = msg.get("role")
            raw_text = msg.get("text", "").strip()
            ts = msg.get("timestamp", "")
            time_html = f"<span class='time-tag'>{ts}</span>" if ts else ""

            def _escape_pre(text: str) -> str:
                escaped = (
                    text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
                return escaped.replace("\n", "<br>")

            if markdown:
                try:
                    formatted = markdown.markdown(raw_text, extensions=["fenced_code", "tables", "nl2br"])
                except Exception:
                    formatted = _escape_pre(raw_text)
            else:
                formatted = _escape_pre(raw_text)

            _stripped = formatted.strip()
            if _stripped.startswith("<p>") and _stripped.endswith("</p>") and _stripped.count("<p>") == 1:
                formatted = _stripped[3:-4]

            if role == "user":
                html_parts.append(f"""
                <div class="msg-container"><div class="user-box">
                    <div class="user-header">👤 Utilisateur {time_html}</div>
                    <div class="msg-body" style="color: {user_text_col};">{formatted}</div>
                </div></div>""")
            elif role == "assistant":
                html_parts.append(f"""
                <div class="msg-container"><div class="model-box">
                    <div class="model-header">◉ Codex {time_html}</div>
                    <div class="msg-body" style="color: {model_text_col};">{formatted}</div>
                </div></div>""")

        html_parts.append("</body></html>")
        self._set_chat_html("".join(html_parts))
        self._prefill_find_from_search()

    def _build_codex_context_menu(self, dtype: str, data: tuple, pos):
        menu = QMenu(self)
        if dtype == "codex_conv":
            conv = data[1]
            act_open = menu.addAction("📂 Ouvrir le dossier du projet dans l'Explorateur")
            act_open.setEnabled(bool(conv.project_root and conv.project_root.is_dir()))
            act_open.triggered.connect(lambda: self._open_codex_project_folder(conv))

            act_copy_id = menu.addAction("📋 Copier l'ID de session")
            act_copy_id.triggered.connect(lambda: QApplication.clipboard().setText(conv.conv_id))

            menu.addSeparator()
            act_exp_proj = menu.addAction("💾 Exporter en Markdown dans le projet")
            act_exp_proj.setEnabled(bool(conv.project_root))
            act_exp_proj.triggered.connect(lambda checked=False, c=conv: self._export_codex_conv_to_project(c))
            act_exp_as = menu.addAction("💾 Exporter en Markdown…")
            act_exp_as.triggered.connect(lambda checked=False, c=conv: self._export_codex_conv_as(c))
        elif dtype == "codex_project":
            _, proj_name, convs = data
            act_open = menu.addAction(f"📂 Ouvrir '{proj_name}' dans l'Explorateur")
            root = convs[0].project_root if convs else None
            act_open.setEnabled(bool(root and root.is_dir()))
            act_open.triggered.connect(lambda: self._open_codex_project_folder(convs[0]) if convs else None)

            menu.addSeparator()
            n = len(convs)
            act_exp_all = menu.addAction(f"💾 Exporter les {n} conversation(s) en Markdown")
            act_exp_all.setEnabled(n > 0)
            act_exp_all.triggered.connect(
                lambda checked=False, p=proj_name, cs=list(convs): self._export_codex_project_all(p, cs)
            )
            act_pdf = menu.addAction("📄 Exporter le projet en PDF…")
            act_pdf.setEnabled(n > 0)
            act_pdf.triggered.connect(
                lambda checked=False, p=proj_name, cs=list(convs): self._export_codex_project_pdf(p, cs)
            )
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _open_codex_project_folder(self, conv):
        if conv.project_root and conv.project_root.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(conv.project_root)))
        else:
            QMessageBox.warning(self, "Erreur", "Dossier de projet introuvable.")

    def _export_codex_conv_to_project(self, conv):
        """Écrit l'export dans `<project_root>/_conversations/`."""
        ok, result = export_codex_conversation_to_project(conv)
        if ok:
            self.status_bar.showMessage(f"💾 Exporté : {result}", 6000)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(result).parent)))
        else:
            QMessageBox.critical(self, "Échec de l'export", result)

    def _export_codex_conv_as(self, conv):
        """Demande l'emplacement puis écrit l'export Markdown."""
        suggested = default_codex_export_filename(conv)
        start_dir = str(conv.project_root) if conv.project_root else str(Path.home())
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter la conversation en Markdown",
            str(Path(start_dir) / suggested),
            "Fichiers Markdown (*.md);;Tous les fichiers (*)",
        )
        if not path:
            return
        ok, result = export_codex_conversation_to_path(conv, path)
        if ok:
            self.status_bar.showMessage(f"💾 Exporté : {result}", 6000)
        else:
            QMessageBox.critical(self, "Échec de l'export", result)

    def _export_codex_project_all(self, project_name: str, convs: list):
        """Exporte en masse toutes les conversations Codex d'un projet
        en Markdown dans `<project_root>/_conversations/`."""
        if not convs:
            return
        root = convs[0].project_root
        if not root:
            QMessageBox.information(
                self, "Racine inconnue",
                "Ce projet n'a pas de dossier local identifiable "
                "(session démarrée ailleurs) — export en masse impossible.\n"
                "Utilisez « Exporter en Markdown… » sur chaque conversation.",
            )
            return
        dest = root / "_conversations"
        ret = QMessageBox.question(
            self,
            "Exporter le projet",
            f"Exporter les {len(convs)} conversation(s) de « {project_name} » "
            f"en Markdown dans :\n{dest}\n\n"
            f"Les fichiers existants seront écrasés. Continuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage(f"💾 Export de « {project_name} »…")
        QApplication.processEvents()
        try:
            ok, fail, dest_dir = export_codex_project_conversations(convs)
        except ValueError as exc:
            QMessageBox.critical(self, "Échec de l'export", str(exc))
            return
        msg = f"💾 {ok} conversation(s) exportée(s) dans {dest_dir}"
        if fail:
            msg += f" — {fail} échec(s)"
        self.status_bar.showMessage(msg, 8000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest_dir)))

    def _export_codex_project_pdf(self, project_name: str, convs: list):
        """Assemble toutes les conversations Codex du projet dans un
        seul PDF (même moteur Edge/Chromium headless que côté Antigravity)."""
        if not convs:
            return
        root = convs[0].project_root
        from data_loader import _slugify
        default_name = f"{_slugify(project_name)}_{__import__('datetime').datetime.now():%Y%m%d}.pdf"
        suggested = str((root / default_name) if root else Path.home() / default_name)
        pdf_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le projet en PDF", suggested, "Document PDF (*.pdf)"
        )
        if not pdf_path:
            return

        from pdf_export_html import export_codex_project_to_pdf

        self.status_bar.showMessage(
            f"📄 Génération du PDF de « {project_name} » ({len(convs)} conv.)…"
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            ok, result = export_codex_project_to_pdf(project_name, convs, pdf_path)
        finally:
            QApplication.restoreOverrideCursor()

        if ok:
            self.status_bar.showMessage(f"📄 PDF créé : {result}", 8000)
            QDesktopServices.openUrl(QUrl.fromLocalFile(result))
        else:
            QMessageBox.critical(self, "Échec de l'export PDF", result)

    # -----------------------------------------------------------------
    # Export / archivage au niveau d'un PROJET
