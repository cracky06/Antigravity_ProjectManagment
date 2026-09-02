#!/usr/bin/env python3
"""antigravity_manager.py — Application graphique Antigravity Project & Chat Manager.

Version optimisée & fluide :
- Redimensionnement interactif complet (séparateur glissant entre sidebar et chat)
- Rendu instantané du chat (début tout en haut, zéro latence)
- Bouton « ⚙️ Paramètres » très visible avec affichage en clair du dossier projet actif
- Dialogue de configuration des dossiers avec explorateur
- Arborescence projets & conversations avec vrais titres officiels et timestamps relatifs
- Suppression en cascade (projet + conversations)
"""

import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk

from config import load_config, save_config, get_projects_root, get_antigravity_root
from data_loader import (
    ConversationInfo,
    build_project_map,
    delete_project_cascade,
    load_chat_messages,
    get_paths,
)

# -----------------------------------------------------------------
# Thème & Couleurs (Fidèle à Antigravity)
# -----------------------------------------------------------------
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

BG_SIDEBAR = "#F8F9FA"
BG_MAIN = "#FFFFFF"
BG_HOVER = "#EDEDF0"
BG_SELECTED = "#E2E7F0"
BG_CODE = "#F1F3F5"

FG_PRIMARY = "#1F1F1F"
FG_SECONDARY = "#5F6368"
FG_MUTED = "#80868B"
FG_USER = "#0B57D0"
FG_AI = "#1E1E1E"

SEPARATOR_COLOR = "#E0E0E0"
FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"


# =================================================================
# Dialogue : Paramètres de l'application
# =================================================================
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_save_callback):
        super().__init__(parent)
        self.title("Paramètres des Emplacements — Antigravity Manager")
        self.geometry("680x360")
        self.minsize(580, 320)
        self.transient(parent)
        self.grab_set()

        self._on_save_callback = on_save_callback
        self.config_data = load_config()

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)

        # Titre
        ctk.CTkLabel(
            self,
            text="⚙️ Configuration des Dossiers",
            font=(FONT_FAMILY, 16, "bold"),
            text_color=FG_PRIMARY,
        ).grid(row=0, column=0, columnspan=3, padx=20, pady=(20, 10), sticky="w")

        # 1. Dossier Projets
        ctk.CTkLabel(
            self,
            text="Dossier Projets :",
            font=(FONT_FAMILY, 12, "bold"),
            text_color=FG_PRIMARY,
        ).grid(row=1, column=0, padx=(20, 10), pady=12, sticky="w")

        self.proj_entry = ctk.CTkEntry(self, font=(FONT_FAMILY, 11), height=34)
        self.proj_entry.grid(row=1, column=1, padx=(0, 10), pady=12, sticky="ew")
        self.proj_entry.insert(0, self.config_data.get("projects_root", r"D:\DEV"))

        btn_browse_proj = ctk.CTkButton(
            self,
            text="📁 Parcourir...",
            width=110,
            height=34,
            font=(FONT_FAMILY, 11),
            command=self._browse_projects,
        )
        btn_browse_proj.grid(row=1, column=2, padx=(0, 20), pady=12)

        # 2. Dossier Antigravity Data
        ctk.CTkLabel(
            self,
            text="Données Antigravity :",
            font=(FONT_FAMILY, 12, "bold"),
            text_color=FG_PRIMARY,
        ).grid(row=2, column=0, padx=(20, 10), pady=12, sticky="w")

        self.ag_entry = ctk.CTkEntry(self, font=(FONT_FAMILY, 11), height=34)
        self.ag_entry.grid(row=2, column=1, padx=(0, 10), pady=12, sticky="ew")
        self.ag_entry.insert(0, self.config_data.get("antigravity_root", ""))

        btn_browse_ag = ctk.CTkButton(
            self,
            text="📁 Parcourir...",
            width=110,
            height=34,
            font=(FONT_FAMILY, 11),
            command=self._browse_antigravity,
        )
        btn_browse_ag.grid(row=2, column=2, padx=(0, 20), pady=12)

        # Explications
        ctk.CTkLabel(
            self,
            text="• Dossier Projets : répertoire racine où sont stockés vos projets de développement (ex: D:\\DEV)\n"
                 "• Données Antigravity : emplacement où Antigravity enregistre l'historique (%USERPROFILE%\\.gemini\\antigravity)",
            font=(FONT_FAMILY, 10),
            text_color=FG_MUTED,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, padx=20, pady=(6, 16), sticky="w")

        # Boutons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, columnspan=3, padx=20, pady=(10, 16), sticky="e")

        ctk.CTkButton(
            btn_frame,
            text="Annuler",
            width=90,
            height=32,
            font=(FONT_FAMILY, 11),
            fg_color=BG_HOVER,
            hover_color=BG_SELECTED,
            text_color=FG_PRIMARY,
            command=self.destroy,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="Enregistrer",
            width=110,
            height=32,
            font=(FONT_FAMILY, 11, "bold"),
            command=self._save,
        ).pack(side="left")

    def _browse_projects(self):
        cur = self.proj_entry.get().strip()
        d = filedialog.askdirectory(initialdir=cur, title="Sélectionner le dossier racine des Projets")
        if d:
            self.proj_entry.delete(0, "end")
            self.proj_entry.insert(0, d.replace("/", "\\"))

    def _browse_antigravity(self):
        cur = self.ag_entry.get().strip()
        d = filedialog.askdirectory(initialdir=cur, title="Sélectionner le dossier des données Antigravity")
        if d:
            self.ag_entry.delete(0, "end")
            self.ag_entry.insert(0, d.replace("/", "\\"))

    def _save(self):
        new_proj = self.proj_entry.get().strip()
        new_ag = self.ag_entry.get().strip()

        if not new_proj:
            messagebox.showerror("Erreur", "Le dossier projets est obligatoire.")
            return

        self.config_data["projects_root"] = new_proj
        if new_ag:
            self.config_data["antigravity_root"] = new_ag

        save_config(self.config_data)
        self.destroy()
        if self._on_save_callback:
            self._on_save_callback()


# =================================================================
# Application Principale Antigravity Manager
# =================================================================
class AntigravityManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Antigravity Manager — Project & Chat Management")
        self.geometry("1240x840")
        self.minsize(800, 500)
        self.configure(fg_color=BG_MAIN)

        # État
        self.project_convs: dict[str, list[ConversationInfo]] = {}
        self.all_convs: list[ConversationInfo] = []
        self.expanded_projects: set[str] = set()
        self.conv_widgets: dict[str, list[tuple[ctk.CTkFrame, ctk.CTkLabel]]] = {}
        self.selected_conv: ConversationInfo | None = None

        self._build_ui()
        self.reload_data()

    # -------------------------------------------------------------
    # Construction de l'interface avec PanedWindow (redimensionnable)
    # -------------------------------------------------------------
    def _build_ui(self):
        # Grille principale : Ligne 0 = PanedWindow (Sidebar + Chat), Ligne 1 = Status bar
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        # ---------------------------------------------------------
        # PanedWindow horizontal : Séparateur déplaçable à la souris
        # ---------------------------------------------------------
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TPanedwindow", background=SEPARATOR_COLOR)
        style.configure("Sash", sashthickness=5, gripcount=0, background=SEPARATOR_COLOR)

        self.paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.paned.grid(row=0, column=0, sticky="nsew")

        # =========================================================
        # 1. VOLET GAUCHE : SIDEBAR
        # =========================================================
        self.sidebar_frame = ctk.CTkFrame(
            self.paned,
            fg_color=BG_SIDEBAR,
            corner_radius=0,
            border_width=0,
            width=340,
        )
        self.paned.add(self.sidebar_frame, weight=0)
        self.sidebar_frame.grid_rowconfigure(2, weight=1)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        # En-tête Sidebar : Titre + Boutons
        sb_header = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        sb_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        sb_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            sb_header,
            text="Antigravity",
            font=(FONT_FAMILY, 15, "bold"),
            text_color=FG_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        btn_box = ctk.CTkFrame(sb_header, fg_color="transparent")
        btn_box.grid(row=0, column=1, sticky="e")

        self.btn_settings = ctk.CTkButton(
            btn_box,
            text="⚙️ Paramètres",
            width=100,
            height=28,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color="#E8EEF9",
            hover_color=BG_SELECTED,
            text_color=FG_USER,
            command=self._open_settings,
        )
        self.btn_settings.pack(side="left", padx=(0, 4))

        self.btn_refresh = ctk.CTkButton(
            btn_box,
            text="🔄",
            width=32,
            height=28,
            font=(FONT_FAMILY, 12),
            fg_color="transparent",
            hover_color=BG_HOVER,
            text_color=FG_SECONDARY,
            command=self.reload_data,
        )
        self.btn_refresh.pack(side="left")

        # Bandeau affichant le chemin du dossier projet actif
        self.path_badge = ctk.CTkFrame(self.sidebar_frame, fg_color="#EBECEF", corner_radius=4, height=24)
        self.path_badge.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.path_badge.grid_columnconfigure(0, weight=1)

        self.path_badge_label = ctk.CTkLabel(
            self.path_badge,
            text="Dossier : D:\\DEV",
            font=(FONT_FAMILY, 9),
            text_color=FG_SECONDARY,
            anchor="w",
        )
        self.path_badge_label.grid(row=0, column=0, padx=8, pady=2, sticky="w")

        # Arborescence scrollable
        self.tree_scroll = ctk.CTkScrollableFrame(
            self.sidebar_frame,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=SEPARATOR_COLOR,
        )
        self.tree_scroll.grid(row=2, column=0, sticky="nsew", padx=2, pady=0)
        self.tree_scroll.grid_columnconfigure(0, weight=1)

        # =========================================================
        # 2. VOLET DROIT : CHAT VIEWER
        # =========================================================
        self.chat_container = ctk.CTkFrame(
            self.paned,
            fg_color=BG_MAIN,
            corner_radius=0,
        )
        self.paned.add(self.chat_container, weight=1)
        self.chat_container.grid_rowconfigure(2, weight=1)
        self.chat_container.grid_columnconfigure(0, weight=1)

        # En-tête du Chat
        self.chat_header = ctk.CTkFrame(self.chat_container, fg_color=BG_MAIN, height=56)
        self.chat_header.grid(row=0, column=0, sticky="ew", padx=18, pady=(8, 4))
        self.chat_header.grid_columnconfigure(0, weight=1)

        self.chat_title_label = ctk.CTkLabel(
            self.chat_header,
            text="Sélectionnez une conversation",
            font=(FONT_FAMILY, 15, "bold"),
            anchor="w",
            text_color=FG_PRIMARY,
        )
        self.chat_title_label.grid(row=0, column=0, sticky="w")

        self.chat_meta_label = ctk.CTkLabel(
            self.chat_header,
            text="Cliquez sur une conversation à gauche pour afficher les échanges.",
            font=(FONT_FAMILY, 11),
            anchor="w",
            text_color=FG_SECONDARY,
        )
        self.chat_meta_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Actions d'en-tête
        self.chat_actions = ctk.CTkFrame(self.chat_header, fg_color="transparent")
        self.chat_actions.grid(row=0, column=1, rowspan=2, sticky="e")

        self.btn_copy_id = ctk.CTkButton(
            self.chat_actions,
            text="📋 Copier ID",
            width=80,
            height=28,
            font=(FONT_FAMILY, 11),
            fg_color=BG_HOVER,
            hover_color=BG_SELECTED,
            text_color=FG_PRIMARY,
            command=self._copy_current_conv_id,
        )
        self.btn_copy_id.pack(side="left", padx=4)

        self.btn_delete_chat = ctk.CTkButton(
            self.chat_actions,
            text="🗑️ Supprimer",
            width=85,
            height=28,
            font=(FONT_FAMILY, 11),
            fg_color="#FEE2E2",
            hover_color="#FCA5A5",
            text_color="#DC2626",
            command=self._delete_current_conv,
        )
        self.btn_delete_chat.pack(side="left", padx=4)

        # Séparateur sous l'en-tête
        ctk.CTkFrame(
            self.chat_container,
            fg_color=SEPARATOR_COLOR,
            height=1,
            corner_radius=0,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 2))

        # Zone d'affichage du Chat ultra-rapide
        chat_text_frame = tk.Frame(self.chat_container, bg=BG_MAIN)
        chat_text_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(4, 8))
        chat_text_frame.grid_rowconfigure(0, weight=1)
        chat_text_frame.grid_columnconfigure(0, weight=1)

        chat_scroll = ttk.Scrollbar(chat_text_frame, orient=tk.VERTICAL)
        chat_scroll.grid(row=0, column=1, sticky="ns")

        self.chat_text = tk.Text(
            chat_text_frame,
            wrap=tk.WORD,
            bg=BG_MAIN,
            fg=FG_PRIMARY,
            font=(FONT_FAMILY, 11),
            relief=tk.FLAT,
            padx=16,
            pady=16,
            yscrollcommand=chat_scroll.set,
            cursor="arrow",
        )
        self.chat_text.grid(row=0, column=0, sticky="nsew")
        chat_scroll.config(command=self.chat_text.yview)

        # Configuration des styles / tags dans le Text widget
        self.chat_text.tag_config("user_box", background="#F0F4F9", lmargin1=10, lmargin2=10, rmargin=10, spacing1=4, spacing3=4)
        self.chat_text.tag_config("user_title", font=(FONT_FAMILY, 11, "bold"), foreground=FG_USER)
        self.chat_text.tag_config("user_text", font=(FONT_FAMILY, 11), foreground=FG_PRIMARY)
        self.chat_text.tag_config("model_title", font=(FONT_FAMILY, 11, "bold"), foreground=FG_AI)
        self.chat_text.tag_config("model_text", font=(FONT_FAMILY, 11), foreground=FG_PRIMARY)
        self.chat_text.tag_config("time_tag", font=(FONT_FAMILY, 9), foreground=FG_MUTED)
        self.chat_text.tag_config("sep_tag", font=(FONT_FAMILY, 4), foreground=SEPARATOR_COLOR)
        self.chat_text.tag_config("empty_tag", font=(FONT_FAMILY, 12, "italic"), foreground=FG_MUTED, justify="center")

        # =========================================================
        # 3. STATUS BAR (Bas)
        # =========================================================
        self.status_bar = ctk.CTkLabel(
            self,
            text="Prêt",
            font=(FONT_FAMILY, 10),
            anchor="w",
            fg_color="#EBECEF",
            text_color=FG_MUTED,
            height=22,
        )
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

    # -------------------------------------------------------------
    # Paramètres
    # -------------------------------------------------------------
    def _open_settings(self):
        SettingsDialog(self, on_save_callback=self.reload_data)

    # -------------------------------------------------------------
    # Chargement des données
    # -------------------------------------------------------------
    def reload_data(self):
        projects_root, _, _, _, _ = get_paths()
        self.path_badge_label.configure(text=f"Dossier : {projects_root}")
        self.status_bar.configure(text="Chargement des données Antigravity...")
        self.update_idletasks()

        self.project_convs, self.all_convs = build_project_map()
        if not self.expanded_projects:
            self.expanded_projects = {p for p, convs in self.project_convs.items() if len(convs) > 0}
        self._render_tree()

        if self.selected_conv:
            found = False
            for c in self.all_convs:
                if c.conv_id == self.selected_conv.conv_id:
                    self.display_chat(c)
                    found = True
                    break
            if not found:
                self._clear_chat_viewer()
        else:
            self._clear_chat_viewer()

        total_p = len(self.project_convs)
        total_c = len(self.all_convs)
        self.status_bar.configure(text=f"Racine : {projects_root} | {total_p} projets — {total_c} conversations")

    # -------------------------------------------------------------
    # Arborescence latérale (Optimisée)
    # -------------------------------------------------------------
    def _render_tree(self):
        self.conv_widgets.clear()
        for w in self.tree_scroll.winfo_children():
            w.destroy()

        # Section 1 : Projects
        proj_sec = ctk.CTkFrame(self.tree_scroll, fg_color="transparent")
        proj_sec.pack(fill="x", padx=4, pady=(2, 2))
        proj_sec.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            proj_sec,
            text="Projects",
            font=(FONT_FAMILY, 12, "bold"),
            text_color=FG_SECONDARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=6)

        for proj_name in sorted(self.project_convs.keys(), key=str.lower):
            convs = self.project_convs[proj_name]
            count = len(convs)
            is_expanded = proj_name in self.expanded_projects and count > 0

            # Ligne de projet
            p_frame = ctk.CTkFrame(self.tree_scroll, fg_color="transparent", corner_radius=5, height=30)
            p_frame.pack(fill="x", padx=2, pady=1)
            p_frame.grid_columnconfigure(1, weight=1)

            if count > 0:
                chevron = "▼ " if is_expanded else "▶ "
                icon_txt = chevron + ("📂" if is_expanded else "📁")
            else:
                icon_txt = "   📁"

            icon_lbl = ctk.CTkLabel(p_frame, text=icon_txt, font=(FONT_FAMILY, 11), width=32, text_color=FG_SECONDARY)
            icon_lbl.grid(row=0, column=0, padx=(4, 2), pady=2)

            name_lbl = ctk.CTkLabel(p_frame, text=proj_name, font=(FONT_FAMILY, 11), anchor="w", text_color=FG_PRIMARY)
            name_lbl.grid(row=0, column=1, padx=2, pady=2, sticky="w")

            if count > 0:
                cnt_lbl = ctk.CTkLabel(p_frame, text=str(count), font=(FONT_FAMILY, 10, "bold"), text_color=FG_MUTED, anchor="e")
                cnt_lbl.grid(row=0, column=2, padx=(0, 8), pady=2, sticky="e")

            # Actions Clic
            def make_toggle(pname=proj_name, c_cnt=count):
                return lambda e: self._toggle_project_click(pname, c_cnt)

            def make_rclick_proj(pname=proj_name, pconvs=convs):
                return lambda e: self._on_project_context_menu(e, pname, pconvs)

            for w in (p_frame, icon_lbl, name_lbl):
                w.bind("<Button-1>", make_toggle())
                w.bind("<Button-3>", make_rclick_proj())
                w.bind("<Enter>", lambda e, f=p_frame: f.configure(fg_color=BG_HOVER))
                w.bind("<Leave>", lambda e, f=p_frame: f.configure(fg_color="transparent"))

            # Conversations imbriquées si déplié (et seulement si non vide)
            if is_expanded:
                for c_info in convs:
                    self._create_conv_widget(c_info, indent=True)

        # Séparateur
        sep = ctk.CTkFrame(self.tree_scroll, fg_color=SEPARATOR_COLOR, height=1, corner_radius=0)
        sep.pack(fill="x", padx=8, pady=(12, 6))

        # Section 2 : Conversations Récentes
        conv_sec = ctk.CTkFrame(self.tree_scroll, fg_color="transparent")
        conv_sec.pack(fill="x", padx=4, pady=(2, 2))
        conv_sec.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            conv_sec,
            text="Conversations ▾",
            font=(FONT_FAMILY, 12, "bold"),
            text_color=FG_SECONDARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=6)

        for c_info in self.all_convs[:40]:
            self._create_conv_widget(c_info, indent=False)

    def _create_conv_widget(self, c_info: ConversationInfo, indent: bool):
        is_sel = bool(self.selected_conv and self.selected_conv.conv_id == c_info.conv_id)
        bg = BG_SELECTED if is_sel else "transparent"

        c_frame = ctk.CTkFrame(self.tree_scroll, fg_color=bg, corner_radius=5, height=28)
        c_frame.pack(fill="x", padx=2, pady=1)
        c_frame.grid_columnconfigure(0, weight=1)

        pad_left = 28 if indent else 8
        display_title = c_info.title if c_info.title else c_info.conv_id[:12]
        if len(display_title) > 34:
            display_title = display_title[:32] + "…"

        title_col = FG_USER if is_sel else FG_PRIMARY
        title_lbl = ctk.CTkLabel(
            c_frame,
            text=display_title,
            font=(FONT_FAMILY, 11),
            anchor="w",
            text_color=title_col,
        )
        title_lbl.grid(row=0, column=0, padx=(pad_left, 4), pady=2, sticky="w")

        # Enregistrer dans le cache de widgets pour mise à jour rapide de la sélection
        self.conv_widgets.setdefault(c_info.conv_id, []).append((c_frame, title_lbl))

        if c_info.rel_time:
            time_lbl = ctk.CTkLabel(
                c_frame,
                text=c_info.rel_time,
                font=(FONT_FAMILY, 10),
                anchor="e",
                text_color=FG_MUTED,
            )
            time_lbl.grid(row=0, column=1, padx=(2, 8), pady=2, sticky="e")

        def on_click(e, info=c_info):
            self.display_chat(info)

        def on_rclick(e, info=c_info):
            self._on_conv_context_menu(e, info)

        for w in (c_frame, title_lbl):
            w.bind("<Button-1>", on_click)
            w.bind("<Button-3>", on_rclick)
            def make_hover(f=c_frame, cid=c_info.conv_id):
                return lambda e: f.configure(fg_color=BG_HOVER) if not (self.selected_conv and self.selected_conv.conv_id == cid) else None
            def make_leave(f=c_frame, cid=c_info.conv_id):
                return lambda e: f.configure(fg_color=BG_SELECTED if (self.selected_conv and self.selected_conv.conv_id == cid) else "transparent")
            w.bind("<Enter>", make_hover())
            w.bind("<Leave>", make_leave())

    def _toggle_project_click(self, project_name: str, count: int):
        if count == 0:
            return  # Dossier vide : aucun espace vide créé
        if project_name in self.expanded_projects:
            self.expanded_projects.remove(project_name)
        else:
            self.expanded_projects.add(project_name)
        self._render_tree()

    # -------------------------------------------------------------
    # Affichage instantané du Chat (Commence TOUT EN HAUT)
    # -------------------------------------------------------------
    def display_chat(self, info: ConversationInfo):
        # Mise à jour visuelle légère sans reconstruire l'arbre complet
        old_id = self.selected_conv.conv_id if self.selected_conv else None
        self.selected_conv = info

        if old_id and old_id in self.conv_widgets:
            for frame, lbl in self.conv_widgets[old_id]:
                try:
                    frame.configure(fg_color="transparent")
                    lbl.configure(text_color=FG_PRIMARY)
                except Exception:
                    pass

        if info.conv_id in self.conv_widgets:
            for frame, lbl in self.conv_widgets[info.conv_id]:
                try:
                    frame.configure(fg_color=BG_SELECTED)
                    lbl.configure(text_color=FG_USER)
                except Exception:
                    pass

        title_text = info.title if info.title else "Conversation sans titre"
        self.chat_title_label.configure(text=title_text)

        proj_str = f"📁 {info.project}" if info.project else "📁 (aucun projet)"
        date_str = info.last_activity.strftime("%d/%m/%Y à %H:%M") if info.last_activity else "Date inconnue"
        self.chat_meta_label.configure(text=f"{proj_str}   •   {date_str}   •   ID: {info.conv_id}")

        # Effacer et repeupler le Text widget instantanément
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)

        messages = load_chat_messages(info.conv_id)

        if not messages:
            self.chat_text.insert(
                tk.END,
                "\n\n\nℹ️ Aucun message textuel dans les journaux.\n\n"
                "Cette session correspond probablement à une sous-tâche technique (subagent)\n"
                "ou ses journaux ont été archivés.\n",
                "empty_tag",
            )
            self.chat_text.config(state=tk.DISABLED)
            self.chat_text.yview_moveto(0.0)
            return

        for msg in messages:
            role = msg.get("role")
            text = msg.get("text", "").strip()
            ts = msg.get("timestamp", "")

            if role == "user":
                header_str = f"👤 Utilisateur   {ts}\n" if ts else "👤 Utilisateur\n"
                self.chat_text.insert(tk.END, header_str, "user_title")
                self.chat_text.insert(tk.END, f"{text}\n\n", "user_text")
            elif role == "model":
                header_str = f"✨ Antigravity   {ts}\n" if ts else "✨ Antigravity\n"
                self.chat_text.insert(tk.END, header_str, "model_title")
                self.chat_text.insert(tk.END, f"{text}\n\n", "model_text")

            self.chat_text.insert(tk.END, "─" * 60 + "\n\n", "sep_tag")

        self.chat_text.config(state=tk.DISABLED)
        # Positionnement forcé au début tout en haut
        self.chat_text.yview_moveto(0.0)

    def _clear_chat_viewer(self):
        self.selected_conv = None
        self.chat_title_label.configure(text="Sélectionnez une conversation")
        self.chat_meta_label.configure(text="Cliquez sur une conversation à gauche pour afficher les échanges.")
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete("1.0", tk.END)
        self.chat_text.config(state=tk.DISABLED)

    def _copy_current_conv_id(self):
        if self.selected_conv:
            self.clipboard_clear()
            self.clipboard_append(self.selected_conv.conv_id)
            messagebox.showinfo("Copié", f"ID copié dans le presse-papiers :\n{self.selected_conv.conv_id}")

    def _delete_current_conv(self):
        if self.selected_conv:
            self._delete_conversation_action(self.selected_conv)

    # -------------------------------------------------------------
    # Menus contextuels & Actions
    # -------------------------------------------------------------
    def _on_project_context_menu(self, event, project_name: str, convs: list[ConversationInfo]):
        menu = tk.Menu(self, tearoff=0, font=(FONT_FAMILY, 11))
        menu.add_command(
            label=f"Renommer « {project_name} »",
            command=lambda: self._rename_project_action(project_name),
        )
        menu.add_separator()
        menu.add_command(
            label=f"Supprimer « {project_name} » (avec ses {len(convs)} convs)",
            command=lambda: self._delete_project_action(project_name, convs),
        )
        menu.tk_popup(event.x_root, event.y_root)

    def _on_conv_context_menu(self, event, info: ConversationInfo):
        menu = tk.Menu(self, tearoff=0, font=(FONT_FAMILY, 11))
        short_title = info.title[:35] if info.title else info.conv_id[:8]

        menu.add_command(
            label=f"Ouvrir « {short_title} »",
            command=lambda: self.display_chat(info),
        )
        menu.add_separator()

        move_menu = tk.Menu(menu, tearoff=0, font=(FONT_FAMILY, 11))
        all_projs = sorted(self.project_convs.keys(), key=str.lower)
        for p in all_projs:
            if p != info.project:
                move_menu.add_command(
                    label=p,
                    command=lambda target=p: self._move_conversation_action(info, target),
                )
        menu.add_cascade(label="Déplacer vers...", menu=move_menu)

        menu.add_command(
            label=f"Copier l'ID ({info.conv_id[:8]}…)",
            command=lambda: self._copy_id_action(info.conv_id),
        )
        menu.add_separator()
        menu.add_command(
            label="Supprimer la conversation",
            command=lambda: self._delete_conversation_action(info),
        )
        menu.tk_popup(event.x_root, event.y_root)

    # -------------------------------------------------------------
    # Exécution des Actions
    # -------------------------------------------------------------
    def _rename_project_action(self, old_name: str):
        dialog = ctk.CTkInputDialog(
            text=f"Nouveau nom pour le projet « {old_name} » :",
            title="Renommer projet",
        )
        new_name = dialog.get_input()
        if not new_name or new_name.strip() == old_name:
            return
        new_name = new_name.strip()

        projects_root, _, brain_dir, _, _ = get_paths()
        old_path = projects_root / old_name
        new_path = projects_root / new_name

        if new_path.exists():
            messagebox.showerror("Erreur", f"Le dossier « {new_name} » existe déjà.")
            return

        if old_path.is_dir():
            try:
                old_path.rename(new_path)
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de renommer le dossier : {e}")
                return

        for c in self.project_convs.get(old_name, []):
            echange = brain_dir / c.conv_id / "echange_IA.md"
            try:
                echange.parent.mkdir(parents=True, exist_ok=True)
                lines = []
                if echange.is_file():
                    lines = echange.read_text(encoding="utf-8").splitlines()
                    lines = [l for l in lines if not l.lower().startswith("project:")]
                lines.insert(0, f"project: {new_name}")
                echange.write_text("\n".join(lines) + "\n", encoding="utf-8")
            except Exception:
                pass

        self.reload_data()
        messagebox.showinfo("Succès", f"Projet renommé en « {new_name} ».")

    def _delete_project_action(self, project_name: str, convs: list[ConversationInfo]):
        c_count = len(convs)
        msg = (
            f"Supprimer définitivement le projet « {project_name} » ?\n\n"
            f"⚠️ ATTENTION : Cela supprimera également les {c_count} conversation(s) associée(s)\n"
            f"dans le stockage Antigravity (brain et bases de données)."
        )
        if not messagebox.askyesno("Confirmation de suppression", msg, icon="warning"):
            return

        conv_ids = [c.conv_id for c in convs]
        success, res_msg = delete_project_cascade(project_name, conv_ids)

        self.reload_data()
        if success:
            messagebox.showinfo("Supprimé", f"Le projet « {project_name} » et ses {c_count} conversation(s) ont été supprimés.")
        else:
            messagebox.showwarning("Avertissement", f"Suppression partielle :\n{res_msg}")

    def _delete_conversation_action(self, info: ConversationInfo):
        msg = f"Supprimer définitivement cette conversation ?\n\n« {info.title} »\nID: {info.conv_id}"
        if not messagebox.askyesno("Supprimer conversation", msg, icon="warning"):
            return

        _, _, brain_dir, conversations_dir, _ = get_paths()
        brain_path = brain_dir / info.conv_id
        if brain_path.is_dir():
            try:
                shutil.rmtree(brain_path)
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur suppression brain : {e}")
                return

        db_path = conversations_dir / f"{info.conv_id}.db"
        if db_path.is_file():
            try:
                db_path.unlink()
            except Exception:
                pass

        for ext in (".db-wal", ".db-shm"):
            extra = conversations_dir / f"{info.conv_id}{ext}"
            if extra.is_file():
                try:
                    extra.unlink()
                except Exception:
                    pass

        if self.selected_conv and self.selected_conv.conv_id == info.conv_id:
            self._clear_chat_viewer()

        self.reload_data()
        messagebox.showinfo("Supprimé", "Conversation supprimée.")

    def _move_conversation_action(self, info: ConversationInfo, target_project: str):
        _, _, brain_dir, _, _ = get_paths()
        echange = brain_dir / info.conv_id / "echange_IA.md"
        try:
            echange.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            if echange.is_file():
                lines = echange.read_text(encoding="utf-8").splitlines()
                lines = [l for l in lines if not l.lower().startswith("project:")]
            lines.insert(0, f"project: {target_project}")
            echange.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de déplacer la conversation : {e}")
            return

        self.reload_data()
        messagebox.showinfo("Déplacé", f"Conversation déplacée vers « {target_project} ».")

    def _copy_id_action(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copié", f"ID copié :\n{text}")


# =================================================================
if __name__ == "__main__":
    app = AntigravityManagerApp()
    app.mainloop()
