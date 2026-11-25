"""Build one production.zip from the current repository."""
from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = REPOSITORY_ROOT / "app"
DATA_SOURCE = REPOSITORY_ROOT / "data"
INSTALLER_SOURCE = REPOSITORY_ROOT / "PackageInstaller"
OUTPUT_ZIP = REPOSITORY_ROOT / "production.zip"
ARCHIVE_ROOT = PurePosixPath("production")

CATALOG_FILES = [
    "horiba_device_catalog.xlsx",
    "piysan_lab_test_catalog.xlsx",
    "new stag test ids.xlsx",
    "SK CBC and ESR test id list.xlsx",
]
INSTALLER_FILES = [
    "install.ps1",
    "manage_service.ps1",
    "uninstall.ps1",
    "INSTALL.txt",
    "README.md",
    ".env.example",
]
ROOT_FILES = [
    "requirements.txt",
    "service_installer.py",
]
DOCUMENT_FILES = [
    "INSTALLATION_AND_TESTING_GUIDE.md",
    "HORIBA_Yumizen_H500_LIS_Installation_Guide.docx",
]


def _add_file(archive: zipfile.ZipFile, source: Path, archive_path: PurePosixPath) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Required production input is missing: {source}")
    archive.write(source, archive_path.as_posix())


def _add_app_tree(archive: zipfile.ZipFile) -> None:
    if not APP_SOURCE.is_dir():
        raise FileNotFoundError(f"Application source folder is missing: {APP_SOURCE}")

    for source in sorted(APP_SOURCE.rglob("*")):
        if not source.is_file():
            continue
        if "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        relative_path = PurePosixPath(*source.relative_to(APP_SOURCE).parts)
        _add_file(archive, source, ARCHIVE_ROOT / "app" / relative_path)


def _add_optional_files(
    archive: zipfile.ZipFile,
    source_folder: Path,
    filenames: list[str],
    archive_folder: PurePosixPath,
) -> None:
    for filename in filenames:
        source = source_folder / filename
        if source.is_file():
            _add_file(archive, source, archive_folder / filename)
        else:
            print(f"Skipping optional production input that is missing: {source}")


def _add_files(
    archive: zipfile.ZipFile,
    source_folder: Path,
    filenames: list[str],
    archive_folder: PurePosixPath,
) -> None:
    for filename in filenames:
        _add_file(
            archive,
            source_folder / filename,
            archive_folder / filename,
        )


def build_production_zip() -> None:
    with tempfile.NamedTemporaryFile(
        prefix=".production-",
        suffix=".tmp",
        dir=REPOSITORY_ROOT,
        delete=False,
    ) as temporary_file:
        temporary_zip = Path(temporary_file.name)

    try:
        with zipfile.ZipFile(temporary_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("production/artifacts/", "")
            archive.writestr("production/data/", "")
            _add_app_tree(archive)
            _add_optional_files(
                archive,
                DATA_SOURCE,
                CATALOG_FILES,
                ARCHIVE_ROOT / "data",
            )
            _add_files(
                archive,
                INSTALLER_SOURCE,
                INSTALLER_FILES,
                ARCHIVE_ROOT,
            )
            _add_files(
                archive,
                REPOSITORY_ROOT,
                ROOT_FILES,
                ARCHIVE_ROOT,
            )
            _add_optional_files(
                archive,
                REPOSITORY_ROOT,
                DOCUMENT_FILES,
                ARCHIVE_ROOT,
            )

        os.replace(temporary_zip, OUTPUT_ZIP)
    finally:
        if temporary_zip.exists():
            temporary_zip.unlink()

    print(f"Created {OUTPUT_ZIP} ({OUTPUT_ZIP.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build_production_zip()
