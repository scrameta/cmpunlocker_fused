import re
import subprocess
import sys

import pytest

import repo


def _python_with_yaml():
    for exe in (sys.executable, "/usr/bin/python3"):
        r = subprocess.run([exe, "-c", "import yaml"], capture_output=True)
        if r.returncode == 0:
            return exe
    return None


@pytest.mark.parametrize("profile", ["8gb", "10gb", "mixed"])
def test_read_constants_profiles(profile):
    py = _python_with_yaml()
    if py is None:
        pytest.skip("PyYAML not installed")
    r = subprocess.run(
        [
            py,
            str(repo.ROOT / "tools" / "read-constants.py"),
            str(repo.ROOT / "common" / "constants.yaml"),
            str(repo.ROOT / "driver" / "patches"),
            str(repo.ROOT / "driver" / "build.sh"),
            profile,
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_swiff_patch_has_no_otp_cmd_write():
    text = (repo.ROOT / "driver" / "patches" / "cmp-fused-probe.patch").read_text()
    # Must only issue CMD_READ (1U) to FUSECTRL and use volatile IFF_SW_FUSING (0x820088) for SRAM writes.
    assert "CMP_FUSE_IFF_SW_FUSING" in text
    assert not re.search(r"writel\s*\(\s*2U?\s*,\s*[^)]*FUSECTRL", text)
    assert not re.search(r"0x0?0?820060", text), "must never write DEBUGCTRL (RIR aperture)"


def test_pcie_patches_never_touch_system_max_speed():
    for name in ("pcie-gen2.patch", "pcie-gen2-probe-retrain.patch"):
        text = (repo.ROOT / "driver" / "patches" / name).read_text().lower()
        code_only = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        code_only = re.sub(r"//.*", "", code_only)
        assert "881c0" not in code_only, "%s must not write 0x881c0 (SYSTEM_MAX_SPEED)" % name


def test_conservative_defaults_in_probe_patch():
    text = (repo.ROOT / "driver" / "patches" / "cmp-fused-probe.patch").read_text()
    assert "+int cmp_auto = 0;" in text
    assert "+int cmp_unlock_vram = -1;" in text
    assert "+int cmp_unlock_sm = -1;" in text
    assert "+int cmp_max_pcie_gen = -1;" in text
    assert "+int cmp_bar1_gb = 0;" in text


def test_build_sh_runtime_geometry_markers_present():
    text = (repo.ROOT / "driver" / "patches" / "sec2-postbl-plm-ss-cfg.patch").read_text()
    for marker in (
        "SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID",
        "SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID",
        "0x02779000U",
        "0x02669000U",
        "0x0000001000000000ULL",
        "0x0000000A00000000ULL",
    ):
        assert marker in text, "missing marker %s in sec2-postbl-plm-ss-cfg.patch" % marker
