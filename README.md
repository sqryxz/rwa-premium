# RWA Premium Tracker

A consolidated tracker for Real World Asset (RWA) premiums and discounts, tracking both CFG and ONDO assets.

## Features

- Track premium/discount rates for CFG and ONDO assets
- Generate consolidated reports in both JSON and CSV formats
- Analyze trends and correlations between different assets
- Calculate risk metrics and market insights
- Support for different timeframes (daily, weekly, monthly)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/rwa-premium-tracker.git
cd rwa-premium-tracker
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

4. Set up environment variables:
Create a `.env` file in the root directory and add your configuration:
```
# Add your environment variables here
```

## Usage

Run the tracker with default settings:
```bash
python src/consolidated_tracker.py
```

Available command-line options:
- `--timeframe`: Choose between 'daily', 'weekly', 'monthly', or 'all'
- `--report-only`: Generate report without fetching new data
- `--format`: Choose output format ('json', 'csv', or 'both')

Example:
```bash
python src/consolidated_tracker.py --timeframe weekly --format csv
```

## Output

The tracker generates two types of reports:
1. Main report (consolidated_report.json/csv) with premium/discount rates and analysis
2. Correlation data (correlations.csv) showing relationships between different assets

## License

[MIT License](LICENSE) 