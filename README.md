# loon-dnsmap

把 [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community) 的 `geosite:cn` 转换成 Loon 可导入的 `[Host]` DNS 映射规则，并将命中的国内域名交给 AliDNS DoH 解析：

```text
https://223.5.5.5/dns-query
```

生成后的插件文件是：

```text
CN-DNS-Alidns.plugin
```

## Loon 导入

在 Loon 配置中添加插件：

```ini
[Plugin]
https://raw.githubusercontent.com/xmxjq/loon-dnsmap/main/CN-DNS-Alidns.plugin, tag=CN-DNS-Alidns, enabled=true
```

建议保留你的默认 DNS 设置，未命中插件中 `[Host]` 规则的域名会继续使用默认 DNS：

```ini
[General]
dns-server = system,https://1.1.1.1/dns-query,https://8.8.8.8/dns-query
```

## 本地生成

```bash
python3 convert_cn_dns_to_loon.py
```

可通过环境变量覆盖源、DoH 地址或输出文件：

```bash
SOURCE="v2fly-cn" \
DOH_SERVER="https://223.5.5.5/dns-query" \
OUTPUT_FILE="CN-DNS-Alidns.plugin" \
python3 convert_cn_dns_to_loon.py
```

转换规则示例：

```text
baidu.com
```

会生成：

```ini
baidu.com = server:https://223.5.5.5/dns-query
*.baidu.com = server:https://223.5.5.5/dns-query
```

也可以用 `SOURCE=dnsmasq-china-list` 读取 `felixonmars/dnsmasq-china-list` 的 `accelerated-domains.china.conf`，但它会生成十万级 `[Host]` 映射，可能导致 Loon 启动 VPN 时反复重启，不建议直接导入。

## 自动更新

仓库内的 GitHub Actions 每天自动运行一次，也可以在 GitHub 页面手动触发 `workflow_dispatch`。
