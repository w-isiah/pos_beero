import os
import random
import logging
from flask import render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from mysql.connector import Error
from apps import get_db_connection
from apps.expenses import blueprint
import mysql.connector


# Adjust if your DB connection function is named differently





from datetime import datetime
import pytz

# Function to get current time in Kampala timezone
def get_kampala_time():
    kampala = pytz.timezone("Africa/Kampala")
    return datetime.now(kampala)

@blueprint.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Fetch customers for dropdown list
    cursor.execute('SELECT CustomerID, name FROM customer_list ORDER BY name')
    customers = cursor.fetchall()

    if request.method == 'POST':
        # Get form data
        expense_name = request.form.get('expense_name', '').strip()
        price = request.form.get('price', '').strip()
        customer_id = request.form.get('customer_id')
        description = request.form.get('description', '').strip()

        # Basic validation
        if not expense_name or not price or not customer_id:
            flash("Please fill in all required fields", "danger")
            return redirect(request.url)

        try:
            price = float(price)
            if price <= 0:
                raise ValueError("Price must be positive")
        except ValueError:
            flash("Price must be a valid positive number.", "danger")
            return redirect(request.url)

        # Auto-generated and static fields
        product_id = f'EXP-{int(price * 100)}'  # Example logic to generate unique product ID
        expense_type = 'expense'
        qty = 1
        discount = 0.0
        discounted_price = price
        total_price = price

        # Get the current time in Kampala timezone
        date_added = get_kampala_time()

        # Insert into sales table, including the expense_name and date_added
        try:
            cursor.execute('''
                INSERT INTO sales 
                    (ProductID, customer_id, type, price, discount, qty, discounted_price, total_price, description, expense_name, date_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                product_id, customer_id, expense_type, price,
                discount, qty, discounted_price, total_price,
                description, expense_name, date_added  # Adding date_added here
            ))

            connection.commit()
            flash("Expense saved successfully!", "success")
            return redirect(url_for('expenses_blueprint.add_expense'))

        except Exception as e:
            connection.rollback()
            flash(f"Error saving expense: {e}", "danger")

    cursor.close()
    connection.close()

    return render_template('expenses/add_expense.html', customers=customers)

















from datetime import datetime
import pytz

# Function to get current time in Kampala timezone
def get_kampala_time(as_string: bool = False, fmt: str = "%Y-%m-%d %H:%M:%S") -> datetime | str:
    kampala_tz = pytz.timezone("Africa/Kampala")
    kampala_time = datetime.now(kampala_tz)
    return kampala_time.strftime(fmt) if as_string else kampala_time

@blueprint.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Fetch the expense record
        cursor.execute('SELECT * FROM sales WHERE salesID = %s', (expense_id,))
        expense = cursor.fetchone()

        if not expense:
            flash("Expense not found!", "warning")
            return redirect(url_for('expenses_blueprint.list_expenses'))

        # Get customer list
        cursor.execute('SELECT CustomerID, name FROM customer_list')
        customers = cursor.fetchall()

        if request.method == 'POST':
            # Get form data
            customer_id = request.form.get('customer_id')
            expense_name = request.form.get('expense_name')
            description = request.form.get('description')
            amount = request.form.get('amount')

            # Automatically set current Kampala time
            date_updated = get_kampala_time(as_string=True)

            # Update the expense
            update_query = '''
                UPDATE sales 
                SET Customer_id = %s,
                    expense_name = %s,
                    description = %s,
                    price = %s,
                    date_updated = %s
                WHERE salesID = %s
            '''
            cursor.execute(update_query, (
                customer_id,
                expense_name,
                description,
                amount,
                date_updated,
                expense_id
            ))

            connection.commit()
            flash("Expense updated successfully!", "success")
            return redirect(url_for('sales_blueprint.sales_view'))

        return render_template('expenses/edit_expenses.html', expense=expense, customers=customers)

    finally:
        cursor.close()
        connection.close()











@blueprint.route('/delete_expense/<string:get_id>')
def delete_expense(get_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute('DELETE FROM sales WHERE salesID = %s', (get_id,))
    connection.commit()
    cursor.close()
    connection.close()
    return redirect(url_for('sales_blueprint.sales_view'))

    


@blueprint.route('/<template>')
def route_template(template):
    try:
        # Ensure the template ends with '.html' for correct render
        if not template.endswith('.html'):
            template += '.html'

        segment = get_segment(request)

        return render_template("expenses/" + template, segment=segment)

    except TemplateNotFound:
        return render_template('expenses/page-404.html'), 404

    except Exception as e:
        return render_template('expenses/page-500.html'), 500


def get_segment(request):
    """Extracts the last part of the URL path to identify the current page."""
    try:
        segment = request.path.split('/')[-1]
        if segment == '':
            segment = 'expenses'
        return segment

    except Exception as e:
        return None
