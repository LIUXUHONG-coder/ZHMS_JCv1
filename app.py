import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, Response, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import json
import requests
import uuid
import xlsxwriter
import io
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# 导入各个子系统的路由模块
from routes.purchase_routes import register_purchase_routes
from routes.inventory_routes import register_inventory_routes
from routes.sales_routes import register_sales_routes
from routes.special_routes import register_special_routes

# 配置目录
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
UPLOAD_FOLDER = os.path.join(STATIC_DIR, 'uploads')
DB_FILE = os.path.join(DATA_DIR, 'restaurant.db')

# 确保所需目录存在
for directory in [DATA_DIR, STATIC_DIR, TEMPLATES_DIR, UPLOAD_FOLDER]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# 确保合同上传目录存在
CONTRACTS_UPLOAD_DIR = os.path.join(UPLOAD_FOLDER, 'contracts')
if not os.path.exists(CONTRACTS_UPLOAD_DIR):
    os.makedirs(CONTRACTS_UPLOAD_DIR)

# 确保静态资源目录存在
IMAGES_DIR = os.path.join(STATIC_DIR, 'images')
if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

# 创建默认图片（如果不存在）
def create_default_images():
    # 需要的图片文件列表
    required_images = [
        'purchase.jpg',
        'inventory.jpg',
        'sales.jpg',
        'special.jpg',
        'default-logo.png'
    ]
    
    for img_name in required_images:
        img_path = os.path.join(IMAGES_DIR, img_name)
        
        # 如果图片不存在，创建一个空文件
        if not os.path.exists(img_path):
            with open(img_path, 'w') as f:
                f.write('')
            print(f"创建了空白图片文件: {img_path}")

# 数据库连接函数
def get_db_connection():
    """连接数据库"""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        # 设置编码
        conn.text_factory = str
        # 启用外键约束
        conn.execute('PRAGMA foreign_keys = ON')
        # 创建本地时区函数
        conn.create_function('local_now', 0, lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        return conn
    except Exception as e:
        print(f"Error connecting to database: {str(e)}")
        raise

# 添加 nl2br 过滤器
def nl2br(value):
    """将换行符转换为 <br> 标签"""
    if value is None:
        return ''
    return value.replace('\n', '<br>')

# 配置Flask应用
app = Flask(__name__,
           static_folder=STATIC_DIR,
           template_folder=TEMPLATES_DIR)
app.secret_key = 'restaurant_management_system_secret_key'

# 添加 nl2br 过滤器到模板环境
app.jinja_env.filters['nl2br'] = nl2br

# 会话配置
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max-limit
app.config['DB_FILE'] = DB_FILE

# 确保每个请求前session中都有username和角色信息
@app.before_request
def ensure_username():
    if 'username' not in session:
        # 设置默认管理员用户和其他必要会话信息
        session['username'] = 'admin'
        session['role'] = 'admin'  # 添加管理员角色
        session['permissions'] = [  # 添加管理员权限
            'purchase_manage',
            'inventory_manage',
            'sales_manage',
            'user_manage',
            'system_manage'
        ]
        session['logged_in'] = True  # 添加登录状态标记
        # 确保每次请求都刷新会话时间
        session.modified = True

# 主页
@app.route('/')
def home():
    return render_template('index.html', username=session.get('username', '默认用户'))

# 退出登录
@app.route('/logout')
def logout():
    session.clear()
    flash('您已退出登录', 'success')
    return redirect(url_for('home'))

# 静态文件服务
@app.route('/static/<path:filename>')
def serve_static(filename):
    # 移除路径中可能存在的 'static/' 前缀
    if filename.startswith('static/'):
        filename = filename[7:]
    return send_from_directory(STATIC_DIR, filename)

# 注册各个子系统的路由
register_purchase_routes(app)
register_inventory_routes(app)
register_sales_routes(app)
register_special_routes(app)

# 创建定时任务调度器
scheduler = BackgroundScheduler()
scheduler.start()

def auto_generate_receipts():
    """自动为已完成的订单生成小票"""
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
            
            print(f"已为订单 {order['order_number']} 自动生成小票 {receipt_number}")
        
        conn.commit()
    except Exception as e:
        print(f"自动生成小票时出错: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

# 添加定时任务，每5分钟检查一次
scheduler.add_job(
    auto_generate_receipts,
    trigger=IntervalTrigger(minutes=5),
    id='auto_generate_receipts',
    name='自动生成小票',
    replace_existing=True
)

# 添加错误处理器
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': '文件大小超过限制，请确保文件不超过200MB'}), 413

if __name__ == '__main__':
    # 确保路由目录存在
    if not os.path.exists('routes'):
        os.makedirs('routes')
        # 创建__init__.py文件，使routes成为一个Python包
        with open(os.path.join('routes', '__init__.py'), 'w') as f:
            f.write('# 这是一个Python包')
    
    # 创建默认图片
    create_default_images()
    
    # 启动Flask应用
    app.run(debug=True, port=5000) 