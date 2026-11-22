"""Static analysis for Mihomo routing rules.

The core accepts almost any rule string and only fails at runtime, which means a
typo in a policy name silently sends traffic to the wrong place. This module
checks rules before the core ever sees them and explains what is wrong in the
same language the UI uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Rule types documented by Mihomo (a superset of Clash.Meta). Unknown types are
# reported as warnings rather than errors so a newer core never becomes unusable.
KNOWN_RULE_TYPES = frozenset(
    {
        "DOMAIN",
        "DOMAIN-SUFFIX",
        "DOMAIN-KEYWORD",
        "DOMAIN-REGEX",
        "GEOSITE",
        "GEOIP",
        "SRC-GEOIP",
        "IP-ASN",
        "SRC-IP-ASN",
        "IP-CIDR",
        "IP-CIDR6",
        "SRC-IP-CIDR",
        "DST-PORT",
        "SRC-PORT",
        "IN-PORT",
        "NETWORK",
        "PROCESS-NAME",
        "PROCESS-PATH",
        "PROCESS-NAME-REGEX",
        "PROCESS-PATH-REGEX",
        "UID",
        "IN-USER",
        "IN-NAME",
        "IN-TYPE",
        "RULE-SET",
        "SUB-RULE",
        "AND",
        "OR",
        "NOT",
        "MATCH",
    }
)

# Policies the core provides itself; everything else must be a proxy or group.
BUILTIN_POLICIES = frozenset(
    {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "PASS-RULE"}
)

# Rules that trigger a DNS lookup unless "no-resolve" is given.
RESOLVING_TYPES = frozenset({"GEOIP", "SRC-GEOIP", "IP-CIDR", "IP-CIDR6", "SRC-IP-CIDR"})
LOGICAL_TYPES = frozenset({"AND", "OR", "NOT"})

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass(frozen=True)
class RuleIssue:
    line: int
    rule: str
    severity: str
    message: str

    def as_text(self) -> str:
        prefix = f"rule {self.line}" if self.line else "rules"
        return f"{prefix}: {self.message}"


@dataclass
class RuleAnalysis:
    total: int = 0
    issues: list[RuleIssue] = field(default_factory=list)
    final_match: str | None = None
    by_type: dict[str, int] = field(default_factory=dict)

    @property
    def errors(self) -> list[RuleIssue]:
        return [issue for issue in self.issues if issue.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> list[RuleIssue]:
        return [issue for issue in self.issues if issue.severity == SEVERITY_WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        if self.total == 0:
            return "No routing rules."
        label = "rule" if self.total == 1 else "rules"
        parts = [f"{self.total} {label}"]
        if self.final_match:
            parts.append(f"final {self.final_match}")
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warnings")
        return " · ".join(parts)

    def messages(self, *, limit: int = 0) -> list[str]:
        texts = [issue.as_text() for issue in self.issues]
        return texts[:limit] if limit else texts


def _names(values: Any, key: str) -> set[str]:
    if not isinstance(values, list):
        return set()
    names: set[str] = set()
    for entry in values:
        if isinstance(entry, dict) and entry.get(key):
            names.add(str(entry[key]))
    return names


def _policy_known(
    policy: str,
    proxies: set[str],
    groups: set[str],
    policies: set[str],
) -> bool:
    upper = policy.upper()
    return (
        upper in BUILTIN_POLICIES
        or upper in policies
        or policy in proxies
        or policy in groups
    )


def _split(rule: str) -> list[str]:
    return [part.strip() for part in rule.split(",")]


def analyze_rules(config: dict[str, Any], *, line_offset: int = 0) -> RuleAnalysis:
    """Inspect the rules section and report problems in source order."""
    analysis = RuleAnalysis()
    rules = config.get("rules")
    if rules is None:
        if not config.get("rule-providers") and not config.get("sub-rules"):
            analysis.issues.append(
                RuleIssue(0, "", SEVERITY_WARNING, "no 'rules' section; traffic uses the default outbound")
            )
        return analysis
    if not isinstance(rules, list):
        analysis.issues.append(RuleIssue(0, "", SEVERITY_ERROR, "'rules' must be a list"))
        return analysis
    if not rules:
        analysis.issues.append(
            RuleIssue(0, "", SEVERITY_WARNING, "'rules' is empty; traffic uses the default outbound")
        )
        return analysis

    proxies = _names(config.get("proxies"), "name")
    groups = _names(config.get("proxy-groups"), "name")
    providers = set((config.get("proxy-providers") or {}).keys()) if isinstance(
        config.get("proxy-providers"), dict
    ) else set()
    sub_rules = set((config.get("sub-rules") or {}).keys()) if isinstance(
        config.get("sub-rules"), dict
    ) else set()
    named_policies = {
        str(item.get("name")).upper()
        for item in (config.get("proxy-groups") or [])
        if isinstance(item, dict) and item.get("name")
    }

    seen: dict[str, int] = {}
    match_line: int | None = None
    analysis.total = len(rules)

    for index, raw in enumerate(rules):
        line = index + 1
        if not isinstance(raw, str) or not raw.strip():
            analysis.issues.append(
                RuleIssue(line, str(raw), SEVERITY_ERROR, "rule is empty or not a string")
            )
            continue
        rule = raw.strip()
        parts = _split(rule)
        kind = parts[0].upper() if parts else ""
        analysis.by_type[kind] = analysis.by_type.get(kind, 0) + 1

        if kind not in KNOWN_RULE_TYPES:
            analysis.issues.append(
                RuleIssue(
                    line,
                    rule,
                    SEVERITY_WARNING,
                    f"unknown rule type '{parts[0]}'; it may need a newer core",
                )
            )
            continue

        if raw != rule or ", " in raw or " ," in raw:
            analysis.issues.append(
                RuleIssue(line, rule, SEVERITY_WARNING, "stray spaces around the commas")
            )

        if kind == "MATCH":
            if len(parts) != 2 or not parts[1]:
                analysis.issues.append(
                    RuleIssue(line, rule, SEVERITY_ERROR, "MATCH needs exactly one policy")
                )
                continue
            if analysis.final_match is None:
                analysis.final_match = parts[1]
                match_line = line
                if index != len(rules) - 1:
                    analysis.issues.append(
                        RuleIssue(
                            line,
                            rule,
                            SEVERITY_WARNING,
                            "MATCH is not the last rule; everything after it is ignored",
                        )
                    )
                if not _policy_known(parts[1], proxies, groups, named_policies):
                    analysis.issues.append(
                        RuleIssue(
                            line,
                            rule,
                            SEVERITY_WARNING,
                            f"unknown policy '{parts[1]}'",
                        )
                    )
            else:
                analysis.issues.append(
                    RuleIssue(
                        line,
                        rule,
                        SEVERITY_WARNING,
                        f"another MATCH was already defined on rule {match_line}; this one is ignored",
                    )
                )
            continue

        if kind in LOGICAL_TYPES:
            policy = parts[-1]
            if len(parts) < 3:
                analysis.issues.append(
                    RuleIssue(line, rule, SEVERITY_ERROR, f"{kind} needs at least one sub-rule and a policy")
                )
                continue
        else:
            if len(parts) < 3:
                analysis.issues.append(
                    RuleIssue(line, rule, SEVERITY_ERROR, "missing payload or policy")
                )
                continue
            payload = parts[1]
            # Trailing modifiers such as "no-resolve" are not the policy.
            policy_options = [p for p in parts[2:] if p.lower() != "no-resolve"]
            if not policy_options:
                analysis.issues.append(
                    RuleIssue(line, rule, SEVERITY_ERROR, "missing policy before 'no-resolve'")
                )
                continue
            policy = policy_options[-1]
            if not payload:
                analysis.issues.append(
                    RuleIssue(line, rule, SEVERITY_ERROR, "missing payload")
                )
                continue
            if kind == "RULE-SET" and payload not in providers:
                analysis.issues.append(
                    RuleIssue(
                        line,
                        rule,
                        SEVERITY_WARNING,
                        f"rule-provider '{payload}' is not defined",
                    )
                )
            if kind == "SUB-RULE" and payload not in sub_rules:
                analysis.issues.append(
                    RuleIssue(
                        line,
                        rule,
                        SEVERITY_WARNING,
                        f"sub-rule '{payload}' is not defined",
                    )
                )
            if kind == "DOMAIN-SUFFIX" and payload.startswith("."):
                analysis.issues.append(
                    RuleIssue(
                        line,
                        rule,
                        SEVERITY_WARNING,
                        "DOMAIN-SUFFIX must not start with a dot",
                    )
                )
            if kind in RESOLVING_TYPES and not any(p.lower() == "no-resolve" for p in parts[2:]):
                analysis.issues.append(
                    RuleIssue(
                        line,
                        rule,
                        SEVERITY_WARNING,
                        f"{kind} triggers a DNS lookup; add ,no-resolve if the domain is already known",
                    )
                )

        if not _policy_known(policy, proxies, groups, named_policies):
            analysis.issues.append(
                RuleIssue(line, rule, SEVERITY_WARNING, f"unknown policy '{policy}'")
            )

        key = ",".join(part.lower() for part in parts)
        if key in seen:
            analysis.issues.append(
                RuleIssue(
                    line,
                    rule,
                    SEVERITY_WARNING,
                    f"duplicate of rule {seen[key]}",
                )
            )
        else:
            seen[key] = line

    if analysis.final_match is None:
        analysis.issues.append(
            RuleIssue(
                0,
                "",
                SEVERITY_WARNING,
                "no final MATCH rule; unmatched traffic falls back to the core default",
            )
        )
    return analysis


def has_final_match(config: dict[str, Any]) -> bool:
    rules = config.get("rules")
    if not isinstance(rules, list):
        return False
    return any(
        isinstance(raw, str) and raw.strip().upper().startswith("MATCH") for raw in rules
    )


def default_policy(config: dict[str, Any]) -> str:
    """Pick a sensible final policy: first real selector group, else DIRECT."""
    groups = config.get("proxy-groups")
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict) or not group.get("name"):
                continue
            if str(group.get("name")) == "GLOBAL":
                continue
            if str(group.get("type", "")).lower() in {"select", "fallback", "load-balance", "relay"}:
                return str(group["name"])
        for group in groups:
            if isinstance(group, dict) and group.get("name") and str(group["name"]) != "GLOBAL":
                return str(group["name"])
    return "DIRECT"
