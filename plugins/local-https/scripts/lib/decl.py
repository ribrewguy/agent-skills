#!/usr/bin/env python3
"""decl.py — read, validate, derive and write .local-https.json.

    python3 decl.py <repo-root> [--server <dir>] [--write]

Prints shell-consumable key=value lines:
    declared=0|1      whether .local-https.json exists (before --write)
    project=, host=, server_dir=, server_https=true|false, server_reason=,
    sans=<comma-separated>, subdomains=<comma-separated>
Without a declaration, project and host are derived from the repo directory
name. --write creates the declaration when absent, listing --server.
Validation errors print `INVALID <field>: <why>` and exit 3.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cert import expected_sans  # noqa: E402

DECL_NAME = ".local-https.json"

# Suffix -> why it is forbidden as a local dev hostname.
FORBIDDEN_SUFFIXES = {
    ".local": "is reserved for mDNS (multicast DNS); lookups stall or bypass /etc/hosts",
    ".localhost": "is resolved to loopback by browsers without consulting /etc/hosts",
    ".dev": "is a real TLD on the HSTS preload list",
    ".app": "is a real TLD on the HSTS preload list",
}


class Invalid(Exception):
    def __init__(self, field, why):
        super().__init__(f"{field}: {why}")
        self.field, self.why = field, why


def derive_project(repo_root):
    name = os.path.basename(os.path.normpath(repo_root)).lower()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def _string_list(value, field):
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise Invalid(field, "must be a list of non-empty strings")
    return value


def validate(decl):
    if not isinstance(decl, dict):
        raise Invalid("declaration", "must be a JSON object")
    for key in ("project", "host"):
        if not isinstance(decl.get(key), str) or not decl[key]:
            raise Invalid(key, "must be a non-empty string")
    host = decl["host"].lower()
    for suffix, why in FORBIDDEN_SUFFIXES.items():
        if host.endswith(suffix):
            raise Invalid("host", f"{decl['host']} uses {suffix}, which {why}; "
                                  f"use {decl['project']}-local or {decl['project']}.test")
    servers = decl.get("servers", [])
    if not isinstance(servers, list):
        raise Invalid("servers", "must be a list")
    for i, s in enumerate(servers):
        where = f"servers[{i}]"
        if not isinstance(s, dict) or not isinstance(s.get("dir"), str) or not s["dir"]:
            raise Invalid(f"{where}.dir", "each server needs a non-empty dir")
        if "https" in s and not isinstance(s["https"], bool):
            raise Invalid(f"{where}.https", "must be true or false")
        if s.get("https") is False and not (isinstance(s.get("reason"), str) and s["reason"].strip()):
            raise Invalid(f"{where}.reason", f"{s['dir']} sets https:false without a reason")
        if "subdomain" in s:
            _string_list([s["subdomain"]], f"{where}.subdomain")
        _string_list(s.get("subdomains", []), f"{where}.subdomains")
    _string_list(decl.get("extraNames", []), "extraNames")


def subdomains_of(decl):
    out = []
    for s in decl.get("servers", []):
        for sub in ([s["subdomain"]] if "subdomain" in s else []) + s.get("subdomains", []):
            if sub not in out:
                out.append(sub)
    return out


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    repo_root, server_dir, write = args[0], None, False
    rest = args[1:]
    while rest:
        arg = rest.pop(0)
        if arg == "--server" and rest:
            server_dir = os.path.normpath(rest.pop(0))
        elif arg == "--write":
            write = True
        else:
            print(f"decl.py: unknown argument {arg}", file=sys.stderr)
            return 2

    path = os.path.join(repo_root, DECL_NAME)
    declared = os.path.isfile(path)
    if declared:
        try:
            with open(path) as f:
                decl = json.load(f)
        except json.JSONDecodeError as e:
            print(f"INVALID {DECL_NAME}: not valid JSON ({e})")
            return 3
    else:
        project = derive_project(repo_root)
        decl = {"project": project, "host": f"{project}-local",
                "servers": [{"dir": server_dir}] if server_dir else [], "extraNames": []}
    try:
        validate(decl)
    except Invalid as e:
        print(f"INVALID {e.field}: {e.why}")
        return 3

    if write and not declared:
        with open(path, "w") as f:
            json.dump(decl, f, indent=2)
            f.write("\n")

    server = next((s for s in decl.get("servers", [])
                   if os.path.normpath(s["dir"]) == server_dir), {}) if server_dir else {}
    subs = subdomains_of(decl)
    print(f"declared={int(declared)}")
    print(f"project={decl['project']}")
    print(f"host={decl['host']}")
    print(f"server_dir={server_dir or ''}")
    print(f"server_https={'false' if server.get('https') is False else 'true'}")
    print(f"server_reason={' '.join(server.get('reason', '').split())}")
    print(f"sans={','.join(expected_sans(decl['host'], subs, decl.get('extraNames', [])))}")
    print(f"subdomains={','.join(subs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
