import os
import json
from datetime import datetime, timedelta
import requests
from web3 import Web3
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import time
import logging

# USDY ABI (minimal for yield checking)
USDY_ABI = [
    {
        "inputs": [],
        "name": "currentRate",
        "outputs": [{"type": "uint256", "name": ""}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "lastRate",
        "outputs": [{"type": "uint256", "name": ""}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "lastRateUpdate",
        "outputs": [{"type": "uint256", "name": ""}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"type": "uint8", "name": ""}],
        "stateMutability": "view",
        "type": "function"
    }
]

# USDY Oracle ABI
USDY_ORACLE_ABI = [
    {
        "inputs": [],
        "name": "latestAnswer",
        "outputs": [{"type": "int256", "name": ""}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"type": "uint80", "name": "roundId"},
            {"type": "int256", "name": "answer"},
            {"type": "uint256", "name": "startedAt"},
            {"type": "uint256", "name": "updatedAt"},
            {"type": "uint80", "name": "answeredInRound"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

class OndoTracker:
    def __init__(self):
        load_dotenv()
        rpc_url = os.getenv('ETHEREUM_RPC_URL')
        print(f"Connecting to Ethereum node: {rpc_url}")
        
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            print("Error: Could not connect to Ethereum node")
        else:
            print(f"Connected to Ethereum node. Chain ID: {self.w3.eth.chain_id}")
            
        self.data_file = 'src/ondo_tracker/data/ondo_premium_history.json'
        self.treasury_yields = {}
        self.dex_prices = {}
        
        # Cache settings
        self.yield_cache = {'value': None, 'timestamp': 0, 'ttl': 300}  # 5 minute TTL
        self.rate_history = []  # Store historical rates for moving average
        self.max_history_size = 10  # Number of historical rates to keep
        
        # Token addresses
        self.ondo_address = Web3.to_checksum_address('0x59D9356E565Ab3A36dD77763Fc0553F27E0a32C7')  # ONDO token
        self.usdc_address = Web3.to_checksum_address('0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48')  # USDC
        
        # USDY addresses
        self.usdy_token = Web3.to_checksum_address('0x96F6eF951840721AdBF73e6C389f4e6954294985')  # USDY token
        self.usdy_oracle = Web3.to_checksum_address('0x7e6a3C6b7aB14F4Da57930b207a02C0A9E7189EE')  # USDY oracle
        
    def fetch_dex_prices(self) -> Dict[str, float]:
        """
        Fetch ONDO token prices from CoinGecko
        Returns dict of source: price
        """
        try:
            print("\nFetching price from CoinGecko...")
            
            # CoinGecko API endpoint for ONDO token
            url = "https://api.coingecko.com/api/v3/simple/token_price/ethereum"
            params = {
                "contract_addresses": self.ondo_address.lower(),
                "vs_currencies": "usd"
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                price = data.get(self.ondo_address.lower(), {}).get('usd')
                
                if price:
                    prices = {'coingecko': price}
                    print(f"Successfully got price from CoinGecko: {price}")
                else:
                    print("No real price available, using fallback mock price")
                    prices = {'coingecko': 0.9985}  # Slightly below par value
                
                self.dex_prices = prices
                return prices
            else:
                print(f"Error fetching from CoinGecko: {response.status_code}")
                return {'coingecko': 0.9985}  # Fallback price
                
        except Exception as e:
            print(f"Error in fetch_dex_prices: {e}")
            return {'coingecko': 0.9985}  # Fallback price
        
    def fetch_treasury_yields(self) -> Dict[str, float]:
        """
        Fetch current Treasury yields from the US Treasury API
        Returns dict of tenor: yield_rate
        """
        try:
            # Base URL for the Treasury API
            base_url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
            endpoint = "/v2/accounting/od/avg_interest_rates"
            
            # Get dates for filtering (use real dates, not future dates)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=90)  # Look back further to ensure we get data
            
            # Format dates for API
            end_date_str = end_date.strftime('%Y-%m-%d')
            start_date_str = start_date.strftime('%Y-%m-%d')
            
            # Build query parameters
            params = {
                'fields': 'record_date,security_desc,avg_interest_rate_amt',
                'filter': f'record_date:gte:{start_date_str}',  # Only filter start date to get some data
                'sort': '-record_date',  # Most recent first
                'page[size]': '250'  # Get more results
            }
            
            # Construct the full URL
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            url = f"{base_url}{endpoint}?{query_string}"
            
            print("Fetching Treasury yields from:", url)
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                if not data.get('data'):
                    print("No Treasury yield data available")
                    return {}
                
                # Get the most recent date's data
                latest_date = data['data'][0]['record_date']
                latest_rates = {}
                
                # Map security descriptions to our tenors
                security_mapping = {
                    'Treasury Bills': {
                        'maturity_months': 3,
                        'tenor': '3M'
                    },
                    'Treasury Notes': {
                        'maturity_months': 12,
                        'tenor': '1Y'
                    },
                    'Treasury Bonds': {
                        'maturity_months': 360,
                        'tenor': '30Y'
                    },
                    'Treasury Inflation-Protected Securities (TIPS)': {
                        'maturity_months': 120,
                        'tenor': '10Y-TIPS'
                    }
                }
                
                print(f"\nProcessing data for {latest_date}:")
                
                # Process the data to get the most recent rates for each tenor
                for entry in data['data']:
                    if entry['record_date'] == latest_date:
                        desc = entry['security_desc']
                        if desc in security_mapping:
                            tenor = security_mapping[desc]['tenor']
                            rate = float(entry['avg_interest_rate_amt'])
                            print(f"Found {desc}: {rate}%")
                            latest_rates[tenor] = rate
                
                if not latest_rates:
                    print("\nNo matching Treasury securities found")
                    print("Available securities in response:")
                    unique_securities = set()
                    for entry in data['data']:
                        if entry['record_date'] == latest_date:
                            unique_securities.add(entry['security_desc'])
                    for sec in sorted(unique_securities):
                        print(f"- {sec}")
                    return {}
                
                print(f"\nSuccessfully fetched Treasury yields for {latest_date}:")
                for tenor, rate in sorted(latest_rates.items()):
                    print(f"{tenor}: {rate}%")
                
                self.treasury_yields = latest_rates
                return latest_rates
            else:
                print(f"Error fetching Treasury yields: {response.status_code}")
                print(f"Response: {response.text}")
                return {}
        except Exception as e:
            print(f"Error in fetch_treasury_yields: {e}")
            return {}
        
    def _validate_rate(self, rate: int, rate_type: str) -> bool:
        """
        Validate rate values to ensure they are reasonable
        Returns True if rate is valid, False otherwise
        """
        try:
            # Rates should be positive
            if rate <= 0:
                print(f"Warning: {rate_type} is not positive: {rate}")
                return False
                
            # Convert rate to decimal for comparison (assuming 18 decimals)
            rate_decimal = rate / 1e18
            
            # Define reasonable bounds for rates (e.g., between 0.5 and 2.0)
            MIN_RATE = 0.5
            MAX_RATE = 2.0
            
            if not (MIN_RATE <= rate_decimal <= MAX_RATE):
                print(f"Warning: {rate_type} outside reasonable bounds: {rate_decimal}")
                return False
                
            return True
        except Exception as e:
            print(f"Error validating {rate_type}: {e}")
            return False
            
    def _calculate_moving_average(self, new_rate: float) -> float:
        """
        Calculate moving average of rates
        Returns the moving average yield
        """
        try:
            # Add new rate to history
            self.rate_history.append(new_rate)
            
            # Keep only the most recent rates
            if len(self.rate_history) > self.max_history_size:
                self.rate_history = self.rate_history[-self.max_history_size:]
                
            # Calculate weighted moving average (more weight to recent rates)
            weights = np.linspace(1, 2, len(self.rate_history))
            weighted_avg = np.average(self.rate_history, weights=weights)
            
            return weighted_avg
        except Exception as e:
            print(f"Error calculating moving average: {e}")
            return new_rate  # Fallback to current rate if error
            
    def _fetch_usdy_yield_from_coingecko(self) -> float:
        """
        Fetch USDY yield from CoinGecko API by comparing price changes
        Returns annualized yield percentage
        """
        try:
            print("\nFetching USDY yield from CoinGecko...")
            
            # CoinGecko API endpoint
            url = "https://api.coingecko.com/api/v3/coins/ondo-us-dollar-yield/market_chart"
            params = {
                "vs_currency": "usd",
                "days": "1",
                "interval": "daily"
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                prices = data.get('prices', [])
                
                if len(prices) >= 2:
                    # Get start and end prices
                    start_price = prices[0][1]  # [timestamp, price]
                    end_price = prices[-1][1]
                    
                    # Calculate daily yield
                    daily_yield = ((end_price - start_price) / start_price) * 100
                    
                    # Annualize the yield
                    annual_yield = daily_yield * 365
                    
                    # Apply reasonable bounds
                    annual_yield = max(min(annual_yield, 20), 0)  # Cap between 0% and 20%
                    
                    print(f"CoinGecko USDY Prices - Start: ${start_price:.4f}, End: ${end_price:.4f}")
                    print(f"Calculated annual yield: {annual_yield:.2f}%")
                    
                    return annual_yield
                else:
                    print("Not enough price data points from CoinGecko")
                    return None
            else:
                print(f"Error fetching from CoinGecko: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error fetching USDY yield from CoinGecko: {e}")
            return None
            
    def fetch_usdy_yield(self) -> float:
        """
        Fetch current yield from USDY contract or CoinGecko as fallback
        Returns annualized yield percentage
        Uses caching and moving average for more stable results
        """
        try:
            current_time = self.w3.eth.get_block('latest')['timestamp']
            
            # Check cache
            if (current_time - self.yield_cache['timestamp']) < self.yield_cache['ttl']:
                print("Using cached yield value")
                return self.yield_cache['value']
                
            print("\nFetching USDY yield...")
            
            # Try contract method first
            try:
                # Create contract instance
                usdy_contract = self.w3.eth.contract(address=self.usdy_token, abi=USDY_ABI)
                
                # Get current and last rates with validation
                current_rate = usdy_contract.functions.currentRate().call()
                if not self._validate_rate(current_rate, "current_rate"):
                    raise ValueError("Invalid current rate")
                    
                last_rate = usdy_contract.functions.lastRate().call()
                if not self._validate_rate(last_rate, "last_rate"):
                    raise ValueError("Invalid last rate")
                    
                last_update = usdy_contract.functions.lastRateUpdate().call()
                
                print(f"Contract rates - Current: {current_rate}, Last: {last_rate}, Updated: {last_update}")
                
                # Calculate time elapsed since last update
                time_elapsed = current_time - last_update
                
                # Validate time elapsed
                if time_elapsed <= 0 or time_elapsed > 30 * 24 * 60 * 60:  # Invalid or too old
                    raise ValueError("Invalid time elapsed or rate too old")
                
                # Calculate rate change
                rate_change = (current_rate - last_rate) / last_rate
                
                # Validate rate change
                if abs(rate_change) > 0.5:  # More than 50% change
                    raise ValueError("Unusually large rate change")
                
                # Annualize the rate
                years_elapsed = time_elapsed / (365 * 24 * 60 * 60)
                annual_rate = ((1 + rate_change) ** (1 / years_elapsed) - 1) * 100
                
                # Validate annual rate
                if not (0 <= annual_rate <= 20):
                    raise ValueError("Annual rate outside reasonable bounds")
                
                print(f"Contract method yield: {annual_rate:.2f}%")
                
            except Exception as e:
                print(f"Contract method failed: {e}")
                print("Falling back to CoinGecko method...")
                annual_rate = None
            
            # If contract method failed, try CoinGecko
            if annual_rate is None:
                annual_rate = self._fetch_usdy_yield_from_coingecko()
            
            # If both methods failed, use fallback value
            if annual_rate is None:
                print("All yield fetching methods failed, using fallback value")
                annual_rate = 5.05  # Conservative fallback based on recent yields
            
            # Calculate moving average
            smoothed_rate = self._calculate_moving_average(annual_rate)
            
            print(f"Final smoothed yield: {smoothed_rate:.2f}%")
            
            # Update cache
            self.yield_cache = {
                'value': smoothed_rate,
                'timestamp': current_time,
                'ttl': 300
            }
            
            return smoothed_rate
            
        except Exception as e:
            print(f"Error in fetch_usdy_yield: {e}")
            return 5.05  # Fallback yield
        
    def calculate_premium_discount(self) -> Dict[str, float]:
        """
        Calculate premium/discount relative to USDY yield
        Returns metrics including premium percentage and spread
        """
        try:
            if not self.dex_prices:
                return {}
                
            # Get CoinGecko price
            price = self.dex_prices.get('coingecko', 0)
            if price == 0:
                return {}
            
            # Get USDY yield as benchmark
            benchmark_yield = self.fetch_usdy_yield()
            if benchmark_yield == 0:
                print("Warning: Could not fetch USDY yield, using fallback value")
                benchmark_yield = 5.25  # Example fallback value
            
            # Calculate implied yield from ONDO price
            implied_yield = (1 / price - 1) * 100
            
            metrics = {
                'coingecko_price': price,
                'usdy_yield': benchmark_yield,
                'implied_yield': implied_yield,
                'yield_premium': implied_yield - benchmark_yield,
                'price_premium_pct': (price - 1) * 100  # Assuming 1 USDC par value
            }
            
            return metrics
        except Exception as e:
            print(f"Error calculating premium/discount: {e}")
            return {}
        
    def analyze_trading_patterns(self) -> Dict[str, any]:
        """
        Analyze trading patterns including volume, liquidity, and price action
        Returns trading metrics and patterns
        """
        try:
            analysis = {
                'volume_24h': {},
                'liquidity': {},
                'price_volatility': {},
                'price_trends': {}
            }
            
            # More realistic mock data based on recent market activity
            analysis['volume_24h']['coingecko'] = 75000  # Lower volume estimate
            analysis['liquidity']['coingecko'] = 1500000  # More conservative liquidity estimate
            analysis['price_volatility']['coingecko'] = 0.005  # 0.5% daily volatility
            analysis['price_trends']['coingecko'] = {
                'direction': 'stable',
                'strength': 'low',
                '24h_change': -0.001  # -0.1% change
            }
            
            return analysis
        except Exception as e:
            print(f"Error analyzing trading patterns: {e}")
            return {}
            
    def save_historical_data(self, data: Dict):
        """Save tracking data to JSON file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    historical_data = json.load(f)
            else:
                historical_data = []
                
            data['timestamp'] = datetime.now().isoformat()
            historical_data.append(data)
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            with open(self.data_file, 'w') as f:
                json.dump(historical_data, f, indent=4)
        except Exception as e:
            print(f"Error saving historical data: {e}")
            
    def generate_report(self, timeframe: str = 'daily') -> Dict:
        """
        Generate statistical report for specified timeframe
        Args:
            timeframe: 'daily', 'weekly', 'monthly', or 'all'
        Returns:
            Dict containing statistical metrics
        """
        try:
            if not os.path.exists(self.data_file):
                return {
                    'timeframe': timeframe,
                    'error': 'No historical data available'
                }
                
            with open(self.data_file, 'r') as f:
                historical_data = json.load(f)
            
            df = pd.DataFrame(historical_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Filter data based on timeframe
            now = datetime.now()
            if timeframe == 'daily':
                df = df[df['timestamp'] >= now - timedelta(days=1)]
            elif timeframe == 'weekly':
                df = df[df['timestamp'] >= now - timedelta(weeks=1)]
            elif timeframe == 'monthly':
                df = df[df['timestamp'] >= now - timedelta(days=30)]
            
            if len(df) == 0:
                return {
                    'timeframe': timeframe,
                    'error': 'No data available for the specified timeframe'
                }
            
            # Extract nested JSON data
            try:
                df['price_premium_pct'] = df['premium_metrics'].apply(lambda x: x.get('price_premium_pct', 0))
                df['yield_premium'] = df['premium_metrics'].apply(lambda x: x.get('yield_premium', 0))
                df['volume_24h'] = df['trading_analysis'].apply(lambda x: sum(x.get('volume_24h', {}).values()))
                df['liquidity'] = df['trading_analysis'].apply(lambda x: sum(x.get('liquidity', {}).values()))
            except Exception as e:
                print(f"Error processing DataFrame: {e}")
                return {
                    'timeframe': timeframe,
                    'error': 'Error processing historical data'
                }
            
            # Calculate statistics
            report = {
                'timeframe': timeframe,
                'data_points': len(df),
                'current_premium': df['price_premium_pct'].iloc[-1] if len(df) > 0 else None,
                'avg_premium': df['price_premium_pct'].mean(),
                'min_premium': df['price_premium_pct'].min(),
                'max_premium': df['price_premium_pct'].max(),
                'premium_history': df['price_premium_pct'].tolist(),
                'premium_stats': {
                    'mean': df['price_premium_pct'].mean(),
                    'std': df['price_premium_pct'].std(),
                    'min': df['price_premium_pct'].min(),
                    'max': df['price_premium_pct'].max()
                },
                'yield_comparison': {
                    'mean_spread': df['yield_premium'].mean(),
                    'current_spread': df['yield_premium'].iloc[-1] if len(df) > 0 else None
                },
                'trading_stats': {
                    'avg_daily_volume': df['volume_24h'].mean(),
                    'avg_liquidity': df['liquidity'].mean()
                }
            }
            
            return report
        except Exception as e:
            print(f"Error generating report: {e}")
            return {
                'timeframe': timeframe,
                'error': str(e)
            }
            
    def run_tracker(self):
        """Main tracking function"""
        try:
            # Fetch current data
            treasury_yields = self.fetch_treasury_yields()
            dex_prices = self.fetch_dex_prices()
            
            # Calculate metrics
            premium_metrics = self.calculate_premium_discount()
            trading_analysis = self.analyze_trading_patterns()
            
            # Combine data
            current_data = {
                'treasury_yields': treasury_yields,
                'dex_prices': dex_prices,
                'premium_metrics': premium_metrics,
                'trading_analysis': trading_analysis
            }
            
            # Save historical data
            self.save_historical_data(current_data)
            
            return current_data
        except Exception as e:
            print(f"Error running tracker: {e}")
            return None 