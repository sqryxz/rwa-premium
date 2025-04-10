import os
import time
import json
import csv
from datetime import datetime, timedelta, UTC
from dotenv import load_dotenv
import argparse
from typing import Dict, Any, List, Tuple
import numpy as np
from scipy import stats
from collections import defaultdict

from cfg_tracker import CFGTracker
from ondo_tracker.ondo_tracker import OndoTracker
from data_fetchers import OndeDataFetcher, CentrifugeDataFetcher

class ConsolidatedTracker:
    def __init__(self):
        self.cfg_tracker = CFGTracker()
        self.ondo_tracker = OndoTracker()
        self.ondo_fetcher = OndeDataFetcher()
        self.centrifuge_fetcher = CentrifugeDataFetcher()
        
    def fetch_current_data(self) -> Dict[str, Any]:
        """Fetch current data from both trackers"""
        data = {
            'timestamp': datetime.now(UTC).isoformat(),
            'cfg_data': {},
            'ondo_data': {}
        }
        
        # Fetch CFG data
        cfg_price = self.centrifuge_fetcher.get_cfg_price()
        pool_ids = [
            '0x4cA805cE8EcE2E63FfC1F9f8F2731D3F48DF89Df',  # HVB Real Estate Pool
            '0x6F2A3B2f6c07034b3BCf1c916F8091B1425E61d9',  # Cauris Global Fintech Pool
            '0x0Cf79cB86E2b9E46F14cE85d35B9E118E4ADc8c0'   # BlockTower High Yield Loan Pool
        ]
        
        for pool_id in pool_ids:
            pool_data = self.centrifuge_fetcher.get_pool_data(pool_id)
            if pool_data and cfg_price:
                data['cfg_data'][pool_id] = {
                    'drop_premium': self.cfg_tracker.calculate_premium(
                        pool_data['drop_price'],
                        pool_data['nav_per_token']
                    ),
                    'tin_premium': self.cfg_tracker.calculate_premium(
                        pool_data['tin_price'],
                        pool_data['nav_per_token']
                    )
                }
        
        # Fetch ONDO data
        ondo_data = self.ondo_tracker.run_tracker()
        if ondo_data:
            data['ondo_data'] = ondo_data
            
        return data
    
    def analyze_trend(self, data_series: List[float]) -> Dict[str, Any]:
        """Analyze trends in a time series of premium/discount rates"""
        if not data_series or len(data_series) < 2:
            return {
                'trend': 'insufficient_data',
                'volatility': None,
                'momentum': None
            }

        # Calculate trend using linear regression
        x = np.arange(len(data_series))
        slope, _, r_value, _, _ = stats.linregress(x, data_series)
        
        # Determine trend direction and strength
        trend = 'stable'
        if abs(slope) > 0.01:  # 1% change per period threshold
            trend = 'increasing' if slope > 0 else 'decreasing'
            if abs(slope) > 0.05:  # 5% change per period threshold
                trend = 'strongly_' + trend
        
        # Calculate volatility (standard deviation)
        volatility = np.std(data_series)
        
        # Calculate momentum (rate of change)
        momentum = data_series[-1] - data_series[0] if len(data_series) > 1 else 0
        
        return {
            'trend': trend,
            'volatility': volatility,
            'momentum': momentum,
            'r_squared': r_value ** 2
        }

    def calculate_correlation(self, cfg_data: List[float], ondo_data: List[float]) -> Dict[str, float]:
        """Calculate correlations between CFG and ONDO premiums"""
        if len(cfg_data) != len(ondo_data) or len(cfg_data) < 2:
            return {
                'correlation': None,
                'significance': None
            }
        
        correlation, p_value = stats.pearsonr(cfg_data, ondo_data)
        return {
            'correlation': correlation,
            'significance': p_value
        }

    def generate_consolidated_report(self, timeframe: str = 'daily') -> Dict[str, Any]:
        """Generate a consolidated report from both trackers with analysis"""
        report = {
            'timestamp': datetime.now(UTC).isoformat(),
            'timeframe': timeframe,
            'cfg_report': {},
            'ondo_report': {},
            'usdy_data': {
                'current_yield': self.ondo_tracker.fetch_usdy_yield(),
                'yield_history': []  # Will be populated from historical data
            },
            'analysis': {
                'trends': {},
                'correlations': {},
                'market_insights': {},
                'risk_metrics': {}
            }
        }
        
        # Generate base reports
        cfg_report = self.cfg_tracker.generate_report(timeframe)
        ondo_report = self.ondo_tracker.generate_report(timeframe)
        report['cfg_report'] = cfg_report
        report['ondo_report'] = ondo_report
        
        # Extract USDY yield history from ONDO data if available
        if os.path.exists(self.ondo_tracker.data_file):
            with open(self.ondo_tracker.data_file, 'r') as f:
                historical_data = json.load(f)
                report['usdy_data']['yield_history'] = [
                    entry.get('premium_metrics', {}).get('usdy_yield', None) 
                    for entry in historical_data
                    if entry.get('premium_metrics', {}).get('usdy_yield') is not None
                ]
        
        # Analyze trends for each asset
        for pool_id, stats in cfg_report.items():
            if isinstance(stats, dict) and 'premium_history' in stats:
                report['analysis']['trends'][f'cfg_pool_{pool_id}'] = self.analyze_trend(stats['premium_history'])

        for token, stats in ondo_report.items():
            if isinstance(stats, dict) and 'premium_history' in stats:
                report['analysis']['trends'][f'ondo_{token}'] = self.analyze_trend(stats['premium_history'])
        
        # Analyze USDY yield trends
        if report['usdy_data']['yield_history']:
            report['analysis']['trends']['usdy_yield'] = self.analyze_trend(report['usdy_data']['yield_history'])
            
            # Add market insights specific to USDY yield
            latest_yield = report['usdy_data']['current_yield']
            historical_yields = report['usdy_data']['yield_history']
            if historical_yields:
                avg_yield = sum(y for y in historical_yields if y is not None) / len([y for y in historical_yields if y is not None])
                report['analysis']['market_insights']['usdy_yield'] = {
                    'current_vs_average': {
                        'value': latest_yield - avg_yield if latest_yield is not None else None,
                        'description': f"Current USDY yield is {'above' if latest_yield > avg_yield else 'below'} historical average by {abs(latest_yield - avg_yield):.2f}%" if latest_yield is not None else "No current yield data available"
                    },
                    'volatility': self.calculate_volatility(historical_yields)
                }
        
        # Calculate correlations between assets
        for pool_id, pool_stats in cfg_report.items():
            if not isinstance(pool_stats, dict) or 'premium_history' not in pool_stats:
                continue
                
            cfg_premiums = pool_stats['premium_history']
            
            # Correlate with ONDO tokens
            for token, ondo_stats in ondo_report.items():
                if not isinstance(ondo_stats, dict) or 'premium_history' not in ondo_stats:
                    continue
                    
                ondo_premiums = ondo_stats['premium_history']
                min_length = min(len(cfg_premiums), len(ondo_premiums))
                
                if min_length > 1:
                    report['analysis']['correlations'][f'cfg_pool_{pool_id}_vs_ondo_{token}'] = \
                        self.calculate_correlation(cfg_premiums[-min_length:], ondo_premiums[-min_length:])
            
            # Correlate with USDY yield if available
            if report['usdy_data']['yield_history']:
                usdy_yields = report['usdy_data']['yield_history']
                min_length = min(len(cfg_premiums), len(usdy_yields))
                
                if min_length > 1:
                    report['analysis']['correlations'][f'cfg_pool_{pool_id}_vs_usdy_yield'] = \
                        self.calculate_correlation(cfg_premiums[-min_length:], usdy_yields[-min_length:])

        # Generate market summary
        report['market_summary'] = []
        
        # Add CFG pools to market summary
        for pool_id, stats in cfg_report.items():
            if isinstance(stats, dict):
                report['market_summary'].append({
                    'pool_id': pool_id,
                    'token_type': 'CFG',
                    'current_premium': stats.get('current_premium', 'N/A'),
                    'trend': report['analysis']['trends'].get(f'cfg_pool_{pool_id}', {}).get('trend', 'N/A'),
                    'volatility': report['analysis']['trends'].get(f'cfg_pool_{pool_id}', {}).get('volatility', 'N/A'),
                    'momentum': report['analysis']['trends'].get(f'cfg_pool_{pool_id}', {}).get('momentum', 'N/A'),
                    'trend_stability': report['analysis']['risk_metrics']['trend_stability'].get(f'cfg_pool_{pool_id}', 'N/A')
                })

        # Add ONDO tokens to market summary
        for token, stats in ondo_report.items():
            if isinstance(stats, dict):
                report['market_summary'].append({
                    'token': token,
                    'token_type': 'ONDO',
                    'current_premium': stats.get('current_premium', 'N/A'),
                    'trend': report['analysis']['trends'].get(f'ondo_{token}', {}).get('trend', 'N/A'),
                    'volatility': report['analysis']['trends'].get(f'ondo_{token}', {}).get('volatility', 'N/A'),
                    'momentum': report['analysis']['trends'].get(f'ondo_{token}', {}).get('momentum', 'N/A'),
                    'trend_stability': report['analysis']['risk_metrics']['trend_stability'].get(f'ondo_{token}', 'N/A')
                })
        
        # Add USDY yield to market summary
        if report['usdy_data']['current_yield'] is not None:
            report['market_summary'].append({
                'token': 'USDY',
                'token_type': 'YIELD',
                'current_value': report['usdy_data']['current_yield'],
                'trend': report['analysis']['trends'].get('usdy_yield', {}).get('trend', 'N/A'),
                'volatility': report['analysis']['trends'].get('usdy_yield', {}).get('volatility', 'N/A'),
                'momentum': report['analysis']['trends'].get('usdy_yield', {}).get('momentum', 'N/A'),
                'trend_stability': report['analysis']['risk_metrics']['trend_stability'].get('usdy_yield', 'N/A')
            })
        
        # Generate market insights
        report['analysis']['market_insights'] = self.generate_market_insights(report)
        
        # Calculate risk metrics
        report['analysis']['risk_metrics'] = self.calculate_risk_metrics(report)
        
        return report

    def generate_market_insights(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Generate market insights based on the analyzed data"""
        insights = {
            'summary': [],
            'opportunities': [],
            'risks': []
        }
        
        # Analyze trends for insights
        for asset, trend_data in report['analysis']['trends'].items():
            if not trend_data:
                continue
                
            trend = trend_data.get('trend')
            volatility = trend_data.get('volatility')
            
            if trend == 'strongly_increasing':
                insights['summary'].append(f"Strong upward trend in {asset} premium")
                insights['opportunities'].append(f"Consider increasing exposure to {asset}")
            elif trend == 'strongly_decreasing':
                insights['summary'].append(f"Strong downward trend in {asset} premium")
                insights['risks'].append(f"Monitor {asset} for potential stabilization")
            
            if volatility is not None and volatility > 0.1:  # 10% volatility threshold
                insights['risks'].append(f"High volatility in {asset}")
        
        # Analyze correlations for insights
        for pair, corr_data in report['analysis']['correlations'].items():
            if not corr_data:
                continue
                
            correlation = corr_data.get('correlation')
            if correlation is not None:
                if correlation > 0.7:
                    insights['summary'].append(f"Strong positive correlation between {pair}")
                elif correlation < -0.7:
                    insights['summary'].append(f"Strong negative correlation between {pair}")
                    insights['opportunities'].append(f"Potential diversification opportunity with {pair}")
        
        return insights

    def calculate_risk_metrics(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate risk metrics for the portfolio"""
        risk_metrics = {
            'volatility_ranking': [],
            'trend_stability': {},
            'correlation_risk': 'low'
        }
        
        # Rank assets by volatility
        volatilities = []
        for asset, trend_data in report['analysis']['trends'].items():
            if trend_data.get('volatility'):
                volatilities.append((asset, trend_data['volatility']))
        
        volatilities.sort(key=lambda x: x[1], reverse=True)
        risk_metrics['volatility_ranking'] = volatilities
        
        # Assess trend stability
        for asset, trend_data in report['analysis']['trends'].items():
            r_squared = trend_data.get('r_squared', 0)
            risk_metrics['trend_stability'][asset] = 'high' if r_squared > 0.7 else 'medium' if r_squared > 0.3 else 'low'
        
        # Assess correlation risk
        high_correlations = sum(1 for corr in report['analysis']['correlations'].values() 
                              if abs(corr.get('correlation', 0)) > 0.7)
        risk_metrics['correlation_risk'] = 'high' if high_correlations > 2 else 'medium' if high_correlations > 0 else 'low'
        
        return risk_metrics
    
    def save_report(self, report: Dict[str, Any], filename: str = 'consolidated_report.json'):
        """Save the consolidated report to a file"""
        os.makedirs('src/data', exist_ok=True)
        filepath = os.path.join('src/data', filename)
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Report saved to {filepath}")

    def save_report_as_csv(self, report: Dict[str, Any], filename: str = 'consolidated_report.csv'):
        """Save the consolidated report as a CSV file"""
        os.makedirs('src/data', exist_ok=True)
        filepath = os.path.join('src/data', filename)
        
        # Prepare data for CSV format
        csv_data = []
        timestamp = report['timestamp']
        timeframe = report['timeframe']
        
        # Add CFG data
        for pool_id, stats in report['cfg_report'].items():
            if stats:
                csv_data.append({
                    'timestamp': timestamp,
                    'timeframe': timeframe,
                    'asset_type': 'CFG',
                    'pool_id': pool_id,
                    'token_type': 'DROP',
                    'current_premium': stats.get('drop_premium', 'N/A'),
                    'trend': report['analysis']['trends'].get(f'cfg_pool_{pool_id}', {}).get('trend', 'N/A'),
                    'volatility': report['analysis']['trends'].get(f'cfg_pool_{pool_id}', {}).get('volatility', 'N/A'),
                    'momentum': report['analysis']['trends'].get(f'cfg_pool_{pool_id}', {}).get('momentum', 'N/A'),
                    'trend_stability': report['analysis']['risk_metrics']['trend_stability'].get(f'cfg_pool_{pool_id}', 'N/A')
                })
                
                csv_data.append({
                    'timestamp': timestamp,
                    'timeframe': timeframe,
                    'asset_type': 'CFG',
                    'pool_id': pool_id,
                    'token_type': 'TIN',
                    'current_premium': stats.get('tin_premium', 'N/A'),
                    'trend': report['analysis']['trends'].get(f'cfg_pool_{pool_id}', {}).get('trend', 'N/A'),
                    'volatility': report['analysis']['trends'].get(f'cfg_pool_{pool_id}', {}).get('volatility', 'N/A'),
                    'momentum': report['analysis']['trends'].get(f'cfg_pool_{pool_id}', {}).get('momentum', 'N/A'),
                    'trend_stability': report['analysis']['risk_metrics']['trend_stability'].get(f'cfg_pool_{pool_id}', 'N/A')
                })
        
        # Add ONDO data
        if report['ondo_report']:
            csv_data.append({
                'timestamp': timestamp,
                'timeframe': timeframe,
                'asset_type': 'ONDO',
                'pool_id': 'N/A',
                'token_type': 'ONDO',
                'current_premium': report['ondo_report'].get('current_premium', 'N/A'),
                'trend': report['analysis']['trends'].get('ondo_current_premium', {}).get('trend', 'N/A'),
                'volatility': report['analysis']['trends'].get('ondo_current_premium', {}).get('volatility', 'N/A'),
                'momentum': report['analysis']['trends'].get('ondo_current_premium', {}).get('momentum', 'N/A'),
                'trend_stability': report['analysis']['risk_metrics']['trend_stability'].get('ondo_current_premium', 'N/A')
            })
        
        # Write correlation data
        correlation_filepath = os.path.join('src/data', 'correlations.csv')
        with open(correlation_filepath, 'w', newline='') as f:
            correlation_writer = csv.writer(f)
            correlation_writer.writerow(['Asset Pair', 'Correlation', 'Significance'])
            
            for pair, corr_data in report['analysis']['correlations'].items():
                if corr_data['correlation'] is not None:
                    correlation_writer.writerow([
                        pair,
                        f"{corr_data['correlation']:.3f}",
                        f"{corr_data['significance']:.3f}"
                    ])
        
        # Write main report CSV
        if csv_data:
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=csv_data[0].keys())
                writer.writeheader()
                writer.writerows(csv_data)
            
            print(f"CSV report saved to {filepath}")
            print(f"Correlation data saved to {correlation_filepath}")

    def save_report_as_pdf(self, report: Dict[str, Any], filename: str = 'consolidated_report.pdf'):
        """Save the consolidated report as a PDF file with formatting"""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        except ImportError:
            logger.error("reportlab package is required for PDF export. Please install it with: pip install reportlab")
            return

        os.makedirs('src/data', exist_ok=True)
        filepath = os.path.join('src/data', filename)
        
        # Create the PDF document
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30
        )
        story.append(Paragraph("RWA Premium Tracker Report", title_style))
        story.append(Spacer(1, 12))
        
        # Timestamp and timeframe
        story.append(Paragraph(f"Generated: {report['timestamp']}", styles['Normal']))
        story.append(Paragraph(f"Timeframe: {report['timeframe']}", styles['Normal']))
        story.append(Spacer(1, 20))
        
        # CFG Summary Section
        story.append(Paragraph("CFG Summary", styles['Heading2']))
        for pool_id, stats in report['cfg_report'].items():
            if stats:
                story.append(Paragraph(f"Pool: {pool_id}", styles['Heading3']))
                data = [
                    ["Metric", "Value"],
                    ["DROP Premium", f"{format_value(stats.get('drop_premium'))}%"],
                    ["TIN Premium", f"{format_value(stats.get('tin_premium'))}%"]
                ]
                t = Table(data, colWidths=[2*inch, 1.5*inch])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                ]))
                story.append(t)
                story.append(Spacer(1, 12))
        
        # ONDO Summary Section
        story.append(Paragraph("ONDO Summary", styles['Heading2']))
        if report['ondo_report']:
            ondo_stats = report['ondo_report']
            data = [
                ["Metric", "Value"],
                ["Current Premium", f"{format_value(ondo_stats.get('current_premium'))}%"],
                ["Average Premium", f"{format_value(ondo_stats.get('avg_premium'))}%"],
                ["Minimum Premium", f"{format_value(ondo_stats.get('min_premium'))}%"],
                ["Maximum Premium", f"{format_value(ondo_stats.get('max_premium'))}%"]
            ]
            t = Table(data, colWidths=[2*inch, 1.5*inch])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
            ]))
            story.append(t)
        story.append(Spacer(1, 20))
        
        # Trend Analysis Section
        story.append(Paragraph("Trend Analysis", styles['Heading2']))
        for asset, trend_data in report['analysis']['trends'].items():
            if trend_data:
                story.append(Paragraph(f"Asset: {asset}", styles['Heading3']))
                data = [
                    ["Metric", "Value"],
                    ["Trend", trend_data.get('trend', 'N/A')],
                    ["Volatility", f"{format_value(trend_data.get('volatility'))}%"],
                    ["Momentum", f"{format_value(trend_data.get('momentum'))}%"]
                ]
                t = Table(data, colWidths=[2*inch, 1.5*inch])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                ]))
                story.append(t)
                story.append(Spacer(1, 12))
        
        # Market Insights Section
        story.append(Paragraph("Market Insights", styles['Heading2']))
        insights = report['analysis']['market_insights']
        
        if insights['summary']:
            story.append(Paragraph("Key Observations:", styles['Heading3']))
            for insight in insights['summary']:
                story.append(Paragraph(f"• {insight}", styles['Normal']))
            story.append(Spacer(1, 12))
            
        if insights['opportunities']:
            story.append(Paragraph("Opportunities:", styles['Heading3']))
            for opportunity in insights['opportunities']:
                story.append(Paragraph(f"• {opportunity}", styles['Normal']))
            story.append(Spacer(1, 12))
            
        if insights['risks']:
            story.append(Paragraph("Risks:", styles['Heading3']))
            for risk in insights['risks']:
                story.append(Paragraph(f"• {risk}", styles['Normal']))
        
        # Build the PDF
        doc.build(story)
        print(f"PDF report saved to {filepath}")

def format_value(value, format_str='.2f'):
    """Format a value with proper handling of N/A"""
    if value is None or value == 'N/A':
        return 'N/A'
    try:
        return f"{value:{format_str}}"
    except (ValueError, TypeError):
        return str(value)

def main():
    parser = argparse.ArgumentParser(description='Consolidated RWA Premium/Discount Tracker')
    parser.add_argument('--timeframe', type=str, default='daily',
                      choices=['daily', 'weekly', 'monthly', 'all'],
                      help='Timeframe for report generation')
    parser.add_argument('--report-only', action='store_true',
                      help='Only generate report without fetching new data')
    parser.add_argument('--format', type=str, default='both',
                      choices=['json', 'csv', 'pdf', 'all'],
                      help='Output format for the report')
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    tracker = ConsolidatedTracker()
    
    if not args.report_only:
        print("Fetching current data from both trackers...")
        current_data = tracker.fetch_current_data()
        print("\nCurrent Data:")
        print(json.dumps(current_data, indent=2))
    
    print(f"\nGenerating consolidated {args.timeframe} report...")
    report = tracker.generate_consolidated_report(args.timeframe)
    
    # Save reports in specified format(s)
    if args.format in ['json', 'both', 'all']:
        tracker.save_report(report)
    if args.format in ['csv', 'both', 'all']:
        tracker.save_report_as_csv(report)
    if args.format in ['pdf', 'all']:
        tracker.save_report_as_pdf(report)
    
    print("\nReport Summary:")
    print("=" * 50)
    
    # Print CFG summary
    print("\nCFG Summary:")
    for pool_id, stats in report['cfg_report'].items():
        if stats:
            print(f"\n{pool_id}:")
            print(f"DROP Premium: {format_value(stats.get('drop_premium'))}%")
            print(f"TIN Premium: {format_value(stats.get('tin_premium'))}%")
    
    # Print ONDO summary
    print("\nONDO Summary:")
    ondo_stats = report['ondo_report']
    if ondo_stats:
        print(f"Current Premium: {format_value(ondo_stats.get('current_premium'))}%")
        print(f"Average Premium: {format_value(ondo_stats.get('avg_premium'))}%")
        print(f"Range: {format_value(ondo_stats.get('min_premium'))}% to {format_value(ondo_stats.get('max_premium'))}%")
    
    # Print Analysis Summary
    print("\nAnalysis Summary:")
    print("=" * 50)
    
    # Print Trends
    print("\nTrend Analysis:")
    for asset, trend_data in report['analysis']['trends'].items():
        if not trend_data:
            continue
            
        print(f"\n{asset}:")
        print(f"Trend: {trend_data.get('trend', 'N/A')}")
        print(f"Volatility: {format_value(trend_data.get('volatility'))}%")
        print(f"Momentum: {format_value(trend_data.get('momentum'))}%")
    
    # Print Market Insights
    print("\nMarket Insights:")
    insights = report['analysis']['market_insights']
    if insights['summary']:
        print("\nKey Observations:")
        for insight in insights['summary']:
            print(f"- {insight}")
    if insights['opportunities']:
        print("\nOpportunities:")
        for opportunity in insights['opportunities']:
            print(f"- {opportunity}")
    if insights['risks']:
        print("\nRisks:")
        for risk in insights['risks']:
            print(f"- {risk}")
    
    # Print Risk Metrics
    print("\nRisk Analysis:")
    risk_metrics = report['analysis']['risk_metrics']
    print(f"\nPortfolio Correlation Risk: {risk_metrics['correlation_risk']}")
    print("\nVolatility Ranking:")
    for asset, vol in risk_metrics['volatility_ranking']:
        print(f"- {asset}: {format_value(vol)}%")

if __name__ == "__main__":
    main() 