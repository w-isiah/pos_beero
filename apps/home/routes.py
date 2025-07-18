from apps.home import blueprint
from flask import render_template, request, session, flash, redirect, url_for
from flask_login import login_required, current_user
from jinja2 import TemplateNotFound
from apps import get_db_connection
import logging

from flask import render_template, redirect, url_for, flash
from apps import get_db_connection
from datetime import datetime





@blueprint.route('/index')
def index():
    if 'id' not in session:
        flash('Login required to access this page.', 'error')
        return redirect(url_for('authentication_blueprint.login'))

    try:
        with get_db_connection() as connection:
            with connection.cursor(dictionary=True) as cursor:
                # Fetch user info
                cursor.execute("SELECT * FROM users WHERE id = %s", (session['id'],))
                user = cursor.fetchone()

                if not user:
                    flash('User not found. Please log in again.', 'error')
                    return redirect(url_for('authentication_blueprint.login'))

                # Helper function to execute a single-value query
                def fetch_single_value(query, params=None):
                    cursor.execute(query, params or ())
                    result = cursor.fetchone()
                    return result[next(iter(result))] if result else 0

                # Financial summaries
                total_sales_today = fetch_single_value(
                    '''SELECT SUM(total_price) AS total_sales_today
                       FROM sales WHERE DATE(date_updated) = CURDATE() AND type = 'sales';''')

                total_items_sold_today = fetch_single_value(
                    '''SELECT SUM(qty) AS total_items_sold_today
                       FROM sales WHERE DATE(date_updated) = CURDATE() AND type = 'sales';''')

                total_sales_yesterday = fetch_single_value(
                    '''SELECT SUM(total_price) AS total_sales_yesterday
                       FROM sales WHERE DATE(date_updated) = CURDATE() - INTERVAL 1 DAY AND type = 'sales';''')

                total_expenses_today = fetch_single_value(
                    '''SELECT SUM(total_price) AS total_expenses_today
                       FROM sales WHERE DATE(date_updated) = CURDATE() AND type = 'expense';''')

                # Products to reorder
                cursor.execute('''
                    SELECT * FROM product_list
                    WHERE reorder_level > quantity
                    ORDER BY name
                ''')
                products_to_reorder = cursor.fetchall()

                # Formatting helper
                def format_to_ugx(amount):
                    return f"UGX {amount:,.2f}" if amount else "UGX 0"

                context = {
                    'total_sales_today': format_to_ugx(total_sales_today),
                    'total_sales_yesterday': format_to_ugx(total_sales_yesterday),
                    'total_expenses_today': format_to_ugx(total_expenses_today),
                    'total_items_sold_today': total_items_sold_today or 0,
                    'products_to_reorder': products_to_reorder,
                    'segment': 'index'
                }

                if user['role'] == 'admin':
                    return render_template('home/index.html', **context)
                elif user['role'] == 'class_teacher':
                    return render_template('home/user_index.html', **context)

                flash('Unauthorized role. Please log in again.', 'error')
                return redirect(url_for('authentication_blueprint.login'))

    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'danger')
        return redirect(url_for('authentication_blueprint.login'))






@blueprint.route('/<template>')
def route_template(template):
    """
    Renders dynamic templates from the 'home' folder.
    """
    try:
        if not template.endswith('.html'):
            template += '.html'
        
        segment = get_segment(request)
        return render_template("home/" + template, segment=segment)

    except TemplateNotFound:
        logging.error(f"Template {template} not found")
        return render_template('home/page-404.html', segment=segment), 404

    except Exception as e:
        logging.error(f"Error rendering template {template}: {str(e)}")
        return render_template('home/page-500.html', segment=segment), 500

def get_segment(request):
    """
    Extracts the last part of the URL path to identify the current page.
    """
    segment = request.path.strip('/').split('/')[-1]
    if not segment:
        segment = 'index'
    return segment
