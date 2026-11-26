import re
import shutil
import subprocess
import tempfile

import pytest

import repo

PATCH_PATH = repo.ROOT / "driver" / "patches" / "p8-low-power.patch"


def _extract_new_file_from_patch(patch_text, rel_path):
    """Extract a newly added file (--- /dev/null -> +++ b/<rel_path>) from a unified diff."""
    marker = "+++ b/" + rel_path + "\n"
    idx = patch_text.find(marker)
    assert idx != -1, f"{rel_path} not found in {PATCH_PATH.name}"
    lines = patch_text[idx + len(marker):].splitlines()
    out = []
    in_hunk = False
    for line in lines:
        if line.startswith("diff --git ") or line.startswith("--- "):
            break
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if in_hunk:
            if line.startswith("+"):
                out.append(line[1:])
            elif line.startswith("\\"):
                continue
            else:
                break
    assert out, f"no added lines extracted for {rel_path}"
    return "\n".join(out) + "\n"


def test_p8_low_power_conservative_defaults():
    text = PATCH_PATH.read_text()
    assert "+int cmp_p8_low_power = -1;" in text
    assert "+int cmp_p8_vbios = -1;" in text
    assert "+int cmp_hbm_governor = -1;" in text
    assert "+int cmp_p8_min_mhz = 135;" in text
    assert "+int cmp_hbm_idle_ms = 5000;" in text
    assert "+#define CMP_HBM_DEFAULT_MIN_CYCLES 8192U" in text
    assert "+module_param(cmp_hbm_min_cycles, int, 0644);" in text
    assert "stop_machine(cmp_hbm_switch_profile" in text


def test_p8_vbios_override_host_harness(tmp_path):
    assert shutil.which("gcc"), "gcc is required to compile host unit tests"
    header = _extract_new_file_from_patch(
        PATCH_PATH.read_text(),
        "src/nvidia/src/kernel/gpu/gsp/nv_cmp_p8_vbios.h",
    )
    (tmp_path / "nv_cmp_p8_vbios.h").write_text(header)

    harness = r"""
#define CMP_P8_HOST_TEST 1
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "nv_cmp_p8_vbios.h"

struct fixture {
    cmp_u8 rom[0x6000];
    cmp_u32 base, adjust, perf, end, bit, token;
    cmp_u8 version[5];
};

static void write16(cmp_u8 *p, cmp_u16 v) { p[0] = (cmp_u8)v; p[1] = (cmp_u8)(v >> 8); }
static void write32(cmp_u8 *p, cmp_u32 v) { write16(p, (cmp_u16)v); write16(p + 2, (cmp_u16)(v >> 16)); }

static unsigned int sum8(const cmp_u8 *p, size_t n) {
    unsigned int total = 0;
    for (size_t i = 0; i < n; i++) total += p[i];
    return total & 0xffU;
}

static void expansion(cmp_u8 *img, cmp_u32 bytes, cmp_u8 type, bool last) {
    write16(img, 0xaa55U);
    write16(img + 0x18, 0x20U);
    memcpy(img + 0x20, type == 0xe0U ? "NPDS" : "PCIR", 4);
    write16(img + 0x24, 0x10deU);
    write16(img + 0x2a, 0x18U);
    write16(img + 0x30, (cmp_u16)(bytes / 512U));
    img[0x34] = type;
    img[0x35] = last ? 0x80U : 0U;
}

static void fix_checksum(struct fixture *f) {
    cmp_u8 *rom = f->rom + f->base;
    cmp_u32 start = 0x400U + f->adjust;
    rom[f->end - 1U] = 0U;
    rom[f->end - 1U] = (cmp_u8)((256U - sum8(rom + start, f->end - start)) & 0xffU);
}

static void make_fixture(struct fixture *f, bool container, bool efi, cmp_u8 stride, bool alt_hdr) {
    static const cmp_u16 floors[10] = { 210, 615, 1215, 630, 27, 585, 540, 27, 1, 555 };
    cmp_u8 *rom, *bit, *tok, *p0;

    memset(f, 0, sizeof(*f));
    f->base = container ? 0x2000U : 0U;
    f->adjust = efi ? 0x200U : 0U;
    f->perf = 0x800U + f->adjust;
    f->end = 0x2400U + f->adjust;
    f->bit = 0x50U;
    f->token = stride == 8U ? 0x1c0U : 0x140U;
    memcpy(f->version, container ? "\x92\x00\x6d\x00\x0a" : "\x92\x00\x66\x00\x02", 5);

    if (container) {
        memcpy(f->rom, "NVGI", 4);
        write32(f->rom + 4, 0x300U);
        write32(f->rom + 8, 0x20U);
        write32(f->rom + 0x20, 0x100U);
        memcpy(f->rom + 0x1100, "RFRD", 4);
        write32(f->rom + 0x1108, f->base);
    }
    rom = f->rom + f->base;
    expansion(rom, 0x400U, 0U, false);
    if (efi) expansion(rom + 0x400U, 0x200U, 3U, false);
    expansion(rom + 0x400U + f->adjust, 0x2000U, 0xe0U, true);

    bit = rom + f->bit;
    memcpy(bit, "\xff\xb8" "BIT\0\x00\x01\x0c", 9);
    bit[9] = stride;
    bit[10] = 2U;
    bit[11] = (cmp_u8)((256U - sum8(bit, 12)) & 0xffU);

    tok = bit + 12;
    tok[0] = 'B'; tok[1] = 2U; write16(tok + 2, 5U); write16(tok + 4, 0x100U);
    rom[0x100] = f->version[3]; rom[0x101] = f->version[2];
    rom[0x102] = f->version[1]; rom[0x103] = f->version[0];
    rom[0x104] = f->version[4];

    tok += stride;
    tok[0] = 'P'; tok[1] = 2U; write16(tok + 2, 0x30U); write16(tok + 4, (cmp_u16)f->token);
    write32(rom + f->token, 0x800U);

    memcpy(rom + f->perf, "\x60\x0a\x05\x04\x06\x0a\x00\x0f\x00\x01", 10);
    for (unsigned int i = 0; i < 4U; i++)
        rom[f->perf + 10U + 65U * i] = 0xffU;
    p0 = rom + f->perf + 10U + 65U * 3U;
    memcpy(p0, alt_hdr ? "\x0f\x08\x03\xff\x00" : "\x0f\x08\x03\x00\x00", 5);
    for (unsigned int i = 0; i < 10U; i++) {
        write16(p0 + 5U + 6U * i, floors[i]);
        write32(p0 + 7U + 6U * i, (cmp_u32)floors[i] | ((cmp_u32)floors[i] << 14));
    }
    fix_checksum(f);
}

static void apply_rec(struct fixture *f, const cmp_u8 *rec, size_t len) {
    cmp_u32 off = cmp_p8_r32(rec + 5);
    assert(len == (size_t)rec[9] + 10U);
    assert(memcmp(rec, f->version, 5) == 0);
    assert(off + rec[9] <= f->end);
    memcpy(f->rom + f->base + off, rec + 10, rec[9]);
}

int main(void) {
    static const cmp_u8 lowered[5] = { 0, 1, 3, 5, 9 };
    static const cmp_u16 orig_floors[10] = { 210, 615, 1215, 630, 27, 585, 540, 27, 1, 555 };

    /* 1. All 16 variants: container/raw, EFI, stride 6/8, both P0 headers. */
    for (unsigned int v = 0; v < 16U; v++) {
        struct fixture orig, applied;
        cmp_u8 p8[CMP_P8_RECORD_SIZE], csum[CMP_P8_CHECKSUM_SIZE];
        make_fixture(&orig, (v & 1U) != 0, (v & 2U) != 0, (v & 4U) ? 8U : 6U, (v & 8U) != 0);
        applied = orig;

        assert(cmp_p8_build_overrides(orig.rom, sizeof(orig.rom), 135U, p8, csum) == CMP_P8_OK);
        assert(cmp_p8_r32(p8 + 5) == orig.perf + 10U);
        assert(p8[9] == 65U);
        assert(csum[9] == 1U);
        assert(cmp_p8_r32(csum + 5) == orig.end - 1U);

        apply_rec(&applied, p8, sizeof(p8));
        apply_rec(&applied, csum, sizeof(csum));

        /* Checksum valid, factory P0 untouched, P8 in slot 0 with lowered floors. */
        assert(sum8(applied.rom + orig.base + 0x400U + orig.adjust, 0x2000U) == 0U);
        assert(memcmp(applied.rom + orig.base + orig.perf + 10U + 65U * 3U,
                      orig.rom + orig.base + orig.perf + 10U + 65U * 3U, 65U) == 0);
        const cmp_u8 *p8_row = applied.rom + orig.base + orig.perf + 10U;
        assert(p8_row[0] == 7U);
        for (unsigned int d = 0; d < 10U; d++) {
            const cmp_u8 *tuple = p8_row + 5U + d * 6U;
            cmp_u32 lim = cmp_p8_r32(tuple + 2);
            bool is_lowered = false;
            for (unsigned int k = 0; k < 5U; k++)
                if (lowered[k] == d) is_lowered = true;
            cmp_u32 want_min = is_lowered ? 135U : orig_floors[d];
            assert((lim & 0x3fffU) == want_min);
            assert(((lim >> 14) & 0x3fffU) == orig_floors[d]);
        }
        /* Re-running on patched image detects existing P8. */
        assert(cmp_p8_build_overrides(applied.rom, sizeof(applied.rom), 135U, p8, csum) == CMP_P8_ERR_ALREADY);
    }

    /* 2. Reject invalid inputs and malformed VBIOS layouts. */
    struct fixture f;
    cmp_u8 p8[CMP_P8_RECORD_SIZE], csum[CMP_P8_CHECKSUM_SIZE];
    make_fixture(&f, false, false, 6U, false);
    assert(cmp_p8_build_overrides(f.rom, sizeof(f.rom), 0U, p8, csum) == CMP_P8_ERR_INVAL);
    assert(cmp_p8_build_overrides(f.rom, sizeof(f.rom), 0x4000U, p8, csum) == CMP_P8_ERR_INVAL);

    /* Non-slot-0 empty entry rejected. */
    f.rom[f.perf + 10U] = 10U;
    fix_checksum(&f);
    assert(cmp_p8_build_overrides(f.rom, sizeof(f.rom), 135U, p8, csum) == CMP_P8_ERR_UNSUP);

    /* Duplicate P0 rejected. */
    make_fixture(&f, false, false, 6U, false);
    f.rom[f.perf + 10U + 65U] = 15U;
    fix_checksum(&f);
    assert(cmp_p8_build_overrides(f.rom, sizeof(f.rom), 135U, p8, csum) == CMP_P8_ERR_BADMSG);

    /* Bad ROM checksum rejected. */
    make_fixture(&f, false, false, 6U, false);
    f.rom[f.end - 1U] ^= 1U;
    assert(cmp_p8_build_overrides(f.rom, sizeof(f.rom), 135U, p8, csum) == CMP_P8_ERR_BADMSG);

    /* Zero floor on a lowered domain rejected. */
    make_fixture(&f, false, false, 6U, false);
    write32(f.rom + f.perf + 10U + 65U * 3U + 7U, 0U);
    fix_checksum(&f);
    assert(cmp_p8_build_overrides(f.rom, sizeof(f.rom), 135U, p8, csum) == CMP_P8_ERR_UNSUP);

    puts("P8 VBIOS host tests passed");
    return 0;
}
"""
    src = tmp_path / "test_p8.c"
    exe = tmp_path / "test_p8"
    src.write_text(harness)
    r = subprocess.run(
        ["gcc", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
         "-I", str(tmp_path), str(src), "-o", str(exe)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "P8 VBIOS host tests passed" in run.stdout


def test_hbm_governor_host_harness(tmp_path):
    assert shutil.which("gcc"), "gcc is required to compile host unit tests"
    header = _extract_new_file_from_patch(
        PATCH_PATH.read_text(),
        "kernel-open/nvidia/nv-cmp-hbm.h",
    )
    (tmp_path / "nv-cmp-hbm.h").write_text(header)

    harness = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define __iomem
#define BUSY_COEFF   0x00014001U /* 1728 MHz (27*64/1/1) */
#define IDLE_COEFF   0x00011401U /* 540 MHz  (27*20/1/1) */
#define BUSY_REFRESH 0xc4028033U /* refresh=6 (0x30 >> 3) */
#define MS           1000000ULL

struct cpumask;
static u32 readl(const void *addr);
static void writel(u32 value, void *addr);
static void udelay(unsigned long us);
static void ndelay(unsigned long ns);
static int stop_machine(int (*fn)(void *), void *data, const struct cpumask *cpus);

#include "nv-cmp-hbm.h"

struct sim_card {
    u32 active_mask; /* bitmask of present FBPAs (16, 20, or 24) */
    u32 refresh[24], coeff[24], cfg;
    u32 refresh_plm, pll_plm;
    u32 gfw_boot, gsp_status;
    u32 request, ack, count, fb_count;
    u32 counter_ctrl;
    bool split_counters; /* true: 615.xx layout (slot 0 GR+CE, slot 1 pure FB) */
    unsigned int lock_reads, lock_wait;
    unsigned int stop_machine_calls, clock_writes, sw_refreshes;
    bool cpus_held;
    bool saw_refresh_before_raise, saw_refresh_after_lower;
    bool force_lock_timeout;
};

static struct sim_card card;
static char fake_bar[1];

static bool fbpa_present(unsigned int i) {
    return i < 24U && ((card.active_mask & (1U << i)) != 0U);
}

static void reset_card(u32 active_mask) {
    memset(&card, 0, sizeof(card));
    card.active_mask = active_mask;
    card.cfg = CMP_HBM_PLL_LOCK | 1U;
    card.refresh_plm = 0xffffffffU;
    card.pll_plm = 0xffffffffU;
    card.gfw_boot = 0x3ffU;
    card.gsp_status = 0x33U;
    card.counter_ctrl = 2U;
    for (unsigned int i = 0; i < 24U; i++) {
        card.refresh[i] = BUSY_REFRESH;
        card.coeff[i] = BUSY_COEFF;
    }
}

static u32 readl(const void *addr) {
    u32 reg = (u32)((const char *)addr - fake_bar);
    if (reg >= CMP_HBM_FBPA_BASE && reg < CMP_HBM_FBPA_BASE + 24U * CMP_HBM_FBPA_STRIDE) {
        unsigned int idx = (reg - CMP_HBM_FBPA_BASE) / CMP_HBM_FBPA_STRIDE;
        u32 off = reg % CMP_HBM_FBPA_STRIDE;
        if (!fbpa_present(idx)) return 0xbadf2016U;
        switch (off) {
        case CMP_HBM_FBPA_CFG1:   return 0x02779000U;
        case CMP_HBM_REFRESH_PLM: return card.refresh_plm;
        case CMP_HBM_PLL_PLM:     return card.pll_plm;
        case CMP_HBM_REFRESH:     return card.refresh[idx];
        case CMP_HBM_PLL_COEFF:   return card.coeff[idx];
        case CMP_HBM_PLL_CFG:
            if (card.force_lock_timeout)
                return card.cfg & ~CMP_HBM_PLL_LOCK;
            if (card.lock_wait > 0U) {
                card.lock_wait--;
                return card.cfg & ~CMP_HBM_PLL_LOCK;
            }
            return card.cfg;
        }
        return 0U;
    }
    switch (reg) {
    case CMP_HBM_GFW_BOOT:         return card.gfw_boot;
    case CMP_HBM_GSP_RISCV_STATUS: return card.gsp_status;
    case CMP_HBM_FB_STOP_OUTPUT:   return 0x3ffffc00U | card.request;
    case CMP_HBM_FB_STOP_INPUT:    return 0x00501400U | card.ack;
    case 0x0010be40U:              return card.split_counters ? 0x00380001U : 0x00380081U;
    case 0x0010be80U:              return 0x00700000U;
    case 0x0010bec0U:              return 0x00000007U;
    case 0x0010bfc0U:              return card.counter_ctrl;
    case 0x0010bf80U:              return card.count;
    case 0x0010be44U:              return card.split_counters ? 0x00000080U : 0U;
    case 0x0010be84U:              return 0U;
    case 0x0010bec4U:              return 0U;
    case 0x0010bfc4U:              return card.split_counters ? card.counter_ctrl : 0U;
    case 0x0010bf84U:              return card.fb_count;
    }
    return 0U;
}

static void writel(u32 value, void *addr) {
    u32 reg = (u32)((char *)addr - fake_bar);
    if (reg >= CMP_HBM_FBPA_BASE && reg < CMP_HBM_FBPA_BASE + 24U * CMP_HBM_FBPA_STRIDE) {
        unsigned int idx = (reg - CMP_HBM_FBPA_BASE) / CMP_HBM_FBPA_STRIDE;
        u32 off = reg % CMP_HBM_FBPA_STRIDE;
        if (fbpa_present(idx) && off == CMP_HBM_REFRESH) {
            assert(card.cpus_held);
            assert(card.ack == CMP_HBM_FB_STOP);
            u32 target = (value & CMP_HBM_REFRESH_MASK) >> 3;
            if (target == CMP_HBM_IDLE_REFRESH) {
                /* Lengthen refresh AFTER clock lowered. */
                assert(card.coeff[idx] == IDLE_COEFF);
                card.saw_refresh_after_lower = true;
            } else {
                /* Shorten refresh BEFORE clock raised. */
                assert(card.coeff[idx] == IDLE_COEFF);
                card.saw_refresh_before_raise = true;
            }
            card.refresh[idx] = value;
        } else if (fbpa_present(idx) && off == CMP_HBM_SOFTWARE_REF) {
            assert(card.cpus_held);
            card.sw_refreshes++;
        }
        return;
    }
    switch (reg) {
    case CMP_HBM_FB_STOP_SET:
        assert(card.cpus_held);
        card.request |= value & CMP_HBM_FB_STOP;
        card.ack = card.request;
        break;
    case CMP_HBM_FB_STOP_CLEAR:
        assert(card.cpus_held);
        card.request &= ~(value & CMP_HBM_FB_STOP);
        card.ack = card.request;
        break;
    case CMP_HBM_PLL_CFG_MC2:
        assert(card.cpus_held);
        assert(card.ack == CMP_HBM_FB_STOP);
        card.cfg = value;
        break;
    case CMP_HBM_PLL_COEFF_MC2:
        assert(card.cpus_held);
        assert(card.ack == CMP_HBM_FB_STOP);
        card.clock_writes++;
        card.lock_wait = card.lock_reads;
        for (unsigned int i = 0; i < 24U; i++)
            if (fbpa_present(i)) card.coeff[i] = value;
        break;
    }
}

static void udelay(unsigned long us) { (void)us; }
static void ndelay(unsigned long ns) { (void)ns; }

static int stop_machine(int (*fn)(void *), void *data, const struct cpumask *cpus) {
    int ret;
    (void)cpus;
    assert(!card.cpus_held);
    card.cpus_held = true;
    card.stop_machine_calls++;
    ret = fn(data);
    card.cpus_held = false;
    return ret;
}

static void test_topology(u32 mask, unsigned int expected_fbpas) {
    struct cmp_hbm hbm;
    u64 t = 1000ULL * MS;

    reset_card(mask);
    card.lock_reads = 6U;
    cmp_hbm_init(&hbm, CMP_HBM_DEFAULT_IDLE_MS);

    /* GFW/GSP boot gate. */
    card.gsp_status = 0U;
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == -EAGAIN);
    card.gsp_status = 0x33U;

    /* PLM host write gate. */
    card.refresh_plm = 0U;
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == -EAGAIN);
    card.refresh_plm = 0xffffffffU;

    /* Baseline capture. */
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    assert(hbm.profile && hbm.baseline && !hbm.idle);
    assert(hbm.fbpas == mask);

    /* Quiet for 4.98s -> still busy. */
    for (unsigned int step = 0; step < 249U; step++) {
        t += 20ULL * MS;
        assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
        assert(!hbm.idle);
    }
    /* At 5.00s quiet -> enters idle under stop_machine(). */
    t += 20ULL * MS;
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    assert(hbm.idle);
    assert(card.saw_refresh_after_lower);
    assert(card.stop_machine_calls == 1U);
    assert(card.sw_refreshes == expected_fbpas);

    /* Activity counter wraparound wakes immediately. */
    card.count = 0x7fffffffU;
    t += 20ULL * MS;
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    assert(!hbm.idle);
    assert(card.saw_refresh_before_raise);
    assert(card.stop_machine_calls == 2U);

    /* Sample gap > 1s safely resets baseline. */
    t += 2000ULL * MS;
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == -EAGAIN);
    assert(!hbm.baseline && !hbm.idle);

    /* Re-baseline and test explicit restore after idle. */
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    for (unsigned int step = 0; step < 250U; step++) {
        t += 20ULL * MS;
        assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    }
    assert(hbm.idle);
    assert(cmp_hbm_restore(&hbm, fake_bar) == 0);
    assert(!hbm.idle && !hbm.fb_stopped);
}

static void test_housekeeping_threshold(void) {
    struct cmp_hbm hbm;
    u64 t = 1000ULL * MS;

    /* 615.xx split layout: slot 0 = GR+CE0..8, slot 1 = pure FB (0x80). */
    reset_card(0x003fcfffU);
    card.split_counters = true;
    cmp_hbm_init(&hbm, 100U);
    assert(hbm.policy.min_cycles == CMP_HBM_DEFAULT_MIN_CYCLES);

    assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    assert(hbm.counters == 0x3U);

    /* Periodic ~2890-cycle GSP housekeeping blip on slot 0 while busy does not block idle. */
    for (unsigned int i = 0; i < 5U; i++) {
        if (i == 2U) card.count += 2890U;
        t += 20ULL * MS;
        assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    }
    assert(hbm.idle);
    assert(card.stop_machine_calls == 1U);

    /* Once idle, another 2890-cycle GR/CE blip with zero FB delta stays idle. */
    card.count += 2890U;
    t += 20ULL * MS;
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    assert(hbm.idle);
    assert(hbm.active_counters == 0U);
    assert(hbm.max_delta == 2890U);
    assert(card.stop_machine_calls == 1U);

    /* Pure FB counter (slot 1) wakes immediately even on delta == 1. */
    card.fb_count += 1U;
    t += 20ULL * MS;
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    assert(!hbm.idle);
    assert(hbm.active_counters == (1U << 1));
    assert(hbm.max_delta == 1U);
    assert(card.stop_machine_calls == 2U);

    /* Return to idle, then verify real GR/CE work (>= min_cycles) wakes immediately. */
    for (unsigned int i = 0; i < 5U; i++) {
        t += 20ULL * MS;
        assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    }
    assert(hbm.idle);
    card.count += CMP_HBM_DEFAULT_MIN_CYCLES;
    t += 20ULL * MS;
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    assert(!hbm.idle);
    assert(hbm.active_counters == (1U << 0));
    assert(hbm.max_delta == CMP_HBM_DEFAULT_MIN_CYCLES);

    /* Setting min_cycles=1 restores strict delta != 0 on slot 0. */
    for (unsigned int i = 0; i < 5U; i++) {
        t += 20ULL * MS;
        assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    }
    assert(hbm.idle);
    hbm.policy.min_cycles = 1U;
    card.count += 2890U;
    t += 20ULL * MS;
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    assert(!hbm.idle);
    assert(hbm.active_counters == (1U << 0));
}

int main(void) {
    /* 8-FBP (16 FBPA), 10-FBP (20 FBPA), and 12-FBP (24 FBPA) CMP 170HX layouts. */
    test_topology(0x0000ffffU, 16U);
    test_topology(0x003fcfffU, 20U);
    test_topology(0x00ffffffU, 24U);
    test_housekeeping_threshold();

    /* PLL lock timeout rolls back cleanly and resumes FB. */
    struct cmp_hbm hbm;
    u64 t = 1000ULL * MS;
    reset_card(0x003fcfffU);
    cmp_hbm_init(&hbm, 100U);
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    card.force_lock_timeout = true;
    for (unsigned int i = 0; i < 4U; i++) {
        t += 20ULL * MS;
        assert(cmp_hbm_poll(&hbm, fake_bar, t) == 0);
    }
    t += 20ULL * MS;
    /* Timeout fails enter_idle, restores cleanly once lock recovers. */
    assert(cmp_hbm_poll(&hbm, fake_bar, t) == -ETIMEDOUT);
    assert(hbm.fb_stopped);
    card.force_lock_timeout = false;
    assert(cmp_hbm_restore(&hbm, fake_bar) == 0);
    assert(!hbm.idle && !hbm.fb_stopped);

    puts("HBM governor host tests passed");
    return 0;
}
"""
    src = tmp_path / "test_hbm.c"
    exe = tmp_path / "test_hbm"
    src.write_text(harness)
    r = subprocess.run(
        ["gcc", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
         "-I", str(tmp_path), str(src), "-o", str(exe)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "HBM governor host tests passed" in run.stdout


def test_install_sh_p8_cli_flags():
    r = subprocess.run(
        ["bash", str(repo.ROOT / "install.sh"), "--help"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    for flag in (
        "--p8-low-power", "--no-p8-low-power", "--p8-vbios",
        "--no-hbm-governor", "--p8-min-mhz=N", "--hbm-idle-ms=N",
        "--hbm-min-cycles=N",
    ):
        assert flag in r.stdout

    bad_mhz = subprocess.run(
        ["bash", str(repo.ROOT / "install.sh"), "--p8-min-mhz=0"],
        capture_output=True, text=True,
    )
    assert bad_mhz.returncode != 0
    bad_idle = subprocess.run(
        ["bash", str(repo.ROOT / "install.sh"), "--hbm-idle-ms=50"],
        capture_output=True, text=True,
    )
    assert bad_idle.returncode != 0
    bad_cycles = subprocess.run(
        ["bash", str(repo.ROOT / "install.sh"), "--hbm-min-cycles=0"],
        capture_output=True, text=True,
    )
    assert bad_cycles.returncode != 0
