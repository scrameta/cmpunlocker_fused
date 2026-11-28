#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
IFF_APPLY="${IFF_APPLY:-$(command -v iff_apply.py 2>/dev/null || true)}"
SERVICE_NAME="cmp-swiff.service"
SERVICE_SOURCE="${PROJECT_DIR}/systemd/${SERVICE_NAME}"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}"
BIN_TARGET="/usr/local/sbin/cmp-swiff-unlock"

if [[ -r "${PROJECT_DIR}/common/lib.sh" ]]; then
    # shellcheck source=../common/lib.sh
    source "${PROJECT_DIR}/common/lib.sh"
else
    info() { echo "[INFO] $*"; }
    ok()   { echo "[ OK ] $*"; }
    warn() { echo "[WARN] $*"; }
    err()  { echo "[FAIL] $*" >&2; }
    die()  { err "$*"; exit 1; }
    normalize_bus_id() { echo "$1"; }
fi

usage() {
    cat <<EOF
Usage: sudo $0 <command> [args...]

Commands:
  status                 Show CMP 170HX GPUs, module params, and link speeds
  inspect <bdf>          Read-only floorplan/defect/SW-IFF check (GPU must be unbound)
  arm <bdf> [--vram] [--flr]
                         Dynamically compute defect-preserving SW-IFF records and arm
                         via iff_apply.py (GPU must be unbound; --flr issues FLR after)
  undo <bdf> [--flr]     Disarm SW-IFF overlay (GPU must be unbound; --flr reverts now)
  rebind                 Rebind GPUs that logged closed cold-boot PLMs so nvidia.ko
                         arms SW-IFF + FLR automatically (used by ${SERVICE_NAME})
  pcie-settle            Re-initialise (open/close, no unbind) any GPU whose GSP-RM
                         booted before the probe-time Gen3/Gen4 retrain, so nvidia-smi
                         reports the real link generation (used by ${SERVICE_NAME})
  install-service        Install and enable ${SERVICE_NAME} for cold-boot SW-IFF
  remove-service         Disable and remove ${SERVICE_NAME}
EOF
}

require_root() {
    [[ "${EUID}" -eq 0 ]] || die "Run as root"
}

supported_gpus() {
    local id
    for id in 20c2 2082; do
        lspci -D -d "10de:${id}" 2>/dev/null | awk '{print $1}'
    done
}

read_modparam() {
    local name="$1"
    local path="/sys/module/nvidia/parameters/${name}"
    if [[ -r "${path}" ]]; then
        tr -d '\n' < "${path}"
    else
        echo "unset"
    fi
}

cmd_status() {
    local -a gpus=()
    local gpu dev speed width driver
    echo "Module parameters (/sys/module/nvidia/parameters):"
    for p in cmp_auto cmp_unlock_vram cmp_unlock_sm cmp_max_pcie_gen cmp_pcie_retrain cmp_bar1_gb cmp_p2p cmp_magicd_a100 cmp_p8_low_power cmp_p8_vbios cmp_hbm_governor cmp_p8_min_mhz cmp_hbm_idle_ms cmp_hbm_min_cycles cmp_bdf; do
        printf "  %-18s = %s\n" "${p}" "$(read_modparam "${p}")"
    done
    echo ""
    mapfile -t gpus < <(supported_gpus)
    if [[ ${#gpus[@]} -eq 0 ]]; then
        warn "No CMP 170HX GPUs found (10de:20c2 / 10de:2082)"
        return 0
    fi
    printf "%-16s %-8s %-10s %-14s %-6s\n" "BDF" "Device" "Driver" "Link Speed" "Width"
    for gpu in "${gpus[@]}"; do
        dev="$(cat "/sys/bus/pci/devices/${gpu}/device" 2>/dev/null || echo '?')"
        speed="$(cat "/sys/bus/pci/devices/${gpu}/current_link_speed" 2>/dev/null || echo '?')"
        width="$(cat "/sys/bus/pci/devices/${gpu}/current_link_width" 2>/dev/null || echo '?')"
        if [[ -L "/sys/bus/pci/devices/${gpu}/driver" ]]; then
            driver="$(basename "$(readlink -f "/sys/bus/pci/devices/${gpu}/driver")")"
        else
            driver="unbound"
        fi
        printf "%-16s %-8s %-10s %-14s x%-5s\n" "${gpu}" "${dev}" "${driver}" "${speed}" "${width}"
    done
}

check_unbound() {
    local bdf="$1"
    [[ -d "/sys/bus/pci/devices/${bdf}" ]] || die "PCI device ${bdf} not found"
    if [[ -L "/sys/bus/pci/devices/${bdf}/driver" ]]; then
        die "${bdf} is bound to $(basename "$(readlink -f "/sys/bus/pci/devices/${bdf}/driver")"); unbind first: echo ${bdf} > /sys/bus/pci/devices/${bdf}/driver/unbind"
    fi
}

compute_plan_py() {
    local bdf="$1"
    local mode="$2"
    local include_vram="$3"
    python3 - "${bdf}" "${mode}" "${include_vram}" <<'PY'
import mmap, os, struct, sys

bdf, mode, inc_vram = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
os.system("setpci -s %s COMMAND=0x0006 >/dev/null 2>&1" % bdf[5:])
p = "/sys/bus/pci/devices/%s/resource0" % bdf
fd = os.open(p, os.O_RDONLY | os.O_SYNC)
mm = mmap.mmap(fd, min(os.stat(p).st_size, 16 << 20), mmap.MAP_SHARED, mmap.PROT_READ)

def rd(off):
    return struct.unpack_from("<I", mm, off)[0]

def popcount(v):
    return bin(v).count("1")

try:
    boot0 = rd(0x0)
    if boot0 in (0, 0xFFFFFFFF) or (boot0 & 0xFFFF0000) == 0xBADF0000:
        sys.exit("BAR0 invalid PMC_BOOT_0=0x%08x" % boot0)

    dsov = rd(0x820084)
    en_sw = rd(0x820040)
    iff_rec = rd(0x820050)
    plm_e0 = rd(0x8200E0)
    plm_f4 = rd(0x8200F4)

    gpc_def = rd(0x8205C4) & 0xFF
    gpc_dis = rd(0x820350) & 0xFF
    pes_def = rd(0x820698) & 0xFFFFFF
    pes_dis = rd(0x820690) & 0xFFFFFF
    tpc_def_addrs = [0x8205C8, 0x820508, 0x82050C, 0x820514, 0x820564, 0x8205AC, 0x820B84, 0x820B80]
    tpc_def = [rd(a) & 0xFF for a in tpc_def_addrs]
    tpc_dis = [rd(0x820760 + 4 * g) & 0xFF for g in range(8)]

    fbp_def = rd(0x8205CC) & 0xFFF
    fbp_dis = rd(0x820364) & 0xFFF
    fbpa_def = rd(0x8205D0) & 0xFFFFFF
    fbio_def = rd(0x8205D4) & 0xFFFFFF
    l2_def = rd(0x8205E8) & 0xFFFFFF

    target_gpc = gpc_def
    target_pes = pes_def
    target_tpc = [0xFF] * 8
    sm_now = 0
    sm_target = 0
    for g in range(8):
        if (gpc_dis & (1 << g)) == 0:
            sm_now += 2 * (8 - popcount(tpc_dis[g]))
        if tpc_def[g] == 0xFF:
            target_gpc |= (1 << g)
        if target_gpc & (1 << g):
            target_pes |= (0x7 << (3 * g))
            target_tpc[g] = 0xFF
        else:
            target_tpc[g] = tpc_def[g]
            sm_target += 2 * (8 - popcount(target_tpc[g]))

    target_fbp = fbp_def
    target_fbpa = fbpa_def
    target_fbio = fbio_def
    target_l2 = l2_def
    for f in range(12):
        sub = 0x3 << (2 * f)
        if (target_fbp & (1 << f)) or (fbpa_def & sub) or (fbio_def & sub) or (l2_def & sub):
            target_fbp |= (1 << f)
            target_fbpa |= sub
            target_fbio |= sub
            target_l2 |= sub

    if mode == "inspect":
        print("BDF=%s  PMC_BOOT_0=0x%08x" % (bdf, boot0))
        print("  DSOV (0x820084)     = %u (%s)" % (dsov & 1, "LOCKED" if (dsov & 1) else "SW override ALLOWED"))
        print("  EN_SW_OVR (0x820040)= %u" % (en_sw & 1))
        print("  IFF_RECORD(0x820050)= 0x%08x (START=%u LAST=%u)" % (iff_rec, iff_rec & 0x1FF, (iff_rec >> 16) & 0x1FF))
        print("  PLM 0x8200E0/0xF4   = 0x%08x / 0x%08x (L0-open=%s)" % (
            plm_e0, plm_f4, "YES" if (((plm_e0 >> 4) & 1) and ((plm_f4 >> 4) & 1)) else "NO"))
        print("  GPC dis/def/target  = 0x%02x / 0x%02x / 0x%02x" % (gpc_dis, gpc_def, target_gpc))
        print("  PES dis/def/target  = 0x%06x / 0x%06x / 0x%06x" % (pes_dis, pes_def, target_pes))
        print("  TPC defective[0..7] = %s" % " ".join("0x%02x" % x for x in tpc_def))
        print("  FBP dis/def/target  = 0x%03x / 0x%03x / 0x%03x (%u -> %u active FBPs)" % (
            fbp_dis, fbp_def, target_fbp, 12 - popcount(fbp_dis), 12 - popcount(target_fbp)))
        print("  SMs (pre-RECONFIG)  = %u current -> %u defect-preserving target" % (sm_now, sm_target))
        print("  PCIe gen3/bgen3/mgD = %u / %u / 0x%08x (gen4_dis=%u)" % (
            rd(0x820250) & 1, rd(0x820580) & 1, rd(0x820520), (rd(0x820520) >> 25) & 1))
    elif mode == "records":
        if (dsov & 1) != 0:
            sys.exit("ABORT: DISABLE_SW_OVERRIDE_STATUS=1; SW-IFF requires RIR gate burn")
        recs = ["0x820350=0x%x" % target_gpc, "0x820690=0x%x" % target_pes]
        for g in range(8):
            if (target_gpc & (1 << g)) == 0:
                recs.append("0x%x=0x%x" % (0x820760 + 4 * g, target_tpc[g]))
        if inc_vram and (fbp_dis & ~target_fbp) != 0:
            recs.extend([
                "0x820364=0x%x" % target_fbp,
                "0x820368=0x%x" % target_fbpa,
                "0x82036c=0x%x" % target_fbio,
                "0x8202c4=0x%x" % target_l2,
            ])
        print(" ".join(recs))
finally:
    mm.close()
    os.close(fd)
PY
}

do_flr() {
    local bdf="$1"
    info "Issuing bare-metal FLR on ${bdf}..."
    if [[ -w "/sys/bus/pci/devices/${bdf}/reset_method" ]]; then
        echo flr > "/sys/bus/pci/devices/${bdf}/reset_method"
    fi
    echo 1 > "/sys/bus/pci/devices/${bdf}/reset"
    sleep 0.2
    ok "FLR complete on ${bdf}"
}

cmd_inspect() {
    require_root
    local bdf
    bdf="$(normalize_bus_id "${1:-}")"
    [[ -n "${bdf}" ]] || die "Usage: $0 inspect <bdf>"
    check_unbound "${bdf}"
    compute_plan_py "${bdf}" inspect 0
}

cmd_arm() {
    require_root
    local bdf=""
    local inc_vram=0
    local run_flr=0
    local arg
    for arg in "$@"; do
        case "${arg}" in
            --vram) inc_vram=1 ;;
            --flr)  run_flr=1 ;;
            *)
                if [[ -z "${bdf}" ]]; then
                    bdf="$(normalize_bus_id "${arg}")"
                else
                    die "Unknown argument: ${arg}"
                fi
                ;;
        esac
    done
    [[ -n "${bdf}" ]] || die "Usage: $0 arm <bdf> [--vram] [--flr]"
    [[ -n "${IFF_APPLY}" && -f "${IFF_APPLY}" ]] || die "iff_apply.py not found (install from https://github.com/scrameta/iff_apply and set IFF_APPLY=/path/to/iff_apply.py)"
    check_unbound "${bdf}"

    local recs_str
    recs_str="$(compute_plan_py "${bdf}" records "${inc_vram}")"
    info "Arming SW-IFF on ${bdf} (IFF_STOCK_FIRST=1): ${recs_str}"
    # shellcheck disable=SC2086
    IFF_STOCK_FIRST=1 python3 "${IFF_APPLY}" "${bdf}" install ${recs_str}
    if (( run_flr == 1 )); then
        do_flr "${bdf}"
        compute_plan_py "${bdf}" inspect 0
    else
        info "Now issue an FLR (reset_method=flr) and rebind the nvidia driver."
    fi
}

cmd_undo() {
    require_root
    local bdf=""
    local run_flr=0
    local arg
    for arg in "$@"; do
        case "${arg}" in
            --flr) run_flr=1 ;;
            *)
                if [[ -z "${bdf}" ]]; then
                    bdf="$(normalize_bus_id "${arg}")"
                else
                    die "Unknown argument: ${arg}"
                fi
                ;;
        esac
    done
    [[ -n "${bdf}" ]] || die "Usage: $0 undo <bdf> [--flr]"
    [[ -n "${IFF_APPLY}" && -f "${IFF_APPLY}" ]] || die "iff_apply.py not found (install from https://github.com/scrameta/iff_apply and set IFF_APPLY=/path/to/iff_apply.py)"
    check_unbound "${bdf}"
    python3 "${IFF_APPLY}" "${bdf}" undo
    if (( run_flr == 1 )); then
        do_flr "${bdf}"
    fi
}

cmd_rebind() {
    require_root
    local p_auto p_sm
    p_auto="$(read_modparam cmp_auto)"
    p_sm="$(read_modparam cmp_unlock_sm)"
    if [[ "${p_sm}" == "0" ]] || [[ "${p_sm}" != "1" && "${p_sm}" != "2" && "${p_auto}" != "1" ]]; then
        info "SW-IFF SM unlock disabled by kernel options (cmp_auto=${p_auto}, cmp_unlock_sm=${p_sm}); nothing to do"
        return 0
    fi

    # Wait briefly for initial nvidia probe/open to finish opening PLMs via SEC2 Booter.
    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi -L >/dev/null 2>&1 || true
    fi

    local -a targets=()
    mapfile -t targets < <(
        dmesg 2>/dev/null \
            | grep 'CMP SW-IFF: PLMs closed on cold boot' \
            | grep -oE '[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]' \
            | sort -u || true
    )

    if [[ ${#targets[@]} -eq 0 ]]; then
        info "No CMP 170HX GPU reported cold-boot closed PLMs needing SW-IFF rebind"
        return 0
    fi

    local bdf
    for bdf in "${targets[@]}"; do
        bdf="$(normalize_bus_id "${bdf}")"
        if [[ ! -L "/sys/bus/pci/devices/${bdf}/driver" ]]; then
            warn "${bdf} is not bound to nvidia; skipping"
            continue
        fi
        info "Rebinding ${bdf} so nvidia.ko arms SW-IFF + single-shot FLR with open PLMs..."
        echo "${bdf}" > /sys/bus/pci/drivers/nvidia/unbind
        sleep 0.5
        echo "${bdf}" > /sys/bus/pci/drivers/nvidia/bind
        ok "Rebound ${bdf}; triggering driver init..."
    done

    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi -L >/dev/null 2>&1 || true
    fi
}

# PCIe generation from sysfs current_link_speed ("16.0 GT/s PCIe" -> 4).
link_gen_from_sysfs() {
    local s
    s="$(cat "/sys/bus/pci/devices/$1/current_link_speed" 2>/dev/null || true)"
    case "${s%% *}" in
        2.5)    echo 1 ;;
        5|5.0)  echo 2 ;;
        8|8.0)  echo 3 ;;
        16|16.0) echo 4 ;;
        32|32.0) echo 5 ;;
        *)      echo 0 ;;
    esac
}

# Link generation as GSP-RM sees it. Without persistence, this open also
# initialises the GPU (GSP boot + post-GSP PHY sequence + probe-time retrain).
smi_gen_max() {
    local v
    v="$(nvidia-smi -i "$1" --query-gpu=pcie.link.gen.max --format=csv,noheader,nounits 2>/dev/null \
         | head -n1 | tr -d ' ')" || true
    if [[ "${v}" =~ ^[0-9]+$ ]]; then echo "${v}"; else echo 0; fi
}

# PIDs holding this GPU's /dev/nvidiaN open (empty if none / fuser missing).
gpu_holders() {
    local minor
    minor="$(awk -F: '/Device Minor/ {gsub(/[ \t]/, "", $2); print $2}' \
             "/proc/driver/nvidia/gpus/$1/information" 2>/dev/null || true)"
    [[ -n "${minor}" && -e "/dev/nvidia${minor}" ]] || return 0
    command -v fuser >/dev/null 2>&1 || return 0
    fuser "/dev/nvidia${minor}" 2>/dev/null | tr -s ' ' | sed 's/^ //' || true
}

cmd_pcie_settle() {
    require_root
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        info "nvidia-smi not found; skipping PCIe settle"
        return 0
    fi

    local -a gpus=()
    mapfile -t gpus < <(supported_gpus)
    mkdir -p /run/cmp-swiff

    local bdf drv smi link pm holders marker
    for bdf in "${gpus[@]}"; do
        drv="$(basename "$(readlink -f "/sys/bus/pci/devices/${bdf}/driver" 2>/dev/null)" 2>/dev/null || true)"
        [[ "${drv}" == "nvidia" ]] || continue

        # Per the driver: the Gen3/Gen4 retrain runs in nv_start_device() right
        # after rm_init_adapter(), i.e. after GSP-RM has already sampled the link.
        # GSP-RM only reports the real generation if it boots again afterwards.
        smi="$(smi_gen_max "${bdf}")"
        link="$(link_gen_from_sysfs "${bdf}")"
        if (( smi == 0 || link == 0 )); then
            warn "${bdf}: could not read link generation (nvidia-smi=${smi} sysfs=${link}); skipping"
            continue
        fi
        if (( smi >= link )); then
            ok "${bdf}: GSP-RM reports Gen${smi} max, link is Gen${link}; nothing to do"
            continue
        fi

        marker="/run/cmp-swiff/${bdf}.pcie-settled"
        if [[ -e "${marker}" ]]; then
            warn "${bdf}: already re-initialised once this boot and GSP-RM still reports Gen${smi} (link Gen${link}); not retrying"
            continue
        fi

        # Never unbind: nv_pci_remove() blocks forever while the GPU is in use.
        # A re-init only happens if nothing keeps the adapter alive.
        pm="$(nvidia-smi -i "${bdf}" --query-gpu=persistence_mode --format=csv,noheader 2>/dev/null \
              | head -n1 | tr -d ' ')" || true
        holders="$(gpu_holders "${bdf}")"
        if [[ "${pm}" == "Enabled" || -n "${holders}" ]]; then
            warn "${bdf}: GSP-RM reports Gen${smi} but link is Gen${link}; GPU is kept open (persistence=${pm:-?} pids=${holders:-none})."
            warn "${bdf}: stop nvidia-persistenced / those processes, run 'cmp-swiff-unlock pcie-settle', then restart them"
            continue
        fi

        touch "${marker}"
        info "${bdf}: GSP-RM booted before the Gen${link} retrain (reports Gen${smi}); re-initialising once"
        # Previous nvidia-smi closed the last handle -> adapter shut down; this
        # open boots GSP-RM again with the link already at Gen${link}.
        smi="$(smi_gen_max "${bdf}")"
        link="$(link_gen_from_sysfs "${bdf}")"
        if (( smi >= link )); then
            ok "${bdf}: GSP-RM now reports Gen${smi} max (link Gen${link})"
        else
            warn "${bdf}: GSP-RM still reports Gen${smi} max (link Gen${link}) after re-init"
        fi
    done
}

cmd_install_service() {
    require_root
    [[ -f "${SERVICE_SOURCE}" ]] || die "Missing ${SERVICE_SOURCE}"
    install -m 0755 "$0" "${BIN_TARGET}"
    install -m 0644 "${SERVICE_SOURCE}" "${SERVICE_TARGET}"
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}" >/dev/null
    ok "Installed and enabled ${SERVICE_NAME}"
}

cmd_remove_service() {
    require_root
    systemctl disable --now "${SERVICE_NAME}" 2>/dev/null || true
    rm -f "${SERVICE_TARGET}" "${BIN_TARGET}"
    systemctl daemon-reload
    systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true
    ok "Removed ${SERVICE_NAME}"
}

case "${1:-}" in
    status)          cmd_status ;;
    inspect)         shift; cmd_inspect "$@" ;;
    arm)             shift; cmd_arm "$@" ;;
    undo)            shift; cmd_undo "$@" ;;
    rebind)          cmd_rebind ;;
    pcie-settle)     cmd_pcie_settle ;;
    install-service) cmd_install_service ;;
    remove-service)  cmd_remove_service ;;
    -h|--help|"")    usage ;;
    *)               usage >&2; exit 1 ;;
esac
