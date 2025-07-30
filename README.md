# Camera Hostname Resolution with dnsmasq on Raspberry Pi

This README documents how to configure a Raspberry Pi to resolve camera hostnames using `dnsmasq`, including DNS forwarding fallback and protection against changes to `/etc/resolv.conf`.

---

## 1. Files Created and Modified

### `/etc/dnsmasq.conf`

```conf
conf-dir=/etc/dnsmasq.d
```

### `/etc/dnsmasq.d/cam-tracker.conf`

```conf
port=53
# Prevent dnsmasq from acting as a DHCP server
no-dhcp-interface=*

# Load extra host mappings from cam-tracker
addn-hosts=/etc/dnsmasq.cam.hosts

# Prevent forwarding incomplete queries
domain-needed

# Optional: If using .local
# local=/local/
```

### `/etc/dnsmasq.cam.hosts`

```hosts
10.1.1.136 garage-cam.home
10.1.1.138 front-cam.home
```

### `/etc/resolv.conf`

```conf
nameserver 127.0.0.1
nameserver 75.75.75.75
nameserver 75.75.76.76
nameserver 8.8.8.8
```

* Protected from being overwritten with:

```bash
sudo chattr +i /etc/resolv.conf
```

---

## 2. Permissions

```bash
sudo chmod 644 /etc/dnsmasq.cam.hosts
```

---

## 3. Masking Default dnsmasq

To prevent a preexisting instance from conflicting:

```bash
sudo systemctl mask dnsmasq.service
```

To reverse:

```bash
sudo systemctl unmask dnsmasq.service
```

---

## 4. Testing

### Resolve hostname:

```bash
dig garage-cam.home @127.0.0.1 +short
```

### Ping:

```bash
ping garage-cam.home
```

### FFmpeg Test:

```bash
ffmpeg -y -rtsp_transport tcp -i 'rtsp://admin:admin@garage-cam.home:554/cam/realmonitor?channel=1&subtype=0' -frames:v 1 snapshot_test.jpg
```

---

## 5. Service Restart

After changes:

```bash
sudo systemctl restart dnsmasq
```

Check status:

```bash
sudo systemctl status dnsmasq
```

---

## 6. Notes

* Only your Raspberry Pi is using this DNS config.
* `dnsmasq` will check your host entries first and forward unresolved requests to the fallback nameservers.
* The `.home` domain is used to avoid `.local` mDNS conflicts.

---

## Future Automation

If integrating with a Python script that updates `/etc/dnsmasq.cam.hosts`, you must:

1. Update the file.
2. Restart dnsmasq.
3. Optionally validate with `dig`.
# cam-tracker-dns
