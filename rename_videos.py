#!/usr/bin/env python3
"""Number videos independently in output/ and input/rejected/ for upload order."""
from pathlib import Path
import uuid

PROJECT_ROOT = Path(__file__).resolve().parent
VIDEO_DIR = PROJECT_ROOT / "video-processing"
FOLDERS = [VIDEO_DIR / "output", VIDEO_DIR / "input" / "rejected"]
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def rename_videos(folder: Path) -> None:
    if not folder.exists():
        print(f"\n{folder.name}: Folder does not exist; skipping.")
        return

    files = sorted(
        (path for path in folder.iterdir()
         if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS),
        key=lambda path: path.name.casefold(),
    )
    if not files:
        print(f"\n{folder.name}: No videos found.")
        return

    operations = [(old, folder / f"{index}{old.suffix.lower()}")
                  for index, old in enumerate(files, start=1)]

    print(f"\n=== {folder.relative_to(PROJECT_ROOT)} ===")
    for old, new in operations:
        print(f"  {old.name}  ->  {new.name}")

    # Allow destinations that are themselves in the rename set; all source
    # files are first moved aside to unique temporary names to avoid collisions.
    source_set = set(files)
    for old, new in operations:
        if new.exists() and new not in source_set:
            print(f"\nERROR: Destination already exists and is not part of this rename: {new.name}")
            return

    answer = input(f"\nRename {len(files)} videos in {folder.name}? Type YES to confirm: ")
    if answer.strip() != "YES":
        print("Skipped; no filenames were changed.")
        return

    temporary: dict[Path, tuple[Path, Path]] = {}
    try:
        for old, new in operations:
            temp = folder / f".mity_tmp_{uuid.uuid4().hex}{old.suffix}"
            old.rename(temp)
            temporary[old] = (temp, new)
    except OSError as error:
        print(f"ERROR during temporary rename: {error}")
        for old, (temp, _) in temporary.items():
            if temp.exists():
                temp.rename(old)
        return

    completed: list[tuple[Path, Path]] = []
    try:
        for old, (temp, new) in temporary.items():
            temp.rename(new)
            completed.append((old, new))
    except OSError as error:
        print(f"ERROR during final rename: {error}. Attempting rollback.")
        for old, new in reversed(completed):
            if new.exists():
                new.rename(temporary[old][0])
        for old, (temp, _) in temporary.items():
            if temp.exists():
                temp.rename(old)
        return

    print(f"SUCCESS: Renamed {len(files)} videos in {folder.name}.")


if __name__ == "__main__":
    print("MITY CLIPPING STUDIO — UPLOAD RENAME")
    print("Files are sorted by current filename and numbered separately in each folder.")
    for video_folder in FOLDERS:
        rename_videos(video_folder)
    print("\nRename operation finished.")
