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


def test_p2p_patch_trap30_ordering_and_safety():
    raw = (repo.ROOT / "driver" / "patches" / "p2p-unlock.patch").read_text()
    assert "+int cmp_p2p = 1;" in raw
    text = raw.lower()
    m = re.search(r"p2ptable\[\]\s*=\s*\{(.*?)\};", text, re.S)
    assert m, "p2pTable[] not found in p2p-unlock.patch"
    table = m.group(1)
    # Must install PLM, trap PLM, match, mask, data1, data2, cfg strictly before arming trap 30 action.
    expected_order = [
        "0x0013affc",  # P2P_PLM
        "0x00122778",  # P2P_TRAP_PLM (trap 30)
        "0x00122478",  # P2P_TRAP_MATCH
        "0x001224f8",  # P2P_TRAP_MASK
        "0x00122578",  # P2P_TRAP_DATA1
        "0x001225f8",  # P2P_TRAP_DATA2
        "0x001226f8",  # P2P_TRAP_CFG
        "0x00122678",  # P2P_TRAP_ACTION (must be last in p2pTable)
    ]
    positions = [table.index(addr) for addr in expected_order]
    assert positions == sorted(positions), "p2pTable must arm TRAP_ACTION strictly last"
    # Must never touch trap 31 (0x12247c / 0x12267c / 0x12277c), reserved for IFF requester.
    for trap31 in ("12247c", "1224fc", "12257c", "1225fc", "12267c", "1226fc", "12277c"):
        assert trap31 not in text, "must not touch SYS trap 31 (%s)" % trap31
    # Must verify 0x00821030 readback == 0 and disarm 0x00122678 with 0 on failure.
    assert "0x00821030u" in text
    assert "gpu_reg_wr32(pgpu, 0x00122678u, 0x00000000u)" in text


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
