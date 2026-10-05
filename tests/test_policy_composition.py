"""Every matched resource must be authorized independently of policy order."""
import itertools

from promption.policies import PolicyEngine, ResourcePolicy


POLICIES = (
    ResourcePolicy("catalog", "catalog", "public", "catalog", (r"catalogo",)),
    ResourcePolicy("payroll", "payroll", "private", "payroll", (r"sueldos",)),
    ResourcePolicy("stock", "stock", "internal", "stock", (r"stock",)),
)
ROLES = {"public": {"customer", "sales", "admin"}, "private": {"admin"}, "internal": {"sales", "admin"}}


def test_mixed_requests_require_every_permission_regardless_of_order():
    for policies in itertools.permutations(POLICIES):
        engine = PolicyEngine(policies, tier_roles=ROLES)
        for evaluate in (engine.evaluate, engine.evaluate_output):
            decision = evaluate("catálogo, stock y sueldos", ["sales"])
            assert not decision.allowed
            assert decision.policy_id == "payroll"
            assert set(decision.matched_policy_ids) == {"catalog", "stock", "payroll"}
            assert evaluate("catálogo, stock y sueldos", ["admin"]).allowed


def test_nonhierarchical_roles_must_satisfy_each_resource():
    engine = PolicyEngine(POLICIES[1:], tier_roles={"private": {"hr"}, "internal": {"warehouse"}})
    assert not engine.evaluate("stock y sueldos", ["hr"]).allowed
    assert not engine.evaluate("stock y sueldos", ["warehouse"]).allowed
    assert engine.evaluate("stock y sueldos", ["hr", "warehouse"]).allowed


def test_unclassified_content_requires_explicit_application_policy():
    assert not PolicyEngine(POLICIES, tier_roles=ROLES).evaluate("Hola", ["admin"]).allowed
    decision = PolicyEngine(POLICIES, tier_roles=ROLES, allow_unmatched=True).evaluate("Hola", ["customer"])
    assert decision.allowed and not decision.matched
    assert decision.policy_id == "unclassified" and decision.tool_name is None


def test_excluding_one_output_policy_does_not_hide_other_matches():
    engine = PolicyEngine(POLICIES, tier_roles=ROLES, output_excluded_policy_ids=frozenset({"catalog"}),
                          allow_unmatched=True)
    decision = engine.evaluate_output("catálogo y sueldos", ["customer"])
    assert not decision.allowed and decision.policy_id == "payroll"
    assert decision.matched_policy_ids == ("payroll",)
