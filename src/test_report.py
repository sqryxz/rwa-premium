import os
from dotenv import load_dotenv
from premium_tracker import PremiumTracker
from data_fetchers import OndeDataFetcher, CentrifugeDataFetcher
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_test_report():
    # Load environment variables
    load_dotenv()
    
    # Initialize trackers and fetchers
    tracker = PremiumTracker()
    ondo_fetcher = OndeDataFetcher()
    centrifuge_fetcher = CentrifugeDataFetcher()
    
    # Example Centrifuge pool IDs - using real pools from Tinlake
    pool_ids = [
        '0x53b2d22d07E069a3b132BfeaaD275b10273d381E',  # NewSilver
        '0x4cA805cE8EcE2E63FfC1F9f8F2731D3F48DF89Df'   # ConsolFreight
    ]
    
    try:
        logger.info("Starting test report...")
        
        # Track ONDO/USDY premium
        logger.info("Fetching ONDO/USDY data...")
        ondo_price = ondo_fetcher.get_ondo_price()
        usdy_price = ondo_fetcher.get_usdy_price()
        
        if ondo_price and usdy_price:
            tracker.record_premium('ONDO/USDY', ondo_price, usdy_price)
            logger.info(f"Recorded ONDO/USDY premium - ONDO: ${ondo_price:.4f}, USDY: ${usdy_price:.4f}")
        else:
            logger.warning("Could not fetch ONDO/USDY prices")
        
        # Track Centrifuge pools
        logger.info("Fetching Centrifuge data...")
        cfg_price = centrifuge_fetcher.get_cfg_price()
        if cfg_price:
            logger.info(f"CFG Price: ${cfg_price:.4f}")
        
        for pool_id in pool_ids:
            logger.info(f"Processing pool {pool_id}...")
            pool_data = centrifuge_fetcher.get_pool_data(pool_id)
            if pool_data:
                # Track DROP token premium
                if pool_data['drop_price'] and pool_data['nav_per_token']:
                    tracker.record_premium(
                        f"DROP_{pool_id}",
                        pool_data['drop_price'],
                        pool_data['nav_per_token']
                    )
                    logger.info(f"Recorded DROP premium for pool {pool_id}")
                
                # Track TIN token premium
                if pool_data['tin_price'] and pool_data['nav_per_token']:
                    tracker.record_premium(
                        f"TIN_{pool_id}",
                        pool_data['tin_price'],
                        pool_data['nav_per_token']
                    )
                    logger.info(f"Recorded TIN premium for pool {pool_id}")
            else:
                logger.warning(f"Could not fetch data for pool {pool_id}")
        
        # Generate and print report
        report = tracker.generate_report('all')
        print("\nPremium/Discount Report:")
        print("=" * 50)
        for token, stats in report.items():
            if stats:
                print(f"\n{token}:")
                print(f"Current Premium: {stats['current_premium']:.2f}%")
                print(f"Average Premium: {stats['avg_premium']:.2f}%")
                print(f"Range: {stats['min_premium']:.2f}% to {stats['max_premium']:.2f}%")
                print(f"Standard Deviation: {stats['std_dev']:.2f}%")
                print(f"Number of observations: {stats['num_observations']}")
        
    except Exception as e:
        logger.error(f"Error in test report: {e}")

if __name__ == "__main__":
    run_test_report() 