import sys
import os

sys.path.insert(0, os.path.abspath("."))
print("Step 1: sys.path ready", flush=True)

import backend.engine.graph_model as gm
print("Step 2: graph_model imported", flush=True)

import backend.engine.simulator as sim
print("Step 3: simulator imported", flush=True)

import backend.engine.threat_intelligence as ti
print("Step 4: threat_intelligence imported", flush=True)

p = ti.ThreatIntelligencePredictor()
print("Step 5: ThreatIntelligencePredictor instantiated", flush=True)

import backend.engine.multimodal_network as mn
print("Step 6: multimodal_network imported", flush=True)

m = mn.create_multimodal_network()
print("Step 7: multimodal_network created", flush=True)

import backend.engine.route_recommender as rr
print("Step 8: route_recommender imported", flush=True)

import backend.engine.scenario_manager as sm
print("Step 9: scenario_manager imported", flush=True)

recommender = rr.RouteRecommender(m, p, None, sm.ScenarioManager(), demo_mode=True)
print("Step 10: recommender instantiated", flush=True)

res = recommender.recommend("Shanghai", "Rotterdam", scenario="SUEZ_BLOCK", priority="urgent", budget_sensitivity="high")
print(f"Step 11: Route computed! Total recommendations: {len(res.get('recommendations', []))}", flush=True)
for r in res.get("recommendations", []):
    print(f"  {r['persona']}: {r['adjusted_eta']}h, ${r['total_cost']}")
