<div align="center" style="text-align: center;">
  <img width="1280" height="300" alt="cmpunlocker banner" src="https://github.com/user-attachments/assets/6edceb8e-afcb-43a4-b5b2-4321d81284d1" />
</div>

---

## What is cmpunlocker?

<p>
  cmpunlocker restores numerous features that are restricted in firmware/OTP configuration of the NVIDIA CMP 170HX. cmpunlocker has been featured by multiple outlets like wccftech, Tom's Hardware and LinusTechTips.
</p>

<table>
  <tr>
    <td><a href="https://www.youtube.com/watch?v=pvSdeU13hKc" title=""><img src="https://github.com/user-attachments/assets/be0a9cab-19b6-47c4-91cd-cb6a98be406f"></a></td>
    <td><a href="https://www.tomshardware.com/pc-components/gpus/nvidia-crypto-mining-gpus-hacked-to-restore-locked-away-vram-in-order-to-feed-ai-boom-software-mod-unlocks-64gb-of-vram-on-usd250-cmp-170hx" title="Article by Tom's Hardware"><img src="https://github.com/user-attachments/assets/e801b2b3-3002-4346-a9ad-6b228ef62b6a"></a></td>
    <td><a href="https://wccftech.com/nvidia-cmp-170hx-8-10-gb-prices-explode-over-1000-usd-as-tool-unlocks-hidden-64-80gb-vram/" title="Article by wccftech"><img src="https://github.com/user-attachments/assets/475b5acf-999b-430c-8ede-1c39e9fd6b97"></a></td>
  </tr>
</table>

**[Join our Discord community](https://discord.gg/CdHSakKSFv)** for support and discussions.

---

## Proof of Concept

Below are memory and performance results after applying the unlock:

<table>
  <tr>
    <td><b>Memory Unlock Results</b></td>
  </tr>
  <tr>
    <td><img alt="memory unlock" src="https://github.com/user-attachments/assets/ae062bd8-e3a7-4e73-b9a4-fbcde53f3c7b" width="100%" style="max-width: 900px;" /></td>
  </tr>
</table>

<table>
  <tr>
    <td><b>Performance Benchmarks (<a href="https://github.com/ProjectPhysX/OpenCL-Benchmark">OpenCL-Benchmark</a>)</b></td>
  </tr>
  <tr>
    <td><img alt="performance benchmarks" src="https://github.com/user-attachments/assets/2501506d-420f-4014-9574-b1bd0290eb60" width="100%" style="max-width: 900px;" /></td>
  </tr>
</table>

---

## Requirements

- Linux (x86-64)
- Root access
- NVIDIA CMP 170HX
- **nvidia-open 610.xx.xx+ already installed** (libs + firmware)
- Kernel headers matching the running kernel (`linux-headers-$(uname -r)` / `kernel-devel`)
- Secure Boot disabled (patched modules are unsigned)
- Network access on first install (downloads matching stock `open-gpu-kernel-modules` sources)
- Python 3 (used at build time to select 8GB/10GB geometry)

---

## Install

To install cmpunlocker, run the following command:

```bash
sudo ./install.sh
```

To force a certain memory profile, use the `--profile` option:

```bash
sudo ./install.sh --profile=8gb    # 8GB card → 64GB unlock
sudo ./install.sh --profile=10gb   # 10GB card → 40GB unlock
```

Then perform a reboot.

## What Gets Unlocked

<table>
  <tr>
    <th>Feature</th>
    <th>Status</th>
  </tr>
  <tr>
    <td>Full SM compute throughput (SS0/SS1)</td>
    <td>Working ✓</td>
  </tr>
  <tr>
    <td>Memory geometry (64GB on 8GB cards, 40GB on 10GB cards)</td>
    <td>Working ✓</td>
  </tr>
  <tr>
    <td>PCIe Gen 2 speeds</td>
    <td>Working ✓</td>
  </tr>
    <tr>
    <td>Error-Correcting Code (ECC) DRAM and SRAM </td>
    <td>Working ✓</td>
  </tr>
  <tr>
    <td>Full BAR1 Size (64GB)</td>
    <td>Working ✓</td>
  </tr>
  <tr>
    <td>JTAG (Host2Jtag register access)</td>
    <td>Working ✓</td>
  </tr>
  <tr>
    <td>VFIO-based passthrough</td>
    <td>Working ✓</td>
  </tr>
  <tr>
    <td>GPU profiling</td>
    <td>Working ✓</td>
  </tr>
  <tr>
    <td>Persistence across reboot (patched modules)</td>
    <td>Working ✓</td>
  </tr>
  <tr>
    <td>Extended VRAM (80/96GB on glitched 8GB cards, 48GB on lucky 12-FBP 10GB cards)</td>
    <td>Opt-in (<code>cmp_unlock_vram=1</code> / <code>cmp_auto=1</code>) ✓</td>
  </tr>
  <tr>
    <td>PCIe Gen3 &amp; Gen4 (RIR-unlocked 10GB or FF-burned 8GB/10GB, automatic single-shot retrain)</td>
    <td>Opt-in (<code>cmp_max_pcie_gen=3|4</code> / <code>cmp_auto=1</code>) ✓</td>
  </tr>
  <tr>
    <td>Full defect-preserving SM unlock (FF-burned cards + volatile SW-IFF on RIR-unlocked <code>DSOV=0</code> cards)</td>
    <td>Opt-in (<code>cmp_unlock_sm=1</code> / <code>cmp_auto=1</code>) ✓</td>
  </tr>
  <tr>
    <td>Auto-sized BAR1 (64GB for &le;64GB VRAM, 128GB for &gt;64GB VRAM)</td>
    <td>Working (<code>cmp_bar1_gb=0|64|128</code>) ✓</td>
  </tr>
  <tr>
    <td>Zagitta P8 low-power mode (P8 VBIOS idle core clocks + HBM idle clock governor, ~40W &rarr; ~23W idle)</td>
    <td>Opt-in (<code>cmp_p8_low_power=1</code> / <code>cmp_auto=1</code>) ✓</td>
  </tr>
</table>

---

## Fused / RIR / Glitched Card Options (`nvidia.ko`)

Every GPU (`10de:20c2` / `10de:2082`) is evaluated independently at runtime based on:
1. **Live fuse state** (`DISABLE_SW_OVERRIDE_STATUS`, PCIe speed fuses, active coherent FBPs),
2. **Hardware defect floorplan** (`OPT_*_DEFECTIVE` — factory-defective silicon is never unmasked), and
3. **Kernel module options** (conservative defaults: plain 64GB/40GB, 74 SMs, PCIe Gen2).

> **Zero OTP / No Fuse Burning:** Neither the patched driver nor any helper script in this repository writes `FUSECTRL CMD_WRITE` or `DEBUGCTRL`. All SW-IFF writes target the volatile SRAM overlay via `IFF_SW_FUSING (0x820088)` and disappear on power cycle.

### What Each Card Gets

| Card State | Conservative Default (`sudo ./install.sh`) | Auto Mode (`sudo ./install.sh --auto` / `cmp_auto=1`) |
|---|---|---|
| Plain stock 8 GB (`0x20C2`, `DSOV=1`) | 64 GiB, 64 GiB BAR1, 74 SMs, PCIe Gen2 | 64 GiB, 64 GiB BAR1, 74 SMs, PCIe Gen2, **P8 low-power (~23W idle)** |
| Plain stock 10 GB (`0x2082`, `DSOV=1`) | 40 GiB, 64 GiB BAR1, 74 SMs, PCIe Gen2 | 40 GiB, 64 GiB BAR1, 74 SMs, PCIe Gen2, **P8 low-power (~23W idle)** |
| RIR-unlocked 10 GB (`0x2082`, `DSOV=0`) | 40 GiB, 64 GiB BAR1, 74 SMs, PCIe Gen2 | 40 GiB (or 48 GiB if 12 non-defective FBPs), 64 GiB BAR1, all non-defective SMs via SW-IFF (up to 128), PCIe Gen4 (or host slot max), **P8 low-power (~23W idle)** |
| Glitched / FF-burned 8 GB (`0x20C2`, 10 FBPs, Gen4 fuses) | 64 GiB, 64 GiB BAR1, burned SMs + RECONFIG, PCIe Gen2 | **80 GiB**, **128 GiB BAR1**, all non-defective SMs + RECONFIG, **PCIe Gen4** (or host slot max), **P8 low-power (~23W idle)** |

### Kernel Module Options

| Option | Default | Description |
|---|---|---|
| `cmp_auto=0\|1` | `0` | `0` = conservative defaults (stock cmpunlocker behavior). `1` = automatically enable every unlock allowed by each card's fuses, defect floorplan, and host PCIe root port, **plus Zagitta P8 low-power mode**. |
| `cmp_unlock_vram=-1\|0\|1` | `-1` | `-1` = follow `cmp_auto`. `0` = cap to 64/40 GiB. `1` = size VRAM dynamically from active coherent FBPs (`80/96 GiB` on glitched 8GB cards, `48 GiB` on 12-FBP 10GB cards). |
| `cmp_unlock_sm=-1\|0\|1\|2` | `-1` | `-1` = follow `cmp_auto`. `0` = off. `1` = volatile defect-preserving SW-IFF + single-shot FLR on `DSOV=0` cards (bare metal). `2` = SW-IFF when PLMs are open, else late TPC-only override inside already-awake GPCs (~80 SMs, VM fallback). |
| `cmp_max_pcie_gen=-1\|2\|3\|4` | `-1` | `-1` = follow `cmp_auto` (`2` conservative, `4` auto). Caps per-card PCIe target by card fuses and host root-port `LnkCap`. |
| `cmp_pcie_retrain=0\|1` | `1` | `1` = automatic staged single-shot link retrain (`Gen1 -> 2 -> 3 [-> 4]`) during init. `0` = apply PHY init only (manual retrain). |
| `cmp_bar1_gb=0\|64\|128` | `0` | `0` = auto (`64 GiB` for &le;64 GiB VRAM, `128 GiB` for &gt;64 GiB VRAM). |
| `cmp_magicd_a100=0\|1` | `0` | `1` = also clear extra A100 parity bits (`0x14480000`) in `PCIE_MAGIC_BITS_D` during volatile Gen4 override. |
| `cmp_p8_low_power=-1\|0\|1` | `-1` | `-1` = follow `cmp_auto` (off by default, **on with `--auto`**). `0` = disable both P8 VBIOS override and HBM governor. `1` = enable [Zagitta](https://github.com/Zagitta/gpu-unlock) P8 low-power mode (`~40W -> ~23W` idle across 8/10/12-FBP cards). |
| `cmp_p8_vbios=-1\|0\|1` | `-1` | `-1` = follow `cmp_p8_low_power`. `0` = disable P8 VBIOS override. `1` = enable boot-generated P8 VBIOS override (`romOverride00`/`01`, factory P0 preserved, never flashed to ROM). |
| `cmp_hbm_governor=-1\|0\|1` | `-1` | `-1` = follow `cmp_p8_low_power`. `0` = disable HBM governor. `1` = enable activity-based HBM idle governor (540 MHz / refresh 48 when idle, `stop_machine()` CPU hold during ~2 ms FB-stop switch, instant restore on activity/suspend/unbind). |
| `cmp_p8_min_mhz=N` | `135` | Minimum idle clock floor in MHz for P8 VBIOS override domains (GPC, XBAR, SYS, NVD, HOST; valid `1..16383`). |
| `cmp_hbm_idle_ms=N` | `5000` | Quiet time in milliseconds before the HBM governor lowers the HBM clock (default `5000` ms to avoid transition churn during LLM model loads; minimum `100` ms). |
| `cmp_bdf=""` | `""` | Optional comma-separated PCI BDF filter (e.g. `0000:01:00.0`) limiting advanced options (including P8 low-power mode) to specific GPUs. |

### Install &amp; Configuration Examples

```bash
# 1. Conservative stock install (64GB/40GB, 74 SMs, Gen2, no P8 low-power):
sudo ./install.sh

# 2. Auto-enable everything supported per card (includes Zagitta P8 low-power, ~40W -> ~23W idle):
sudo ./install.sh --auto

# 3. Auto unlocks WITHOUT P8 low-power mode:
sudo ./install.sh --auto --no-p8-low-power

# 4. Auto unlocks with P8 VBIOS idle core clocks only (disabling HBM stop_machine() governor):
sudo ./install.sh --auto --no-hbm-governor

# 5. Plain card with ONLY Zagitta P8 low-power mode (64GB/40GB, Gen2, ~23W idle):
sudo ./install.sh --p8-low-power

# 6. Explicit fine-grained install with 30 s HBM idle window (e.g. for vLLM):
sudo ./install.sh --unlock-vram --unlock-sm --pcie-gen=4 --p8-low-power --hbm-idle-ms=30000
```

You can also change options anytime without rebuilding by editing `/etc/modprobe.d/cmp-pcie-gen2.conf` and rebooting:

```ini
# Auto-enable everything supported per GPU (including P8 low-power mode):
options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x15" cmp_auto=1

# Disable P8 low-power completely while keeping --auto unlocks:
options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x15" cmp_auto=1 cmp_p8_low_power=0

# Keep P8 VBIOS idle core clocks, disable only the HBM stop_machine() clock governor:
options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x15" cmp_auto=1 cmp_hbm_governor=0

# Or target a specific GPU only (e.g. 0000:01:00.0 at Gen4 + SW-IFF SMs + P8 low power):
options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x15" cmp_unlock_sm=1 cmp_max_pcie_gen=4 cmp_p8_low_power=1 cmp_bdf="0000:01:00.0"
```

### Verification

```bash
sudo ./verify.sh                           # Check unlocked VRAM, module options, P8/HBM telemetry, dmesg, and PCIe link speed
sudo ./tools/service.sh verify             # Check authoritative live PCIe LnkSta speed & width per GPU
sudo ./tools/swiff-unlock.sh status        # Show active cmp_* module params, driver binding, and link speed
sudo dmesg | grep -E 'SEC2_DEBUG|CMP '     # Inspect geometry, SM-RECONFIG activeSMs, SW-IFF, BAR1, PCIe, P8, and HBM logs
```

> **Note on PCIe Gen4 reporting:** `nvidia-smi` caches `LnkCap` from early boot and may display `Gen3` even when the link is trained at `16.0 GT/s`. Use `sudo ./tools/service.sh verify`, `sudo lspci -vv`, or `/sys/bus/pci/devices/<bdf>/current_link_speed` for the authoritative live link speed.
>
> **Note on Zagitta P8 low-power mode & potential impact:** Enabled automatically under `--auto` (`cmp_auto=1`), the P8 VBIOS override is generated in memory from each card's own PROM image and delivered to GSP-RM via per-device binary registry keys (`romOverride00`/`01`) without flashing the card or altering factory P0. The accompanying HBM idle clock governor lowers HBM to 540 MHz / refresh 48 after 5 s of inactivity (`cmp_hbm_idle_ms=5000`), dropping idle power from ~40W to ~23W, and uses Linux `stop_machine()` during each clock transition (per Zagitta PR #373) to prevent concurrent host MMIO collisions while the framebuffer is stopped. **Potential impact:** each idle/wake HBM clock switch pauses all host CPUs for ~2–4 ms (noticeable only on real-time / ultra-low-latency host workloads, and cannot block non-CPU peer-to-peer writes), and waking from idle adds a few milliseconds to the first kernel launch. To disable it without rebuilding, add `cmp_p8_low_power=0` (or install with `--no-p8-low-power`) to turn both off, or add `cmp_hbm_governor=0` (`--no-hbm-governor`) to disable only the HBM `stop_machine()` governor while keeping P8 idle core clocks.

### SW-IFF Helper (`tools/swiff-unlock.sh`)

For RIR-unlocked cards (`DISABLE_SW_OVERRIDE_STATUS=0`), `0x8200E0`/`0x8200F4` PLMs start closed on a cold boot and are opened during the first GSP boot by `cmpunlocker`. Enabling `cmp-swiff.service` (installed automatically with `--auto` or `--unlock-sm`, or manually via `sudo ./tools/swiff-unlock.sh install-service`) performs a one-time unbind/rebind of only those GPUs that reported closed cold-boot PLMs so `nvidia.ko` arms SW-IFF + single-shot FLR automatically — no external script is needed for normal boot operation.

```bash
sudo ./tools/swiff-unlock.sh status                 # Show GPUs, module params, and link speeds
sudo ./tools/swiff-unlock.sh inspect 0000:01:00.0   # Read-only defect/floorplan report (GPU must be unbound)
```

For manual userspace SW-IFF arm/undo outside the driver, point `IFF_APPLY` at `iff_apply.py` from [scrameta/iff_apply](https://github.com/scrameta/iff_apply):

```bash
sudo IFF_APPLY=/path/to/iff_apply.py ./tools/swiff-unlock.sh arm 0000:01:00.0 --flr
sudo IFF_APPLY=/path/to/iff_apply.py ./tools/swiff-unlock.sh undo 0000:01:00.0 --flr
```

---

## Uninstall

To uninstall cmpunlocker, run the following command:

```bash
sudo ./remove.sh --yes
```

Then perform a reboot.

## Contributions

Please read [docs/CONTRIBUTING.md](https://github.com/amoghmunikote/cmpunlocker/blob/master/docs/CONTRIBUTING.md) before opening a PR.

## Support & Community

Having issues? Need help? Join our [Discord community](https://discord.gg/CdHSakKSFv) to discuss with other users and get support.
