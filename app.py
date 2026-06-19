from __future__ import annotations

import json
import hashlib
import io
import mimetypes
import os
import getpass
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import ctypes
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
import tkinter.font as tkfont

import smbclient
from PIL import Image, ImageDraw, ImageTk


APP_NAME = "AccessView"
APP_VERSION = "0.10.1"
APP_ICON_FILE = "AccessView.ico"
APP_LOGO_FILE = "AccessView.png"
APP_UPDATER_FILE = "AccessViewUpdater.exe"
APP_USER_MODEL_ID = "NexuSync.AccessView"
UPDATE_MANIFEST_FILE = "update.json"
UPDATE_PAYLOAD_PREFIX = "payload/"


def resource_path(relative_path: str) -> Path:
    """Resolve bundled assets both in source mode and PyInstaller mode."""
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / relative_path)

    candidates.append(Path(__file__).resolve().parent / relative_path)

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(Path(bundle_dir) / relative_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0] if candidates else Path(relative_path)

COLORS = {
    # Neutral graphite theme. Semantic colors are intentionally restrained so
    # the interface remains predominantly grayscale.
    "window": "#111315",
    "bg_primary": "#151719",
    "bg_secondary": "#1c1f22",
    "bg_tertiary": "#24282c",
    "bg_elevated": "#2b3035",
    "bg_hover": "#32373c",
    "bg_active": "#3a4046",
    "border": "#34393e",
    "border_light": "#474d53",
    "text_primary": "#f3f4f5",
    "text_secondary": "#b9bec3",
    "text_muted": "#858b91",
    "accent": "#69717a",
    "accent_hover": "#7b848e",
    "accent_light": "#30353a",
    "accent_border": "#8b949e",
    "success": "#76b696",
    "success_bg": "#263a31",
    "warning": "#c8b780",
    "warning_bg": "#3b3625",
    "danger": "#d77979",
    "danger_bg": "#4a292b",
    "danger_hover": "#e18787",
    "selection": "#3a4148",
    "selection_border": "#8d969f",
    "focus": "#a6adb4",
    "blue": "#2878c8",
    "blue_hover": "#3489dc",
    "green": "#287a4d",
    "green_hover": "#329560",
    "purple": "#68509a",
    "purple_hover": "#7a61ae",
    "amber": "#8a6728",
    "amber_hover": "#a17a31",
    "folder_blue": "#2784d6",
    "folder_blue_light": "#55a8ed",
    "path_green": "#78d79b",
    "path_green_muted": "#58b97b",
    "path_green_bg": "#263b30",
}
BASE_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = Path(os.environ.get("PROGRAMDATA", BASE_DIR)) / "AccessView" / "logs"
UPDATE_DATA_DIR = (
    Path(os.environ.get("PROGRAMDATA", BASE_DIR)) / APP_NAME / "updates"
)
UPDATE_STATE_FILE = UPDATE_DATA_DIR / "state.json"


def version_tuple(value: str) -> tuple[int, ...]:
    """Convert dotted versions into comparable integer tuples."""
    try:
        parts = tuple(int(part) for part in str(value).strip().split("."))
    except (TypeError, ValueError) as error:
        raise ValueError(f"Versão inválida: {value}") from error
    if not parts or any(part < 0 for part in parts):
        raise ValueError(f"Versão inválida: {value}")
    return parts + (0,) * max(0, 4 - len(parts))


def load_update_state() -> dict:
    if not UPDATE_STATE_FILE.is_file():
        return {}
    try:
        state = json.loads(UPDATE_STATE_FILE.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_update_package(package_path: Path) -> dict:
    """Validate package structure, compatibility and payload checksums."""
    if not package_path.is_file():
        raise ValueError("O pacote de atualização não foi encontrado.")
    if package_path.suffix.lower() != ".zip":
        raise ValueError("Selecione um pacote de atualização no formato ZIP.")

    package_hash = file_sha256(package_path)
    update_state = load_update_state()
    installed_packages = {
        str(value).casefold()
        for value in update_state.get("installed_package_sha256", [])
    }
    if package_hash.casefold() in installed_packages:
        installed_version = update_state.get("installed_version", APP_VERSION)
        raise ValueError(
            f"Este pacote já foi instalado anteriormente.\n\n"
            f"Versão atual: {installed_version}"
        )

    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            names = set(archive.namelist())
            if UPDATE_MANIFEST_FILE not in names:
                raise ValueError("O ZIP não contém o arquivo update.json.")

            manifest = json.loads(
                archive.read(UPDATE_MANIFEST_FILE).decode("utf-8-sig")
            )
            if manifest.get("app") != APP_NAME:
                raise ValueError("Este pacote não pertence ao AccessView.")

            target_version = str(manifest.get("version", "")).strip()
            minimum_version = str(
                manifest.get("minimum_version", "0.0.0")
            ).strip()
            if version_tuple(target_version) <= version_tuple(APP_VERSION):
                raise ValueError(
                    f"A versão {target_version} não é mais nova que a versão "
                    f"instalada ({APP_VERSION})."
                )
            if version_tuple(APP_VERSION) < version_tuple(minimum_version):
                raise ValueError(
                    f"Esta atualização exige no mínimo a versão {minimum_version}."
                )

            files = manifest.get("files")
            if not isinstance(files, dict) or not files:
                raise ValueError("O manifesto não contém a lista de arquivos.")

            normalized_names = {
                name.replace("\\", "/").lstrip("/"): name
                for name in archive.namelist()
                if not name.endswith("/")
            }
            for relative_name, expected_hash in files.items():
                raw_name = str(relative_name).replace("\\", "/")
                pure_name = PurePosixPath(raw_name)
                if (
                    not raw_name
                    or raw_name.startswith("/")
                    or pure_name.is_absolute()
                    or ".." in pure_name.parts
                    or (pure_name.parts and ":" in pure_name.parts[0])
                ):
                    raise ValueError(
                        f"Caminho inválido no pacote: {relative_name}"
                    )
                clean_name = pure_name.as_posix()
                if (
                    clean_name.casefold() == "config.json"
                ):
                    raise ValueError(
                        f"Caminho inválido no pacote: {relative_name}"
                    )
                archive_name = UPDATE_PAYLOAD_PREFIX + clean_name
                stored_name = normalized_names.get(archive_name)
                if not stored_name:
                    raise ValueError(f"Arquivo ausente no pacote: {clean_name}")
                digest = hashlib.sha256(archive.read(stored_name)).hexdigest()
                if digest.casefold() != str(expected_hash).casefold():
                    raise ValueError(
                        f"Falha na verificação de integridade: {clean_name}"
                    )

            if "AccessView.exe" not in files:
                raise ValueError("O pacote não contém o executável principal.")

            manifest["_package_sha256"] = package_hash
            return manifest
    except zipfile.BadZipFile as error:
        raise ValueError("O arquivo selecionado não é um ZIP válido.") from error


@dataclass(frozen=True)
class AppConfig:
    server_ip: str
    shares: tuple[str, ...]
    display_name: str
    port: int = 445
    connection_timeout: int = 8
    skip_dfs: bool = True
    auth_protocol: str = "ntlm"

    def share_path(self, share_name: str) -> str:
        return rf"\\{self.server_ip}\{share_name}"


def load_config() -> AppConfig:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILE}")

    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    required = ("server_ip", "display_name")
    missing = [key for key in required if not str(raw.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Missing configuration fields: {', '.join(missing)}")

    raw_shares = raw.get("shares")
    if raw_shares is None and raw.get("share_name"):
        raw_shares = [raw["share_name"]]
    if not isinstance(raw_shares, list) or not raw_shares:
        raise ValueError("Configure pelo menos um compartilhamento no campo shares.")

    shares: list[str] = []
    for raw_share in raw_shares:
        share_name = str(raw_share).strip().strip("\\/")
        if not share_name or "\\" in share_name or "/" in share_name:
            raise ValueError(
                "Cada item de shares deve conter somente o nome do compartilhamento "
                "Samba. Exemplo: SERVER-FILES"
            )
        if share_name.casefold() not in {item.casefold() for item in shares}:
            shares.append(share_name)

    auth_protocol = str(raw.get("auth_protocol", "ntlm")).strip().lower()
    if auth_protocol not in {"negotiate", "ntlm", "kerberos"}:
        raise ValueError("auth_protocol deve ser: negotiate, ntlm ou kerberos")

    return AppConfig(
        server_ip=str(raw["server_ip"]).strip(),
        shares=tuple(shares),
        display_name=str(raw["display_name"]).strip(),
        port=int(raw.get("port", 445)),
        connection_timeout=int(raw.get("connection_timeout", 8)),
        skip_dfs=bool(raw.get("skip_dfs", True)),
        auth_protocol=auth_protocol,
    )


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def friendly_connection_error(error: Exception, config: AppConfig) -> str:
    raw_error = str(error)
    error_upper = raw_error.upper()
    server_path = rf"\\{config.server_ip}"

    if "STATUS_LOGON_FAILURE" in error_upper or "STATUS_WRONG_PASSWORD" in error_upper:
        return (
            "Usuário ou senha Samba inválidos.\n\n"
            "Confirme as credenciais e tente novamente."
        )

    if "STATUS_ACCOUNT_LOCKED_OUT" in error_upper:
        return "A conta Samba está bloqueada no servidor."

    if "STATUS_ACCESS_DENIED" in error_upper:
        return (
            "As credenciais foram aceitas, mas este usuário não possui permissão "
            f"para acessar o recurso solicitado em:\n\n{server_path}"
        )

    if (
        "STATUS_BAD_NETWORK_NAME" in error_upper
        or "STATUS_OBJECT_NAME_NOT_FOUND" in error_upper
        or "STATUS_OBJECT_PATH_NOT_FOUND" in error_upper
        or "STATUS_NOT_FOUND" in error_upper
    ):
        return (
            "O servidor respondeu, mas o compartilhamento Samba não foi encontrado.\n\n"
            f"Servidor:\n{server_path}\n\n"
            "No config.json, cada item de shares deve ser exatamente o nome entre "
            "colchetes no smb.conf."
        )

    if isinstance(error, (ConnectionRefusedError, TimeoutError, socket.timeout)):
        return (
            f"O servidor {config.server_ip}:{config.port} não respondeu.\n\n"
            "Confirme se o Tailscale está conectado e se o Samba está ativo."
        )

    if (
        "NO CREDENTIALS ARE AVAILABLE IN THE SECURITY PACKAGE" in error_upper
        or "SPNEGOERROR" in error_upper
        or "PROCESSING SECURITY TOKEN" in error_upper
    ):
        return (
            "A sessão de autenticação Samba não pôde ser reutilizada para este "
            "compartilhamento.\n\n"
            "Encerre a sessão no AccessView, entre novamente e tente abrir a pasta.\n\n"
            "Se o problema persistir, confirme se auth_protocol está definido como "
            "\"ntlm\" no config.json e se o usuário possui acesso a este compartilhamento."
        )

    return (
        "Não foi possível acessar o servidor.\n\n"
        f"Servidor: {server_path}\n\n"
        f"Detalhes técnicos: {raw_error}"
    )


class AuditLogger:
    def __init__(self) -> None:
        self.samba_user = "-"
        self.server = "-"
        self.computer = os.environ.get("COMPUTERNAME", socket.gethostname())
        self.windows_user = os.environ.get("USERNAME", getpass.getuser())
        preferred_dir = LOG_DIR
        try:
            preferred_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            preferred_dir = (
                Path(os.environ.get("LOCALAPPDATA", BASE_DIR))
                / "AccessView"
                / "logs"
            )
            preferred_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = preferred_dir / f"{datetime.now():%Y-%m-%d}.log"

    def write(self, action: str, detail: str = "") -> None:
        clean_detail = str(detail).replace("\t", " ").replace("\r", " ").replace("\n", " ")
        line = (
            f"{datetime.now():%Y-%m-%d %H:%M:%S}\t"
            f"computer={self.computer}\twindows_user={self.windows_user}\t"
            f"samba_user={self.samba_user}\tserver={self.server}\t"
            f"action={action}\tdetail={clean_detail}\n"
        )
        try:
            with self.file_path.open("a", encoding="utf-8") as file:
                file.write(line)
        except OSError:
            pass

    def set_session(self, samba_user: str, server: str) -> None:
        self.samba_user = samba_user or "-"
        self.server = server or "-"

    def clear_session(self) -> None:
        self.samba_user = "-"
        self.server = "-"


class AutoHideScrollbar(ttk.Scrollbar):
    """Hide the scrollbar while the entire scrollable area is visible."""

    def __init__(self, master=None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._pack_options: dict = {}
        self._is_visible = False

    def pack(self, **kwargs) -> None:
        self._pack_options = dict(kwargs)
        self._is_visible = True
        super().pack(**kwargs)

    pack_configure = pack

    def set(self, first, last) -> None:
        try:
            content_fits = float(first) <= 0.0 and float(last) >= 1.0
        except (TypeError, ValueError):
            content_fits = False

        if content_fits and self._is_visible:
            super().pack_forget()
            self._is_visible = False
        elif not content_fits and not self._is_visible and self._pack_options:
            super().pack(**self._pack_options)
            self._is_visible = True

        super().set(first, last)


class Tooltip:
    """Small delayed tooltip used for contextual information."""

    def __init__(
        self,
        widget: tk.Widget,
        text: str,
        delay_ms: int = 350,
    ) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._job: str | None = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _event=None) -> None:
        self.hide()
        self._job = self.widget.after(self.delay_ms, self.show)

    def show(self) -> None:
        self._job = None
        if self._window is not None or not self.widget.winfo_exists():
            return

        self._window = tk.Toplevel(self.widget)
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)

        card = tk.Frame(
            self._window,
            background=COLORS["bg_elevated"],
            highlightbackground=COLORS["border_light"],
            highlightthickness=1,
            padx=14,
            pady=11,
        )
        card.pack()
        tk.Label(
            card,
            text=self.text,
            justify="left",
            font=("Segoe UI", 9),
            foreground=COLORS["text_primary"],
            background=COLORS["bg_elevated"],
            wraplength=310,
        ).pack()

        self._window.update_idletasks()
        tooltip_width = self._window.winfo_reqwidth()
        tooltip_height = self._window.winfo_reqheight()
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()
        x = self.widget.winfo_rootx() + self.widget.winfo_width() - tooltip_width
        y = self.widget.winfo_rooty() - tooltip_height - 8
        x = max(8, min(x, screen_width - tooltip_width - 8))
        if y < 8:
            y = min(
                screen_height - tooltip_height - 8,
                self.widget.winfo_rooty() + self.widget.winfo_height() + 8,
            )
        self._window.geometry(f"+{x}+{y}")

    def hide(self, _event=None) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None


class RoundedButton(tk.Canvas):
    """Modern canvas button with true rounded corners."""

    def __init__(
        self,
        master,
        text: str,
        command,
        background: str,
        hover: str,
        foreground: str = "#ffffff",
        width: int | None = None,
        radius: int = 8,
        outline: str | None = None,
        height: int = 38,
    ) -> None:
        self._text = text
        self._command = command
        self._normal_color = background
        self._hover_color = hover
        self._foreground = foreground
        self._radius = radius
        self._outline = outline
        self._state = "normal"
        self._mouse_inside = False
        self._font = tkfont.Font(family="Segoe UI Semibold", size=9)
        measured_width = self._font.measure(text) + 30
        if width is not None:
            measured_width = max(measured_width, width * 9)
        parent_background = master.cget("background")
        super().__init__(
            master,
            width=measured_width,
            height=height,
            background=parent_background,
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
            cursor="hand2",
        )
        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_click)
        self._redraw()

    @staticmethod
    def _rounded_points(
        left: float,
        top: float,
        right: float,
        bottom: float,
        radius: float,
    ) -> list[float]:
        return [
            left + radius, top,
            right - radius, top,
            right, top,
            right, top + radius,
            right, bottom - radius,
            right, bottom,
            right - radius, bottom,
            left + radius, bottom,
            left, bottom,
            left, bottom - radius,
            left, top + radius,
            left, top,
        ]

    def _redraw(self, _event=None) -> None:
        self.delete("all")
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        color = self._normal_color
        if self._state == "disabled":
            color = COLORS["bg_active"]
        elif self._mouse_inside:
            color = self._hover_color
        radius = min(self._radius, height // 2, width // 2)
        self.create_polygon(
            self._rounded_points(1, 1, width - 1, height - 1, radius),
            smooth=True,
            splinesteps=24,
            fill=color,
            outline=self._outline or "",
            width=1 if self._outline else 0,
        )
        self.create_text(
            width / 2,
            height / 2,
            text=self._text,
            fill=self._foreground,
            font=self._font,
        )

    def _on_enter(self, _event=None) -> None:
        self._mouse_inside = True
        self._redraw()

    def _on_leave(self, _event=None) -> None:
        self._mouse_inside = False
        self._redraw()

    def _on_click(self, _event=None) -> None:
        if self._state != "disabled" and callable(self._command):
            self._command()

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf or {})
        options.update(kwargs)
        if "text" in options:
            self._text = str(options.pop("text"))
        if "background" in options:
            self._normal_color = str(options.pop("background"))
        if "state" in options:
            self._state = str(options.pop("state"))
            super().configure(
                cursor="arrow" if self._state == "disabled" else "hand2"
            )
        if "outline" in options:
            self._outline = str(options.pop("outline"))
        if options:
            super().configure(**options)
        self._redraw()

    config = configure


class RoundedThumbnailCard(tk.Canvas):
    """Rounded file/folder card used by the thumbnail view."""

    def __init__(
        self,
        master,
        image: ImageTk.PhotoImage,
        text: str,
    ) -> None:
        super().__init__(
            master,
            width=154,
            height=158,
            background=master.cget("background"),
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
            cursor="hand2",
        )
        self._photo = image
        self._selected = False
        self._card_shape: int | None = None
        self._image_item: int | None = None
        self._text_item: int | None = None
        self._label = text
        self.bind("<Configure>", self._redraw)
        self._redraw()

    def _redraw(self, _event=None) -> None:
        self.delete("all")
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        fill = COLORS["selection"] if self._selected else COLORS["bg_tertiary"]
        outline = (
            COLORS["selection_border"] if self._selected else COLORS["border"]
        )
        self._card_shape = self.create_polygon(
            RoundedButton._rounded_points(2, 2, width - 2, height - 2, 12),
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline=outline,
            width=1,
        )
        self._image_item = self.create_image(
            width / 2,
            62,
            image=self._photo,
            anchor="center",
        )
        self._text_item = self.create_text(
            width / 2,
            130,
            text=self._label,
            fill=COLORS["text_primary"],
            font=("Segoe UI", 9),
            justify="center",
            width=136,
            anchor="center",
        )

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._redraw()

    def set_image(self, image: ImageTk.PhotoImage) -> None:
        self._photo = image
        if self._image_item is not None:
            self.itemconfigure(self._image_item, image=image)


class SecureFileBrowser(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self._configure_application_identity()
        self.configure(background=COLORS["window"])
        self.overrideredirect(True)
        self.protocol("WM_DELETE_WINDOW", self.close_application)
        self.bind("<Alt-F4>", lambda _event: self.close_application())
        self._set_initial_geometry()

        self.config_data: AppConfig | None = None
        self.logger = AuditLogger()
        self.username = ""
        self.current_parts: list[str] = []
        self.entries: dict[str, dict] = {}
        self.preview_image: ImageTk.PhotoImage | None = None
        self.selected_item_id: str | None = None
        self.selected_item_ids: set[str] = set()
        self.selection_anchor_id: str | None = None
        self.view_mode = "thumbnails"
        self.base_icons: dict[str, ImageTk.PhotoImage] = {}
        self.thumbnail_images: dict[str, ImageTk.PhotoImage] = {}
        self.thumbnail_labels: dict[str, RoundedThumbnailCard] = {}
        self.grid_cards: dict[str, RoundedThumbnailCard] = {}
        self.directory_generation = 0
        self.navigation_paths: dict[str, tuple[str, ...]] = {}
        self.navigation_nodes: dict[tuple[str, ...], str] = {}
        self.navigation_loaded: set[tuple[str, ...]] = set()
        self.navigation_loading: set[tuple[str, ...]] = set()
        self.navigation_node_counter = 0
        self.navigation_generation = 0
        self._syncing_navigation = False
        self.temp_dir = Path(tempfile.mkdtemp(prefix="accessview_"))
        self.task_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.connected = False
        self.download_active = False
        self.download_progress = tk.DoubleVar(value=0)
        self._drag_x = 0
        self._drag_y = 0
        self._restore_override_pending = False
        self._rounding_job: str | None = None

        self._configure_style()
        self._create_base_icons()
        self._build_window_chrome()
        self._build_login_screen()
        self.after(100, self._process_task_queue)
        self.after(100, self._show_in_taskbar)
        self.after(120, self._apply_rounded_window)
        self.bind("<Configure>", self._schedule_rounded_window, add="+")

        try:
            self.config_data = load_config()
            self.server_label.configure(
                text=f"Servidor: {self.config_data.display_name} ({self.config_data.server_ip})"
            )
        except Exception as error:
            self.login_button.configure(state="disabled")
            messagebox.showerror("Erro de configuração", str(error))

    def _load_photo_asset(
        self,
        filename: str,
        size: tuple[int, int] | None = None,
    ) -> ImageTk.PhotoImage | None:
        path = resource_path(filename)
        if not path.exists():
            return None
        try:
            with Image.open(path) as image:
                image = image.convert("RGBA")
                if size:
                    image.thumbnail(size, Image.Resampling.LANCZOS)
                    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
                    x = (size[0] - image.width) // 2
                    y = (size[1] - image.height) // 2
                    canvas.paste(image, (x, y), image)
                    image = canvas
                return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _configure_application_identity(self) -> None:
        self._app_icon_photo: ImageTk.PhotoImage | None = None
        if sys.platform == "win32":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    APP_USER_MODEL_ID
                )
            except Exception:
                pass

            icon_path = resource_path(APP_ICON_FILE)
            if icon_path.exists():
                try:
                    self.iconbitmap(default=str(icon_path))
                except Exception:
                    pass

        icon_photo = self._load_photo_asset(APP_LOGO_FILE, (64, 64))
        if icon_photo is not None:
            self._app_icon_photo = icon_photo
            try:
                self.iconphoto(True, icon_photo)
            except Exception:
                pass

    def _set_initial_geometry(self) -> None:
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        window_width = max(980, round(screen_width * 0.78))
        window_height = max(620, round(screen_height * 0.78))

        window_width = min(window_width, screen_width)
        window_height = min(window_height, screen_height)

        position_x = max(0, (screen_width - window_width) // 2)
        position_y = max(0, (screen_height - window_height) // 2)

        minimum_width = min(900, window_width)
        minimum_height = min(580, window_height)
        self.minsize(minimum_width, minimum_height)
        self.geometry(
            f"{window_width}x{window_height}+{position_x}+{position_y}"
        )

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Treeview",
            rowheight=38,
            font=("Segoe UI", 10),
            background=COLORS["bg_secondary"],
            fieldbackground=COLORS["bg_secondary"],
            foreground=COLORS["text_primary"],
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", COLORS["selection"])],
            foreground=[("selected", COLORS["text_primary"])],
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI Semibold", 10),
            background=COLORS["bg_tertiary"],
            foreground=COLORS["text_primary"],
            relief="flat",
            padding=(14, 11),
        )
        style.map("Treeview.Heading", background=[("active", COLORS["bg_hover"])])
        style.configure(
            "Navigation.Treeview",
            rowheight=34,
            font=("Segoe UI", 10),
            background=COLORS["bg_secondary"],
            fieldbackground=COLORS["bg_secondary"],
            foreground=COLORS["text_primary"],
            borderwidth=0,
        )
        style.map(
            "Navigation.Treeview",
            background=[("selected", COLORS["path_green_bg"])],
            foreground=[("selected", COLORS["path_green"])],
        )
        style.configure(
            "Office.Horizontal.TProgressbar",
            troughcolor=COLORS["bg_tertiary"],
            background=COLORS["accent"],
            bordercolor=COLORS["bg_tertiary"],
            lightcolor=COLORS["accent"],
            darkcolor=COLORS["accent"],
            thickness=8,
        )
        style.configure(
            "Vertical.TScrollbar",
            troughcolor=COLORS["bg_secondary"],
            background=COLORS["bg_active"],
            bordercolor=COLORS["bg_secondary"],
            arrowcolor=COLORS["text_secondary"],
            relief="flat",
        )
        style.configure(
            "Horizontal.TScrollbar",
            troughcolor=COLORS["bg_secondary"],
            background=COLORS["bg_active"],
            bordercolor=COLORS["bg_secondary"],
            arrowcolor=COLORS["text_secondary"],
            relief="flat",
        )
        style.configure(
            "TCombobox",
            fieldbackground=COLORS["bg_tertiary"],
            background=COLORS["bg_tertiary"],
            foreground=COLORS["text_primary"],
            bordercolor=COLORS["border"],
            arrowcolor=COLORS["text_secondary"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["bg_tertiary"])],
            background=[("readonly", COLORS["bg_tertiary"])],
        )

    def _build_window_chrome(self) -> None:
        self.window_border = tk.Frame(
            self,
            background=COLORS["border_light"],
            padx=1,
            pady=1,
        )
        self.window_border.pack(fill="both", expand=True)

        self.window_surface = tk.Frame(
            self.window_border,
            background=COLORS["bg_primary"],
        )
        self.window_surface.pack(fill="both", expand=True)

        self.title_bar = tk.Frame(
            self.window_surface,
            height=48,
            background=COLORS["bg_secondary"],
        )
        self.title_bar.pack(fill="x")
        self.title_bar.pack_propagate(False)

        self.title_icon_image = self._load_photo_asset(APP_LOGO_FILE, (24, 24))
        if self.title_icon_image is not None:
            title_icon = tk.Label(
                self.title_bar,
                image=self.title_icon_image,
                background=COLORS["bg_secondary"],
            )
        else:
            title_icon = tk.Label(
                self.title_bar,
                text="▣",
                font=("Segoe UI Symbol", 14),
                foreground=COLORS["text_primary"],
                background=COLORS["bg_secondary"],
            )
        title_icon.pack(side="left", padx=(16, 9))

        self.title_text = tk.Label(
            self.title_bar,
            text=APP_NAME,
            font=("Segoe UI Semibold", 10),
            foreground=COLORS["text_primary"],
            background=COLORS["bg_secondary"],
        )
        self.title_text.pack(side="left")
        self.version_text = tk.Label(
            self.title_bar,
            text=f"v{APP_VERSION}",
            font=("Segoe UI", 8),
            foreground=COLORS["text_muted"],
            background=COLORS["bg_secondary"],
        )
        self.version_text.pack(side="left", padx=(8, 0))

        self.close_button = tk.Button(
            self.title_bar,
            text="×",
            command=self.close_application,
            font=("Segoe UI", 16),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_secondary"],
            activeforeground=COLORS["text_primary"],
            activebackground=COLORS["danger_bg"],
            relief="flat",
            borderwidth=0,
            width=5,
            cursor="hand2",
        )
        self.close_button.pack(side="right", fill="y")
        self.close_button.bind(
            "<Enter>",
            lambda _event: self.close_button.configure(background=COLORS["danger_bg"]),
        )
        self.close_button.bind(
            "<Leave>",
            lambda _event: self.close_button.configure(background=COLORS["bg_secondary"]),
        )

        self.minimize_button = tk.Button(
            self.title_bar,
            text="—",
            command=self.minimize_window,
            font=("Segoe UI Semibold", 12),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_secondary"],
            activeforeground=COLORS["text_primary"],
            activebackground=COLORS["bg_hover"],
            relief="flat",
            borderwidth=0,
            width=5,
            cursor="hand2",
        )
        self.minimize_button.pack(side="right", fill="y")
        self.minimize_button.bind(
            "<Enter>",
            lambda _event: self.minimize_button.configure(background=COLORS["bg_hover"]),
        )
        self.minimize_button.bind(
            "<Leave>",
            lambda _event: self.minimize_button.configure(background=COLORS["bg_secondary"]),
        )

        for widget in (self.title_bar, title_icon, self.title_text, self.version_text):
            widget.bind("<ButtonPress-1>", self._start_window_drag)
            widget.bind("<B1-Motion>", self._move_window)

        self.content_frame = tk.Frame(
            self.window_surface,
            background=COLORS["bg_primary"],
        )
        self.content_frame.pack(fill="both", expand=True)

    def _start_window_drag(self, event) -> None:
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _move_window(self, event) -> None:
        x = event.x_root - self._drag_x
        y = max(0, event.y_root - self._drag_y)
        self.geometry(f"+{x}+{y}")

    def _native_window_handle(self) -> int:
        self.update_idletasks()
        if sys.platform == "win32":
            return ctypes.windll.user32.GetParent(self.winfo_id())
        return self.winfo_id()

    def _show_in_taskbar(self) -> None:
        if sys.platform != "win32" or not self.winfo_exists():
            return
        try:
            hwnd = self._native_window_handle()
            get_style = ctypes.windll.user32.GetWindowLongW
            set_style = ctypes.windll.user32.SetWindowLongW
            extended_style = get_style(hwnd, -20)
            extended_style = (extended_style & ~0x00000080) | 0x00040000
            set_style(hwnd, -20, extended_style)
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                0x0001 | 0x0002 | 0x0004 | 0x0020,
            )
        except Exception:
            pass

    def _schedule_rounded_window(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        if self._rounding_job is not None:
            try:
                self.after_cancel(self._rounding_job)
            except Exception:
                pass
        self._rounding_job = self.after(35, self._apply_rounded_window)

    def _apply_rounded_window(self) -> None:
        self._rounding_job = None
        if sys.platform != "win32" or not self.winfo_exists():
            return
        try:
            hwnd = self._native_window_handle()
            width = max(1, self.winfo_width())
            height = max(1, self.winfo_height())

            # Ask Windows 11 for its native rounded-corner treatment.
            corner_preference = ctypes.c_int(2)
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    33,
                    ctypes.byref(corner_preference),
                    ctypes.sizeof(corner_preference),
                )
            except Exception:
                pass

            # Real clipping also works with the custom frameless title bar.
            region = ctypes.windll.gdi32.CreateRoundRectRgn(
                0,
                0,
                width + 1,
                height + 1,
                22,
                22,
            )
            if region:
                ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
        except Exception:
            pass

    def minimize_window(self) -> None:
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.ShowWindow(self._native_window_handle(), 6)
                return
            except Exception:
                pass
        self.overrideredirect(False)
        self.iconify()
        self._restore_override_pending = True
        self.bind("<Map>", self._restore_frameless, add="+")

    def _restore_frameless(self, _event=None) -> None:
        if not self._restore_override_pending:
            return
        self._restore_override_pending = False
        self.after(10, lambda: self.overrideredirect(True))
        self.after(30, self._show_in_taskbar)

    def _create_base_icons(self) -> None:
        def make_icon(kind: str, color: str, label: str = "") -> ImageTk.PhotoImage:
            image = Image.new("RGBA", (112, 84), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            if kind == "folder":
                draw.rounded_rectangle(
                    (9, 22, 103, 76),
                    radius=8,
                    fill=color,
                    outline=COLORS["folder_blue_light"],
                    width=2,
                )
                draw.rounded_rectangle(
                    (14, 12, 55, 32),
                    radius=6,
                    fill=COLORS["folder_blue_light"],
                )
                draw.rectangle((11, 29, 101, 38), fill="#3c96df")
            else:
                draw.rounded_rectangle(
                    (25, 5, 87, 79),
                    radius=6,
                    fill="#dfe2e5",
                    outline="#858d95",
                    width=2,
                )
                draw.polygon([(69, 5), (87, 23), (69, 23)], fill="#aeb4ba")
                if label:
                    draw.rounded_rectangle((32, 43, 80, 65), radius=5, fill=color)
                    draw.text((56, 54), label, anchor="mm", fill="#f7f8f9")
            return ImageTk.PhotoImage(image)

        self.base_icons = {
            "folder": make_icon("folder", COLORS["folder_blue"]),
            "image": make_icon("file", "#59636c", "IMG"),
            "pdf": make_icon("file", "#6c5f60", "PDF"),
            "video": make_icon("file", "#625e6b", "VID"),
            "text": make_icon("file", "#596760", "TXT"),
            "file": make_icon("file", "#5f666d", "FILE"),
        }

        navigation_folder = Image.new("RGBA", (18, 16), (0, 0, 0, 0))
        navigation_draw = ImageDraw.Draw(navigation_folder)
        navigation_draw.rounded_rectangle(
            (1, 4, 17, 15),
            radius=2,
            fill=COLORS["folder_blue"],
            outline=COLORS["folder_blue_light"],
        )
        navigation_draw.rounded_rectangle(
            (3, 1, 10, 6),
            radius=2,
            fill=COLORS["folder_blue_light"],
        )
        self.navigation_folder_icon = ImageTk.PhotoImage(navigation_folder)

    def _clear_window(self) -> None:
        for child in self.content_frame.winfo_children():
            child.destroy()

    @staticmethod
    def _office_button(
        parent,
        text: str,
        command,
        background: str,
        hover: str,
        foreground: str = COLORS["text_primary"],
        width: int | None = None,
        outline: str | None = None,
    ) -> RoundedButton:
        return RoundedButton(
            parent,
            text=text,
            command=command,
            foreground=foreground,
            background=background,
            hover=hover,
            width=width,
            outline=outline,
        )

    def _build_login_screen(self) -> None:
        self._clear_window()
        self.connected = False

        outer = tk.Frame(self.content_frame, background=COLORS["bg_primary"])
        outer.pack(fill="both", expand=True)

        shell = tk.Frame(
            outer,
            background=COLORS["bg_secondary"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        shell.place(
            relx=0.5,
            rely=0.5,
            anchor="center",
            relwidth=0.72,
            relheight=0.72,
        )
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=5)
        shell.grid_columnconfigure(1, weight=6)

        brand_panel = tk.Frame(
            shell,
            background=COLORS["bg_tertiary"],
            padx=44,
            pady=42,
        )
        brand_panel.grid(row=0, column=0, sticky="nsew")

        self.login_logo_image = self._load_photo_asset(APP_LOGO_FILE, (132, 132))
        logo_kwargs = {
            "text": APP_NAME,
            "font": ("Segoe UI Semibold", 26),
            "foreground": COLORS["text_primary"],
            "background": COLORS["bg_tertiary"],
        }
        if self.login_logo_image is not None:
            logo_kwargs.update({"image": self.login_logo_image, "compound": "top"})
        tk.Label(brand_panel, **logo_kwargs).pack(anchor="w")

        tk.Label(
            brand_panel,
            text="Navegação segura para os arquivos\nda sua organização.",
            justify="left",
            font=("Segoe UI", 13),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_tertiary"],
        ).pack(anchor="w", pady=(20, 28))

        for text in (
            "✓  Acesso somente leitura",
            "✓  Credenciais não armazenadas",
            "✓  Downloads com registro local",
        ):
            tk.Label(
                brand_panel,
                text=text,
                font=("Segoe UI", 10),
                foreground=COLORS["text_secondary"],
                background=COLORS["bg_tertiary"],
                anchor="w",
            ).pack(fill="x", pady=5)

        form_panel = tk.Frame(
            shell,
            background=COLORS["bg_secondary"],
            padx=52,
            pady=48,
        )
        form_panel.grid(row=0, column=1, sticky="nsew")
        form_panel.grid_columnconfigure(0, weight=1)

        tk.Label(
            form_panel,
            text="Bem-vindo",
            font=("Segoe UI Semibold", 24),
            foreground=COLORS["text_primary"],
            background=COLORS["bg_secondary"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            form_panel,
            text="Entre com sua conta Samba para continuar.",
            font=("Segoe UI", 10),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_secondary"],
        ).grid(row=1, column=0, sticky="w", pady=(6, 24))

        self.server_label = tk.Label(
            form_panel,
            text="Carregando configuração...",
            font=("Segoe UI", 9),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_tertiary"],
            anchor="w",
            padx=12,
            pady=10,
        )
        self.server_label.grid(row=2, column=0, sticky="ew", pady=(0, 22))

        tk.Label(
            form_panel,
            text="Usuário",
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_secondary"],
            font=("Segoe UI Semibold", 9),
        ).grid(row=3, column=0, sticky="w", pady=(0, 7))
        self.username_entry = tk.Entry(
            form_panel,
            font=("Segoe UI", 11),
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["focus"],
            background=COLORS["bg_tertiary"],
            foreground=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"],
            bd=0,
        )
        self.username_entry.grid(row=4, column=0, sticky="ew", ipady=9)

        tk.Label(
            form_panel,
            text="Senha",
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_secondary"],
            font=("Segoe UI Semibold", 9),
        ).grid(row=5, column=0, sticky="w", pady=(18, 7))
        password_field = tk.Frame(
            form_panel,
            background=COLORS["bg_tertiary"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        password_field.grid(row=6, column=0, sticky="ew")
        password_field.grid_columnconfigure(0, weight=1)

        self.password_visible = False
        self.password_entry = tk.Entry(
            password_field,
            show="●",
            font=("Segoe UI", 11),
            relief="flat",
            highlightthickness=0,
            background=COLORS["bg_tertiary"],
            foreground=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"],
            bd=0,
        )
        self.password_entry.grid(
            row=0,
            column=0,
            sticky="ew",
            ipady=9,
            padx=(10, 4),
        )
        self.password_toggle_button = tk.Button(
            password_field,
            text="👁",
            command=self.toggle_password_visibility,
            font=("Segoe UI Emoji", 11),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_tertiary"],
            activeforeground=COLORS["folder_blue_light"],
            activebackground=COLORS["bg_hover"],
            relief="flat",
            borderwidth=0,
            width=3,
            cursor="hand2",
            takefocus=False,
        )
        self.password_toggle_button.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(0, 3),
            pady=3,
        )
        self.password_entry.bind(
            "<FocusIn>",
            lambda _event: password_field.configure(
                highlightbackground=COLORS["focus"]
            ),
        )
        self.password_entry.bind(
            "<FocusOut>",
            lambda _event: password_field.configure(
                highlightbackground=COLORS["border"]
            ),
        )
        self.password_tooltip = Tooltip(
            self.password_toggle_button,
            "Mostrar ou ocultar a senha.",
            delay_ms=250,
        )

        self.login_button = self._office_button(
            form_panel,
            text="Entrar com segurança  →",
            command=self.login,
            background=COLORS["blue"],
            hover=COLORS["blue_hover"],
            outline=COLORS["blue_hover"],
        )
        self.login_button.grid(row=7, column=0, sticky="ew", pady=(24, 10))

        self.login_status = tk.Label(
            form_panel,
            text="",
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_secondary"],
            font=("Segoe UI", 9),
        )
        self.login_status.grid(row=8, column=0, sticky="w")

        login_info = tk.Label(
            form_panel,
            text="ⓘ  Informações e atualização",
            font=("Segoe UI Semibold", 9),
            foreground=COLORS["folder_blue_light"],
            background=COLORS["bg_secondary"],
            cursor="hand2",
        )
        login_info.grid(row=9, column=0, sticky="w", pady=(14, 0))
        login_info.bind("<Button-1>", self.show_about_dialog)
        login_info.bind(
            "<Enter>",
            lambda _event: login_info.configure(
                foreground=COLORS["path_green"]
            ),
        )
        login_info.bind(
            "<Leave>",
            lambda _event: login_info.configure(
                foreground=COLORS["folder_blue_light"]
            ),
        )

        self.password_entry.bind("<Return>", lambda _event: self.login())
        self.username_entry.focus_set()

    def toggle_password_visibility(self) -> None:
        self.password_visible = not self.password_visible
        self.password_entry.configure(
            show="" if self.password_visible else "●"
        )
        self.password_toggle_button.configure(
            text="◉" if self.password_visible else "👁",
            foreground=(
                COLORS["path_green"]
                if self.password_visible
                else COLORS["text_secondary"]
            ),
        )

    def login(self) -> None:
        if not self.config_data:
            return

        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            messagebox.showwarning("Credenciais", "Informe o usuário e a senha.")
            return
        if self.password_visible:
            self.toggle_password_visibility()

        self.login_button.configure(state="disabled")
        self.login_status.configure(text="Conectando...")
        self.update_idletasks()
        self.logger.set_session(username, self.config_data.server_ip)
        self.logger.write("LOGIN_ATTEMPT", f"display_name={self.config_data.display_name}")

        def worker() -> None:
            try:
                socket.create_connection(
                    (self.config_data.server_ip, self.config_data.port),
                    timeout=self.config_data.connection_timeout,
                ).close()
                smbclient.ClientConfig(
                    skip_dfs=self.config_data.skip_dfs,
                    auth_protocol=self.config_data.auth_protocol,
                )
                smbclient.register_session(
                    self.config_data.server_ip,
                    username=username,
                    password=password,
                    port=self.config_data.port,
                    connection_timeout=self.config_data.connection_timeout,
                    auth_protocol=self.config_data.auth_protocol,
                )
                self.task_queue.put(("login_success", username))
            except Exception as error:
                self.logger.write("LOGIN_FAILED", str(error))
                smbclient.reset_connection_cache()
                self.task_queue.put(
                    ("login_error", friendly_connection_error(error, self.config_data))
                )

        threading.Thread(target=worker, daemon=True).start()

    def _build_browser_screen(self) -> None:
        self._clear_window()

        top = tk.Frame(
            self.content_frame,
            background=COLORS["bg_secondary"],
            padx=22,
            pady=16,
        )
        top.pack(fill="x")

        identity = tk.Frame(top, background=COLORS["bg_secondary"])
        identity.pack(side="left")
        tk.Label(
            identity,
            text=self.config_data.display_name if self.config_data else APP_NAME,
            font=("Segoe UI Semibold", 18),
            foreground=COLORS["text_primary"],
            background=COLORS["bg_secondary"],
        ).pack(anchor="w")
        tk.Label(
            identity,
            text="Arquivos corporativos • acesso protegido",
            font=("Segoe UI", 9),
            foreground=COLORS["text_muted"],
            background=COLORS["bg_secondary"],
        ).pack(anchor="w", pady=(3, 0))

        account = tk.Frame(top, background=COLORS["bg_secondary"])
        account.pack(side="right")
        user_badge = tk.Frame(
            account,
            background=COLORS["bg_tertiary"],
            padx=12,
            pady=7,
        )
        user_badge.pack(side="left", padx=(0, 10))
        tk.Label(
            user_badge,
            text="●",
            font=("Segoe UI", 8),
            foreground=COLORS["success"],
            background=COLORS["bg_tertiary"],
        ).pack(side="left", padx=(0, 7))
        tk.Label(
            user_badge,
            text=self.username,
            font=("Segoe UI Semibold", 9),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_tertiary"],
        ).pack(side="left")
        self._office_button(
            account,
            text="Sair",
            command=self.logout,
            background=COLORS["danger_bg"],
            hover=COLORS["danger"],
            outline=COLORS["danger"],
        ).pack(side="left")

        toolbar = tk.Frame(
            self.content_frame,
            background=COLORS["bg_tertiary"],
            padx=18,
            pady=11,
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        toolbar.pack(fill="x")

        self._office_button(
            toolbar,
            text="⌂  Home",
            command=self.go_home,
            background="#365f78",
            hover="#427795",
            outline="#4f88a8",
        ).pack(side="left", padx=(0, 7))
        self._office_button(
            toolbar,
            text="←  Voltar",
            command=self.go_back,
            background="#46505a",
            hover="#596570",
            outline="#68737e",
        ).pack(side="left")
        self._office_button(
            toolbar,
            text="↻  Atualizar",
            command=self.refresh,
            background=COLORS["blue"],
            hover=COLORS["blue_hover"],
            outline=COLORS["blue_hover"],
        ).pack(side="left", padx=7)
        self.download_button = self._office_button(
            toolbar,
            text="↓  Baixar selecionados",
            command=self.download_selected,
            background=COLORS["green"],
            hover=COLORS["green_hover"],
            outline=COLORS["green_hover"],
        )
        self.download_button.pack(side="left", padx=(5, 7))
        self._office_button(
            toolbar,
            text="✓  Selecionar tudo",
            command=self.select_all_items,
            background=COLORS["purple"],
            hover=COLORS["purple_hover"],
            outline=COLORS["purple_hover"],
        ).pack(side="left")

        self.view_button = self._office_button(
            toolbar,
            text="☷  Detalhes",
            command=self.toggle_view_mode,
            background=COLORS["amber"],
            hover=COLORS["amber_hover"],
            outline=COLORS["amber_hover"],
        )
        self.view_button.pack(side="left", padx=(12, 0))

        self.path_label = tk.Label(
            toolbar,
            text="",
            anchor="e",
            font=("Segoe UI", 9),
            foreground=COLORS["text_muted"],
            background=COLORS["bg_tertiary"],
        )
        self.path_label.pack(side="right", fill="x", expand=True, padx=(18, 0))

        browser_panes = tk.PanedWindow(
            self.content_frame,
            orient="horizontal",
            background=COLORS["border"],
            borderwidth=0,
            relief="flat",
            sashwidth=5,
            sashrelief="flat",
            showhandle=False,
        )
        browser_panes.pack(fill="both", expand=True, padx=16, pady=(14, 10))

        navigation_frame = tk.Frame(
            browser_panes,
            width=270,
            background=COLORS["bg_secondary"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        navigation_frame.pack_propagate(False)
        browser_panes.add(navigation_frame, minsize=210, width=270)

        navigation_header = tk.Frame(
            navigation_frame,
            background=COLORS["bg_tertiary"],
            padx=14,
            pady=12,
        )
        navigation_header.pack(fill="x")
        tk.Label(
            navigation_header,
            text="NAVEGAÇÃO",
            font=("Segoe UI Semibold", 10),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_tertiary"],
        ).pack(side="left")

        navigation_body = tk.Frame(navigation_frame, background=COLORS["bg_secondary"])
        navigation_body.pack(fill="both", expand=True)
        self.navigation_tree = ttk.Treeview(
            navigation_body,
            show="tree",
            selectmode="browse",
            style="Navigation.Treeview",
        )
        navigation_scrollbar = AutoHideScrollbar(
            navigation_body,
            orient="vertical",
            command=self.navigation_tree.yview,
        )
        self.navigation_tree.configure(yscrollcommand=navigation_scrollbar.set)
        self.navigation_tree.tag_configure(
            "active_path",
            foreground=COLORS["path_green_muted"],
            font=("Segoe UI Semibold", 10),
        )
        self.navigation_tree.tag_configure(
            "current_path",
            foreground=COLORS["path_green"],
            background=COLORS["path_green_bg"],
            font=("Segoe UI Semibold", 10),
        )
        self.navigation_tree.tag_configure(
            "placeholder",
            foreground=COLORS["text_muted"],
            font=("Segoe UI", 9, "italic"),
        )
        self.navigation_tree.pack(side="left", fill="both", expand=True)
        navigation_scrollbar.pack(side="right", fill="y")
        self.navigation_tree.bind("<<TreeviewOpen>>", self._on_navigation_open)
        self.navigation_tree.bind(
            "<<TreeviewSelect>>", self._on_navigation_select
        )
        self._initialize_navigation_tree()

        list_frame = tk.Frame(
            browser_panes,
            background=COLORS["bg_secondary"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        browser_panes.add(list_frame, minsize=420, stretch="always")

        self.view_container = tk.Frame(list_frame, background=COLORS["bg_secondary"])
        self.view_container.pack(fill="both", expand=True)

        self.details_frame = tk.Frame(self.view_container, background=COLORS["bg_secondary"])
        columns = ("name", "type", "size", "modified")
        self.tree = ttk.Treeview(
            self.details_frame, columns=columns, show="headings", selectmode="extended"
        )
        self.tree.heading("name", text="Nome")
        self.tree.heading("type", text="Tipo")
        self.tree.heading("size", text="Tamanho")
        self.tree.heading("modified", text="Modificado")
        self.tree.column("name", width=360, anchor="w")
        self.tree.column("type", width=110, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("modified", width=150, anchor="center")

        scrollbar = AutoHideScrollbar(
            self.details_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self.open_selected)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        self.thumbnail_frame = tk.Frame(self.view_container, background=COLORS["bg_secondary"])
        self.thumbnail_canvas = tk.Canvas(
            self.thumbnail_frame,
            background=COLORS["bg_secondary"],
            highlightthickness=0,
        )
        thumbnail_scrollbar = AutoHideScrollbar(
            self.thumbnail_frame, orient="vertical", command=self.thumbnail_canvas.yview
        )
        self.thumbnail_canvas.configure(yscrollcommand=thumbnail_scrollbar.set)
        self.thumbnail_canvas.pack(side="left", fill="both", expand=True)
        thumbnail_scrollbar.pack(side="right", fill="y")

        self.thumbnail_inner = tk.Frame(self.thumbnail_canvas, background=COLORS["bg_secondary"])
        self.thumbnail_window = self.thumbnail_canvas.create_window(
            (0, 0), window=self.thumbnail_inner, anchor="nw"
        )
        self.thumbnail_inner.bind(
            "<Configure>",
            lambda _event: self.thumbnail_canvas.configure(
                scrollregion=self.thumbnail_canvas.bbox("all")
            ),
        )
        self.thumbnail_canvas.bind(
            "<Configure>",
            lambda event: self.thumbnail_canvas.itemconfigure(
                self.thumbnail_window, width=event.width
            ),
        )
        self.thumbnail_canvas.bind_all("<MouseWheel>", self._on_thumbnail_mousewheel)
        self._show_active_view()

        self.progress_frame = tk.Frame(
            self.content_frame,
            background=COLORS["bg_tertiary"],
            padx=18,
            pady=10,
        )
        self.progress_label = tk.Label(
            self.progress_frame,
            text="Preparando download...",
            font=("Segoe UI Semibold", 9),
            foreground=COLORS["text_primary"],
            background=COLORS["bg_tertiary"],
        )
        self.progress_label.pack(side="left", padx=(0, 12))
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.download_progress,
            maximum=100,
            style="Office.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_percent = tk.Label(
            self.progress_frame,
            text="0%",
            width=5,
            font=("Segoe UI Semibold", 9),
            foreground=COLORS["accent"],
            background=COLORS["bg_tertiary"],
        )
        self.progress_percent.pack(side="right", padx=(12, 0))

        self.status_frame = tk.Frame(
            self.content_frame,
            background=COLORS["bg_secondary"],
            padx=18,
            pady=10,
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        self.status_frame.pack(fill="x")
        self.status_label = tk.Label(
            self.status_frame,
            text="●  Conectado",
            anchor="w",
            font=("Segoe UI", 9),
            foreground=COLORS["success"],
            background=COLORS["bg_secondary"],
        )
        self.status_label.pack(side="left")
        self.selection_label = tk.Label(
            self.status_frame,
            text="0 selecionado(s)",
            font=("Segoe UI", 9),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_secondary"],
        )
        self.selection_label.pack(side="left", padx=(18, 0))
        self.toast_label = tk.Label(
            self.status_frame,
            text="",
            font=("Segoe UI Semibold", 9),
            foreground=COLORS["success"],
            background=COLORS["bg_secondary"],
        )
        self.toast_label.pack(side="left", padx=(24, 0))
        security_note = tk.Label(
            self.status_frame,
            text="Somente leitura  •  credenciais não são salvas",
            font=("Segoe UI", 9),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_secondary"],
        )
        security_note.pack(side="right")

        self.info_badge = tk.Label(
            self.status_frame,
            text="ⓘ",
            font=("Segoe UI Symbol", 14),
            foreground=COLORS["folder_blue_light"],
            background=COLORS["bg_secondary"],
            cursor="hand2",
            padx=8,
        )
        self.info_badge.pack(side="right", padx=(0, 8))
        self.info_badge.bind(
            "<Enter>",
            lambda _event: self.info_badge.configure(
                foreground=COLORS["path_green"]
            ),
            add="+",
        )
        self.info_badge.bind(
            "<Leave>",
            lambda _event: self.info_badge.configure(
                foreground=COLORS["folder_blue_light"]
            ),
            add="+",
        )
        self.info_badge.bind("<Button-1>", self.show_about_dialog, add="+")
        self.info_tooltip = Tooltip(
            self.info_badge,
            "AccessView\n\n"
            "Este software pertence à Click's da Serra.\n"
            "Desenvolvido por Raphael Alves.\n\n"
            "Clique para ver informações e carregar atualizações.",
        )

        self.refresh()

    def _next_navigation_id(self) -> str:
        self.navigation_node_counter += 1
        return f"nav_{self.navigation_node_counter}"

    def _initialize_navigation_tree(self) -> None:
        self.navigation_generation += 1
        self.navigation_tree.delete(*self.navigation_tree.get_children())
        self.navigation_paths.clear()
        self.navigation_nodes.clear()
        self.navigation_loaded.clear()
        self.navigation_loading.clear()
        self.navigation_node_counter = 0

        root_id = self._next_navigation_id()
        root_text = self.config_data.display_name if self.config_data else APP_NAME
        self.navigation_tree.insert(
            "",
            "end",
            iid=root_id,
            text=root_text,
            open=True,
            image=self.navigation_folder_icon,
        )
        self.navigation_paths[root_id] = ()
        self.navigation_nodes[()] = root_id
        self.navigation_loaded.add(())

        if self.config_data:
            for share_name in self.config_data.shares:
                self._insert_navigation_node(
                    root_id,
                    (share_name,),
                    share_name,
                    may_have_children=True,
                )

        self._select_navigation_path(())

    def _insert_navigation_node(
        self,
        parent_id: str,
        parts: tuple[str, ...],
        name: str,
        may_have_children: bool,
    ) -> str:
        existing = self.navigation_nodes.get(parts)
        if existing and self.navigation_tree.exists(existing):
            return existing

        node_id = self._next_navigation_id()
        self.navigation_tree.insert(
            parent_id,
            "end",
            iid=node_id,
            text=name,
            open=False,
            image=self.navigation_folder_icon,
        )
        self.navigation_paths[node_id] = parts
        self.navigation_nodes[parts] = node_id
        if may_have_children:
            self.navigation_tree.insert(
                node_id,
                "end",
                iid=f"{node_id}_loading",
                text="Carregar pastas...",
                tags=("placeholder",),
            )
        return node_id

    def _select_navigation_path(self, parts: tuple[str, ...]) -> None:
        node_id = self.navigation_nodes.get(parts)
        if not node_id or not self.navigation_tree.exists(node_id):
            return
        self._syncing_navigation = True
        try:
            self._focus_navigation_branch(parts)
            self.navigation_tree.selection_set(node_id)
            self.navigation_tree.focus(node_id)
            self.navigation_tree.see(node_id)
        finally:
            self._syncing_navigation = False

    def _focus_navigation_branch(self, parts: tuple[str, ...]) -> None:
        """Highlight the active path and collapse branches outside it."""
        for node_parts, node_id in tuple(self.navigation_nodes.items()):
            if not self.navigation_tree.exists(node_id):
                continue

            is_prefix = (
                len(node_parts) <= len(parts)
                and parts[: len(node_parts)] == node_parts
            )
            if node_parts == parts:
                tags = ("current_path",)
            elif is_prefix:
                tags = ("active_path",)
            else:
                tags = ()

            self.navigation_tree.item(node_id, tags=tags)
            self.navigation_tree.item(
                node_id,
                open=bool(is_prefix),
            )

    def _on_navigation_select(self, _event=None) -> None:
        if self._syncing_navigation or not self.connected:
            return
        selected = self.navigation_tree.selection()
        if not selected:
            return
        parts = self.navigation_paths.get(selected[0])
        if parts is None or list(parts) == self.current_parts:
            return
        self.current_parts = list(parts)
        self.logger.write("NAVIGATE_TREE", self.current_path)
        self.refresh()

    def _on_navigation_open(self, _event=None) -> None:
        node_id = self.navigation_tree.focus()
        parts = self.navigation_paths.get(node_id)
        if parts is None or not parts:
            return
        self._load_navigation_children(node_id, parts)

    def _load_navigation_children(
        self,
        node_id: str,
        parts: tuple[str, ...],
    ) -> None:
        if (
            parts in self.navigation_loaded
            or parts in self.navigation_loading
            or not self.connected
        ):
            return
        self.navigation_loading.add(parts)
        self._set_navigation_placeholder(node_id, "Carregando...")
        remote_path = self._path_from_parts(parts)
        generation = self.navigation_generation

        def worker() -> None:
            try:
                folders = sorted(
                    (
                        entry.name
                        for entry in smbclient.scandir(remote_path)
                        if entry.is_dir()
                    ),
                    key=str.casefold,
                )
                self.task_queue.put(
                    (
                        "navigation_loaded",
                        (node_id, parts, folders, generation),
                    )
                )
            except Exception as error:
                self.task_queue.put(
                    (
                        "navigation_error",
                        (node_id, parts, str(error), generation),
                    )
                )

        threading.Thread(target=worker, daemon=True).start()

    def _set_navigation_placeholder(self, node_id: str, text: str) -> None:
        for child_id in self.navigation_tree.get_children(node_id):
            if "placeholder" in self.navigation_tree.item(child_id, "tags"):
                self.navigation_tree.item(child_id, text=text)
                return
        self.navigation_tree.insert(
            node_id,
            "end",
            iid=f"{node_id}_loading",
            text=text,
            tags=("placeholder",),
        )

    def _populate_navigation_children(
        self,
        node_id: str,
        parts: tuple[str, ...],
        folders: list[str],
    ) -> None:
        if not self.navigation_tree.exists(node_id):
            return
        for child_id in self.navigation_tree.get_children(node_id):
            if "placeholder" in self.navigation_tree.item(child_id, "tags"):
                self.navigation_tree.delete(child_id)

        for folder_name in folders:
            child_parts = parts + (folder_name,)
            self._insert_navigation_node(
                node_id,
                child_parts,
                folder_name,
                may_have_children=True,
            )
        self.navigation_loading.discard(parts)
        self.navigation_loaded.add(parts)

    def _path_from_parts(self, parts: tuple[str, ...]) -> str:
        if not self.config_data:
            return ""
        if not parts:
            return rf"\\{self.config_data.server_ip}"
        share_name, *subfolders = parts
        path = self.config_data.share_path(share_name)
        if subfolders:
            path += "\\" + "\\".join(subfolders)
        return path

    def _sync_current_navigation(
        self,
        rows: list[dict],
    ) -> None:
        current_parts = tuple(self.current_parts)
        node_id = self.navigation_nodes.get(current_parts)
        if node_id and self.navigation_tree.exists(node_id):
            folders = [
                str(entry["name"])
                for entry in rows
                if entry["is_dir"] and not entry.get("is_share")
            ]
            if current_parts:
                self._populate_navigation_children(
                    node_id,
                    current_parts,
                    folders,
                )
            self._select_navigation_path(current_parts)

    def toggle_view_mode(self) -> None:
        self.view_mode = "details" if self.view_mode == "thumbnails" else "thumbnails"
        self._show_active_view()

    def _show_active_view(self) -> None:
        if not hasattr(self, "thumbnail_frame"):
            return
        self.details_frame.pack_forget()
        self.thumbnail_frame.pack_forget()
        if self.view_mode == "thumbnails":
            self.thumbnail_frame.pack(fill="both", expand=True)
            self.view_button.configure(text="☷ Detalhes")
        else:
            self.details_frame.pack(fill="both", expand=True)
            self.view_button.configure(text="▦ Miniaturas")

    def _on_thumbnail_mousewheel(self, event) -> None:
        if (
            self.view_mode == "thumbnails"
            and hasattr(self, "thumbnail_canvas")
            and self.thumbnail_canvas.winfo_exists()
        ):
            self.thumbnail_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_tree_select(self, _event=None) -> None:
        selected = self.tree.selection()
        self.selected_item_ids = set(selected)
        self.selected_item_id = selected[-1] if selected else None
        if self.selected_item_id:
            self.selection_anchor_id = self.selected_item_id
        self._update_grid_selection_style()
        self._update_selection_status()

    @property
    def current_path(self) -> str:
        if not self.config_data:
            return ""
        if not self.current_parts:
            return rf"\\{self.config_data.server_ip}"
        share_name, *subfolders = self.current_parts
        path = self.config_data.share_path(share_name)
        if subfolders:
            path += "\\" + "\\".join(subfolders)
        return path

    def remote_child_path(self, name: str) -> str:
        return self.current_path.rstrip("\\") + "\\" + name

    def refresh(self) -> None:
        if not self.connected:
            return
        self.directory_generation += 1
        generation = self.directory_generation
        self.selected_item_id = None
        self.selected_item_ids.clear()
        self.selection_anchor_id = None
        self.status_label.configure(
            text="●  Carregando conteúdo...",
            foreground=COLORS["text_secondary"],
        )
        if not self.current_parts:
            self.path_label.configure(text=rf"\\{self.config_data.server_ip}")
            rows = [
                {
                    "name": share_name,
                    "is_dir": True,
                    "is_share": True,
                    "size": 0,
                    "modified": None,
                }
                for share_name in self.config_data.shares
            ]
            self.task_queue.put(("directory_loaded", (rows, generation)))
            return

        self.path_label.configure(text=self.current_path)

        def worker() -> None:
            try:
                rows = []
                for entry in smbclient.scandir(self.current_path):
                    stat = entry.stat()
                    is_dir = entry.is_dir()
                    rows.append(
                        {
                            "name": entry.name,
                            "is_dir": is_dir,
                            "is_share": False,
                            "size": 0 if is_dir else stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime),
                        }
                    )
                rows.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
                self.task_queue.put(("directory_loaded", (rows, generation)))
            except Exception as error:
                self.task_queue.put(
                    (
                        "operation_error",
                        (
                            "Falha ao abrir o compartilhamento",
                            friendly_connection_error(error, self.config_data),
                        ),
                    )
                )

        threading.Thread(target=worker, daemon=True).start()

    def _selected_entry(self) -> dict | None:
        if not self.selected_item_id:
            return None
        return self.entries.get(self.selected_item_id)

    def _selected_entries(self) -> list[tuple[str, dict]]:
        return [
            (item_id, entry)
            for item_id, entry in self.entries.items()
            if item_id in self.selected_item_ids
        ]

    def _file_icon_key(self, entry: dict) -> str:
        if entry["is_dir"]:
            return "folder"
        suffix = Path(entry["name"]).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}:
            return "image"
        if suffix == ".pdf":
            return "pdf"
        if suffix in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}:
            return "video"
        if suffix in {".txt", ".log", ".csv", ".json", ".xml", ".ini", ".md", ".doc", ".docx"}:
            return "text"
        return "file"

    def _thumbnail_key(self, entry: dict) -> str:
        return f"{self.current_path}|{entry['name']}"

    def _bind_card(self, widget: tk.Widget, item_id: str) -> None:
        widget.bind(
            "<Button-1>",
            lambda event, value=item_id: self.select_grid_item(value, event.state),
        )
        widget.bind("<Double-1>", lambda _event, value=item_id: self.open_grid_item(value))
        for child in widget.winfo_children():
            self._bind_card(child, item_id)

    def select_grid_item(self, item_id: str, state: int = 0) -> None:
        ctrl_pressed = bool(state & 0x0004)
        shift_pressed = bool(state & 0x0001)

        if shift_pressed and self.selection_anchor_id in self.entries:
            ordered_ids = list(self.entries)
            start = ordered_ids.index(self.selection_anchor_id)
            end = ordered_ids.index(item_id)
            first, last = sorted((start, end))
            if not ctrl_pressed:
                self.selected_item_ids.clear()
            self.selected_item_ids.update(ordered_ids[first : last + 1])
        elif ctrl_pressed:
            if item_id in self.selected_item_ids:
                self.selected_item_ids.remove(item_id)
            else:
                self.selected_item_ids.add(item_id)
            self.selection_anchor_id = item_id
        else:
            self.selected_item_ids = {item_id}
            self.selection_anchor_id = item_id

        self.selected_item_id = item_id
        self._update_grid_selection_style()
        existing_tree_ids = [
            selected_id
            for selected_id in self.selected_item_ids
            if self.tree.exists(selected_id)
        ]
        self.tree.selection_set(existing_tree_ids)
        if self.tree.exists(item_id):
            self.tree.focus(item_id)
        self._update_selection_status()

    def _update_grid_selection_style(self) -> None:
        for current_id, card in self.grid_cards.items():
            card.set_selected(current_id in self.selected_item_ids)

    def _update_selection_status(self) -> None:
        if hasattr(self, "selection_label"):
            count = len(self.selected_item_ids)
            self.selection_label.configure(text=f"{count} selecionado(s)")

    def select_all_items(self) -> None:
        self.selected_item_ids = set(self.entries)
        self.selected_item_id = next(reversed(self.entries), None) if self.entries else None
        self.selection_anchor_id = self.selected_item_id
        self.tree.selection_set(
            [item_id for item_id in self.selected_item_ids if self.tree.exists(item_id)]
        )
        self._update_grid_selection_style()
        self._update_selection_status()

    def open_grid_item(self, item_id: str) -> None:
        self.select_grid_item(item_id, 0)
        self.open_selected()

    def _render_thumbnail_grid(self) -> None:
        for child in self.thumbnail_inner.winfo_children():
            child.destroy()
        self.thumbnail_labels.clear()
        self.grid_cards.clear()

        if not self.entries:
            empty = tk.Frame(
                self.thumbnail_inner,
                background=COLORS["bg_secondary"],
                padx=30,
                pady=50,
            )
            empty.grid(row=0, column=0, sticky="nsew")
            tk.Label(
                empty,
                text="Esta pasta está vazia",
                font=("Segoe UI Semibold", 15),
                foreground=COLORS["text_primary"],
                background=COLORS["bg_secondary"],
            ).pack()
            tk.Label(
                empty,
                text="Não há arquivos ou subpastas para exibir.",
                font=("Segoe UI", 10),
                foreground=COLORS["text_muted"],
                background=COLORS["bg_secondary"],
            ).pack(pady=(7, 0))
            return

        available_width = max(self.thumbnail_canvas.winfo_width(), 600)
        columns = max(2, available_width // 170)
        for column in range(columns):
            self.thumbnail_inner.grid_columnconfigure(column, weight=1, minsize=160)

        for index, (item_id, entry) in enumerate(self.entries.items()):
            row, column = divmod(index, columns)
            thumbnail_key = self._thumbnail_key(entry)
            icon = self.thumbnail_images.get(
                thumbnail_key, self.base_icons[self._file_icon_key(entry)]
            )
            card = RoundedThumbnailCard(
                self.thumbnail_inner,
                image=icon,
                text=entry["name"],
            )
            card.grid(row=row, column=column, padx=8, pady=8, sticky="n")
            self.grid_cards[item_id] = card
            self.thumbnail_labels[thumbnail_key] = card
            self._bind_card(card, item_id)

        self.thumbnail_inner.update_idletasks()
        self.thumbnail_canvas.configure(scrollregion=self.thumbnail_canvas.bbox("all"))

    def _start_thumbnail_loading(self, generation: int) -> None:
        candidates = [
            entry
            for entry in self.entries.values()
            if not entry["is_dir"]
            and self._file_icon_key(entry) == "image"
            and entry["size"] <= 25 * 1024 * 1024
            and self._thumbnail_key(entry) not in self.thumbnail_images
        ][:60]
        if not candidates:
            return

        base_path = self.current_path

        def worker() -> None:
            for entry in candidates:
                if generation != self.directory_generation or not self.connected:
                    return
                try:
                    remote_path = base_path.rstrip("\\") + "\\" + entry["name"]
                    with smbclient.open_file(remote_path, mode="rb") as remote:
                        data = remote.read()
                    with Image.open(io.BytesIO(data)) as image:
                        image = image.convert("RGB")
                        image.thumbnail((120, 82), Image.Resampling.LANCZOS)
                        canvas = Image.new("RGB", (120, 84), "white")
                        x = (120 - image.width) // 2
                        y = (84 - image.height) // 2
                        canvas.paste(image, (x, y))
                    key = f"{base_path}|{entry['name']}"
                    self.task_queue.put(("thumbnail_ready", (key, canvas, generation)))
                except Exception:
                    continue

        threading.Thread(target=worker, daemon=True).start()

    def open_selected(self, _event=None) -> None:
        selected = self._selected_entries()
        if len(selected) != 1:
            return
        _, entry = selected[0]
        if entry["is_dir"]:
            self.logger.write(
                "OPEN_SHARE" if entry.get("is_share") else "OPEN_FOLDER",
                self.remote_child_path(entry["name"]),
            )
            self.current_parts.append(entry["name"])
            self.refresh()

    def go_back(self) -> None:
        if self.current_parts:
            self.current_parts.pop()
            self.logger.write("NAVIGATE_BACK", self.current_path)
            self.refresh()

    def go_home(self) -> None:
        """Return to the server root and collapse the navigation tree."""
        self.current_parts.clear()
        self.selected_item_id = None
        self.selected_item_ids.clear()
        self.selection_anchor_id = None
        self.logger.write("NAVIGATE_HOME", self.current_path)
        self._select_navigation_path(())
        self.refresh()

    def show_about_dialog(self, _event=None) -> None:
        if hasattr(self, "_about_window") and self._about_window.winfo_exists():
            self._about_window.lift()
            self._about_window.focus_force()
            return

        dialog = tk.Toplevel(self)
        self._about_window = dialog
        dialog.title(f"Sobre o {APP_NAME}")
        dialog.configure(background=COLORS["bg_secondary"])
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        width, height = 470, 405
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - width) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        body = tk.Frame(
            dialog,
            background=COLORS["bg_secondary"],
            padx=30,
            pady=26,
        )
        body.pack(fill="both", expand=True)

        about_logo = self._load_photo_asset(APP_LOGO_FILE, (78, 78))
        if about_logo is not None:
            self._about_logo = about_logo
            tk.Label(
                body,
                image=about_logo,
                background=COLORS["bg_secondary"],
            ).pack()

        tk.Label(
            body,
            text=f"{APP_NAME}  •  v{APP_VERSION}",
            font=("Segoe UI Semibold", 18),
            foreground=COLORS["text_primary"],
            background=COLORS["bg_secondary"],
        ).pack(pady=(10, 4))
        tk.Label(
            body,
            text=(
                "Este software pertence à Click's da Serra.\n"
                "Desenvolvido por Raphael Alves."
            ),
            justify="center",
            font=("Segoe UI", 10),
            foreground=COLORS["text_secondary"],
            background=COLORS["bg_secondary"],
        ).pack(pady=(0, 20))

        update_state = load_update_state()
        if update_state.get("updated_at"):
            update_status = (
                f"Última atualização: {update_state.get('installed_version', APP_VERSION)}\n"
                f"Aplicada em: {update_state['updated_at']}"
            )
        else:
            update_status = (
                "Instalação base — nenhuma atualização por pacote foi aplicada."
            )
        tk.Label(
            body,
            text=update_status,
            justify="center",
            font=("Segoe UI", 9),
            foreground=COLORS["path_green"],
            background=COLORS["bg_tertiary"],
            padx=14,
            pady=9,
        ).pack(fill="x", pady=(0, 16))

        self._office_button(
            body,
            text="↑  Carregar atualização",
            command=lambda: self.choose_update_package(dialog),
            background=COLORS["blue"],
            hover=COLORS["blue_hover"],
            outline=COLORS["blue_hover"],
        ).pack(fill="x", pady=(0, 10))
        self._office_button(
            body,
            text="Fechar",
            command=dialog.destroy,
            background=COLORS["bg_elevated"],
            hover=COLORS["bg_hover"],
            outline=COLORS["border_light"],
        ).pack(fill="x")

    def choose_update_package(self, parent: tk.Toplevel | None = None) -> None:
        package_name = filedialog.askopenfilename(
            parent=parent or self,
            title="Selecione o pacote de atualização do AccessView",
            filetypes=[
                ("Atualização do AccessView", "*.zip"),
                ("Arquivos ZIP", "*.zip"),
            ],
        )
        if not package_name:
            return

        package_path = Path(package_name)
        try:
            manifest = validate_update_package(package_path)
        except Exception as error:
            messagebox.showerror(
                "Atualização inválida",
                str(error),
                parent=parent or self,
            )
            return

        target_version = str(manifest["version"])
        confirmed = messagebox.askyesno(
            "Instalar atualização",
            (
                f"Versão instalada: {APP_VERSION}\n"
                f"Nova versão: {target_version}\n\n"
                "O AccessView será fechado durante a atualização. O config.json "
                "será preservado e uma cópia de segurança será criada.\n\n"
                "Deseja continuar?"
            ),
            parent=parent or self,
        )
        if not confirmed:
            return

        try:
            self._launch_external_updater(
                package_path,
                target_version,
                str(manifest["_package_sha256"]),
            )
        except Exception as error:
            messagebox.showerror(
                "Não foi possível iniciar o atualizador",
                str(error),
                parent=parent or self,
            )

    def _launch_external_updater(
        self,
        package_path: Path,
        target_version: str,
        package_sha256: str,
    ) -> None:
        staging_dir = Path(tempfile.mkdtemp(prefix="accessview_update_"))
        staged_package = staging_dir / package_path.name
        shutil.copy2(package_path, staged_package)

        install_dir = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent
        )
        arguments = [
            "--package",
            str(staged_package),
            "--install-dir",
            str(install_dir),
            "--pid",
            str(os.getpid()),
            "--app-exe",
            "AccessView.exe",
            "--target-version",
            target_version,
            "--previous-version",
            APP_VERSION,
            "--package-sha256",
            package_sha256,
        ]

        if getattr(sys, "frozen", False):
            updater_source = install_dir / APP_UPDATER_FILE
            if not updater_source.is_file():
                raise FileNotFoundError(
                    f"O atualizador não foi encontrado: {updater_source}"
                )
            staged_updater = staging_dir / APP_UPDATER_FILE
            shutil.copy2(updater_source, staged_updater)
            parameter_text = subprocess.list2cmdline(arguments)
            result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                str(staged_updater),
                parameter_text,
                str(staging_dir),
                1,
            )
            if result <= 32:
                raise RuntimeError(
                    "A permissão administrativa foi cancelada ou negada."
                )
        else:
            updater_script = install_dir / "updater.py"
            if not updater_script.is_file():
                raise FileNotFoundError(
                    f"O script do atualizador não foi encontrado: {updater_script}"
                )
            subprocess.Popen(
                [sys.executable, str(updater_script), *arguments],
                cwd=staging_dir,
            )

        self.logger.write(
            "UPDATE_STARTED",
            f"from={APP_VERSION} to={target_version} package={package_path.name}",
        )
        smbclient.reset_connection_cache()
        self.after(250, self.destroy)

    def download_selected(self) -> None:
        if self.download_active:
            return

        selected = [
            entry for _, entry in self._selected_entries() if not entry["is_dir"]
        ]
        if not selected:
            messagebox.showinfo("Download", "Selecione um ou mais arquivos.")
            return

        destination = filedialog.askdirectory(title="Escolha a pasta para salvar os arquivos")
        if not destination:
            return

        destination_dir = Path(destination)
        base_remote_path = self.current_path
        total_bytes = sum(max(0, int(entry["size"])) for entry in selected)
        self.download_active = True
        self.download_progress.set(0)
        self.download_button.configure(state="disabled", background=COLORS["green"])
        self.progress_label.configure(text=f"Preparando {len(selected)} arquivo(s)...")
        self.progress_percent.configure(text="0%")
        self.progress_frame.pack(fill="x", before=self.status_frame)
        self.status_label.configure(
            text=f"●  Baixando {len(selected)} arquivo(s)...",
            foreground=COLORS["accent"],
        )
        self.logger.write(
            "DOWNLOAD_BATCH_START",
            f"count={len(selected)} source={base_remote_path} destination={destination_dir}",
        )

        def worker() -> None:
            completed = 0
            failures: list[str] = []
            downloaded_bytes = 0
            try:
                for index, entry in enumerate(selected, start=1):
                    remote_path = base_remote_path.rstrip("\\") + "\\" + entry["name"]
                    local_path = self._available_local_path(destination_dir / entry["name"])
                    self.task_queue.put(
                        ("status", f"Baixando {index} de {len(selected)}: {entry['name']}")
                    )
                    try:
                        with smbclient.open_file(remote_path, mode="rb") as remote:
                            with local_path.open("wb") as local:
                                while True:
                                    chunk = remote.read(1024 * 1024)
                                    if not chunk:
                                        break
                                    local.write(chunk)
                                    downloaded_bytes += len(chunk)
                                    self.task_queue.put(
                                        (
                                            "download_progress",
                                            (
                                                downloaded_bytes,
                                                total_bytes,
                                                index,
                                                len(selected),
                                                entry["name"],
                                            ),
                                        )
                                    )
                        completed += 1
                        self.logger.write(
                            "DOWNLOAD",
                            f"source={remote_path} destination={local_path} "
                            f"size={entry['size']}",
                        )
                    except Exception as error:
                        downloaded_bytes += max(0, int(entry["size"]))
                        failures.append(f"{entry['name']}: {error}")
                        self.logger.write(
                            "DOWNLOAD_FAILED",
                            f"source={remote_path} error={error}",
                        )

                self.logger.write(
                    "DOWNLOAD_BATCH_END",
                    f"requested={len(selected)} completed={completed} failed={len(failures)}",
                )
                self.task_queue.put(
                    (
                        "download_batch_done",
                        (completed, len(failures), failures, destination_dir),
                    )
                )
            except Exception as error:
                self.task_queue.put(("operation_error", ("Falha no download", error)))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _available_local_path(path: Path) -> Path:
        if not path.exists():
            return path
        counter = 1
        while True:
            candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _show_temporary_notice(
        self,
        message: str,
        color: str = COLORS["success"],
        duration_ms: int = 3000,
    ) -> None:
        if not hasattr(self, "toast_label") or not self.toast_label.winfo_exists():
            return
        self.toast_label.configure(text=message, foreground=color)
        self.after(
            duration_ms,
            lambda: (
                self.toast_label.configure(text="")
                if self.toast_label.winfo_exists()
                else None
            ),
        )

    def _finish_download_ui(self) -> None:
        self.download_active = False
        self.download_button.configure(
            state="normal",
            background=COLORS["green"],
        )
        self.download_progress.set(100)
        self.progress_percent.configure(text="100%")
        self.after(
            3000,
            lambda: (
                self.progress_frame.pack_forget()
                if self.progress_frame.winfo_exists()
                else None
            ),
        )

    def logout(self) -> None:
        self.logger.write("LOGOUT", self.username)
        self.connected = False
        self.directory_generation += 1
        self.navigation_generation += 1
        self.username = ""
        self.current_parts.clear()
        self.entries.clear()
        self.selected_item_id = None
        self.selected_item_ids.clear()
        self.selection_anchor_id = None
        self.preview_image = None
        self.thumbnail_images.clear()
        self.thumbnail_labels.clear()
        self.grid_cards.clear()
        smbclient.reset_connection_cache()
        self._clear_temp_files()
        self.logger.clear_session()
        self._build_login_screen()
        if self.config_data:
            self.server_label.configure(
                text=f"Servidor: {self.config_data.display_name} ({self.config_data.server_ip})"
            )

    def _clear_temp_files(self) -> None:
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = Path(tempfile.mkdtemp(prefix="accessview_"))
        except OSError:
            pass

    def close_application(self) -> None:
        if self.connected:
            self.logger.write("APPLICATION_CLOSED", self.username)
        smbclient.reset_connection_cache()
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        finally:
            self.destroy()

    def _process_task_queue(self) -> None:
        try:
            while True:
                event, payload = self.task_queue.get_nowait()

                if event == "login_success":
                    self.username = str(payload)
                    self.password_entry.delete(0, "end")
                    self.connected = True
                    self.logger.set_session(
                        self.username,
                        self.config_data.server_ip if self.config_data else "-",
                    )
                    self.logger.write("LOGIN", self.username)
                    self._build_browser_screen()

                elif event == "login_error":
                    self.logger.clear_session()
                    self.login_button.configure(state="normal")
                    self.login_status.configure(text="")
                    self.password_entry.delete(0, "end")
                    messagebox.showerror(
                        "Falha na conexão",
                        str(payload),
                    )

                elif event == "directory_loaded":
                    rows, generation = payload
                    if generation != self.directory_generation:
                        continue
                    self.tree.delete(*self.tree.get_children())
                    self.entries.clear()
                    self.selected_item_id = None
                    self.selected_item_ids.clear()
                    self.selection_anchor_id = None
                    for index, entry in enumerate(rows):
                        item_id = f"item_{index}"
                        self.entries[item_id] = entry
                        self.tree.insert(
                            "",
                            "end",
                            iid=item_id,
                            values=(
                                entry["name"],
                                (
                                    "Compartilhamento"
                                    if entry.get("is_share")
                                    else "Pasta"
                                    if entry["is_dir"]
                                    else "Arquivo"
                                ),
                                "" if entry["is_dir"] else format_size(entry["size"]),
                                (
                                    ""
                                    if entry["modified"] is None
                                    else entry["modified"].strftime("%d/%m/%Y %H:%M")
                                ),
                            ),
                        )
                    self._sync_current_navigation(rows)
                    self._render_thumbnail_grid()
                    self._start_thumbnail_loading(self.directory_generation)
                    self._update_selection_status()
                    self.logger.write(
                        "LIST_FOLDER",
                        f"path={self.current_path} items={len(rows)}",
                    )
                    self.status_label.configure(
                        text=f"●  Conectado  •  {len(rows)} item(ns)",
                        foreground=COLORS["success"],
                    )

                elif event == "navigation_loaded":
                    node_id, parts, folders, generation = payload
                    if (
                        generation != self.navigation_generation
                        or not self.connected
                        or not self.navigation_tree.winfo_exists()
                    ):
                        continue
                    self._populate_navigation_children(
                        node_id,
                        parts,
                        folders,
                    )

                elif event == "navigation_error":
                    node_id, parts, _error, generation = payload
                    if (
                        generation != self.navigation_generation
                        or not self.connected
                        or not self.navigation_tree.winfo_exists()
                    ):
                        continue
                    self.navigation_loading.discard(parts)
                    if self.navigation_tree.exists(node_id):
                        self._set_navigation_placeholder(
                            node_id,
                            "Não foi possível carregar",
                        )

                elif event == "thumbnail_ready":
                    key, image, generation = payload
                    if generation != self.directory_generation:
                        continue
                    photo = ImageTk.PhotoImage(image)
                    self.thumbnail_images[key] = photo
                    card = self.thumbnail_labels.get(key)
                    if card and card.winfo_exists():
                        card.set_image(photo)

                elif event == "status":
                    self.status_label.configure(text=str(payload))

                elif event == "download_progress":
                    downloaded, total, index, count, name = payload
                    percent = (
                        min(100, int(downloaded * 100 / total))
                        if total > 0
                        else min(99, int(index * 100 / max(1, count)))
                    )
                    self.download_progress.set(percent)
                    self.progress_percent.configure(text=f"{percent}%")
                    self.progress_label.configure(
                        text=f"Baixando {index} de {count}: {name}"
                    )
                    self.status_label.configure(
                        text=f"●  Download em andamento • {format_size(downloaded)}",
                        foreground=COLORS["accent"],
                    )

                elif event == "download_batch_done":
                    completed, failed, failures, destination = payload
                    self._finish_download_ui()
                    self.status_label.configure(
                        text=f"●  Conectado",
                        foreground=COLORS["success"],
                    )
                    if failed:
                        self._show_temporary_notice(
                            f"Download concluído com {failed} falha(s)",
                            color=COLORS["danger"],
                        )
                    else:
                        self._show_temporary_notice("✓  Download concluído")

                elif event == "operation_error":
                    title, error = payload
                    if self.download_active:
                        self.download_active = False
                        self.download_button.configure(
                            state="normal",
                            background=COLORS["green"],
                        )
                        self.progress_frame.pack_forget()
                    self.status_label.configure(text="Operação não concluída")
                    messagebox.showerror(title, str(error))
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_task_queue)


if __name__ == "__main__":
    mimetypes.init()
    application = SecureFileBrowser()
    application.mainloop()
