import os
import json
from datetime import datetime
from dotenv import load_dotenv
from data_fetchers import CentrifugeDataFetcher
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_centrifuge_api():
    """Test Centrifuge API data fetching"""
    load_dotenv()
    
    fetcher = CentrifugeDataFetcher()
    
    # Test 1: Get list of active pools
    logger.info("Testing active pools fetching...")
    active_pools = fetcher.list_active_pools()
    if active_pools:
        logger.info(f"Found {len(active_pools)} active pools")
        for pool in active_pools:
            logger.info(f"Pool: {pool['name']} (ID: {pool['id']}, Currency: {pool['currency']['symbol']})")
    else:
        logger.error("No active pools found or error fetching pools")
        return

    # Test 2: Get pool data for each active pool
    logger.info("\nTesting pool data fetching...")
    for pool in active_pools[:2]:  # Test first 2 pools to avoid rate limits
        pool_id = pool['id']
        logger.info(f"\nFetching data for pool {pool['name']} ({pool_id})")
        
        pool_data = fetcher.get_pool_data(pool_id)
        if pool_data:
            logger.info("Pool Metrics:")
            logger.info(f"DROP Price: ${pool_data['drop_price']:.4f}")
            logger.info(f"TIN Price: ${pool_data['tin_price']:.4f}")
            logger.info(f"NAV per Token: ${pool_data['nav_per_token']:.4f}")
            
            metrics = pool_data['pool_metrics']
            logger.info("\nDetailed Metrics:")
            logger.info(f"NAV: ${metrics['nav']:.2f}")
            logger.info(f"Reserve: ${metrics['reserve']:.2f}")
            logger.info(f"Outstanding Orders: ${metrics['outstanding_orders']:.2f}")
            logger.info(f"Senior Interest Rate: {metrics['senior_interest_rate']:.2%}")
            logger.info(f"Total Portfolio Value: ${metrics['total_portfolio_value']:.2f}")
            logger.info(f"Number of Assets: {metrics['num_assets']}")
            logger.info(f"Last Updated: {metrics['last_update']}")
        else:
            logger.error(f"Failed to fetch data for pool {pool_id}")

    # Test 3: Get CFG price
    logger.info("\nTesting CFG price fetching...")
    cfg_price = fetcher.get_cfg_price()
    if cfg_price:
        logger.info(f"CFG Price: ${cfg_price:.4f}")
    else:
        logger.error("Failed to fetch CFG price")

    # Test 4: Test error handling with invalid pool ID
    logger.info("\nTesting error handling with invalid pool ID...")
    invalid_pool_data = fetcher.get_pool_data("invalid_pool_id")
    if invalid_pool_data is None:
        logger.info("Error handling working correctly for invalid pool ID")
    else:
        logger.error("Error handling failed for invalid pool ID")

if __name__ == "__main__":
    test_centrifuge_api() 