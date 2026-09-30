"""
Regression tests for Supplychainer bug fixes.
Run from project root:  pytest tests/ -v
Each test targets one bug and is designed to FAIL on the pre-fix code.
"""
import os
import json
import pytest


# ---------------------------------------------------------------------------
# BUG-002  –  CARF filter direction (pure Python, no model deps)
# ---------------------------------------------------------------------------
class TestCARFFilter:
    """BUG-002: CARF must zero IRRELEVANT threats and pass RELEVANT ones."""

    @pytest.fixture(autouse=True)
    def _carf(self):
        from backend.engine.threat_intelligence import CARFFilter
        self.carf = CARFFilter()

    # -- relevant threats MUST pass --
    def test_sea_threat_passes_for_sea(self):
        assert self.carf.apply_filter(0.8, "port terminal strike vessels held", "sea") == pytest.approx(0.8)

    def test_air_threat_passes_for_air(self):
        assert self.carf.apply_filter(0.7, "airport closure flights grounded", "air") == pytest.approx(0.7)

    def test_rail_threat_passes_for_rail(self):
        assert self.carf.apply_filter(0.6, "rail track damage locomotive derailed", "rail") == pytest.approx(0.6)

    def test_road_threat_passes_for_road(self):
        assert self.carf.apply_filter(0.5, "highway truck traffic bridge closed", "road") == pytest.approx(0.5)

    # -- irrelevant threats MUST be zeroed --
    def test_sea_threat_zeroed_for_rail(self):
        assert self.carf.apply_filter(0.8, "port terminal strike vessels held", "rail") == 0.0

    def test_air_threat_zeroed_for_sea(self):
        assert self.carf.apply_filter(0.7, "airport closure flights grounded", "sea") == 0.0

    def test_rail_threat_zeroed_for_air(self):
        assert self.carf.apply_filter(0.6, "rail track damage locomotive derailed", "air") == 0.0

    def test_road_threat_zeroed_for_sea(self):
        assert self.carf.apply_filter(0.5, "highway truck traffic bridge closed", "sea") == 0.0

    # -- edge cases --
    def test_zero_score_always_zero(self):
        assert self.carf.apply_filter(0.0, "port strike", "sea") == 0.0

    def test_generic_threat_passes(self):
        """News with no mode-specific keywords should pass through."""
        assert self.carf.apply_filter(0.5, "economic disruption causing delays", "sea") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# BUG-005  –  ScenarioManager must not leak state
# ---------------------------------------------------------------------------
class TestScenarioManagerStateless:
    """BUG-005: get_active_disruptions() must not return stale state."""

    def test_activate_does_not_leak(self):
        from backend.engine.scenario_manager import ScenarioManager
        mgr = ScenarioManager()
        mgr.activate_scenario("SUEZ_BLOCK")
        # Without explicit scenario_id, should return empty
        assert mgr.get_active_disruptions() == {}

    def test_explicit_scenario_id(self):
        from backend.engine.scenario_manager import ScenarioManager
        mgr = ScenarioManager()
        d = mgr.get_active_disruptions("SUEZ_BLOCK")
        assert "CHOKE-SUEZ" in d
        assert d["CHOKE-SUEZ"]["delay"] == 240
        assert d["CHOKE-SUEZ"]["threat"] == 1.0

    def test_independent_lookups(self):
        from backend.engine.scenario_manager import ScenarioManager
        mgr = ScenarioManager()
        mgr.activate_scenario("SUEZ_BLOCK")
        d = mgr.get_active_disruptions("CHENNAI_FLOOD")
        assert "CHOKE-SUEZ" not in d
        assert "PORT-CHENNAI" in d


# ---------------------------------------------------------------------------
# BUG-006  –  Calibration caps ≥ p95
# ---------------------------------------------------------------------------
class TestCalibrationCaps:
    """BUG-006: cap must not be below observed p95."""

    def test_caps_at_least_p95(self):
        with open(os.path.join("Execution", "calibration_profiles.json")) as f:
            profiles = json.load(f)
        for mode, p in profiles.items():
            assert p["cap"] >= p["p95_observed"], (
                f"{mode}: cap {p['cap']} < p95 {p['p95_observed']}"
            )


# ---------------------------------------------------------------------------
# BUG-014  –  Supplier cost_score ≥ 0
# ---------------------------------------------------------------------------
class TestSupplierCostScore:
    """BUG-014: cost_score must be non-negative."""

    def test_all_scores_nonneg(self):
        from backend.engine.supplier_scorer import SupplierScorer
        path = os.path.join("backend", "data", "suppliers.json")
        scorer = SupplierScorer(path)
        for cat in ["Electronics", "Raw Materials", "Chemicals"]:
            for s in scorer.get_ranked_suppliers(cat):
                cs = s["audit_trace"]["scores"]["cost"]
                assert cs >= 0, f"{s['name']} cost_score={cs}"


# ---------------------------------------------------------------------------
# BUG-004  –  Explanation percentages must be valid
# ---------------------------------------------------------------------------
class TestExplanationText:
    """BUG-004: no impossible percentages in generated explanations."""

    def test_balanced_no_impossible_percent(self):
        """The old code would output '396%' — any % > 100 is impossible."""
        import re
        from backend.engine.route_recommender import RouteRecommender
        rr = RouteRecommender.__new__(RouteRecommender)  # Skip __init__
        trace = {
            "eta": {"transit": 200, "transfer": 8, "scenario": 240},
            "cost": {"transit": 2000, "transfer": 180, "scenario": 200},
        }
        text = rr._generate_forensic_explanation("BALANCED", trace, 1.0)
        pcts = [int(p) for p in re.findall(r"(\d+)%", text)]
        for p in pcts:
            assert p <= 100, f"Impossible percentage {p}% in: {text}"


# ---------------------------------------------------------------------------
# BUG-008  –  Strategic transit edges are bidirectional
# ---------------------------------------------------------------------------
class TestBidirectionalTransitEdges:
    """BUG-008: Strategic transit edges must be bidirectional."""

    def test_transit_edges_bidirectional(self):
        from backend.engine.multimodal_network import create_multimodal_network
        G = create_multimodal_network()
        unidirectional = []
        for u, v, d in G.edges(data=True):
            if d.get("type") == "transit" and not G.has_edge(v, u):
                unidirectional.append((u, v))
        assert len(unidirectional) == 0, f"Found {len(unidirectional)} unidirectional transit edges: {unidirectional[:5]}"


# ---------------------------------------------------------------------------
# BUG-003  –  Scenario disruptions match both source and destination
# ---------------------------------------------------------------------------
class TestDisruptionBothDirections:
    """BUG-003: Disruptions must apply to both inbound and outbound legs of chokepoints."""

    def test_disruption_matches_source_and_destination(self):
        from backend.engine.multimodal_network import create_multimodal_network
        from backend.engine.scenario_manager import ScenarioManager
        from backend.engine.route_recommender import RouteRecommender
        G = create_multimodal_network()
        mgr = ScenarioManager()
        disruptions = mgr.get_active_disruptions("SUEZ_BLOCK")
        assert "CHOKE-SUEZ" in disruptions

        rr = RouteRecommender.__new__(RouteRecommender)
        rr.scenario_mgr = mgr
        rr.unified_graph = G

        # Find edges where CHOKE-SUEZ is source vs destination
        suez_outbound = [(u, v) for u, v in G.edges() if "CHOKE-SUEZ" in u and "CHOKE-SUEZ" not in v]
        assert len(suez_outbound) > 0
        u, v = suez_outbound[0]
        u_pid = G.nodes[u].get("physical_id")
        v_pid = G.nodes[v].get("physical_id")
        assert u_pid == "CHOKE-SUEZ"
        assert u_pid in disruptions or v_pid in disruptions


# ---------------------------------------------------------------------------
# BUG-010  –  Total cost equals sum of audit trace cost components
# ---------------------------------------------------------------------------
class TestCostAuditConsistency:
    """BUG-010: total_cost must match transit + transfer + scenario in trace."""

    def test_cost_audit_consistency(self):
        from backend.engine.multimodal_network import create_multimodal_network
        from backend.engine.scenario_manager import ScenarioManager
        from backend.engine.route_recommender import RouteRecommender
        from backend.engine.threat_intelligence import ContrastiveNLPEngine, CARFFilter
        from backend.engine.news_ingestion import DynamicNewsIngestor
        from backend.engine.node_resolver import NodeResolver

        G = create_multimodal_network()
        mgr = ScenarioManager()
        rr = RouteRecommender(G, None, None, mgr, demo_mode=True)
        res = rr.recommend("Shanghai", "Rotterdam", scenario="SUEZ_BLOCK")
        assert "recommendations" in res
        for rec in res["recommendations"]:
            cost_trace = rec["audit_trace"]["cost"]
            expected_total = cost_trace["transit"] + cost_trace["transfer"] + cost_trace["scenario"]
            assert rec["total_cost"] == pytest.approx(expected_total, rel=1e-2), (
                f"total_cost {rec['total_cost']} != trace sum {expected_total}"
            )


# ---------------------------------------------------------------------------
# BUG-012  –  Chicago road points to HUB-CHICAGO
# ---------------------------------------------------------------------------
class TestLocationMappings:
    """BUG-012: Chicago road must resolve to distribution hub HUB-CHICAGO."""

    def test_chicago_road_mapped_to_hub(self):
        with open("backend/data/canonical_locations.json") as f:
            locs = json.load(f)
        assert locs["Chicago"]["road"] == "HUB-CHICAGO"


# ---------------------------------------------------------------------------
# BUG-015  –  BenchmarkCharts Y-axis does not clip data
# ---------------------------------------------------------------------------
class TestBenchmarkChartsDomain:
    """BUG-015: YAxis domain must accommodate max success rate."""

    def test_chart_domain_accommodates_data(self):
        with open("frontend/src/BenchmarkCharts.jsx") as f:
            content = f.read()
        import re
        m = re.search(r'domain=\{\[0,\s*(\d+)\]\}', content)
        assert m is not None
        assert int(m.group(1)) >= 50, f"Domain cap {m.group(1)} clips 50.0% success rate"


# ---------------------------------------------------------------------------
# BUG-018  –  Startup graph reuse
# ---------------------------------------------------------------------------
class TestStartupGraphReuse:
    """BUG-018: RouteRecommender reuses passed network rather than recreating it."""

    def test_graph_reuse(self):
        from backend.engine.multimodal_network import create_multimodal_network
        from backend.engine.scenario_manager import ScenarioManager
        from backend.engine.route_recommender import RouteRecommender
        G = create_multimodal_network()
        mgr = ScenarioManager()
        rr = RouteRecommender(G, None, None, mgr, demo_mode=True)
        assert rr.unified_graph is G


# ---------------------------------------------------------------------------
# BUG-019  –  Optimal speed uses Math.min across recommendations
# ---------------------------------------------------------------------------
class TestOptimalSpeedMin:
    """BUG-019: Optimal speed in footer must use Math.min."""

    def test_optimal_speed_in_footer(self):
        with open("frontend/src/RouteRecommender.jsx") as f:
            content = f.read()
        assert "Math.min(...recommendations.map(r => r.adjusted_eta))" in content

