from typing import Dict, List, Any, Optional
import structlog

from .base_detector import BaseAnomalyDetector, AnomalyResult

logger = structlog.get_logger(__name__)


class InventoryAnomalyDetector(BaseAnomalyDetector):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Inventory-specific thresholds
        self.negative_stock_threshold = -10
        self.rapid_depletion_threshold = 0.8  # 80% of stock in short time
        self.unusual_location_threshold = 0.95
        
    def detect(self, data: Dict[str, Any]) -> AnomalyResult:
        # Add data to analysis window
        self._add_to_window(data)
        
        # Run various anomaly detection methods
        anomalies = []
        
        # 1. Volume-based anomalies
        volume_anomaly = self._detect_volume_anomaly(data)
        if volume_anomaly and volume_anomaly.is_anomaly:
            anomalies.append(volume_anomaly)
        
        # 2. Time-based anomalies
        time_anomaly = self._detect_time_based_anomaly(data)
        if time_anomaly and time_anomaly.is_anomaly:
            anomalies.append(time_anomaly)
        
        # 3. Frequency anomalies
        frequency_anomaly = self._detect_frequency_anomaly(data)
        if frequency_anomaly and frequency_anomaly.is_anomaly:
            anomalies.append(frequency_anomaly)
        
        # 4. Inventory-specific anomalies
        inventory_anomalies = self._detect_inventory_specific_anomalies(data)
        anomalies.extend(inventory_anomalies)
        
        # Return the most significant anomaly or no anomaly
        if not anomalies:
            return AnomalyResult(
                is_anomaly=False,
                confidence=0.0,
                anomaly_type="none",
                details={},
            )
        
        # Return the highest confidence anomaly
        best_anomaly = max(anomalies, key=lambda x: x.confidence)
        return best_anomaly

    def _detect_inventory_specific_anomalies(self, data: Dict[str, Any]) -> List[AnomalyResult]:
        anomalies = []
        
        # 1. Negative stock detection
        negative_stock = self._detect_negative_stock(data)
        if negative_stock:
            anomalies.append(negative_stock)
        
        # 2. Rapid stock depletion
        rapid_depletion = self._detect_rapid_depletion(data)
        if rapid_depletion:
            anomalies.append(rapid_depletion)
        
        # 3. Unusual location activity
        location_anomaly = self._detect_unusual_location_activity(data)
        if location_anomaly:
            anomalies.append(location_anomaly)
        
        # 4. High-value item anomalies
        high_value_anomaly = self._detect_high_value_anomalies(data)
        if high_value_anomaly:
            anomalies.append(high_value_anomaly)
        
        # 5. Supplier pattern anomalies
        supplier_anomaly = self._detect_supplier_anomalies(data)
        if supplier_anomaly:
            anomalies.append(supplier_anomaly)
        
        return anomalies

    def _detect_negative_stock(self, data: Dict[str, Any]) -> Optional[AnomalyResult]:
        action = data.get("action")
        quantity = data.get("quantity_normalized", 0)
        item_id = data.get("item_id")
        
        if action != "stock_out":
            return None
        
        # Simulate current stock level check
        current_stock = self._get_current_stock_level(item_id)
        projected_stock = current_stock + quantity  # quantity is negative for stock_out
        
        if projected_stock < self.negative_stock_threshold:
            return AnomalyResult(
                is_anomaly=True,
                confidence=0.9,
                anomaly_type="negative_stock_risk",
                details={
                    "current_stock": current_stock,
                    "transaction_quantity": abs(quantity),
                    "projected_stock": projected_stock,
                    "item_id": item_id,
                },
                severity="high",
            )
        
        return None

    def _detect_rapid_depletion(self, data: Dict[str, Any]) -> Optional[AnomalyResult]:
        item_id = data.get("item_id")
        current_time = data.get("timestamp_parsed")
        
        if not current_time or data.get("action") != "stock_out":
            return None
        
        # Calculate total stock out in last hour
        from datetime import timedelta
        recent_window = current_time - timedelta(hours=1)
        
        recent_depletions = [
            d.get("quantity_abs", 0) for d in self.data_window
            if (
                d.get("item_id") == item_id and
                d.get("action") == "stock_out" and
                d.get("timestamp_parsed") and
                d.get("timestamp_parsed") > recent_window
            )
        ]
        
        total_depleted = sum(recent_depletions)
        current_stock = self._get_current_stock_level(item_id)
        
        if current_stock > 0:
            depletion_rate = total_depleted / current_stock
            
            if depletion_rate > self.rapid_depletion_threshold:
                return AnomalyResult(
                    is_anomaly=True,
                    confidence=min(depletion_rate, 1.0),
                    anomaly_type="rapid_stock_depletion",
                    details={
                        "depletion_rate": depletion_rate,
                        "total_depleted_1h": total_depleted,
                        "current_stock": current_stock,
                        "transaction_count": len(recent_depletions),
                    },
                    severity="high",
                )
        
        return None

    def _detect_unusual_location_activity(self, data: Dict[str, Any]) -> Optional[AnomalyResult]:
        location_id = data.get("location_id")
        item_id = data.get("item_id")
        
        if not location_id or not item_id:
            return None
        
        # Check historical location patterns for this item
        historical_locations = [
            d.get("location_id") for d in self.data_window
            if (
                d.get("item_id") == item_id and
                d.get("location_id") is not None
            )
        ]
        
        if len(historical_locations) < 5:
            return None
        
        location_frequency = {}
        for loc in historical_locations:
            location_frequency[loc] = location_frequency.get(loc, 0) + 1
        
        total_transactions = len(historical_locations)
        current_location_freq = location_frequency.get(location_id, 0) / total_transactions
        
        if current_location_freq < (1 - self.unusual_location_threshold):
            return AnomalyResult(
                is_anomaly=True,
                confidence=1 - current_location_freq,
                anomaly_type="unusual_location",
                details={
                    "location_id": location_id,
                    "historical_frequency": current_location_freq,
                    "common_locations": sorted(
                        location_frequency.items(), 
                        key=lambda x: x[1], 
                        reverse=True
                    )[:3],
                },
                severity="medium",
            )
        
        return None

    def _detect_high_value_anomalies(self, data: Dict[str, Any]) -> Optional[AnomalyResult]:
        item_details = data.get("item_details", {})
        risk_assessment = data.get("risk_assessment", {})
        
        if not item_details.get("high_value"):
            return None
        
        # High-value items should have extra scrutiny
        risk_factors = risk_assessment.get("factors", [])
        
        # Check for multiple risk factors with high-value items
        high_risk_factors = ["after_hours", "bulk_transaction", "unusual_location"]
        present_high_risks = [f for f in risk_factors if f in high_risk_factors]
        
        if len(present_high_risks) >= 2:
            return AnomalyResult(
                is_anomaly=True,
                confidence=0.8,
                anomaly_type="high_value_risk_combination",
                details={
                    "item_value": item_details.get("unit_cost", 0),
                    "risk_factors": present_high_risks,
                    "total_value": data.get("total_value", 0),
                },
                severity="high",
            )
        
        return None

    def _detect_supplier_anomalies(self, data: Dict[str, Any]) -> Optional[AnomalyResult]:
        action = data.get("action")
        supplier = data.get("item_details", {}).get("supplier")
        
        if action != "stock_in" or not supplier:
            return None
        
        # Check if this supplier delivery pattern is unusual
        recent_deliveries = [
            d for d in self.data_window
            if (
                d.get("action") == "stock_in" and
                d.get("item_details", {}).get("supplier") == supplier
            )
        ]
        
        if len(recent_deliveries) < 3:
            return None
        
        # Check delivery timing patterns
        current_time = data.get("timestamp_parsed")
        if current_time:
            # Simplified pattern check - in real implementation, use more sophisticated timing analysis
            weekend_deliveries = sum(
                1 for d in recent_deliveries[-10:]  # Last 10 deliveries
                if d.get("business_context", {}).get("is_weekend", False)
            )
            
            if (
                data.get("business_context", {}).get("is_weekend") and
                weekend_deliveries / min(len(recent_deliveries), 10) < 0.1
            ):
                return AnomalyResult(
                    is_anomaly=True,
                    confidence=0.7,
                    anomaly_type="unusual_supplier_delivery_timing",
                    details={
                        "supplier": supplier,
                        "weekend_delivery_rate": weekend_deliveries / min(len(recent_deliveries), 10),
                        "is_weekend": True,
                    },
                    severity="low",
                )
        
        return None

    def _get_current_stock_level(self, item_id: str) -> float:
        # Mock implementation - in real system, query actual stock levels
        # Calculate based on recent transactions in window
        stock_changes = [
            d.get("quantity_normalized", 0) for d in self.data_window
            if d.get("item_id") == item_id
        ]
        
        # Start with a mock baseline stock level
        baseline_stock = hash(item_id) % 1000 + 100
        current_stock = baseline_stock + sum(stock_changes)
        
        return max(current_stock, 0)  # Stock can't go below 0 in this simulation