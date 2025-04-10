import os
import time
from datetime import datetime
from dotenv import load_dotenv
from premium_tracker import PremiumTracker
from data_fetchers import OndeDataFetcher, CentrifugeDataFetcher

def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize trackers and fetchers
    tracker = PremiumTracker()
    ondo_fetcher = OndeDataFetcher()
    centrifuge_fetcher = CentrifugeDataFetcher()
    
    # Example Centrifuge pool IDs (replace with actual pool IDs)
    pool_ids = ['pool1', 'pool2']
    
    while True:
        try:
            # Track ONDO/USDY premium
            ondo_price = ondo_fetcher.get_ondo_price()
            usdy_price = ondo_fetcher.get_usdy_price()
            
            if ondo_price and usdy_price:
                tracker.record_premium('ONDO/USDY', ondo_price, usdy_price)
                print(f"Recorded ONDO/USDY premium at {datetime.utcnow()}")
            
            # Track Centrifuge pools
            cfg_price = centrifuge_fetcher.get_cfg_price()
            
            for pool_id in pool_ids:
                pool_data = centrifuge_fetcher.get_pool_data(pool_id)
                if pool_data and cfg_price:
                    # Track DROP token premium
                    tracker.record_premium(
                        f"DROP_{pool_id}",
                        pool_data['drop_price'],
                        pool_data['nav_per_token']
                    )
                    
                    # Track TIN token premium
                    tracker.record_premium(
                        f"TIN_{pool_id}",
                        pool_data['tin_price'],
                        pool_data['nav_per_token']
                    )
                    
                    print(f"Recorded {pool_id} premiums at {datetime.utcnow()}")
            
            # Generate and print report
            report = tracker.generate_report('day')
            print("\nDaily Premium Report:")
            print("=" * 50)
            for token, stats in report.items():
                if stats:
                    print(f"\n{token}:")
                    print(f"Current Premium: {stats['current_premium']:.2f}%")
                    print(f"Average Premium: {stats['avg_premium']:.2f}%")
                    print(f"Range: {stats['min_premium']:.2f}% to {stats['max_premium']:.2f}%")
            
            # Wait for 1 hour before next update
            time.sleep(3600)
            
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(300)  # Wait 5 minutes before retrying

if __name__ == "__main__":
    main() 