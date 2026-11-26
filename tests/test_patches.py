import os
import pathlib
import shutil
import subprocess
import tempfile
import urllib.request

import pytest

import repo

URL = "https://github.com/NVIDIA/open-gpu-kernel-modules/archive/refs/tags/%s.tar.gz"
CACHE = pathlib.Path(os.environ.get("CMPUNLOCKER_BUILD_DIR", repo.ROOT / "driver" / ".build"))
PATCHES = repo.ROOT / "driver" / "patches"
ORDER = repo.patch_order()
COMPAT = repo.compat_patches()
VERSIONS = repo.versions()
assert VERSIONS, "driver/VERSION lists no versions"


def tarball(version):
    path = CACHE / ("open-gpu-kernel-modules-%s.tar.gz" % version)
    if not path.is_file():
        CACHE.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        with urllib.request.urlopen(URL % version, timeout=60) as resp, open(partial, "wb") as out:
            shutil.copyfileobj(resp, out)
        partial.replace(path)
    return path


def test_patch_order_covers_patch_dir():
    assert set(ORDER).isdisjoint(COMPAT)
    assert sorted(ORDER + COMPAT) == sorted(p.name for p in PATCHES.glob("*.patch"))


@pytest.mark.parametrize("version", VERSIONS)
def test_patches_apply(version):
    assert shutil.which("patch"), "GNU patch is not installed"
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["tar", "-xzf", str(tarball(version)), "-C", tmp], check=True)
        src = pathlib.Path(tmp, "open-gpu-kernel-modules-" + version)
        assert src.is_dir(), os.listdir(tmp)
        for name in ORDER:
            r = subprocess.run(["patch", "-p1", "-i", str(PATCHES / name)], cwd=src,
                               stdin=subprocess.DEVNULL, capture_output=True, text=True)
            assert r.returncode == 0, "%s on %s:\n%s%s" % (name, version, r.stdout, r.stderr)
        nv_linux = src / "kernel-open" / "common" / "inc" / "nv-linux.h"
        nv_linux_text = nv_linux.read_text() if nv_linux.is_file() else ""
        needs_cxl = (
            "NV_CXL_CXL_H_PRESENT" in nv_linux_text
            and "NV_CXL_STRUCTS_PRESENT" not in nv_linux_text
        )
        if needs_cxl:
            r = subprocess.run(["patch", "-p1", "-i", str(PATCHES / "cxl-structs.patch")], cwd=src,
                               stdin=subprocess.DEVNULL, capture_output=True, text=True)
            assert r.returncode == 0, "cxl-structs.patch on %s:\n%s%s" % (version, r.stdout, r.stderr)
            assert "NV_CXL_STRUCTS_PRESENT" in nv_linux.read_text()
            assert "NV_CXL_CXL_H_PRESENT" not in nv_linux.read_text()
            assert "cxl_structs_present" in (src / "kernel-open" / "conftest.sh").read_text()
            assert "cxl_structs_present" in (src / "kernel-open" / "nvidia" / "nvidia.Kbuild").read_text()
