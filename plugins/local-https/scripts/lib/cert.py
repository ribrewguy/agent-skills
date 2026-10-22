#!/usr/bin/env python3
"""cert.py — expected SAN list, and SANs/expiry of an existing cert.

    python3 cert.py <cert.pem> <expected-sans-csv>

Prints shell-consumable lines:
    missing=<comma-separated expected SANs absent from the cert>
    sans=<comma-separated SANs the cert carries; names outside
          [A-Za-z0-9.*:-] are dropped, never printed>
    not_after=<YYYY-MM-DD>
    days_left=<int>
Exit 2 when openssl cannot read the cert.
"""
import ipaddress
import re
import subprocess
import sys
from datetime import datetime, timezone

LOOPBACK = ["localhost", "127.0.0.1", "::1"]
SAFE_SAN_RE = re.compile(r"[A-Za-z0-9.*:-]+")


def expected_sans(host, subdomains, extra_names):
    """Exact SAN list: host, wildcard, each subdomain, loopback, extras."""
    names = [host, f"*.{host}"]
    names += [f"{sub}.{host}" for sub in subdomains]
    names += LOOPBACK + list(extra_names)
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _canon(name):
    """Normalize IPs so 0:0:0:0:0:0:0:1 and ::1 compare equal."""
    try:
        return str(ipaddress.ip_address(name))
    except ValueError:
        return name.lower()


def parse_sans(x509_text):
    """SANs from `openssl x509 -noout -text` output."""
    lines = x509_text.splitlines()
    for i, line in enumerate(lines):
        if "Subject Alternative Name" in line and i + 1 < len(lines):
            out = []
            for entry in lines[i + 1].split(","):
                _, _, value = entry.strip().partition(":")
                out.append(value.strip())
            return out
    return []


def parse_not_after(enddate_line):
    """datetime from `notAfter=Jan 22 11:15:06 2029 GMT`."""
    stamp = enddate_line.strip().split("=", 1)[1]
    return datetime.strptime(stamp, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)


def _openssl(pem, *args):
    return subprocess.run(["openssl", "x509", "-in", pem, "-noout", *args],
                          check=True, capture_output=True, text=True).stdout


def main(argv):
    pem, expected_csv = argv[1], argv[2]
    try:
        text = _openssl(pem, "-text")
        enddate = _openssl(pem, "-enddate")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"cert.py: cannot read {pem}: {e}", file=sys.stderr)
        return 2
    sans = parse_sans(text)
    have = {_canon(n) for n in sans}
    expected = [n for n in expected_csv.split(",") if n]
    missing = [n for n in expected if _canon(n) not in have]
    not_after = parse_not_after(enddate)
    days_left = (not_after - datetime.now(timezone.utc)).days
    print(f"missing={','.join(missing)}")
    print(f"sans={','.join(_canon(n) for n in sans if SAFE_SAN_RE.fullmatch(n))}")
    print(f"not_after={not_after.date().isoformat()}")
    print(f"days_left={days_left}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
