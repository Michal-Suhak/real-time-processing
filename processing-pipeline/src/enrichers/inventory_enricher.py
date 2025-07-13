from typing import Dict, Any, Optional
import json
import structlog

logger = structlog.get_logger(__name__)


class InventoryEnricher:
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.item_cache = {}  # In-memory fallback cache
        self.location_cache = {}

    def enrich(self, data: Dict[str, Any]) -> Dict[str, Any]:
        enriched_data = data.copy()
        
        # Enrich with item details
        item_details = self._get_item_details(data.get("item_id"))
        if item_details:
            enriched_data["item_details"] = item_details
        
        # Enrich with location details
        location_details = self._get_location_details(data.get("location_id"))
        if location_details:
            enriched_data["location_details"] = location_details
        
        # Add inventory classification
        enriched_data["classification"] = self._classify_inventory_event(enriched_data)
        
        # Add risk assessment
        enriched_data["risk_assessment"] = self._assess_risk(enriched_data)
        
        # Add seasonal context
        enriched_data["seasonal_context"] = self._get_seasonal_context(enriched_data)
        
        logger.debug(
            "Enriched inventory data",
            item_id=data.get("item_id"),
            enrichments=list(enriched_data.keys()),
        )
        
        return enriched_data

    def _get_item_details(self, item_id: str) -> Optional[Dict[str, Any]]:
        if not item_id:
            return None
        
        # Try Redis cache first
        if self.redis_client:
            try:
                cached_data = self.redis_client.get(f"item:{item_id}")
                if cached_data:
                    return json.loads(cached_data)
            except Exception as e:
                logger.warning("Redis cache error for item", item_id=item_id, error=str(e))
        
        # Try in-memory cache
        if item_id in self.item_cache:
            return self.item_cache[item_id]
        
        # Mock item details (in real implementation, fetch from database)
        mock_details = self._generate_mock_item_details(item_id)
        
        # Cache the result
        self.item_cache[item_id] = mock_details
        
        if self.redis_client:
            try:
                self.redis_client.setex(
                    f"item:{item_id}", 
                    3600,  # 1 hour TTL
                    json.dumps(mock_details)
                )
            except Exception as e:
                logger.warning("Failed to cache item details", error=str(e))
        
        return mock_details

    def _get_location_details(self, location_id: str) -> Optional[Dict[str, Any]]:
        if not location_id:
            return None
        
        # Try cache first
        if location_id in self.location_cache:
            return self.location_cache[location_id]
        
        # Mock location details
        mock_details = self._generate_mock_location_details(location_id)
        self.location_cache[location_id] = mock_details
        
        return mock_details

    def _generate_mock_item_details(self, item_id: str) -> Dict[str, Any]:
        # Generate consistent mock data based on item_id
        hash_val = hash(item_id) % 1000
        
        categories = ["Electronics", "Clothing", "Food", "Tools", "Books"]
        suppliers = ["Supplier_A", "Supplier_B", "Supplier_C", "Supplier_D"]
        
        return {
            "name": f"Item_{item_id}",
            "category": categories[hash_val % len(categories)],
            "supplier": suppliers[hash_val % len(suppliers)],
            "unit_cost": round(10 + (hash_val % 100), 2),
            "weight": round(0.1 + (hash_val % 50) * 0.1, 1),
            "perishable": hash_val % 4 == 0,
            "high_value": hash_val % 10 == 0,
            "reorder_point": 50 + (hash_val % 100),
            "max_stock": 500 + (hash_val % 1000),
        }

    def _generate_mock_location_details(self, location_id: str) -> Dict[str, Any]:
        hash_val = hash(location_id) % 100
        
        zones = ["A", "B", "C", "D"]
        types = ["storage", "picking", "shipping", "receiving"]
        
        return {
            "zone": zones[hash_val % len(zones)],
            "type": types[hash_val % len(types)],
            "capacity": 1000 + (hash_val % 5000),
            "temperature_controlled": hash_val % 5 == 0,
            "automated": hash_val % 3 == 0,
        }

    def _classify_inventory_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        classification = {
            "event_type": data.get("normalized_action", "unknown"),
            "volume_category": self._get_volume_category(data),
            "value_category": self._get_value_category(data),
            "urgency": self._get_urgency_level(data),
        }
        
        return classification

    def _get_volume_category(self, data: Dict[str, Any]) -> str:
        quantity = data.get("quantity_abs", 0)
        
        if quantity < 10:
            return "low"
        elif quantity < 100:
            return "medium"
        elif quantity < 1000:
            return "high"
        else:
            return "bulk"

    def _get_value_category(self, data: Dict[str, Any]) -> str:
        total_value = data.get("total_value")
        if not total_value:
            return "unknown"
        
        if total_value < 100:
            return "low"
        elif total_value < 1000:
            return "medium"
        elif total_value < 10000:
            return "high"
        else:
            return "critical"

    def _get_urgency_level(self, data: Dict[str, Any]) -> str:
        item_details = data.get("item_details", {})
        
        # High urgency for perishable items
        if item_details.get("perishable"):
            return "high"
        
        # High urgency for high-value items
        if item_details.get("high_value"):
            return "high"
        
        # High urgency for stock-out events
        if data.get("action") == "stock_out":
            return "medium"
        
        return "low"

    def _assess_risk(self, data: Dict[str, Any]) -> Dict[str, Any]:
        risk_factors = []
        risk_score = 0
        
        # Check for high-value items
        if data.get("item_details", {}).get("high_value"):
            risk_factors.append("high_value_item")
            risk_score += 3
        
        # Check for large quantities
        if data.get("classification", {}).get("volume_category") == "bulk":
            risk_factors.append("bulk_transaction")
            risk_score += 2
        
        # Check for after-hours activity
        if not data.get("business_context", {}).get("is_business_hours"):
            risk_factors.append("after_hours")
            risk_score += 1
        
        # Check for perishable items
        if data.get("item_details", {}).get("perishable"):
            risk_factors.append("perishable_item")
            risk_score += 1
        
        risk_level = "low"
        if risk_score >= 5:
            risk_level = "high"
        elif risk_score >= 3:
            risk_level = "medium"
        
        return {
            "score": risk_score,
            "level": risk_level,
            "factors": risk_factors,
        }

    def _get_seasonal_context(self, data: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = data.get("timestamp_parsed")
        if not timestamp:
            return {}
        
        month = timestamp.month
        
        # Define seasons
        if month in [12, 1, 2]:
            season = "winter"
        elif month in [3, 4, 5]:
            season = "spring"
        elif month in [6, 7, 8]:
            season = "summer"
        else:
            season = "fall"
        
        # Seasonal demand patterns
        seasonal_demand = "normal"
        category = data.get("item_details", {}).get("category", "")
        
        if season == "winter" and category == "Clothing":
            seasonal_demand = "high"
        elif season == "summer" and category == "Electronics":
            seasonal_demand = "high"
        
        return {
            "season": season,
            "month": month,
            "seasonal_demand": seasonal_demand,
        }