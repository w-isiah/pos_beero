from apps.home import blueprint
from flask import render_template, request, session, flash, redirect, url_for
from jinja2 import TemplateNotFound
from apps import get_db_connection
import logging
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

                def fetch_single_value(query, params=None):
                    cursor.execute(query, params or ())
                    result = cursor.fetchone()
                    return result[next(iter(result))] if result else 0

                # Financial summaries
                total_sales_today = fetch_single_value('''
                    SELECT SUM(total_price) AS total_sales_today
                    FROM sales
                    WHERE DATE(date_updated) = CURDATE()
                      AND type = 'sales'
                      AND order_status = 'Completed'
                ''')

                total_expenses_today = fetch_single_value('''
                    SELECT SUM(total_price) AS total_expenses_today
                    FROM sales
                    WHERE DATE(date_updated) = CURDATE()
                      AND type = 'expense'
                ''')

                # Products to reorder
                cursor.execute('''
                    SELECT * FROM product_list
                    WHERE reorder_level > quantity
                    ORDER BY name
                ''')
                products_to_reorder = cursor.fetchall()

                def format_to_ugx(amount):
                    return f"UGX {amount:,.2f}" if amount else "UGX 0"

                context = {
                    'total_sales_today': format_to_ugx(total_sales_today),
                    'total_expenses_today': format_to_ugx(total_expenses_today),
                    'products_to_reorder': products_to_reorder,
                    'segment': 'index'
                }

                role = user.get('role')
                if role == 'manager':
                    return render_template('home/manager_index.html', **context)
                elif role in ('waiter', 'user'):
                    return render_template('home/user_index.html', **context)
                elif role == 'admin':
                    return render_template('home/admin_index.html', **context)
                elif role == 'super_admin':
                    return render_template('home/super_admin_index.html', **context)

                flash('Unauthorized role. Please log in again.', 'error')
                return redirect(url_for('authentication_blueprint.login'))

    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'danger')
        return redirect(url_for('authentication_blueprint.login'))


@blueprint.route('/<template>')
def route_template(template):
    """Render dynamic templates from the 'home' folder."""
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
    """Extracts the last part of the URL path to identify the current page."""
    segment = request.path.strip('/').split('/')[-1]
    return segment or 'index'


# ✅ GLOBAL: Inject notifications into every template


@blueprint.app_context_processor
def inject_notifications():
    if 'id' not in session:
        return {}

    user_id = session.get('id')
    user_role = session.get('role')

    try:
        with get_db_connection() as connection:
            with connection.cursor(dictionary=True) as cursor:
                # Build base query
                base_query = '''
                    SELECT salesID, ProductID, qty, total_price, order_status, date_updated
                    FROM sales
                    WHERE order_status IN ('pending', 'processing', 'edited', 'credit_sale', 'recieved_on_credit')
                '''

                # Filter by user_id only for waiters or users
                if user_role in ('waiter', 'user'):
                    base_query += ' AND user_id = %s ORDER BY date_updated DESC LIMIT 10'
                    cursor.execute(base_query, (user_id,))
                else:
                    base_query += ' ORDER BY date_updated DESC LIMIT 10'
                    cursor.execute(base_query)

                orders = cursor.fetchall()

                def format_to_ugx(amount):
                    return f"UGX {amount:,.2f}" if amount else "UGX 0"

                notifications = [
                    {
                        'icon': 'fas fa-shopping-cart',
                        'text': f"Order #{o['salesID']} ({o['order_status'].capitalize()}) - {o['qty']} items - {format_to_ugx(o['total_price'])}",
                        'time': o['date_updated'].strftime('%b %d %H:%M')
                    }
                    for o in orders
                ]

                return {'notifications': notifications}

    except Exception as e:
        logging.error(f"Notification context injection failed: {str(e)}")
        return {'notifications': []}

