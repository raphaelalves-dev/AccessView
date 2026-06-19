from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


APP_NAME = "AccessView"
EXCLUDED_NAMES = {
    "config.json",
    "BUILD-RELEASE.log",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_app_version(app_source: Path) -> str:
    match = re.search(
        r'^APP_VERSION\s*=\s*"([^"]+)"',
        app_source.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if not match:
        raise ValueError("Não foi possível identificar APP_VERSION no app.py.")
    return match.group(1)


def create_package(
    source_dir: Path,
    output_dir: Path,
    version: str,
    minimum_version: str,
    version_subdir: bool = False,
    overwrite: bool = False,
) -> Path:
    if not (source_dir / "AccessView.exe").is_file():
        raise FileNotFoundError(
            f"AccessView.exe não foi encontrado em {source_dir}"
        )
    if not (source_dir / "AccessViewUpdater.exe").is_file():
        raise FileNotFoundError(
            f"AccessViewUpdater.exe não foi encontrado em {source_dir}"
        )

    files = sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.name not in EXCLUDED_NAMES
    )
    checksums = {
        path.relative_to(source_dir).as_posix(): sha256_file(path)
        for path in files
    }
    manifest = {
        "schema": 1,
        "app": APP_NAME,
        "version": version,
        "minimum_version": minimum_version,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": checksums,
    }

    release_dir = output_dir / f"v{version}" if version_subdir else output_dir
    release_dir.mkdir(parents=True, exist_ok=True)
    package_path = release_dir / f"AccessView-Update-v{version}.zip"
    if package_path.exists():
        if not overwrite:
            raise FileExistsError(
                f"A atualização v{version} já foi gerada:\n{package_path}\n\n"
                "Altere APP_VERSION antes de gerar uma nova atualização."
            )
        package_path.unlink()

    with zipfile.ZipFile(
        package_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        archive.writestr(
            "update.json",
            json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
        )
        for path in files:
            relative_name = path.relative_to(source_dir).as_posix()
            archive.write(path, f"payload/{relative_name}")

    catalog = {
        "app": APP_NAME,
        "latest_version": version,
        "package": str(package_path.relative_to(output_dir)).replace("\\", "/"),
        "sha256": sha256_file(package_path),
        "created_at": manifest["created_at"],
    }
    (output_dir / "ULTIMA-VERSAO.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "ULTIMA-VERSAO.txt").write_text(
        (
            f"AccessView {version}\n"
            f"Pacote: {catalog['package']}\n"
            f"SHA-256: {catalog['sha256']}\n"
        ),
        encoding="utf-8",
    )
    return package_path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="dist/AccessView")
    parser.add_argument("--output", default="output")
    parser.add_argument("--app-source", default="app.py")
    parser.add_argument("--minimum-version", default="0.10.0")
    parser.add_argument("--version-subdir", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    app_source = Path(args.app_source).resolve()
    version = read_app_version(app_source)
    result = create_package(
        Path(args.source).resolve(),
        Path(args.output).resolve(),
        version,
        args.minimum_version,
        args.version_subdir,
        args.overwrite,
    )
    print(result)
