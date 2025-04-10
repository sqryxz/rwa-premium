import os
import logging
import asyncio
import requests
from typing import Dict, Tuple, Optional, List
from datetime import datetime
import ccxt
from pycoingecko import CoinGeckoAPI
from web3 import Web3
from utils import retry_with_backoff, calculate_weighted_average

logger = logging.getLogger(__name__)

# Uniswap V2 Router ABI (minimal for price checking)
UNISWAP_V2_ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    }
]

class DEXPriceFetcher:
    """Class for fetching prices from DEXes"""
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(os.getenv('ETHEREUM_RPC_URL', 'https://eth-mainnet.g.alchemy.com/v2/demo')))
        
        # Contract addresses
        self.uniswap_router = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
        self.sushiswap_router = "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
        self.usdc_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
        self.weth_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

    @retry_with_backoff(retries=3)
    def get_token_price(self, token_address: str, dex_router: str) -> Optional[tuple[float, float]]:
        """Get token price from a DEX"""
        try:
            router_contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(dex_router),
                abi=UNISWAP_V2_ROUTER_ABI
            )
            
            # Amount in: 1 token (in wei)
            amount_in = 10**18  # 1 token
            
            # Path: token -> WETH -> USDC
            path = [
                self.w3.to_checksum_address(token_address),
                self.w3.to_checksum_address(self.weth_address),
                self.w3.to_checksum_address(self.usdc_address)
            ]
            
            try:
                amounts = router_contract.functions.getAmountsOut(amount_in, path).call()
                usdc_amount = amounts[-1] / (10**6)  # USDC has 6 decimals
                price = usdc_amount
                
                # Use the input amount as a proxy for volume
                return (price, float(amount_in))
            except Exception as e:
                logger.warning(f"Error getting price from DEX router {dex_router}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error in get_token_price: {e}")
            return None

    def get_uniswap_price(self, token_address: str) -> Optional[tuple[float, float]]:
        """Get token price from Uniswap"""
        return self.get_token_price(token_address, self.uniswap_router)

    def get_sushiswap_price(self, token_address: str) -> Optional[tuple[float, float]]:
        """Get token price from SushiSwap"""
        return self.get_token_price(token_address, self.sushiswap_router)

class OndeDataFetcher:
    def __init__(self):
        self.coingecko = CoinGeckoAPI()
        self.dex_fetcher = DEXPriceFetcher()
        
        # Contract addresses
        self.ondo_address = "0x73488dc690c2cF2B6086C0E0ABDE2628802c3433"
        self.usdy_address = "0x96F6eF951840721AdBF46Ac996b59E0235b3D875"
        
    @retry_with_backoff(retries=3)
    def get_ondo_price(self) -> Optional[float]:
        """Get ONDO token price in USD with multiple sources"""
        prices = []
        
        try:
            # Get CoinGecko price
            cg_data = self.coingecko.get_price(ids='ondo-finance', vs_currencies='usd')
            if cg_data and 'ondo-finance' in cg_data:
                prices.append((float(cg_data['ondo-finance']['usd']), 1.0))  # Weight of 1.0 for CoinGecko
                
            # Get DEX prices
            dex_prices = []
            for dex_price in [
                self.dex_fetcher.get_uniswap_price(self.ondo_address),
                self.dex_fetcher.get_sushiswap_price(self.ondo_address)
            ]:
                if dex_price:
                    dex_prices.append(dex_price)
            
            prices.extend(dex_prices)
            
            # Calculate weighted average
            return calculate_weighted_average(prices)
            
        except Exception as e:
            logger.error(f"Error fetching ONDO price: {e}")
            return None

    @retry_with_backoff(retries=3)
    def get_usdy_price(self) -> Optional[float]:
        """Get USDY token price in USD with multiple sources"""
        try:
            prices = []
            
            # Get Ondo API price
            response = requests.get('https://api.ondo.finance/api/v1/usdy/price')
            if response.status_code == 200:
                prices.append((float(response.json()['price']), 2.0))  # Higher weight for official API
                
            # Get DEX prices
            dex_prices = []
            for dex_price in [
                self.dex_fetcher.get_uniswap_price(self.usdy_address),
                self.dex_fetcher.get_sushiswap_price(self.usdy_address)
            ]:
                if dex_price:
                    dex_prices.append(dex_price)
            
            prices.extend(dex_prices)
            
            return calculate_weighted_average(prices)
            
        except Exception as e:
            logger.error(f"Error fetching USDY price: {e}")
            return None

class CentrifugeDataFetcher:
    """Class for fetching Centrifuge pool data and token prices"""
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(os.getenv('ETHEREUM_RPC_URL', 'https://eth-mainnet.g.alchemy.com/v2/demo')))
        self.coingecko = CoinGeckoAPI()
        self.dex_fetcher = DEXPriceFetcher()
        
        # API configuration
        self.api_base_url = "https://api.centrifuge.io"
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

    @retry_with_backoff(retries=3)
    def _graphql_query(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute a GraphQL query against Centrifuge API"""
        try:
            payload = {"query": query}
            if variables:
                payload["variables"] = variables

            response = self.session.post(
                f"{self.api_base_url}/graphql",
                json=payload
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"GraphQL query failed: {e}")
            return None

    @retry_with_backoff(retries=3)
    def get_pool_data(self, pool_id: str) -> Optional[Dict]:
        """Get comprehensive pool data including token prices and metrics"""
        query = """
        query GetPoolData($id: String!) {
            pool(id: $id) {
                id
                name
                status
                currency {
                    id
                    symbol
                    decimals
                }
                seniorToken {
                    id
                    symbol
                    price
                    totalSupply
                }
                juniorToken {
                    id
                    symbol
                    price
                    totalSupply
                }
                portfolio {
                    totalValue
                    numAssets
                }
                metrics {
                    reserve
                    netAssetValue
                    seniorInterestRate
                }
                lastUpdated
            }
        }
        """
        
        result = self._graphql_query(query, {"id": pool_id})
        
        if not result or "errors" in result:
            logger.error(f"Failed to fetch pool data: {result.get('errors') if result else 'No response'}")
            return None
            
        pool = result.get("data", {}).get("pool")
        if not pool:
            logger.warning(f"No data found for pool {pool_id}")
            return None

        # Check if pool is active
        if pool["status"] != "ACTIVE":
            logger.warning(f"Pool {pool_id} is not active (status: {pool['status']})")
            return None

        try:
            # Extract token prices and pool metrics
            drop_price = float(pool["seniorToken"]["price"])
            tin_price = float(pool["juniorToken"]["price"])
            nav_per_token = float(pool["metrics"]["netAssetValue"]) / float(pool["metrics"]["reserve"]) if float(pool["metrics"]["reserve"]) > 0 else None

            # Get additional price data from DEXes for validation
            drop_prices = [(drop_price, 2.0)]  # Higher weight for official price
            tin_prices = [(tin_price, 2.0)]

            # Add DEX prices if available
            for token_prices, token_data in [(drop_prices, pool["seniorToken"]), (tin_prices, pool["juniorToken"])]:
                dex_prices = [
                    self.dex_fetcher.get_uniswap_price(token_data["id"]),
                    self.dex_fetcher.get_sushiswap_price(token_data["id"])
                ]
                token_prices.extend([p for p in dex_prices if p is not None])

            return {
                "drop_price": calculate_weighted_average(drop_prices),
                "tin_price": calculate_weighted_average(tin_prices),
                "nav_per_token": nav_per_token,
                "pool_metrics": {
                    "nav": float(pool["metrics"]["netAssetValue"]),
                    "reserve": float(pool["metrics"]["reserve"]),
                    "senior_interest_rate": float(pool["metrics"]["seniorInterestRate"]),
                    "total_portfolio_value": float(pool["portfolio"]["totalValue"]),
                    "num_assets": int(pool["portfolio"]["numAssets"]),
                    "last_update": pool["lastUpdated"],
                    "senior_token_supply": float(pool["seniorToken"]["totalSupply"]),
                    "junior_token_supply": float(pool["juniorToken"]["totalSupply"])
                }
            }
            
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error processing pool data: {e}")
            return None

    @retry_with_backoff(retries=3)
    def list_active_pools(self) -> List[Dict]:
        """Get list of active pools"""
        query = """
        {
            pools {
                id
                name
                status
                currency {
                    symbol
                }
            }
        }
        """
        
        result = self._graphql_query(query)
        if not result or "errors" in result:
            logger.error(f"Failed to fetch pools list: {result.get('errors') if result else 'No response'}")
            return []
            
        return [
            pool for pool in result.get("data", {}).get("pools", [])
            if pool["status"] == "ACTIVE"
        ]

    @retry_with_backoff(retries=3)
    def get_cfg_price(self) -> Optional[float]:
        """Get CFG token price in USD with multiple sources"""
        try:
            prices = []
            
            # Get CoinGecko price
            cg_data = self.coingecko.get_price(ids='centrifuge', vs_currencies='usd')
            if cg_data and 'centrifuge' in cg_data:
                prices.append((float(cg_data['centrifuge']['usd']), 1.0))
            
            # Get DEX prices for CFG
            cfg_address = "0xc221b7E65FfC80DE234bB6667ABDd46593D34F03"
            dex_prices = []
            for dex_price in [
                self.dex_fetcher.get_uniswap_price(cfg_address),
                self.dex_fetcher.get_sushiswap_price(cfg_address)
            ]:
                if dex_price:
                    dex_prices.append(dex_price)
            
            prices.extend(dex_prices)
            
            return calculate_weighted_average(prices)
            
        except Exception as e:
            logger.error(f"Error fetching CFG price: {e}")
            return None 