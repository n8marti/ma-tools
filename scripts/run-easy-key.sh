#!/usr/bin/env bash

WINE_VERSION="11.21"

MA_DATA="$HOME/Insync/nate_marti@sil.org/Google Drive/SIL Documents/MissionAssist"
DEV="$HOME/dev"
MA_DEV="${DEV}/MissionAssist"
WINE_DEV="${DEV}/wine"
WINE_BIN_DIR="${WINE_DEV}/wine_${WINE_VERSION}+26.04/wine_${WINE_VERSION}/bin"
export LC_ALL=C.UTF-8
export PATH="$WINE_BIN_DIR:$PATH"
export XDG_CACHE_HOME="${WINE_DEV}/cache"
#export WINE="${WINE_DEV}/wine_${WINE_VERSION}+26.04/wine_${WINE_VERSION}/bin/wine"
export WINEDEBUG="${WINEDEBUG:-fixme-all}"
export WINEPREFIX="${MA_DEV}/wineprefix"
export WINETRICKS="${WINE_DEV}/winetricks"
export WINE_D3D_CONFIG="renderer=vulkan"
export WINEDLLOVERRIDES="winemenubuilder.exe=d;"
MA_DRIVE="${WINEPREFIX}/dosdevices/m:"
MA_PROGRAMS_DIR="${WINEPREFIX}/drive_c/Program Files (x86)/MissionAssist"
MA_ROAMING="${WINEPREFIX}/drive_c/users/${USER}/AppData/Roaming/MissionAssist"
EASYKEYDLMANAGER_URL="https://www.easy-key.info/installs/InstallFiles/Easy-KeyDownloadManager.msi"
EASYKEYDLMANAGER_MSI="${MA_DEV}/cache/Easy-KeyDownloadManager.msi"
SPEC_BACKUP_DIR="${MA_DEV}/cache/spec-backups"
EASYKEYDLMANAGER_DIR="${MA_PROGRAMS_DIR}/Easy-KeyDownloadManagerInstall"
EASYKEYDLMANAGER="${EASYKEYDLMANAGER_DIR}/Easy-KeyDownloadManager.exe"
EASYKEYEDIT_DIR="${MA_PROGRAMS_DIR}/Easy-KeyEdit4"
EASYKEYEDIT="${EASYKEYEDIT_DIR}/Easy-KeyEdit4.exe"
# For font linking.
LINK_KEY='HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontLink\SystemLink'
LINK_FONTS='CharisSIL-Regular.ttf,Charis SIL|DejaVuSans.ttf,DejaVu Sans'

## winetricks
# APT dependencies
# - cabextract
# source
# - https://raw.githubusercontent.com/Winetricks/winetricks/refs/tags/20260125/src/winetricks
# additions
# - dotnet48

# True if SystemLink value $1 exactly equals $2 (entries separated by '|')
fontlink_is_set() {
    local name=$1 want=$2 reg="${WINEPREFIX}/system.reg"
    [[ -f $reg ]] || return 1
    local got
    got=$(awk -v name="$name" '
        /^\[/ { insec = ($0 ~ /^\[Software\\\\Microsoft\\\\Windows NT\\\\CurrentVersion\\\\FontLink\\\\SystemLink\]/); next }
        insec && index($0, "\"" name "\"=hex(7):") == 1 { cap = 1 }
        cap { line = $0; sub(/^.*hex\(7\):/, "", line); gsub(/[ \\]/, "", line); buf = buf line
              if ($0 !~ /\\$/) { print buf; exit } }
    ' "$reg" | tr ',' '\n' | sed '/^$/d; s/^/\\x/' | tr -d '\n')
    [[ -n $got ]] || return 1
    got=$(printf '%b' "$got" | iconv -f UTF-16LE -t UTF-8 | tr '\0' '|' | sed 's/|*$//')
    [[ $got == "$want" ]]
}

write_setup_reg() {
    cat << 'EOF'
Windows Registry Editor Version 5.00

; --- Keyboard layout names (missing in Wine; Paratext crashes at KeyboardHelper.cs:123 without them)
[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Keyboard Layouts\00000409]
"Layout File"="KBDUS.DLL"
"Layout Text"="US"

[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Keyboard Layouts\00020409]
"Layout File"="KBDUSX.DLL"
"Layout Id"="0001"
"Layout Text"="United States-International"

[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Keyboard Layouts\00000809]
"Layout File"="KBDUK.DLL"
"Layout Text"="United Kingdom"

[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Keyboard Layouts\0000040c]
"Layout File"="KBDFR.DLL"
"Layout Text"="French"

[HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Keyboard Layouts\0000080c]
"Layout File"="KBDBE.DLL"
"Layout Text"="Belgian French"

; --- Do not start winedbg on crashes (it hangs and keeps Paratext.exe alive)
[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\AeDebug]
"Debugger"="false"

[HKEY_LOCAL_MACHINE\SOFTWARE\Wow6432Node\Microsoft\Windows NT\CurrentVersion\AeDebug]
"Debugger"="false"
EOF
}

ensure_setup() {
    # Ensure system has been initialized.
    if [[ ! -d ${WINEPREFIX}/drive_c ]]; then
	    WINEDLLOVERRIDES="mscoree=d;$WINEDLLOVERRIDES" wine wineboot -u
    fi
    # Ensure dotnet is installed.
    dotnet_hex=$(wine reg query "HKLM\Software\Microsoft\NET Framework Setup\NDP\v4\Full" /v Release 2>/dev/null | grep -i Release | grep -Eo "0x[0-9a-f]+")
    if (( ${dotnet_hex:-0} < 528040 )); then
	    "$WINETRICKS" -q dotnet48
    fi
    # Ensure Easy-KeyDownloadManager is installed.
    if [[ ! -x $EASYKEYDLMANAGER ]]; then
	    if [[ ! -f $EASYKEYDLMANAGER_MSI ]]; then
	        wget --directory-prefix="${MA_DEV}/cache" "$EASYKEYDLMANAGER_URL"
	    fi
	    # Ensure a valid MSI & not botcheck HTML.
	    if [[ -f $EASYKEYDLMANAGER_MSI ]] && file "$EASYKEYDLMANAGER_MSI" | grep -qi html; then
            echo "MSI download is an HTML page (likely a bot check); fetch it in a browser." >&2
            rm -f "$EASYKEYDLMANAGER_MSI"
            exit 1
        fi
	    wine msiexec /i "$EASYKEYDLMANAGER_MSI"
    fi
    # Ensure MissionAssist folder access.
    if [[ ! -L $MA_DRIVE ]]; then
        ln -s "$MA_DATA" "$MA_DRIVE"
    fi
    # Ensure font links are made for missing characters.
    for font in Tahoma Arial; do
        if ! fontlink_is_set "$font" "$LINK_FONTS"; then
            echo "Setting font fallback for $font"
            wine reg add "$LINK_KEY" /v "$font" /t REG_MULTI_SZ /d "${LINK_FONTS//|/\\0}" /f
        fi
    done
    local reg="${WINEPREFIX}/setup.reg"
    write_setup_reg > "$reg"
    wine reg import "$(winepath -w "$reg" 2>/dev/null)"
    # Ensure desktop launcher files.
    cp -u "${MA_DEV}/cache/"*.desktop $HOME/.local/share/applications
}

run_download_manager() {
  ensure_setup
  wine "$EASYKEYDLMANAGER"
}

run_editor() {
  ensure_setup
  wine "$EASYKEYEDIT"
}

# Only accept first argument as a command.
help="Supported commands: clean|dl|download|downloads|edit|edit4|editor|winetricks|wine/bin/*"
cmd="$1"
if [[ -z $cmd ]]; then
  run_download_manager
  exit $?
elif [[ $cmd == -h ]] || [[ $cmd == -help ]]; then
  echo "$help"
  exit 0
fi
shift

case $cmd in
  clean)
    rm -rf "${WINEPREFIX:?}"
    exit 0
    ;;
  dl|download|downloads)
    run_download_manager
    ;;
  edit|edit4|editor)
    run_editor
    ;;
  setup)
    ensure_setup
    ;;
  winetricks)
    "$WINETRICKS" "$@"
    ;;
  *)
    # Run cmd in wine env.
    "$cmd" "$@"
  	;;
esac
