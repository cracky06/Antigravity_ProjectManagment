"""test_pdf_export.py — Export PDF d'un projet (v2.4, moteur Edge/Chromium headless)."""

import datetime

import pytest


@pytest.fixture(autouse=True)
def _need_qapp(qapp):
    """QImage exige un QApplication (fourni par conftest)."""
    yield


class _Conv:
    def __init__(self, cid, title="", project="P"):
        self.conv_id = cid
        self.title = title
        self.project = project


@pytest.fixture
def stub(monkeypatch):
    import pdf_export_html as pe
    import data_loader as dl

    msgs = {
        "c1": [
            {"role": "user", "text": "Fais X", "timestamp": "10:00", "epoch": 100.0},
            {"role": "model", "text": "## OK\n\nVoici **X**.\n- a\n- b", "timestamp": "10:01", "epoch": 110.0},
        ],
        "c2": [
            {"role": "user", "text": "Et Y ?", "timestamp": "11:00", "epoch": 200.0},
            {"role": "model", "text": "Voir [config.py](file:///E:/Dev/P/config.py).", "timestamp": "11:01", "epoch": 210.0},
        ],
    }
    monkeypatch.setattr(pe, "load_chat_messages", lambda cid: list(msgs.get(cid, [])))
    monkeypatch.setattr(pe, "get_transcript_info",
                        lambda cid: (f"T-{cid}", datetime.datetime(2026, 1, 15, 10, 0)))
    monkeypatch.setattr(pe, "_find_brain_path", lambda cid: None)
    monkeypatch.setattr(dl, "get_projects_root", lambda: __import__("pathlib").Path("E:/Dev"))
    return pe


@pytest.fixture
def fake_browser(monkeypatch):
    """Simule le navigateur headless : évite de dépendre d'Edge/Chrome en CI
    et de payer le coût d'un vrai lancement de processus à chaque test."""
    import pdf_export_html as pe

    monkeypatch.setattr(pe, "_find_browser", lambda: "fake-browser.exe")

    def _fake_print(html_path, pdf_path, browser):
        # Un vrai PDF minimal (en-tête %PDF- suffisant pour nos assertions).
        pdf_path.write_bytes(b"%PDF-1.7\n%fake\n%%EOF")
        return True, str(pdf_path)

    monkeypatch.setattr(pe, "_html_to_pdf", _fake_print)
    return pe


def test_pdf_is_generated(stub, fake_browser, tmp_path):
    out = tmp_path / "projet.pdf"
    ok, res = stub.export_project_to_pdf("MonProjet", [_Conv("c1", "A"), _Conv("c2", "B")], out)
    assert ok is True
    assert out.is_file()
    assert out.read_bytes()[:5] == b"%PDF-"


def test_pdf_empty_project_list(stub, fake_browser, tmp_path):
    out = tmp_path / "vide.pdf"
    ok, res = stub.export_project_to_pdf("Vide", [], out)
    assert ok is True
    assert out.read_bytes()[:5] == b"%PDF-"


def test_pdf_creates_parent_dirs(stub, fake_browser, tmp_path):
    out = tmp_path / "a" / "b" / "p.pdf"
    ok, _res = stub.export_project_to_pdf("P", [_Conv("c1", "T")], out)
    assert ok and out.is_file()


def test_pdf_no_browser_found(stub, monkeypatch, tmp_path):
    import pdf_export_html as pe

    monkeypatch.setattr(pe, "_find_browser", lambda: None)
    ok, msg = pe.export_project_to_pdf("P", [_Conv("c1", "T")], tmp_path / "x.pdf")
    assert ok is False
    assert "navigateur" in msg.lower()


def test_pdf_reports_browser_failure(stub, monkeypatch, tmp_path):
    import pdf_export_html as pe

    monkeypatch.setattr(pe, "_find_browser", lambda: "fake-browser.exe")
    monkeypatch.setattr(pe, "_html_to_pdf", lambda h, p, b: (False, "boom"))
    ok, msg = pe.export_project_to_pdf("P", [_Conv("c1", "T")], tmp_path / "x.pdf")
    assert ok is False
    assert "Échec de l'export PDF" in msg


def test_img_data_uri_size_guard(stub, tmp_path):
    big = tmp_path / "big.png"
    big.write_bytes(b"\x00" * (stub._MAX_RAW_BYTES + 1))
    assert stub._image_data_uri(big) is None


def test_md_to_html_fallback():
    import pdf_export_html as pe

    html = pe._md_to_html("## Titre\n\ndu **gras**")
    assert "gras" in html


def test_build_full_html_contains_sections(stub):
    import pdf_export_html as pe

    html, n = pe._build_full_html("MonProjet", [_Conv("c1", "A"), _Conv("c2", "B")], "2026-01-15 10:00")
    assert n == 2
    assert "MonProjet" in html
    assert "Table des matières" in html
    assert "conv-section" in html
    assert "@page" in html


@pytest.mark.skipif(True, reason="Intégration réelle : lance Edge/Chrome, à activer manuellement en local.")
def test_pdf_real_browser_integration(stub, tmp_path):
    """Test d'intégration réel (non exécuté en CI) : vérifie qu'un vrai
    navigateur headless produit bien un PDF exploitable."""
    import pdf_export_html as pe

    out = tmp_path / "reel.pdf"
    ok, res = pe.export_project_to_pdf("MonProjet", [_Conv("c1", "A")], out)
    assert ok is True
    assert out.stat().st_size > 1000


# --- Visuel de couverture (v2.4) --------------------------------------------
def _make_png(path):
    """Un vrai PNG minimal 1x1 (QImage doit pouvoir le charger)."""
    from PyQt6.QtGui import QImage
    from PyQt6.QtCore import Qt

    img = QImage(4, 4, QImage.Format.Format_RGB32)
    img.fill(Qt.GlobalColor.blue)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert img.save(str(path), "PNG")


@pytest.fixture
def cover_root(tmp_path, monkeypatch):
    import data_loader as dl
    import pdf_export_html as pe

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(dl, "get_projects_root", lambda: root)
    monkeypatch.setattr(pe, "get_projects_root", lambda: root)
    return root


def test_cover_image_prefers_background_over_splash(cover_root):
    import pdf_export_html as pe

    proj = cover_root / "MonProjet"
    _make_png(proj / "assets" / "splash.png")
    _make_png(proj / "assets" / "background.png")
    hit = pe._find_cover_image("MonProjet")
    assert hit.name == "background.png"


def test_cover_image_falls_back_to_logo_keyword(cover_root):
    import pdf_export_html as pe

    proj = cover_root / "MonProjet"
    _make_png(proj / "assets" / "some_logo_title_1.png")
    hit = pe._find_cover_image("MonProjet")
    assert hit.name == "some_logo_title_1.png"


def test_cover_image_falls_back_to_project_name(cover_root):
    import pdf_export_html as pe

    proj = cover_root / "MonProjet"
    _make_png(proj / "assets" / "MonProjet_icon.png")
    hit = pe._find_cover_image("MonProjet")
    assert hit.name == "MonProjet_icon.png"


def test_cover_image_searches_nested_assets_dirs(cover_root):
    """Cas Naturalchimie2 : le dossier assets n'est pas <projet>/assets/
    directement mais un sous-dossier (dist/assets, public/assets, …)."""
    import pdf_export_html as pe

    proj = cover_root / "MonProjet"
    _make_png(proj / "public" / "assets" / "splash_screen.png")
    hit = pe._find_cover_image("MonProjet")
    assert hit.name == "splash_screen.png"


def test_cover_image_excludes_node_modules(cover_root):
    import pdf_export_html as pe

    proj = cover_root / "MonProjet"
    _make_png(proj / "node_modules" / "somepkg" / "assets" / "background.png")
    hit = pe._find_cover_image("MonProjet")
    assert hit is None


def test_cover_image_none_when_nothing_matches(cover_root):
    import pdf_export_html as pe

    proj = cover_root / "MonProjet"
    (proj / "assets").mkdir(parents=True)
    (proj / "assets" / "unrelated.png").touch()
    # Aucune correspondance : ni background/splash/logo, ni nom du projet, ni .ico
    hit = pe._find_cover_image("MonProjet")
    assert hit is None


def test_build_full_html_embeds_cover_image(cover_root, stub):
    import pdf_export_html as pe

    proj = cover_root / "MonProjet"
    _make_png(proj / "assets" / "background.png")
    html, _n = pe._build_full_html("MonProjet", [_Conv("c1", "A")], "2026-01-15 10:00")
    assert "cover-img" in html
    assert "data:image/" in html


# --- Attente de stabilisation du fichier (course PDF async, v2.4) ----------
def test_wait_for_stable_file_detects_late_write(tmp_path):
    """Reproduit la course observée avec Edge headless : le fichier n'existe
    pas encore quand le process appelant a rendu la main."""
    import threading
    import time
    import pdf_export_html as pe

    target = tmp_path / "late.pdf"

    def _write_later():
        time.sleep(0.3)
        target.write_bytes(b"%PDF-1.7 partial")
        time.sleep(0.15)
        target.write_bytes(b"%PDF-1.7 partial complete")

    threading.Thread(target=_write_later, daemon=True).start()
    assert pe._wait_for_stable_file(target, timeout_s=5.0, poll_s=0.05) is True
    assert target.read_bytes() == b"%PDF-1.7 partial complete"


def test_wait_for_stable_file_times_out_when_never_written(tmp_path):
    import pdf_export_html as pe

    target = tmp_path / "never.pdf"
    assert pe._wait_for_stable_file(target, timeout_s=0.3, poll_s=0.05) is False
