import time
import functools
from typing import Callable, Any, Optional
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def retry_with_backoff(
    retries: int = 3,
    backoff_in_seconds: int = 1,
    max_backoff_in_seconds: int = 30,
    exponential: bool = True
) -> Callable:
    """
    Retry decorator with exponential backoff
    
    Args:
        retries: Number of times to retry
        backoff_in_seconds: Initial backoff time
        max_backoff_in_seconds: Maximum backoff time
        exponential: Whether to use exponential backoff
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Convert backoff time to milliseconds for more precise waiting
            temp_backoff = backoff_in_seconds
            
            for i in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == retries:
                        logger.error(f"Failed after {retries} retries: {str(e)}")
                        raise
                    
                    wait = min(
                        temp_backoff * (2 ** i if exponential else 1),
                        max_backoff_in_seconds
                    )
                    
                    logger.warning(
                        f"Error on attempt {i + 1}/{retries + 1}: {str(e)}. "
                        f"Retrying in {wait} seconds..."
                    )
                    
                    time.sleep(wait)
            return None
        return wrapper
    return decorator

def calculate_weighted_average(prices: list[tuple[float, float]]) -> Optional[float]:
    """
    Calculate weighted average price from a list of (price, volume) tuples
    """
    if not prices:
        return None
        
    total_volume = sum(volume for _, volume in prices)
    if total_volume == 0:
        return None
        
    weighted_sum = sum(price * volume for price, volume in prices)
    return weighted_sum / total_volume

def format_number(num: float, decimals: int = 2) -> str:
    """Format number with thousand separators and fixed decimals"""
    return f"{num:,.{decimals}f}" 