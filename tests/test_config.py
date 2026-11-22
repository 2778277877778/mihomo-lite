import pytest
import yaml

from mihomo_lite.config.generator import generate_runtime_config, write_runtime_config
from mihomo_lite.config.loader import load_yaml_file, load_yaml_text, parse_yaml
from mihomo_lite.config.validator import validate_config
from mihomo_lite.utils.exceptions import ConfigError


def test_valid_profile_passes(sample_profile):
    result = validate_config(sample_profile)
    assert result.ok
    assert any("external-controller" in w for w in result.warnings)
    assert any("allow-lan" in w for w in result.warnings)


def test_missing_proxies_is_an_error():
    result = validate_config({"rules": ["MATCH,DIRECT"]})
    assert not result.ok
    assert "proxies" in result.errors[0]


def test_duplicate_proxy_names_are_rejected(sample_profile):
    sample_profile["proxies"].append(dict(sample_profile["proxies"][0]))
    result = validate_config(sample_profile)
    assert not result.ok
    assert any("duplicate" in error for error in result.errors)


def test_group_without_members_is_rejected(sample_profile):
    sample_profile["proxy-groups"][0]["proxies"] = []
    result = validate_config(sample_profile)
    assert not result.ok


def test_bad_yaml_reports_position():
    with pytest.raises(ConfigError) as info:
        parse_yaml("proxies: [\n  - bad", source="broken.yaml")
    assert "broken.yaml" in str(info.value)


def test_non_mapping_yaml_is_rejected():
    with pytest.raises(ConfigError):
        parse_yaml("- just\n- a list")


def test_empty_yaml_is_rejected():
    with pytest.raises(ConfigError):
        parse_yaml("   \n")


def test_html_instead_of_yaml_is_rejected():
    with pytest.raises(ConfigError) as info:
        load_yaml_text("<html><body>login required</body></html>", source="sub")
    assert "HTML" in str(info.value)


def test_load_yaml_file_roundtrip(tmp_path, sample_profile):
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(sample_profile), encoding="utf-8")
    loaded = load_yaml_file(path)
    assert loaded["proxies"][0]["name"] == "node-a"


def test_runtime_config_forces_local_safe_values(sample_profile):
    generated = generate_runtime_config(
        sample_profile,
        mixed_port=23456,
        api_port=23457,
        secret="s3cret",
        log_level="warning",
    )
    data = generated.data
    assert data["external-controller"] == "127.0.0.1:23457"
    assert data["secret"] == "s3cret"
    assert data["bind-address"] == "127.0.0.1"
    assert data["allow-lan"] is False
    assert data["mixed-port"] == 23456
    assert data["port"] == 0
    assert data["socks-port"] == 0
    assert data["tun"] == {"enable": False}
    assert data["log-level"] == "warning"
    assert data["profile"]["store-selected"] is True


def test_generator_does_not_mutate_the_original(sample_profile):
    before = dict(sample_profile)
    generate_runtime_config(sample_profile, mixed_port=1, api_port=2, secret="x")
    assert sample_profile == before
    assert sample_profile["external-controller"] == "0.0.0.0:9090"


def test_generator_strips_extra_controllers(sample_profile):
    sample_profile["external-controller-tls"] = "0.0.0.0:9443"
    sample_profile["listeners"] = [{"name": "extra", "type": "http", "port": 9999}]
    generated = generate_runtime_config(sample_profile, mixed_port=1, api_port=2, secret="x")
    assert "external-controller-tls" not in generated.data
    assert "listeners" not in generated.data
    assert any("listener" in note for note in generated.notes)


def test_generator_appends_a_final_match(sample_profile):
    sample_profile["rules"] = ["DOMAIN-SUFFIX,example.com,Proxy"]
    generated = generate_runtime_config(sample_profile, mixed_port=1, api_port=2, secret="x")
    assert generated.data["rules"][-1] == "MATCH,Proxy"
    assert any("MATCH,Proxy" in note for note in generated.notes)


def test_generator_keeps_an_existing_match(sample_profile):
    generated = generate_runtime_config(sample_profile, mixed_port=1, api_port=2, secret="x")
    rules = generated.data["rules"]
    assert rules == ["MATCH,Proxy"]
    assert not any("appended" in note for note in generated.notes)


def test_generator_adds_match_to_empty_rules(sample_profile):
    sample_profile["rules"] = []
    generated = generate_runtime_config(sample_profile, mixed_port=1, api_port=2, secret="x")
    assert generated.data["rules"] == ["MATCH,Proxy"]


def test_generator_uses_direct_without_groups(sample_profile):
    sample_profile["proxy-groups"] = []
    sample_profile["rules"] = ["DOMAIN,example.com,DIRECT"]
    generated = generate_runtime_config(sample_profile, mixed_port=1, api_port=2, secret="x")
    assert generated.data["rules"][-1] == "MATCH,DIRECT"


def test_validator_reports_rule_policy_typos(sample_profile):
    sample_profile["rules"] = ["DOMAIN,example.com,Typo", "MATCH,Proxy"]
    result = validate_config(sample_profile)
    assert result.ok
    assert any("unknown policy 'Typo'" in warning for warning in result.warnings)


def test_validator_rejects_empty_rule_payload(sample_profile):
    sample_profile["rules"] = ["DOMAIN-SUFFIX,,DIRECT", "MATCH,Proxy"]
    result = validate_config(sample_profile)
    assert not result.ok


def test_generator_rejects_missing_secret(sample_profile):
    with pytest.raises(ConfigError):
        generate_runtime_config(sample_profile, mixed_port=1, api_port=2, secret="")


def test_write_runtime_config_is_atomic(paths, sample_profile):
    generated = generate_runtime_config(sample_profile, mixed_port=1, api_port=2, secret="abc")
    target = paths.runtime_config
    write_runtime_config(target, generated)
    text = target.read_text(encoding="utf-8")
    assert "secret: abc" in text
    assert not list(target.parent.glob(".*.tmp"))
