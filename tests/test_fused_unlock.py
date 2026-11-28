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


def _extract_added_c_block(patch_text, start_marker, end_marker):
    lines = []
    for line in patch_text.splitlines():
        if line.startswith("+") and not line.startswith("+++ "):
            lines.append(line[1:])
    blob = "\n".join(lines)
    s = blob.index(start_marker)
    e = blob.index(end_marker, s)
    return blob[s:e]


def test_geometry_and_bar1_host_harness(tmp_path):
    import shutil

    assert shutil.which("gcc"), "gcc is required to compile host unit tests"

    gsp_patch = (repo.ROOT / "driver" / "patches" / "sec2-postbl-plm-ss-cfg.patch").read_text()
    geom_c = _extract_added_c_block(
        gsp_patch,
        "static NvBool\n_kgspCmp170hxRegReadable(",
        "\nstatic NvBool\n_kgspSec2PostblTimingEnabled(",
    )

    bar1_patch = (repo.ROOT / "driver" / "patches" / "bar1-resize-unlock.patch").read_text()
    bar1_c = _extract_added_c_block(
        bar1_patch,
        "static u32 nv_cmp_bar1_target_gb(",
        "\nstatic void nv_cmp_unlock_bar1_resize(",
    )

    harness = (
        """
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

typedef uint32_t NvU32;
typedef uint64_t NvU64;
typedef uint32_t u32;
typedef uint64_t resource_size_t;
typedef int NvBool;
#define NV_TRUE  1
#define NV_FALSE 0
#define LEVEL_ERROR 0
#define NV_PRINTF(lvl, fmt, ...) ((void)0)
#define __iomem

#define SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID   0x20C2
#define SEC2_POSTBL_TIMING_CMP_170HX_10GB_PCI_DEVICE_ID 0x2082

typedef struct {
    struct { NvU32 PCIDeviceID; } idInfo;
} OBJGPU;

struct pci_bus { unsigned int number; };
struct pci_dev {
    struct pci_bus *bus;
    unsigned int devfn;
    u32 device;
};

static int g_want_vram = 0;
static int g_want_bar1 = 0;
static NvU32 g_reg_fbp = 0;
static NvU32 g_reg_fbpa = 0;
static NvU32 g_reg_fbio = 0;
static NvU32 g_reg_num_active = 0;

static unsigned int gpuGetDomain(OBJGPU *g) { (void)g; return 0; }
static unsigned int gpuGetBus(OBJGPU *g)    { (void)g; return 1; }
static unsigned int gpuGetDevice(OBJGPU *g) { (void)g; return 0; }

static int cmp170hx_want_unlock_vram(unsigned int d, unsigned int b, unsigned int dev, unsigned int fn)
{
    (void)d; (void)b; (void)dev; (void)fn;
    return g_want_vram;
}

static int cmp170hx_want_bar1_gb(void)
{
    return g_want_bar1;
}

static NvU32 GPU_REG_RD32(OBJGPU *g, NvU32 addr)
{
    (void)g;
    if (addr == 0x00820d38U) return g_reg_fbp;
    if (addr == 0x00820c18U) return g_reg_fbpa;
    if (addr == 0x00820c14U) return g_reg_fbio;
    if (addr == 0x009a0164U) return g_reg_num_active;
    assert(0 && "unexpected register read");
    return 0;
}

static unsigned int pci_domain_nr(struct pci_bus *bus) { (void)bus; return 0; }
#define PCI_SLOT(devfn) ((devfn) >> 3)
#define PCI_FUNC(devfn) ((devfn) & 7U)
static uint64_t pci_resource_len(struct pci_dev *p, int bar) { (void)p; (void)bar; return 0x01000000ULL; }

static uint8_t g_fake_fuse[0x1000];
static void *ioremap(resource_size_t base, size_t len) { (void)base; (void)len; return g_fake_fuse; }
static void iounmap(void *p) { (void)p; }
static u32 readl(const void *addr)
{
    uintptr_t off = (const uint8_t *)addr - g_fake_fuse;
    if (off == 0xD38U) return g_reg_fbp;
    if (off == 0xC18U) return g_reg_fbpa;
    if (off == 0xC14U) return g_reg_fbio;
    assert(0 && "unexpected fuse offset");
    return 0;
}

"""
        + geom_c
        + "\n"
        + bar1_c
        + """

static void make_masks(int active_fbps, int half_fbps, NvU32 *fbp, NvU32 *fbpa, NvU32 *fbio)
{
    *fbp = 0xfffU;
    *fbpa = 0xffffffU;
    *fbio = 0xffffffU;
    for (int f = 0; f < active_fbps; f++) {
        *fbp &= ~(1U << f);
        if (f < active_fbps - half_fbps) {
            *fbpa &= ~(0x3U << (2 * f));
            *fbio &= ~(0x3U << (2 * f));
        } else {
            /* Enable only lower slice of this FBP (half-FBP). */
            *fbpa &= ~(0x1U << (2 * f));
            *fbio &= ~(0x1U << (2 * f));
        }
    }
}

static void check_case(NvU32 dev_id, int want_vram, NvU32 fbp, NvU32 fbpa, NvU32 fbio,
                       NvU32 num_active, NvU32 exp_lmr, NvU64 exp_gib, NvU32 exp_full,
                       u32 exp_bar1)
{
    OBJGPU gpu = { .idInfo = { .PCIDeviceID = dev_id << 16 } };
    struct pci_bus bus = { .number = 1 };
    struct pci_dev pdev = { .bus = &bus, .devfn = 0, .device = dev_id };
    NvU32 cfg1 = 0, lmr = 0, full = 0;
    NvU64 fb_bytes = 0;
    u32 bar1 = 0;

    g_want_vram = want_vram;
    g_want_bar1 = 0;
    g_reg_fbp = fbp;
    g_reg_fbpa = fbpa;
    g_reg_fbio = fbio;
    g_reg_num_active = num_active;

    _kgspCmp170hxComputeGeometry(&gpu, &cfg1, &lmr, &fb_bytes, &full);
    bar1 = nv_cmp_bar1_target_gb(&pdev, 0x10000000ULL);

    assert(cfg1 == (dev_id == 0x20C2U ? 0x02779000U : 0x02669000U));
    assert(lmr == exp_lmr);
    assert(fb_bytes == (exp_gib << 30));
    assert(full == exp_full);
    assert(bar1 == exp_bar1);
}

int main(void)
{
    NvU32 fbp, fbpa, fbio;

    /* 1. Standard 0x20C2 (8 full FBPs) */
    make_masks(8, 0, &fbp, &fbpa, &fbio);
    check_case(0x20C2, 0, fbp, fbpa, fbio, 8, 0x20BU, 64, 8, 64);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 8, 0x20BU, 64, 8, 64);

    /* 2. Glitched 0x20C2 (9/10/11/12 full FBPs) */
    make_masks(9, 0, &fbp, &fbpa, &fbio);
    check_case(0x20C2, 0, fbp, fbpa, fbio, 9, 0x20BU, 64, 9, 64);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 9, 0x24BU, 72, 9, 128);

    make_masks(10, 0, &fbp, &fbpa, &fbio);
    check_case(0x20C2, 0, fbp, fbpa, fbio, 10, 0x20BU, 64, 10, 64);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 10, 0x28BU, 80, 10, 128);

    make_masks(12, 0, &fbp, &fbpa, &fbio);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 12, 0x30BU, 96, 12, 128);

    /* 3. Half-FBP overrun regression on 0x20C2: 8 active FBPs, 1 half (7 full + 1 half = 60 GiB real) -> 56 GiB safe floor */
    make_masks(8, 1, &fbp, &fbpa, &fbio);
    check_case(0x20C2, 0, fbp, fbpa, fbio, 8, 0x1CBU, 56, 7, 64);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 8, 0x1CBU, 56, 7, 64);

    /* 4. Half-FBP on 0x20C2 with 10 active FBPs (9 full + 1 half = 76 GiB real) -> 72 GiB (not wasted to 64 GiB) */
    make_masks(10, 1, &fbp, &fbpa, &fbio);
    check_case(0x20C2, 0, fbp, fbpa, fbio, 10, 0x20BU, 64, 9, 64);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 10, 0x24BU, 72, 9, 128);
    check_case(0x20C2, 1, fbp, fbpa, fbio,  9, 0x24BU, 72, 9, 128);

    /* 5. Half-FBP BAR1 match: 9 active FBPs (8 full + 1 half) -> 64 GiB VRAM and 64 GiB BAR1 */
    make_masks(9, 1, &fbp, &fbpa, &fbio);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 9, 0x20BU, 64, 8, 64);

    /* 6. Under-stock full FBPs on 0x20C2 (7 full) -> 56 GiB, never 64 GiB */
    make_masks(7, 0, &fbp, &fbpa, &fbio);
    check_case(0x20C2, 0, fbp, fbpa, fbio, 7, 0x1CBU, 56, 7, 64);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 7, 0x1CBU, 56, 7, 64);

    /* 7. Standard and extended 0x2082 (10/12 full FBPs) */
    make_masks(10, 0, &fbp, &fbpa, &fbio);
    check_case(0x2082, 0, fbp, fbpa, fbio, 10, 0x28AU, 40, 10, 64);
    check_case(0x2082, 1, fbp, fbpa, fbio, 10, 0x28AU, 40, 10, 64);

    make_masks(12, 0, &fbp, &fbpa, &fbio);
    check_case(0x2082, 0, fbp, fbpa, fbio, 12, 0x28AU, 40, 12, 64);
    check_case(0x2082, 1, fbp, fbpa, fbio, 12, 0x30AU, 48, 12, 64);

    /* 8. Half-FBP overrun regression on 0x2082: 10 active FBPs, 1 half (9 full + 1 half = 38 GiB real) -> 36 GiB safe floor */
    make_masks(10, 1, &fbp, &fbpa, &fbio);
    check_case(0x2082, 0, fbp, fbpa, fbio, 10, 0x24AU, 36, 9, 64);
    check_case(0x2082, 1, fbp, fbpa, fbio, 10, 0x24AU, 36, 9, 64);

    /* 9. Half-FBP extended on 0x2082: 12 active FBPs, 1 half (11 full + 1 half = 46 GiB real) -> 44 GiB */
    make_masks(12, 1, &fbp, &fbpa, &fbio);
    check_case(0x2082, 0, fbp, fbpa, fbio, 12, 0x28AU, 40, 11, 64);
    check_case(0x2082, 1, fbp, fbpa, fbio, 12, 0x2CAU, 44, 11, 64);

    /* 10. Under-stock full FBPs on 0x2082 (8 and 9 full) -> 32 / 36 GiB, never 40 GiB */
    make_masks(8, 0, &fbp, &fbpa, &fbio);
    check_case(0x2082, 0, fbp, fbpa, fbio, 8, 0x20AU, 32, 8, 64);
    make_masks(9, 0, &fbp, &fbpa, &fbio);
    check_case(0x2082, 1, fbp, fbpa, fbio, 9, 0x24AU, 36, 9, 64);

    /* 11. Misaligned FBPA != FBIO: blocks extension above stock, still clamps downward */
    make_masks(10, 0, &fbp, &fbpa, &fbio);
    fbpa |= (1U << 18); /* FBP 9 FBPA0 off, FBIO0 still on -> 9 full FBPs, misaligned */
    check_case(0x20C2, 1, fbp, fbpa, fbio, 10, 0x20BU, 64, 9, 64);

    make_masks(8, 0, &fbp, &fbpa, &fbio);
    fbpa |= (1U << 14); /* FBP 7 FBPA0 off, FBIO0 still on -> 7 full FBPs -> must clamp to 56 GiB */
    check_case(0x20C2, 0, fbp, fbpa, fbio, 8, 0x1CBU, 56, 7, 64);

    /* 12. Poisoned fuse status -> stock fallback */
    check_case(0x20C2, 1, 0xffffffffU, 0xffffffffU, 0xffffffffU, 0xffffffffU, 0x20BU, 64, 0, 64);
    check_case(0x2082, 1, 0xbadf5040U, 0xbadf5040U, 0xbadf5040U, 0xbadf5040U, 0x28AU, 40, 0, 64);

    /* 13. NUM_ACTIVE poison is tolerated; unexpected NUM_ACTIVE blocks extension but still clamps down */
    make_masks(10, 0, &fbp, &fbpa, &fbio);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 0xbadf5040U, 0x28BU, 80, 10, 128);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 5, 0x20BU, 64, 10, 128);

    make_masks(7, 0, &fbp, &fbpa, &fbio);
    check_case(0x20C2, 1, fbp, fbpa, fbio, 5, 0x1CBU, 56, 7, 64);

    puts("ALL GEOMETRY + BAR1 TESTS PASSED");
    return 0;
}
"""
    )

    src = tmp_path / "test_geom.c"
    exe = tmp_path / "test_geom"
    src.write_text(harness)
    c = subprocess.run(
        ["gcc", "-Wall", "-Wextra", "-Werror", "-O2", str(src), "-o", str(exe)],
        capture_output=True,
        text=True,
    )
    assert c.returncode == 0, c.stdout + c.stderr
    r = subprocess.run([str(exe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ALL GEOMETRY + BAR1 TESTS PASSED" in r.stdout

