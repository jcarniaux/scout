"""
HTML email templates for Scout reports.
"""
from typing import List, Dict, Any
from datetime import datetime


def base_template(title: str, body_html: str, footer: str = "") -> str:
    """
    Wrap content in responsive HTML email layout.

    Args:
        title: Email title
        body_html: HTML content
        footer: Optional footer HTML

    Returns:
        Complete HTML email
    """
    if not footer:
        footer = f'<p style="color: #666; font-size: 12px;">© {datetime.utcnow().year} Scout - Job Aggregation Platform</p>'

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 600px;
            margin: 20px auto;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
        }}
        .content {{
            padding: 30px;
        }}
        .table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        .table th {{
            background-color: #f8f9fa;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #dee2e6;
            font-size: 14px;
        }}
        .table td {{
            padding: 12px;
            border-bottom: 1px solid #dee2e6;
            font-size: 14px;
        }}
        .table tr:hover {{
            background-color: #f8f9fa;
        }}
        .table a {{
            color: #667eea;
            text-decoration: none;
        }}
        .table a:hover {{
            text-decoration: underline;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }}
        .badge-success {{
            background-color: #d4edda;
            color: #155724;
        }}
        .badge-info {{
            background-color: #d1ecf1;
            color: #0c5460;
        }}
        .badge-warning {{
            background-color: #fff3cd;
            color: #856404;
        }}
        .salary {{
            color: #28a745;
            font-weight: 600;
        }}
        .rating {{
            color: #ffc107;
            font-weight: 600;
        }}
        .cta-button {{
            display: inline-block;
            padding: 12px 24px;
            background-color: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            margin: 20px 0;
            font-weight: 600;
        }}
        .cta-button:hover {{
            background-color: #5568d3;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 20px 30px;
            text-align: center;
            border-top: 1px solid #dee2e6;
            font-size: 12px;
        }}
        .footer a {{
            color: #667eea;
            text-decoration: none;
        }}
        .summary-box {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 4px;
            margin: 20px 0;
        }}
        .summary-item {{
            display: inline-block;
            margin-right: 30px;
            margin-bottom: 10px;
        }}
        .summary-number {{
            font-size: 24px;
            font-weight: 700;
            color: #667eea;
        }}
        .summary-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
        </div>
        <div class="content">
            {body_html}
        </div>
        <div class="footer">
            {footer}
        </div>
    </div>
</body>
</html>"""


def jobs_table_html(jobs: List[Dict[str, Any]]) -> str:
    """
    Render a list of jobs as an HTML table.

    Args:
        jobs: List of job dicts

    Returns:
        HTML table
    """
    if not jobs:
        return '<p>No jobs found.</p>'

    rows = ""
    for job in jobs:
        title = job.get("title", "N/A")
        company = job.get("company", "N/A")
        location = job.get("location", "N/A")
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")
        rating = job.get("rating")
        job_url = job.get("job_url", "#")
        source = job.get("source", "").upper()

        salary_text = ""
        if salary_min and salary_max:
            salary_text = f'<span class="salary">${salary_min:,} - ${salary_max:,}</span>'
        elif salary_min:
            salary_text = f'<span class="salary">${salary_min:,}+</span>'

        rating_text = ""
        if rating:
            rating_text = f'<span class="rating">★ {rating:.1f}</span>'

        rows += f"""
        <tr>
            <td><strong><a href="{job_url}" target="_blank">{title}</a></strong><br><small style="color: #666;">{company}</small></td>
            <td>{location}</td>
            <td>{salary_text}</td>
            <td>{rating_text}</td>
            <td><span class="badge badge-info">{source}</span></td>
        </tr>
        """

    return f"""<table class="table">
    <thead>
        <tr>
            <th>Role & Company</th>
            <th>Location</th>
            <th>Salary</th>
            <th>Rating</th>
            <th>Source</th>
        </tr>
    </thead>
    <tbody>
        {rows}
    </tbody>
</table>"""


def status_summary_html(status_groups: Dict[str, List[Dict[str, Any]]]) -> str:
    """
    Render application pipeline summary.

    Args:
        status_groups: Dict mapping status -> list of jobs

    Returns:
        HTML summary
    """
    total = sum(len(jobs) for jobs in status_groups.values())

    status_labels = {
        "NOT_APPLIED": ("Not Applied", "badge-warning"),
        "APPLIED": ("Applied", "badge-info"),
        "RECRUITER_INTERVIEW": ("Recruiter Interview", "badge-info"),
        "TECHNICAL_INTERVIEW": ("Technical Interview", "badge-info"),
        "OFFER_RECEIVED": ("Offer Received", "badge-success"),
        "OFFER_ACCEPTED": ("Offer Accepted", "badge-success"),
    }

    summary_items = ""
    for status, jobs in sorted(status_groups.items()):
        label, badge_class = status_labels.get(status, (status, "badge-info"))
        count = len(jobs)
        summary_items += f"""
        <div class="summary-item">
            <div class="summary-number">{count}</div>
            <div class="summary-label">{label}</div>
        </div>
        """

    html = f"""
    <div class="summary-box">
        <h2 style="margin-top: 0;">Application Pipeline</h2>
        {summary_items}
        <div class="summary-item">
            <div class="summary-number" style="color: #764ba2;">{total}</div>
            <div class="summary-label">Total</div>
        </div>
    </div>
    """

    # Add tables for each status group
    for status, jobs in status_groups.items():
        label, _ = status_labels.get(status, (status, "badge-info"))
        if jobs:
            html += f"<h3>{label}</h3>\n"
            html += jobs_table_html(jobs)

    return html


def daily_report_email(jobs: List[Dict[str, Any]], date: str) -> str:
    """
    Build daily report email.

    Args:
        jobs: List of new jobs
        date: Date string for the report

    Returns:
        Complete HTML email
    """
    if not jobs:
        body = '<p>No new jobs posted in the last 24 hours.</p>'
    else:
        body = f'<p>Found <strong>{len(jobs)} new job opportunities</strong> in the last 24 hours:</p>\n'
        body += jobs_table_html(jobs)

    footer = f"""
    <p><a href="https://scout.carniaux.io" class="cta-button">View All Jobs</a></p>
    <p>Scout is your personal job aggregation platform. Check back daily for new opportunities in your field.</p>
    """

    return base_template(f"Scout Daily Report — {date}", body, footer)


def weekly_report_email(status_groups: Dict[str, List[Dict[str, Any]]], new_jobs_count: int, date: str) -> str:
    """
    Build weekly report email.

    Args:
        status_groups: Dict mapping application status -> list of jobs
        new_jobs_count: Count of new postings this week
        date: Date string for the report

    Returns:
        Complete HTML email
    """
    body = status_summary_html(status_groups)

    if new_jobs_count > 0:
        body += f'<p style="margin-top: 20px;"><strong>{new_jobs_count} new job postings</strong> were added this week.</p>'

    footer = f"""
    <p><a href="https://scout.carniaux.io" class="cta-button">View Your Pipeline</a></p>
    <p>Keep pushing towards your goals. You\'ve got this!</p>
    """

    return base_template(f"Scout Weekly Status — {date}", body, footer)
