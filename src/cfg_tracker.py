import os
import json
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, List, Optional
from pathlib import Path
import requests

class CFGTracker:
    def __init__(self, data_dir: str = "src/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_dir / "cfg_history.json"
        self.api_endpoint = "https://api.centrifuge.io/graphql"
        self.load_history()

    def load_history(self):
        """Load historical premium/discount data from file"""
        if self.history_file.exists():
            with open(self.history_file, 'r') as f:
                self.history = json.load(f)
        else:
            self.history = {}

    def save_history(self):
        """Save premium/discount data to file"""
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=4)

    def fetch_pool_data(self, pool_id):
        query = """
        {
            pool(id: "%s") {
                id
                name
                currency {
                    symbol
                    decimals
                }
                tranches {
                    nodes {
                        id
                        name
                        type
                        tokenPrice
                        tokenSupply
                    }
                }
            }
        }
        """ % pool_id
        
        response = requests.post(
            self.api_endpoint,
            json={'query': query}
        )
        return response.json()
    
    def calculate_premium_discount(self, token_price, nav=1.0):
        """Calculate premium/discount percentage relative to NAV"""
        token_price = float(token_price) / (10 ** 18)  # Convert from wei to DAI
        return ((token_price - nav) / nav) * 100
    
    def update_premium_history(self, pool_id):
        pool_data = self.fetch_pool_data(pool_id)
        
        if not os.path.exists(self.history_file):
            with open(self.history_file, 'w') as f:
                json.dump({}, f)
        
        with open(self.history_file, 'r') as f:
            history = json.load(f)
        
        pool = pool_data['data']['pool']
        current_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d"),
            "tranches": {}
        }
        
        for tranche in pool['data']['pool']['tranches']['nodes']:
            tranche_type = "junior" if "junior" in tranche['id'].lower() else "senior"
            token_type = "TIN" if tranche_type == "junior" else "DROP"
            
            token_price = float(tranche['tokenPrice']) / (10 ** 18)
            premium_discount = self.calculate_premium_discount(tranche['tokenPrice'])
            
            current_data["tranches"][tranche_type] = {
                "token_price": token_price,
                "nav": 1.0,
                "discount_premium_percentage": round(premium_discount, 2),
                "token_type": token_type
            }
        
        # Update the history
        if pool_id not in history:
            history[pool_id] = {
                "pool_name": pool['name'],
                "currency": pool['currency']['symbol'],
                "latest_update": current_data,
                "historical_data": []
            }
        else:
            history[pool_id]["historical_data"].append(history[pool_id]["latest_update"])
            history[pool_id]["latest_update"] = current_data
        
        with open(self.history_file, 'w') as f:
            json.dump(history, f, indent=2)
    
    def generate_premium_report(self, pool_id, timeframe="all"):
        """Generate a report of premium/discount statistics"""
        with open(self.history_file, 'r') as f:
            history = json.load(f)
        
        if pool_id not in history:
            return "No data available for this pool"
        
        pool_data = history[pool_id]
        all_data = [pool_data["latest_update"]] + pool_data["historical_data"]
        
        report = {
            "pool_name": pool_data["pool_name"],
            "currency": pool_data["currency"],
            "current_premium": {
                "junior": pool_data["latest_update"]["tranches"]["junior"]["discount_premium_percentage"],
                "senior": pool_data["latest_update"]["tranches"]["senior"]["discount_premium_percentage"]
            },
            "statistics": {
                "junior": self._calculate_statistics([d["tranches"]["junior"]["discount_premium_percentage"] for d in all_data]),
                "senior": self._calculate_statistics([d["tranches"]["senior"]["discount_premium_percentage"] for d in all_data])
            }
        }
        
        return report
    
    def _calculate_statistics(self, values):
        """Calculate basic statistics for a list of premium/discount values"""
        if not values:
            return None
            
        return {
            "average": sum(values) / len(values),
            "max": max(values),
            "min": min(values),
            "observations": len(values)
        }

    def record_premium(self, token: str, market_price: float, reference_price: float, timestamp: Optional[str] = None):
        """Record premium/discount for a token"""
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()

        premium_percent = ((market_price / reference_price) - 1) * 100
        
        if token not in self.history:
            self.history[token] = []
            
        self.history[token].append({
            'timestamp': timestamp,
            'market_price': market_price,
            'reference_price': reference_price,
            'premium_percent': premium_percent
        })
        
        self.save_history()

    def get_premium_stats(self, token: str, timeframe: str = 'all') -> Dict:
        """Get premium statistics for a token over a specific timeframe"""
        if not self.history:
            return {}

        # Extract data from the current structure
        data = []
        latest = self.history.get('latest_update', {}).get('tranches', {})
        historical = self.history.get('historical_data', [])
        
        # Process latest data
        if latest:
            for tranche_type, tranche_data in latest.items():
                if tranche_data['token_type'] == token:
                    data.append({
                        'timestamp': self.history['latest_update']['timestamp'],
                        'premium_percent': tranche_data['discount_premium_percentage']
                    })
        
        # Process historical data
        for hist in historical:
            tranches = hist.get('tranches', {})
            for tranche_type, tranche_data in tranches.items():
                if tranche_data['token_type'] == token:
                    data.append({
                        'timestamp': hist['timestamp'],
                        'premium_percent': tranche_data['discount_premium_percentage']
                    })

        if not data:
            return {}

        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)

        now = pd.Timestamp.now(tz='UTC')
        if timeframe == 'day':
            df = df[df.index > now - timedelta(days=1)]
        elif timeframe == 'week':
            df = df[df.index > now - timedelta(weeks=1)]
        elif timeframe == 'month':
            df = df[df.index > now - timedelta(days=30)]

        if len(df) == 0:
            return {}

        return {
            'current_premium': df['premium_percent'].iloc[-1],
            'avg_premium': df['premium_percent'].mean(),
            'max_premium': df['premium_percent'].max(),
            'min_premium': df['premium_percent'].min(),
            'std_dev': df['premium_percent'].std(),
            'num_observations': len(df),
            'premium_history': df['premium_percent'].tolist()
        }

    def generate_report(self, timeframe: str = 'all') -> Dict:
        """Generate a report of premium statistics for all tracked tokens"""
        report = {}
        # Generate stats for both DROP and TIN tokens
        report['DROP'] = self.get_premium_stats('DROP', timeframe)
        report['TIN'] = self.get_premium_stats('TIN', timeframe)
        return report

if __name__ == "__main__":
    tracker = CFGTracker()
    # Track Harbor Trade 2 pool
    tracker.update_premium_history("0x4ca805ce8ece2e63ffc1f9f8f2731d3f48df89df")
    report = tracker.generate_premium_report("0x4ca805ce8ece2e63ffc1f9f8f2731d3f48df89df")
    print(json.dumps(report, indent=2)) 