#!/usr/bin/env python3
"""decl.py — read, validate, derive and write .local-https.json.

    python3 decl.py <repo-root> [--main-root <dir>] [--server <dir>] [--write]

Prints shell-consumable key=value lines:
    declared=0|1         whether .local-https.json exists (before --write)
    server_declared=0|1  whether --server is listed in it (before --write)
    project=, host=, server_dir=, server_https=true|false, server_reason=,
    sans=, subdomains=, host_names=   (lists are comma-separated)
    server=<dir>         one line per https server (key repeats; opted-out
                         servers are omitted)
host_names is <host> then <sub>.<host> per declared subdomain: the names
the hosts lines must carry.
Without a declaration, project and host are derived from the name of
--main-root (the main checkout, so linked worktrees agree), else repo-root.
--write creates the declaration when absent, or appends {"dir": <server>}
to servers when the declaration exists but does not list it.
Every value in the declaration is untrusted input (the file is tracked and
may come from a cloned repo): anything that is not a plain name is rejected
with `INVALID <field>: <why>`, exit 3, before any value is printed.
"""
import ipaddress
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


PROJECT_RE = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?")
NAME_RE = re.compile(r"[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?")
# ipaddress accepts IPv6 scope ids ("fe80::1%<anything>"), so only strings
# made of address characters may reach the parser.
IP_CHARS_RE = re.compile(r"[0-9A-Fa-f:.]+")


class Invalid(Exception):
    def __init__(self, field, why):
        super().__init__(f"{field}: {why}")
        self.field, self.why = field, why


def derive_project(repo_root):
    name = os.path.basename(os.path.normpath(repo_root)).lower()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def _is_ip(value):
    if not IP_CHARS_RE.fullmatch(value):
        return False
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return getattr(ip, "scope_id", None) is None


def _check_name(value, field, wildcard=False):
    """A DNS name (letters, digits, '.', '-'; no leading '-') or an IP."""
    if not isinstance(value, str):
        raise Invalid(field, "must be a string")
    bare = value[2:] if wildcard and value.startswith("*.") else value
    if not (NAME_RE.fullmatch(bare) or _is_ip(value)):
        raise Invalid(field, f"{value!r} is not a DNS name or IP address "
                             "(letters, digits, '.', '-' only; must not start with '-')")


def _name_list(value, field, wildcard=False):
    if not isinstance(value, list):
        raise Invalid(field, "must be a list")
    for i, v in enumerate(value):
        _check_name(v, f"{field}[{i}]", wildcard)
    return value


def _check_dir(value, field):
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise Invalid(field, "each server needs a non-empty single-line dir")
    if os.path.isabs(value) or ".." in value.replace("\\", "/").split("/"):
        raise Invalid(field, f"{value!r} must be a path inside the repo, relative to its root")


def validate(decl):
    if not isinstance(decl, dict):
        raise Invalid("declaration", "must be a JSON object")
    project = decl.get("project")
    if not isinstance(project, str) or not PROJECT_RE.fullmatch(project):
        raise Invalid("project", f"{project!r} must be lowercase letters, digits and '-', "
                                 "starting and ending with a letter or digit")
    _check_name(decl.get("host"), "host")
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
        if not isinstance(s, dict):
            raise Invalid(where, "each server must be an object")
        _check_dir(s.get("dir"), f"{where}.dir")
        if "https" in s and not isinstance(s["https"], bool):
            raise Invalid(f"{where}.https", "must be true or false")
        if s.get("https") is False and not (isinstance(s.get("reason"), str) and s["reason"].strip()):
            raise Invalid(f"{where}.reason", f"{s['dir']} sets https:false without a reason")
        if "subdomain" in s:
            _check_name(s["subdomain"], f"{where}.subdomain")
        _name_list(s.get("subdomains", []), f"{where}.subdomains")
        if "port" in s and (not isinstance(s["port"], int) or isinstance(s["port"], bool)
                            or not 1 <= s["port"] <= 65535):
            raise Invalid(f"{where}.port", "must be an integer 1-65535")
        launch = s.get("launch", [])
        if not isinstance(launch, list) or not all(isinstance(x, str) for x in launch):
            raise Invalid(f"{where}.launch", "must be a list of regex strings")
        for j, rx in enumerate(launch):
            try:
                re.compile(rx)
            except re.error as e:
                raise Invalid(f"{where}.launch[{j}]", f"not a valid regex ({e})")
    _name_list(decl.get("extraNames", []), "extraNames", wildcard=True)


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
    repo_root, main_root, server_dir, write = args[0], None, None, False
    rest = args[1:]
    while rest:
        arg = rest.pop(0)
        if arg == "--main-root" and rest:
            main_root = rest.pop(0)
        elif arg == "--server" and rest:
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
        project = derive_project(main_root or repo_root)
        decl = {"project": project, "host": f"{project}-local",
                "servers": [{"dir": server_dir}] if server_dir else [], "extraNames": []}
    try:
        validate(decl)
    except Invalid as e:
        print(f"INVALID {e.field}: {e.why}")
        return 3

    server = next((s for s in decl.get("servers", [])
                   if os.path.normpath(s["dir"]) == server_dir), None) if server_dir else None
    server_declared = declared and server is not None

    server = server or {}
    subs = subdomains_of(decl)
    host_names = [decl["host"]] + [f"{sub}.{decl['host']}" for sub in subs]
    facts = [
        ("declared", str(int(declared))),
        ("server_declared", str(int(server_declared))),
        ("project", decl["project"]),
        ("host", decl["host"]),
        ("server_dir", server_dir or ""),
        ("server_https", "false" if server.get("https") is False else "true"),
        ("server_reason", " ".join(server.get("reason", "").split())),
        ("sans", ",".join(expected_sans(decl["host"], subs, decl.get("extraNames", [])))),
        ("subdomains", ",".join(subs)),
        ("host_names", ",".join(host_names)),
    ]
    facts += [("server", os.path.normpath(s["dir"]))
              for s in decl.get("servers", []) if s.get("https") is not False]
    # Defence in depth for the key=value line protocol: no value may carry a
    # line break or '=', whatever validate() let through.
    for key, value in facts:
        if any(c in value for c in "\r\n="):
            print(f"INVALID {key}: {value!r} contains a line break or '='")
            return 3
    if write and server_dir and not server_declared:
        if declared:
            decl.setdefault("servers", []).append({"dir": server_dir})
        with open(path, "w") as f:
            json.dump(decl, f, indent=2)
            f.write("\n")

    for key, value in facts:
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
