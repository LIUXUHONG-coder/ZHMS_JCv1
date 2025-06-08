import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash
import random
import time

app = Flask(__name__)
app.secret_key = 'restaurant_management_system_secret_key'

# 确保数据目录存在
if not os.path.exists('data'):
    os.makedirs('data')

# 数据库文件路径
DB_PATH = os.path.join('data', 'restaurant.db')

def get_db_connection():
    """连接数据库"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        # 设置编码
        conn.text_factory = str
        # 启用外键约束
        conn.execute('PRAGMA foreign_keys = ON')
        return conn
    except Exception as e:
        print(f"Error connecting to database: {str(e)}")
        raise

def disable_foreign_keys(conn):
    """禁用外键约束"""
    conn.execute('PRAGMA foreign_keys = OFF')
    
def enable_foreign_keys(conn):
    """启用外键约束"""
    conn.execute('PRAGMA foreign_keys = ON')

def init_db():
    """初始化仓储管理数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 开始事务
        conn.execute('BEGIN')
        
        # 检查入库单表是否存在
        table_exists = cursor.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='inbound_records'
        ''').fetchone()
        
        if not table_exists:
            # 创建入库单表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS inbound_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inbound_no TEXT NOT NULL UNIQUE,
                purchase_no TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                inbound_time DATETIME NOT NULL,
                quality_check BOOLEAN NOT NULL,
                inspector TEXT NOT NULL,
                remarks TEXT,
                storage_location TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(inbound_no, item_name)
            )
            ''')
            print("Created inbound_records table.")
        else:
            # 检查是否需要添加storage_location列
            columns = cursor.execute('PRAGMA table_info(inbound_records)').fetchall()
            if not any(col[1] == 'storage_location' for col in columns):
                cursor.execute('ALTER TABLE inbound_records ADD COLUMN storage_location TEXT')
                print("Added storage_location column to inbound_records table.")

        # 检查出库记录表是否存在
        outbound_exists = cursor.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='outbound_records'
        ''').fetchone()
        
        if not outbound_exists:
            # 如果表不存在，创建新表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS outbound_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    outbound_no TEXT NOT NULL,
                    inbound_no TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    unit TEXT NOT NULL,
                    outbound_time DATETIME,
                    receiver TEXT,
                    approver TEXT,
                    purpose TEXT,
                    status TEXT NOT NULL DEFAULT '待出库',
                    remarks TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (inbound_no, item_name) REFERENCES inbound_records(inbound_no, item_name)
                )
            ''')
            print("Created new outbound_records table.")
        else:
            # 检查是否需要更新表结构
            columns = cursor.execute('PRAGMA table_info(outbound_records)').fetchall()
            required_columns = {
                'outbound_time': 'DATETIME',
                'receiver': 'TEXT',
                'approver': 'TEXT',
                'purpose': 'TEXT',
                'status': 'TEXT',
                'remarks': 'TEXT'
            }
            
            # 检查并添加缺失的列
            for col_name, col_type in required_columns.items():
                if not any(col[1] == col_name for col in columns):
                    cursor.execute(f'ALTER TABLE outbound_records ADD COLUMN {col_name} {col_type}')
                    print(f"Added {col_name} column to outbound_records table.")
            
            # 确保status列有默认值
            cursor.execute('''
                UPDATE outbound_records 
                SET status = '待出库' 
                WHERE status IS NULL
            ''')

        # 创建库存设置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                warning_threshold_red REAL NOT NULL,
                warning_threshold_yellow REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 插入示例预警阈值（如果不存在）
        cursor.execute('''
            INSERT OR IGNORE INTO inventory_settings (item_name, warning_threshold_red, warning_threshold_yellow)
            VALUES 
                ('尖椒', 50, 100),
                ('香菇', 30, 60)
        ''')

        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_inbound_records_inbound_no ON inbound_records(inbound_no)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_inbound_records_item_name ON inbound_records(item_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_inbound_records_inbound_time ON inbound_records(inbound_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_outbound_records_outbound_no ON outbound_records(outbound_no)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_outbound_records_inbound_no ON outbound_records(inbound_no)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_outbound_records_item_name ON outbound_records(item_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_outbound_records_status ON outbound_records(status)')

        # 提交事务
        conn.commit()
        print("数据库初始化完成")
        
    except Exception as e:
        # 如果出现错误，回滚事务
        conn.rollback()
        print(f"数据库初始化出错: {str(e)}")
        raise
    finally:
        conn.close()

# 初始化数据库
try:
    init_db()
    print("数据库初始化成功")
except Exception as e:
    print(f"数据库初始化失败: {str(e)}")

# 首页路由
@app.route('/')
def index():
    return render_template('inventory/index.html')

# 仓储管理主页
@app.route('/inventory')
def inventory():
    return render_template('inventory/index.html')

# 库存管理相关路由
@app.route('/inventory/stock')
def stock_management():
    return render_template('inventory/stock.html')

# 入库管理相关路由
@app.route('/inventory/inbound')
def inbound_management():
    return render_template('inventory/inbound.html')

# 出库管理相关路由
@app.route('/inventory/outbound')
def outbound_management():
    return render_template('inventory/outbound.html')

# 物资流转信息路由
@app.route('/inventory/transfer')
def transfer_management():
    return render_template('inventory/transfer.html')

# 采购管理路由
@app.route('/purchase')
def purchase_redirect():
    return redirect('http://localhost:5000/purchase')

# 物资流转统计API
@app.route('/api/inventory/transfer/stats')
def get_transfer_stats():
    conn = get_db_connection()
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        current_month = datetime.now().strftime('%Y-%m')
        
        print(f"开始获取物资流转统计，今天日期: {today}, 本月: {current_month}")
        
        # 获取所有入库记录的时间
        all_inbound_times = conn.execute('SELECT inbound_time FROM inbound_records').fetchall()
        print(f"所有入库记录的时间: {[row['inbound_time'] for row in all_inbound_times]}")
        
        # 获取所有出库记录的时间
        all_outbound_times = conn.execute('SELECT outbound_time FROM outbound_records').fetchall()
        print(f"所有出库记录的时间: {[row['outbound_time'] for row in all_outbound_times]}")
        
        # 获取今日入库数量
        today_inbound_query = '''
            SELECT COUNT(*) as count
            FROM inbound_records
            WHERE strftime('%Y-%m-%d', inbound_time) = ?
            AND quality_check = 1
        '''
        
        # 获取今日出库数量
        today_outbound_query = '''
            SELECT COUNT(*) as count
            FROM outbound_records
            WHERE strftime('%Y-%m-%d', outbound_time) = ?
            AND status = '已出库'
        '''
        
        # 获取本月入库数量
        monthly_inbound_query = '''
            SELECT COUNT(*) as count
            FROM inbound_records
            WHERE strftime('%Y-%m', inbound_time) = ?
            AND quality_check = 1
        '''
        
        # 获取本月出库数量
        monthly_outbound_query = '''
            SELECT COUNT(*) as count
            FROM outbound_records
            WHERE strftime('%Y-%m', outbound_time) = ?
            AND status = '已出库'
        '''
        
        # 执行查询
        today_inbound = conn.execute(today_inbound_query, (today,)).fetchone()['count']
        today_outbound = conn.execute(today_outbound_query, (today,)).fetchone()['count']
        monthly_inbound = conn.execute(monthly_inbound_query, (current_month,)).fetchone()['count']
        monthly_outbound = conn.execute(monthly_outbound_query, (current_month,)).fetchone()['count']
        
        print(f"统计结果: 今日入库={today_inbound}, 今日出库={today_outbound}, 本月入库={monthly_inbound}, 本月出库={monthly_outbound}")
        
        return jsonify({
            'today_transfers': today_inbound + today_outbound,
            'today_inbound': today_inbound,
            'today_outbound': today_outbound,
            'monthly_transfers': monthly_inbound + monthly_outbound,
            'monthly_inbound': monthly_inbound,
            'monthly_outbound': monthly_outbound
        })
        
    except Exception as e:
        print(f"Error getting transfer stats: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 重置采购单状态
@app.route('/api/inventory/reset_purchase_status', methods=['POST'])
def reset_purchase_status():
    conn = get_db_connection()
    try:
        # 将所有已收货和已付款状态的采购单重置为已审核状态
        conn.execute('''
            UPDATE purchase_orders 
            SET status = '已审核' 
            WHERE status IN ('已收货', '已付款', '已入库')
        ''')
        conn.commit()
        
        # 删除所有入库记录
        conn.execute('DELETE FROM inbound_records')
        conn.commit()
        
        return jsonify({'success': True, 'message': '采购单状态已重置'})
    except Exception as e:
        conn.rollback()
        print(f"Error in reset_purchase_status: {str(e)}")
        return jsonify({'success': False, 'message': f'重置状态失败：{str(e)}'}), 500
    finally:
        conn.close()

# 获取待入库的采购单
@app.route('/api/inventory/pending_purchases')
def get_pending_purchases():
    conn = get_db_connection()
    try:
        # 获取已入库且质检合格的采购单号
        processed_orders = {row['purchase_no'] for row in 
            conn.execute('SELECT DISTINCT purchase_no FROM inbound_records WHERE quality_check = 1').fetchall()}
        
        # 获取已审核及之后状态的采购单
        purchases = conn.execute('''
            SELECT DISTINCT
                po.order_id,
                po.status,
                po.created_at,
                s.name as supplier_name,
                GROUP_CONCAT(poi.item_name || '(' || poi.quantity || poi.unit || ')') as product_name
            FROM purchase_orders po
            JOIN purchase_order_items poi ON po.order_id = poi.order_id
            JOIN suppliers s ON po.supplier_id = s.code
            WHERE po.status IN ('已审核', '已收货', '已付款')
            AND po.order_id NOT IN (
                SELECT DISTINCT purchase_no 
                FROM inbound_records 
                WHERE quality_check = 1
            )
            GROUP BY po.order_id
            ORDER BY 
                CASE po.status
                    WHEN '已审核' THEN 1
                    WHEN '已收货' THEN 2
                    WHEN '已付款' THEN 3
                END,
                po.created_at DESC
        ''').fetchall()
        
        # 处理数据
        result = []
        for row in purchases:
            result.append({
                'purchase_no': row['order_id'],
                'product_name': row['product_name'],
                'supplier_name': row['supplier_name'],
                'approved_time': row['created_at'],
                'status': row['status']
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Error in get_pending_purchases: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 获取入库统计数据
@app.route('/api/inventory/inbound_stats')
def get_inbound_stats():
    conn = get_db_connection()
    try:
        # 获取已入库且质检合格的入库单数量
        completed = conn.execute('''
            SELECT COUNT(DISTINCT inbound_no) as count
            FROM inbound_records
            WHERE quality_check = 1
        ''').fetchone()['count']
        
        # 获取质检不合格的入库单数量
        rejected = conn.execute('''
            SELECT COUNT(DISTINCT inbound_no) as count
            FROM inbound_records
            WHERE quality_check = 0
        ''').fetchone()['count']
        
        # 获取待入库的采购单数量
        pending = conn.execute('''
            SELECT COUNT(DISTINCT po.order_id) as count
            FROM purchase_orders po
            WHERE po.status IN ('已审核', '已收货', '已付款')
            AND po.order_id NOT IN (
                SELECT DISTINCT purchase_no
                FROM inbound_records
                WHERE quality_check = 1
            )
        ''').fetchone()['count']
        
        stats = {
            'pending': pending,
            'completed': completed,
            'rejected': rejected
        }
        
        return jsonify(stats)
    except Exception as e:
        print(f"Error in get_inbound_stats: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 获取采购单详细信息的API
@app.route('/api/inventory/purchase_info/<purchase_no>')
def get_purchase_info(purchase_no):
    conn = get_db_connection()
    try:
        # 获取采购单基本信息
        purchase = conn.execute('''
            SELECT 
                po.order_id,
                po.status,
                po.created_at,
                s.name as supplier_name
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.code
            WHERE po.order_id = ?
        ''', (purchase_no,)).fetchone()
        
        if not purchase:
            return jsonify({'error': '采购单不存在'}), 404
            
        # 获取采购单商品明细
        items = conn.execute('''
            SELECT 
                item_name,
                quantity,
                unit
            FROM purchase_order_items
            WHERE order_id = ?
        ''', (purchase_no,)).fetchall()
        
        # 构建商品信息列表
        products = []
        for item in items:
            products.append({
                'name': item['item_name'],
                'quantity': item['quantity'],
                'unit': item['unit']
            })
        
        return jsonify({
            'purchase_no': purchase['order_id'],
            'status': purchase['status'],
            'supplier_name': purchase['supplier_name'],
            'approved_time': purchase['created_at'],
            'products': products
        })
    except Exception as e:
        print(f"Error in get_purchase_info: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 创建入库单的API
@app.route('/api/inventory/create_inbound', methods=['POST'])
def create_inbound_api():
    data = request.json
    conn = get_db_connection()
    
    try:
        # 生成入库单号：IN + 采购单号后11位
        base_inbound_no = f"IN{data['purchaseNo'][-11:]}"
        
        # 开始事务
        conn.execute('BEGIN')
        
        # 插入入库记录
        for product in data['products']:
            inbound_no = f"{base_inbound_no}"  # 所有商品使用相同的入库单号
            print(f"Inserting inbound record: {inbound_no}, {product['name']}")
            conn.execute('''
                INSERT INTO inbound_records (
                    inbound_no, purchase_no, item_name, quantity, unit,
                    inbound_time, quality_check, inspector, remarks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                inbound_no,
                data['purchaseNo'],
                product['name'],
                product['quantity'],
                product['unit'],
                data['inboundTime'],
                data['qualityCheck'] == '1',
                data['inspector'],
                data.get('remarks', '')
            ))
        
        # 如果质检合格，更新采购单状态为"已入库"
        if data['qualityCheck'] == '1':
            print(f"Updating purchase order status: {data['purchaseNo']}")
            conn.execute('''
                UPDATE purchase_orders
                SET status = '已入库'
                WHERE order_id = ?
            ''', (data['purchaseNo'],))
        
        conn.commit()
        print(f"Successfully created inbound record: {base_inbound_no}")
        return jsonify({'success': True, 'message': '入库单创建成功'})
    except Exception as e:
        conn.rollback()
        print(f"Error in create_inbound_api: {str(e)}")
        return jsonify({'success': False, 'message': f'创建入库单失败：{str(e)}'}), 400
    finally:
        conn.close()

# 获取不同状态的入库单列表
@app.route('/api/inventory/inbound_list/<status>')
def get_inbound_list(status):
    conn = get_db_connection()
    try:
        if status == 'pending':
            # 获取待入库的采购单
            return get_pending_purchases()
        elif status == 'completed':
            # 获取已完成的入库单
            records = conn.execute('''
                SELECT 
                    ir.inbound_no,
                    ir.purchase_no,
                    s.name as supplier_name,
                    ir.inbound_time,
                    ir.inspector,
                    GROUP_CONCAT(ir.item_name || '(' || ir.quantity || ir.unit || ')') as items
                FROM inbound_records ir
                JOIN purchase_orders po ON ir.purchase_no = po.order_id
                JOIN suppliers s ON po.supplier_id = s.code
                WHERE ir.quality_check = 1
                GROUP BY ir.inbound_no
                ORDER BY ir.inbound_time DESC
            ''').fetchall()
            
            # 处理数据
            result = []
            for row in records:
                result.append({
                    'inbound_no': row['inbound_no'],
                    'purchase_no': row['purchase_no'],
                    'supplier_name': row['supplier_name'],
                    'items': row['items'],
                    'inbound_time': row['inbound_time'],
                    'inspector': row['inspector']
                })
            
            return jsonify(result)
        else:  # rejected
            # 获取质检不合格的入库单
            records = conn.execute('''
                SELECT 
                    ir.inbound_no,
                    ir.purchase_no,
                    s.name as supplier_name,
                    ir.inbound_time,
                    ir.inspector,
                    GROUP_CONCAT(ir.item_name || '(' || ir.quantity || ir.unit || ')') as items
                FROM inbound_records ir
                JOIN purchase_orders po ON ir.purchase_no = po.order_id
                JOIN suppliers s ON po.supplier_id = s.code
                WHERE ir.quality_check = 0
                GROUP BY ir.inbound_no
                ORDER BY ir.inbound_time DESC
            ''').fetchall()
            
            # 处理数据
            result = []
            for row in records:
                result.append({
                    'inbound_no': row['inbound_no'],
                    'purchase_no': row['purchase_no'],
                    'supplier_name': row['supplier_name'],
                    'items': row['items'],
                    'inbound_time': row['inbound_time'],
                    'inspector': row['inspector']
                })
            
            return jsonify(result)
    except Exception as e:
        print(f"Error in get_inbound_list: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/inventory/inbound_detail/<inbound_no>')
def get_inbound_detail(inbound_no):
    conn = get_db_connection()
    try:
        # 获取入库单基本信息
        basic_info = conn.execute('''
            SELECT DISTINCT
                ir.inbound_no,
                ir.purchase_no,
                s.name as supplier_name,
                ir.inbound_time,
                ir.inspector,
                ir.quality_check,
                ir.remarks
            FROM inbound_records ir
            JOIN purchase_orders po ON ir.purchase_no = po.order_id
            JOIN suppliers s ON po.supplier_id = s.code
            WHERE ir.inbound_no = ?
        ''', (inbound_no,)).fetchone()
        
        if not basic_info:
            return jsonify({'error': '入库单不存在'}), 404
            
        # 获取入库单商品明细
        items = conn.execute('''
            SELECT 
                item_name,
                quantity,
                unit
            FROM inbound_records
            WHERE inbound_no = ?
        ''', (inbound_no,)).fetchall()
        
        return jsonify({
            'inbound_no': basic_info['inbound_no'],
            'purchase_no': basic_info['purchase_no'],
            'supplier_name': basic_info['supplier_name'],
            'inbound_time': basic_info['inbound_time'],
            'inspector': basic_info['inspector'],
            'quality_check': basic_info['quality_check'],
            'remarks': basic_info['remarks'],
            'items': [dict(item) for item in items]
        })
    except Exception as e:
        print(f"Error in get_inbound_detail: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 入库单创建页面
@app.route('/inventory/inbound/create/<purchase_no>')
def create_inbound(purchase_no):
    return render_template('inventory/create_inbound.html')

# 获取库存统计信息
@app.route('/api/inventory/stats')
def get_inventory_stats():
    conn = get_db_connection()
    try:
        # 获取库存种类数量（已入库且质检合格的不同商品数量）
        total_types = conn.execute('''
            SELECT COUNT(DISTINCT item_name) as count
            FROM inbound_records
            WHERE quality_check = 1
        ''').fetchone()['count']

        # 获取预警商品数量（数量小于等于1的商品）
        warning_items = conn.execute('''
            SELECT 
                item_name,
                SUM(quantity) as total_quantity
            FROM inbound_records
            WHERE quality_check = 1
            GROUP BY item_name
            HAVING total_quantity <= 1
        ''').fetchall()

        # 分别统计红色预警（数量=0）和黄色预警（数量=1）的商品数量
        red_warning = 0
        yellow_warning = 0
        for item in warning_items:
            if item['total_quantity'] == 0:
                red_warning += 1
            elif item['total_quantity'] == 1:
                yellow_warning += 1
                
        # 获取待处理出库单数量
        pending_outbound = conn.execute('''
            SELECT COUNT(DISTINCT outbound_no) as count
            FROM outbound_records
            WHERE status = '待出库'
        ''').fetchone()['count']
        
        # 获取本月已处理的出库单数量
        current_month = datetime.now().strftime('%Y-%m')
        monthly_outbound = conn.execute('''
            SELECT COUNT(DISTINCT outbound_no) as count
            FROM outbound_records
            WHERE status = '已出库'
            AND outbound_time LIKE ?
        ''', (f'{current_month}%',)).fetchone()['count']

        return jsonify({
            'total_types': total_types,
            'red_warning': red_warning,
            'yellow_warning': yellow_warning,
            'total_warning': red_warning + yellow_warning,
            'pending_outbound': pending_outbound,
            'monthly_outbound': monthly_outbound
        })
    except Exception as e:
        print(f"Error in get_inventory_stats: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 获取库存列表
@app.route('/api/inventory/stock/list')
def get_stock_list_api():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取库存数据（按商品名称分组计算总数量）
        cursor.execute('''
            WITH latest_records AS (
                SELECT 
                    item_name,
                    ROUND(SUM(quantity), 2) as total_quantity,
                    MIN(unit) as unit,
                    MAX(inbound_time) as latest_inbound_time
                FROM inbound_records
                WHERE quality_check = 1
                GROUP BY item_name
            )
            SELECT 
                ir.inbound_no,
                ir.purchase_no,
                s.name as supplier_name,
                lr.item_name,
                lr.total_quantity,
                lr.unit,
                lr.latest_inbound_time,
                ir.storage_location,
                ir.inspector
            FROM latest_records lr
            JOIN inbound_records ir ON lr.item_name = ir.item_name 
                AND lr.latest_inbound_time = ir.inbound_time
            JOIN purchase_orders po ON ir.purchase_no = po.order_id
            JOIN suppliers s ON po.supplier_id = s.code
            WHERE ir.quality_check = 1
            ORDER BY lr.latest_inbound_time DESC
        ''')
        
        stock_list = []
        for row in cursor.fetchall():
            item_name = row[3]
            total_quantity = float(row[4])
            
            # 确定预警级别：数量为0时红色预警，小于等于1时黄色预警
            warning_level = 'normal'
            if total_quantity == 0:
                warning_level = 'red'
            elif total_quantity <= 1:
                warning_level = 'yellow'
            
            stock_list.append({
                'inbound_no': row[0],
                'purchase_no': row[1],
                'supplier_name': row[2],
                'item_name': item_name,
                'quantity': round(total_quantity, 2),  # 确保返回的数量保留2位小数
                'unit': row[5],
                'inbound_time': row[6],
                'storage_location': row[7],
                'inspector': row[8],
                'warning_level': warning_level
            })
        
        return jsonify(stock_list)
    
    except Exception as e:
        print(f"Error getting stock list: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

# 更新存放位置
@app.route('/api/inventory/stock/update_location', methods=['POST'])
def update_storage_location():
    data = request.json
    if not data or 'inbound_no' not in data or 'item_name' not in data or 'storage_location' not in data:
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400
        
    # 验证存放位置格式
    location = data['storage_location']
    if not is_valid_storage_location(location):
        return jsonify({'success': False, 'message': '存放位置格式不正确'}), 400
    
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE inbound_records 
            SET storage_location = ? 
            WHERE inbound_no = ? AND item_name = ?
        ''', (location, data['inbound_no'], data['item_name']))
        conn.commit()
        return jsonify({'success': True, 'message': '存放位置更新成功'})
    except Exception as e:
        conn.rollback()
        print(f"Error in update_storage_location: {str(e)}")
        return jsonify({'success': False, 'message': f'更新存放位置失败：{str(e)}'}), 500
    finally:
        conn.close()

def is_valid_storage_location(location):
    """验证存放位置格式是否正确"""
    import re
    # 格式：字母(A-F)-数字(1-9)-数字(1-6)-数字(01-99)
    pattern = r'^[A-F]-[1-9]-[1-6]-(?:0[1-9]|[1-9][0-9])$'
    return bool(re.match(pattern, location))

# 获取入库单详情（库存信息用）
@app.route('/api/inventory/stock/detail/<inbound_no>')
def get_stock_detail(inbound_no):
    conn = get_db_connection()
    try:
        # 获取入库单基本信息
        basic_info = conn.execute('''
            SELECT DISTINCT
                ir.inbound_no,
                ir.purchase_no,
                s.name as supplier_name,
                ir.inbound_time,
                ir.inspector,
                ir.quality_check,
                ir.remarks,
                ir.storage_location
            FROM inbound_records ir
            JOIN purchase_orders po ON ir.purchase_no = po.order_id
            JOIN suppliers s ON po.supplier_id = s.code
            WHERE ir.inbound_no = ?
        ''', (inbound_no,)).fetchone()
        
        if not basic_info:
            return jsonify({'error': '入库单不存在'}), 404
            
        # 获取入库单商品明细
        items = conn.execute('''
            SELECT 
                item_name,
                quantity,
                unit,
                storage_location
            FROM inbound_records
            WHERE inbound_no = ?
        ''', (inbound_no,)).fetchall()
        
        # 解析存放位置
        def parse_location(location):
            if not location:
                return "未设置"
            try:
                area, shelf, layer, position = location.split('-')
                area_names = {
                    'A': '生鲜区',
                    'B': '冷藏区',
                    'C': '干货区',
                    'D': '调味品区',
                    'E': '饮品区',
                    'F': '其他区域'
                }
                return f"{area_names.get(area, '未知区域')} {shelf}号货架 {layer}层 {position}号位置"
            except:
                return location

        return jsonify({
            'inbound_no': basic_info['inbound_no'],
            'purchase_no': basic_info['purchase_no'],
            'supplier_name': basic_info['supplier_name'],
            'inbound_time': basic_info['inbound_time'],
            'inspector': basic_info['inspector'],
            'quality_check': basic_info['quality_check'],
            'remarks': basic_info['remarks'],
            'storage_location': basic_info['storage_location'],
            'storage_location_desc': parse_location(basic_info['storage_location']),
            'items': [{
                'item_name': item['item_name'],
                'quantity': item['quantity'],
                'unit': item['unit'],
                'storage_location': item['storage_location'],
                'storage_location_desc': parse_location(item['storage_location'])
            } for item in items]
        })
    except Exception as e:
        print(f"Error in get_stock_detail: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 获取出库统计数据
@app.route('/api/inventory/outbound_stats')
def get_outbound_stats():
    conn = get_db_connection()
    try:
        # 获取各状态的出库单数量（使用DISTINCT确保每个出库单只计算一次）
        query = '''
            SELECT status, COUNT(DISTINCT outbound_no) as count
            FROM outbound_records
            GROUP BY status
        '''
        
        cursor = conn.execute(query)
        
        stats = {
            '待出库': 0,
            '已出库': 0,
            '已取消': 0
        }
        
        for row in cursor.fetchall():
            if row[0] in stats:
                stats[row[0]] = row[1]
        
        # 打印调试信息
        print(f"出库统计结果: {stats}")
        
        # 获取本月已出库记录数量（用于首页统计）
        current_month = datetime.now().strftime('%Y-%m')
        monthly_query = '''
            SELECT COUNT(DISTINCT outbound_no) as count
            FROM outbound_records
            WHERE status = '已出库'
            AND outbound_time LIKE ?
        '''
        
        monthly_count = conn.execute(monthly_query, (f'{current_month}%',)).fetchone()['count']
        print(f"本月已出库数量: {monthly_count}")
        
        # 扩展统计结果，添加本月数据
        stats['monthly'] = monthly_count
        
        return jsonify(stats)
    except Exception as e:
        print(f"Error in get_outbound_stats: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 获取出库单列表
@app.route('/api/inventory/outbound/list/<status>')
def get_outbound_list(status):
    conn = get_db_connection()
    try:
        # 记录查询日志
        print(f"查询出库单列表，状态: {status}")
        
        # 根据状态获取出库记录，使用GROUP BY确保每个出库单只显示一次
        query = '''
            SELECT DISTINCT 
                o.outbound_no,
                o.inbound_no,
                GROUP_CONCAT(o.item_name || '(' || o.quantity || o.unit || ')') as items,
                o.status,
                o.created_at,
                o.outbound_time,
                o.receiver,
                o.approver,
                o.purpose,
                o.remarks
            FROM outbound_records o
            WHERE o.status = ?
            GROUP BY o.outbound_no
            ORDER BY 
                CASE 
                    WHEN o.outbound_time IS NULL THEN o.created_at 
                    ELSE o.outbound_time 
                END DESC
        '''
        
        records = conn.execute(query, (status,)).fetchall()
        
        # 打印查询结果数量和部分数据示例
        print(f"查询到 {len(records)} 条出库记录，状态: {status}")
        if len(records) > 0:
            sample = records[0]
            print(f"示例数据: 出库单号={sample['outbound_no']}, 出库时间={sample['outbound_time']}")
        
        result = []
        for row in records:
            result.append({
                'outbound_no': row['outbound_no'],
                'inbound_no': row['inbound_no'],
                'items': row['items'],
                'status': row['status'],
                'created_at': row['created_at'],
                'outbound_time': row['outbound_time'],
                'receiver': row['receiver'],
                'approver': row['approver'],
                'purpose': row['purpose'],
                'remarks': row['remarks']
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Error in get_outbound_list: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 获取出库单详情
@app.route('/api/inventory/outbound/detail/<outbound_no>')
def get_outbound_detail(outbound_no):
    conn = get_db_connection()
    try:
        # 获取出库单基本信息
        outbound = conn.execute('''
            SELECT DISTINCT
                o.outbound_no,
                o.inbound_no,
                o.status,
                o.created_at,
                o.outbound_time,
                o.receiver,
                o.approver,
                o.purpose,
                o.remarks
            FROM outbound_records o
            WHERE o.outbound_no = ?
        ''', (outbound_no,)).fetchone()
        
        if not outbound:
            return jsonify({'error': '出库单不存在'}), 404
            
        # 获取出库单商品明细
        items = conn.execute('''
            SELECT 
                item_name,
                quantity,
                unit
            FROM outbound_records
            WHERE outbound_no = ?
        ''', (outbound_no,)).fetchall()
        
        return jsonify({
            'outbound_no': outbound['outbound_no'],
            'inbound_no': outbound['inbound_no'],
            'status': outbound['status'],
            'created_at': outbound['created_at'],
            'outbound_time': outbound['outbound_time'],
            'receiver': outbound['receiver'],
            'approver': outbound['approver'],
            'purpose': outbound['purpose'],
            'remarks': outbound['remarks'],
            'items': [dict(item) for item in items]
        })
    except Exception as e:
        print(f"Error in get_outbound_detail: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 处理出库 V2 - 解决外键约束问题
@app.route('/api/inventory/outbound/process_v2', methods=['POST'])
def process_outbound_v2():
    data = request.json
    conn = get_db_connection()
    
    try:
        # 验证请求数据
        if 'outbound_no' not in data or 'status' not in data:
            return jsonify({'success': False, 'message': '请求数据不完整'}), 400
        
        print("开始处理出库，临时禁用外键约束")
        disable_foreign_keys(conn)  # 在整个处理过程开始时就禁用外键约束
            
        # 检查出库单是否存在且状态为待出库
        outbound = conn.execute('''
            SELECT status
            FROM outbound_records
            WHERE outbound_no = ?
            LIMIT 1
        ''', (data['outbound_no'],)).fetchone()
        
        if not outbound:
            conn.rollback()
            return jsonify({'success': False, 'message': '出库单不存在'}), 404
        
        if outbound['status'] != '待出库':
            conn.rollback()
            return jsonify({'success': False, 'message': '该出库单不是待出库状态'}), 400
        
        # 开始事务
        conn.execute('BEGIN')
        
        try:
            # 判断是否有自定义商品列表
            has_custom_items = 'items' in data and isinstance(data['items'], list) and len(data['items']) > 0
            
            # 获取当前日期时间
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if data['status'] == '已出库':
                # 获取原始出库单中的所有商品
                original_items = conn.execute('''
                    SELECT id, outbound_no, inbound_no, item_name, quantity, unit
                    FROM outbound_records
                    WHERE outbound_no = ?
                ''', (data['outbound_no'],)).fetchall()
                
                # 如果没有商品，返回错误
                if not original_items:
                    conn.rollback()
                    return jsonify({'success': False, 'message': '出库单中没有商品'}), 400
                
                # 构建商品字典，便于查找
                original_items_dict = {item['item_name']: item for item in original_items}
                
                # 确定出库商品列表
                output_items = []
                remaining_items = []
                
                if has_custom_items:
                    # 使用客户端提供的商品列表
                    print(f"使用自定义商品列表处理出库: {data['items']}")
                    
                    for custom_item in data['items']:
                        item_name = custom_item['item_name']
                        try:
                            new_quantity = float(custom_item['quantity'])
                        except (ValueError, TypeError):
                            conn.rollback()
                            return jsonify({'success': False, 'message': f'商品 {item_name} 的数量格式不正确'}), 400
                        
                        # 验证商品是否存在于原出库单
                        if item_name not in original_items_dict:
                            conn.rollback()
                            return jsonify({'success': False, 'message': f'商品 {item_name} 不在出库单中'}), 400
                        
                        original_item = original_items_dict[item_name]
                        original_quantity = float(original_item['quantity'])
                        
                        # 验证数量
                        if new_quantity <= 0:
                            # 忽略数量为0的商品
                            continue
                            
                        if new_quantity > original_quantity:
                            conn.rollback()
                            return jsonify({'success': False, 'message': f'商品 {item_name} 出库数量 {new_quantity} 不能超过原数量 {original_quantity}'}), 400
                        
                        # 添加到出库列表
                        output_items.append({
                            'id': original_item['id'],
                            'item_name': item_name,
                            'inbound_no': original_item['inbound_no'],
                            'quantity': new_quantity,
                            'unit': original_item['unit']
                        })
                        
                        # 如果有剩余，添加到剩余列表
                        remaining = original_quantity - new_quantity
                        if remaining > 0:
                            remaining_items.append({
                                'id': original_item['id'],
                                'item_name': item_name,
                                'inbound_no': original_item['inbound_no'],
                                'quantity': remaining,
                                'unit': original_item['unit']
                            })
                else:
                    # 使用原始商品列表
                    print("使用原始商品列表处理出库")
                    
                    for item in original_items:
                        output_items.append({
                            'id': item['id'],
                            'item_name': item['item_name'],
                            'inbound_no': item['inbound_no'],
                            'quantity': float(item['quantity']),
                            'unit': item['unit']
                        })
                
                # 验证是否有商品要出库
                if not output_items:
                    conn.rollback()
                    return jsonify({'success': False, 'message': '没有有效的商品要出库'}), 400
                
                # 处理部分出库的情况
                if remaining_items:
                    print(f"部分出库处理：出库 {len(output_items)} 件商品，剩余 {len(remaining_items)} 件商品")
                    
                    # 创建一个新的出库单号用于已出库部分
                    timestamp = int(time.time())
                    random_suffix = random.randint(1000, 9999)
                    new_outbound_no = f"OUT{timestamp}{random_suffix}"
                    
                    print(f"创建新的已出库单号: {new_outbound_no} 用于出库部分")
                    
                    try:
                        # 对每个部分出库的商品创建新的已出库记录
                        for item in output_items:
                            # 创建新的已出库记录
                            conn.execute('''
                                INSERT INTO outbound_records 
                                (outbound_no, inbound_no, item_name, quantity, unit, status, created_at, outbound_time, receiver, approver, purpose, remarks)
                                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)
                            ''', (
                                new_outbound_no,
                                item['inbound_no'],
                                item['item_name'],
                                item['quantity'],
                                item['unit'],
                                '已出库',
                                current_time,
                                data.get('receiver', ''),
                                data.get('approver', ''),
                                data.get('purpose', ''),
                                data.get('remarks', '')
                            ))
                            
                            print(f"创建已出库记录: {item['item_name']} 数量 {item['quantity']} 到新出库单 {new_outbound_no}")
                            
                            # 更新原出库记录的数量为剩余数量
                            remaining_quantity = None
                            for remaining_item in remaining_items:
                                if remaining_item['item_name'] == item['item_name']:
                                    remaining_quantity = remaining_item['quantity']
                                    break
                                    
                            if remaining_quantity is not None:
                                conn.execute('''
                                    UPDATE outbound_records
                                    SET quantity = ?
                                    WHERE id = ?
                                ''', (remaining_quantity, item['id']))
                                
                                print(f"更新原出库记录: ID={item['id']} {item['item_name']} 剩余数量={remaining_quantity}")
                            
                            # 更新库存
                            stock_exists = conn.execute('''
                                SELECT quantity FROM inbound_records
                                WHERE inbound_no = ? AND item_name = ?
                                LIMIT 1
                            ''', (item['inbound_no'], item['item_name'])).fetchone()
                            
                            if stock_exists:
                                current_quantity = float(stock_exists['quantity'])
                                if current_quantity >= item['quantity']:
                                    # 确保不会出现负库存，并且保留2位小数
                                    new_quantity = round(current_quantity - item['quantity'], 2)
                                    conn.execute('''
                                        UPDATE inbound_records
                                        SET quantity = ?
                                        WHERE inbound_no = ? AND item_name = ?
                                    ''', (new_quantity, item['inbound_no'], item['item_name']))
                                    
                                    print(f"更新库存: {item['inbound_no']} - {item['item_name']} 减少 {item['quantity']}, 剩余 {new_quantity}")
                    except Exception as e:
                        print(f"创建新出库记录时出错: {str(e)}")
                        conn.rollback()
                        return jsonify({
                            'success': False,
                            'message': f'创建新出库记录失败: {str(e)}'
                        }), 500
                else:
                    # 全部出库的情况
                    print("处理全部出库")
                    
                    try:
                        # 更新原出库单状态为已出库
                        conn.execute('''
                            UPDATE outbound_records
                            SET status = ?,
                                outbound_time = ?,
                                receiver = ?,
                                approver = ?,
                                purpose = ?,
                                remarks = ?
                            WHERE outbound_no = ?
                        ''', (
                            '已出库',
                            current_time,
                            data.get('receiver', ''),
                            data.get('approver', ''),
                            data.get('purpose', ''),
                            data.get('remarks', ''),
                            data['outbound_no']
                        ))
                        
                        print(f"更新出库单状态: {data['outbound_no']} -> 已出库")
                        
                        # 更新库存
                        for item in output_items:
                            stock_exists = conn.execute('''
                                SELECT quantity FROM inbound_records
                                WHERE inbound_no = ? AND item_name = ?
                                LIMIT 1
                            ''', (item['inbound_no'], item['item_name'])).fetchone()
                            
                            if stock_exists:
                                current_quantity = float(stock_exists['quantity'])
                                if current_quantity >= item['quantity']:
                                    # 确保不会出现负库存，并且保留2位小数
                                    new_quantity = round(current_quantity - item['quantity'], 2)
                                    conn.execute('''
                                        UPDATE inbound_records
                                        SET quantity = ?
                                        WHERE inbound_no = ? AND item_name = ?
                                    ''', (new_quantity, item['inbound_no'], item['item_name']))
                                    
                                    print(f"更新库存: {item['inbound_no']} - {item['item_name']} 减少 {item['quantity']}, 剩余 {new_quantity}")
                                else:
                                    conn.rollback()
                                    return jsonify({
                                        'success': False,
                                        'message': f'商品 {item["item_name"]} 库存不足，当前库存: {round(current_quantity, 2)}, 需要: {round(item["quantity"], 2)}'
                                    }), 400
                            else:
                                conn.rollback()
                                return jsonify({
                                    'success': False,
                                    'message': f'商品 {item["item_name"]} 的库存记录不存在'
                                }), 400
                                
                    except Exception as e:
                        print(f"全部出库处理时出错: {str(e)}")
                        conn.rollback()
                        return jsonify({
                            'success': False,
                            'message': f'全部出库处理失败: {str(e)}'
                        }), 500
            else:
                # 处理取消出库
                conn.execute('''
                    UPDATE outbound_records
                    SET status = ?,
                        remarks = COALESCE(?, remarks)
                    WHERE outbound_no = ?
                ''', (
                    data['status'],
                    data.get('remarks'),
                    data['outbound_no']
                ))
            
            # 提交事务
            conn.commit()
            
            print("处理完成，重新启用外键约束")
            enable_foreign_keys(conn)  # 处理完成后重新启用外键约束
            
            return jsonify({
                'success': True,
                'message': f'出库单已{data["status"]}'
            })
            
        except Exception as e:
            conn.rollback()
            error_msg = str(e)
            print(f"处理出库单内部操作失败: {error_msg}")
            return jsonify({
                'success': False, 
                'message': f'处理出库单内部操作失败: {error_msg}'
            }), 500
        
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
            
        error_msg = str(e)
        print(f"Error in process_outbound_v2: {error_msg}")
        return jsonify({
            'success': False, 
            'message': error_msg
        }), 500
    finally:
        try:
            # 确保在任何情况下都重新启用外键约束
            enable_foreign_keys(conn)
            print("最终确保重新启用外键约束")
        except:
            pass
        conn.close()

# 创建一个新的从库存导入函数，临时禁用外键约束
@app.route('/api/inventory/force_migrate_inventory', methods=['POST'])
def force_migrate_inventory():
    conn = get_db_connection()
    try:
        print("开始执行从库存导入到出库系统的操作，临时禁用外键约束")
        
        # 禁用外键约束
        conn.execute("PRAGMA foreign_keys = OFF")
        print("外键约束已禁用")
        
        # 获取所有已存在的入库单号和商品名称组合
        existing_records = conn.execute('''
            SELECT DISTINCT inbound_no, item_name 
            FROM outbound_records
        ''').fetchall()
        
        # 创建一个集合来存储已存在的记录标识
        existing_set = {(r['inbound_no'], r['item_name']) for r in existing_records}
        
        # 获取所有符合条件的入库记录，但排除已经存在于出库系统中的记录
        records = conn.execute('''
            SELECT id, inbound_no, item_name, quantity, unit
            FROM inbound_records
            WHERE quality_check = 1 AND quantity > 0
        ''').fetchall()
        
        print(f"找到符合条件的库存记录数量: {len(records)}")
        
        # 手动为每条新记录创建出库记录
        imported_count = 0
        skipped_count = 0
        import time
        timestamp = int(time.time())
        
        for i, record in enumerate(records):
            # 检查记录是否已存在
            record_key = (record['inbound_no'], record['item_name'])
            if record_key in existing_set:
                skipped_count += 1
                continue
                
            # 使用时间戳和序号创建唯一的出库单号
            suffix = f"{i+1:03d}"
            outbound_no = f"OUT{timestamp}{suffix}"
            
            print(f"创建出库单: {outbound_no} 对应入库单: {record['inbound_no']}")
            
            conn.execute('''
                INSERT INTO outbound_records (
                    outbound_no, inbound_no, item_name, quantity, unit, status, created_at
                ) VALUES (?, ?, ?, ?, ?, '待出库', datetime('now'))
            ''', (
                outbound_no,
                record['inbound_no'],
                record['item_name'],
                record['quantity'],
                record['unit']
            ))
            
            imported_count += 1
        
        conn.commit()
        print(f"导入完成：成功导入 {imported_count} 条记录，跳过 {skipped_count} 条已存在记录")
        
        # 重新启用外键约束
        conn.execute("PRAGMA foreign_keys = ON")
        print("外键约束已重新启用")
        
        return jsonify({
            'success': True,
            'message': f'成功导入 {imported_count} 条记录，跳过 {skipped_count} 条已存在记录',
            'imported_count': imported_count,
            'skipped_count': skipped_count
        })
        
    except Exception as e:
        conn.rollback()
        print(f"导入过程中出错: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'导入失败: {str(e)}'
        }), 500
    finally:
        conn.close()

# 修改原来的函数，调用新的强制导入函数
@app.route('/api/inventory/migrate_inventory_to_outbound', methods=['POST'])
def migrate_inventory_to_outbound():
    # 直接调用强制导入函数
    return force_migrate_inventory()

# 处理出库单路由
@app.route('/inventory/outbound/process/<outbound_no>')
def process_outbound_page(outbound_no):
    return render_template('inventory/process_outbound.html', outbound_no=outbound_no)

# 添加一个新的API来修复数据库外键约束
@app.route('/api/inventory/fix_database', methods=['POST'])
def fix_database():
    """修复数据库外键约束问题的API"""
    conn = get_db_connection()
    
    try:
        # 开始事务
        conn.execute('BEGIN')
        
        # 禁用外键约束
        disable_foreign_keys(conn)
        
        # 1. 删除不合法的出库记录（找出引用不存在入库单的记录）
        invalid_records = conn.execute('''
            SELECT outbound_records.inbound_no, COUNT(*) as count
            FROM outbound_records
            LEFT JOIN inbound_records ON outbound_records.inbound_no = inbound_records.inbound_no
            WHERE inbound_records.inbound_no IS NULL
            GROUP BY outbound_records.inbound_no
        ''').fetchall()
        
        deleted_count = 0
        for record in invalid_records:
            inbound_no = record['inbound_no']
            count = record['count']
            
            conn.execute('''
                DELETE FROM outbound_records 
                WHERE inbound_no = ?
            ''', (inbound_no,))
            
            deleted_count += count
            print(f"Deleted {count} invalid outbound records with inbound_no: {inbound_no}")
        
        # 2. 重建出库表（通过init_db函数）
        if deleted_count > 0:
            # 重新启用外键约束
            enable_foreign_keys(conn)
            
            # 提交当前事务
            conn.commit()
            
            # 调用初始化函数重建表结构
            init_db()
            
            return jsonify({
                'success': True,
                'message': f'已修复数据库：删除了 {deleted_count} 条无效的出库记录，并重建了出库记录表。'
            })
        else:
            # 重新启用外键约束
            enable_foreign_keys(conn)
            
            # 提交事务
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': '数据库检查完成，未发现无效的出库记录。'
            })
    
    except Exception as e:
        conn.rollback()
        
        try:
            # 确保重新启用外键约束
            enable_foreign_keys(conn)
        except:
            pass
        
        error_msg = str(e)
        print(f"Error in fix_database: {error_msg}")
        return jsonify({
            'success': False,
            'message': f'修复数据库失败：{error_msg}'
        }), 500
    
    finally:
        conn.close()

# 添加调试页面路由
@app.route('/debug_api')
def debug_api_page():
    """调试页面，显示所有API端点"""
    # 获取所有路由信息
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'url': str(rule)
        })
    
    # 按URL排序
    routes = sorted(routes, key=lambda x: x['url'])
    
    # 检查数据库连接
    db_status = "正常"
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
    except Exception as e:
        db_status = f"错误: {str(e)}"
    
    # 检查表结构
    table_info = {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取所有表
        tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        
        for table in tables:
            table_name = table['name']
            # 获取表结构
            columns = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
            table_info[table_name] = columns
            
            # 获取记录数量
            count = cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}").fetchone()
            table_info[f"{table_name}_count"] = count['count']
        
        conn.close()
    except Exception as e:
        table_info['error'] = str(e)
    
    return jsonify({
        'database_status': db_status,
        'routes': routes,
        'table_info': table_info,
        'app_config': {
            'debug': app.debug,
            'secret_key_set': bool(app.secret_key),
            'db_path': DB_PATH
        }
    })

@app.route('/api/inventory/debug/all_outbound_records', methods=['GET'])
def debug_all_outbound_records():
    """调试API，获取所有出库记录并按状态分组展示"""
    conn = get_db_connection()
    try:
        # 获取所有出库记录，并按状态分组
        records = conn.execute('''
            SELECT 
                status, 
                outbound_no, 
                item_name, 
                quantity, 
                outbound_time
            FROM outbound_records
            ORDER BY status, outbound_no
        ''').fetchall()
        
        # 将记录按状态分组
        result = {
            '待出库': [],
            '已出库': [],
            '已取消': []
        }
        
        # 处理记录
        for record in records:
            status = record['status']
            if status not in result:
                result[status] = []
            
            result[status].append({
                'outbound_no': record['outbound_no'],
                'item_name': record['item_name'],
                'quantity': record['quantity'],
                'outbound_time': record['outbound_time']
            })
        
        # 添加统计信息
        stats = {}
        for status, items in result.items():
            stats[status] = len(items)
            
        return jsonify({
            'stats': stats,
            'records': result
        })
    except Exception as e:
        print(f"Error in debug_all_outbound_records: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 物资流转历史API
@app.route('/api/inventory/transfer/history', methods=['GET'])
def get_transfer_history():
    conn = get_db_connection()
    try:
        print("开始获取物资流转历史")
        
        query = '''
            WITH 
            -- 入库记录
            inbound_info AS (
                SELECT 
                    ir.inbound_no,
                    ir.item_name,
                    ir.unit,
                    ir.inbound_time,
                    ir.storage_location,
                    ir.inspector,
                    ir.quantity as current_stock,
                    ir.remarks as inbound_remarks
                FROM inbound_records ir
                WHERE ir.quality_check = 1  -- 只查询质检合格的记录
            ),
            -- 出库记录
            outbound_info AS (
                SELECT 
                    out_rec.inbound_no,
                    out_rec.item_name,
                    MIN(CASE WHEN out_rec.status = '待出库' THEN out_rec.outbound_time END) as pending_time,
                    MIN(CASE WHEN out_rec.status = '已出库' THEN out_rec.outbound_time END) as outbound_time,
                    MAX(CASE WHEN out_rec.status = '已出库' THEN out_rec.receiver END) as receiver,
                    MAX(CASE WHEN out_rec.status = '已出库' THEN out_rec.purpose END) as purpose,
                    MAX(CASE WHEN out_rec.status = '已出库' THEN out_rec.remarks END) as outbound_remarks,
                    MAX(CASE WHEN out_rec.status = '已出库' THEN 1 ELSE 0 END) as is_outbound,
                    MAX(CASE WHEN out_rec.status = '待出库' THEN 1 ELSE 0 END) as is_pending
                FROM outbound_records out_rec
                GROUP BY out_rec.inbound_no, out_rec.item_name
            )
            -- 合并信息
            SELECT 
                ii.inbound_no,
                ii.item_name,
                ii.unit,
                ii.inbound_time,
                ii.storage_location,
                ii.inspector as inbound_inspector,
                ii.inbound_remarks,
                ii.current_stock,
                oi.pending_time,
                oi.outbound_time,
                oi.receiver,
                oi.purpose,
                oi.outbound_remarks,
                CASE
                    WHEN ii.current_stock <= 0 THEN '已出库'
                    WHEN oi.is_pending = 1 THEN '待出库'
                    ELSE '在库'
                END as current_status
            FROM inbound_info ii
            LEFT JOIN outbound_info oi ON ii.inbound_no = oi.inbound_no AND ii.item_name = oi.item_name
            ORDER BY ii.inbound_time DESC, oi.outbound_time DESC
        '''
        
        records = conn.execute(query).fetchall()
        print(f"查询到 {len(records)} 条物资流转记录")
        
        # 处理查询结果
        result = []
        for row in records:
            # 构建流转节点
            transfer_nodes = []
            
            # 入库节点
            transfer_nodes.append({
                'stage': 1,
                'name': '入库',
                'time': row['inbound_time'],
                'status': 'completed',
                'details': {
                    'storage_location': row['storage_location'],
                    'inspector': row['inbound_inspector'],
                    'remarks': row['inbound_remarks']
                }
            })
            
            # 库存/出库节点
            if row['current_status'] == '在库':
                transfer_nodes.append({
                    'stage': 2,
                    'name': '在库',
                    'status': 'in_progress',
                    'details': {
                        'storage_location': row['storage_location']
                    }
                })
            elif row['current_status'] == '待出库':
                transfer_nodes.append({
                    'stage': 2,
                    'name': '待出库',
                    'time': row['pending_time'],
                    'status': 'in_progress',
                    'details': {
                        'storage_location': row['storage_location']
                    }
                })
            elif row['current_status'] == '已出库':
                transfer_nodes.append({
                    'stage': 2,
                    'name': '已出库',
                    'time': row['outbound_time'],
                    'status': 'completed',
                    'details': {
                        'receiver': row['receiver'],
                        'purpose': row['purpose'],
                        'remarks': row['outbound_remarks']
                    }
                })
            
            result.append({
                'inbound_no': row['inbound_no'],
                'item_name': row['item_name'],
                'current_status': row['current_status'],
                'transfer_nodes': transfer_nodes
            })
        
        print("物资流转历史数据处理完成")
        return jsonify(result)
        
    except Exception as e:
        print(f"获取物资流转历史时出错: {str(e)}")
        return jsonify({
            'error': f'获取物资流转历史失败: {str(e)}'
        }), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5001) 