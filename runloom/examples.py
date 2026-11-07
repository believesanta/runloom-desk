"""Bundled local automations. Run with ``python -m runloom.examples --help``.

All actions copy into a separate destination. Preview performs no writes. Links
and Windows junctions are skipped; this is a safety convention, not a sandbox.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import fnmatch
import json
import os
from pathlib import Path
import shutil
import sys


def emit(kind: str, **fields):
    print(json.dumps({"runloom": 1, "type": kind, **fields}), flush=True)


def linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def reject_links(path: Path):
    for part in (path, *path.parents):
        if linked(part):
            raise ValueError(f"Symbolic links and junctions are not allowed in output paths: {part}")


def paths(source: str, destination: str):
    raw_source = Path(source).expanduser().absolute()
    raw_dest = Path(destination).expanduser().absolute()
    if linked(raw_source):
        raise ValueError("Source must be a real folder, not a symbolic link or junction")
    reject_links(raw_dest)
    src, dst = raw_source.resolve(), raw_dest.resolve()
    if not src.is_dir():
        raise ValueError(f"Source folder does not exist: {src}")
    if src == dst or src in dst.parents or dst in src.parents:
        raise ValueError("Source and destination must be separate, non-overlapping folders")
    if dst.exists() and not dst.is_dir():
        raise ValueError(f"Destination is not a folder: {dst}")
    return src, dst


def scan(source: Path, patterns=()):
    """Walk regular files without traversing links; patterns match path or name."""
    found, skipped = [], []
    def excluded(path):
        rel = path.relative_to(source).as_posix()
        return any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern)
                   for pattern in patterns)
    def on_error(error):
        raise error
    for current, dirs, files in os.walk(source, followlinks=False, onerror=on_error):
        base = Path(current)
        for name in sorted(dirs.copy()):
            path = base / name
            if linked(path) or excluded(path):
                dirs.remove(name)
                skipped.append(str(path.relative_to(source)))
        dirs.sort()
        for name in sorted(files):
            path = base / name
            if linked(path) or excluded(path) or not path.is_file():
                skipped.append(str(path.relative_to(source)))
            else:
                found.append(path)
    return found, skipped


def unique_open(path: Path):
    """Exclusive file creation also prevents accidental overwrite between runs."""
    reject_links(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    index = 0
    while True:
        candidate = path if index == 0 else path.with_name(f"{path.stem} ({index}){path.suffix}")
        try:
            return candidate, candidate.open("xb")
        except FileExistsError:
            index += 1


def copy_file(source: Path, target: Path):
    if linked(source):
        raise ValueError(f"Source changed into a link: {source}")
    target, handle = unique_open(target)
    try:
        with handle, source.open("rb") as reader:
            shutil.copyfileobj(reader, handle)
        shutil.copystat(source, target, follow_symlinks=False)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def report(destination: Path, action: str, source: Path, records: list, skipped: list):
    path, handle = unique_open(destination / f"{action}-report.json")
    payload = {"action": action, "source": str(source), "created": datetime.now().isoformat(),
               "copied": len(records), "files": records, "skipped": skipped,
               "restore": "Copy the selected file from its recorded destination to a new folder. Originals remain in place."}
    with handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))
    emit("artifact", path=str(path))
    print(f"Completed: {len(records)} files; {len(skipped)} skipped.", flush=True)


def group_type(path: Path):
    suffix = path.suffix.lower()
    for group, extensions in {
        "images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"},
        "documents": {".txt", ".md", ".pdf", ".doc", ".docx", ".csv", ".xlsx", ".json"},
        "audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"},
        "video": {".mp4", ".mkv", ".mov", ".webm"},
        "archives": {".zip", ".7z", ".tar", ".gz", ".rar"},
    }.items():
        if suffix in extensions:
            return group
    return "other"


def organizer(args):
    source, destination = paths(args.source, args.destination)
    files, skipped = scan(source)
    records = []
    for index, path in enumerate(files, 1):
        group = group_type(path) if args.group == "type" else datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m")
        target = destination / group / path.name
        print(f"{'Would copy' if args.preview else 'Copy'} {path.relative_to(source)} -> {target}", flush=True)
        if not args.preview:
            target = copy_file(path, target)
            records.append({"source": str(path), "destination": str(target)})
        emit("progress", value=round(index / len(files) * 100))
    emit("progress", value=100)
    if not args.preview:
        report(destination, "organizer", source, records, skipped)
        emit("artifact", path=str(destination))


def images(args):
    from PIL import Image, ImageOps, UnidentifiedImageError
    source, destination = paths(args.source, args.destination)
    if not 1 <= args.width <= 12000 or not 1 <= args.height <= 12000:
        raise ValueError("Width and height must be between 1 and 12000 pixels")
    files, skipped = scan(source)
    records = []
    supported = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    for index, path in enumerate(files, 1):
        try:
            if path.suffix.lower() not in supported:
                raise ValueError("unsupported image extension")
            try:
                with Image.open(path) as original:
                    picture = ImageOps.exif_transpose(original)
                    picture.thumbnail((args.width, args.height), Image.Resampling.LANCZOS)
                    if args.format == "jpeg":
                        rgba = picture.convert("RGBA")
                        picture = Image.new("RGB", rgba.size, "white")
                        picture.paste(rgba, mask=rgba.getchannel("A"))
                    elif picture.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                        picture = picture.convert("RGBA")
            except OSError as error:
                raise ValueError(f"unreadable image: {error}") from error
            extension = ".jpg" if args.format == "jpeg" else ".png"
            target = destination / (path.stem + extension)
            print(f"{'Would resize' if args.preview else 'Resize'} {path.name} -> {picture.width}x{picture.height} {args.format}", flush=True)
            if not args.preview:
                target, handle = unique_open(target)
                try:
                    with handle:
                        picture.save(handle, format=args.format.upper())
                except BaseException:
                    target.unlink(missing_ok=True)
                    raise
                records.append({"source": str(path), "destination": str(target), "width": picture.width, "height": picture.height})
                emit("artifact", path=str(target))
        except (UnidentifiedImageError, ValueError, Image.DecompressionBombError) as error:
            skipped.append(str(path.relative_to(source)))
            print(f"Skipped {path.name}: {error}", flush=True)
        emit("progress", value=round(index / len(files) * 100))
    emit("progress", value=100)
    if not args.preview:
        report(destination, "images", source, records, skipped)


def snapshot(args):
    source, destination = paths(args.source, args.destination)
    patterns = [item.strip() for item in args.exclude.split(",") if item.strip()]
    files, skipped = scan(source, patterns)
    stamp = datetime.now().strftime("snapshot-%Y%m%d-%H%M%S-%f")
    folder = destination / stamp
    if not args.preview:
        destination.mkdir(parents=True, exist_ok=True)
        folder.mkdir()  # Refuse a collision; never reuse an existing snapshot.
    records = []
    for index, path in enumerate(files, 1):
        target = folder / "files" / path.relative_to(source)
        print(f"{'Would snapshot' if args.preview else 'Snapshot'} {path.relative_to(source)}", flush=True)
        if not args.preview:
            target = copy_file(path, target)
            records.append({"source": str(path), "destination": str(target), "relative": path.relative_to(source).as_posix()})
        emit("progress", value=round(index / len(files) * 100))
    emit("progress", value=100)
    if not args.preview:
        report(folder, "snapshot", source, records, skipped)
        emit("artifact", path=str(folder))


def seed_demo(root: Path, data_dir: Path) -> Path:
    source = data_dir / "demo-input"
    source.mkdir(parents=True, exist_ok=True)
    fixtures = root / "examples" / "fixtures"
    if fixtures.is_dir():
        for path in fixtures.iterdir():
            target = source / path.name
            if path.is_file() and not target.exists():
                shutil.copy2(path, target)
    image_path = source / "sample-landscape.png"
    if not image_path.exists():
        from PIL import Image, ImageDraw
        picture = Image.new("RGB", (1200, 800), "#d9ece7")
        draw = ImageDraw.Draw(picture)
        draw.ellipse((780, 80, 1020, 320), fill="#f4bd65")
        draw.polygon([(0, 800), (450, 250), (900, 800)], fill="#31574b")
        draw.polygon([(500, 800), (950, 360), (1200, 640), (1200, 800)], fill="#6c9384")
        picture.save(image_path)
    return source.resolve()


def builtins(root: Path, data_dir: Path) -> list[dict]:
    root, data_dir = Path(root).resolve(), Path(data_dir).resolve()
    source = seed_demo(root, data_dir)
    definitions = [
        ("organizer", "Folder organizer", "Copy files into type or modified-month folders. Originals stay in place.", "Files",
         [{"id": "group", "label": "Group by", "type": "select", "default": "type", "options": ["type", "month"], "required": True}]),
        ("images", "Batch image resizer", "Resize images to fit a bounding box and convert to PNG or JPEG. Originals stay in place.", "Images",
         [{"id": "width", "label": "Maximum width (px)", "type": "number", "default": 1200, "min": 1, "max": 12000, "required": True},
          {"id": "height", "label": "Maximum height (px)", "type": "number", "default": 800, "min": 1, "max": 12000, "required": True},
          {"id": "format", "label": "Output format", "type": "select", "default": "png", "options": ["png", "jpeg"], "required": True}]),
        ("snapshot", "Versioned folder snapshot", "Copy a folder into a timestamped snapshot with exclusions and a restore report.", "Backups",
         [{"id": "exclude", "label": "Exclude patterns (comma separated)", "type": "string", "default": "*.tmp,__pycache__,.git", "required": False}]),
    ]
    manifests = []
    for action, name, description, category, extra in definitions:
        parameters = [
            {"id": "source", "label": "Source folder", "type": "folder", "default": str(source), "required": True},
            {"id": "destination", "label": "Destination folder", "type": "folder", "default": str(data_dir / "demo-output" / action), "required": True},
            *extra,
        ]
        frozen = getattr(sys, 'frozen', False)
        executable = str(Path(sys.executable).resolve().parent / 'RunloomWorker.exe') if frozen else '{python}'
        arguments = [action] if frozen else ["-m", "runloom.examples", action]
        for param in parameters:
            arguments.extend(["--" + param["id"], "{" + param["id"] + "}"])
        manifests.append({"schema_version": 1, "id": "builtin-" + action, "name": name, "description": description,
                          "category": category, "executable": executable, "args": arguments, "cwd": str(root),
                          "parameters": parameters, "timeout": 120, "allow_parallel": False, "preview": True})
    return manifests


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="action", required=True)
    for action in ("organizer", "images", "snapshot"):
        child = subcommands.add_parser(action)
        child.add_argument("--source", required=True)
        child.add_argument("--destination", required=True)
        child.add_argument("--preview", action="store_true")
        if action == "organizer":
            child.add_argument("--group", choices=("type", "month"), default="type")
        elif action == "images":
            child.add_argument("--width", type=int, default=1200)
            child.add_argument("--height", type=int, default=800)
            child.add_argument("--format", choices=("png", "jpeg"), default="png")
        else:
            child.add_argument("--exclude", default="*.tmp,__pycache__,.git")
    args = parser.parse_args(argv)
    try:
        if args.preview:
            print("Preview: destination files will not be written.", flush=True)
        {"organizer": organizer, "images": images, "snapshot": snapshot}[args.action](args)
        return 0
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
