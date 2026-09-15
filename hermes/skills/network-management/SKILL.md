---
name: network-management
description: WiFi, ethernet, VPN, internet status, no connection
triggers: wifi, wi-fi, internet, network, connect, vpn, ethernet, offline, no internet, вайфай, интернет, сеть, подключись, впн, нет интернета
---

# Network Management (Infiny OS / NetworkManager)

## Non-negotiable acceptance criteria
- Never invent network names or connection status — always run the actual command.
- Do not print or store WiFi passwords in memory. Use them only in the connect command.

## WiFi
- List networks: `nmcli -t -f SSID,SIGNAL,SECURITY device wifi list | head -20`
- Connect (open): `nmcli device wifi connect '<SSID>'`
- Connect (password): `nmcli device wifi connect '<SSID>' password '<password>'`
- Current connection: `nmcli -t -f NAME,DEVICE connection show --active`
- Disconnect: `nmcli device disconnect <iface>`

## Diagnose "no internet"
1. Default route present? `ip route get 1.1.1.1`
2. Interface up? `ip link`
3. DNS working? `getent hosts deb.debian.org`
4. WiFi associated? `nmcli device status`

If WiFi hardware is missing after boot, the firmware may not be loaded — check
`dmesg | grep -i firmware` and see the self-healing skill.

## VPN
- List VPN connections: `nmcli connection show | grep vpn`
- Up: `nmcli connection up '<name>'`
- Down: `nmcli connection down '<name>'`

## Output
State the network you connected to (or the problem found) in one line.
