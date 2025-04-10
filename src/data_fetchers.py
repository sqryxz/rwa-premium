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
import time

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
    def get_token_price(self, token_address: str, router_address: str) -> Optional[float]:
        """Get token price from DEX with fallback mechanisms"""
        try:
            # Try Uniswap V2 style router first
            router = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_address),
                abi=UNISWAP_V2_ROUTER_ABI
            )
            
            # Prepare parameters for price check
            path = [
                Web3.to_checksum_address(token_address),
                Web3.to_checksum_address(self.usdc_address)  # Using USDC as price reference
            ]
            amount_in = Web3.to_wei(1, 'ether')  # 1 token
            
            try:
                # Try getAmountsOut first
                amounts = router.functions.getAmountsOut(
                    amount_in,
                    path
                ).call()
                price = Web3.from_wei(amounts[1], 'mwei')  # Convert from USDC decimals (6)
                logger.info(f"Got price from DEX router (getAmountsOut): {price}")
                return float(price)
            except Exception as e1:
                logger.debug(f"getAmountsOut failed: {e1}")
                
                try:
                    # Try alternative method - getReserves
                    pair_address = router.functions.factory().call().functions.getPair(
                        path[0],
                        path[1]
                    ).call()
                    
                    if pair_address != "0x0000000000000000000000000000000000000000":
                        pair = self.w3.eth.contract(
                            address=pair_address,
                            abi=UNISWAP_V2_ROUTER_ABI
                        )
                        reserves = pair.functions.getReserves().call()
                        token0 = pair.functions.token0().call()
                        
                        # Calculate price based on reserves
                        if token0.lower() == token_address.lower():
                            price = (reserves[1] / 10**6) / (reserves[0] / 10**18)
                        else:
                            price = (reserves[0] / 10**6) / (reserves[1] / 10**18)
                            
                        logger.info(f"Got price from DEX pair reserves: {price}")
                        return float(price)
                except Exception as e2:
                    logger.debug(f"getReserves method failed: {e2}")
        
        except Exception as e:
            logger.warning(f"Error getting price from DEX router: {e}")
        
        # If DEX methods fail, try getting price from a price feed
        try:
            price_feed_address = self.price_feeds.get(token_address)
            if price_feed_address:
                price_feed = self.w3.eth.contract(
                    address=Web3.to_checksum_address(price_feed_address),
                    abi=self.price_feed_abi
                )
                latest_data = price_feed.functions.latestRoundData().call()
                price = latest_data[1] / 10**8  # Chainlink typically uses 8 decimals
                logger.info(f"Got price from price feed: {price}")
                return float(price)
        except Exception as e:
            logger.warning(f"Error getting price from price feed: {e}")
        
        # If all methods fail, try getting price from CoinGecko
        try:
            token_id = self.token_ids.get(token_address.lower())
            if token_id:
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={token_id}&vs_currencies=usd"
                response = requests.get(url)
                if response.status_code == 200:
                    price = response.json()[token_id]['usd']
                    logger.info(f"Got price from CoinGecko: {price}")
                    return float(price)
        except Exception as e:
            logger.warning(f"Error getting price from CoinGecko: {e}")
        
        # If all methods fail, return None
        logger.error("All price fetching methods failed")
        return None

    def get_uniswap_price(self, token_address: str) -> Optional[tuple[float, float]]:
        """Get token price from Uniswap"""
        return self.get_token_price(token_address, self.uniswap_router)

    def get_sushiswap_price(self, token_address: str) -> Optional[tuple[float, float]]:
        """Get token price from SushiSwap"""
        return self.get_token_price(token_address, self.sushiswap_router)

    def get_dex_price(self, token_address: str, router_addresses: List[str]) -> Optional[float]:
        """Get token price from DEX routers with fallback mechanisms"""
        for router_address in router_addresses:
            try:
                # Get router contract
                router = self.w3.eth.contract(
                    address=Web3.to_checksum_address(router_address),
                    abi=UNISWAP_V2_ROUTER_ABI
                )
                
                # Prepare parameters for price check
                path = [
                    Web3.to_checksum_address(token_address),
                    Web3.to_checksum_address(self.usdc_address)  # Using USDC as price reference
                ]
                amount_in = Web3.to_wei(1, 'ether')  # 1 token
                
                try:
                    # Try getAmountsOut first
                    amounts = router.functions.getAmountsOut(
                        amount_in,
                        path
                    ).call()
                    price = Web3.from_wei(amounts[1], 'mwei') # Convert from USDC decimals (6)
                    logger.info(f"Got price from DEX router {router_address}: {price}")
                    return float(price)
                except Exception as e1:
                    logger.debug(f"getAmountsOut failed for router {router_address}: {e1}")
                    try:
                        # Fallback to quoteExactInputSingle if available
                        price = router.functions.quoteExactInputSingle(
                            path[0],
                            path[1],
                            amount_in,
                            0,  # No fee data needed
                            0   # No extra data needed
                        ).call()
                        price = Web3.from_wei(price, 'mwei')
                        logger.info(f"Got price from DEX router {router_address} (fallback method): {price}")
                        return float(price)
                    except Exception as e2:
                        logger.debug(f"quoteExactInputSingle failed for router {router_address}: {e2}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Error getting price from DEX router {router_address}: {e}")
                continue
        
        # If all DEX routers fail, try getting price from a price feed
        try:
            price_feed_address = self.price_feeds.get(token_address)
            if price_feed_address:
                price_feed = self.w3.eth.contract(
                    address=Web3.to_checksum_address(price_feed_address),
                    abi=self.price_feed_abi
                )
                latest_data = price_feed.functions.latestRoundData().call()
                price = latest_data[1] / 10**8  # Chainlink typically uses 8 decimals
                logger.info(f"Got price from price feed: {price}")
                return float(price)
        except Exception as e:
            logger.warning(f"Error getting price from price feed: {e}")
        
        # If all methods fail, return None
        logger.error("All price fetching methods failed")
        return None

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

    def get_usdy_yield(self) -> Optional[float]:
        """Get USDY yield with multiple fallback methods"""
        try:
            # Try getting yield from contract
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.usdy_contract),
                abi=self.usdy_abi
            )
            
            try:
                # Try getting current yield rate
                current_rate = contract.functions.currentYieldRate().call()
                annual_yield = (current_rate / 1e18) * 365 * 100  # Convert to annual percentage
                logger.info(f"Got USDY yield from contract: {annual_yield}%")
                return float(annual_yield)
            except Exception as e:
                logger.debug(f"Failed to get yield rate from contract: {e}")
                
                # Try alternative method - calculate from total supply change
                try:
                    current_supply = contract.functions.totalSupply().call()
                    time.sleep(1)  # Wait a bit to see supply change
                    new_supply = contract.functions.totalSupply().call()
                    
                    if new_supply > current_supply:
                        supply_change = (new_supply - current_supply) / current_supply
                        annual_yield = supply_change * 365 * 24 * 3600 * 100  # Annualize the yield
                        logger.info(f"Calculated USDY yield from supply change: {annual_yield}%")
                        return float(annual_yield)
                except Exception as e2:
                    logger.debug(f"Failed to calculate yield from supply change: {e2}")
        
        except Exception as e:
            logger.warning(f"Failed to interact with USDY contract: {e}")
        
        # Fallback to calculating yield from price change
        try:
            historical_prices = self.get_historical_prices()
            if historical_prices and len(historical_prices) >= 2:
                start_price = historical_prices[0]
                end_price = historical_prices[-1]
                price_change = (end_price - start_price) / start_price
                days_between = 7  # Assuming weekly historical data
                annual_yield = (price_change / days_between) * 365 * 100
                logger.info(f"Calculated USDY yield from price change: {annual_yield}%")
                return float(annual_yield)
        except Exception as e:
            logger.warning(f"Failed to calculate yield from price change: {e}")
        
        # If all methods fail, return None
        logger.error("All yield calculation methods failed")
        return None

class CentrifugeDataFetcher:
    """Class for fetching Centrifuge pool data and token prices"""
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(os.getenv('ETHEREUM_RPC_URL', 'https://eth-mainnet.g.alchemy.com/v2/demo')))
        self.coingecko = CoinGeckoAPI()
        self.dex_fetcher = DEXPriceFetcher()
        
        # API configuration
        self.api_base_url = os.getenv('CENTRIFUGE_API_URL', 'https://api.centrifuge.io')
        self.api_key = os.getenv('CENTRIFUGE_API_KEY')
        
        # Initialize session with headers
        self.session = requests.Session()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self.session.headers.update(headers)

    @retry_with_backoff(retries=3)
    def _graphql_query(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute a GraphQL query against Centrifuge API"""
        try:
            payload = {"query": query}
            if variables:
                payload["variables"] = variables

            response = self.session.post(
                f"{self.api_base_url}/graphql",
                json=payload,
                timeout=30  # Add timeout
            )
            
            # Check for HTTP errors
            if response.status_code == 401:
                logger.error("Authentication failed. Please check your API key.")
                return None
            elif response.status_code == 403:
                logger.error("Access forbidden. Please check your API permissions.")
                return None
            elif response.status_code >= 400:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return None
                
            response.raise_for_status()
            result = response.json()
            
            # Check for GraphQL errors
            if "errors" in result:
                error_messages = [error.get("message", "Unknown error") for error in result["errors"]]
                logger.error(f"GraphQL errors: {', '.join(error_messages)}")
                return None
                
            return result
            
        except requests.exceptions.Timeout:
            logger.error("API request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in GraphQL query: {e}")
            return None

    @retry_with_backoff(retries=3)
    def get_pool_data(self, pool_id: str) -> Optional[Dict]:
        """
        Fetch pool data from Centrifuge's GraphQL API
        """
        query = """
        query GetPoolData($poolId: String!) {
            pool(id: $poolId) {
                id
                name
                status
                tranches {
                    nodes {
                        id
                        tokenSymbol
                        tokenPrice {
                            value
                        }
                        totalIssuance
                        currency {
                            id
                            symbol
                            decimals
                        }
                        interestRatePerSec
                        orders {
                            nodes {
                                id
                                amount
                                currency {
                                    id
                                    symbol
                                }
                            }
                        }
                    }
                }
                valuations {
                    nodes {
                        id
                        timestamp
                        value
                    }
                }
                metrics {
                    netAssetValue
                }
            }
        }
        """
        
        variables = {
            "poolId": pool_id
        }
        
        try:
            response = self._graphql_query(query, variables)
            if response and 'data' in response and 'pool' in response['data']:
                pool_data = response['data']['pool']
                return {
                    'id': pool_data.get('id'),
                    'name': pool_data.get('name'),
                    'status': pool_data.get('status'),
                    'nav': pool_data.get('metrics', {}).get('netAssetValue'),
                    'tranches': [{
                        'id': tranche['id'],
                        'token_symbol': tranche['tokenSymbol'],
                        'token_price': tranche.get('tokenPrice', {}).get('value'),
                        'total_supply': tranche['totalIssuance'],
                        'currency': {
                            'id': tranche['currency']['id'],
                            'symbol': tranche['currency']['symbol'],
                            'decimals': tranche['currency']['decimals']
                        },
                        'interest_rate': tranche.get('interestRatePerSec'),
                        'orders': [{
                            'id': order['id'],
                            'amount': order['amount'],
                            'currency': {
                                'id': order['currency']['id'],
                                'symbol': order['currency']['symbol']
                            }
                        } for order in tranche.get('orders', {}).get('nodes', [])]
                    } for tranche in pool_data.get('tranches', {}).get('nodes', [])],
                    'valuations': [{
                        'id': val['id'],
                        'timestamp': val['timestamp'],
                        'value': val['value']
                    } for val in pool_data.get('valuations', {}).get('nodes', [])]
                }
            return None
        except Exception as e:
            logger.error(f"Failed to fetch data for pool {pool_id}")
            logger.error(str(e))
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