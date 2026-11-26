#!/bin/bash
set -euo pipefail

say() { printf '%s\n' "$*"; }
section() { printf '\n==== %s ====\n' "$*"; }

section "System"
uname -a
printf 'cmdline: '
cat /proc/cmdline

section "CMP P2P module state"
if [[ -r /sys/module/nvidia/parameters/cmp_p2p ]]; then
    say "cmp_p2p = $(cat /sys/module/nvidia/parameters/cmp_p2p 2>/dev/null || echo '?')"
else
    say "cmp_p2p parameter not exposed (stock or older nvidia module?)"
fi
p2p_logs="$(dmesg 2>/dev/null | grep -E 'SEC2_DEBUG: (P2P\[|CMP P2P)' || true)"
if [[ -n "${p2p_logs}" ]]; then
    printf '%s\n' "${p2p_logs}" | tail -n 20
else
    say "No CMP P2P log lines in dmesg (may need root or logs may have rotated)"
fi

section "NVIDIA driver and GPUs"
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=index,name,memory.total,pci.bus_id,driver_version --format=csv
else
    say "nvidia-smi not found"
fi

section "PCIe link state for NVIDIA devices"
if command -v lspci >/dev/null 2>&1; then
    while read -r bdf; do
        [[ -n "${bdf}" ]] || continue
        say "-- ${bdf} --"
        lspci -vv -s "${bdf}" 2>/dev/null | grep -E 'LnkCap:|LnkSta:' || true
    done < <(lspci -Dnnd 10de: 2>/dev/null | awk '{print $1}')
else
    say "lspci not found (install pciutils)"
fi

section "IOMMU"
if grep -qE '(^| )(intel_iommu|amd_iommu)=off( |$)' /proc/cmdline; then
    say "Kernel command line: IOMMU disabled"
elif grep -qE '(^| )iommu=pt( |$)' /proc/cmdline; then
    say "Kernel command line: IOMMU passthrough (iommu=pt)"
else
    say "Kernel command line: default IOMMU mode"
fi
if [[ -d /sys/kernel/iommu_groups ]]; then
    groups="$(find /sys/kernel/iommu_groups -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)"
    say "Visible IOMMU groups: ${groups}"
else
    say "No /sys/kernel/iommu_groups directory"
fi

section "NVIDIA P2P topology"
if command -v nvidia-smi >/dev/null 2>&1; then
    say "-- matrix --"
    nvidia-smi topo -m 2>&1 || true
    say "-- read --"
    nvidia-smi topo -p2p r 2>&1 || true
    say "-- write --"
    nvidia-smi topo -p2p w 2>&1 || true
    say "-- PCIe atomics --"
    nvidia-smi topo -p2p p 2>&1 || true
fi

section "ACS controls"
if command -v lspci >/dev/null 2>&1; then
    while read -r bdf; do
        [[ -n "${bdf}" ]] || continue
        out="$(lspci -vv -s "${bdf}" 2>/dev/null | grep -E 'ACSCap:|ACSCtl:' || true)"
        if [[ -n "${out}" ]]; then
            say "-- ${bdf} --"
            printf '%s\n' "${out}"
        fi
    done < <(lspci -D 2>/dev/null | awk '{print $1}')
fi

section "BAR1"
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi -q 2>/dev/null | grep -i -A4 -B2 'BAR1 Memory Usage' || true
fi

section "Next step"
say "1. If 'nvidia-smi topo -p2p r/w' reports CNS (Chipset Not Supported), append ';ForceP2P=0x11'"
say "   to NVreg_RegistryDwords (or run 'sudo ./install.sh --force-p2p') and reboot."
say "2. Verify actual peer data integrity (cudaMemcpyPeer + SM remote read/write, e.g. p2p-integrity)"
say "   and bandwidth/latency with NVIDIA p2pBandwidthLatencyTest."
say "3. Check 'dmesg | grep -iE \"Xid|AER\"' after testing. This script is read-only."
