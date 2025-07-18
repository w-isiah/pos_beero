from flask import render_template, request, jsonify, current_app,session
from datetime import datetime
import mysql.connector
import traceback
from apps import get_db_connection
from apps.sales import blueprint
import traceback
from flask import flash
from flask import Blueprint, request, jsonify, session, current_app
from datetime import datetime
import pytz
import traceback



@blueprint.route('/sales', methods=['GET'])
def sales():
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Fetch customer data
        cursor.execute('SELECT * FROM customer_list ORDER BY name')
        customers = cursor.fetchall()

        # Fetch product data with category information using a JOIN
        cursor.execute('''
            SELECT p.*, c.name AS category_name, c.description AS category_description
            FROM product_list p
            INNER JOIN category_list c ON p.category_id = c.CategoryID
            ORDER BY name
        ''')
        products = cursor.fetchall()

    except mysql.connector.Error as e:
        current_app.logger.error(f"Database error: {e}")
        return "Database error", 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return render_template('sales/sale.html', customers=customers, products=products, segment='sales')











# Kampala timezone function
def get_kampala_time():
    kampala = pytz.timezone("Africa/Kampala")
    return datetime.now(kampala)




@blueprint.route('/save_sale', methods=['POST'])
def save_sale():
    connection = None
    cursor = None
    try:
        if 'id' not in session:
            return jsonify({'message': 'You must be logged in to make a sale.'}), 401

        user_id = session['id']
        data = request.get_json()
        customer_id = data.get('customer_id')
        items = data.get('cart_items')
        total_price = data.get('total_price')
        discounted_price = data.get('discounted_price')

        current_app.logger.debug(f"Received data: {data}")

        # Validate required fields
        if not customer_id or not items:
            return jsonify({'message': 'Missing customer ID or cart items.'}), 400
        if len(items) == 0:
            return jsonify({'message': 'Cart items cannot be empty.'}), 400
        if not total_price or discounted_price is None:
            return jsonify({'message': 'Total price or discounted price missing.'}), 400

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        connection.start_transaction()

        # Insert into sales_summary
        cursor.execute("""
            INSERT INTO sales_summary (customer_id, total_price, discounted_price)
            VALUES (%s, %s, %s)
        """, (customer_id, total_price, discounted_price))
        sale_id = cursor.lastrowid

        for item in items:
            product_id = item.get('product_id')
            price = item.get('price')
            quantity = item.get('quantity')
            discount = item.get('discount', 0.00)
            total_item_price = item.get('total_price')
            discounted_item_price = item.get('discounted_price')

            current_app.logger.debug(f"Processing item: {item}")

            if not price or not quantity or quantity <= 0:
                return jsonify({'message': f'Invalid data for product ID {product_id}.'}), 400
            if total_item_price is None or discounted_item_price is None:
                return jsonify({'message': f'Missing price data for product ID {product_id}.'}), 400

            # Insert sale item with date_updated and type='sales'
            log_time = get_kampala_time()
            cursor.execute("""
                INSERT INTO sales (
                    ProductID, customer_id, price, discount, qty, total_price,
                    discounted_price, date_updated, type
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                product_id, customer_id, price, discount, quantity,
                total_item_price, discounted_item_price, log_time, 'sales'
            ))

            # Update inventory
            cursor.execute("""
                UPDATE product_list SET quantity = quantity - %s WHERE ProductID = %s
            """, (quantity, product_id))

            # Log inventory change with Kampala time
            cursor.execute("""
                INSERT INTO inventory_logs (product_id, quantity_change, reason, log_date, user_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (product_id, -quantity, 'sale', log_time, user_id))

        connection.commit()
        return jsonify({'message': 'Sale data added and inventory updated successfully!'}), 201

    except Exception as e:
        if connection:
            connection.rollback()
        current_app.logger.error(f"Error: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({'message': 'Error occurred: ' + str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

















@blueprint.route('/sales_view', methods=['GET', 'POST'])
def sales_view():
    if 'id' not in session:
        flash('Login required to access this page.', 'error')
        return redirect(url_for('authentication_blueprint.login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Get user info from DB using session id
        cursor.execute("SELECT * FROM users WHERE id = %s", (session['id'],))
        user = cursor.fetchone()
        if not user:
            flash('User not found. Please log in again.', 'error')
            return redirect(url_for('authentication_blueprint.login'))

        today = datetime.today().strftime('%Y-%m-%d')
        start_date = today
        end_date = today
        searched = False

        if request.method == 'POST':
            start_date = request.form.get('start_date') or today
            end_date = request.form.get('end_date') or today
            searched = True

        # ---- Sales Data ----
        cursor.execute("""
            SELECT 
                s.salesID,
                p.name AS product_name,
                c.name AS customer_name,
                s.price,
                s.discount,
                s.discounted_price,
                s.qty,
                s.date_updated
            FROM sales s
            JOIN product_list p ON s.ProductID = p.ProductID
            JOIN customer_list c ON s.customer_id = c.CustomerID
            WHERE s.type = 'sales' AND DATE(s.date_updated) BETWEEN %s AND %s
        """, (start_date, end_date))
        sales = cursor.fetchall()

        # ---- Sales Totals ----
        cursor.execute("""
            SELECT 
                SUM(s.qty) AS total_quantity,
                SUM(s.total_price) AS total_sales
            FROM sales s
            WHERE s.type = 'sales' AND DATE(s.date_updated) BETWEEN %s AND %s
        """, (start_date, end_date))
        totals = cursor.fetchone()
        total_sales = totals['total_sales'] or 0
        total_quantity = totals['total_quantity'] or 0

        # ---- Expense Data ----
        cursor.execute("""
            SELECT 
                s.salesID,
                s.ProductID AS expense_code,
                s.expense_name,
                c.name AS customer_name,
                s.price AS amount,
                s.description,
                s.date_updated
            FROM sales s
            JOIN customer_list c ON s.customer_id = c.CustomerID
            WHERE s.type = 'expense' AND DATE(s.date_updated) BETWEEN %s AND %s
        """, (start_date, end_date))
        expenses = cursor.fetchall()

        # ---- Expense Total ----
        cursor.execute("""
            SELECT 
                SUM(s.total_price) AS total_expenses
            FROM sales s
            WHERE s.type = 'expense' AND DATE(s.date_updated) BETWEEN %s AND %s
        """, (start_date, end_date))
        expense_total = cursor.fetchone()
        total_expenses = expense_total['total_expenses'] or 0

    finally:
        cursor.close()
        connection.close()

    # Format numbers
    formatted_total_sales = f"{total_sales:,.2f}"
    formatted_total_expenses = f"{total_expenses:,.2f}"
    formatted_total_quantity = f"{total_quantity:,}"

    return render_template(
        'sales/sales_view.html',
        user=user,  # pass user to template for access to user.role etc.
        sales=sales,
        expenses=expenses,
        total_sales=formatted_total_sales,
        total_expenses=formatted_total_expenses,
        total_quantity=formatted_total_quantity,
        start_date=start_date,
        end_date=end_date,
        searched=searched,
        segment='sales_view'
    )













from datetime import datetime
import pytz
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash
)

def get_kampala_time(as_string: bool = False, fmt: str = "%Y-%m-%d %H:%M:%S") -> datetime | str:
    kampala_tz = pytz.timezone("Africa/Kampala")
    kampala_time = datetime.now(kampala_tz)
    return kampala_time.strftime(fmt) if as_string else kampala_time

@blueprint.route('/edit_sale/<int:salesID>', methods=['GET', 'POST'])
def edit_sale(salesID):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch the sale record
        cursor.execute('SELECT * FROM sales WHERE salesID = %s', (salesID,))
        sale = cursor.fetchone()

        if not sale:
            flash("Sale record not found!", "warning")
            return redirect(url_for('sales_blueprint.sales_view'))

        # Get customers list
        cursor.execute('SELECT CustomerID, name FROM customer_list')
        customers = cursor.fetchall()

        if request.method == 'POST':
            # Get form data
            customer_id = request.form.get('customer_id')
            price = request.form.get('price')
            discount = request.form.get('discount') or 0
            qty = request.form.get('qty')
            date_updated_str = request.form.get('date_updated')

            # Validate and parse date_updated
            try:
                # Convert string to datetime object (local time)
                date_updated = datetime.strptime(date_updated_str, '%Y-%m-%dT%H:%M')
                # Convert to Kampala timezone aware datetime
                kampala_tz = pytz.timezone("Africa/Kampala")
                date_updated = kampala_tz.localize(date_updated)
                # Format for SQL
                date_updated_formatted = date_updated.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                flash("Invalid date format.", "danger")
                return redirect(request.url)

            # Update the sale record
            update_query = '''
                UPDATE sales 
                SET customer_id = %s,
                    price = %s,
                    discount = %s,
                    qty = %s,
                    date_updated = %s
                WHERE salesID = %s
            '''
            cursor.execute(update_query, (
                customer_id,
                price,
                discount,
                qty,
                date_updated_formatted,
                salesID
            ))
            connection.commit()

            flash("Sale updated successfully!", "success")
            return redirect(url_for('sales_blueprint.sales_view'))

        # GET request — render template with sale and customers
        return render_template('sales/edit_sale.html', sale=sale, customers=customers)

    finally:
        cursor.close()
        connection.close()










@blueprint.route('/discount_percentage', methods=['GET', 'POST'])
def discount_percentage():
    if request.method == 'POST':
        try:
            original_price = float(request.form['original_price'])
            discounted_price = float(request.form['discounted_price'])

            if original_price <= 0 or discounted_price < 0:
                raise ValueError("Prices must be positive numbers.")

            discount_amount = original_price - discounted_price
            discount_percentage = (discount_amount / original_price) * 100

            return render_template('sales/discount_percentage.html',
                                   original_price=original_price, 
                                   discounted_price=discounted_price,
                                   discount_amount=discount_amount,
                                   discount_percentage=discount_percentage)
        except (ValueError, TypeError):
            error = "Please enter valid numeric values."
            return render_template('sales/discount_percentage.html',  error=error)

    return render_template('sales/discount_percentage.html')









from datetime import datetime
import pytz

# Get Kampala time
def get_kampala_time():
    kampala = pytz.timezone("Africa/Kampala")
    return datetime.now(kampala)

@blueprint.route('/delete_sale/<int:sales_id>',methods=['GET', 'POST'])
def delete_sale(sales_id):
    try:
        with get_db_connection() as connection:
            with connection.cursor(dictionary=True) as cursor:
                # 1. Fetch the sale record
                cursor.execute("""
                    SELECT qty, ProductID, price 
                    FROM sales 
                    WHERE salesID = %s AND type = 'sales'
                """, (sales_id,))
                sale = cursor.fetchone()

                if not sale:
                    flash("Sale record not found or is not of type 'sales'.", "warning")
                    return redirect(url_for('sales_blueprint.sales_view'))

                product_id = sale['ProductID']
                restored_qty = sale['qty']
                sale_price = sale['price']

                # 2. Restore product quantity
                cursor.execute("""
                    UPDATE product_list 
                    SET quantity = quantity + %s 
                    WHERE ProductID = %s
                """, (restored_qty, product_id))

                # 3. Log inventory change
                cursor.execute("""
                    INSERT INTO inventory_logs (
                        product_id, quantity_change, log_date, reason, user_id, old_price
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    product_id,
                    restored_qty,
                    get_kampala_time(),  # Using Kampala local time
                    "Sale deleted, stock restored",
                    session.get('id'),
                    sale_price
                ))

                # 4. Delete the sale
                cursor.execute("DELETE FROM sales WHERE salesID = %s", (sales_id,))
                connection.commit()

                flash("Sale deleted and inventory log updated.", "success")

    except Exception as e:
        flash(f"Error deleting sale: {str(e)}", "danger")

    return redirect(url_for('sales_blueprint.sales_view'))







@blueprint.route('/<template>')
def route_template(template):
    """Renders a dynamic template page."""
    try:
        if not template.endswith('.html'):
            template += '.html'

        segment = get_segment(request)

        return render_template(f"sales/{template}", segment=segment)

    except TemplateNotFound:
        return render_template('home/page-404.html'), 404

    except Exception as e:
        return render_template('home/page-500.html'), 500













def get_segment(request):
    """Extracts the last part of the URL to determine the current page."""
    try:
        segment = request.path.split('/')[-1]
        return segment if segment else 'sales'
    except Exception:
        return None
