import abc
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque
import structlog

logger = structlog.get_logger(__name__)


class TimeWindow:
    def __init__(self, window_size: timedelta, slide_interval: timedelta = None):
        self.window_size = window_size
        self.slide_interval = slide_interval or window_size
        self.data = deque()
        
    def add(self, timestamp: datetime, data: Any):
        self.data.append((timestamp, data))
        self._cleanup_old_data(timestamp)
    
    def _cleanup_old_data(self, current_time: datetime):
        cutoff_time = current_time - self.window_size
        while self.data and self.data[0][0] < cutoff_time:
            self.data.popleft()
    
    def get_data(self) -> List[Any]:
        return [item[1] for item in self.data]
    
    def get_data_with_timestamps(self) -> List[tuple]:
        return list(self.data)


class BaseAggregator(abc.ABC):
    def __init__(
        self, 
        window_size: timedelta = timedelta(minutes=5),
        slide_interval: timedelta = None,
        redis_client = None
    ):
        self.window_size = window_size
        self.slide_interval = slide_interval or window_size
        self.redis_client = redis_client
        
        # Time windows for different aggregation types
        self.time_windows = {}
        self.metrics_cache = {}
        
        # Initialize windows
        self._initialize_windows()
    
    def _initialize_windows(self):
        # Create different time windows for various aggregations
        self.time_windows = {
            "1min": TimeWindow(timedelta(minutes=1)),
            "5min": TimeWindow(timedelta(minutes=5)),
            "15min": TimeWindow(timedelta(minutes=15)),
            "1hour": TimeWindow(timedelta(hours=1)),
        }
    
    @abc.abstractmethod
    def aggregate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    def process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = data.get("timestamp_parsed", datetime.now())
        
        # Add to all time windows
        for window in self.time_windows.values():
            window.add(timestamp, data)
        
        # Generate aggregated metrics
        aggregated_metrics = self.aggregate(data)
        
        # Store in cache and Redis
        self._cache_metrics(aggregated_metrics, timestamp)
        
        return aggregated_metrics
    
    def _cache_metrics(self, metrics: Dict[str, Any], timestamp: datetime):
        # Cache in memory
        cache_key = timestamp.strftime("%Y-%m-%d_%H-%M")
        self.metrics_cache[cache_key] = metrics
        
        # Store in Redis if available
        if self.redis_client:
            try:
                import json
                redis_key = f"metrics:{self.__class__.__name__}:{cache_key}"
                self.redis_client.setex(
                    redis_key,
                    3600,  # 1 hour TTL
                    json.dumps(metrics, default=str)
                )
            except Exception as e:
                logger.warning("Failed to cache metrics in Redis", error=str(e))
    
    def get_windowed_data(self, window_name: str) -> List[Any]:
        if window_name in self.time_windows:
            return self.time_windows[window_name].get_data()
        return []
    
    def calculate_basic_stats(self, values: List[float]) -> Dict[str, float]:
        if not values:
            return {"count": 0, "sum": 0, "mean": 0, "min": 0, "max": 0}
        
        import numpy as np
        
        return {
            "count": len(values),
            "sum": sum(values),
            "mean": np.mean(values),
            "min": min(values),
            "max": max(values),
            "std": np.std(values) if len(values) > 1 else 0,
            "median": np.median(values),
        }
    
    def calculate_percentiles(self, values: List[float], percentiles: List[int] = None) -> Dict[str, float]:
        if not values:
            return {}
        
        if percentiles is None:
            percentiles = [50, 75, 90, 95, 99]
        
        import numpy as np
        
        result = {}
        for p in percentiles:
            result[f"p{p}"] = np.percentile(values, p)
        
        return result
    
    def calculate_rate(self, current_count: int, previous_count: int, time_diff_seconds: float) -> float:
        if time_diff_seconds <= 0:
            return 0.0
        
        return (current_count - previous_count) / time_diff_seconds
    
    def get_trend_direction(self, values: List[float], min_points: int = 3) -> str:
        if len(values) < min_points:
            return "insufficient_data"
        
        # Simple trend calculation using linear regression slope
        import numpy as np
        
        x = np.arange(len(values))
        slope, _ = np.polyfit(x, values, 1)
        
        if slope > 0.1:
            return "increasing"
        elif slope < -0.1:
            return "decreasing"
        else:
            return "stable"