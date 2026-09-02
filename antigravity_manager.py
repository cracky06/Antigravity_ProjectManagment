#!/usr/bin/env python3
"""antigravity_manager.py — Application graphique Antigravity Project & Chat Manager.

Fonctionnalités complètes :
- Arborescence projets avec icônes dépliables (pas d'espace vide si dossier vide)
- Vrais titres officiels des conversations et timestamps relatifs
- Dialogue Paramètres pour configurer les répertoires Projets et Antigravity
- Suppression en cascade : supprimer un projet supprime aussi toutes ses conversations associées
- Volet droit avec visionneuse complète de chat (requêtes utilisateur et réponses IA)
- Menus contextuels (renommer, supprimer, déplacer, copier l'ID)
"""

import shutil
import tkinter as tk
from tkinter import messagebox, filedialog
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
# Configuration de l'apparence
# -----------------------------------------------------------------
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

BG_SIDEBAR = "#F7F7F8"
BG_MAIN = "#FFFFFF"
BG_HOVER = "#ECECF1"
BG_SELECTED = "#E3E3E8"
BG_USER_BUBBLE = "#F0F4F9"
BORDER_USER_BUBBLE = "#D3E3FD"
BG_MODEL_CARD = "#FFFFFF"
BORDER_MODEL_CARD = "#E5E5E5"

FG_TEXT_PRIMARY = "#1F1F1F"
FG_TEXT_SECONDARY = "#6E6E80"
FG_TEXT_MUTED = "#8E8EA0"
FG_SECTION_TITLE = "#444746"
SEPARATOR_COLOR = "#E5E5E5"
ACCENT_COLOR = "#0B57D0"

FONT_FAMILY = "Segoe UI"


# =================================================================
# Dialogue : Paramètres de l'application
# =================================================================
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_save_callback):
        super().__init__(parent)
        self.title("Paramètres — Antigravity Manager")
        self.geometry("620x320")
        self.minsize(540, 280)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_save_callback = on_save_callback
        self.config_data = load_config()

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)

        title_lbl = ctk.CTkLabel(
            self,
            text="Configuration des Emplacements",
            font=(FONT_FAMILY, 15, "bold"),
            text_color=FG_TEXT_PRIMARY,
        )
        title_lbl.grid(row=0, column=0, columnspan=3, padx=20, pady=(18, 12), sticky="w")

        # 1. Répertoire des Projets
        ctk.CTkLabel(
            self,
            text="Dossier Projets :",
            font=(FONT_FAMILY, 12, "bold"),
            text_color=FG_TEXT_PRIMARY,
        ).grid(row=1, column=0, padx=(20, 10), pady=10, sticky="w")

        self.proj_entry = ctk.CTkEntry(self, font=(FONT_FAMILY, 11), height=32)
        self.proj_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.proj_entry.insert(0, self.config_data.get("projects_root", r"D:\DEV"))

        btn_browse_proj = ctk.CTkButton(
            self,
            text="Parcourir...",
            width=90,
            height=32,
            font=(FONT_FAMILY, 11),
            command=self._browse_projects,
        )
        btn_browse_proj.grid(row=1, column=2, padx=(0, 20), pady=10)

        # 2. Répertoire Antigravity Data
        ctk.CTkLabel(
            self,
            text="Dossier Antigravity :",
            font=(FONT_FAMILY, 12, "bold"),
            text_color=FG_TEXT_PRIMARY,
        ).grid(row=2, column=0, padx=(20, 10), pady=10, sticky="w")

        self.ag_entry = ctk.CTkEntry(self, font=(FONT_FAMILY, 11), height=32)
        self.ag_entry.grid(row=2, column=1, padx=(0, 10), pady=10, sticky="ew")
        self.ag_entry.insert(0, self.config_data.get("antigravity_root", ""))

        btn_browse_ag = ctk.CTkButton(
            self,
            text="Parcourir...",
            width=90,
            height=32,
            font=(FONT_FAMILY, 11),
            command=self._browse_antigravity,
        )
        btn_browse_ag.grid(row=2, column=2, padx=(0, 20), pady=10)

        # Description explicative
        desc_lbl = ctk.CTkLabel(
            self,
            text="Antigravity stocke ses données dans %USERPROFILE%\\.gemini\\antigravity\nLe dossier projets correspond à la racine où sont créés vos répertoires de développement.",
            font=(FONT_FAMILY, 10),
            text_color=FG_TEXT_MUTED,
            justify="left",
        )
        desc_lbl.grid(row=3, column=0, columnspan=3, padx=20, pady=(6, 16), sticky="w")

        # Boutons d'action
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, columnspan=3, padx=20, pady=(0, 16), sticky="e")

        btn_cancel = ctk.CTkButton(
            btn_frame,
            text="Annuler",
            width=90,
            height=32,
            font=(FONT_FAMILY, 11),
            fg_color=BG_HOVER,
            hover_color=BG_SELECTED,
            text_color=FG_TEXT_PRIMARY,
            command=self.destroy,
        )
        btn_cancel.pack(side="left", padx=(0, 10))

        btn_save = ctk.CTkButton(
            btn_frame,
            text="Enregistrer",
            width=100,
            height=32,
            font=(FONT_FAMILY, 11, "bold"),
            command=self._save,
        )
        btn_save.pack(side="left")

    def _browse_projects(self):
        cur = self.proj_entry.get().strip()
        d = filedialog.askdirectory(initialdir=cur, title="Sélectionnez le répertoire racine des Projets")
        if d:
            self.proj_entry.delete(0, "end")
            self.proj_entry.insert(0, d.replace("/", "\\"))

    def _browse_antigravity(self):
        cur = self.ag_entry.get().strip()
        d = filedialog.askdirectory(initialdir=cur, title="Sélectionnez le répertoire des données Antigravity")
        if d:
            self.ag_entry.delete(0, "end")
            self.ag_entry.insert(0, d.replace("/", "\\"))

    def _save(self):
        new_proj = self.proj_entry.get().strip()
        new_ag = self.ag_entry.get().strip()

        if not new_proj:
            messagebox.showerror("Erreur", "Le chemin du dossier projets ne peut pas être vide.")
            return

        self.config_data["projects_root"] = new_proj
        if new_ag:
            self.config_data["antigravity_root"] = new_ag

        save_config(self.config_data)
        self.destroy()
        if self._on_save_callback:
            self._on_save_callback()


# =================================================================
# Widget : Ligne de Projet dans la sidebar
# =================================================================
class ProjectItem(ctk.CTkFrame):
    """Ligne représentant un projet dans la liste latérale."""

    def __init__(self, master, project_name: str, convs: list[ConversationInfo],
                 on_toggle_callback, on_right_click_callback):
        super().__init__(master, fg_color="transparent", corner_radius=6, height=34)
        self.project_name = project_name
        self.convs = convs
        self.conv_count = len(convs)
        self.expanded = False
        self._on_toggle = on_toggle_callback
        self._on_right_click = on_right_click_callback

        self.grid_columnconfigure(1, weight=1)

        self.icon_label = ctk.CTkLabel(
            self,
            text="📁",
            font=(FONT_FAMILY, 14),
            width=24,
            fg_color="transparent",
            text_color=FG_TEXT_SECONDARY,
        )
        self.icon_label.grid(row=0, column=0, padx=(8, 4), pady=4)

        self.name_label = ctk.CTkLabel(
            self,
            text=project_name,
            font=(FONT_FAMILY, 12, "normal"),
            anchor="w",
            fg_color="transparent",
            text_color=FG_TEXT_PRIMARY,
        )
        self.name_label.grid(row=0, column=1, padx=(2, 4), pady=4, sticky="w")

        if self.conv_count > 0:
            self.count_label = ctk.CTkLabel(
                self,
                text=str(self.conv_count),
                font=(FONT_FAMILY, 10),
                anchor="e",
                fg_color="transparent",
                text_color=FG_TEXT_MUTED,
            )
            self.count_label.grid(row=0, column=2, padx=(0, 10), pady=4, sticky="e")

        for w in (self, self.icon_label, self.name_label):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Button-3>", self._on_right_click_event)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    def _on_click(self, event=None):
        if self.conv_count == 0:
            return
        self.expanded = not self.expanded
        self.icon_label.configure(text="📂" if self.expanded else "📁")
        self._on_toggle(self.project_name, self.expanded)

    def _on_right_click_event(self, event):
        self._on_right_click(event, self.project_name, self.convs)

    def _on_enter(self, event=None):
        self.configure(fg_color=BG_HOVER)

    def _on_leave(self, event=None):
        self.configure(fg_color="transparent")


# =================================================================
# Widget : Ligne de Conversation dans la sidebar
# =================================================================
class ConversationItem(ctk.CTkFrame):
    """Ligne représentant une conversation cliquable."""

    def __init__(self, master, info: ConversationInfo, indent: bool = False,
                 on_select_callback = None, on_right_click_callback = None,
                 is_selected: bool = False):
        super().__init__(
            master,
            fg_color=BG_SELECTED if is_selected else "transparent",
            corner_radius=6,
            height=30,
        )
        self.info = info
        self._on_select = on_select_callback
        self._on_right_click = on_right_click_callback
        self.is_selected = is_selected

        self.grid_columnconfigure(0, weight=1)

        pad_left = 32 if indent else 10

        display_title = info.title if info.title else info.conv_id[:12]
        if len(display_title) > 36:
            display_title = display_title[:34] + "…"

        self.title_label = ctk.CTkLabel(
            self,
            text=display_title,
            font=(FONT_FAMILY, 12),
            anchor="w",
            fg_color="transparent",
            text_color=FG_TEXT_PRIMARY if not is_selected else ACCENT_COLOR,
        )
        self.title_label.grid(row=0, column=0, padx=(pad_left, 4), pady=3, sticky="w")

        if info.rel_time:
            self.time_label = ctk.CTkLabel(
                self,
                text=info.rel_time,
                font=(FONT_FAMILY, 11),
                anchor="e",
                fg_color="transparent",
                text_color=FG_TEXT_MUTED,
            )
            self.time_label.grid(row=0, column=1, padx=(2, 10), pady=3, sticky="e")

        for w in (self, self.title_label):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Button-3>", self._on_right_click_event)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    def _on_click(self, event=None):
        if self._on_select:
            self._on_select(self.info)

    def _on_right_click_event(self, event):
        if self._on_right_click:
            self._on_right_click(event, self.info)

    def _on_enter(self, event=None):
        if not self.is_selected:
            self.configure(fg_color=BG_HOVER)

    def _on_leave(self, event=None):
        if not self.is_selected:
            self.configure(fg_color="transparent")


# =================================================================
# Application Principale Antigravity Manager
# =================================================================
class AntigravityManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Antigravity Manager — Project & Chat Management")
        self.geometry("1200x820")
        self.minsize(960, 600)
        self.configure(fg_color=BG_MAIN)

        self.project_convs: dict[str, list[ConversationInfo]] = {}
        self.all_convs: list[ConversationInfo] = []
        self.expanded_projects: set[str] = set()
        self.selected_conv: ConversationInfo | None = None

        self._build_ui()
        self.reload_data()

    # -------------------------------------------------------------
    # Construction UI
    # -------------------------------------------------------------
    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=0, minsize=330)
        self.grid_columnconfigure(1, weight=1)

        # 1. SIDEBAR
        self.sidebar_frame = ctk.CTkFrame(
            self,
            fg_color=BG_SIDEBAR,
            corner_radius=0,
            border_width=0,
            width=330,
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(1, weight=1)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        # En-tête Sidebar
        sb_top = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent", height=42)
        sb_top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        sb_top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            sb_top,
            text="Antigravity",
            font=(FONT_FAMILY, 15, "bold"),
            text_color=FG_TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=4)

        actions_box = ctk.CTkFrame(sb_top, fg_color="transparent")
        actions_box.grid(row=0, column=1, sticky="e")

        settings_btn = ctk.CTkButton(
            actions_box,
            text="⚙️",
            width=32,
            height=28,
            fg_color="transparent",
            hover_color=BG_HOVER,
            text_color=FG_TEXT_SECONDARY,
            font=(FONT_FAMILY, 13),
            command=self._open_settings,
        )
        settings_btn.pack(side="left", padx=2)

        refresh_btn = ctk.CTkButton(
            actions_box,
            text="🔄",
            width=32,
            height=28,
            fg_color="transparent",
            hover_color=BG_HOVER,
            text_color=FG_TEXT_SECONDARY,
            font=(FONT_FAMILY, 13),
            command=self.reload_data,
        )
        refresh_btn.pack(side="left", padx=2)

        # Arborescence scrollable
        self.tree_scroll = ctk.CTkScrollableFrame(
            self.sidebar_frame,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=SEPARATOR_COLOR,
        )
        self.tree_scroll.grid(row=1, column=0, sticky="nsew", padx=2, pady=0)
        self.tree_scroll.grid_columnconfigure(0, weight=1)

        # 2. CHAT VIEWER
        self.chat_viewer_frame = ctk.CTkFrame(
            self,
            fg_color=BG_MAIN,
            corner_radius=0,
        )
        self.chat_viewer_frame.grid(row=0, column=1, sticky="nsew")
        self.chat_viewer_frame.grid_rowconfigure(2, weight=1)
        self.chat_viewer_frame.grid_columnconfigure(0, weight=1)

        # En-tête Chat
        self.chat_header = ctk.CTkFrame(
            self.chat_viewer_frame,
            fg_color=BG_MAIN,
            corner_radius=0,
            height=60,
        )
        self.chat_header.grid(row=0, column=0, sticky="ew", padx=16, pady=8)
        self.chat_header.grid_columnconfigure(0, weight=1)

        self.chat_title_label = ctk.CTkLabel(
            self.chat_header,
            text="Sélectionnez une conversation",
            font=(FONT_FAMILY, 15, "bold"),
            anchor="w",
            text_color=FG_TEXT_PRIMARY,
        )
        self.chat_title_label.grid(row=0, column=0, sticky="w")

        self.chat_meta_label = ctk.CTkLabel(
            self.chat_header,
            text="",
            font=(FONT_FAMILY, 11),
            anchor="w",
            text_color=FG_TEXT_SECONDARY,
        )
        self.chat_meta_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.chat_actions_frame = ctk.CTkFrame(self.chat_header, fg_color="transparent")
        self.chat_actions_frame.grid(row=0, column=1, rowspan=2, sticky="e", padx=(10, 0))

        self.btn_copy_id = ctk.CTkButton(
            self.chat_actions_frame,
            text="📋 Copier ID",
            width=80,
            height=28,
            font=(FONT_FAMILY, 11),
            fg_color=BG_HOVER,
            hover_color=BG_SELECTED,
            text_color=FG_TEXT_PRIMARY,
            command=self._copy_current_conv_id,
        )
        self.btn_copy_id.pack(side="left", padx=4)

        self.btn_delete_chat = ctk.CTkButton(
            self.chat_actions_frame,
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

        # Ligne de séparation
        ctk.CTkFrame(
            self.chat_viewer_frame,
            fg_color=SEPARATOR_COLOR,
            height=1,
            corner_radius=0,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))

        # Messages scrollables
        self.chat_messages_scroll = ctk.CTkScrollableFrame(
            self.chat_viewer_frame,
            fg_color=BG_MAIN,
            corner_radius=0,
            scrollbar_button_color=SEPARATOR_COLOR,
        )
        self.chat_messages_scroll.grid(row=2, column=0, sticky="nsew", padx=16, pady=8)
        self.chat_messages_scroll.grid_columnconfigure(0, weight=1)

        # 3. STATUS BAR
        self.status_bar = ctk.CTkLabel(
            self,
            text="Prêt",
            font=(FONT_FAMILY, 10),
            anchor="w",
            fg_color="#EFEFEF",
            text_color=FG_TEXT_MUTED,
            height=22,
        )
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

    def _open_settings(self):
        SettingsDialog(self, on_save_callback=self.reload_data)

    # -------------------------------------------------------------
    # Chargement des données
    # -------------------------------------------------------------
    def reload_data(self):
        self.status_bar.configure(text="Chargement des données...")
        self.update_idletasks()

        self.project_convs, self.all_convs = build_project_map()
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

        projects_root, _, _, _, _ = get_paths()
        total_p = len(self.project_convs)
        total_c = len(self.all_convs)
        self.status_bar.configure(text=f"Projets : {projects_root} | {total_p} projets — {total_c} conversations")

    def _render_tree(self):
        for w in self.tree_scroll.winfo_children():
            w.destroy()

        # Section Projects
        proj_sec_frame = ctk.CTkFrame(self.tree_scroll, fg_color="transparent")
        proj_sec_frame.pack(fill="x", padx=4, pady=(4, 4))
        proj_sec_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            proj_sec_frame,
            text="Projects",
            font=(FONT_FAMILY, 12, "bold"),
            text_color=FG_SECTION_TITLE,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=6)

        for proj_name in sorted(self.project_convs.keys(), key=str.lower):
            convs = self.project_convs[proj_name]
            p_item = ProjectItem(
                self.tree_scroll,
                project_name=proj_name,
                convs=convs,
                on_toggle_callback=self._on_project_toggle,
                on_right_click_callback=self._on_project_context_menu,
            )
            p_item.pack(fill="x", padx=2, pady=1)

            if proj_name in self.expanded_projects and convs:
                p_item.expanded = True
                p_item.icon_label.configure(text="📂")

                conv_container = ctk.CTkFrame(self.tree_scroll, fg_color="transparent")
                conv_container.pack(fill="x", padx=0, pady=0)

                for c_info in convs:
                    is_sel = bool(self.selected_conv and self.selected_conv.conv_id == c_info.conv_id)
                    c_item = ConversationItem(
                        conv_container,
                        info=c_info,
                        indent=True,
                        on_select_callback=self.display_chat,
                        on_right_click_callback=self._on_conv_context_menu,
                        is_selected=is_sel,
                    )
                    c_item.pack(fill="x", padx=2, pady=1)

        # Séparateur
        sep = ctk.CTkFrame(self.tree_scroll, fg_color=SEPARATOR_COLOR, height=1, corner_radius=0)
        sep.pack(fill="x", padx=8, pady=(14, 8))

        # Section Conversations Récentes
        conv_sec_frame = ctk.CTkFrame(self.tree_scroll, fg_color="transparent")
        conv_sec_frame.pack(fill="x", padx=4, pady=(2, 4))
        conv_sec_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            conv_sec_frame,
            text="Conversations ▾",
            font=(FONT_FAMILY, 12, "bold"),
            text_color=FG_SECTION_TITLE,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=6)

        for c_info in self.all_convs[:40]:
            is_sel = bool(self.selected_conv and self.selected_conv.conv_id == c_info.conv_id)
            c_item = ConversationItem(
                self.tree_scroll,
                info=c_info,
                indent=False,
                on_select_callback=self.display_chat,
                on_right_click_callback=self._on_conv_context_menu,
                is_selected=is_sel,
            )
            c_item.pack(fill="x", padx=2, pady=1)

    def _on_project_toggle(self, project_name: str, expanded: bool):
        if expanded:
            self.expanded_projects.add(project_name)
        else:
            self.expanded_projects.discard(project_name)
        self._render_tree()

    # -------------------------------------------------------------
    # Visionneuse de Chat
    # -------------------------------------------------------------
    def display_chat(self, info: ConversationInfo):
        self.selected_conv = info
        self._render_tree()

        title_text = info.title if info.title else "Conversation sans titre"
        self.chat_title_label.configure(text=title_text)

        proj_str = f"Projet : {info.project}" if info.project else "Projet : (aucun)"
        date_str = info.last_activity.strftime("%d/%m/%Y %H:%M") if info.last_activity else "Date inconnue"
        self.chat_meta_label.configure(text=f"{proj_str}  •  {date_str}  •  ID: {info.conv_id}")

        for w in self.chat_messages_scroll.winfo_children():
            w.destroy()

        messages = load_chat_messages(info.conv_id)

        if not messages:
            empty_lbl = ctk.CTkLabel(
                self.chat_messages_scroll,
                text="Aucun message trouvé dans l'historique de cette conversation.",
                font=(FONT_FAMILY, 13),
                text_color=FG_TEXT_MUTED,
            )
            empty_lbl.pack(pady=40)
            return

        for msg in messages:
            role = msg.get("role")
            text = msg.get("text", "")
            ts = msg.get("timestamp", "")

            if role == "user":
                self._render_user_message(text, ts)
            elif role == "model":
                self._render_model_message(text, ts)

    def _render_user_message(self, text: str, timestamp: str):
        card = ctk.CTkFrame(
            self.chat_messages_scroll,
            fg_color=BG_USER_BUBBLE,
            border_color=BORDER_USER_BUBBLE,
            border_width=1,
            corner_radius=8,
        )
        card.pack(fill="x", padx=12, pady=(12, 6))
        card.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Utilisateur",
            font=(FONT_FAMILY, 11, "bold"),
            text_color=ACCENT_COLOR,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        if timestamp:
            ctk.CTkLabel(
                header,
                text=timestamp,
                font=(FONT_FAMILY, 10),
                text_color=FG_TEXT_MUTED,
                anchor="e",
            ).grid(row=0, column=1, sticky="e")

        txt_box = ctk.CTkTextbox(
            card,
            font=(FONT_FAMILY, 12),
            fg_color="transparent",
            text_color=FG_TEXT_PRIMARY,
            wrap="word",
            border_width=0,
            activate_scrollbars=False,
        )
        txt_box.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        txt_box.insert("1.0", text)
        txt_box.configure(state="disabled")

        line_count = len(text.splitlines())
        calc_height = max(40, min(line_count * 20 + 20, 300))
        txt_box.configure(height=calc_height)

    def _render_model_message(self, text: str, timestamp: str):
        card = ctk.CTkFrame(
            self.chat_messages_scroll,
            fg_color=BG_MODEL_CARD,
            border_color=BORDER_MODEL_CARD,
            border_width=1,
            corner_radius=8,
        )
        card.pack(fill="x", padx=12, pady=(6, 12))
        card.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Antigravity",
            font=(FONT_FAMILY, 11, "bold"),
            text_color=FG_SECTION_TITLE,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        if timestamp:
            ctk.CTkLabel(
                header,
                text=timestamp,
                font=(FONT_FAMILY, 10),
                text_color=FG_TEXT_MUTED,
                anchor="e",
            ).grid(row=0, column=1, sticky="e")

        txt_box = ctk.CTkTextbox(
            card,
            font=(FONT_FAMILY, 12),
            fg_color="transparent",
            text_color=FG_TEXT_PRIMARY,
            wrap="word",
            border_width=0,
            activate_scrollbars=False,
        )
        txt_box.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        txt_box.insert("1.0", text)
        txt_box.configure(state="disabled")

        line_count = len(text.splitlines())
        calc_height = max(50, min(line_count * 20 + 25, 600))
        txt_box.configure(height=calc_height)

    def _clear_chat_viewer(self):
        self.selected_conv = None
        self.chat_title_label.configure(text="Sélectionnez une conversation")
        self.chat_meta_label.configure(text="Cliquez sur un projet ou une conversation à gauche pour afficher les échanges.")
        for w in self.chat_messages_scroll.winfo_children():
            w.destroy()

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
            label=f"Supprimer la conversation",
            command=lambda: self._delete_conversation_action(info),
        )
        menu.tk_popup(event.x_root, event.y_root)

    # -------------------------------------------------------------
    # Implémentation des Actions
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
                messagebox.showerror("Erreur", f"Erreur lors de la suppression du brain : {e}")
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
