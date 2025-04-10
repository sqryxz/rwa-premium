from ondo_tracker import OndoTracker
import argparse
import json
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description='ONDO Premium/Discount Tracker')
    parser.add_argument('--timeframe', type=str, default='daily',
                      choices=['daily', 'weekly', 'monthly', 'all'],
                      help='Timeframe for report generation')
    parser.add_argument('--report-only', action='store_true',
                      help='Only generate report without fetching new data')
    args = parser.parse_args()
    
    tracker = OndoTracker()
    
    if not args.report_only:
        print("Fetching current ONDO data...")
        current_data = tracker.run_tracker()
        if current_data:
            print("\nCurrent Data:")
            print(json.dumps(current_data, indent=2))
    
    print(f"\nGenerating {args.timeframe} report...")
    report = tracker.generate_report(args.timeframe)
    print("\nReport:")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main() 