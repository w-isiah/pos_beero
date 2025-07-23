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
        user_role = session.get('role', 'user')
        order_status = 'completed' if user_role not in ('user', 'waiter') else 'pending'
        log_time = get_kampala_time()

        data = request.get_json()
        current_app.logger.debug(f"Received data: {data}")

        customer_id = data.get('customer_id')
        items = data.get('cart_items', [])
        total_price = data.get('total_price')
        discounted_price = data.get('discounted_price')

        if not customer_id or not isinstance(items, list) or not items:
            return jsonify({'message': 'Missing customer ID or cart items.'}), 400

        if total_price is None or discounted_price is None:
            return jsonify({'message': 'Total or discounted price missing.'}), 400

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        connection.start_transaction()

        # Insert into sales_summary
        cursor.execute("""
            INSERT INTO sales_summary (
                customer_id, total_price, discounted_price, order_status, user_id, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (customer_id, total_price, discounted_price, order_status, user_id, log_time))
        sale_summary_id = cursor.lastrowid

        # Loop through each cart item
        for item in items:
            try:
                product_id = int(item.get('product_id'))
                quantity = int(item.get('quantity'))
                price = float(item.get('price'))
                discount = float(item.get('discount', 0))
                total_item_price = float(item.get('total_price', price * quantity))
                discounted_item_price = float(item.get('discounted_price', total_item_price - discount))
            except (TypeError, ValueError) as e:
                return jsonify({'message': f'Invalid data for product {item.get("product_id")}: {e}'}), 400

            if quantity <= 0:
                return jsonify({'message': f'Quantity must be greater than 0 for product ID {product_id}'}), 400

            # Get current product price (old_price)
            cursor.execute("SELECT price FROM product_list WHERE ProductID = %s", (product_id,))
            product = cursor.fetchone()
            if not product:
                return jsonify({'message': f'Product ID {product_id} not found.'}), 400

            old_price = product['price']

            # Insert into sales table
            cursor.execute("""
                INSERT INTO sales (
                    ProductID, customer_id, price, discount, qty, total_price,
                    discounted_price, date_updated, type, user_id, order_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                product_id, customer_id, price, discount, quantity,
                total_item_price, discounted_item_price, log_time,
                'sales', user_id, order_status
            ))

            # Update stock
            cursor.execute("""
                UPDATE product_list SET quantity = quantity - %s WHERE ProductID = %s
            """, (quantity, product_id))

            # Insert detailed inventory log
            cursor.execute("""
                INSERT INTO inventory_logs (
                    product_id, quantity_change, log_date, reason,
                    order_status, price_change, user_id, sales_user_id, old_price
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                product_id,
                -quantity,
                log_time,
                'New sale',
                order_status,
                price,
                user_id,         # who is logged in now
                user_id,         # who made the sale
                old_price
            ))

        connection.commit()
        return jsonify({'message': 'Sale submitted successfully!'}), 201

    except Exception as e:
        if connection:
            connection.rollback()
        current_app.logger.error(f"Error: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({'message': f'Error occurred: {str(e)}'}), 500

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
        # Fetch current user info
        cursor.execute("SELECT * FROM users WHERE id = %s", (session['id'],))
        user = cursor.fetchone()

        # Fetch all users for filter dropdown
        cursor.execute("SELECT id, username FROM users")
        all_users = cursor.fetchall()

        # Fetch all products for filter dropdown
        cursor.execute("SELECT ProductID, name FROM product_list")
        all_products = cursor.fetchall()

        today = datetime.today().strftime('%Y-%m-%d')
        start_date = end_date = today
        selected_user_id = selected_product_id = None

        if request.method == 'POST':
            start_date = request.form.get('start_date') or today
            end_date = request.form.get('end_date') or today
            selected_user_id = request.form.get('user_id') or None
            selected_product_id = request.form.get('product_id') or None

        # === SALES QUERY ===
        sales_query = """
            SELECT 
                s.salesID,
                p.name AS product_name,
                c.name AS customer_name,
                s.price,
                s.discount,
                s.discounted_price,
                s.qty,
                s.total_price,
                s.date_updated,
                u.username AS sold_by
            FROM sales s
            JOIN product_list p ON s.ProductID = p.ProductID
            JOIN customer_list c ON s.customer_id = c.CustomerID
            LEFT JOIN users u ON s.user_id = u.id
            WHERE s.type = 'sales' 
              AND s.order_status = 'Completed'
              AND DATE(s.date_updated) BETWEEN %s AND %s
        """
        query_params = [start_date, end_date]

        if selected_user_id:
            sales_query += " AND s.user_id = %s"
            query_params.append(selected_user_id)

        if selected_product_id:
            sales_query += " AND s.ProductID = %s"
            query_params.append(selected_product_id)

        sales_query += " ORDER BY s.date_updated DESC"
        cursor.execute(sales_query, tuple(query_params))
        sales = cursor.fetchall()

        # Totals
        total_quantity = sum(s['qty'] for s in sales)
        total_sales = sum(s['total_price'] for s in sales)
        total_commission = sum(s['qty'] * 500 for s in sales)

    finally:
        cursor.close()
        connection.close()

    return render_template(
        'sales/sales_view.html',
        user=user,
        sales=sales,
        total_quantity=total_quantity,
        total_sales=f"{total_sales:,.0f}",
        total_commission=f"{total_commission:,.0f}",
        start_date=start_date,
        end_date=end_date,
        all_users=all_users,
        all_products=all_products,
        selected_user_id=selected_user_id,
        selected_product_id=selected_product_id,
        searched=True,
        segment='sales_view'
    )










@blueprint.route('/user_sales_view', methods=['GET', 'POST'])
def user_sales_view():
    if 'id' not in session:
        flash('Login required to access this page.', 'error')
        return redirect(url_for('authentication_blueprint.login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch current user info
        cursor.execute("SELECT * FROM users WHERE id = %s", (session['id'],))
        user = cursor.fetchone()

        # Fetch all products for filter dropdown
        cursor.execute("SELECT ProductID, name FROM product_list")
        all_products = cursor.fetchall()

        today = datetime.today().strftime('%Y-%m-%d')
        start_date = end_date = today
        selected_product_id = None

        if request.method == 'POST':
            start_date = request.form.get('start_date') or today
            end_date = request.form.get('end_date') or today
            selected_product_id = request.form.get('product_id') or None

        # === SALES QUERY ===
        sales_query = """
            SELECT 
                s.salesID,
                p.name AS product_name,
                c.name AS customer_name,
                s.price,
                s.discount,
                s.discounted_price,
                s.qty,
                s.total_price,
                s.date_updated,
                u.username AS sold_by
            FROM sales s
            JOIN product_list p ON s.ProductID = p.ProductID
            JOIN customer_list c ON s.customer_id = c.CustomerID
            LEFT JOIN users u ON s.user_id = u.id
            WHERE s.type = 'sales' 
              AND s.order_status = 'Completed'
              AND s.user_id = %s
              AND DATE(s.date_updated) BETWEEN %s AND %s
        """
        query_params = [session['id'], start_date, end_date]

        if selected_product_id:
            sales_query += " AND s.ProductID = %s"
            query_params.append(selected_product_id)

        sales_query += " ORDER BY s.date_updated DESC"
        cursor.execute(sales_query, tuple(query_params))
        sales = cursor.fetchall()

        # Totals
        total_quantity = sum(s['qty'] for s in sales)
        total_sales = sum(s['total_price'] for s in sales)
        total_commission = sum(s['qty'] * 500 for s in sales)

    finally:
        cursor.close()
        connection.close()

    return render_template(
        'sales/user_sales_view.html',
        user=user,
        sales=sales,
        total_quantity=total_quantity,
        total_sales=f"{total_sales:,.0f}",
        total_commission=f"{total_commission:,.0f}",
        start_date=start_date,
        end_date=end_date,
        all_products=all_products,
        selected_product_id=selected_product_id,
        searched=True,
        segment='user_sales_view'
    )









def get_kampala_time():
    kampala = pytz.timezone("Africa/Kampala")
    return datetime.now(kampala)





@blueprint.route('/mark_order_complete', methods=['POST'])
def mark_order_complete():
    if 'id' not in session or session.get('role') != 'user':
        flash('Unauthorized', 'danger')
        return redirect(url_for('authentication_blueprint.login'))

    sales_id = request.form.get('salesID')
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Step 1: Fetch sales and product data
        cursor.execute("""
            SELECT s.salesID, s.ProductID, s.qty, s.order_status, s.price, s.user_id,
                   p.quantity AS current_stock, p.price AS old_price, p.ProductID AS product_id
            FROM sales s
            JOIN product_list p ON s.ProductID = p.ProductID
            WHERE s.salesID = %s
        """, (sales_id,))
        sale = cursor.fetchone()

        if not sale:
            flash('Sale not found.', 'danger')
            return redirect(url_for('sales_blueprint.orders_view'))

        if sale['order_status'].lower() not in ('processing', 'edited','received_on_credit'):
            flash('Only processing orders can be marked as complete.', 'warning')
            return redirect(url_for('sales_blueprint.orders_view'))

        qty_sold = sale['qty']
        current_stock = sale['current_stock']
        new_stock = current_stock - qty_sold

        #if new_stock < 0:
        #    flash('Insufficient stock to complete order.', 'danger')
        #    return redirect(url_for('sales_blueprint.orders_view'))

        # Step 2: Update order status
        cursor.execute("""
            UPDATE sales SET order_status = 'completed'
            WHERE salesID = %s
        """, (sales_id,))

        # Step 3: Update product quantity
        cursor.execute("""
            UPDATE product_list SET quantity = %s
            WHERE ProductID = %s
        """, (new_stock, sale['ProductID']))

        # Step 4: Insert into inventory_logs (with order_status logged)
        cursor.execute("""
            INSERT INTO inventory_logs (
                product_id, quantity_change, log_date, reason, order_status,
                price_change, user_id, old_price
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            sale['product_id'],
            -qty_sold,
            get_kampala_time(),
            'Order completed',
            'completed',
            sale['price'],
            session['id'],
            sale['old_price']
        ))

        # Step 5: Commit transaction
        connection.commit()
        flash('Order marked as complete and inventory updated.', 'success')

    except Exception as e:
        connection.rollback()
        flash(f'Error completing order: {str(e)}', 'danger')

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('sales_blueprint.orders_view'))




@blueprint.route('/mark_order_credit', methods=['POST'])
def mark_order_credit():
    if 'id' not in session or session.get('role') != 'user':
        flash('Unauthorized', 'danger')
        return redirect(url_for('authentication_blueprint.login'))

    sales_id = request.form.get('salesID')
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Step 1: Fetch sale
        cursor.execute("""
            SELECT s.salesID, s.ProductID, s.qty, s.order_status, s.price, s.user_id,
                   p.quantity AS current_stock, p.price AS old_price
            FROM sales s
            JOIN product_list p ON s.ProductID = p.ProductID
            WHERE s.salesID = %s
        """, (sales_id,))
        sale = cursor.fetchone()

        if not sale:
            flash('Sale not found.', 'danger')
            return redirect(url_for('sales_blueprint.orders_view'))

        if sale['order_status'].lower() != 'credit_sale':
            flash('Only credit sale orders can be marked as received.', 'warning')
            return redirect(url_for('sales_blueprint.orders_view'))

        qty_sold = sale['qty']
        current_stock = sale['current_stock']
        new_stock = current_stock - qty_sold

        # Step 2: Update order status to 'recieved_on_credit'
        cursor.execute("""
            UPDATE sales SET order_status = 'received_on_credit'
            WHERE salesID = %s
        """, (sales_id,))

        # Step 3: Update product quantity
        cursor.execute("""
            UPDATE product_list SET quantity = %s
            WHERE ProductID = %s
        """, (new_stock, sale['ProductID']))

        # Step 4: Log inventory
        cursor.execute("""
            INSERT INTO inventory_logs (
                product_id, quantity_change, log_date, reason, order_status,
                price_change, user_id, old_price
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            sale['ProductID'],
            -qty_sold,
            get_kampala_time(),
            'Received on credit',
            'completed',
            sale['price'],
            session['id'],
            sale['old_price']
        ))

        connection.commit()
        flash('Order received on credit and inventory updated.', 'success')

    except Exception as e:
        connection.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('sales_blueprint.orders_view'))









@blueprint.route('/update_order_status', methods=['POST'])
def update_order_status():
    if 'id' not in session or session.get('role') != 'admin':
        flash('Admin privileges required.', 'danger')
        return redirect(url_for('authentication_blueprint.login'))

    sales_id = request.form.get('salesID')
    new_status = request.form.get('order_status')

    allowed_statuses = ['processing', 'canceled','credit_sale','completed']
    if new_status not in allowed_statuses:
        flash('Invalid status.', 'warning')
        return redirect(url_for('sales_blueprint.orders_view'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch sale details
        cursor.execute("""
            SELECT s.qty, s.ProductID, s.price, s.order_status, s.user_id AS sales_user_id,
                   p.price AS old_price, p.quantity AS current_stock
            FROM sales s
            JOIN product_list p ON s.ProductID = p.ProductID
            WHERE s.salesID = %s
        """, (sales_id,))
        sale = cursor.fetchone()

        if not sale:
            flash('Sale record not found.', 'danger')
            return redirect(url_for('sales_blueprint.orders_view'))

        current_qty = sale['qty']
        product_id = sale['ProductID']
        current_status = sale['order_status']
        current_stock = sale['current_stock']
        inventory_change = 0
        reason = ''

        # === Inventory adjustments based on new status ===
        if new_status == 'canceled' and current_status != 'canceled':
            inventory_change = current_qty
            reason = 'Order canceled - stock returned'

            cursor.execute("""
                UPDATE product_list SET quantity = quantity + %s WHERE ProductID = %s
            """, (current_qty, product_id))

        elif new_status == 'processing' and current_status == 'canceled':
            if current_stock < current_qty:
                flash('Insufficient stock to revert order to processing.', 'danger')
                return redirect(url_for('sales_blueprint.orders_view'))

            inventory_change = -current_qty
            reason = 'Order reverted to processing - stock deducted'

            cursor.execute("""
                UPDATE product_list SET quantity = quantity - %s WHERE ProductID = %s
            """, (current_qty, product_id))
        
        else:
            reason = f'Order status changed from {current_status} to {new_status} - no stock change'

        # === Update order status ===
        cursor.execute("""
            UPDATE sales SET order_status = %s WHERE salesID = %s
        """, (new_status, sales_id))

        # === Log inventory movement ===
        cursor.execute("""
            INSERT INTO inventory_logs (
                product_id, quantity_change, log_date, reason, order_status,
                price_change, user_id, sales_user_id, old_price
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            product_id,
            inventory_change,
            get_kampala_time(),
            reason,
            new_status,
            sale['price'],
            session['id'],             # Logged-in admin
            sale['sales_user_id'],     # Original sales user
            sale['old_price']
        ))

        connection.commit()
        flash('Order status updated and inventory log recorded.', 'success')

    except Exception as e:
        connection.rollback()
        flash(f'Error updating order status: {str(e)}', 'danger')

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('sales_blueprint.orders_view'))



















@blueprint.route('/orders_view', methods=['GET', 'POST'])
def orders_view():
    if 'id' not in session:
        flash('Login required to access this page.', 'error')
        return redirect(url_for('authentication_blueprint.login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch user info
        cursor.execute("SELECT * FROM users WHERE id = %s", (session['id'],))
        user = cursor.fetchone()
        if not user:
            flash('User not found. Please log in again.', 'error')
            return redirect(url_for('authentication_blueprint.login'))

        today = datetime.today().strftime('%Y-%m-%d')
        start_date = request.form.get('start_date', today)
        end_date = request.form.get('end_date', today)
        searched = request.method == 'POST'

        # ---- Pending + Processing Sales Data ----
        cursor.execute("""
            SELECT 
                s.salesID,
                p.name AS product_name,
                c.name AS customer_name,
                s.price,
                s.discount,
                s.discounted_price,
                s.qty,
                s.date_updated,
                s.order_status
            FROM sales s
            JOIN product_list p ON s.ProductID = p.ProductID
            JOIN customer_list c ON s.customer_id = c.CustomerID
            WHERE s.type = 'sales'
              AND s.order_status IN ('pending', 'processing','edited','credit_sale','received_on_credit')
              AND DATE(s.date_updated) BETWEEN %s AND %s
            ORDER BY s.date_updated DESC
        """, (start_date, end_date))
        sales = cursor.fetchall()

        # ---- Totals for Pending + Processing ----
        cursor.execute("""
            SELECT 
                SUM(s.qty) AS total_quantity,
                SUM(s.total_price) AS total_sales
            FROM sales s
            WHERE s.type = 'sales'
              AND s.order_status IN ('pending', 'processing','edited','credit_sale','recieved_on_credit')
              AND DATE(s.date_updated) BETWEEN %s AND %s
        """, (start_date, end_date))
        totals = cursor.fetchone()
        total_sales = totals['total_sales'] or 0
        total_quantity = totals['total_quantity'] or 0

    finally:
        cursor.close()
        connection.close()

    return render_template(
        'sales/orders_view.html',
        user=user,
        sales=sales,
        total_sales=f"{total_sales:,.2f}",
        total_quantity=f"{total_quantity:,}",
        start_date=start_date,
        end_date=end_date,
        searched=searched,
        segment='orders_view'
    )








@blueprint.route('/user_orders_view', methods=['GET', 'POST'])
def user_orders_view():
    if 'id' not in session:
        flash('Login required to access this page.', 'error')
        return redirect(url_for('authentication_blueprint.login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch user info
        cursor.execute("SELECT * FROM users WHERE id = %s", (session['id'],))
        user = cursor.fetchone()
        if not user:
            flash('User not found. Please log in again.', 'error')
            return redirect(url_for('authentication_blueprint.login'))

        today = datetime.today().strftime('%Y-%m-%d')
        start_date = request.form.get('start_date', today)
        end_date = request.form.get('end_date', today)
        searched = request.method == 'POST'

        # ---- Pending + Processing Sales Data (FOR LOGGED-IN USER ONLY) ----
        cursor.execute("""
            SELECT 
                s.salesID,
                p.name AS product_name,
                c.name AS customer_name,
                s.price,
                s.discount,
                s.discounted_price,
                s.qty,
                s.date_updated,
                s.order_status
            FROM sales s
            JOIN product_list p ON s.ProductID = p.ProductID
            JOIN customer_list c ON s.customer_id = c.CustomerID
            WHERE s.type = 'sales'
              AND s.user_id = %s
              AND s.order_status IN ('pending', 'processing', 'edited', 'credit_sale', 'received_on_credit')
              AND DATE(s.date_updated) BETWEEN %s AND %s
            ORDER BY s.date_updated DESC
        """, (session['id'], start_date, end_date))
        sales = cursor.fetchall()

        # ---- Totals (FOR LOGGED-IN USER ONLY) ----
        cursor.execute("""
            SELECT 
                SUM(s.qty) AS total_quantity,
                SUM(s.total_price) AS total_sales
            FROM sales s
            WHERE s.type = 'sales'
              AND s.user_id = %s
              AND s.order_status IN ('pending', 'processing', 'edited', 'credit_sale', 'received_on_credit')
              AND DATE(s.date_updated) BETWEEN %s AND %s
        """, (session['id'], start_date, end_date))
        totals = cursor.fetchone()
        total_sales = totals['total_sales'] or 0
        total_quantity = totals['total_quantity'] or 0

    finally:
        cursor.close()
        connection.close()

    return render_template(
        'sales/user_orders_view.html',
        user=user,
        sales=sales,
        total_sales=f"{total_sales:,.2f}",
        total_quantity=f"{total_quantity:,}",
        start_date=start_date,
        end_date=end_date,
        searched=searched,
        segment='user_orders_view'
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

        product_id = sale['ProductID']
        old_qty = sale['qty']
        old_status = sale['order_status']

        # Fetch available stock for the product
        cursor.execute('SELECT quantity FROM product_list WHERE ProductID = %s', (product_id,))
        product = cursor.fetchone()
        if not product:
            flash("Product not found!", "danger")
            return redirect(url_for('sales_blueprint.sales_view'))

        available_stock = product['quantity']

        # Get customers for dropdown
        cursor.execute('SELECT CustomerID, name FROM customer_list')
        customers = cursor.fetchall()

        if request.method == 'POST':
            # Get submitted form data
            customer_id = request.form.get('customer_id')
            price = float(request.form.get('price'))
            discount = float(request.form.get('discount') or 0)
            new_qty = int(request.form.get('qty'))
            new_status = 'edited'
            date_updated_str = request.form.get('date_updated')

            # Check if order status is valid
            #allowed_statuses = ['pending', 'processing', 'completed', 'canceled']
            #if new_status not in allowed_statuses:
            #    flash("Invalid order status.", "danger")
            #    return redirect(request.url)

            # Compute quantity difference
            qty_difference = new_qty - old_qty  # Positive = needs more stock

            if qty_difference > 0 and qty_difference > available_stock:
                flash(f"Not enough stock. Available: {available_stock}, Needed: {qty_difference}.", "danger")
                return redirect(request.url)

            # Parse and format the datetime string
            try:
                local_dt = datetime.strptime(date_updated_str, '%Y-%m-%dT%H:%M')
                kampala_tz = pytz.timezone("Africa/Kampala")
                localized_dt = kampala_tz.localize(local_dt)
                date_updated_formatted = localized_dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                flash("Invalid date format.", "danger")
                return redirect(request.url)

            # Perform update
            cursor.execute("""
                UPDATE sales 
                SET customer_id = %s,
                    price = %s,
                    discount = %s,
                    qty = %s,
                    date_updated = %s,
                    order_status = %s
                WHERE salesID = %s
            """, (
                customer_id,
                price,
                discount,
                new_qty,
                date_updated_formatted,
                new_status,
                salesID
            ))

            connection.commit()
            flash("Sale updated successfully!", "success")
            return redirect(url_for('sales_blueprint.sales_view'))

        # GET: Show edit form
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
