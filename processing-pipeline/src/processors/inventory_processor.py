from typing import Dict, Any
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger(__name__)


class InventoryProcessor:
    def __init__(self):
        self.action_mappings = {
            "stock_in": "inbound",
            "stock_out": "outbound", 
            "adjustment": "adjustment",
            "transfer": "transfer",
        }

    def process(self, data: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        processed_data = data.copy()
        
        # Add processing metadata
        processed_data["processing"] = {
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "processor": "inventory_processor",
            "kafka_metadata": metadata,
        }
        
        # Normalize action
        if "action" in processed_data:
            processed_data["normalized_action"] = self.action_mappings.get(
                processed_data["action"], processed_data["action"]
            )
        
        # Calculate derived fields
        processed_data["quantity_abs"] = abs(float(processed_data.get("quantity", 0)))
        
        # Add quantity direction
        quantity = float(processed_data.get("quantity", 0))
        if processed_data.get("action") == "stock_out":
            processed_data["quantity_direction"] = "negative"
            processed_data["quantity_normalized"] = -abs(quantity)
        else:
            processed_data["quantity_direction"] = "positive"
            processed_data["quantity_normalized"] = abs(quantity)
        
        # Parse and normalize timestamp
        processed_data["timestamp_parsed"] = self._parse_timestamp(
            processed_data.get("timestamp")
        )
        
        # Add business hour classification
        processed_data["business_context"] = self._get_business_context(
            processed_data["timestamp_parsed"]
        )
        
        # Calculate value if unit_price is available
        if "unit_price" in processed_data:
            processed_data["total_value"] = (
                processed_data["quantity_abs"] * float(processed_data["unit_price"])
            )
        
        logger.debug(
            "Processed inventory data",
            item_id=processed_data.get("item_id"),
            action=processed_data.get("action"),
            quantity=processed_data.get("quantity"),
        )
        
        return processed_data

    def _parse_timestamp(self, timestamp: Any) -> datetime:
        if isinstance(timestamp, datetime):
            return timestamp
        
        if isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        
        if isinstance(timestamp, str):
            try:
                # Try ISO format first
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                try:
                    # Try timestamp format
                    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
                except ValueError:
                    logger.warning("Unable to parse timestamp", timestamp=timestamp)
                    return datetime.now(timezone.utc)
        
        return datetime.now(timezone.utc)

    def _get_business_context(self, timestamp: datetime) -> Dict[str, Any]:
        hour = timestamp.hour
        day_of_week = timestamp.weekday()  # 0 = Monday, 6 = Sunday
        
        context = {
            "hour": hour,
            "day_of_week": day_of_week,
            "is_business_hours": 8 <= hour <= 18 and day_of_week < 5,
            "is_weekend": day_of_week >= 5,
            "shift": self._get_shift(hour),
        }
        
        return context

    def _get_shift(self, hour: int) -> str:
        if 6 <= hour < 14:
            return "morning"
        elif 14 <= hour < 22:
            return "afternoon"
        else:
            return "night"