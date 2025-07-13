from typing import Dict, List, Any
from datetime import datetime, timedelta
from collections import defaultdict
import structlog

from .base_aggregator import BaseAggregator

logger = structlog.get_logger(__name__)


class InventoryAggregator(BaseAggregator):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Track running totals and counters
        self.running_metrics = {
            "total_transactions": 0,
            "total_volume": 0,
            "total_value": 0,
            "item_counts": defaultdict(int),
            "location_counts": defaultdict(int),
            "action_counts": defaultdict(int),
            "supplier_counts": defaultdict(int),
        }
    
    def aggregate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = data.get("timestamp_parsed", datetime.now())
        
        # Update running metrics
        self._update_running_metrics(data)
        
        # Generate aggregated metrics for different time windows
        aggregated_metrics = {
            "timestamp": timestamp.isoformat(),
            "window_metrics": {},
            "running_totals": self._get_running_totals(),
            "top_items": self._get_top_items(),
            "location_distribution": self._get_location_distribution(),
            "action_distribution": self._get_action_distribution(),
            "supplier_metrics": self._get_supplier_metrics(),
            "volume_metrics": self._calculate_volume_metrics(),
            "value_metrics": self._calculate_value_metrics(),
            "throughput_metrics": self._calculate_throughput_metrics(),
            "quality_metrics": self._calculate_quality_metrics(),
        }
        
        # Calculate metrics for each time window
        for window_name in self.time_windows.keys():
            window_data = self.get_windowed_data(window_name)
            aggregated_metrics["window_metrics"][window_name] = self._aggregate_window_data(
                window_data, window_name
            )
        
        return aggregated_metrics
    
    def _update_running_metrics(self, data: Dict[str, Any]):
        # Update counters
        self.running_metrics["total_transactions"] += 1
        
        quantity = data.get("quantity_abs", 0)
        self.running_metrics["total_volume"] += quantity
        
        value = data.get("total_value", 0)
        if value:
            self.running_metrics["total_value"] += value
        
        # Update categorical counts
        item_id = data.get("item_id")
        if item_id:
            self.running_metrics["item_counts"][item_id] += 1
        
        location_id = data.get("location_id")
        if location_id:
            self.running_metrics["location_counts"][location_id] += 1
        
        action = data.get("action")
        if action:
            self.running_metrics["action_counts"][action] += 1
        
        supplier = data.get("item_details", {}).get("supplier")
        if supplier:
            self.running_metrics["supplier_counts"][supplier] += 1
    
    def _get_running_totals(self) -> Dict[str, Any]:
        return {
            "total_transactions": self.running_metrics["total_transactions"],
            "total_volume": self.running_metrics["total_volume"],
            "total_value": self.running_metrics["total_value"],
            "unique_items": len(self.running_metrics["item_counts"]),
            "unique_locations": len(self.running_metrics["location_counts"]),
            "unique_suppliers": len(self.running_metrics["supplier_counts"]),
        }
    
    def _get_top_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        sorted_items = sorted(
            self.running_metrics["item_counts"].items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [
            {"item_id": item_id, "transaction_count": count}
            for item_id, count in sorted_items[:limit]
        ]
    
    def _get_location_distribution(self) -> Dict[str, Any]:
        total_transactions = self.running_metrics["total_transactions"]
        if total_transactions == 0:
            return {}
        
        distribution = {}
        for location_id, count in self.running_metrics["location_counts"].items():
            distribution[location_id] = {
                "count": count,
                "percentage": (count / total_transactions) * 100
            }
        
        return distribution
    
    def _get_action_distribution(self) -> Dict[str, Any]:
        total_transactions = self.running_metrics["total_transactions"]
        if total_transactions == 0:
            return {}
        
        distribution = {}
        for action, count in self.running_metrics["action_counts"].items():
            distribution[action] = {
                "count": count,
                "percentage": (count / total_transactions) * 100
            }
        
        return distribution
    
    def _get_supplier_metrics(self) -> Dict[str, Any]:
        supplier_data = {}
        
        for supplier, count in self.running_metrics["supplier_counts"].items():
            supplier_data[supplier] = {
                "transaction_count": count,
                "percentage": (count / self.running_metrics["total_transactions"]) * 100
                if self.running_metrics["total_transactions"] > 0 else 0
            }
        
        return supplier_data
    
    def _calculate_volume_metrics(self) -> Dict[str, Any]:
        # Get volume data from current window
        current_data = self.get_windowed_data("5min")
        
        if not current_data:
            return {"error": "no_data"}
        
        volumes = [d.get("quantity_abs", 0) for d in current_data]
        
        # Calculate basic statistics
        stats = self.calculate_basic_stats(volumes)
        
        # Calculate percentiles
        percentiles = self.calculate_percentiles(volumes)
        
        # Calculate volume by action type
        volume_by_action = defaultdict(list)
        for d in current_data:
            action = d.get("action", "unknown")
            volume_by_action[action].append(d.get("quantity_abs", 0))
        
        action_stats = {}
        for action, action_volumes in volume_by_action.items():
            action_stats[action] = self.calculate_basic_stats(action_volumes)
        
        return {
            "overall": {**stats, **percentiles},
            "by_action": action_stats,
            "trend": self.get_trend_direction(volumes),
        }
    
    def _calculate_value_metrics(self) -> Dict[str, Any]:
        current_data = self.get_windowed_data("5min")
        
        if not current_data:
            return {"error": "no_data"}
        
        values = [d.get("total_value", 0) for d in current_data if d.get("total_value")]
        
        if not values:
            return {"error": "no_value_data"}
        
        stats = self.calculate_basic_stats(values)
        percentiles = self.calculate_percentiles(values)
        
        # High-value transaction detection
        high_value_threshold = stats.get("mean", 0) + (2 * stats.get("std", 0))
        high_value_count = sum(1 for v in values if v > high_value_threshold)
        
        return {
            "overall": {**stats, **percentiles},
            "high_value_transactions": {
                "count": high_value_count,
                "threshold": high_value_threshold,
                "percentage": (high_value_count / len(values)) * 100,
            },
            "trend": self.get_trend_direction(values),
        }
    
    def _calculate_throughput_metrics(self) -> Dict[str, Any]:
        metrics = {}
        
        # Calculate throughput for different time windows
        for window_name, window in self.time_windows.items():
            window_data = window.get_data()
            
            if not window_data:
                continue
            
            transaction_count = len(window_data)
            total_volume = sum(d.get("quantity_abs", 0) for d in window_data)
            
            # Calculate rates per minute
            window_minutes = self.time_windows[window_name].window_size.total_seconds() / 60
            
            metrics[window_name] = {
                "transactions_per_minute": transaction_count / window_minutes,
                "volume_per_minute": total_volume / window_minutes,
                "transaction_count": transaction_count,
                "total_volume": total_volume,
            }
        
        return metrics
    
    def _calculate_quality_metrics(self) -> Dict[str, Any]:
        current_data = self.get_windowed_data("5min")
        
        if not current_data:
            return {"error": "no_data"}
        
        total_transactions = len(current_data)
        
        # Count transactions with missing or invalid data
        missing_item_id = sum(1 for d in current_data if not d.get("item_id"))
        missing_location = sum(1 for d in current_data if not d.get("location_id"))
        invalid_quantity = sum(
            1 for d in current_data 
            if not isinstance(d.get("quantity_abs"), (int, float)) or d.get("quantity_abs", 0) <= 0
        )
        
        # Count anomalies
        anomaly_count = sum(
            1 for d in current_data 
            if d.get("anomaly_detected", False)
        )
        
        # Calculate quality scores
        quality_metrics = {
            "data_completeness": {
                "item_id_completeness": ((total_transactions - missing_item_id) / total_transactions) * 100,
                "location_completeness": ((total_transactions - missing_location) / total_transactions) * 100,
                "quantity_validity": ((total_transactions - invalid_quantity) / total_transactions) * 100,
            },
            "anomaly_rate": (anomaly_count / total_transactions) * 100,
            "overall_quality_score": self._calculate_overall_quality_score(
                missing_item_id, missing_location, invalid_quantity, anomaly_count, total_transactions
            ),
        }
        
        return quality_metrics
    
    def _calculate_overall_quality_score(
        self, missing_item: int, missing_location: int, invalid_qty: int, 
        anomalies: int, total: int
    ) -> float:
        if total == 0:
            return 100.0
        
        # Weight different quality issues
        weights = {
            "missing_item": 0.3,
            "missing_location": 0.2,
            "invalid_quantity": 0.3,
            "anomalies": 0.2,
        }
        
        quality_score = 100.0
        quality_score -= (missing_item / total) * 100 * weights["missing_item"]
        quality_score -= (missing_location / total) * 100 * weights["missing_location"]
        quality_score -= (invalid_qty / total) * 100 * weights["invalid_quantity"]
        quality_score -= (anomalies / total) * 100 * weights["anomalies"]
        
        return max(quality_score, 0.0)
    
    def _aggregate_window_data(self, window_data: List[Dict[str, Any]], window_name: str) -> Dict[str, Any]:
        if not window_data:
            return {"error": "no_data", "window": window_name}
        
        # Basic aggregation for the window
        transaction_count = len(window_data)
        total_volume = sum(d.get("quantity_abs", 0) for d in window_data)
        total_value = sum(d.get("total_value", 0) for d in window_data if d.get("total_value"))
        
        # Action distribution
        action_counts = defaultdict(int)
        for d in window_data:
            action = d.get("action", "unknown")
            action_counts[action] += 1
        
        # Calculate time range
        timestamps = [d.get("timestamp_parsed") for d in window_data if d.get("timestamp_parsed")]
        if timestamps:
            time_range = {
                "start": min(timestamps).isoformat(),
                "end": max(timestamps).isoformat(),
            }
        else:
            time_range = {}
        
        return {
            "window": window_name,
            "time_range": time_range,
            "transaction_count": transaction_count,
            "total_volume": total_volume,
            "total_value": total_value,
            "average_volume_per_transaction": total_volume / transaction_count if transaction_count > 0 else 0,
            "action_distribution": dict(action_counts),
            "unique_items": len(set(d.get("item_id") for d in window_data if d.get("item_id"))),
            "unique_locations": len(set(d.get("location_id") for d in window_data if d.get("location_id"))),
        }