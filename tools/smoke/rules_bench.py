import sys
import time

sys.path.insert(0, "src")
from mihomo_lite.config.rules import analyze_rules

for count in (500, 5000):
    config = {
        "proxies": [{"name": f"n{i}", "type": "socks5", "server": "127.0.0.1", "port": 1} for i in range(200)],
        "proxy-groups": [{"name": "G", "type": "select", "proxies": ["DIRECT"]}],
        "rules": [f"DOMAIN-SUFFIX,d{i}.example.com,G" for i in range(count)] + ["MATCH,G"],
    }
    start = time.perf_counter()
    analysis = analyze_rules(config)
    elapsed = (time.perf_counter() - start) * 1000
    print(f"rules={analysis.total} analysis_ms={elapsed:.1f}")
