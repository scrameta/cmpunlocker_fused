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
    <td>Native PCIe P2P (mailbox PLM + secure-option override)</td>
    <td>Working (<code>cmp_p2p=1</code> default) ✓</td>
  </tr>
</table>

---

## Fused / RIR / Glitched Card Options (`nvidia.ko`)

Every GPU (`10de:20c2` / `10de:2082`) is evaluated independently at runtime based on:
1. **Live fuse state** (`DISABLE_SW_OVERRIDE_STATUS`, PCIe speed fuses, active coherent FBPs),
2. **Hardware defect floorplan** (`OPT_*_DEFECTIVE` — factory-defective silicon is never unmasked), and
3. **Kernel module options** (conservative defaults: plain 64GB/40GB, 74 SMs, PCIe Gen2, native PCIe P2P).

> **Zero OTP / No Fuse Burning:** Neither the patched driver nor any helper script in this repository writes `FUSECTRL CMD_WRITE` or `DEBUGCTRL`. All SW-IFF writes target the volatile SRAM overlay via `IFF_SW_FUSING (0x820088)` and disappear on power cycle.

### What Each Card Gets

| Card State | Conservative Default (`sudo ./install.sh`) | Auto Mode (`sudo ./install.sh --auto` / `cmp_auto=1`) |
|---|---|---|
| Plain stock 8 GB (`0x20C2`, `DSOV=1`) | 64 GiB, 64 GiB BAR1, 74 SMs, PCIe Gen2, Native P2P | 64 GiB, 64 GiB BAR1, 74 SMs, PCIe Gen2, Native P2P |
| Plain stock 10 GB (`0x2082`, `DSOV=1`) | 40 GiB, 64 GiB BAR1, 74 SMs, PCIe Gen2, Native P2P | 40 GiB, 64 GiB BAR1, 74 SMs, PCIe Gen2, Native P2P |
| RIR-unlocked 10 GB (`0x2082`, `DSOV=0`) | 40 GiB, 64 GiB BAR1, 74 SMs, PCIe Gen2, Native P2P | 40 GiB (or 48 GiB if 12 non-defective FBPs), 64 GiB BAR1, all non-defective SMs via SW-IFF (up to 128), PCIe Gen4 (or host slot max), Native P2P |
| Glitched / FF-burned 8 GB (`0x20C2`, 10 FBPs, Gen4 fuses) | 64 GiB, 64 GiB BAR1, burned SMs + RECONFIG, PCIe Gen2, Native P2P | **80 GiB**, **128 GiB BAR1**, all non-defective SMs + RECONFIG, **PCIe Gen4** (or host slot max), **Native P2P** |

### Kernel Module Options

| Option | Default | Description |
|---|---|---|
| `cmp_auto=0\|1` | `0` | `0` = conservative defaults (stock cmpunlocker behavior). `1` = automatically enable every unlock allowed by each card's fuses, defect floorplan, and host PCIe root port. |
| `cmp_unlock_vram=-1\|0\|1` | `-1` | `-1` = follow `cmp_auto`. `0` = cap to 64/40 GiB. `1` = size VRAM dynamically from active coherent FBPs (`80/96 GiB` on glitched 8GB cards, `48 GiB` on 12-FBP 10GB cards). |
| `cmp_unlock_sm=-1\|0\|1\|2` | `-1` | `-1` = follow `cmp_auto`. `0` = off. `1` = volatile defect-preserving SW-IFF + single-shot FLR on `DSOV=0` cards (bare metal). `2` = SW-IFF when PLMs are open, else late TPC-only override inside already-awake GPCs (~80 SMs, VM fallback). |
| `cmp_max_pcie_gen=-1\|2\|3\|4` | `-1` | `-1` = follow `cmp_auto` (`2` conservative, `4` auto). Caps per-card PCIe target by card fuses and host root-port `LnkCap`. |
| `cmp_pcie_retrain=0\|1` | `1` | `1` = automatic staged single-shot link retrain (`Gen1 -> 2 -> 3 [-> 4]`) during init. `0` = apply PHY init only (manual retrain). |
| `cmp_bar1_gb=0\|64\|128` | `0` | `0` = auto (`64 GiB` for &le;64 GiB VRAM, `128 GiB` for &gt;64 GiB VRAM). |
| `cmp_p2p=0\|1` | `1` | `1` = enable native PCIe mailbox P2P unlock (`0x0013affc` PLM + SYS decode trap 30 overriding `0x00821030`). `0` = disable. |
| `cmp_magicd_a100=0\|1` | `0` | `1` = also clear extra A100 parity bits (`0x14480000`) in `PCIE_MAGIC_BITS_D` during volatile Gen4 override. |
| `cmp_bdf=""` | `""` | Optional comma-separated PCI BDF filter (e.g. `0000:01:00.0`) limiting advanced options to specific GPUs. |

### Native PCIe P2P

Native PCIe mailbox P2P (ported from [Zagitta/gpu-unlock](https://github.com/Zagitta/gpu-unlock) 3.0 and validated on 64/80 GiB CMP 170HX hosts in [satspace-cpu/cmp170hx-linux-p2p](https://github.com/satspace-cpu/cmp170hx-linux-p2p)) is enabled by default (`cmp_p2p=1`). During GSP boot, the SEC2 Booter opens the P2P mailbox PLM (`0x0013affc`) and configures SYS PRI decode trap 30 (`0x00122478`–`0x00122778`) to override reads of the secure P2P disable option (`0x00821030`) to `0`, disarming trap 30 automatically if the readback check fails. It works with both 40/64 GiB and 80/96 GiB cards without Static BAR1 (`RMForceStaticBar1` / `RMPcieP2PType` are **not** required and should not be used with 80 GiB cards).

Check both directions after reboot:

```bash
sudo ./tools/check-p2p.sh
nvidia-smi topo -p2p r
nvidia-smi topo -p2p w
```

- **`OK`**: Native P2P is active. Verify actual peer data integrity (peer copies + SM remote loads/stores, e.g. `p2p-integrity`) and measure with `p2pBandwidthLatencyTest`.
- **`GNS`** (GPU not supported): Check `sudo dmesg | grep 'CMP P2P'` and verify `cmp_p2p=1`.
- **`CNS`** (Chipset not supported): The GPU side is unlocked, but NVIDIA's chipset allowlist does not recognize the motherboard. On platforms whose root complex actually routes peer traffic, pass `--force-p2p` to `install.sh` (or append `;ForceP2P=0x11` inside `NVreg_RegistryDwords` in `/etc/modprobe.d/cmp-pcie-gen2.conf`) and reboot. `ForceP2P=0x11` bypasses all driver P2P checks (enabling reads and writes while leaving atomics off), so only use it when all GPUs are P2P-unlocked and always run a content integrity test afterward.
- **IOMMU & ACS note:** P2P throughput and reachability depend on PCIe topology (same root complex / PCIe switch), ACS settings, and IOMMU mode (`iommu=pt` or `iommu=off` on bare metal).

### Install &amp; Configuration Examples

```bash
# 1. Conservative stock install (64GB/40GB, 74 SMs, Gen2, Native P2P — plain cards):
sudo ./install.sh

# 2. Auto-enable everything supported per card (mixed plain + RIR + glitched rigs):
sudo ./install.sh --auto

# 3. Auto-enable + ForceP2P=0x11 on CNS motherboards:
sudo ./install.sh --auto --force-p2p

# 4. Explicit fine-grained install:
sudo ./install.sh --unlock-vram --unlock-sm --pcie-gen=4
```

You can also change options anytime without rebuilding by editing `/etc/modprobe.d/cmp-pcie-gen2.conf` and rebooting:

```ini
# Auto-enable everything supported per GPU:
options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x15" cmp_auto=1

# Or target a specific GPU only (e.g. 0000:01:00.0 at Gen4 + SW-IFF SMs, leaving other GPUs stock):
options nvidia NVreg_RegistryDwords="RmForceEnableGen2=1;RMPcieLinkSpeed=0x15" cmp_unlock_sm=1 cmp_max_pcie_gen=4 cmp_bdf="0000:01:00.0"
```

### Verification

```bash
sudo ./verify.sh                           # Check unlocked VRAM, module options, dmesg, P2P, and PCIe link speed
sudo ./tools/check-p2p.sh                  # Read-only PCIe P2P, IOMMU, ACS, BAR1, and link speed diagnostics
sudo ./tools/service.sh verify             # Check authoritative live PCIe LnkSta speed & width per GPU
sudo ./tools/swiff-unlock.sh status        # Show active cmp_* module params, driver binding, and link speed
sudo dmesg | grep -E 'SEC2_DEBUG|CMP '     # Inspect geometry, SM-RECONFIG activeSMs, SW-IFF, BAR1, P2P, and PCIe logs
```

> **Note on PCIe Gen4 reporting:** `nvidia-smi` caches `LnkCap` from early boot and may display `Gen3` even when the link is trained at `16.0 GT/s`. Use `sudo ./tools/service.sh verify`, `sudo lspci -vv`, or `/sys/bus/pci/devices/<bdf>/current_link_speed` for the authoritative live link speed.

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
