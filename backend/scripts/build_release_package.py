"""Build a UTF-8 safe release ZIP for direct Alibaba Cloud upload.

The Windows tar/Compress-Archive tools in this environment can encode Chinese
filenames with the active code page.  ``zipfile`` marks non-ASCII names as
UTF-8, so the Ubuntu server can restore the exact frontend and knowledge-base
paths.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[2]
STATIC_EXTENSIONS = {".css", ".js", ".json", ".png", ".ico"}
DATA_EXTENSIONS = {".txt", ".json"}
FORBIDDEN = (
    "competition.db", "official_docs.json", "uploads", "generated", "tmp_export",
    ".env", "uid_secret", "admin_users", "quota", "chroma_db", "训练库",
)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def build_manifest() -> list[str]:
    files: set[str] = {
        "TEAM_RUN_GUIDE.md",
        "frontend/index.html",
        "frontend/科创赛事助手.ico",
        "backend/requirements.txt",
        "backend/Procfile",
        "backend/Dockerfile",
        "backend/scripts/safe_restart.sh",
        "backend/scripts/deploy_safe.sh",
    }
    static_dir = ROOT / "frontend/static"
    files.update(
        rel(p) for p in static_dir.iterdir()
        if p.is_file() and p.suffix.lower() in STATIC_EXTENSIONS and not p.name.startswith("tmp_")
    )
    files.update(rel(p) for p in (ROOT / "backend").glob("*.py"))
    data_dir = ROOT / "backend/data"
    files.update(
        rel(p) for p in data_dir.iterdir()
        if p.is_file() and p.suffix.lower() in DATA_EXTENSIONS
        and p.name not in {"official_docs.json", "vulns.json"}
    )
    kb_dir = ROOT / "backend/knowledge_base"
    files.update(rel(p) for p in kb_dir.iterdir() if p.is_file() and p.suffix.lower() in DATA_EXTENSIONS)
    manifest = sorted(files)
    missing = [p for p in manifest if not (ROOT / p).is_file()]
    if missing:
        raise FileNotFoundError("发布文件不存在: " + ", ".join(missing))
    forbidden = [p for p in manifest if any(token in p for token in FORBIDDEN) or "/tmp_" in p]
    if forbidden:
        raise RuntimeError("发布清单包含禁止文件: " + ", ".join(forbidden))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="", help="输出 ZIP 路径")
    args = parser.parse_args()
    output = Path(args.output) if args.output else (
        ROOT / "artifacts/releases" / f"competition-agent-release-{datetime.now():%Y%m%d_%H%M%S}.zip"
    )
    output = output if output.is_absolute() else ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest()
    manifest_path = output.with_suffix(".manifest.txt")
    manifest_path.write_text("\n".join(manifest) + "\n", encoding="utf-8")
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for item in manifest:
            archive.write(ROOT / item, arcname=item)
    digest = hashlib.sha256(output.read_bytes()).hexdigest().upper()
    print(f"发布文件数: {len(manifest)}")
    print(f"发布包: {output}")
    print(f"清单: {manifest_path}")
    print(f"SHA256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
