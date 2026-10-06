#!/usr/bin/env bash
# Install the Tokyo Night GRUB theme: compiles the theme at native screen resolution and updates GRUB.
# Every step is reversible: if anything fails, /etc/default/grub and grub.cfg are restored.
set -o errexit -o nounset -o pipefail

# ----- CONFIGURATION & GLOBALS ---------------------------------------------- #

REPO_DIR="$(dirname "$(readlink -f "${0}")")"
THEME_NAME=tokyonight
SCREEN="" TYPE=window SIDE=left PHOTO="" LOGO=cachyos GRADE=soft REMOVE=false DRY_RUN=false
DESTDIR="${DESTDIR:-}" # prefix for packaging and testing: with DESTDIR, GRUB is not touched

# ----- HELPER FUNCTIONS ----------------------------------------------------- #

usage() {
  cat <<EOF2
Usage: sudo ./install.sh [OPTIONS]

  -s, --screen  1080p|1440p|1600p|4k     Resolution (default: detected, otherwise 1080p)
  -p, --type    window|float|sharp|blur  Style (default: window)
  -i, --side    left|right               Photo side (default: left)
  -f, --photo   NAME|FILE                Photo in backgrounds/ or path to an image
  -l, --logo    NAME|none                Logo in assets/logos/ (default: cachyos)
  -g, --grade   none|soft|full           Color grading towards palette (default: soft)
  -n, --dry-run                          Build and validate theme without modifying system
  -r, --remove                           Remove theme and restore GRUB
  -h, --help                             Show this help message
EOF2
}

die() {
  echo "Error: $*" >&2
  exit 1
}
in_list() {
  local v="${1}"
  shift
  for x in "$@"; do [[ "${x}" == "${v}" ]] && return 0; done
  return 1
}

detect_screen() {
  local st mode
  for st in /sys/class/drm/*/status; do
    [[ -r "${st}" && "$(cat "${st}")" == connected ]] || continue
    mode="$(head -n1 "$(dirname "${st}")/modes" 2>/dev/null || true)"
    case "${mode}" in
      1920x1080)
        echo 1080p
        return
        ;;
      2560x1440)
        echo 1440p
        return
        ;;
      2560x1600)
        echo 1600p
        return
        ;;
      3840x2160)
        echo 4k
        return
        ;;
    esac
  done
  echo 1080p
}

# ----- ARGUMENT PARSING ----------------------------------------------------- #

while [[ $# -gt 0 ]]; do
  case "${1}" in
    -s | --screen)
      SCREEN="${2:?missing value for ${1}}"
      shift 2
      ;;
    -p | --type)
      TYPE="${2:?missing value for ${1}}"
      shift 2
      ;;
    -i | --side)
      SIDE="${2:?missing value for ${1}}"
      shift 2
      ;;
    -f | --photo)
      PHOTO="${2:?missing value for ${1}}"
      shift 2
      ;;
    -l | --logo)
      LOGO="${2:?missing value for ${1}}"
      shift 2
      ;;
    -g | --grade)
      GRADE="${2:?missing value for ${1}}"
      shift 2
      ;;
    -n | --dry-run)
      DRY_RUN=true
      shift
      ;;
    -r | --remove)
      REMOVE=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage
      die "unknown option: ${1}"
      ;;
  esac
done

# ----- PRE-FLIGHT VALIDATION ------------------------------------------------ #

[[ -z "${SCREEN}" ]] || in_list "${SCREEN}" 1080p 1440p 1600p 4k || die "invalid resolution: ${SCREEN}"
in_list "${TYPE}" window float sharp blur || die "invalid style: ${TYPE}"
in_list "${SIDE}" left right || die "invalid side: ${SIDE}"
in_list "${GRADE}" none soft full || die "invalid grade: ${GRADE}"
[[ "${LOGO}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "invalid logo name: ${LOGO}"
[[ "${REMOVE}" == false || "${DRY_RUN}" == false ]] || die "--remove and --dry-run cannot be combined."
if [[ -n "${DESTDIR}" ]]; then
  [[ "${DESTDIR}" == /* && "${DESTDIR}" != / ]] || die "DESTDIR must be an absolute staging directory, not /."
  DESTDIR="${DESTDIR%/}"
fi

if [[ -z "${DESTDIR}" && "${DRY_RUN}" == false ]]; then
  [[ "${EUID}" -eq 0 ]] || die "run as root (or use --dry-run)."
  [[ ! -e /etc/NIXOS ]] || die "on NixOS the theme is configured via the module (see README), not with this script."
fi

GRUB_BASE=/boot/grub
[[ -d "${DESTDIR}${GRUB_BASE}" || ! -d "${DESTDIR}/boot/grub2" ]] || GRUB_BASE=/boot/grub2
THEME_DIR="${GRUB_BASE}/themes/${THEME_NAME}"
GRUB_DEFAULT_FILE="${DESTDIR}/etc/default/grub"
MARKER=.tokyonight-theme

# ----- GRUB CONFIGURATION HELPERS ------------------------------------------- #

build_args() {
  BUILD_ARGS=(-s "${SCREEN}" -p "${TYPE}" -i "${SIDE}" -l "${LOGO}" -g "${GRADE}")
  [[ -z "${PHOTO}" ]] || BUILD_ARGS+=(-f "${PHOTO}")
}

set_option() { # set or add KEY=VALUE in /etc/default/grub
  if grep -q "^#\?${1}=" "${GRUB_DEFAULT_FILE}"; then
    sed -i "s|^#\?${1}=.*|${1}=${2}|" "${GRUB_DEFAULT_FILE}"
  else
    echo "${1}=${2}" >>"${GRUB_DEFAULT_FILE}"
  fi
}

# Regenerate grub.cfg in a temporary file and install it only if it contains (or does not contain) the expected theme.
regenerate_grub_cfg() {
  local want="${1}" mkconfig cfg="${DESTDIR}${GRUB_BASE}/grub.cfg" tmp
  mkconfig="$(command -v grub-mkconfig || command -v grub2-mkconfig)" || return 1
  tmp="$(mktemp "${cfg}.tmp.XXXXXX")" || return 1
  "${mkconfig}" -o "${tmp}" || {
    rm -f "${tmp}"
    return 1
  }
  [[ -s "${tmp}" ]] || {
    rm -f "${tmp}"
    echo "generated grub.cfg is empty" >&2
    return 1
  }
  if [[ "${want}" == present ]] && ! grep -q "themes/${THEME_NAME}/theme.txt" "${tmp}"; then
    rm -f "${tmp}"
    echo "generated grub.cfg does not contain the theme" >&2
    return 1
  fi
  if [[ "${want}" == absent ]] && grep -q "themes/${THEME_NAME}/theme.txt" "${tmp}"; then
    rm -f "${tmp}"
    echo "generated grub.cfg still references the removed theme" >&2
    return 1
  fi
  local checker
  checker="$(command -v grub-script-check || command -v grub2-script-check || true)"
  if [[ -n "${checker}" ]] && ! "${checker}" "${tmp}"; then
    rm -f "${tmp}"
    return 1
  fi
  if [[ -f "${cfg}" ]]; then
    if [[ ! -f "${cfg}.pre-${THEME_NAME}" ]] && ! cp -a "${cfg}" "${cfg}.pre-${THEME_NAME}"; then
      rm -f "${tmp}"
      return 1
    fi
    chmod --reference="${cfg}" "${tmp}" || { rm -f "${tmp}"; return 1; }
  else
    chmod 600 "${tmp}" || { rm -f "${tmp}"; return 1; }
  fi
  # Same-filesystem rename leaves the previous file intact if the commit fails.
  mv -f "${tmp}" "${cfg}" || { rm -f "${tmp}"; return 1; }
  rm -f "${tmp}"
}

# ----- INSTANCE LOCK -------------------------------------------------------- #

lock_instance() {
  local lock_dir="${DESTDIR}/run/grub-${THEME_NAME}"
  mkdir -p "${DESTDIR}/run"
  [[ -d "${lock_dir}" ]] || mkdir -m 700 "${lock_dir}"
  [[ ! -L "${lock_dir}" && -O "${lock_dir}" ]] || die "unsafe lock directory: ${lock_dir}"
  chmod 700 "${lock_dir}"
  [[ ! -L "${lock_dir}/install.lock" ]] || die "lock file is a symlink: refusing to open it."
  exec 9>"${lock_dir}/install.lock"
  flock -n 9 || die "another instance is already running."
}

# ----- TRANSACTION CLEANUP -------------------------------------------------- #

WORK="" CONFIG_CHANGED=false THEME_CHANGED=false COMMITTED=false
cleanup() {
  local status=$? rollback_failed=false
  trap - EXIT
  if [[ -n "${WORK}" ]]; then
    if [[ "${COMMITTED}" == false ]]; then
      if "${CONFIG_CHANGED}"; then
        cp -a "${WORK}/grub-default" "${GRUB_DEFAULT_FILE}" || { status=1; rollback_failed=true; }
      fi
      if "${THEME_CHANGED}" || [[ -d "${WORK}/previous-theme" ]]; then
        rm -rf "${DESTDIR}${THEME_DIR}" || { status=1; rollback_failed=true; }
        if [[ -d "${WORK}/previous-theme" ]]; then
          mv "${WORK}/previous-theme" "${DESTDIR}${THEME_DIR}" || { status=1; rollback_failed=true; }
        fi
      fi
    fi
    if "${rollback_failed}" || [[ -d "${WORK}/previous-theme" && "${COMMITTED}" == false ]]; then
      echo "Rollback incomplete; recovery files retained in ${WORK}" >&2
      status=1
    else
      rm -rf "${WORK}"
    fi
  fi
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

start_transaction() {
  [[ ! -L "${DESTDIR}${THEME_DIR}" ]] || die "${THEME_DIR} is a symlink: refusing to modify it."
  if [[ -e "${DESTDIR}${THEME_DIR}" && ! -f "${DESTDIR}${THEME_DIR}/${MARKER}" ]]; then
    die "${THEME_DIR} was not created by this script: refusing to modify it."
  fi
  mkdir -p "${DESTDIR}${THEME_DIR%/*}"
  WORK="$(mktemp -d "${DESTDIR}${THEME_DIR%/*}/.tokyonight-install.XXXXXX")"
  cp -a "${GRUB_DEFAULT_FILE}" "${WORK}/grub-default"
}

# ----- THEME REMOVAL -------------------------------------------------------- #

if "${REMOVE}"; then
  lock_instance
  [[ -f "${GRUB_DEFAULT_FILE}" ]] || die "${GRUB_DEFAULT_FILE} not found."
  start_transaction
  if [[ -d "${DESTDIR}${THEME_DIR}" ]]; then
    mv "${DESTDIR}${THEME_DIR}" "${WORK}/previous-theme"
    THEME_CHANGED=true
  fi
  CONFIG_CHANGED=true
  sed -i -E "\\|^[[:space:]]*GRUB_THEME=['\"]?${THEME_DIR}/theme[.]txt['\"]?([[:space:]]*(#.*)?)?$|s|^|#|" "${GRUB_DEFAULT_FILE}"
  if [[ -z "${DESTDIR}" ]] && ! regenerate_grub_cfg absent; then
    die "grub.cfg regeneration failed; restoring /etc/default/grub."
  fi
  COMMITTED=true
  echo "Theme removed. GRUB_GFXMODE and graphical terminal remain as configured."
  exit 0
fi

# ----- THEME BUILD & INSTALLATION ------------------------------------------- #

python3 -c 'import PIL' 2>/dev/null || die "Pillow is required (Arch/CachyOS: pacman -S python-pillow)."
[[ -n "${SCREEN}" ]] || SCREEN="$(detect_screen)"
build_args

if "${DRY_RUN}"; then
  check="$(mktemp -d "${TMPDIR:-/tmp}/tokyonight-check.XXXXXX")"
  trap 'rm -rf "${check}"' EXIT
  python3 "${REPO_DIR}/tools/build.py" "${check}/theme" "${BUILD_ARGS[@]}"
  echo "Dry run successful (${SCREEN}, ${TYPE}, ${SIDE}): valid theme, system unmodified."
  exit 0
fi

[[ -f "${GRUB_DEFAULT_FILE}" ]] || die "${GRUB_DEFAULT_FILE} not found."
lock_instance
echo "Building theme (${SCREEN}, ${TYPE}, ${SIDE}) in ${THEME_DIR}"
start_transaction
python3 "${REPO_DIR}/tools/build.py" "${WORK}/new-theme" "${BUILD_ARGS[@]}"
[[ -f "${GRUB_DEFAULT_FILE}.bak" ]] || cp -a "${GRUB_DEFAULT_FILE}" "${GRUB_DEFAULT_FILE}.bak"
if [[ -d "${DESTDIR}${THEME_DIR}" ]]; then
  mv "${DESTDIR}${THEME_DIR}" "${WORK}/previous-theme"
fi
THEME_CHANGED=true
mv "${WORK}/new-theme" "${DESTDIR}${THEME_DIR}"
CONFIG_CHANGED=true
set_option GRUB_THEME "\"${THEME_DIR}/theme.txt\""
case "${SCREEN}" in
  1080p) set_option GRUB_GFXMODE "1920x1080,auto" ;; 1440p) set_option GRUB_GFXMODE "2560x1440,auto" ;;
  1600p) set_option GRUB_GFXMODE "2560x1600,auto" ;; 4k) set_option GRUB_GFXMODE "3840x2160,auto" ;;
esac
# The theme requires a graphical terminal
sed -i -E 's|^GRUB_TERMINAL(_OUTPUT)?="?console"?|#&|' "${GRUB_DEFAULT_FILE}"

if [[ -z "${DESTDIR}" ]] && ! regenerate_grub_cfg present; then
  die "GRUB update failed; restoring defaults and previous theme, grub.cfg unchanged."
fi
COMMITTED=true
echo "Done: theme will appear on next reboot. To revert: sudo ./install.sh --remove"
