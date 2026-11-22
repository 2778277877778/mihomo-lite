from mihomo_lite.config.rules import (
    SEVERITY_ERROR,
    analyze_rules,
    default_policy,
    has_final_match,
)


def make_config(rules, *, groups=True, providers=None):
    config = {
        "proxies": [{"name": "node-a", "type": "socks5", "server": "127.0.0.1", "port": 1}],
        "rules": rules,
    }
    if groups:
        config["proxy-groups"] = [
            {"name": "GLOBAL", "type": "select", "proxies": ["DIRECT"]},
            {"name": "Proxy", "type": "select", "proxies": ["node-a", "DIRECT"]},
        ]
    if providers:
        config["proxy-providers"] = providers
    return config


def messages(analysis):
    return " | ".join(analysis.messages())


def test_clean_rule_set_has_no_issues():
    analysis = analyze_rules(
        make_config(
            [
                "DOMAIN-SUFFIX,example.com,Proxy",
                "GEOIP,CN,DIRECT,no-resolve",
                "MATCH,Proxy",
            ]
        )
    )
    assert analysis.total == 3
    assert analysis.ok
    assert analysis.final_match == "Proxy"
    assert analysis.issues == []


def test_missing_match_is_a_warning():
    analysis = analyze_rules(make_config(["DOMAIN,example.com,DIRECT"]))
    assert analysis.final_match is None
    assert any("no final MATCH" in issue.message for issue in analysis.warnings)


def test_match_must_be_last():
    analysis = analyze_rules(make_config(["MATCH,DIRECT", "DOMAIN,example.com,DIRECT"]))
    assert any("not the last rule" in issue.message for issue in analysis.warnings)


def test_second_match_is_ignored():
    analysis = analyze_rules(make_config(["MATCH,DIRECT", "MATCH,Proxy"]))
    assert analysis.final_match == "DIRECT"
    assert any("another MATCH" in issue.message for issue in analysis.warnings)


def test_unknown_policy_warns():
    analysis = analyze_rules(make_config(["DOMAIN,example.com,TypoGroup", "MATCH,DIRECT"]))
    assert any("unknown policy 'TypoGroup'" in issue.message for issue in analysis.warnings)


def test_unknown_rule_type_warns():
    analysis = analyze_rules(make_config(["FANCY-RULE,x,DIRECT", "MATCH,DIRECT"]))
    assert any("unknown rule type" in issue.message for issue in analysis.warnings)


def test_missing_payload_is_an_error():
    analysis = analyze_rules(make_config(["DOMAIN-SUFFIX,,DIRECT", "MATCH,DIRECT"]))
    assert any(issue.severity == SEVERITY_ERROR for issue in analysis.issues)
    assert not analysis.ok


def test_duplicate_rules_warn():
    analysis = analyze_rules(
        make_config(["DOMAIN,a.com,DIRECT", "DOMAIN,a.com,DIRECT", "MATCH,DIRECT"])
    )
    assert any("duplicate of rule 1" in issue.message for issue in analysis.warnings)


def test_ip_rules_without_no_resolve_warn():
    analysis = analyze_rules(make_config(["IP-CIDR,10.0.0.0/8,DIRECT", "MATCH,DIRECT"]))
    assert any("no-resolve" in issue.message for issue in analysis.warnings)


def test_no_resolve_silences_the_warning():
    analysis = analyze_rules(make_config(["IP-CIDR,10.0.0.0/8,DIRECT,no-resolve", "MATCH,DIRECT"]))
    assert not any("no-resolve" in issue.message for issue in analysis.warnings)


def test_domain_suffix_with_dot_warns():
    analysis = analyze_rules(make_config(["DOMAIN-SUFFIX,.example.com,DIRECT", "MATCH,DIRECT"]))
    assert any("must not start with a dot" in issue.message for issue in analysis.warnings)


def test_rule_set_provider_must_exist():
    analysis = analyze_rules(
        make_config(["RULE-SET,ads,REJECT", "MATCH,DIRECT"], providers={}),
    )
    assert any("'ads' is not defined" in issue.message for issue in analysis.warnings)


def test_rule_set_provider_resolves():
    analysis = analyze_rules(
        make_config(
            ["RULE-SET,ads,REJECT", "MATCH,DIRECT"],
            providers={"ads": {"type": "http", "url": "https://example.test/ads.yaml"}},
        )
    )
    assert not any("not defined" in issue.message for issue in analysis.warnings)


def test_stray_spaces_warn():
    analysis = analyze_rules(make_config(["DOMAIN-SUFFIX, example.com, DIRECT", "MATCH,DIRECT"]))
    assert any("stray spaces" in issue.message for issue in analysis.warnings)


def test_rules_must_be_a_list():
    analysis = analyze_rules({"rules": "MATCH,DIRECT"})
    assert analysis.errors and "must be a list" in analysis.errors[0].message


def test_empty_rule_list_warns():
    analysis = analyze_rules({"rules": []})
    assert any("empty" in issue.message for issue in analysis.warnings)


def test_missing_rules_section_warns():
    analysis = analyze_rules({"proxies": []})
    assert any("no 'rules' section" in issue.message for issue in analysis.warnings)


def test_summary_mentions_counts():
    analysis = analyze_rules(make_config(["MATCH,DIRECT"]))
    assert "1 rule" in analysis.summary()
    assert "final DIRECT" in analysis.summary()


def test_default_policy_prefers_real_selector():
    config = {
        "proxy-groups": [
            {"name": "GLOBAL", "type": "select", "proxies": ["DIRECT"]},
            {"name": "Auto", "type": "url-test", "proxies": ["DIRECT"]},
            {"name": "Proxy", "type": "select", "proxies": ["DIRECT"]},
        ]
    }
    assert default_policy(config) == "Proxy"


def test_default_policy_falls_back_to_direct():
    assert default_policy({}) == "DIRECT"
    assert default_policy({"proxy-groups": [{"name": "GLOBAL", "type": "select"}]}) == "DIRECT"


def test_has_final_match():
    assert has_final_match({"rules": ["DOMAIN,a,DIRECT", "MATCH,Proxy"]})
    assert not has_final_match({"rules": ["DOMAIN,a,DIRECT"]})
    assert not has_final_match({"rules": "nope"})
