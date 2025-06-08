from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import sqlite3
import os
import json
from datetime import datetime, timedelta
import uuid
import xlsxwriter
import io
from werkzeug.utils import secure_filename
import time

app = Flask(__name__)
app.secret_key = 'sales_management_key'

# 会话配置
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['SESSION_TYPE'] = 'filesystem'

@app.before_request
def ensure_username():
    if 'username' not in session:
        # 设置默认用户名和其他必要会话信息
        session['username'] = '管理员'

def init_db():
    """初始化数据库，只在数据库不存在时创建新的数据库"""
    db_path = 'data/sales.db'
    
    # 如果数据库已存在，直接返回
    if os.path.exists(db_path):
        return
    
    # 确保数据目录存在
    os.makedirs('data', exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建菜单项表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS menu_items (
        item_code TEXT PRIMARY KEY,
        item_name TEXT NOT NULL,
        category TEXT NOT NULL,
        is_heritage INTEGER DEFAULT 0,
        price REAL NOT NULL,
        cost REAL NOT NULL,
        sales_count INTEGER DEFAULT 0,
        description TEXT,
        image_path TEXT,
        status TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 创建订单表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        order_number TEXT PRIMARY KEY,
        order_type TEXT NOT NULL,
        order_status TEXT NOT NULL,
        table_number TEXT,
        customer_name TEXT,
        customer_phone TEXT,
        total_amount REAL NOT NULL,
        discount_amount REAL DEFAULT 0,
        final_amount REAL NOT NULL,
        payment_method TEXT,
        notes TEXT,
        assigned_chef TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 创建订单明细表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT NOT NULL,
        item_code TEXT NOT NULL,
        item_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        total_price REAL NOT NULL,
        notes TEXT,
        FOREIGN KEY (order_number) REFERENCES orders (order_number),
        FOREIGN KEY (item_code) REFERENCES menu_items (item_code)
    )
    ''')
    
    # 创建会员表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS members (
        member_id TEXT PRIMARY KEY,
        member_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT,
        points INTEGER DEFAULT 0,
        level TEXT DEFAULT '普通会员',
        total_consumption REAL DEFAULT 0,
        registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_visit_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT '活跃'
    )
    ''')
    
    # 创建餐桌表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tables (
        table_id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_number TEXT NOT NULL UNIQUE,
        capacity INTEGER NOT NULL,
        location TEXT,
        status TEXT DEFAULT '空闲',
        current_order TEXT,
        last_order_time TIMESTAMP
    )
    ''')

    # 创建小票表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_number TEXT UNIQUE NOT NULL,
        order_number TEXT NOT NULL,
        order_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        dining_mode TEXT,
        total_amount REAL NOT NULL,
        customer_name TEXT,
        customer_phone TEXT,
        member_info TEXT,
        is_printed INTEGER DEFAULT 0,
        receipt_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (order_number) REFERENCES orders (order_number)
    )
    ''')

    # 创建小票明细表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS receipt_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_id INTEGER NOT NULL,
        item_code TEXT NOT NULL,
        item_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        total_price REAL NOT NULL,
        notes TEXT,
        FOREIGN KEY (receipt_id) REFERENCES receipts (id),
        FOREIGN KEY (item_code) REFERENCES menu_items (item_code)
    )
    ''')
    
    conn.commit()
    conn.close()
    print("数据库初始化完成：创建了新的数据库文件")

def get_db_connection():
    conn = sqlite3.connect('data/sales.db')
    conn.row_factory = sqlite3.Row
    return conn

# 主页
@app.route('/')
def home():
    return render_template('sales/index.html', username=session['username'])

@app.route('/logout')
def logout():
    session.clear()
    flash('您已退出登录', 'success')
    return redirect(url_for('home'))

# 销售管理主页
@app.route('/sales')
def sales():
    return render_template('sales/index.html', username=session['username'])

# 菜单管理
@app.route('/sales/menu')
def menu():
    # 获取筛选参数
    category = request.args.get('category', '')
    status = request.args.get('status', '')
    is_heritage = request.args.get('is_heritage', '')
    search = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'item_code')
    sort_order = request.args.get('sort_order', 'asc')
    
    # 连接数据库
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 构建查询条件
    query = "SELECT * FROM menu_items WHERE 1=1"
    params = []
    
    if category:
        query += " AND category = ?"
        params.append(category)
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    if is_heritage:
        query += " AND is_heritage = ?"
        params.append(1 if is_heritage == '1' else 0)
    
    if search:
        query += " AND (item_name LIKE ? OR item_code LIKE ? OR description LIKE ?)"
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term])
    
    # 添加排序
    valid_sort_fields = {
        'item_code': 'item_code',
        'item_name': 'item_name',
        'price': 'price',
        'sales_count': 'sales_count',
        'created_at': 'created_at'
    }
    
    if sort_by not in valid_sort_fields:
        sort_by = 'item_code'
    
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'
    
    query += f" ORDER BY {valid_sort_fields[sort_by]} {sort_order.upper()}"
    
    # 执行查询
    cursor.execute(query, params)
    menu_items = cursor.fetchall()
    
    # 获取所有菜品分类
    cursor.execute("SELECT DISTINCT category FROM menu_items ORDER BY category")
    categories = [row['category'] for row in cursor.fetchall()]
    
    # 获取销量最高的菜品
    cursor.execute("""
        SELECT item_code, item_name, sales_count, category 
        FROM menu_items 
        ORDER BY sales_count DESC 
        LIMIT 5
    """)
    top_dishes = cursor.fetchall()
    
    # 获取菜品总数和传承菜数量
    cursor.execute("SELECT COUNT(*) as total FROM menu_items")
    total_items = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as heritage_count FROM menu_items WHERE is_heritage = 1")
    heritage_count = cursor.fetchone()['heritage_count']
    
    # 获取各分类的菜品数量
    cursor.execute("""
        SELECT category, COUNT(*) as count,
               SUM(CASE WHEN status = '上架' THEN 1 ELSE 0 END) as active_count
        FROM menu_items
        GROUP BY category
        ORDER BY count DESC
    """)
    category_stats = cursor.fetchall()
    
    conn.close()
    
    return render_template('sales/menu.html',
                          username=session['username'],
                          menu_items=menu_items,
                          categories=categories,
                          top_dishes=top_dishes,
                          total_items=total_items,
                          heritage_count=heritage_count,
                          category_stats=category_stats,
                          current_category=category,
                          current_status=status,
                          current_heritage=is_heritage,
                          current_sort_by=sort_by,
                          current_sort_order=sort_order,
                          search=search)

# 新增菜品
@app.route('/sales/menu/add', methods=['GET', 'POST'])
def add_menu_item():
    if request.method == 'POST':
        # 获取表单数据
        item_name = request.form['item_name']
        category = request.form['category']
        is_heritage = 1 if 'is_heritage' in request.form else 0
        price = request.form['price']
        cost = request.form['cost']
        description = request.form['description']
        status = request.form['status']
        
        # 处理图片上传
        image_path = ''
        if 'image' in request.files:
            image = request.files['image']
            if image and image.filename:
                # 获取文件扩展名
                _, ext = os.path.splitext(image.filename)
                # 生成唯一的文件名：时间戳_随机数.扩展名
                unique_filename = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
                # 确保目录存在
                if not os.path.exists('static/uploads/menu'):
                    os.makedirs('static/uploads/menu')
                image_path = f'uploads/menu/{unique_filename}'
                image.save(os.path.join('static', image_path))
        
        # 连接数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # 生成菜品编号：ID+年份+序号(001-999)
            current_year = datetime.now().year
            
            # 获取当前年份最大序号
            cursor.execute("""
                SELECT MAX(SUBSTR(item_code, 7)) as max_seq 
                FROM menu_items 
                WHERE item_code LIKE ?
            """, (f'ID{current_year}%',))
            
            result = cursor.fetchone()
            max_seq = result['max_seq'] if result['max_seq'] else '000'
            
            # 尝试转换为数字，如果不是数字则默认为0
            try:
                next_seq = int(max_seq) + 1
            except (ValueError, TypeError):
                next_seq = 1
                
            # 格式化编号
            item_code = f'ID{current_year}{next_seq:03d}'
            
            # 插入数据
            cursor.execute('''
                INSERT INTO menu_items (
                    item_code, item_name, category, is_heritage, price, cost, 
                    description, image_path, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item_code, item_name, category, is_heritage, price, cost,
                description, image_path, status
            ))
            
            conn.commit()
            flash(f'菜品添加成功! 编号: {item_code}', 'success')
            return redirect(url_for('menu'))
            
        except Exception as e:
            flash(f'添加失败: {str(e)}', 'danger')
        finally:
            conn.close()
    
    # GET请求，显示添加表单
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取所有现有菜品分类
    cursor.execute("SELECT DISTINCT category FROM menu_items ORDER BY category")
    categories = [row['category'] for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('sales/add_menu_item.html',
                          username=session['username'],
                          categories=categories)

@app.route('/sales/menu/view/<item_code>')
def view_menu_item(item_code):
    # 连接数据库
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取菜品信息
    cursor.execute("SELECT * FROM menu_items WHERE item_code = ?", (item_code,))
    item = cursor.fetchone()
    
    if not item:
        flash('菜品不存在', 'danger')
        return redirect(url_for('menu'))
    
    conn.close()
    
    return render_template('sales/view_menu_item.html',
                          username=session['username'],
                          item=item)

# 编辑菜品
@app.route('/sales/menu/edit/<item_code>', methods=['GET', 'POST'])
def edit_menu_item(item_code):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        # 获取表单数据
        item_name = request.form['item_name']
        category = request.form['category']
        is_heritage = 1 if 'is_heritage' in request.form else 0
        price = request.form['price']
        cost = request.form['cost']
        description = request.form['description']
        status = request.form['status']
        
        try:
            # 更新菜品信息
            cursor.execute('''
                UPDATE menu_items 
                SET item_name = ?, 
                    category = ?, 
                    is_heritage = ?,
                    price = ?,
                    cost = ?,
                    description = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_code = ?
            ''', (item_name, category, is_heritage, price, cost, description, status, item_code))
            
            conn.commit()
            flash('菜品信息已更新', 'success')
            return redirect(url_for('menu'))
            
        except sqlite3.Error as e:
            flash(f'更新失败：{str(e)}', 'error')
            conn.rollback()
    
    # GET请求：获取菜品信息
    cursor.execute('SELECT * FROM menu_items WHERE item_code = ?', (item_code,))
    item = cursor.fetchone()
    
    if item is None:
        flash('菜品不存在', 'error')
        return redirect(url_for('menu'))
    
    # 获取所有分类供选择
    cursor.execute('SELECT DISTINCT category FROM menu_items ORDER BY category')
    categories = [row['category'] for row in cursor.fetchall()]
    
    conn.close()
    return render_template('sales/edit_menu_item.html',
                         username=session['username'],
                         item=item,
                         categories=categories)

# 删除菜品
@app.route('/sales/menu/delete/<item_code>', methods=['POST'])
def delete_menu_item(item_code):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 检查菜品是否存在
        cursor.execute('SELECT * FROM menu_items WHERE item_code = ?', (item_code,))
        item = cursor.fetchone()
        
        if item is None:
            flash('菜品不存在', 'error')
            return redirect(url_for('menu'))
        
        # 检查是否有关联的订单
        cursor.execute('SELECT COUNT(*) as count FROM order_items WHERE item_code = ?', (item_code,))
        order_count = cursor.fetchone()['count']
        
        if order_count > 0:
            flash('该菜品已有关联订单，无法删除', 'error')
            return redirect(url_for('view_menu_item', item_code=item_code))
        
        # 删除菜品图片（如果有）
        if item['image_path']:
            image_path = os.path.join('static', item['image_path'])
            if os.path.exists(image_path):
                os.remove(image_path)
        
        # 删除菜品记录
        cursor.execute('DELETE FROM menu_items WHERE item_code = ?', (item_code,))
        conn.commit()
        
        flash('菜品已成功删除', 'success')
        return redirect(url_for('menu'))
        
    except sqlite3.Error as e:
        conn.rollback()
        flash(f'删除失败：{str(e)}', 'error')
        return redirect(url_for('view_menu_item', item_code=item_code))
    finally:
        conn.close()

# 订单管理路由
@app.route('/sales/orders')
def orders():
    # 获取筛选参数
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 查询所有订单
    cursor.execute('''
        SELECT * FROM orders
        ORDER BY created_at DESC
    ''')
    orders = cursor.fetchall()
    
    # 获取统计数据（排除已取消订单）
    cursor.execute("""
        SELECT COUNT(*) as total 
        FROM orders 
        WHERE order_status != '已取消'
    """)
    total_orders = cursor.fetchone()['total']
    
    # 获取今日订单数（排除已取消订单）
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT COUNT(*) as today 
        FROM orders 
        WHERE DATE(created_at) = ? 
        AND order_status != '已取消'
    """, (today,))
    today_orders = cursor.fetchone()['today']
    
    # 获取总销售额（排除已取消订单）
    cursor.execute("""
        SELECT SUM(final_amount) as total 
        FROM orders 
        WHERE order_status != '已取消'
    """)
    result = cursor.fetchone()
    total_sales = result['total'] if result['total'] else 0
    
    # 获取今日销售额（排除已取消订单）
    cursor.execute("""
        SELECT SUM(final_amount) as today 
        FROM orders 
        WHERE DATE(created_at) = ? 
        AND order_status != '已取消'
    """, (today,))
    result = cursor.fetchone()
    today_sales = result['today'] if result['today'] else 0
    
    conn.close()
    
    return render_template('sales/orders.html',
                          username=session['username'],
                          orders=orders,
                          total_orders=total_orders,
                          today_orders=today_orders,
                          total_sales=total_sales,
                          today_sales=today_sales)

# POS系统路由
@app.route('/sales/pos')
def pos():
    return render_template('sales/pos.html', username=session['username'])

# 会员管理路由
@app.route('/sales/members')
def members():
    return render_template('sales/members.html', username=session['username'])

# 餐桌管理路由
@app.route('/sales/tables')
def tables():
    return render_template('sales/tables.html', username=session['username'])

# 销售分析路由
@app.route('/sales/analysis')
def sales_analysis():
    try:
        # 获取今日销售数据
        today = datetime.now().strftime('%Y-%m-%d')
        cur = get_db_connection().cursor()
        
        # 今日销售额和订单数
        cur.execute("""
            SELECT COALESCE(SUM(final_amount), 0) as total_amount,
                   COUNT(*) as order_count
            FROM orders 
            WHERE DATE(created_at) = ? AND order_status != '已取消'
        """, (today,))
        daily_stats = cur.fetchone()
        today_sales = daily_stats['total_amount']
        today_orders = daily_stats['order_count']

        # 今日热门菜品（基于订单项统计）
        cur.execute("""
            SELECT 
                mi.item_name,
                SUM(oi.quantity) as total_quantity,
                COUNT(DISTINCT o.order_number) as order_count,
                SUM(oi.total_price) as total_amount
            FROM order_items oi
            JOIN menu_items mi ON oi.item_code = mi.item_code
            JOIN orders o ON oi.order_number = o.order_number
            WHERE DATE(o.created_at) = ?
            AND o.order_status != '已取消'
            GROUP BY mi.item_code, mi.item_name
            ORDER BY order_count DESC, total_quantity DESC
            LIMIT 5
        """, (today,))
        hot_dishes = [dict(row) for row in cur.fetchall()]

        # 月度菜品销售占比
        cur.execute("""
            WITH monthly_sales AS (
                SELECT 
                    mi.item_name,
                    SUM(oi.quantity) as quantity,
                    SUM(oi.total_price) as amount
                FROM order_items oi
                JOIN menu_items mi ON oi.item_code = mi.item_code
                JOIN orders o ON oi.order_number = o.order_number
                WHERE strftime('%Y-%m', o.created_at) = strftime('%Y-%m', 'now')
                AND o.order_status != '已取消'
                GROUP BY mi.item_code, mi.item_name
            )
            SELECT 
                item_name,
                quantity,
                amount,
                ROUND(quantity * 100.0 / (SELECT SUM(quantity) FROM monthly_sales), 2) as percentage
            FROM monthly_sales
            ORDER BY quantity DESC
            LIMIT 10
        """)
        monthly_dish_stats = [dict(row) for row in cur.fetchall()]

        # 最近12个月的销售数据
        cur.execute("""
            WITH RECURSIVE dates(date) AS (
                SELECT date('now', 'start of month', '-11 months')
                UNION ALL
                SELECT date(date, '+1 month')
                FROM dates
                WHERE date < date('now', 'start of month')
            )
            SELECT 
                strftime('%Y-%m', dates.date) as month,
                COALESCE(COUNT(DISTINCT o.order_number), 0) as order_count,
                COALESCE(SUM(CASE WHEN o.order_type = '堂食' THEN 1 ELSE 0 END), 0) as dine_in_count,
                COALESCE(SUM(CASE WHEN o.order_type = '外卖' THEN 1 ELSE 0 END), 0) as takeout_count,
                COALESCE(SUM(o.final_amount), 0) as total_amount,
                COALESCE(SUM(CASE WHEN o.order_type = '堂食' THEN o.final_amount ELSE 0 END), 0) as dine_in_amount,
                COALESCE(SUM(CASE WHEN o.order_type = '外卖' THEN o.final_amount ELSE 0 END), 0) as takeout_amount
            FROM dates
            LEFT JOIN orders o ON strftime('%Y-%m', o.created_at) = strftime('%Y-%m', dates.date)
                AND o.order_status != '已取消'
            GROUP BY strftime('%Y-%m', dates.date)
            ORDER BY month DESC
        """)
        monthly_stats = [dict(row) for row in cur.fetchall()]

        # 当月菜品销售明细
        cur.execute("""
            SELECT 
                mi.item_name,
                SUM(oi.quantity) as quantity,
                SUM(oi.total_price) as total_amount,
                COUNT(DISTINCT o.order_number) as order_count,
                ROUND(CAST(SUM(oi.quantity) AS FLOAT) / COUNT(DISTINCT o.order_number), 2) as avg_quantity_per_order
            FROM order_items oi
            JOIN menu_items mi ON oi.item_code = mi.item_code
            JOIN orders o ON oi.order_number = o.order_number
            WHERE strftime('%Y-%m', o.created_at) = strftime('%Y-%m', 'now')
            AND o.order_status != '已取消'
            GROUP BY mi.item_code, mi.item_name
            ORDER BY quantity DESC
        """)
        dish_details = [dict(row) for row in cur.fetchall()]

        current_month = datetime.now().strftime('%Y年%m月')

        return render_template('sales/analysis.html',
                            today_sales=today_sales,
                            today_orders=today_orders,
                            hot_dishes=hot_dishes,
                            monthly_dish_stats=monthly_dish_stats,
                            monthly_stats=monthly_stats,
                            dish_details=dish_details,
                            current_month=current_month)

    except Exception as e:
        print(f"销售分析错误：{str(e)}")  # 添加错误日志
        flash(f'获取销售分析数据失败：{str(e)}', 'error')
        return redirect(url_for('sales'))

@app.route('/sales/update_order_status/<order_number>', methods=['POST'])
def update_order_status(order_number):
    status = request.form['status']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE orders
            SET order_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE order_number = ?
        ''', (status, order_number))
        
        conn.commit()
        flash(f'订单 {order_number} 状态更新为 {status}', 'success')
    except Exception as e:
        flash(f'更新失败: {str(e)}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('orders'))

@app.route('/sales/batch_orders', methods=['POST'])
def batch_orders():
    action = request.form.get('action')
    order_numbers = request.form.get('order_numbers', '').split(',')
    
    if not order_numbers or not action:
        return jsonify({'status': 'error', 'message': '无效的请求参数'})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 状态映射
        status_map = {
            'accept': '已接单',
            'make': '制作中',
            'complete': '已完成',
            'cancel': '已取消'
        }
        
        if action in status_map:
            # 更新订单状态
            new_status = status_map[action]
            success_count = 0
            
            for order_number in order_numbers:
                cursor.execute('''
                    UPDATE orders 
                    SET order_status = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE order_number = ?
                ''', (new_status, order_number))
                success_count += cursor.rowcount
            
            conn.commit()
            return jsonify({
                'status': 'success',
                'message': f'成功更新 {success_count} 个订单状态为{new_status}'
            })
            
        elif action == 'delete':
            success_count = 0
            for order_number in order_numbers:
                # 删除订单项
                cursor.execute('DELETE FROM order_items WHERE order_number = ?', (order_number,))
                # 删除订单
                cursor.execute('DELETE FROM orders WHERE order_number = ?', (order_number,))
                success_count += 1
            
            conn.commit()
            return jsonify({
                'status': 'success',
                'message': f'成功删除 {success_count} 个订单'
            })
        
        else:
            return jsonify({
                'status': 'error',
                'message': '不支持的操作类型'
            })
    
    except Exception as e:
        conn.rollback()
        return jsonify({
            'status': 'error',
            'message': f'操作失败: {str(e)}'
        })
    finally:
        conn.close()

@app.route('/sales/export_orders')
def export_orders():
    # 获取要导出的订单号列表
    order_numbers = request.args.get('orders', '').split(',')
    if not order_numbers or not order_numbers[0]:
        flash('请选择要导出的订单', 'warning')
        return redirect(url_for('orders'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 创建Excel文件
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        
        # 添加格式
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#F4F4F4'
        })
        
        date_format = workbook.add_format({
            'num_format': 'yyyy-mm-dd hh:mm:ss'
        })
        
        # 创建订单汇总工作表
        summary = workbook.add_worksheet('订单汇总')
        summary.set_column('A:A', 15)  # 订单编号
        summary.set_column('B:B', 10)  # 订单类型
        summary.set_column('C:C', 10)  # 订单状态
        summary.set_column('D:D', 15)  # 顾客姓名
        summary.set_column('E:E', 15)  # 联系电话
        summary.set_column('F:F', 10)  # 金额
        summary.set_column('G:G', 20)  # 下单时间
        
        # 写入汇总表头
        headers = ['订单编号', '订单类型', '订单状态', '顾客姓名', '联系电话', '金额', '下单时间']
        for col, header in enumerate(headers):
            summary.write(0, col, header, header_format)
        
        # 获取并写入订单数据
        placeholders = ','.join('?' * len(order_numbers))
        cursor.execute(f'''
            SELECT * FROM orders 
            WHERE order_number IN ({placeholders})
            ORDER BY created_at DESC
        ''', order_numbers)
        
        orders = cursor.fetchall()
        row = 1
        total_amount = 0
        
        for order in orders:
            summary.write(row, 0, order['order_number'])
            summary.write(row, 1, order['order_type'])
            summary.write(row, 2, order['order_status'])
            summary.write(row, 3, order['customer_name'] or '-')
            summary.write(row, 4, order['customer_phone'] or '-')
            summary.write(row, 5, order['final_amount'])
            summary.write(row, 6, order['created_at'], date_format)
            
            total_amount += order['final_amount']
            
            # 为每个订单创建详细工作表
            detail = workbook.add_worksheet(f'订单_{order["order_number"]}')
            detail.set_column('A:A', 15)  # 商品编号
            detail.set_column('B:B', 20)  # 商品名称
            detail.set_column('C:C', 10)  # 数量
            detail.set_column('D:D', 10)  # 单价
            detail.set_column('E:E', 10)  # 金额
            
            # 写入订单基本信息
            detail.merge_range('A1:E1', f'订单详情 - {order["order_number"]}', header_format)
            detail.write('A2', '订单编号:')
            detail.write('B2', order['order_number'])
            detail.write('A3', '订单类型:')
            detail.write('B3', order['order_type'])
            detail.write('A4', '下单时间:')
            detail.write('B4', order['created_at'], date_format)
            
            # 获取并写入订单项
            cursor.execute('''
                SELECT * FROM order_items 
                WHERE order_number = ?
            ''', (order['order_number'],))
            items = cursor.fetchall()
            
            # 写入商品明细表头
            item_headers = ['商品编号', '商品名称', '数量', '单价', '金额']
            for col, header in enumerate(item_headers):
                detail.write(5, col, header, header_format)
            
            # 写入商品明细
            detail_row = 6
            for item in items:
                detail.write(detail_row, 0, item['item_code'])
                detail.write(detail_row, 1, item['item_name'])
                detail.write(detail_row, 2, item['quantity'])
                detail.write(detail_row, 3, item['unit_price'])
                detail.write(detail_row, 4, item['total_price'])
                detail_row += 1
            
            row += 1
        
        # 写入汇总信息
        summary.write(row + 1, 4, '总计:', header_format)
        summary.write(row + 1, 5, total_amount, header_format)
        summary.write(row + 3, 0, f'导出时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        
        workbook.close()
        output.seek(0)
        
        # 生成下载文件名
        filename = f'订单导出_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        flash(f'导出失败：{str(e)}', 'error')
        return redirect(url_for('orders'))
    finally:
        conn.close()

# 新增订单
@app.route('/sales/orders/new', methods=['GET', 'POST'])
def new_order():
    if request.method == 'POST':
        # 获取表单数据
        order_type = request.form['order_type']
        table_number = request.form.get('table_number', '')
        customer_name = request.form.get('customer_name', '')
        customer_phone = request.form.get('customer_phone', '')
        notes = request.form.get('notes', '')
        
        # 获取菜品数据
        item_codes = request.form.getlist('item_code[]')
        quantities = request.form.getlist('quantity[]')
        item_notes = request.form.getlist('item_note[]')
        
        # 验证至少有一个菜品
        if not item_codes or len(item_codes) == 0:
            flash('订单必须包含至少一个菜品', 'danger')
            return redirect(url_for('new_order'))
        
        # 连接数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # 生成订单编号：DD + 年月日 + 4位序号（每天从0001开始）
            today = datetime.now().strftime('%Y%m%d')
            cursor.execute("""
                SELECT MAX(SUBSTR(order_number, -4)) as max_seq 
                FROM orders 
                WHERE order_number LIKE ?
            """, (f'DD{today}%',))
            
            result = cursor.fetchone()
            max_seq = result['max_seq'] if result['max_seq'] else '0000'
            
            try:
                next_seq = int(max_seq) + 1
            except (ValueError, TypeError):
                next_seq = 1
                
            # 格式化订单编号：DD + 年月日 + 4位序号
            order_number = f'DD{today}{next_seq:04d}'
            
            # 计算订单总金额
            total_amount = 0
            order_items = []
            
            # 确保所有列表长度一致
            num_items = len(item_codes)
            quantities = quantities[:num_items]
            item_notes = (item_notes + [''] * num_items)[:num_items]
            
            for i in range(num_items):
                if item_codes[i] and quantities[i]:
                    # 获取菜品信息
                    cursor.execute("SELECT * FROM menu_items WHERE item_code = ?", (item_codes[i],))
                    item = cursor.fetchone()
                    
                    if item:
                        quantity = int(quantities[i])
                        unit_price = float(item['price'])
                        total_price = quantity * unit_price
                        total_amount += total_price
                        
                        order_items.append({
                            'item_code': item_codes[i],
                            'item_name': item['item_name'],
                            'quantity': quantity,
                            'unit_price': unit_price,
                            'total_price': total_price,
                            'notes': item_notes[i]
                        })
            
            # 应用折扣（如果有）
            discount_amount = 0
            final_amount = total_amount - discount_amount
            
            # 插入订单
            cursor.execute('''
                INSERT INTO orders (
                    order_number, order_type, order_status, table_number,
                    customer_name, customer_phone, total_amount, discount_amount,
                    final_amount, notes, assigned_chef
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_number, order_type, '已接单', table_number,
                customer_name, customer_phone, total_amount, discount_amount,
                final_amount, notes, '系统分配'
            ))
            
            # 插入订单明细
            for item in order_items:
                cursor.execute('''
                    INSERT INTO order_items (
                        order_number, item_code, item_name, quantity,
                        unit_price, total_price, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    order_number, item['item_code'], item['item_name'], item['quantity'],
                    item['unit_price'], item['total_price'], item['notes']
                ))
                
                # 更新菜品销量
                cursor.execute('''
                    UPDATE menu_items
                    SET sales_count = sales_count + ?
                    WHERE item_code = ?
                ''', (item['quantity'], item['item_code']))
            
            # 创建小票
            receipt_number = f'FP{order_number[2:]}'
            cursor.execute('''
                INSERT INTO receipts (
                    receipt_number, order_number, order_time, dining_mode,
                    total_amount, customer_name, customer_phone, member_info,
                    is_printed, receipt_date
                ) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
            ''', (
                receipt_number,
                order_number,
                order_type,
                final_amount,
                customer_name,
                customer_phone,
                None  # 会员信息（暂无）
            ))
            
            # 获取新创建的小票ID
            cursor.execute("SELECT last_insert_rowid() as receipt_id")
            receipt_id = cursor.fetchone()['receipt_id']
            
            # 创建小票明细
            for item in order_items:
                cursor.execute('''
                    INSERT INTO receipt_items (
                        receipt_id, item_code, item_name, quantity,
                        unit_price, total_price, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    receipt_id,
                    item['item_code'],
                    item['item_name'],
                    item['quantity'],
                    item['unit_price'],
                    item['total_price'],
                    item['notes']
                ))
            
            conn.commit()
            flash(f'订单创建成功! 订单号: {order_number}', 'success')
            
            return redirect(url_for('view_order', order_number=order_number))
            
        except Exception as e:
            conn.rollback()
            flash(f'创建订单失败: {str(e)}', 'danger')
        finally:
            conn.close()
    
    # GET 请求，显示订单创建表单
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取菜单 - 修改查询条件，显示所有可用菜品
    cursor.execute("""
        SELECT * FROM menu_items 
        WHERE status IN ('上架', '在售') 
        ORDER BY category, item_name
    """)
    menu_items = cursor.fetchall()
    
    # 获取菜品分类
    cursor.execute("SELECT DISTINCT category FROM menu_items ORDER BY category")
    categories = [row['category'] for row in cursor.fetchall()]
    
    # 生成桌号选项
    table_prefixes = ['天', '地', '玄', '黄']  # 桌号前缀
    table_numbers = []
    for prefix in table_prefixes:
        for num in range(1, 100):  # 01-99
            table_numbers.append(f"{prefix}{num:02d}")  # 使用:02d格式化数字为两位
    
    conn.close()
    
    return render_template('sales/new_order.html',
                          username=session['username'],
                          menu_items=menu_items,
                          categories=categories,
                          table_numbers=table_numbers)

# 查看订单详情
@app.route('/sales/orders/view/<order_number>')
def view_order(order_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取订单基本信息
    cursor.execute('''
        SELECT * FROM orders 
        WHERE order_number = ?
    ''', (order_number,))
    order = cursor.fetchone()
    
    if not order:
        flash('订单不存在', 'error')
        return redirect(url_for('orders'))
    
    # 获取订单明细
    cursor.execute('''
        SELECT oi.*, mi.image_path 
        FROM order_items oi 
        LEFT JOIN menu_items mi ON oi.item_code = mi.item_code 
        WHERE oi.order_number = ?
    ''', (order_number,))
    order_items = cursor.fetchall()
    
    # 获取订单的小票信息
    cursor.execute('''
        SELECT * FROM receipts 
        WHERE order_number = ?
    ''', (order_number,))
    receipt = cursor.fetchone()
    
    conn.close()
    
    return render_template('sales/view_order.html',
                         username=session['username'],
                         order=order,
                         order_items=order_items,
                         receipt=receipt)

# 小票管理
@app.route('/sales/receipts')
def receipts():
    # 获取筛选参数
    search = request.args.get('search', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    page = int(request.args.get('page', 1))
    per_page = 10
    
    # 连接数据库
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 构建查询
    base_query = "SELECT * FROM receipts WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM receipts WHERE 1=1"
    params = []
    
    if search:
        search_condition = " AND (receipt_number LIKE ? OR order_number LIKE ? OR customer_name LIKE ? OR customer_phone LIKE ?)"
        base_query += search_condition
        count_query += search_condition
        search_param = f'%{search}%'
        params.extend([search_param, search_param, search_param, search_param])
    
    if date_from:
        base_query += " AND DATE(receipt_date) >= ?"
        count_query += " AND DATE(receipt_date) >= ?"
        params.append(date_from)
    
    if date_to:
        base_query += " AND DATE(receipt_date) <= ?"
        count_query += " AND DATE(receipt_date) <= ?"
        params.append(date_to)
    
    # 获取总记录数
    cursor.execute(count_query, params)
    total_records = cursor.fetchone()[0]
    total_pages = (total_records + per_page - 1) // per_page
    
    # 添加分页
    base_query += " ORDER BY receipt_date DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    
    # 执行查询
    cursor.execute(base_query, params)
    receipts_list = cursor.fetchall()
    
    conn.close()
    
    return render_template('sales/receipts.html',
                          username=session['username'],
                          receipts=receipts_list,
                          search=search,
                          date_from=date_from,
                          date_to=date_to,
                          page=page,
                          total_pages=total_pages,
                          has_prev=(page > 1),
                          has_next=(page < total_pages))

@app.route('/receipt/<int:id>')
def get_receipt_detail(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取小票信息
    cursor.execute("""
        SELECT r.*, o.table_number, o.notes 
        FROM receipts r 
        LEFT JOIN orders o ON r.order_number = o.order_number 
        WHERE r.id = ?
    """, (id,))
    receipt = cursor.fetchone()
    
    if not receipt:
        return jsonify({'error': '小票不存在'}), 404
    
    # 获取订单明细
    cursor.execute("""
        SELECT oi.* 
        FROM order_items oi 
        WHERE oi.order_number = ?
    """, (receipt['order_number'],))
    items = cursor.fetchall()
    
    conn.close()
    
    return render_template('sales/receipt_detail.html',
                          receipt=receipt,
                          items=items)

@app.route('/print_receipt/<int:id>')
def print_receipt_by_id(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取小票信息
    cursor.execute("""
        SELECT r.*, o.table_number, o.notes, o.created_at as order_time
        FROM receipts r 
        LEFT JOIN orders o ON r.order_number = o.order_number 
        WHERE r.id = ?
    """, (id,))
    receipt = cursor.fetchone()
    
    if not receipt:
        flash('小票不存在', 'danger')
        return redirect(url_for('receipts'))
    
    # 获取订单明细
    cursor.execute("""
        SELECT oi.* 
        FROM order_items oi 
        WHERE oi.order_number = ?
    """, (receipt['order_number'],))
    items = cursor.fetchall()
    
    # 更新打印状态
    cursor.execute("UPDATE receipts SET is_printed = 1 WHERE id = ?", (id,))
    conn.commit()
    
    conn.close()
    
    return render_template('sales/print_receipt.html',
                          receipt=receipt,
                          items=items,
                          print_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

@app.route('/export_receipts')
def export_receipts():
    # 获取选中的小票ID列表
    ids = request.args.get('ids', '').split(',')
    if not ids or not ids[0]:
        flash('请选择要导出的小票', 'warning')
        return redirect(url_for('receipts'))

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 创建Excel文件
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    
    # 设置格式
    title_format = workbook.add_format({
        'bold': True,
        'align': 'center',
        'valign': 'vcenter',
        'font_size': 12,
        'bg_color': '#F4F4F4'
    })
    
    header_format = workbook.add_format({
        'bold': True,
        'align': 'center',
        'valign': 'vcenter',
        'bg_color': '#F4F4F4'
    })
    
    date_format = workbook.add_format({
        'num_format': 'yyyy-mm-dd hh:mm:ss'
    })
    
    # 创建汇总工作表
    summary = workbook.add_worksheet('汇总')
    summary.set_column('A:A', 15)  # 小票编号
    summary.set_column('B:B', 15)  # 订单编号
    summary.set_column('C:C', 20)  # 下单时间
    summary.set_column('D:D', 10)  # 就餐方式
    summary.set_column('E:E', 15)  # 顾客手机
    summary.set_column('F:F', 15)  # 会员信息
    summary.set_column('G:G', 10)  # 总金额
    summary.set_column('H:H', 10)  # 打印状态
    
    # 写入汇总表头
    headers = ['小票编号', '订单编号', '下单时间', '就餐方式', '顾客手机', '会员信息', '总金额', '打印状态']
    for col, header in enumerate(headers):
        summary.write(0, col, header, header_format)
    
    # 获取并写入小票数据
    placeholders = ','.join('?' * len(ids))
    cursor.execute(f"""
        SELECT r.*, o.created_at as order_time, o.table_number, o.notes
        FROM receipts r
        LEFT JOIN orders o ON r.order_number = o.order_number
        WHERE r.id IN ({placeholders})
        ORDER BY r.receipt_date DESC
    """, ids)
    receipts = cursor.fetchall()
    
    row = 1
    total_amount = 0
    
    for receipt in receipts:
        summary.write(row, 0, receipt['receipt_number'])
        summary.write(row, 1, receipt['order_number'])
        summary.write(row, 2, receipt['order_time'], date_format)
        summary.write(row, 3, receipt['dining_mode'] or '-')
        summary.write(row, 4, receipt['customer_phone'] or '-')
        summary.write(row, 5, receipt['member_info'] or '非会员')
        summary.write(row, 6, receipt['total_amount'])
        summary.write(row, 7, '已打印' if receipt['is_printed'] else '未打印')
        
        total_amount += receipt['total_amount']
        
        # 为每个小票创建详细工作表
        detail = workbook.add_worksheet(f'小票_{receipt["receipt_number"]}')
        detail.set_column('A:A', 15)
        detail.set_column('B:B', 20)
        detail.set_column('C:C', 10)
        detail.set_column('D:D', 12)
        detail.set_column('E:E', 12)
        
        # 写入小票基本信息
        detail.merge_range('A1:E1', '销售小票', title_format)
        detail.write('A2', '小票编号:')
        detail.write('B2', receipt['receipt_number'])
        detail.write('A3', '订单编号:')
        detail.write('B3', receipt['order_number'])
        detail.write('A4', '下单时间:')
        detail.write('B4', receipt['order_time'])
        detail.write('A5', '就餐方式:')
        detail.write('B5', receipt['dining_mode'] or '-')
        
        # 获取并写入商品明细
        cursor.execute("""
            SELECT * FROM order_items 
            WHERE order_number = ?
        """, (receipt['order_number'],))
        items = cursor.fetchall()
        
        # 写入商品明细表头
        item_headers = ['商品编号', '商品名称', '数量', '单价', '金额']
        for col, header in enumerate(item_headers):
            detail.write(6, col, header, header_format)
        
        # 写入商品明细数据
        detail_row = 7
        for item in items:
            detail.write(detail_row, 0, item['item_code'])
            detail.write(detail_row, 1, item['item_name'])
            detail.write(detail_row, 2, item['quantity'])
            detail.write(detail_row, 3, item['unit_price'])
            detail.write(detail_row, 4, item['total_price'])
            detail_row += 1
        
        row += 1
    
    # 写入汇总信息
    summary.write(row + 1, 5, '总计:', header_format)
    summary.write(row + 1, 6, total_amount, header_format)
    summary.write(row + 3, 0, f'导出时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    
    workbook.close()
    output.seek(0)
    
    # 生成下载文件名
    filename = f'小票批量导出_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    conn.close()
    
    return send_file(output,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/delete_receipts', methods=['POST'])
def delete_receipts():
    data = request.get_json()
    if not data or 'ids' not in data or not data['ids']:
        return jsonify({'success': False, 'message': '请选择要删除的小票'})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 删除选中的小票
        placeholders = ','.join('?' * len(data['ids']))
        cursor.execute(f"DELETE FROM receipts WHERE id IN ({placeholders})", data['ids'])
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'成功删除 {cursor.rowcount} 张小票'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'删除失败：{str(e)}'
        })
    finally:
        conn.close()

def migrate_receipts_table():
    """迁移小票表结构，添加新字段"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取当前表结构
        cursor.execute("PRAGMA table_info(receipts)")
        current_columns = {column[1] for column in cursor.fetchall()}

        # 需要添加的字段列表
        required_columns = {
            'receipt_number': 'TEXT UNIQUE NOT NULL',
            'order_number': 'TEXT NOT NULL',
            'order_time': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            'dining_mode': 'TEXT',
            'total_amount': 'REAL NOT NULL',
            'customer_name': 'TEXT',
            'customer_phone': 'TEXT',
            'member_info': 'TEXT',
            'is_printed': 'INTEGER DEFAULT 0',
            'receipt_date': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        }

        # 如果表不存在，创建表
        if 'receipts' not in {table[0] for table in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}:
            create_table_sql = '''
            CREATE TABLE receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_number TEXT UNIQUE NOT NULL,
                order_number TEXT NOT NULL,
                order_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                dining_mode TEXT,
                total_amount REAL NOT NULL,
                customer_name TEXT,
                customer_phone TEXT,
                member_info TEXT,
                is_printed INTEGER DEFAULT 0,
                receipt_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_number) REFERENCES orders (order_number)
            )
            '''
            cursor.execute(create_table_sql)
            print("Created receipts table")
        else:
            # 添加缺失的列
            for column, type_def in required_columns.items():
                if column not in current_columns:
                    try:
                        cursor.execute(f"ALTER TABLE receipts ADD COLUMN {column} {type_def}")
                        print(f"Added column {column} to receipts table")
                    except Exception as e:
                        print(f"Error adding column {column}: {str(e)}")

        conn.commit()
        print("小票表迁移完成")

    except Exception as e:
        print(f"小票表迁移失败: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

# 添加上下文处理器，为所有模板提供now()函数
@app.context_processor
def utility_processor():
    return {
        'now': datetime.now
    }

@app.route('/export_receipt/<int:id>')
def export_receipt_by_id(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取小票信息
    cursor.execute("""
        SELECT r.*, o.table_number, o.notes, o.created_at as order_time
        FROM receipts r 
        LEFT JOIN orders o ON r.order_number = o.order_number 
        WHERE r.id = ?
    """, (id,))
    receipt = cursor.fetchone()
    
    if not receipt:
        flash('小票不存在', 'danger')
        return redirect(url_for('receipts'))
    
    # 获取订单明细
    cursor.execute("""
        SELECT oi.* 
        FROM order_items oi 
        WHERE oi.order_number = ?
    """, (receipt['order_number'],))
    items = cursor.fetchall()
    
    # 创建Excel文件
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()
    
    # 设置列宽
    worksheet.set_column('A:A', 15)  # 编号列
    worksheet.set_column('B:B', 20)  # 名称列
    worksheet.set_column('C:C', 10)  # 数量列
    worksheet.set_column('D:D', 12)  # 单价列
    worksheet.set_column('E:E', 12)  # 金额列
    
    # 添加标题
    title_format = workbook.add_format({
        'bold': True,
        'align': 'center',
        'valign': 'vcenter',
        'font_size': 14
    })
    worksheet.merge_range('A1:E1', '销售小票', title_format)
    
    # 添加小票基本信息
    info_format = workbook.add_format({'bold': True})
    worksheet.write('A2', '小票编号:', info_format)
    worksheet.write('B2', receipt['receipt_number'])
    worksheet.write('A3', '订单编号:', info_format)
    worksheet.write('B3', receipt['order_number'])
    worksheet.write('A4', '下单时间:', info_format)
    worksheet.write('B4', receipt['order_time'])
    worksheet.write('A5', '就餐方式:', info_format)
    worksheet.write('B5', receipt['dining_mode'] or '-')
    worksheet.write('A6', '顾客手机:', info_format)
    worksheet.write('B6', receipt['customer_phone'] or '-')
    worksheet.write('A7', '会员信息:', info_format)
    worksheet.write('B7', receipt['member_info'] or '非会员')
    
    # 添加表头
    header_format = workbook.add_format({
        'bold': True,
        'align': 'center',
        'valign': 'vcenter',
        'bg_color': '#F4F4F4'
    })
    headers = ['商品编号', '商品名称', '数量', '单价', '金额']
    for col, header in enumerate(headers):
        worksheet.write(8, col, header, header_format)
    
    # 添加商品明细
    row = 9
    for item in items:
        worksheet.write(row, 0, item['item_code'])
        worksheet.write(row, 1, item['item_name'])
        worksheet.write(row, 2, item['quantity'])
        worksheet.write(row, 3, item['unit_price'])
        worksheet.write(row, 4, item['total_price'])
        row += 1
    
    # 添加合计
    total_format = workbook.add_format({
        'bold': True,
        'align': 'right'
    })
    worksheet.merge_range(f'A{row+1}:D{row+1}', '合计:', total_format)
    worksheet.write(row, 4, receipt['total_amount'])
    
    # 添加备注（如果有）
    if receipt['notes']:
        row += 2
        worksheet.merge_range(f'A{row}:B{row}', '订单备注:', info_format)
        worksheet.merge_range(f'C{row}:E{row}', receipt['notes'])
    
    # 添加导出时间
    row += 2
    worksheet.merge_range(f'A{row}:E{row}', f'导出时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 
                         workbook.add_format({'align': 'center'}))
    
    workbook.close()
    output.seek(0)
    
    # 生成文件名
    filename = f"小票_{receipt['receipt_number']}.xlsx"
    
    conn.close()
    
    return send_file(output,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

def fix_order_numbers():
    """修正现有订单的编号格式"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取所有订单，按创建时间排序
        cursor.execute("""
            SELECT order_number, created_at, 
                   strftime('%Y%m%d', created_at) as order_date
            FROM orders 
            ORDER BY created_at
        """)
        orders = cursor.fetchall()
        
        # 按日期分组
        date_orders = {}
        for order in orders:
            date = order['order_date']
            if date not in date_orders:
                date_orders[date] = []
            date_orders[date].append(order['order_number'])
        
        # 开始事务
        cursor.execute("BEGIN TRANSACTION")
        
        try:
            # 更新订单编号
            for date, order_numbers in date_orders.items():
                for i, old_number in enumerate(order_numbers, 1):
                    new_number = f'DD{date}{i:04d}'
                    
                    # 更新订单表
                    cursor.execute("""
                        UPDATE orders 
                        SET order_number = ? 
                        WHERE order_number = ?
                    """, (new_number, old_number))
                    
                    # 更新订单明细表
                    cursor.execute("""
                        UPDATE order_items 
                        SET order_number = ? 
                        WHERE order_number = ?
                    """, (new_number, old_number))
                    
                    # 更新小票表
                    cursor.execute("""
                        UPDATE receipts 
                        SET order_number = ?,
                            receipt_number = ?
                        WHERE order_number = ?
                    """, (new_number, f'FP{date}{i:04d}', old_number))
                    
                    # 更新小票明细表（通过receipts表的关联）
                    cursor.execute("""
                        UPDATE receipt_items
                        SET receipt_id = (
                            SELECT id FROM receipts WHERE order_number = ?
                        )
                        WHERE receipt_id IN (
                            SELECT id FROM receipts WHERE order_number = ?
                        )
                    """, (new_number, old_number))
            
            # 提交事务
            cursor.execute("COMMIT")
            print("订单编号修正完成")
            
        except Exception as e:
            # 发生错误时回滚
            cursor.execute("ROLLBACK")
            print(f"修正订单编号时发生错误: {str(e)}")
            raise
            
    except Exception as e:
        print(f"修正订单编号失败: {str(e)}")
    finally:
        conn.close()

@app.route('/receipts/import', methods=['POST'])
def import_receipts():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 查找已完成但未生成小票的订单
        cursor.execute('''
            SELECT o.*, COUNT(r.id) as receipt_count
            FROM orders o
            LEFT JOIN receipts r ON o.order_number = r.order_number
            WHERE o.order_status = '已完成'
            GROUP BY o.order_number
            HAVING receipt_count = 0
        ''')
        orders = cursor.fetchall()
        
        imported_count = 0
        
        for order in orders:
            # 生成小票编号
            receipt_number = f'FP{order["order_number"][3:]}'
            
            # 创建小票
            cursor.execute('''
                INSERT INTO receipts (
                    receipt_number, order_number, order_time, dining_mode,
                    total_amount, customer_name, customer_phone, member_info,
                    is_printed, receipt_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
            ''', (
                receipt_number,
                order['order_number'],
                order['created_at'],
                order['order_type'],
                order['final_amount'],
                order['customer_name'],
                order['customer_phone'],
                None  # 会员信息（暂无）
            ))
            
            # 获取新创建的小票ID
            cursor.execute("SELECT last_insert_rowid() as receipt_id")
            receipt_id = cursor.fetchone()['receipt_id']
            
            # 获取订单明细
            cursor.execute('''
                SELECT * FROM order_items 
                WHERE order_number = ?
            ''', (order['order_number'],))
            items = cursor.fetchall()
            
            # 创建小票明细
            for item in items:
                cursor.execute('''
                    INSERT INTO receipt_items (
                        receipt_id, item_code, item_name, quantity,
                        unit_price, total_price, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    receipt_id,
                    item['item_code'],
                    item['item_name'],
                    item['quantity'],
                    item['unit_price'],
                    item['total_price'],
                    item['notes']
                ))
            
            imported_count += 1
        
        conn.commit()
        return jsonify({
            'success': True,
            'message': f'成功导入 {imported_count} 张小票'
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({
            'success': False,
            'message': f'导入小票失败: {str(e)}'
        })
    finally:
        conn.close()

if __name__ == '__main__':
    try:
        # 初始化数据库（如果不存在）
        init_db()
        
        # 修正订单编号
        fix_order_numbers()
        
        # 启动应用
        app.run(debug=True, host='localhost', port=5002)
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
