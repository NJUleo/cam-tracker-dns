import os
import json
import time
import logging
import subprocess
import threading
from pathlib import Path
from ipaddress import ip_network
from datetime import datetime

import socket
import fcntl
import struct

CONFIG_FILE = "/home/pi/dns/configs/config.json"
DNSMASQ_HOSTS_FILE = "/etc/dnsmasq.cam.hosts"
CHECK_INTERVAL = 60  # seconds
failure_counts = {} # for failure exponential backoff

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def load_config():
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    return config['mappings'], config['subnet'], config['interface']

def get_mac_from_ip(ip):
    try:
        pid = subprocess.run(['arp', '-n', ip], capture_output=True, text=True, check=True)
        for line in pid.stdout.splitlines():
            if ip in line:
                return line.split()[2]
    except subprocess.CalledProcessError:
        return None

def run_arp_scan(subnet, interface):
    try:
        result = subprocess.run([
            'arp-scan',
            '--interface', interface,
            '--retry=3',
            '--quiet',
            subnet
        ], capture_output=True, text=True, check=True)

        mac_ip_map = {}
        for line in result.stdout.splitlines():
            parts = line.strip().split('\t')
            if len(parts) >= 2:
                ip, mac = parts[0], parts[1].upper()
                mac_ip_map[mac.lower()] = ip

        logging.info(f"ARP scan complete: found {len(mac_ip_map)} devices.")
        return mac_ip_map

    except subprocess.CalledProcessError as e:
        logging.error(f"arp-scan failed: {e}")
        return {}

# given mac -> ip, combine with mac -> host in config, update dnsmasq
def update_dnsmasq_hosts(mapping):
    with open(DNSMASQ_HOSTS_FILE, 'w') as f:
        for mac, ip in mapping.items():
            hostname = config_mac_to_host.get(mac)
            if hostname:
                f.write(f"{ip} {hostname}\n")

    subprocess.run(['systemctl', 'restart', 'dnsmasq'], check=False)
    logging.info("dnsmasq restarted with updated mappings.")

# read from dnsmasq host file(ip -> hostname), combine with config (mac -> hostname), return current (mac -> IP)
def read_dnsmasq_hosts():
    hostname_to_ip = {}

    try:
        with open(DNSMASQ_HOSTS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    ip, hostname = parts[0], parts[1]
                    hostname_to_ip[hostname] = ip
    except FileNotFoundError:
        logging.warning(f"{DNSMASQ_HOSTS_FILE} not found.")
        return {}
    except Exception as e:
        logging.error(f"Failed to read {DNSMASQ_HOSTS_FILE}: {e}")
        return {}

    # Now map MAC -> IP using config_mac_to_host
    mac_to_ip = {}
    for mac, hostname in config_mac_to_host.items():
        ip = hostname_to_ip.get(hostname)
        if ip:
            mac_to_ip[mac] = ip

    return mac_to_ip

# return true if changed
def verify_and_update():
    global failure_counts
    changes_detected = False
    current_mac_to_ip = read_dnsmasq_hosts()

    for mac, hostname in config_mac_to_host.items():
        current_ip = current_mac_to_ip.get(mac)
        reachable = ping(current_ip) if current_ip else False
        mac_now = get_mac_from_ip(current_ip) if reachable else None

        match = reachable and mac_now and mac_now.lower() == mac.lower()

        if match:
            failure_counts[mac] = 0  # reset
            continue

        # increment failure count
        failure_counts[mac] = failure_counts.get(mac, 0) + 1
        attempt = failure_counts[mac]

        # only scan on exponential backoff attempts
        if attempt in [1, 2, 4, 8, 16] or attempt % 16 == 0:
            logging.warning(f"Issue with {hostname} ({mac}), failure count = {attempt}. Running ARP scan.")
            changes_detected = True
            break
        else:
            logging.info(f"Issue with {hostname} ({mac}), failure count = {attempt}. Skipping scan for now.")

    if changes_detected:
        scan_and_update_dnsmasq_hosts()
        return True
    else:
        return False


def ping(ip):
    result = subprocess.run(['ping', '-c', '1', '-W', '1', ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0

# run arp scan and update dns for the hosts
def scan_and_update_dnsmasq_hosts():
    logging.info("Starting ARP scan...")
    scanned_map = run_arp_scan(config_subnet, config_interface)
    known_mac_to_ip = {}
    for mac, hostname in config_mac_to_host.items():
        ip = scanned_map.get(mac)
        if ip:
            known_mac_to_ip[mac] = ip
            logging.info(f"Discovered {hostname} at {ip}")
        else:
            logging.warning(f"MAC {mac} ({hostname}) not found in ARP scan.")
    update_dnsmasq_hosts(known_mac_to_ip)

def tracker_loop():
    count = 10
    while True:
        changed = verify_and_update()
        if not changed:
            count -= 1
            if count <= 0:
                logging.info("No changes detected in the last 10 intervals.")
                count = 10
        else:
            count = 10
        
        time.sleep(CHECK_INTERVAL)

def main():
    global config_mac_to_host, config_subnet, config_interface
    config_mac_to_host, config_subnet, config_interface = load_config()

    thread = threading.Thread(target=tracker_loop, daemon=True)
    thread.start()
    thread.join()

if __name__ == "__main__":
    try:
        logging.info("starting camera IP tracker.")
        main()
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
