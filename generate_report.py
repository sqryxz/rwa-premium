from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime
import sys
import os
import json

# Add src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def load_historical_data():
    """Load historical data from tracker data files"""
    data = {
        'cfg_data': {},
        'ondo_data': {}
    }
    
    # Load CFG historical data
    cfg_history_path = os.path.join('src', 'data', 'cfg_history.json')
    if os.path.exists(cfg_history_path):
        with open(cfg_history_path, 'r') as f:
            data['cfg_data'] = json.load(f)
    
    # Load Ondo historical data
    ondo_history_path = os.path.join('src', 'ondo_tracker', 'data', 'ondo_premium_history.json')
    if os.path.exists(ondo_history_path):
        with open(ondo_history_path, 'r') as f:
            data['ondo_data'] = json.load(f)
    
    return data

def analyze_cfg_premiums(senior_premium, junior_premium):
    """Analyze CFG premiums and provide insights"""
    insights = []
    
    # Analyze DROP (senior) premium
    if senior_premium > 30:
        insights.append("• High DROP premium indicates strong demand for senior tranches. Consider increasing DROP issuance or adjusting yield parameters.")
    elif senior_premium > 10:
        insights.append("• Moderate DROP premium suggests healthy market demand. Monitor for stability.")
    elif senior_premium < 0:
        insights.append("• DROP trading at discount signals potential market concerns. Review risk parameters and market conditions.")
    
    # Analyze TIN (junior) premium/discount
    if junior_premium < -50:
        insights.append("• Severe TIN discount indicates high risk perception. Consider:") 
        insights.append("  - Reviewing collateral quality and risk parameters")
        insights.append("  - Enhancing transparency on underlying assets")
        insights.append("  - Implementing additional credit enhancements")
    elif junior_premium < -20:
        insights.append("• Significant TIN discount suggests market uncertainty. Monitor risk metrics closely.")
    elif junior_premium > 0:
        insights.append("• TIN premium indicates strong confidence in pool performance.")
    
    # Analyze relationship between tranches
    spread = senior_premium - junior_premium
    if spread > 100:
        insights.append("• Large senior-junior spread indicates market polarization. Consider rebalancing tranche structure.")
    
    return insights

def analyze_ondo_metrics(metrics, trading_data):
    """Analyze Ondo metrics and provide insights"""
    insights = []
    
    # Analyze price premium
    if 'price_premium_pct' in metrics:
        premium = metrics['price_premium_pct']
        if premium > 5:
            insights.append("• Above-target price premium suggests strong demand. Consider:") 
            insights.append("  - Increasing USDY issuance")
            insights.append("  - Reviewing yield parameters")
        elif premium < -2:
            insights.append("• Price discount indicates potential market stress. Monitor liquidity conditions.")
        else:
            insights.append("• Price premium within target range. Maintain current parameters.")
    
    # Analyze yield premium
    if 'yield_premium' in metrics:
        yield_premium = metrics['yield_premium']
        if yield_premium < -10:
            insights.append("• Significant negative yield premium suggests:") 
            insights.append("  - Market may be overvaluing stability over yield")
            insights.append("  - Consider adjusting yield parameters to align with market rates")
        elif yield_premium > 2:
            insights.append("• Positive yield premium indicates competitive yield offering.")
    
    # Analyze trading metrics
    if trading_data:
        volume = sum(trading_data.get('volume_24h', {}).values()) if isinstance(trading_data.get('volume_24h'), dict) else 0
        liquidity = sum(trading_data.get('liquidity', {}).values()) if isinstance(trading_data.get('liquidity'), dict) else 0
        
        if volume > 250000:
            insights.append("• High trading volume indicates strong market activity.")
        elif volume < 50000:
            insights.append("• Low trading volume suggests need for improved market making.")
            
        if liquidity > 3000000:
            insights.append("• Strong liquidity position. Consider optimizing yield strategy.")
        elif liquidity < 1000000:
            insights.append("• Limited liquidity. Consider implementing liquidity incentives.")
    
    return insights

def create_pdf_report():
    # Load historical data
    historical_data = load_historical_data()
    
    # Create the PDF document
    doc = SimpleDocTemplate(
        "rwa_findings_report.pdf",
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Get styles
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    heading_style = styles['Heading2']
    subheading_style = styles['Heading3']
    normal_style = styles['Normal']
    
    # Custom style for findings
    finding_style = ParagraphStyle(
        'FindingStyle',
        parent=styles['Normal'],
        spaceAfter=12,
        leftIndent=20,
        firstLineIndent=0
    )
    
    # Add title
    title = Paragraph("RWA Premium Tracker Findings Report", title_style)
    elements.append(title)
    elements.append(Spacer(1, 20))
    
    # Add date
    date_text = Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style)
    elements.append(date_text)
    elements.append(Spacer(1, 30))
    
    # CFG Findings Section
    cfg_title = Paragraph("CFG Findings", heading_style)
    elements.append(cfg_title)
    elements.append(Spacer(1, 12))
    
    # Process CFG findings from historical data
    if historical_data['cfg_data']:
        for pool_id, pool_data in historical_data['cfg_data'].items():
            # Add pool title
            pool_title = Paragraph(f"Pool: {pool_data.get('pool_name', pool_id)}", finding_style)
            elements.append(pool_title)
            
            latest_data = pool_data.get('latest_update', {})
            if 'tranches' in latest_data:
                senior_premium = None
                junior_premium = None
                
                # Process senior tranche (DROP)
                if 'senior' in latest_data['tranches']:
                    senior_data = latest_data['tranches']['senior']
                    senior_premium = senior_data.get('discount_premium_percentage', 0)
                    drop_title = Paragraph("<b>DROP Token Premium</b> (Impact: High)", finding_style)
                    elements.append(drop_title)
                    drop_desc = Paragraph(f"Current premium: {senior_premium:.2f}%", finding_style)
                    elements.append(drop_desc)
                
                # Process junior tranche (TIN)
                if 'junior' in latest_data['tranches']:
                    junior_data = latest_data['tranches']['junior']
                    junior_premium = junior_data.get('discount_premium_percentage', 0)
                    tin_title = Paragraph("<b>TIN Token Premium</b> (Impact: High)", finding_style)
                    elements.append(tin_title)
                    tin_desc = Paragraph(f"Current premium: {junior_premium:.2f}%", finding_style)
                    elements.append(tin_desc)
                
                # Add analysis and insights
                if senior_premium is not None and junior_premium is not None:
                    elements.append(Spacer(1, 12))
                    analysis_title = Paragraph("<b>Analysis & Actionable Insights</b>", finding_style)
                    elements.append(analysis_title)
                    
                    insights = analyze_cfg_premiums(senior_premium, junior_premium)
                    for insight in insights:
                        elements.append(Paragraph(insight, finding_style))
            
            elements.append(Spacer(1, 12))
    
    elements.append(Spacer(1, 20))
    
    # Ondo Findings Section
    ondo_title = Paragraph("Ondo Findings", heading_style)
    elements.append(ondo_title)
    elements.append(Spacer(1, 12))
    
    # Process Ondo findings from historical data
    if historical_data['ondo_data']:
        latest_ondo = historical_data['ondo_data'][-1] if isinstance(historical_data['ondo_data'], list) else {}
        
        metrics = latest_ondo.get('premium_metrics', {})
        trading = latest_ondo.get('trading_analysis', {})
        
        # Add USDY yield information if available
        if metrics:
            usdy_title = Paragraph("<b>USDY Yield</b> (Impact: High)", finding_style)
            elements.append(usdy_title)
            
            if 'usdy_yield' in metrics:
                usdy_desc = Paragraph(f"Current Yield: {metrics['usdy_yield']:.2f}%", finding_style)
                elements.append(usdy_desc)
            
            if 'price_premium_pct' in metrics:
                elements.append(Paragraph(f"Price Premium: {metrics['price_premium_pct']:.2f}%", finding_style))
            if 'yield_premium' in metrics:
                elements.append(Paragraph(f"Yield Premium Spread: {metrics['yield_premium']:.2f}%", finding_style))
        
        # Add trading analysis if available
        if trading:
            trading_title = Paragraph("<b>Trading Analysis</b> (Impact: Medium)", finding_style)
            elements.append(trading_title)
            
            if 'volume_24h' in trading:
                volume_sum = sum(trading['volume_24h'].values()) if isinstance(trading['volume_24h'], dict) else 0
                elements.append(Paragraph(f"24h Trading Volume: ${volume_sum:,.2f}", finding_style))
            if 'liquidity' in trading:
                liquidity_sum = sum(trading['liquidity'].values()) if isinstance(trading['liquidity'], dict) else 0
                elements.append(Paragraph(f"Total Liquidity: ${liquidity_sum:,.2f}", finding_style))
        
        # Add analysis and insights
        elements.append(Spacer(1, 12))
        analysis_title = Paragraph("<b>Analysis & Actionable Insights</b>", finding_style)
        elements.append(analysis_title)
        
        insights = analyze_ondo_metrics(metrics, trading)
        for insight in insights:
            elements.append(Paragraph(insight, finding_style))
    
    # Build the PDF
    doc.build(elements)

if __name__ == "__main__":
    create_pdf_report() 