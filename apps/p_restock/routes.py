from flask import render_template, request, redirect, url_for, flash, session
from apps.p_restock import blueprint
from mysql.connector import Error
from apps import get_db_connection
import logging
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import random
import re
from jinja2 import TemplateNotFound


# Route for the 'products' restock page
@blueprint.route('/p_restock')
def p_restock():
    """Renders the 'products' restock page."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute('''
            SELECT 
                p.*, 
                p.name AS product_name,
                c.name AS category_name, 
                (p.quantity * p.price) AS total_price
            FROM product_list p
            JOIN category_list c ON p.category_id = c.CategoryID
            ORDER BY p.name
        ''')
        products = cursor.fetchall()

    except Error as e:
        logging.exception("Database error while fetching products for restock.")
        flash("An error occurred while fetching products.", "error")
        return render_template('home/page-500.html'), 500

    finally:
        cursor.close()
        connection.close()

    return render_template(
        'p_restock/p_restock.html',
        products=products,
        segment='p_restock'
    )



@blueprint.route('/restock_item', methods=['POST'])
def restock_item():
    # Ensure the user is logged in
    if 'id' not in session:
        flash("You must be logged in to restock products.", "danger")
        return redirect(url_for('authentication_blueprint.login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Retrieve and validate form data
        sku = request.form.get('sku')
        restock_quantity = request.form.get('restock_quantity')
        user_id = session['id']

        if not sku or not restock_quantity:
            flash("Missing SKU or quantity.", "danger")
            return redirect(url_for('sales_blueprint.p_restock'))

        try:
            restock_quantity = int(restock_quantity)
            if restock_quantity <= 0:
                raise ValueError
        except ValueError:
            flash("Restock quantity must be a positive integer.", "warning")
            return redirect(url_for('sales_blueprint.p_restock'))

        # Fetch product
        cursor.execute('SELECT * FROM product_list WHERE sku = %s', (sku,))
        product = cursor.fetchone()

        if not product:
            flash(f"Product with SKU {sku} does not exist!", "danger")
            return redirect(url_for('sales_blueprint.p_restock'))

        # Update quantity
        new_quantity = product['quantity'] + restock_quantity
        cursor.execute('UPDATE product_list SET quantity = %s WHERE sku = %s', (new_quantity, sku))
        connection.commit()

        # Log restock
        cursor.execute("""
            INSERT INTO inventory_logs (product_id, quantity_change, reason, log_date, user_id)
            VALUES (%s, %s, %s, NOW(), %s)
        """, (product['ProductID'], restock_quantity, 'restock', user_id))
        connection.commit()

        flash(f"✅ Restocked {restock_quantity} units of '{product['name']}' (SKU: {sku}). New quantity: {new_quantity}.", "success")

    except Exception as e:
        connection.rollback()
        logging.exception("Error during restock operation")
        flash("⚠️ An unexpected error occurred during restocking.", "danger")

    finally:
        cursor.close()
        connection.close()

    # Redirect to avoid form re-submission
    return redirect(url_for('sales_blueprint.p_restock'))



# Route to handle template rendering
@blueprint.route('/<template>')
def route_template(template):
    try:
        if not template.endswith('.html'):
            template += '.html'

        # Detect the current page
        segment = get_segment(request)

        # Serve the file from app/templates/home/FILE.html
        return render_template(f"home/{template}", segment=segment)

    except TemplateNotFound:
        return render_template('home/page-404.html'), 404

    except Exception as e:
        logging.error(f"Error rendering template: {e}")
        return render_template('home/page-500.html'), 500


# Helper function to extract the current page name from request
def get_segment(request):
    try:
        segment = request.path.split('/')[-1]
        return segment if segment else 'p_restock'
    except Exception as e:
        logging.error(f"Error extracting segment: {e}")
        return None
