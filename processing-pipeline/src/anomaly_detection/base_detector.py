import abc
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import numpy as np
from collections import deque, defaultdict
import structlog

logger = structlog.get_logger(__name__)


class AnomalyResult:
    def __init__(
        self,
        is_anomaly: bool,
        confidence: float,
        anomaly_type: str,
        details: Dict[str, Any],
        severity: str = "medium",
    ):
        self.is_anomaly = is_anomaly
        self.confidence = confidence
        self.anomaly_type = anomaly_type
        self.details = details
        self.severity = severity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_anomaly": self.is_anomaly,
            "confidence": self.confidence,
            "anomaly_type": self.anomaly_type,
            "details": self.details,
            "severity": self.severity,
        }


class BaseAnomalyDetector(abc.ABC):
    def __init__(
        self,
        window_size: int = 1000,
        confidence_threshold: float = 0.8,
        redis_client=None,
    ):
        self.window_size = window_size
        self.confidence_threshold = confidence_threshold
        self.redis_client = redis_client
        
        # In-memory data structures for pattern analysis
        self.data_window = deque(maxlen=window_size)
        self.time_series = defaultdict(lambda: deque(maxlen=100))
        self.pattern_cache = {}
        
        # Statistical thresholds
        self.z_score_threshold = 3.0
        self.iqr_multiplier = 1.5

    @abc.abstractmethod
    def detect(self, data: Dict[str, Any]) -> AnomalyResult:
        pass

    def batch_detect(self, data_batch: List[Dict[str, Any]]) -> List[AnomalyResult]:
        results = []
        for data in data_batch:
            result = self.detect(data)
            results.append(result)
        return results

    def _add_to_window(self, data: Dict[str, Any]):
        self.data_window.append(data)

    def _get_historical_data(self, key: str, hours: int = 24) -> List[Any]:
        # Try Redis first for historical data
        if self.redis_client:
            try:
                # Implementation would query Redis for historical data
                pass
            except Exception as e:
                logger.warning("Redis query failed", error=str(e))
        
        # Fallback to in-memory time series
        return list(self.time_series[key])

    def _calculate_z_score(self, value: float, historical_values: List[float]) -> float:
        if len(historical_values) < 3:
            return 0.0
        
        mean = np.mean(historical_values)
        std = np.std(historical_values)
        
        if std == 0:
            return 0.0
        
        return abs((value - mean) / std)

    def _calculate_iqr_outlier(self, value: float, historical_values: List[float]) -> bool:
        if len(historical_values) < 4:
            return False
        
        q1 = np.percentile(historical_values, 25)
        q3 = np.percentile(historical_values, 75)
        iqr = q3 - q1
        
        lower_bound = q1 - (self.iqr_multiplier * iqr)
        upper_bound = q3 + (self.iqr_multiplier * iqr)
        
        return value < lower_bound or value > upper_bound

    def _detect_time_based_anomaly(self, data: Dict[str, Any]) -> Optional[AnomalyResult]:
        timestamp = data.get("timestamp_parsed")
        if not timestamp:
            return None
        
        hour = timestamp.hour
        day_of_week = timestamp.weekday()
        
        # Check for unusual timing patterns
        business_context = data.get("business_context", {})
        
        # Activity during unusual hours
        if not business_context.get("is_business_hours"):
            # Check if this is unusual for this type of activity
            activity_type = data.get("action", "unknown")
            historical_after_hours = self._get_after_hours_frequency(activity_type)
            
            if historical_after_hours < 0.1:  # Less than 10% of activity after hours
                return AnomalyResult(
                    is_anomaly=True,
                    confidence=0.7,
                    anomaly_type="unusual_timing",
                    details={
                        "reason": "activity_after_hours",
                        "hour": hour,
                        "expected_frequency": historical_after_hours,
                    },
                    severity="medium",
                )
        
        return None

    def _detect_volume_anomaly(
        self, data: Dict[str, Any], value_field: str = "quantity_abs"
    ) -> Optional[AnomalyResult]:
        current_value = data.get(value_field)
        if current_value is None:
            return None
        
        current_value = float(current_value)
        
        # Get historical values for this type of transaction
        key = self._get_pattern_key(data)
        historical_values = [
            float(d.get(value_field, 0)) 
            for d in self.data_window 
            if self._matches_pattern(d, data) and d.get(value_field) is not None
        ]
        
        if len(historical_values) < 5:
            return None
        
        # Calculate z-score
        z_score = self._calculate_z_score(current_value, historical_values)
        
        if z_score > self.z_score_threshold:
            return AnomalyResult(
                is_anomaly=True,
                confidence=min(z_score / self.z_score_threshold, 1.0),
                anomaly_type="volume_anomaly",
                details={
                    "z_score": z_score,
                    "current_value": current_value,
                    "historical_mean": np.mean(historical_values),
                    "historical_std": np.std(historical_values),
                },
                severity="high" if z_score > 5 else "medium",
            )
        
        return None

    def _detect_frequency_anomaly(self, data: Dict[str, Any]) -> Optional[AnomalyResult]:
        key = self._get_pattern_key(data)
        current_time = data.get("timestamp_parsed")
        
        if not current_time:
            return None
        
        # Count recent events of same type
        recent_window = current_time - timedelta(hours=1)
        recent_count = sum(
            1 for d in self.data_window
            if (
                self._matches_pattern(d, data) and
                d.get("timestamp_parsed") and
                d.get("timestamp_parsed") > recent_window
            )
        )
        
        # Get historical hourly frequencies
        historical_hourly_counts = self._get_historical_frequencies(key)
        
        if len(historical_hourly_counts) < 5:
            return None
        
        # Check if current frequency is anomalous
        z_score = self._calculate_z_score(recent_count, historical_hourly_counts)
        
        if z_score > self.z_score_threshold:
            return AnomalyResult(
                is_anomaly=True,
                confidence=min(z_score / self.z_score_threshold, 1.0),
                anomaly_type="frequency_anomaly",
                details={
                    "recent_count": recent_count,
                    "z_score": z_score,
                    "historical_mean": np.mean(historical_hourly_counts),
                },
                severity="medium",
            )
        
        return None

    def _get_pattern_key(self, data: Dict[str, Any]) -> str:
        # Generate a key for pattern matching
        return f"{data.get('action', 'unknown')}_{data.get('item_id', 'unknown')}"

    def _matches_pattern(self, d1: Dict[str, Any], d2: Dict[str, Any]) -> bool:
        # Check if two data points match the same pattern
        return (
            d1.get("action") == d2.get("action") and
            d1.get("item_id") == d2.get("item_id")
        )

    def _get_after_hours_frequency(self, activity_type: str) -> float:
        # Calculate what percentage of this activity type happens after hours
        total_count = sum(
            1 for d in self.data_window
            if d.get("action") == activity_type
        )
        
        if total_count == 0:
            return 0.5  # Unknown, assume moderate
        
        after_hours_count = sum(
            1 for d in self.data_window
            if (
                d.get("action") == activity_type and
                not d.get("business_context", {}).get("is_business_hours", True)
            )
        )
        
        return after_hours_count / total_count

    def _get_historical_frequencies(self, pattern_key: str) -> List[int]:
        # Mock implementation - in real system, query from Redis/database
        # Return hourly counts for the past several days
        return [5, 7, 3, 8, 6, 4, 9, 2, 6, 7]  # Mock data