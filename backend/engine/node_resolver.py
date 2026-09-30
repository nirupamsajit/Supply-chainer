import json
import os
from typing import Dict, Optional, Any

class NodeResolver:
    """
    Supplychainer Unified Node Resolver.
    V4: Virtual Node Edition (Forensic Fix).
    """
    def __init__(self, locations_path: str = None, hubs_path: str = None):
        if not locations_path:
            locations_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'canonical_locations.json')
        if not hubs_path:
            hubs_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'canonical_hubs.json')
            
        self.location_map = {}
        if os.path.exists(locations_path):
            with open(locations_path, 'r') as f:
                self.location_map = json.load(f)
                
        self.hubs = []
        if os.path.exists(hubs_path):
            with open(hubs_path, 'r') as f:
                self.hubs = json.load(f)

    def resolve_node_to_entry_point(self, location_or_id: str) -> Dict[str, Any]:
        """
        Resolves a location to its primary virtual entry node in the Split Graph.
        """
        if not location_or_id or not isinstance(location_or_id, str):
            return {"id": None, "error": "Invalid location identifier"}

        clean_input = location_or_id.strip()

        # Direct virtual node check (e.g., 'PORT-SHANGHAI:sea')
        if ":" in clean_input:
            base_id, mode = clean_input.split(":", 1)
            target_hub = next((h for h in self.hubs if h["id"] == base_id), None)
            if target_hub and mode in target_hub.get("modes", []):
                return {"id": clean_input}

        physical_id = None
        current_hub = next((h for h in self.hubs if h["id"] == clean_input), None)
        
        # City level exact match
        if clean_input in self.location_map:
            physical_id = self.location_map[clean_input].get("road")
            if not physical_id:
                physical_id = list(self.location_map[clean_input].values())[0]
        
        # ID level exact match
        elif current_hub:
            physical_id = clean_input

        # Case-insensitive city or hub fallback
        if not physical_id:
            loc_lower = clean_input.lower()
            for city_name, modes in self.location_map.items():
                if city_name.lower() == loc_lower:
                    physical_id = modes.get("road") or (list(modes.values())[0] if modes else None)
                    break
            if not physical_id:
                matched_hub = next(
                    (h for h in self.hubs if h["id"].lower() == loc_lower or h.get("display_name", "").lower() == loc_lower),
                    None
                )
                if matched_hub:
                    physical_id = matched_hub["id"]

        if not physical_id:
            return {"id": None, "error": f"Entry point unavailable for {location_or_id}"}

        # For the split graph, we usually enter through 'road' (DC) or the hub's primary mode
        target_hub = next((h for h in self.hubs if h["id"] == physical_id), None)
        if not target_hub:
            return {"id": None, "error": f"Physical Hub mapping corrupted for {physical_id}"}
            
        entry_mode = "road" if "road" in target_hub["modes"] else target_hub["modes"][0]
        return {"id": f"{physical_id}:{entry_mode}"}

    def resolve_node(self, location_or_id: str, mode: str = "any") -> str:
        """Legacy support"""
        res = self.resolve_node_to_entry_point(location_or_id)
        return res.get("id")
