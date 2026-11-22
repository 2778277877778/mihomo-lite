import sys
from pathlib import Path

sys.path.insert(0, "src")
from mihomo_lite.config.loader import load_yaml_file
from mihomo_lite.config.rules import analyze_rules

print("== examples/sample.yaml ==")
print(analyze_rules(load_yaml_file(Path("examples/sample.yaml"))).summary())

broken = {
    "proxies": [{"name": "n1", "type": "socks5", "server": "127.0.0.1", "port": 1}],
    "proxy-groups": [{"name": "Proxy", "type": "select", "proxies": ["n1", "DIRECT"]}],
    "rules": [
        "DOMAIN-SUFFIX, example.com, Proxi",
        "IP-CIDR,10.0.0.0/8,DIRECT",
        "RULE-SET,ads,REJECT",
        "MATCH,Proxy",
        "DOMAIN,dead.example,DIRECT",
        "DOMAIN-SUFFIX,example.com, Proxi",
    ],
}
analysis = analyze_rules(broken)
print("== broken profile ==")
print(analysis.summary())
for issue in analysis.messages():
    print(" ", issue)
