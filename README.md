# RWA Premium Tracker

A Python-based tool for tracking and analyzing Real World Assets (RWA) tokens, including:
- Centrifuge (CFG) pool tokens premium/discount rates relative to NAV
- ONDO token premium/discount rates relative to Treasury yields and DEX trading patterns

## Currently Supported Features

1. CFG Tracker:
   - Track premium/discount rates for DROP and TIN tokens
   - Monitor pool metrics and performance
   - Generate statistical reports and analysis
   - Historical data tracking

2. ONDO Tracker:
   - Monitor ONDO token prices across major DEXs
   - Track Treasury yield rates
   - Calculate premium/discount relative to Treasury yields
   - Analyze trading patterns and liquidity
   - Generate statistical reports with customizable timeframes

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd cfg-tracker
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your API keys:
```bash
ETHEREUM_RPC_URL=your_ethereum_node_url
```

## Usage

Run the CFG tracker:
```bash
python3 src/main.py
```

Run the ONDO tracker:
```bash
python3 src/ondo_tracker/main.py [--timeframe {daily,weekly,monthly,all}] [--report-only]
```

Options for ONDO tracker:
- `--timeframe`: Select report timeframe (default: daily)
- `--report-only`: Generate report without fetching new data

The CFG tracker will:
- Fetch current data from Centrifuge pools
- Calculate premium/discount rates for tranches
- Generate statistical reports
- Store historical data in `src/data/premium_history.json`

## Data Storage

1. CFG data is stored in `src/data/premium_history.json`
2. ONDO data is stored in `src/ondo_tracker/data/ondo_premium_history.json`

Both use JSON format and include:
- Timestamp
- Price data
- Premium/discount metrics
- Trading analysis

## Reports

The tracker generates reports with the following metrics:
- Current premium/discount rates
- Historical averages
- Maximum and minimum values
- Standard deviation
- Number of observations

Reports can be generated for different timeframes:
- Daily
- Weekly
- Monthly
- All-time

## Contributing

Feel free to submit issues and enhancement requests!

## License

MIT 