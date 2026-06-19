from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import messagebox, ttk


APP_NAME = "AccessView"
MANIFEST_FILE = "update.json"
PAYLOAD_PREFIX = "payload/"
PROTECTED_FILES = {"config.json"}
PROGRAM_DATA = Path(os.environ.get("PROGRAMDATA", tempfile.gettempdir()))
UPDATE_DATA_DIR = PROGRAM_DATA / APP_NAME / "updates"
BACKUP_DIR = UPDATE_DATA_DIR / "backups"
LOG_FILE = UPDATE_DATA_DIR / "updater.log"
STATE_FILE = UPDATE_DATA_DIR / "state.json"


def write_log(message: str) -> None:
    try:
        UPDATE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as file:
            file.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\t{message}\n")
    except OSError:
        pass


def load_update_state() -> dict:
    if not STATE_FILE.is_file():
        return {}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save_update_state(
    installed_version: str,
    previous_version: str,
    package_sha256: str,
    package_name: str,
    backup_path: Path,
) -> None:
    state = load_update_state()
    installed_hashes = [
        str(value)
        for value in state.get("installed_package_sha256", [])
        if str(value).strip()
    ]
    if package_sha256.casefold() not in {
        value.casefold() for value in installed_hashes
    }:
        installed_hashes.append(package_sha256)
    installed_hashes = installed_hashes[-50:]

    history = state.get("history", [])
    if not isinstance(history, list):
        history = []
    updated_at = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    history.append(
        {
            "version": installed_version,
            "previous_version": previous_version,
            "updated_at": updated_at,
            "package": package_name,
            "package_sha256": package_sha256,
            "backup": str(backup_path),
        }
    )
    history = history[-50:]

    new_state = {
        "installed_version": installed_version,
        "previous_version": previous_version,
        "updated_at": updated_at,
        "last_package": package_name,
        "last_package_sha256": package_sha256,
        "installed_package_sha256": installed_hashes,
        "history": history,
    }
    UPDATE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(new_state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, STATE_FILE)


def safe_relative_path(value: str) -> Path:
    normalized = str(value).replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or pure.is_absolute()
        or ".." in pure.parts
        or (pure.parts and ":" in pure.parts[0])
    ):
        raise ValueError(f"Caminho inseguro no pacote: {value}")
    if normalized.casefold() in PROTECTED_FILES:
        raise ValueError(f"O pacote tentou substituir {normalized}.")
    return Path(*pure.parts)


def load_and_validate_package(package_path: Path) -> tuple[dict, dict[str, str]]:
    with zipfile.ZipFile(package_path, "r") as archive:
        if MANIFEST_FILE not in archive.namelist():
            raise ValueError("O pacote não contém update.json.")
        manifest = json.loads(archive.read(MANIFEST_FILE).decode("utf-8-sig"))
        if manifest.get("app") != APP_NAME:
            raise ValueError("O pacote não pertence ao AccessView.")

        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            raise ValueError("O manifesto não contém arquivos.")

        archive_names = {
            name.replace("\\", "/").lstrip("/"): name
            for name in archive.namelist()
            if not name.endswith("/")
        }
        validated: dict[str, str] = {}
        for relative_name, expected_hash in files.items():
            relative = safe_relative_path(relative_name)
            normalized = relative.as_posix()
            archive_name = PAYLOAD_PREFIX + normalized
            stored_name = archive_names.get(archive_name)
            if not stored_name:
                raise ValueError(f"Arquivo ausente no pacote: {normalized}")
            digest = hashlib.sha256(archive.read(stored_name)).hexdigest()
            if digest.casefold() != str(expected_hash).casefold():
                raise ValueError(f"Integridade inválida: {normalized}")
            validated[normalized] = stored_name

        if "AccessView.exe" not in validated:
            raise ValueError("O pacote não contém AccessView.exe.")
        return manifest, validated


def wait_for_process(process_id: int, timeout_seconds: int = 60) -> None:
    if process_id <= 0:
        return
    write_log(f"Aguardando encerramento do processo pid={process_id}")

    if sys.platform == "win32":
        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(
            synchronize,
            False,
            process_id,
        )
        if handle:
            try:
                result = ctypes.windll.kernel32.WaitForSingleObject(
                    handle,
                    timeout_seconds * 1000,
                )
                if result == 0x00000102:
                    raise TimeoutError(
                        "O AccessView não encerrou dentro do tempo esperado."
                    )
                return
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(process_id, 0)
        except OSError:
            return
        time.sleep(0.25)
    raise TimeoutError("O AccessView não encerrou dentro do tempo esperado.")


def extract_payload(
    package_path: Path,
    files: dict[str, str],
    destination: Path,
) -> None:
    with zipfile.ZipFile(package_path, "r") as archive:
        for relative_name, archive_name in files.items():
            target = destination / safe_relative_path(relative_name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(archive_name, "r") as source:
                with target.open("wb") as output:
                    shutil.copyfileobj(source, output)


def create_backup(
    install_dir: Path,
    files: dict[str, str],
    version: str,
) -> tuple[Path, set[str]]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"before-{version}-{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=True)
    existing_files: set[str] = set()

    for relative_name in files:
        relative = safe_relative_path(relative_name)
        source = install_dir / relative
        if source.is_file():
            existing_files.add(relative.as_posix())
            destination = backup_path / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    metadata = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "install_dir": str(install_dir),
        "files": sorted(existing_files),
    }
    (backup_path / "backup.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return backup_path, existing_files


def install_payload(
    extracted_payload: Path,
    install_dir: Path,
    files: dict[str, str],
) -> None:
    for relative_name in files:
        relative = safe_relative_path(relative_name)
        source = extracted_payload / relative
        destination = install_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".update-new")
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)


def rollback(
    install_dir: Path,
    backup_path: Path,
    files: dict[str, str],
    previously_existing: set[str],
) -> None:
    write_log("Iniciando rollback")
    for relative_name in files:
        relative = safe_relative_path(relative_name)
        destination = install_dir / relative
        backup_file = backup_path / relative
        if relative.as_posix() in previously_existing and backup_file.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, destination)
        elif destination.exists():
            try:
                destination.unlink()
            except OSError:
                pass
    write_log("Rollback concluído")


def prune_old_backups(keep: int = 3) -> None:
    try:
        backups = sorted(
            (path for path in BACKUP_DIR.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[keep:]:
            shutil.rmtree(old_backup, ignore_errors=True)
    except OSError:
        pass


class UpdaterWindow(tk.Tk):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__()
        self.args = args
        self.title("AccessView — Atualização")
        self.geometry("500x230")
        self.resizable(False, False)
        self.configure(background="#1c1f22")
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = tk.Frame(self, background="#1c1f22", padx=28, pady=24)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text="Atualizando o AccessView",
            font=("Segoe UI Semibold", 17),
            foreground="#f3f4f5",
            background="#1c1f22",
        ).pack(anchor="w")
        self.status = tk.Label(
            frame,
            text="Preparando atualização...",
            font=("Segoe UI", 10),
            foreground="#b9bec3",
            background="#1c1f22",
            anchor="w",
        )
        self.status.pack(fill="x", pady=(12, 18))

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Update.Horizontal.TProgressbar",
            troughcolor="#2b3035",
            background="#2878c8",
            bordercolor="#2b3035",
            lightcolor="#2878c8",
            darkcolor="#2878c8",
        )
        self.progress = ttk.Progressbar(
            frame,
            mode="indeterminate",
            style="Update.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x")
        self.progress.start(12)
        self.after(250, self.run_update)

    def set_status(self, text: str) -> None:
        self.status.configure(text=text)
        self.update_idletasks()

    def run_update(self) -> None:
        package_path = Path(self.args.package).resolve()
        install_dir = Path(self.args.install_dir).resolve()
        backup_path: Path | None = None
        existing_files: set[str] = set()
        files: dict[str, str] = {}
        try:
            write_log(
                f"UPDATE_START target={self.args.target_version} "
                f"package={package_path} install_dir={install_dir}"
            )
            self.set_status("Validando o pacote...")
            manifest, files = load_and_validate_package(package_path)
            if str(manifest.get("version")) != self.args.target_version:
                raise ValueError("A versão informada não corresponde ao pacote.")

            self.set_status("Aguardando o AccessView encerrar...")
            wait_for_process(self.args.pid)

            with tempfile.TemporaryDirectory(
                prefix="accessview_payload_"
            ) as temporary_dir:
                payload_dir = Path(temporary_dir)
                self.set_status("Extraindo os novos arquivos...")
                extract_payload(package_path, files, payload_dir)

                self.set_status("Criando cópia de segurança...")
                backup_path, existing_files = create_backup(
                    install_dir,
                    files,
                    self.args.target_version,
                )

                self.set_status("Instalando a nova versão...")
                install_payload(payload_dir, install_dir, files)

            prune_old_backups()
            save_update_state(
                self.args.target_version,
                self.args.previous_version,
                self.args.package_sha256,
                package_path.name,
                backup_path,
            )
            write_log(
                f"UPDATE_SUCCESS version={self.args.target_version} "
                f"backup={backup_path}"
            )
            self.progress.stop()
            self.set_status(
                f"Atualização {self.args.target_version} concluída com sucesso."
            )
            self.update()
            time.sleep(1)
            app_path = install_dir / self.args.app_exe
            subprocess.Popen([str(app_path)], cwd=install_dir)
            self.destroy()
        except Exception as error:
            write_log(f"UPDATE_ERROR error={error}")
            if backup_path is not None:
                try:
                    rollback(install_dir, backup_path, files, existing_files)
                except Exception as rollback_error:
                    write_log(f"ROLLBACK_ERROR error={rollback_error}")
            self.progress.stop()
            messagebox.showerror(
                "Falha na atualização",
                (
                    f"Não foi possível atualizar o AccessView.\n\n{error}\n\n"
                    f"Consulte o log em:\n{LOG_FILE}"
                ),
                parent=self,
            )
            app_path = install_dir / self.args.app_exe
            if app_path.is_file():
                try:
                    subprocess.Popen([str(app_path)], cwd=install_dir)
                except OSError:
                    pass
            self.destroy()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--app-exe", default="AccessView.exe")
    parser.add_argument("--target-version", required=True)
    parser.add_argument("--previous-version", required=True)
    parser.add_argument("--package-sha256", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()
    application = UpdaterWindow(arguments)
    application.mainloop()
