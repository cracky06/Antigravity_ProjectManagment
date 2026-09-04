"""pdf_export_html.py — Export PDF d'un projet entier (moteur Edge/Chromium headless).

Historique : deux moteurs précédents ont été essayés et abandonnés pour ce
besoin (un seul document HTML/Markdown riche, paginé, avec en-tête/pied) :
  - `pdf_export.py` (Qt / QTextDocument + QPainter maison) : rendu correct
    mais blanc résiduel sous les images, pas d'emoji couleur, pagination et
    en-têtes entièrement à la main.
  - `pdf_export_fpdf.py` (fpdf2) : bibliothèque de *composition*, pas un
    moteur HTML — son `write_html` est trop limité (plante sur `<code>` dans
    un `<td>`) et un parseur Markdown maison s'est révélé être une source de
    bugs sans fin (liens, code inline, tableaux, emojis).

Ce module imprime un document HTML/CSS complet via **Edge (ou Chrome/
Chromium) headless**, un vrai moteur de rendu : le Markdown passe par la
bibliothèque `markdown` (fenced_code, tables, nl2br) puis le CSS `@page`
(margin-boxes) gère nativement en-tête/pied/numéro de page reconduits sur
chaque page, sans code de pagination maison. Aucune dépendance ajoutée à la
distribution : on pilote un navigateur déjà présent sur la machine.

Structure du document :
  1. page de garde (nom du projet, visuel éventuel, nb de conversations,
     date) — le visuel est cherché dans <projet>/assets/ puis à la racine du
     projet, dans cet ordre strict de repli : background* -> splash* ->
     fichier au nom du projet -> n'importe quel .ico (cf. `_find_cover_image`) ;
  2. table des matières ;
  3. une section par conversation : titre, méta, échanges ; les images
     générées sont posées dans leur échange d'origine (corrélation
     temporelle, cf. `_image_generation_times`) ;
  4. annexe des images non corrélées à un échange.

Les images sont redimensionnées (<= _MAX_IMG_WIDTH px) et réencodées en JPEG
q82 (sauf PNG à transparence) via QImage avant intégration en `data:` URI.
"""

from __future__ import annotations

import base64
import html as _html
import logging
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt6.QtGui import QImage

from data_loader import (
    _collect_session_images,
    _find_brain_path,
    _image_generation_times,
    _sanitize_message_text,
    load_chat_messages,
    get_projects_root,
    get_transcript_info,
)

try:
    import markdown as _md
except ImportError:  # pragma: no cover
    _md = None

logger = logging.getLogger("antigravity_manager.pdf_export_html")

# --- Images -----------------------------------------------------------------
_MAX_IMG_WIDTH = 900
_JPEG_QUALITY = 82
_MAX_RAW_BYTES = 12 * 1024 * 1024


def _image_data_uri(path: Path, max_width: int = _MAX_IMG_WIDTH) -> str | None:
    """Charge / redimensionne / réencode une image en `data:` URI (via QImage
    — PyQt6 est déjà une dépendance, pas besoin de Pillow).

    JPEG q82, sauf image à transparence réelle (PNG/ICO — conservée en PNG
    pour ne pas perdre le canal alpha).
    """
    try:
        if path.stat().st_size > _MAX_RAW_BYTES:
            return None
        img = QImage(str(path))
        if img.isNull():
            return None
        if img.width() > max_width:
            img = img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)

        has_alpha = img.hasAlphaChannel() and path.suffix.lower() in (".png", ".ico")
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        if has_alpha:
            img.save(buf, "PNG")
            mime = "image/png"
        else:
            img.save(buf, "JPEG", _JPEG_QUALITY)
            mime = "image/jpeg"
        buf.close()
        b64 = base64.b64encode(bytes(ba)).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as exc:  # pragma: no cover
        logger.warning("Image %s non intégrée : %s", path, exc)
        return None


# --- Visuel de couverture ---------------------------------------------------
# Cherché dans TOUS les dossiers nommés « assets » sous la racine du projet
# (scan récursif borné, node_modules/.git/etc. exclus — cas des projets web
# structurés en dist/assets, public/assets, src/assets…), les moins profonds
# d'abord, puis la racine du projet elle-même en dernier repli. DANS CET
# ORDRE STRICT (chaque étape est un repli de la précédente, pas une
# recherche globale) : 1) un fichier « background » ; 2) sinon « splash » ;
# 3) sinon « logo » ; 4) sinon un fichier au nom du projet
# (ex. NomDuProjet.png) ; 5) sinon n'importe quel .ico. Le premier trouvé à
# une étape est utilisé immédiatement, sans regarder les étapes suivantes.
_COVER_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_COVER_MAX_WIDTH = 360


# Dossiers exclus du scan récursif des "assets/" (lourds et/ou non
# pertinents : dépendances, VCS, build cache).
_COVER_SCAN_EXCLUDE_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__",
    ".mypy_cache", ".pytest_cache", "target", ".next", ".turbo",
}
_COVER_SCAN_MAX_DEPTH = 6


def _iter_asset_dirs(proj_root: Path):
    """Trouve tous les dossiers nommés `assets` sous `proj_root` (BFS bornée
    en profondeur, dossiers lourds/techniques exclus). La racine du projet
    elle-même est aussi retournée en dernier (repli si rien n'est nommé
    « assets »)."""
    if not proj_root.is_dir():
        return
    found: list[Path] = []
    stack = [(proj_root, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            entries = list(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if not e.is_dir():
                continue
            if e.name.lower() in _COVER_SCAN_EXCLUDE_DIRS or e.name.startswith("."):
                continue
            if e.name.lower() == "assets":
                found.append(e)
            if depth < _COVER_SCAN_MAX_DEPTH:
                stack.append((e, depth + 1))
    # Dossiers "assets" les moins profonds d'abord (plus probablement les
    # bons), puis la racine du projet en tout dernier repli.
    found.sort(key=lambda p: len(p.relative_to(proj_root).parts))
    yield from found
    yield proj_root


def _find_cover_image(project_name: str) -> Path | None:
    """Cherche une image « évidente » à afficher sous le titre du projet."""
    try:
        proj_root = get_projects_root() / project_name
    except Exception:
        return None

    search_dirs = list(_iter_asset_dirs(proj_root))

    def _files(d: Path):
        if not d.is_dir():
            return []
        try:
            return sorted((p for p in d.iterdir() if p.is_file()), key=lambda p: p.name.lower())
        except OSError:
            return []

    def _first_matching(predicate) -> Path | None:
        for d in search_dirs:
            for f in _files(d):
                if predicate(f):
                    return f
        return None

    slug = re.sub(r"[^a-z0-9]+", "", project_name.lower())

    # 1) background
    hit = _first_matching(
        lambda f: f.suffix.lower() in _COVER_IMG_EXTS and f.stem.lower().startswith("background")
    )
    if hit:
        return hit
    # 2) splash
    hit = _first_matching(
        lambda f: f.suffix.lower() in _COVER_IMG_EXTS and f.stem.lower().startswith("splash")
    )
    if hit:
        return hit
    # 3) logo (mot-clé recherché n'importe où dans le nom, ex.
    #    alchemylogie_logo_title_1.png)
    hit = _first_matching(
        lambda f: f.suffix.lower() in _COVER_IMG_EXTS and "logo" in f.stem.lower()
    )
    if hit:
        return hit
    # 4) nom de l'app (nom du projet dans le nom de fichier)
    hit = _first_matching(
        lambda f: f.suffix.lower() in _COVER_IMG_EXTS
        and bool(slug) and slug in re.sub(r"[^a-z0-9]+", "", f.stem.lower())
    )
    if hit:
        return hit
    # 5) repli : n'importe quel .ico
    return _first_matching(lambda f: f.suffix.lower() == ".ico")


# --- Markdown -> HTML ------------------------------------------------------
def _md_to_html(text: str) -> str:
    if not text:
        return ""
    if _md is not None:
        try:
            return _md.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
        except Exception:
            pass
    esc = _html.escape(text)
    return esc.replace("\n", "<br>")


# --- CSS ----------------------------------------------------------------------
# @page margin-boxes : en-tête/pied natifs, reconduits sur CHAQUE page par le
# moteur de rendu — aucune pagination à gérer nous-même.
_PAGE_CSS = """
@page {
  size: A4;
  margin: 28mm 15mm 20mm 15mm;
  @top-left  { content: var(--hdr); font-size: 8pt; color: #94a3b8;
               font-family: 'Segoe UI', Arial, sans-serif; }
  @bottom-left  { content: "Page " counter(page); font-size: 8pt; color: #94a3b8;
                  font-family: 'Segoe UI', Arial, sans-serif; }
  @bottom-right { content: var(--date); font-size: 8pt; color: #94a3b8;
                  font-family: 'Segoe UI', Arial, sans-serif; }
}
@page cover { margin: 0; }
"""

_BODY_CSS = """
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 9.5pt;
         color: #1e293b; line-height: 1.35; margin: 0; }
  p  { margin: 3pt 0; }
  ul, ol { margin: 3pt 0; padding-left: 18pt; }
  li { margin: 1pt 0; }
  h1 { font-size: 16pt; color: #6d28d9; margin: 0 0 6pt 0; }
  h2 { font-size: 13pt; color: #6d28d9; margin: 10pt 0 4pt 0; }
  h3 { font-size: 10.5pt; margin: 7pt 0 3pt 0; }
  h4 { font-size: 9.5pt; margin: 5pt 0 2pt 0; }
  h1, h2, h3, h4, .who { break-after: avoid; }
  .who { font-weight: bold; font-size: 8.5pt; }
  .who.user  { color: #0284c7; }
  .who.model { color: #6d28d9; }
  .ts { color: #94a3b8; font-weight: normal; font-size: 8pt; }
  .msg-user  { background: #f0f9ff; border: 1px solid #bae6fd;
               border-radius: 6px; padding: 5pt 10pt; margin: 5pt 0;
               break-inside: avoid-page; }
  .msg-model { border-left: 3px solid #7c3aed; padding: 2pt 10pt; margin: 5pt 0; }
  pre { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px;
        padding: 5pt 8pt; font-family: Consolas, monospace; font-size: 8pt;
        line-height: 1.3; white-space: pre-wrap; word-wrap: break-word;
        break-inside: avoid-page; }
  code { background: #f1f5f9; font-family: Consolas, monospace; font-size: 8.5pt;
         padding: 1px 3px; border-radius: 3px; }
  pre code { background: none; padding: 0; }
  img { max-width: 100%; display: block; margin: 6pt 0; break-inside: avoid-page; }
  .imgcap { color: #64748b; font-size: 7.5pt; margin: 0 0 6pt 0; }
  table { border-collapse: collapse; font-size: 8.5pt; width: 100%;
          margin: 6pt 0; break-inside: avoid-page; }
  th, td { border: 1px solid #cbd5e1; padding: 4pt 7pt; text-align: left;
           vertical-align: top; }
  th { background: #f5f3ff; color: #6d28d9; }
  a { color: #0284c7; }
  .lead { color: #64748b; font-size: 8.5pt; margin: 0 0 8pt 0; }
  .conv-section { break-before: page; }
  .conv-section:first-of-type { break-before: auto; }
</style>
"""


# --- Construction du contenu d'une conversation ----------------------------
def _conversation_body_html(conv, brain_p: Path | None) -> tuple[str, str, list]:
    """Retourne (titre_affiché, html_de_la_section, annexe_images).

    annexe_images : liste de (légende, data_uri|None, nom) pour les images
    non corrélées à un échange (regroupées en fin de document).
    """
    title = getattr(conv, "title", "") or ""
    fallback_title, last_dt = get_transcript_info(conv.conv_id)
    disp = title or fallback_title or conv.conv_id[:12]
    date_str = last_dt.strftime("%Y-%m-%d %H:%M") if last_dt else "date inconnue"

    parts = [
        '<div class="conv-section">',
        f"<h2>{_html.escape(disp)}</h2>",
        f'<p class="lead">ID <code>{conv.conv_id}</code> — {date_str}</p>',
    ]

    messages = load_chat_messages(conv.conv_id)
    proj = getattr(conv, "project", "") or ""
    proj_root = None
    if proj:
        try:
            proj_root = get_projects_root() / proj
        except Exception:
            proj_root = None

    gen_times: dict[str, float] = {}
    collected: list[tuple[str, Path]] = []
    if brain_p and brain_p.is_dir():
        gen_times = _image_generation_times(conv.conv_id)
        collected = _collect_session_images(brain_p)

    dated: list[tuple[float, Path]] = []
    undated: list[tuple[str, Path]] = []
    for label, src in collected:
        ep = gen_times.get(src.name)
        (dated if ep is not None else undated).append(
            (ep, src) if ep is not None else (label, src)
        )
    dated.sort(key=lambda e: e[0])

    msg_epochs = [float(m.get("epoch") or 0.0) for m in messages]
    img_i = 0

    def _emit_image(src: Path, note: str = "") -> None:
        uri = _image_data_uri(src)
        if uri:
            parts.append(f'<img src="{uri}"/>')
        cap = f"🖼️ {_html.escape(src.name)}"
        if note:
            cap += f" — {note}"
        parts.append(f'<div class="imgcap">{cap}</div>')

    if messages:
        for i, msg in enumerate(messages):
            is_user = msg.get("role") == "user"
            cls = "msg-user" if is_user else "msg-model"
            who = "user" if is_user else "model"
            name = "👤 Utilisateur" if is_user else "✨ Antigravity"
            ts = msg.get("timestamp", "")
            body = _md_to_html(
                _sanitize_message_text((msg.get("text", "") or "").rstrip(), proj_root)
            )
            parts.append(
                f'<div class="{cls}"><div class="who {who}">{name}'
                f'<span class="ts"> · {_html.escape(ts)}</span></div>{body}</div>'
            )
            next_ep = float("inf")
            for j in range(i + 1, len(messages)):
                if msg_epochs[j] > 0:
                    next_ep = msg_epochs[j]
                    break
            while img_i < len(dated) and dated[img_i][0] < next_ep:
                _ep, src = dated[img_i]
                _emit_image(src)
                img_i += 1
    else:
        parts.append("<p><em>Aucun message textuel dans les journaux.</em></p>")

    while img_i < len(dated):
        _ep, src = dated[img_i]
        _emit_image(src, "fin de session")
        img_i += 1

    annex = [(f"{disp} — {label}", _image_data_uri(src), src.name) for label, src in undated]
    parts.append("</div>")
    return disp, "".join(parts), annex


# --- Détection du navigateur -------------------------------------------------
_EDGE_CANDIDATES = [
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe",
]
_CHROME_CANDIDATES = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]


def _find_browser() -> str | None:
    """Cherche Edge, puis Chrome/Chromium, sur les emplacements standards."""
    import os

    for candidates, exe in ((_EDGE_CANDIDATES, "msedge.exe"), (_CHROME_CANDIDATES, "chrome.exe")):
        for tmpl in candidates:
            p = Path(os.path.expandvars(tmpl))
            if p.is_file():
                return str(p)
        found = shutil.which(exe)
        if found:
            return found
    # Dernier repli : chromium générique sur le PATH
    for exe in ("chromium.exe", "chromium"):
        found = shutil.which(exe)
        if found:
            return found
    return None


def _wait_for_stable_file(path: Path, timeout_s: float = 60.0, poll_s: float = 0.25) -> bool:
    """Attend que `path` existe puis que sa taille se stabilise.

    Chromium en `--headless=new` rend la main au processus appelant dès que
    la fenêtre headless a été lancée — l'écriture réelle du PDF se termine
    APRÈS le retour de `subprocess.run` (surtout quand d'autres instances
    d'Edge tournent déjà sur la machine, cas quasi systématique). Vérifier
    `pdf_path.is_file()` immédiatement après l'appel est donc une course
    perdue d'avance : on sonde le fichier jusqu'à ce qu'il apparaisse et
    cesse de grossir sur deux lectures consécutives.
    """
    import time

    deadline = time.monotonic() + timeout_s
    last_size = -1
    stable_hits = 0
    while time.monotonic() < deadline:
        if path.is_file():
            size = path.stat().st_size
            if size > 0 and size == last_size:
                stable_hits += 1
                if stable_hits >= 2:
                    return True
            else:
                stable_hits = 0
            last_size = size
        time.sleep(poll_s)
    return path.is_file() and path.stat().st_size > 0


def _html_to_pdf(html_path: Path, pdf_path: Path, browser: str) -> tuple[bool, str]:
    """Imprime `html_path` en PDF via le navigateur headless."""
    profile_dir = tempfile.mkdtemp(prefix="antigravity_pdf_profile_")
    try:
        uri = html_path.resolve().as_uri()
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-extensions",
            f"--user-data-dir={profile_dir}",
            f"--print-to-pdf={pdf_path}",
            "--print-to-pdf-no-header",
            "--no-pdf-header-footer",
            uri,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=90,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        except subprocess.TimeoutExpired:
            return False, "Le navigateur n'a pas répondu (délai dépassé)."
        except Exception as exc:
            return False, f"Échec de lancement du navigateur : {exc}"

        # Le process peut rendre la main avant d'avoir fini d'écrire le PDF
        # (cf. docstring de `_wait_for_stable_file`) : on patiente sur le
        # fichier plutôt que sur le seul code de retour du process.
        if not _wait_for_stable_file(pdf_path):
            err = (proc.stderr or proc.stdout or "").strip()[-500:]
            return False, f"Le navigateur n'a produit aucun PDF. {err}"
        return True, str(pdf_path)
    finally:
        # Best-effort : le profil peut rester brièvement verrouillé si un
        # sous-processus Edge traîne encore un instant après l'écriture du
        # PDF (cf. ci-dessus). Ne jamais faire échouer l'export pour ça.
        shutil.rmtree(profile_dir, ignore_errors=True)


# --- Assemblage du document HTML complet ------------------------------------
def _build_full_html(project_name: str, convs, export_date: str) -> tuple[str, int]:
    """Construit le document HTML complet (couverture + TOC + sections +
    annexe). Retourne (html, nb_conversations)."""
    conv_list = list(convs)

    toc_items = []
    for i, c in enumerate(conv_list, 1):
        t = getattr(c, "title", "") or ""
        ft, _dt = get_transcript_info(c.conv_id)
        toc_items.append(f"<li>{i}. {_html.escape(t or ft or c.conv_id[:12])}</li>")

    sections: list[str] = []
    annex_all: list[tuple[str, str | None, str]] = []
    for c in conv_list:
        brain_p = _find_brain_path(c.conv_id)
        disp, body_html, annex = _conversation_body_html(c, brain_p)
        annex_all.extend(annex)
        sections.append(body_html)

    annex_ok = [a for a in annex_all if a[1] is not None]
    annex_html = ""
    if annex_ok:
        rows = []
        for cap, uri, name in annex_ok:
            rows.append(f'<img src="{uri}"/>')
            rows.append(f'<div class="imgcap">{_html.escape(cap)} — {_html.escape(name)}</div>')
        annex_html = (
            '<div class="conv-section"><h1>Annexe — Images</h1>' + "".join(rows) + "</div>"
        )

    header_text = _html.escape(f"{project_name}")

    cover_img_path = _find_cover_image(project_name)
    cover_img_uri = _image_data_uri(cover_img_path, _COVER_MAX_WIDTH) if cover_img_path else None
    cover_img_html = f'<img class="cover-img" src="{cover_img_uri}"/>' if cover_img_uri else ""

    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<style>
  :root {{ --hdr: "{header_text}"; --date: "{_html.escape(export_date)}"; }}
  {_PAGE_CSS}
  .cover {{ page: cover; height: 297mm; display: flex; flex-direction: column;
            align-items: center; justify-content: center; text-align: center;
            font-family: 'Segoe UI', Arial, sans-serif; break-after: page; }}
  .cover h1 {{ font-size: 30pt; color: #6d28d9; margin: 0 0 10pt 0; }}
  .cover p {{ color: #64748b; font-size: 12pt; margin: 2pt 0; }}
  .cover-img {{ max-width: {_COVER_MAX_WIDTH}px; max-height: 120mm; margin: 4pt 0 14pt 0;
                border-radius: 8px; }}
  .toc {{ break-after: page; }}
</style>
{_BODY_CSS}
</head>
<body>
  <div class="cover">
    <h1>{_html.escape(project_name)}</h1>
    {cover_img_html}
    <p>{len(conv_list)} conversation(s)</p>
    <p>Exporté le {_html.escape(export_date)}</p>
  </div>
  <div class="toc">
    <h1>Table des matières</h1>
    <ol>{"".join(toc_items)}</ol>
  </div>
  {"".join(sections)}
  {annex_html}
</body>
</html>"""
    return html, len(conv_list)


# --- API publique -----------------------------------------------------------
def export_project_to_pdf(project_name: str, convs, pdf_path: str | Path) -> tuple[bool, str]:
    """Génère le PDF de toutes les conversations `convs` du projet (moteur
    Edge/Chromium headless).

    Retourne (ok, chemin | message).
    """
    pdf_path = Path(pdf_path)
    try:
        browser = _find_browser()
        if not browser:
            return False, (
                "Aucun navigateur (Edge/Chrome) détecté sur cette machine. "
                "L'export PDF nécessite Microsoft Edge ou Google Chrome installé."
            )

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        export_date = datetime.now().strftime("%Y-%m-%d %H:%M")
        html, _n = _build_full_html(project_name, convs, export_date)

        with tempfile.TemporaryDirectory(prefix="antigravity_pdf_html_") as tmpdir:
            html_path = Path(tmpdir) / "export.html"
            html_path.write_text(html, encoding="utf-8")
            ok, msg = _html_to_pdf(html_path, pdf_path, browser)
            if not ok:
                return False, f"Échec de l'export PDF : {msg}"

        logger.debug("PDF projet %s -> %s (html/%s)", project_name, pdf_path, Path(browser).name)
        return True, str(pdf_path)
    except Exception as exc:
        logger.warning("Échec export PDF %s : %s", project_name, exc)
        return False, f"Échec de l'export PDF : {exc}"
