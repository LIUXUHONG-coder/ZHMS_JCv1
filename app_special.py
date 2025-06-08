import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
import json
import requests
import uuid
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask_sqlalchemy import SQLAlchemy
from models import db, HeritageFood, HeritageFoodTrial

# 配置目录
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_DIR = os.path.join(BASE_DIR, 'data')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
UPLOAD_FOLDER = os.path.join(STATIC_DIR, 'uploads', 'heritage_dishes')

# 配置Flask应用
app = Flask(__name__,
           static_folder=STATIC_DIR,
           template_folder=TEMPLATES_DIR)
app.secret_key = 'special_management_system_secret_key'

# 配置SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(DB_DIR, "restaurant.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 定义模型
class HeritageFood(db.Model):
    __tablename__ = 'heritage_foods'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    video_url = db.Column(db.String(255))
    chef = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    trials = db.relationship('HeritageFoodTrial', backref='food', lazy=True)

class HeritageFoodTrial(db.Model):
    __tablename__ = 'heritage_food_trials'
    
    id = db.Column(db.Integer, primary_key=True)
    food_id = db.Column(db.Integer, db.ForeignKey('heritage_foods.id'), nullable=False)
    applicant = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20))
    trial_date = db.Column(db.DateTime, nullable=False)
    remarks = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

# 销售系统API配置
SALES_API_BASE_URL = 'http://localhost:5001'  # 销售系统的基础URL
SALES_API_KEY = os.getenv('SALES_API_KEY', 'your_api_key_here')  # 从环境变量获取API密钥

# 允许上传的视频文件扩展名
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv'}

# 数据库文件路径
DB_PATH = os.path.join('data', 'restaurant.db')

# 传承菜数据（示例数据，实际应该使用数据库）
heritage_dishes = []
heritage_trials = []

def get_db_connection():
    """连接数据库"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn
    except Exception as e:
        print(f"Error connecting to database: {str(e)}")
        raise

def init_db():
    """初始化特色管理数据库"""
    conn = get_db_connection()
    try:
        # 创建传承菜表
        conn.execute('''
        CREATE TABLE IF NOT EXISTS heritage_dishes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id INTEGER NOT NULL,           -- 关联销售系统的菜品ID
            dish_name TEXT NOT NULL,            -- 菜品名称
            history TEXT,                       -- 传承历史
            craftsmanship TEXT,                 -- 制作工艺
            video_path TEXT,                    -- 制作教程视频路径
            trial_price DECIMAL(10,2),          -- 试做价格
            status INTEGER DEFAULT 1,           -- 状态：1-启用，0-停用
            sync_status INTEGER DEFAULT 0,      -- 同步状态：0-未同步，1-已同步
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(dish_id)
        )
        ''')

        # 创建传承菜试做记录表
        conn.execute('''
        CREATE TABLE IF NOT EXISTS heritage_dish_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            heritage_dish_id INTEGER NOT NULL,  -- 关联传承菜ID
            customer_name TEXT NOT NULL,        -- 顾客姓名
            phone TEXT,                         -- 联系电话
            trial_time DATETIME NOT NULL,       -- 试做时间
            status TEXT NOT NULL,               -- 状态：待试做、试做中、已完成、已取消
            order_id INTEGER,                   -- 关联销售系统的订单ID
            trial_price DECIMAL(10,2),          -- 实际试做价格
            notes TEXT,                         -- 备注信息
            sync_status INTEGER DEFAULT 0,      -- 同步状态：0-未同步，1-已同步
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (heritage_dish_id) REFERENCES heritage_dishes(id)
        )
        ''')

        # 创建DIY饮品配料表
        conn.execute('''
        CREATE TABLE IF NOT EXISTS diy_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,                 -- 配料名称
            price DECIMAL(10,2) NOT NULL,       -- 配料单价
            attribute TEXT NOT NULL,            -- 属性：酸、甜、苦、辣、咸
            stock INTEGER NOT NULL,             -- 库存数量
            unit TEXT NOT NULL,                 -- 单位
            status INTEGER DEFAULT 1,           -- 状态：1-启用，0-停用
            sync_status INTEGER DEFAULT 0,      -- 同步状态：0-未同步，1-已同步
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name)
        )
        ''')

        # 创建DIY饮品订单表
        conn.execute('''
        CREATE TABLE IF NOT EXISTS diy_drink_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,                   -- 关联销售系统的订单ID
            customer_name TEXT NOT NULL,        -- 顾客姓名
            phone TEXT,                         -- 联系电话
            total_price DECIMAL(10,2) NOT NULL, -- 总价
            status TEXT NOT NULL,               -- 状态：待制作、制作中、已完成、已取消
            sync_status INTEGER DEFAULT 0,      -- 同步状态：0-未同步，1-已同步
            notes TEXT,                         -- 备注信息
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # 创建DIY饮品订单配料关联表
        conn.execute('''
        CREATE TABLE IF NOT EXISTS diy_drink_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,          -- 关联DIY饮品订单ID
            ingredient_id INTEGER NOT NULL,     -- 关联配料ID
            quantity INTEGER NOT NULL,          -- 数量
            unit_price DECIMAL(10,2) NOT NULL,  -- 单价（冗余存储，便于历史查询）
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES diy_drink_orders(id),
            FOREIGN KEY (ingredient_id) REFERENCES diy_ingredients(id)
        )
        ''')

        # 创建同步日志表
        conn.execute('''
        CREATE TABLE IF NOT EXISTS sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_type TEXT NOT NULL,            -- 同步类型：heritage_dish, trial, diy_order
            record_id INTEGER NOT NULL,         -- 关联记录ID
            status TEXT NOT NULL,               -- 状态：success, failed
            error_message TEXT,                 -- 错误信息
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        conn.commit()
        print("特色管理数据库初始化完成")

    except Exception as e:
        print(f"特色管理数据库初始化失败: {str(e)}")
        raise
    finally:
        conn.close()

# 销售系统API集成类
class SalesSystemAPI:
    @staticmethod
    def get_headers():
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {SALES_API_KEY}'
        }

    @staticmethod
    def create_order(order_data):
        """创建订单"""
        try:
            response = requests.post(
                f'{SALES_API_BASE_URL}/api/orders/create',
                headers=SalesSystemAPI.get_headers(),
                json=order_data
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"创建订单失败: {str(e)}")
            raise

    @staticmethod
    def update_order(order_id, order_data):
        """更新订单"""
        try:
            response = requests.put(
                f'{SALES_API_BASE_URL}/api/orders/{order_id}',
                headers=SalesSystemAPI.get_headers(),
                json=order_data
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"更新订单失败: {str(e)}")
            raise

    @staticmethod
    def get_dishes():
        """获取菜品列表"""
        try:
            response = requests.get(
                f'{SALES_API_BASE_URL}/api/dishes/list',
                headers=SalesSystemAPI.get_headers()
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"获取菜品列表失败: {str(e)}")
            raise

# 同步管理类
class SyncManager:
    @staticmethod
    def log_sync_attempt(conn, sync_type, record_id, status, error_message=None):
        """记录同步尝试"""
        try:
            conn.execute('''
                INSERT INTO sync_logs (sync_type, record_id, status, error_message)
                VALUES (?, ?, ?, ?)
            ''', (sync_type, record_id, status, error_message))
            conn.commit()
        except Exception as e:
            print(f"记录同步日志失败: {str(e)}")
            conn.rollback()

    @staticmethod
    def sync_heritage_trial(conn, trial_id):
        """同步传承菜试做记录到销售系统"""
        try:
            # 获取试做记录详情
            trial = conn.execute('''
                SELECT t.*, h.dish_name, h.trial_price
                FROM heritage_dish_trials t
                JOIN heritage_dishes h ON t.heritage_dish_id = h.id
                WHERE t.id = ?
            ''', (trial_id,)).fetchone()

            if not trial:
                raise Exception("试做记录不存在")

            # 准备订单数据
            order_data = {
                'customer_name': trial['customer_name'],
                'phone': trial['phone'],
                'amount': float(trial['trial_price']),
                'items': [{
                    'name': f"传承菜试做 - {trial['dish_name']}",
                    'price': float(trial['trial_price']),
                    'quantity': 1
                }],
                'status': 'pending',
                'type': 'heritage_trial',
                'notes': trial['notes']
            }

            # 创建销售订单
            result = SalesSystemAPI.create_order(order_data)

            # 更新试做记录
            conn.execute('''
                UPDATE heritage_dish_trials
                SET order_id = ?,
                    sync_status = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (result['order_id'], trial_id))

            # 记录同步成功
            SyncManager.log_sync_attempt(conn, 'heritage_trial', trial_id, 'success')
            conn.commit()

            return result['order_id']

        except Exception as e:
            # 记录同步失败
            SyncManager.log_sync_attempt(conn, 'heritage_trial', trial_id, 'failed', str(e))
            raise

    @staticmethod
    def sync_diy_order(conn, order_id):
        """同步DIY饮品订单到销售系统"""
        try:
            # 获取订单详情
            order = conn.execute('''
                SELECT o.*, GROUP_CONCAT(i.name) as ingredients
                FROM diy_drink_orders o
                LEFT JOIN diy_drink_ingredients di ON o.id = di.order_id
                LEFT JOIN diy_ingredients i ON di.ingredient_id = i.id
                WHERE o.id = ?
                GROUP BY o.id
            ''', (order_id,)).fetchone()

            if not order:
                raise Exception("订单不存在")

            # 准备订单数据
            order_data = {
                'customer_name': order['customer_name'],
                'phone': order['phone'],
                'amount': float(order['total_price']),
                'items': [{
                    'name': f"DIY饮品（{order['ingredients']}）",
                    'price': float(order['total_price']),
                    'quantity': 1
                }],
                'status': 'pending',
                'type': 'diy_drink',
                'notes': order['notes']
            }

            # 创建销售订单
            result = SalesSystemAPI.create_order(order_data)

            # 更新DIY订单
            conn.execute('''
                UPDATE diy_drink_orders
                SET order_id = ?,
                    sync_status = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (result['order_id'], order_id))

            # 记录同步成功
            SyncManager.log_sync_attempt(conn, 'diy_order', order_id, 'success')
            conn.commit()

            return result['order_id']

        except Exception as e:
            # 记录同步失败
            SyncManager.log_sync_attempt(conn, 'diy_order', order_id, 'failed', str(e))
            raise

# 添加定时任务管理器
class TaskManager:
    def __init__(self, app):
        self.app = app
        self.scheduler = BackgroundScheduler()
        self.setup_tasks()

    def setup_tasks(self):
        """设置定时任务"""
        # 每5分钟同步一次未同步的记录
        self.scheduler.add_job(
            func=self.sync_pending_records,
            trigger=IntervalTrigger(minutes=5),
            id='sync_pending_records',
            name='同步未处理记录',
            replace_existing=True
        )

    def start(self):
        """启动定时任务"""
        self.scheduler.start()
        print("定时任务已启动")

    def sync_pending_records(self):
        """同步所有未同步的记录"""
        with self.app.app_context():
            conn = get_db_connection()
            try:
                # 同步传承菜试做记录
                trials = conn.execute('''
                    SELECT id FROM heritage_dish_trials
                    WHERE sync_status = 0 AND status = '已完成'
                ''').fetchall()

                for trial in trials:
                    try:
                        SyncManager.sync_heritage_trial(conn, trial['id'])
                        print(f"成功同步传承菜试做记录 ID: {trial['id']}")
                    except Exception as e:
                        print(f"同步传承菜试做记录失败 ID: {trial['id']}, 错误: {str(e)}")

                # 同步DIY饮品订单
                orders = conn.execute('''
                    SELECT id FROM diy_drink_orders
                    WHERE sync_status = 0 AND status = '已完成'
                ''').fetchall()

                for order in orders:
                    try:
                        SyncManager.sync_diy_order(conn, order['id'])
                        print(f"成功同步DIY饮品订单 ID: {order['id']}")
                    except Exception as e:
                        print(f"同步DIY饮品订单失败 ID: {order['id']}, 错误: {str(e)}")

            except Exception as e:
                print(f"执行同步任务时出错: {str(e)}")
            finally:
                conn.close()

# 根路由：重定向到特色管理主页
@app.route('/')
def root():
    return redirect('/special')

# 路由：特色管理主页
@app.route('/special')
def special_index():
    return render_template('special/index.html')

# 路由：传承菜管理
@app.route('/special/heritage')
def heritage_index():
    return render_template('special/heritage/index.html')

# API：获取传承菜列表
@app.route('/api/special/heritage/list')
def get_heritage_list():
    conn = get_db_connection()
    try:
        dishes = conn.execute('''
            SELECT 
                h.id,
                h.dish_id,
                h.dish_name,
                h.history,
                h.craftsmanship,
                h.video_path,
                h.trial_price,
                h.created_at,
                h.updated_at
            FROM heritage_dishes h
            ORDER BY h.created_at DESC
        ''').fetchall()
        
        return jsonify([dict(dish) for dish in dishes])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# API：更新传承菜信息
@app.route('/api/special/heritage/update', methods=['POST'])
def update_heritage():
    try:
        data = request.json
        dish_id = data.get('id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE heritage_dishes
            SET history = ?,
                craftsmanship = ?,
                trial_price = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (
            data.get('history'),
            data.get('craftsmanship'),
            data.get('trial_price'),
            dish_id
        ))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# API：上传传承菜视频
@app.route('/api/special/heritage/upload_video', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400
    
    video = request.files['video']
    if video.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
        
    if video:
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{video.filename}"
        video.save(os.path.join('static/uploads/heritage/videos', filename))
        return jsonify({
            'message': '上传成功',
            'url': f'/static/uploads/heritage/videos/{filename}'
        })

    return jsonify({'error': '上传失败'}), 400

# API：从销售系统导入传承菜
@app.route('/api/heritage/import_from_sales', methods=['POST'])
def import_from_sales():
    try:
        # 从销售系统获取菜品列表
        response = requests.get(f'{SALES_API_BASE_URL}/api/dishes/list')
        if not response.ok:
            return jsonify({'success': False, 'message': '无法连接销售系统'}), 500
            
        dishes = response.json()
        
        conn = get_db_connection()
        imported_count = 0
        
        try:
            for dish in dishes:
                # 检查是否已存在
                existing = conn.execute(
                    'SELECT id FROM heritage_dishes WHERE dish_id = ?',
                    (dish['id'],)
                ).fetchone()
                
                if not existing:
                    conn.execute('''
                        INSERT INTO heritage_dishes (
                            dish_id, dish_name, trial_price, created_at
                        ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        dish['id'],
                        dish['name'],
                        dish['price'] * 0.5  # 试做价格默认为售价的一半
                    ))
                    imported_count += 1
            
            conn.commit()
            return jsonify({
                'success': True,
                'message': f'成功导入 {imported_count} 个传承菜'
            })
        finally:
            conn.close()
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# API：获取传承菜信息
@app.route('/api/heritage/foods', methods=['GET'])
def get_heritage_foods():
    foods = HeritageFood.query.all()
    return jsonify([{
        'id': food.id,
        'name': food.name,
        'description': food.description,
        'video_url': food.video_url,
        'chef': food.chef,
        'created_at': food.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for food in foods])

# API：创建传承菜
@app.route('/api/heritage/foods', methods=['POST'])
def create_heritage_food():
    data = request.json
    food = HeritageFood(
        name=data['name'],
        description=data['description'],
        video_url=data.get('video_url', ''),
        chef=data['chef']
    )
    db.session.add(food)
    db.session.commit()
    return jsonify({'message': '创建成功', 'id': food.id})

# API：更新传承菜信息
@app.route('/api/heritage/foods/<int:food_id>', methods=['PUT'])
def update_heritage_food(food_id):
    food = HeritageFood.query.get_or_404(food_id)
    data = request.json
    food.name = data['name']
    food.description = data['description']
    food.video_url = data.get('video_url', food.video_url)
    food.chef = data['chef']
    db.session.commit()
    return jsonify({'message': '更新成功'})

# API：提交试做申请
@app.route('/api/heritage/foods/<int:food_id>/trials', methods=['POST'])
def create_trial(food_id):
    food = HeritageFood.query.get_or_404(food_id)
    data = request.json
    trial = HeritageFoodTrial(
        food_id=food_id,
        applicant=data['applicant'],
        phone=data['phone'],
        trial_date=datetime.strptime(data['trial_date'], '%Y-%m-%d'),
        remarks=data.get('remarks', '')
    )
    db.session.add(trial)
    db.session.commit()
    return jsonify({'message': '试吃申请提交成功', 'id': trial.id})

# API：获取试做记录列表
@app.route('/api/heritage/foods/<int:food_id>/trials', methods=['GET'])
def get_trials(food_id):
    trials = HeritageFoodTrial.query.filter_by(food_id=food_id).all()
    return jsonify([{
        'id': trial.id,
        'applicant': trial.applicant,
        'phone': trial.phone,
        'trial_date': trial.trial_date.strftime('%Y-%m-%d'),
        'remarks': trial.remarks,
        'status': trial.status,
        'created_at': trial.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for trial in trials])

# 路由：DIY饮品管理
@app.route('/special/diy')
def diy_index():
    return render_template('special/diy/index.html')

# API：获取DIY配料列表
@app.route('/api/diy/ingredients')
def get_diy_ingredients():
    conn = get_db_connection()
    try:
        ingredients = conn.execute('''
            SELECT *
            FROM diy_ingredients
            WHERE status = 1
            ORDER BY attribute, name
        ''').fetchall()
        
        return jsonify([dict(ing) for ing in ingredients])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# API：创建DIY饮品订单
@app.route('/api/diy/create_order', methods=['POST'])
def create_diy_order():
    data = request.json
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # 创建DIY饮品订单
        cursor.execute('''
            INSERT INTO diy_drink_orders (
                customer_name, phone, total_price,
                status, notes
            ) VALUES (?, ?, ?, ?, ?)
        ''', (
            data['customer_name'],
            data.get('phone'),
            data['total_price'],
            '待制作',
            data.get('notes', '')
        ))
        order_id = cursor.lastrowid

        # 添加配料明细
        for ingredient in data['ingredients']:
            cursor.execute('''
                INSERT INTO diy_drink_ingredients (
                    order_id, ingredient_id, quantity,
                    unit_price
                ) VALUES (?, ?, ?, ?)
            ''', (
                order_id,
                ingredient['id'],
                ingredient['quantity'],
                ingredient['price']
            ))

            # 更新配料库存
            cursor.execute('''
                UPDATE diy_ingredients
                SET stock = stock - ?
                WHERE id = ?
            ''', (ingredient['quantity'], ingredient['id']))

        conn.commit()
        return jsonify({
            'success': True,
            'order_id': order_id,
            'message': 'DIY饮品订单创建成功'
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# API：获取DIY饮品订单列表
@app.route('/api/diy/orders')
def get_diy_orders():
    conn = get_db_connection()
    try:
        orders = conn.execute('''
            SELECT 
                o.id,
                o.customer_name,
                o.total_price as price,
                o.status,
                GROUP_CONCAT(i.name) as ingredients,
                CASE WHEN o.order_id IS NOT NULL THEN 1 ELSE 0 END as synced
            FROM diy_drink_orders o
            LEFT JOIN diy_drink_ingredients di ON o.id = di.order_id
            LEFT JOIN diy_ingredients i ON di.ingredient_id = i.id
            GROUP BY o.id
            ORDER BY o.created_at DESC
        ''').fetchall()
        
        return jsonify({
            'success': True,
            'orders': [dict(order) for order in orders]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
    finally:
        conn.close()

# API：同步订单到销售系统
@app.route('/api/diy/sync_order', methods=['POST'])
def sync_order_to_sales():
    data = request.json
    conn = get_db_connection()
    try:
        # 获取订单详情
        order = conn.execute('''
            SELECT o.*, GROUP_CONCAT(i.name) as ingredients
            FROM diy_drink_orders o
            LEFT JOIN diy_drink_ingredients di ON o.id = di.order_id
            LEFT JOIN diy_ingredients i ON di.ingredient_id = i.id
            WHERE o.id = ?
            GROUP BY o.id
        ''', (data['order_id'],)).fetchone()
        
        if not order:
            return jsonify({'success': False, 'message': '订单不存在'}), 404
            
        # 准备同步到销售系统的数据
        order_data = {
            'customer_name': data['customer_name'],
            'phone': data['phone'],
            'remarks': data.get('remarks', ''),
            'amount': order['total_price'],
            'items': [{
                'name': f"DIY饮品（{order['ingredients']}）",
                'price': order['total_price'],
                'quantity': 1
            }],
            'status': 'pending',
            'type': 'diy_drink'
        }
        
        # 发送到销售系统
        response = requests.post(
            f'{SALES_API_BASE_URL}/api/orders/create',
            json=order_data
        )
        
        if not response.ok:
            raise Exception('同步到销售系统失败')
            
        # 更新本地订单状态
        sales_order = response.json()
        conn.execute('''
            UPDATE diy_drink_orders
            SET order_id = ?,
                status = '已同步'
            WHERE id = ?
        ''', (sales_order['id'], data['order_id']))
        
        conn.commit()
        return jsonify({'success': True, 'sales_order_id': sales_order['id']})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# API：更新DIY饮品订单状态
@app.route('/api/diy/update_status', methods=['POST'])
def update_diy_order_status():
    try:
        data = request.json
        conn = get_db_connection()
        try:
            # 更新订单状态
            conn.execute('''
                UPDATE diy_drink_orders
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (data['status'], data['order_id']))

            # 如果状态是"已完成"，尝试同步到销售系统
            if data['status'] == '已完成':
                try:
                    order_id = SyncManager.sync_diy_order(conn, data['order_id'])
                    message = f'订单已完成，已同步到销售系统（订单号：{order_id}）'
                except Exception as e:
                    print(f"同步到销售系统失败: {str(e)}")
                    message = '订单已完成，将稍后同步到销售系统'
            else:
                message = f'订单状态已更新为：{data["status"]}'

            conn.commit()
            return jsonify({
                'success': True,
                'message': message
            })
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# API：获取同步状态
@app.route('/api/heritage/sync/status')
def get_sync_status():
    try:
        conn = get_db_connection()
        try:
            # 获取未同步的记录数量
            pending_trials = conn.execute('''
                SELECT COUNT(*) as count
                FROM heritage_dish_trials
                WHERE sync_status = 0 AND status = '已完成'
            ''').fetchone()['count']

            pending_orders = conn.execute('''
                SELECT COUNT(*) as count
                FROM diy_drink_orders
                WHERE sync_status = 0 AND status = '已完成'
            ''').fetchone()['count']

            # 获取最近的同步失败记录
            recent_failures = conn.execute('''
                SELECT sync_type, record_id, error_message, created_at
                FROM sync_logs
                WHERE status = 'failed'
                ORDER BY created_at DESC
                LIMIT 5
            ''').fetchall()

            return jsonify({
                'success': True,
                'pending_trials': pending_trials,
                'pending_orders': pending_orders,
                'recent_failures': [dict(f) for f in recent_failures]
            })
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

def allowed_video_file(filename):
    """检查是否是允许的视频文件类型"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

def ensure_directories():
    """确保所有必要的目录都存在"""
    directories = [
        DB_DIR,
        STATIC_DIR,
        TEMPLATES_DIR,
        UPLOAD_FOLDER,
        os.path.join(STATIC_DIR, 'uploads', 'heritage', 'videos'),
        os.path.join(TEMPLATES_DIR, 'special'),
        os.path.join(TEMPLATES_DIR, 'special', 'heritage'),
        os.path.join(TEMPLATES_DIR, 'special', 'diy')
    ]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"创建目录: {directory}")

# 初始化数据库和定时任务
def init_app():
    print("开始初始化应用...")
    
    # 确保所有必要的目录存在
    ensure_directories()
    print("目录检查完成")
    
    # 初始化数据库
    with app.app_context():
        try:
            # 删除所有表
            db.drop_all()
            print("已删除所有表")
            
            # 重新创建所有表
            db.create_all()
            print("SQLAlchemy表创建完成")
            init_db()
            print("SQLite表创建完成")
        except Exception as e:
            print(f"初始化数据库时出错: {str(e)}")
            raise
    
    # 初始化定时任务
    try:
        task_manager = TaskManager(app)
        task_manager.start()
        print("定时任务启动完成")
    except Exception as e:
        print(f"启动定时任务时出错: {str(e)}")
        raise

if __name__ == '__main__':
    try:
        init_app()
        print("应用初始化完成，启动服务器...")
        # 修改端口为5003，但仅在直接运行时使用
        if not hasattr(app, 'parent_app'):
            app.run(debug=True, port=5003)
    except Exception as e:
        print(f"启动应用时出错: {str(e)}")
        raise 