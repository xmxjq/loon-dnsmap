#!/usr/bin/env python3
"""Convert dnsmasq-china-list accelerated domains to a Loon plugin."""

from __future__ import annotations

import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SOURCE_URL = os.environ.get(
    "SOURCE_URL",
    "https://raw.githubusercontent.com/felixonmars/dnsmasq-china-list/master/accelerated-domains.china.conf",
)
DOH_SERVER = os.environ.get("DOH_SERVER", "https://223.5.5.5/dns-query")
OUTPUT_FILE = Path(os.environ.get("OUTPUT_FILE", "CN-DNS-Alidns.plugin"))

DOMAIN_RE = re.compile(r"^server=/([^/]+)/")


def fetch_source(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8", errors="ignore")


def extract_domains(raw: str) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = DOMAIN_RE.match(line)
        if not match:
            continue

        domain = match.group(1).strip().lower().rstrip(".")
        if "." not in domain or domain in seen:
            continue

        seen.add(domain)
        domains.append(domain)

    return domains


def build_plugin(domains: list[str], source_url: str, doh_server: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "#!name=CN Domains DNS over AliDNS",
        "#!desc=Use AliDNS DoH for domains from felixonmars/dnsmasq-china-list accelerated-domains.china.conf",
        f"#!source={source_url}",
        f"#!doh={doh_server}",
        f"#!domains={len(domains)}",
        f"#!updated={now}",
        "",
        "[Host]",
    ]

    for domain in domains:
        lines.append(f"{domain} = server:{doh_server}")
        lines.append(f"*.{domain} = server:{doh_server}")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    raw = fetch_source(SOURCE_URL)
    domains = extract_domains(raw)
    if not domains:
        print("No domains parsed from source.", file=sys.stderr)
        return 1

    OUTPUT_FILE.write_text(
        build_plugin(domains, SOURCE_URL, DOH_SERVER),
        encoding="utf-8",
    )
    print(
        f"Generated {OUTPUT_FILE}: domains={len(domains)}, host_lines={len(domains) * 2}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
