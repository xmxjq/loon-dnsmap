#!/usr/bin/env python3
"""Convert China domain lists to a Loon Host DNS plugin."""

from __future__ import annotations

import os
import re
import sys
import tarfile
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path


SOURCE = os.environ.get("SOURCE", "v2fly-cn")
DLC_BASE_URL = os.environ.get(
    "DLC_BASE_URL",
    "https://raw.githubusercontent.com/v2fly/domain-list-community/master/data",
)
DLC_TARBALL_URL = os.environ.get(
    "DLC_TARBALL_URL",
    "https://codeload.github.com/v2fly/domain-list-community/tar.gz/refs/heads/master",
)
DNSMASQ_SOURCE_URL = os.environ.get(
    "DNSMASQ_SOURCE_URL",
    "https://raw.githubusercontent.com/felixonmars/dnsmasq-china-list/master/accelerated-domains.china.conf",
)
DOH_SERVER = os.environ.get("DOH_SERVER", "https://223.5.5.5/dns-query")
OUTPUT_FILE = Path(os.environ.get("OUTPUT_FILE", "CN-DNS-Alidns.plugin"))

DOMAIN_RE = re.compile(r"^server=/([^/]+)/")
DLC_DATA: dict[str, str] | None = None


@dataclass
class DomainRules:
    suffixes: set[str] = field(default_factory=set)
    exact: set[str] = field(default_factory=set)
    ignored: set[str] = field(default_factory=set)


def fetch_source(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8", errors="ignore")


def load_dlc_data() -> dict[str, str]:
    global DLC_DATA
    if DLC_DATA is not None:
        return DLC_DATA

    with urllib.request.urlopen(DLC_TARBALL_URL, timeout=120) as response:
        archive = response.read()

    data: dict[str, str] = {}
    with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            marker = "/data/"
            if marker not in member.name or not member.isfile():
                continue

            key = member.name.split(marker, 1)[1]
            extracted = tar.extractfile(member)
            if extracted is None:
                continue

            data[key] = extracted.read().decode("utf-8", errors="ignore")

    DLC_DATA = data
    return data


def parse_dnsmasq_domains(raw: str) -> DomainRules:
    rules = DomainRules()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = DOMAIN_RE.match(line)
        if not match:
            continue

        domain = normalize_domain(match.group(1))
        if "." not in domain:
            continue

        rules.suffixes.add(domain)

    return rules


def parse_v2fly_list(name: str, seen_lists: set[str] | None = None) -> DomainRules:
    seen_lists = seen_lists or set()
    if name in seen_lists:
        return DomainRules()
    seen_lists.add(name)

    try:
        raw = load_dlc_data()[name]
    except KeyError:
        raw = fetch_source(f"{DLC_BASE_URL.rstrip('/')}/{name}")
    rules = DomainRules()

    for original_line in raw.splitlines():
        line = original_line.split("#", 1)[0].strip()
        if not line:
            continue

        token = line.split()[0].strip()
        if not token:
            continue

        if token.startswith("include:"):
            child = parse_v2fly_list(token[len("include:") :], seen_lists)
            rules.suffixes.update(child.suffixes)
            rules.exact.update(child.exact)
            rules.ignored.update(child.ignored)
            continue

        if token.startswith("regexp:") or token.startswith("keyword:"):
            rules.ignored.add(token)
            continue

        is_exact = token.startswith("full:")
        if token.startswith(("full:", "domain:")):
            token = token.split(":", 1)[1]

        domain = normalize_domain(token)
        if not domain:
            continue

        if is_exact:
            rules.exact.add(domain)
        else:
            rules.suffixes.add(domain)

    return rules


def normalize_domain(value: str) -> str:
    return value.strip().lower().rstrip(".")


def remove_covered_suffixes(suffixes: set[str]) -> list[str]:
    sorted_suffixes = sorted(suffixes, key=lambda domain: (domain.count("."), domain))
    kept: list[str] = []
    kept_set: set[str] = set()

    for domain in sorted_suffixes:
        labels = domain.split(".")
        covered = False
        for index in range(1, len(labels)):
            if ".".join(labels[index:]) in kept_set:
                covered = True
                break
        if not covered:
            kept.append(domain)
            kept_set.add(domain)

    return kept


def load_rules() -> tuple[DomainRules, str]:
    if SOURCE == "v2fly-cn":
        return parse_v2fly_list("cn"), f"{DLC_BASE_URL.rstrip('/')}/cn"
    if SOURCE == "dnsmasq-china-list":
        return parse_dnsmasq_domains(fetch_source(DNSMASQ_SOURCE_URL)), DNSMASQ_SOURCE_URL

    print(
        "Unsupported SOURCE. Use SOURCE=v2fly-cn or SOURCE=dnsmasq-china-list.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def build_plugin(rules: DomainRules, source_url: str, doh_server: str) -> str:
    suffixes = remove_covered_suffixes(rules.suffixes)
    exact = sorted(rules.exact - rules.suffixes)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "#!name=CN Domains DNS over AliDNS",
        "#!desc=Use AliDNS DoH for China domains from v2fly/domain-list-community geosite:cn",
        f"#!source={source_url}",
        f"#!doh={doh_server}",
        f"#!suffix_rules={len(suffixes)}",
        f"#!exact_rules={len(exact)}",
        f"#!ignored_rules={len(rules.ignored)}",
        f"#!updated={now}",
        "",
        "[Host]",
    ]

    for domain in exact:
        lines.append(f"{domain} = server:{doh_server}")

    for domain in suffixes:
        if "." in domain:
            lines.append(f"{domain} = server:{doh_server}")
        lines.append(f"*.{domain} = server:{doh_server}")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    rules, source_url = load_rules()
    if not rules.suffixes and not rules.exact:
        print("No domains parsed from source.", file=sys.stderr)
        return 1

    OUTPUT_FILE.write_text(
        build_plugin(rules, source_url, DOH_SERVER),
        encoding="utf-8",
    )
    suffixes = remove_covered_suffixes(rules.suffixes)
    exact = sorted(rules.exact - rules.suffixes)
    host_lines = len(exact) + len(suffixes) + sum(1 for domain in suffixes if "." in domain)
    print(
        f"Generated {OUTPUT_FILE}: suffix_rules={len(suffixes)}, exact_rules={len(exact)}, "
        f"ignored_rules={len(rules.ignored)}, host_lines={host_lines}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
