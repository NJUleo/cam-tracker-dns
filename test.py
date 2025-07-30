import subprocess

if __name__ == "__main__":
    result = subprocess.run([
        'arp-scan',
        '--interface', "eth0",
        '--retry=3',
        '--quiet',
        "10.1.1.0/24"
    ], capture_output=True, text=True, check=True)
    print(result)