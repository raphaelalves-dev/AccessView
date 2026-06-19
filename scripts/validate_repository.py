from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_FILES = {
    "config.json",
    "BUILD-RELEASE.log",
}
FORBIDDEN_PATTERNS = {
    "senha fixa no instalador": re.compile(
        r'#define\s+InstallerPassword\s+"[^"]+"',
        flags=re.IGNORECASE,
    ),
    "caminho absoluto de usuário Windows": re.compile(
        r"[A-Z]:\\Users\\[^\\]+\\",
        flags=re.IGNORECASE,
    ),
}


def main() -> None:
    failures: list[str] = []

    for relative_name in FORBIDDEN_FILES:
        if (ROOT / relative_name).exists():
            failures.append(f"arquivo sensível presente: {relative_name}")

    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ".git" in path.parts
            or path.resolve() == Path(__file__).resolve()
            or path.suffix.lower() in {".png", ".ico", ".exe", ".zip"}
        ):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in FORBIDDEN_PATTERNS.items():
            if pattern.search(content):
                failures.append(
                    f"{label} em {path.relative_to(ROOT)}"
                )

    if failures:
        raise SystemExit("\n".join(failures))
    print("Repository validation passed.")


if __name__ == "__main__":
    main()
