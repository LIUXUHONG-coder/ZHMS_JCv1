import os
import sqlite3
import hashlib
from datetime import datetime
import time
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, Response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import xlsxwriter
import io

app = Flask(__name__)
app.secret_key = 'restaurant_management_system_secret_key'

# 确保每个请求前session中都有username
@app.before_request
def ensure_username():
    if 'username' not in session:
        # 设置默认用户名和其他必要会话信息
        session['username'] = '默认用户'
        session['logged_in'] = True  # 添加登录状态标记
        flash('使用默认用户身份访问系统', 'info')  # 提示用户
    # 确保每次请求都刷新会话时间
    session.modified = True

# 删除现有的数据库文件
# if os.path.exists('data/restaurant.db'):
#     os.remove('data/restaurant.db')

# 数据库初始化
def init_db():
    # 确保数据目录存在
    if not os.path.exists('data'):
        os.makedirs('data')
    
    # 数据库文件路径
    db_path = os.path.join('data', 'restaurant.db')
    db_exists = os.path.exists(db_path)
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 创建供应商表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        contact_person TEXT,
        contact_phone TEXT,
        address TEXT,
        supply_type TEXT,
        cooperation_start_date DATE,
        status TEXT DEFAULT '活跃',
        credit_rating TEXT DEFAULT 'B',
        remarks TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        inspection_id TEXT
    )
    ''')
    
    # 创建供应商检验表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS supplier_inspections (
        inspection_id TEXT PRIMARY KEY,
        supplier_code TEXT NOT NULL,
        supplier_name TEXT NOT NULL,
        contact_person TEXT,
        contact_phone TEXT,
        address TEXT,
        supply_type TEXT NOT NULL,
        inspection_date DATE NOT NULL,
        inspector TEXT NOT NULL,
        inspection_result TEXT DEFAULT '待检验',
        remarks TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 创建供应商评级记录表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS supplier_ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_code TEXT NOT NULL,
        rating TEXT NOT NULL,
        rating_date DATE NOT NULL,
        rater TEXT NOT NULL,
        remarks TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (supplier_code) REFERENCES suppliers (code)
    )
    ''')
    
    # 创建采购订单表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS purchase_orders (
        order_id TEXT PRIMARY KEY,
        supplier_id TEXT NOT NULL,
        order_date DATE NOT NULL,
        delivery_date DATE,
        status TEXT DEFAULT '待审核',
        total_amount DECIMAL(10,2),
        remarks TEXT,
        created_by TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (supplier_id) REFERENCES suppliers (code)
    )
    ''')
    
    # 创建采购订单明细表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS purchase_order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT NOT NULL,
        item_name TEXT NOT NULL,
        specification TEXT,
        unit TEXT,
        quantity DECIMAL(10,2) NOT NULL,
        unit_price DECIMAL(10,2) NOT NULL,
        total_price DECIMAL(10,2) NOT NULL,
        remarks TEXT,
        FOREIGN KEY (order_id) REFERENCES purchase_orders (order_id)
    )
    ''')
    
    # 创建发票表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS purchase_invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id TEXT UNIQUE NOT NULL,
        invoice_type TEXT NOT NULL,  -- '增值税专用发票' 或 '普通发票'
        invoice_code TEXT NOT NULL,
        invoice_number TEXT NOT NULL,
        invoice_date DATE NOT NULL,
        supplier_id TEXT NOT NULL,
        total_amount DECIMAL(10,2) NOT NULL,
        tax_amount DECIMAL(10,2),
        related_orders TEXT,  -- 关联的采购订单ID，多个用逗号分隔
        scan_file TEXT,  -- 发票扫描件路径
        remarks TEXT,
        status TEXT DEFAULT '待审核',  -- '待审核'、'已审核'、'已作废'
        created_by TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (supplier_id) REFERENCES suppliers (code)
    )
    ''')
    
    # 创建收据表
    cursor.execute('''
    DROP TABLE IF EXISTS purchase_receipts
    ''')

    cursor.execute('''
    CREATE TABLE purchase_receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_type TEXT NOT NULL,
        receipt_number TEXT NOT NULL,
        receipt_date DATE NOT NULL,
        amount DECIMAL(10,2) NOT NULL,
        payment_method TEXT NOT NULL,
        purpose TEXT NOT NULL,
        remarks TEXT,
        scan_file TEXT,
        status TEXT DEFAULT '待确认',
        created_by TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_by TEXT,
        updated_at TIMESTAMP,
        receipt_party_type TEXT NOT NULL,
        receipt_party_id TEXT,
        receipt_party_name TEXT,
        issuing_party_type TEXT NOT NULL,
        issuing_party_id TEXT,
        issuing_party_name TEXT
    )
    ''')
    
    # 如果是新数据库，创建默认管理员账户
    if not db_exists:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                      ('admin', 'admin123', 'admin'))
    
    # 提交事务
    conn.commit()
    conn.close()
    
    return not db_exists

# 初始化数据库
init_db()

def get_db_connection():
    try:
        db_path = os.path.join('data', 'restaurant.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        raise

@app.route('/')
def home():
    return render_template('purchase/index.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('您已退出登录', 'success')
    return redirect(url_for('home'))

# 各个子系统的路由
@app.route('/purchase')
def purchase():
    return render_template('purchase/index.html')

@app.route('/purchase/supplier')
def purchase_supplier():
    # 连接数据库获取供应商列表
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 使查询结果以字典形式返回
    cursor = conn.cursor()
    
    # 获取筛选参数
    supply_type = request.args.get('supply_type', '')
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    
    # 构建查询语句
    query = "SELECT * FROM suppliers WHERE 1=1"
    params = []
    
    if supply_type:
        query += " AND supply_type = ?"
        params.append(supply_type)
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    if search:
        query += " AND (name LIKE ? OR code LIKE ? OR contact_person LIKE ?)"
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term])
    
    query += " ORDER BY id DESC"
    
    cursor.execute(query, params)
    suppliers = cursor.fetchall()
    
    # 获取供应商类型列表用于筛选
    cursor.execute("SELECT DISTINCT supply_type FROM suppliers ORDER BY supply_type")
    supply_types = [row['supply_type'] for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('purchase/supplier.html', 
                          suppliers=suppliers,
                          supply_types=supply_types,
                          current_supply_type=supply_type,
                          current_status=status,
                          search=search)

@app.route('/purchase/supplier/add', methods=['GET', 'POST'])
def add_supplier():
    # 添加调试输出
    print("*** 访问 add_supplier 函数 ***")
    print(f"请求方法: {request.method}")
    print(f"会话用户: {session.get('username', '无用户')}")
    
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if request.method == 'POST':
        # 获取表单数据
        inspection_id = request.form['inspection_id']
        
        # 首先检查检验记录是否存在且通过
        cursor.execute("""
            SELECT * FROM supplier_inspections 
            WHERE inspection_id = ? AND inspection_result = '通过'
        """, (inspection_id,))
        inspection = cursor.fetchone()
        
        if not inspection:
            flash('无法添加供应商：未找到通过的检验记录！', 'danger')
            conn.close()
            return redirect(url_for('purchase_supplier'))
        
        # 检查供应商编码是否已存在
        code = inspection['supplier_code']
        cursor.execute("SELECT * FROM suppliers WHERE code = ?", (code,))
        existing_supplier = cursor.fetchone()
        
        if existing_supplier:
            # 编码存在但名称不同 - 这是编码冲突的情况
            if existing_supplier['name'] != inspection['supplier_name']:
                flash(f'供应商编码冲突: 编码 {code} 已被供应商 "{existing_supplier["name"]}" 使用，但检验记录中是 "{inspection["supplier_name"]}"', 'danger')
                flash('请先修正检验记录中的编码，确保每个供应商有唯一的编码', 'warning')
            else:
                flash(f'供应商 "{inspection["supplier_name"]}" 已存在！', 'danger')
            
            conn.close()
            return redirect(url_for('purchase_supplier'))
        
        try:
            # 从检验记录中获取供应商信息
            cursor.execute("""
                INSERT INTO suppliers (
                    code, name, contact_person, contact_phone, address, 
                    supply_type, cooperation_start_date, status, 
                    credit_rating, remarks, inspection_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                inspection['supplier_code'],
                inspection['supplier_name'],
                inspection['contact_person'],
                inspection['contact_phone'],
                inspection['address'],
                inspection['supply_type'],
                datetime.now().strftime('%Y-%m-%d'),  # 合作开始日期默认为当前日期
                '活跃',  # 默认状态为活跃
                'B',    # 默认信用评级为B
                f'通过检验ID: {inspection_id}',  # 备注包含检验ID
                inspection_id
            ))
            
            conn.commit()
            flash('供应商添加成功！', 'success')
            
        except sqlite3.IntegrityError as e:
            flash(f'供应商添加失败(完整性错误): {str(e)}', 'danger')
        except Exception as e:
            flash(f'添加失败: {str(e)}', 'danger')
        finally:
            conn.close()
            
        return redirect(url_for('purchase_supplier'))
    
    # 获取所有通过检验但尚未添加为供应商的记录
    cursor.execute("""
        SELECT si.* 
        FROM supplier_inspections si 
        LEFT JOIN suppliers s ON si.supplier_code = s.code
        WHERE si.inspection_result = '通过'
        AND s.code IS NULL
        ORDER BY si.inspection_date DESC
    """)
    available_inspections = cursor.fetchall()
    
    # 获取已添加的供应商列表（用于显示）
    cursor.execute("""
        SELECT s.*, si.inspection_date
        FROM suppliers s
        LEFT JOIN supplier_inspections si ON s.inspection_id = si.inspection_id
        ORDER BY s.created_at DESC
    """)
    existing_suppliers = cursor.fetchall()
    
    # 统计数据
    available_count = len(available_inspections)
    added_count = len(existing_suppliers)
    
    # 如果没有可添加的供应商，显示提示
    if available_count == 0:
        flash('没有可添加的供应商，所有通过检验的供应商都已添加。', 'info')
    else:
        flash(f'发现 {available_count} 个可添加的供应商', 'success')
    
    conn.close()
    
    try:
        return render_template('purchase/add_supplier.html', 
                         username=session['username'],
                         available_inspections=available_inspections,
                         existing_suppliers=existing_suppliers,
                         available_count=available_count,
                         added_count=added_count)
    except Exception as e:
        print(f"渲染模板错误: {str(e)}")
        flash(f"显示供应商添加界面失败: {str(e)}", "danger")
        return redirect(url_for('purchase_supplier'))

@app.route('/purchase/supplier/view/<code>')
def view_supplier(code):
    # 连接数据库获取供应商详情
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM suppliers WHERE code = ?", (code,))
    supplier = cursor.fetchone()
    
    conn.close()
    
    if not supplier:
        flash('供应商不存在！', 'danger')
        return redirect(url_for('purchase_supplier'))
    
    return render_template('purchase/view_supplier.html', 
                           username=session['username'], 
                           supplier=supplier)

@app.route('/purchase/supplier/edit/<code>', methods=['GET', 'POST'])
def edit_supplier(code):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if request.method == 'POST':
        # 获取表单数据
        name = request.form['name']
        contact_person = request.form['contact_person']
        contact_phone = request.form['contact_phone']
        address = request.form['address']
        supply_type = request.form['supply_type']
        cooperation_start_date = request.form['cooperation_start_date']
        status = request.form['status']
        credit_rating = request.form['credit_rating']
        remarks = request.form['remarks']
        
        try:
            cursor.execute(
                "UPDATE suppliers SET name=?, contact_person=?, contact_phone=?, address=?, supply_type=?, cooperation_start_date=?, status=?, credit_rating=?, remarks=?, updated_at=CURRENT_TIMESTAMP WHERE code=?",
                (name, contact_person, contact_phone, address, supply_type, cooperation_start_date, status, credit_rating, remarks, code)
            )
            conn.commit()
            flash('供应商信息更新成功！', 'success')
        except Exception as e:
            flash(f'更新失败: {str(e)}', 'danger')
        finally:
            conn.close()
            
        return redirect(url_for('purchase_supplier'))
    
    # 获取供应商信息
    cursor.execute("SELECT * FROM suppliers WHERE code = ?", (code,))
    supplier = cursor.fetchone()
    
    conn.close()
    
    if not supplier:
        flash('供应商不存在！', 'danger')
        return redirect(url_for('purchase_supplier'))
    
    return render_template('purchase/edit_supplier.html', 
                           username=session['username'], 
                           supplier=supplier)

@app.route('/purchase/supplier/delete/<code>', methods=['POST'])
def delete_supplier(code):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 删除供应商
        cursor.execute("DELETE FROM suppliers WHERE code = ?", (code,))
        conn.commit()
        flash('供应商删除成功！', 'success')
    except Exception as e:
        flash(f'删除失败: {str(e)}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('purchase_supplier'))

@app.route('/purchase/inspect')
def purchase_inspect():
    # 获取筛选参数
    search = request.args.get('search', '')
    inspection_type = request.args.get('inspection_type', '')
    result = request.args.get('result', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 构建查询条件
    query = """
    SELECT si.*, 
           CASE 
               WHEN sc.status = '有效' THEN '已签订'
               WHEN sc.status = '已过期' OR sc.status = '已终止' THEN '已失效'
               ELSE '未签订'
           END as contract_status
    FROM supplier_inspections si
    LEFT JOIN suppliers s ON si.supplier_code = s.code
    LEFT JOIN supplier_contracts sc ON s.code = sc.supplier_code AND sc.status != '已取消'
    WHERE 1=1
    """
    params = []
    
    if search:
        query += " AND (si.supplier_name LIKE ? OR si.supplier_code LIKE ? OR si.inspection_id LIKE ?)"
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term])
    
    if inspection_type:
        query += " AND si.inspection_type = ?"
        params.append(inspection_type)
    
    if result:
        query += " AND si.inspection_result = ?"
        params.append(result)
    
    if date_from:
        query += " AND si.inspection_date >= ?"
        params.append(date_from)
    
    if date_to:
        query += " AND si.inspection_date <= ?"
        params.append(date_to)
    
    query += " ORDER BY si.created_at DESC"
    
    cursor.execute(query, params)
    inspections = cursor.fetchall()
    
    conn.close()
    
    return render_template('purchase/inspect.html', 
                           username=session['username'],
                           inspections=inspections,
                           search=search,
                           inspection_type=inspection_type,
                           result=result,
                           date_from=date_from,
                           date_to=date_to)

@app.route('/purchase/inspect/new', methods=['GET', 'POST'])
def new_inspection():
    if request.method == 'POST':
        # 获取表单数据
        inspection_id = request.form['inspection_id']
        supplier_code = request.form['supplier_code']
        supplier_name = request.form['supplier_name']
        inspection_date = request.form['inspection_date']
        inspection_type = request.form['inspection_type']
        contact_person = request.form['contact_person']
        contact_phone = request.form['contact_phone']
        address = request.form['address']
        supply_type = request.form['supply_type']
        product_categories = request.form['product_categories']
        inspection_notes = request.form['inspection_notes']
        
        # 连接数据库
        db_path = os.path.join('data', 'restaurant.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            # 获取表单中的产品检验项
            product_names = request.form.getlist('product_name[]')
            product_specs = request.form.getlist('product_spec[]')
            quality_scores = request.form.getlist('quality_score[]')
            price_scores = request.form.getlist('price_score[]')
            quality_notes = request.form.getlist('quality_notes[]')
            price_notes = request.form.getlist('price_notes[]')
            conclusions = request.form.getlist('conclusion[]')
            
            # 计算总体检验结果
            total_items = len([c for c in conclusions if c])  # 有效的检验项数量
            passed_items = len([c for c in conclusions if c == '合格'])  # 通过的检验项数量
            
            # 确定最终检验结果
            # 如果所有检验项都通过，则整体检验通过
            # 如果有任何一个检验项未通过，则整体检验不通过
            inspection_result = '合格' if total_items > 0 and passed_items == total_items else '不合格'
            
            # 插入供应商调研记录
            cursor.execute('''
            INSERT INTO supplier_inspections (
                inspection_id, supplier_code, supplier_name, inspection_date, inspection_type,
                contact_person, contact_phone, address, supply_type, product_categories, 
                inspection_notes, inspector, inspection_result, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                inspection_id, supplier_code, supplier_name, inspection_date, inspection_type,
                contact_person, contact_phone, address, supply_type, product_categories,
                inspection_notes, session['username'], inspection_result
            ))
            
            # 插入产品检验项
            for i in range(len(product_names)):
                if product_names[i]:  # 只处理有产品名称的项
                    cursor.execute('''
                    INSERT INTO inspection_items (
                        inspection_id, product_name, product_spec, quality_score, price_reasonability,
                        quality_notes, price_notes, conclusion
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        inspection_id, product_names[i], product_specs[i], 
                        quality_scores[i] if quality_scores[i] else None,
                        price_scores[i] if price_scores[i] else None,
                        quality_notes[i], price_notes[i], conclusions[i]
                    ))
            
            conn.commit()
            flash('产品检验记录已添加！', 'success')
            return redirect(url_for('view_inspection', inspection_id=inspection_id))
            
        except sqlite3.IntegrityError:
            flash('检验编号已存在，请使用其他编号！', 'danger')
        except Exception as e:
            flash(f'添加失败: {str(e)}', 'danger')
        finally:
            conn.close()
    
    # 生成新的检验编号
    current_date = datetime.now().strftime('%Y%m%d')
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT MAX(inspection_id) FROM supplier_inspections WHERE inspection_id LIKE ?", (f'INSP{current_date}%',))
    max_id = cursor.fetchone()[0]
    
    if max_id:
        # 提取序号并加1
        seq_num = int(max_id[-3:]) + 1
        new_inspection_id = f'INSP{current_date}{seq_num:03d}'
    else:
        # 如果当天没有检验，从001开始
        new_inspection_id = f'INSP{current_date}001'
    
    conn.close()
    
    return render_template('purchase/create_inspection.html',
                           username=session['username'],
                           new_inspection_id=new_inspection_id,
                           current_date=datetime.now().strftime('%Y-%m-%d'))

@app.route('/purchase/inspect/view/<inspection_id>')
def view_inspection(inspection_id):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取检验信息
    cursor.execute("SELECT * FROM supplier_inspections WHERE inspection_id = ?", (inspection_id,))
    inspection = cursor.fetchone()
    
    if not inspection:
        conn.close()
        flash('产品检验记录不存在！', 'danger')
        return redirect(url_for('purchase_inspect'))
    
    # 获取检验项
    cursor.execute("SELECT * FROM inspection_items WHERE inspection_id = ? ORDER BY id", (inspection_id,))
    items = cursor.fetchall()
    
    conn.close()
    
    return render_template('purchase/view_inspection.html',
                           username=session['username'],
                           inspection=inspection,
                           items=items)

@app.route('/purchase/inspect/update_result/<inspection_id>', methods=['POST'])
def update_inspection_result(inspection_id):
    result = request.form.get('result')
    
    if not result or result not in ['合格', '不合格']:
        flash('无效的检验结果！', 'danger')
        return redirect(url_for('view_inspection', inspection_id=inspection_id))
    
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        UPDATE supplier_inspections 
        SET inspection_result = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE inspection_id = ?
        ''', (result, inspection_id))
        
        conn.commit()
        flash(f'检验结果已更新为"{result}"！', 'success')
    except Exception as e:
        flash(f'更新失败: {str(e)}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('view_inspection', inspection_id=inspection_id))

# 附件上传处理
@app.route('/purchase/inspect/upload_attachment/<inspection_id>', methods=['POST'])
def upload_attachment(inspection_id):
        # 检查检验记录是否存在
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM supplier_inspections WHERE inspection_id = ?", (inspection_id,))
    inspection = cursor.fetchone()
    
    if not inspection:
        conn.close()
        return jsonify({"status": "error", "message": "检验记录不存在"}), 404
    
    # 处理上传的文件
    if 'attachment' not in request.files:
        conn.close()
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    
    file = request.files['attachment']
    
    if file.filename == '':
        conn.close()
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    
    if file:
        try:
            # 创建上传目录
            upload_dir = os.path.join('static', 'uploads', 'inspections', inspection_id)
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
            
            # 确保文件名安全
            filename = secure_filename(file.filename)
            
            # 添加时间戳避免重名
            filename_parts = os.path.splitext(filename)
            timestamped_filename = f"{filename_parts[0]}_{int(time.time())}{filename_parts[1]}"
            
            file_path = os.path.join(upload_dir, timestamped_filename)
            file.save(file_path)
            
            # 获取文件信息
            file_size = os.path.getsize(file_path)
            file_size_str = format_file_size(file_size)
            
            # 保存附件信息到数据库
            relative_path = os.path.join('uploads', 'inspections', inspection_id, timestamped_filename)
            
            cursor.execute('''
            INSERT INTO inspection_attachments (
                inspection_id, file_name, file_path, file_type, file_size, uploader
            ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                inspection_id, 
                filename, 
                relative_path, 
                file.content_type, 
                file_size_str, 
                session['username']
            ))
            
            conn.commit()
            conn.close()
            
            return jsonify({"status": "success", "message": "附件上传成功"})
            
        except Exception as e:
            conn.close()
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "error", "message": "上传失败"}), 400

# 获取附件列表
@app.route('/purchase/inspect/get_attachments/<inspection_id>')
def get_attachments(inspection_id):
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 检查检验记录是否存在
    cursor.execute("SELECT * FROM supplier_inspections WHERE inspection_id = ?", (inspection_id,))
    inspection = cursor.fetchone()
    
    if not inspection:
        conn.close()
        return jsonify({"status": "error", "message": "检验记录不存在"}), 404
    
    # 获取附件列表
    cursor.execute('''
    SELECT * FROM inspection_attachments 
    WHERE inspection_id = ? 
    ORDER BY uploaded_at DESC
    ''', (inspection_id,))
    
    attachments = []
    for row in cursor.fetchall():
        attachments.append({
            "id": row['id'],
            "file_name": row['file_name'],
            "file_type": row['file_type'],
            "file_size": row['file_size'],
            "uploader": row['uploader'],
            "uploaded_at": row['uploaded_at']
        })
    
    conn.close()
    return jsonify({"status": "success", "attachments": attachments})

# 下载附件
@app.route('/purchase/inspect/download_attachment/<int:attachment_id>')
def download_attachment(attachment_id):
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取附件信息
    cursor.execute("SELECT * FROM inspection_attachments WHERE id = ?", (attachment_id,))
    attachment = cursor.fetchone()
    
    if not attachment:
        conn.close()
        flash('附件不存在！', 'danger')
        return redirect(url_for('purchase_inspect'))
    
    file_path = os.path.join('static', attachment['file_path'])
    
    if not os.path.exists(file_path):
        conn.close()
        flash('文件不存在！', 'danger')
        return redirect(url_for('view_inspection', inspection_id=attachment['inspection_id']))
    
    conn.close()
    return send_file(file_path, download_name=attachment['file_name'], as_attachment=True)

@app.route('/purchase/inspect/delete_attachment/<int:attachment_id>', methods=['POST'])
def delete_attachment(attachment_id):
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取附件信息
    cursor.execute("SELECT * FROM inspection_attachments WHERE id = ?", (attachment_id,))
    attachment = cursor.fetchone()
    
    if not attachment:
        conn.close()
        return jsonify({"status": "error", "message": "附件不存在"}), 404
    
    file_path = os.path.join('static', attachment['file_path'])
    
    try:
        # 删除数据库记录
        cursor.execute("DELETE FROM inspection_attachments WHERE id = ?", (attachment_id,))
        conn.commit()
        
        # 删除文件
        if os.path.exists(file_path):
            os.remove(file_path)
        
        conn.close()
        return jsonify({"status": "success", "message": "附件已删除"})
    
    except Exception as e:
        conn.close()
        return jsonify({"status": "error", "message": str(e)}), 500

# 供应商评级相关路由
@app.route('/purchase/supplier/handle_rating/<code>', methods=['POST'])
def handle_supplier_rating(code):
    rating = request.form.get('rating')
    reason = request.form.get('reason')
    
    if not rating or rating not in ['A', 'B', 'C', 'D', 'E']:
        flash('无效的评级！', 'danger')
        return redirect(url_for('view_supplier', code=code))
    
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # 更新供应商评级
        cursor.execute('''
        UPDATE suppliers 
        SET credit_rating = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE code = ?
        ''', (rating, code))
        
        # 添加评级历史记录
        current_date = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
        INSERT INTO supplier_rating_history (
            supplier_code, rating, rating_date, reason, created_by
        ) VALUES (?, ?, ?, ?, ?)
        ''', (code, rating, current_date, reason, session['username']))
        
        conn.commit()
        
        # 检查评级是否为C或以下
        if rating in ['C', 'D', 'E']:
            # 获取供应商信息
            cursor.execute("SELECT * FROM suppliers WHERE code = ?", (code,))
            supplier = cursor.fetchone()
            
            # 获取最近的检验
            cursor.execute('''
            SELECT * FROM supplier_inspections 
            WHERE supplier_code = ? 
            ORDER BY created_at DESC LIMIT 1
            ''', (code,))
            inspection = cursor.fetchone()
            
            if inspection:
                # 重定向到检验页面并显示通知
                inspection_id = inspection['inspection_id']
                conn.close()
                
                # 如果是D或E评级，将供应商状态改为非活跃
                if rating in ['D', 'E']:
                    # 重新连接以更新状态
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE suppliers SET status = '非活跃' WHERE code = ?", (code,))
                    conn.commit()
                    conn.close()
                    
                    flash(f'供应商状态已更新为"非活跃"，评级为{rating}级已触发重新检验流程', 'warning')
                else:
                    flash(f'供应商评级为{rating}级，请关注供应商质量', 'warning')
                
                return redirect(url_for('view_inspection', inspection_id=inspection_id, rating_notification=True, rating=rating))
            else:
                # 创建新的检验记录
                conn.close()
                flash(f'供应商评级为{rating}级，请创建新的检验记录', 'warning')
                return redirect(url_for('new_inspection'))
        
        conn.close()
        flash(f'供应商评级已更新为{rating}级！', 'success')
        return redirect(url_for('view_supplier', code=code))
    
    except Exception as e:
        conn.close()
        flash(f'更新失败: {str(e)}', 'danger')
        return redirect(url_for('view_supplier', code=code))

# 辅助函数
def format_file_size(size_bytes):
    """将字节数格式化为人类可读的文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.1f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.1f} GB"

@app.route('/purchase/contract')
def supplier_contracts():
    # 获取筛选参数
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 构建查询条件
    query = """
    SELECT sc.*, s.name as supplier_name
    FROM supplier_contracts sc
    LEFT JOIN suppliers s ON sc.supplier_code = s.code
    WHERE 1=1
    """
    params = []
    
    if search:
        query += " AND (sc.contract_id LIKE ? OR s.name LIKE ? OR sc.supplier_code LIKE ?)"
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term])
    
    if status:
        query += " AND sc.status = ?"
        params.append(status)
    
    query += " ORDER BY sc.created_at DESC"
    
    cursor.execute(query, params)
    contracts = cursor.fetchall()
    
    conn.close()
    
    return render_template('purchase/contracts.html',
                           username=session['username'],
                           contracts=contracts,
                           search=search,
                           status=status)

@app.route('/purchase/contract/new', methods=['GET', 'POST'])
def new_contract():
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取已通过检验的供应商列表
    cursor.execute('''
    SELECT si.*, s.code as existing_code
    FROM supplier_inspections si
    LEFT JOIN suppliers s ON si.supplier_code = s.code
    WHERE si.inspection_result = '通过'
    ORDER BY si.supplier_name
    ''')
    inspections = cursor.fetchall()
    
    if request.method == 'POST':
        # 获取表单数据
        contract_id = request.form['contract_id']
        supplier_code = request.form['supplier_code']
        inspection_id = request.form['inspection_id']
        contract_date = request.form['contract_date']
        effective_date = request.form['effective_date']
        expiry_date = request.form['expiry_date']
        contract_type = request.form['contract_type']
        contract_terms = request.form['contract_terms']
        
        # 处理文件上传
        file_path = None
        file_type = None
        original_filename = None
        if 'contract_file' in request.files:
            file = request.files['contract_file']
            if file and file.filename:
                # 确保上传目录存在
                upload_dir = os.path.join('static', 'uploads', 'contracts')
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)
                
                # 获取原始文件名和扩展名
                original_filename = secure_filename(file.filename)
                file_type = os.path.splitext(original_filename)[1]
                # 使用合同ID和原始扩展名构造新文件名
                filename = f"{contract_id}{file_type}"
                # 保存文件
                filename = f"{contract_id}_{secure_filename(file.filename)}"
                file_path = os.path.join(upload_dir, filename)
                file.save(file_path)
                # 存储相对路径
                file_path = os.path.join('uploads', 'contracts', filename)
        
        try:
            # 开始事务
            cursor.execute("BEGIN TRANSACTION")
            
            # 插入合同记录
            cursor.execute('''
            INSERT INTO supplier_contracts (
                contract_id, supplier_code, contract_date, effective_date, expiry_date,
                contract_type, contract_terms, file_path, status, creator, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                contract_id, supplier_code, contract_date, effective_date, expiry_date,
                contract_type, contract_terms, file_path, '有效', session['username']
            ))
            
            # 检查供应商是否已存在
            cursor.execute("SELECT code FROM suppliers WHERE code = ?", (supplier_code,))
            existing_supplier = cursor.fetchone()
            
            if not existing_supplier:
                # 获取检验记录
                cursor.execute("SELECT * FROM supplier_inspections WHERE inspection_id = ?", (inspection_id,))
                inspection = cursor.fetchone()
                
                if inspection:
                    # 创建新供应商
                    cursor.execute('''
                    INSERT INTO suppliers (
                        code, name, contact_person, contact_phone, address, supply_type,
                        cooperation_start_date, status, remarks, inspection_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        supplier_code, inspection['supplier_name'], inspection['contact_person'],
                        inspection['contact_phone'], inspection['address'], inspection['supply_type'],
                        effective_date, '活跃', f'通过检验ID: {inspection_id}', inspection_id
                    ))
                else:
                    cursor.execute("ROLLBACK")
                    conn.close()
                    flash('无法找到相关的检验记录！', 'danger')
                    return redirect(url_for('new_contract'))
            
            # 提交事务
            cursor.execute("COMMIT")
            flash('供应商合同已添加！', 'success')
            return redirect(url_for('supplier_contracts'))
            
        except sqlite3.IntegrityError:
            cursor.execute("ROLLBACK")
            flash('合同ID已存在或供应商代码无效！', 'danger')
        except Exception as e:
            cursor.execute("ROLLBACK")
            flash(f'添加失败: {str(e)}', 'danger')
        finally:
            conn.close()
    else:
        # 生成新的合同编号
        current_date = datetime.now().strftime('%Y%m%d')
        cursor.execute("SELECT MAX(contract_id) FROM supplier_contracts WHERE contract_id LIKE ?", (f'CT{current_date}%',))
        max_id = cursor.fetchone()[0]
        
        if max_id:
            # 提取序号并加1
            seq_num = int(max_id[-3:]) + 1
            new_contract_id = f'CT{current_date}{seq_num:03d}'
        else:
            # 如果当天没有合同，从001开始
            new_contract_id = f'CT{current_date}001'
        
        conn.close()
        
        return render_template('purchase/create_contract.html',
                            username=session['username'],
                            inspections=inspections,
                            new_contract_id=new_contract_id,
                            current_date=datetime.now().strftime('%Y-%m-%d'))

@app.route('/purchase/contract/view/<contract_id>')
def view_contract(contract_id):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取合同信息
    cursor.execute('''
    SELECT sc.*, s.name as supplier_name
    FROM supplier_contracts sc
    LEFT JOIN suppliers s ON sc.supplier_code = s.code
    WHERE sc.contract_id = ?
    ''', (contract_id,))
    contract = cursor.fetchone()
    
    if not contract:
        conn.close()
        flash('合同不存在！', 'danger')
        return redirect(url_for('supplier_contracts'))
    
    conn.close()
    
    return render_template('purchase/view_contract.html',
                           username=session['username'],
                           contract=contract)

@app.route('/purchase/contract/download/<contract_id>')
def download_contract(contract_id):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取合同文件路径
    cursor.execute("SELECT file_path FROM supplier_contracts WHERE contract_id = ?", (contract_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if not result or not result['file_path']:
        flash('合同文件不存在！', 'danger')
        return redirect(url_for('view_contract', contract_id=contract_id))
    
    file_path = os.path.join('static', result['file_path'])
    return send_file(file_path, as_attachment=True)

@app.route('/purchase/unified')
def purchase_unified():
    # 获取筛选参数
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # 连接数据库获取采购单列表
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 构建查询条件
    query = """
    SELECT po.*, 
           COUNT(poi.id) as items_count, 
           COALESCE(SUM(poi.total_price), 0) as total_amount,
           s.name as supplier_name,
           strftime('%Y-%m-%d %H:%M:%S', po.created_at, 'localtime') as formatted_created_at
    FROM purchase_orders po
    LEFT JOIN purchase_order_items poi ON po.order_id = poi.order_id
    LEFT JOIN suppliers s ON po.supplier_id = s.code
    WHERE 1=1
    """
    params = []
    
    if search:
        query += " AND (po.order_id LIKE ? OR s.name LIKE ? OR po.remarks LIKE ?)"
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term])
    
    if status:
        query += " AND po.status = ?"
        params.append(status)
    
    if date_from:
        query += " AND po.order_date >= ?"
        params.append(date_from)
    
    if date_to:
        query += " AND po.order_date <= ?"
        params.append(date_to)
    
    query += " GROUP BY po.order_id ORDER BY po.created_at DESC"
    
    cursor.execute(query, params)
    purchase_orders = cursor.fetchall()
    
    conn.close()
    
    return render_template('purchase/unified.html', 
                          username=session['username'],
                          purchase_orders=purchase_orders,
                          search=search,
                          status=status,
                          date_from=date_from,
                          date_to=date_to)

@app.route('/purchase/unified/new', methods=['GET', 'POST'])
def new_purchase_order():
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取供应商列表
    cursor.execute("SELECT * FROM suppliers WHERE status = '活跃' ORDER BY name")
    suppliers = cursor.fetchall()
    
    if request.method == 'POST':
        # 获取表单数据 - 采购单基本信息
        order_id = request.form['order_id']
        supplier_id = request.form['supplier_id']
        order_date = request.form['order_date']
        expected_delivery_date = request.form['expected_delivery_date']
        payment_terms = request.form['payment_terms']
        shipping_method = request.form['shipping_method']
        remarks = request.form['remarks']
        status = '草稿' if 'save_draft' in request.form else '已提交'
        
        try:
            # 插入采购单
            cursor.execute('''
            INSERT INTO purchase_orders (
                order_id, supplier_id, order_date, expected_delivery_date, 
                payment_terms, shipping_method, remarks, status, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                order_id, supplier_id, order_date, expected_delivery_date,
                payment_terms, shipping_method, remarks, status, session['username']
            ))
            
            # 获取表单中的采购项
            item_codes = request.form.getlist('item_code[]')
            item_names = request.form.getlist('item_name[]')
            item_types = request.form.getlist('item_type[]')  # 新增：获取物资类型
            quantities = request.form.getlist('quantity[]')
            units = request.form.getlist('unit[]')
            unit_prices = request.form.getlist('unit_price[]')
            total_prices = request.form.getlist('total_price[]')
            item_remarks = request.form.getlist('item_remarks[]')
            
            # 插入采购单项
            for i in range(len(item_codes)):
                if item_codes[i] and item_names[i] and quantities[i]:
                    cursor.execute('''
                    INSERT INTO purchase_order_items (
                        order_id, item_code, item_name, item_type, quantity, unit, 
                        unit_price, total_price, remarks
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        order_id, item_codes[i], item_names[i], item_types[i] or '其他', quantities[i], units[i],
                        unit_prices[i], total_prices[i], item_remarks[i]
                    ))
            
            conn.commit()
            conn.close()
            flash('采购单已' + ('保存为草稿' if status == '草稿' else '提交') + '！', 'success')
            return redirect(url_for('purchase_unified'))
            
        except sqlite3.IntegrityError:
            flash('采购单号已存在，请使用其他编号！', 'danger')
        except Exception as e:
            flash(f'操作失败: {str(e)}', 'danger')
        # 注意：这里不关闭连接，因为下面还需要使用
    
    # 生成新的采购单号
    current_date = datetime.now().strftime('%Y%m%d')
    cursor.execute("SELECT MAX(order_id) FROM purchase_orders WHERE order_id LIKE ?", (f'PO{current_date}%',))
    max_order_id = cursor.fetchone()[0]
    
    if max_order_id:
        # 提取序号并加1
        seq_num = int(max_order_id[-3:]) + 1
        new_order_id = f'PO{current_date}{seq_num:03d}'
    else:
        # 如果当天没有订单，从001开始
        new_order_id = f'PO{current_date}001'
    
    # 现在可以安全地关闭连接
    conn.close()
    
    # 定义物资类型
    item_categories = [
        '肉禽类', '蔬菜类', '香料类', '调味品',
        '主食类', '豆制品蛋奶', '菌菇类', '其他'
    ]
    
    return render_template('purchase/create_order.html',
                          username=session['username'],
                          suppliers=suppliers,
                          new_order_id=new_order_id,
                          current_date=datetime.now().strftime('%Y-%m-%d'),
                          item_categories=item_categories)

@app.route('/purchase/unified/view/<order_id>')
def view_purchase_order(order_id):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取采购单信息
    cursor.execute('''
    SELECT po.*, s.name as supplier_name, s.contact_person, s.contact_phone
    FROM purchase_orders po
    JOIN suppliers s ON po.supplier_id = s.code
    WHERE po.order_id = ?
    ''', (order_id,))
    order = cursor.fetchone()
    
    if not order:
        conn.close()
        flash('采购单不存在！', 'danger')
        return redirect(url_for('purchase_unified'))
    
    # 获取采购单项
    cursor.execute('''
    SELECT * FROM purchase_order_items 
    WHERE order_id = ? 
    ORDER BY id
    ''', (order_id,))
    order_items = cursor.fetchall()
    
    # 计算总金额
    cursor.execute('''
    SELECT COALESCE(SUM(total_price), 0) as total_amount 
    FROM purchase_order_items 
    WHERE order_id = ?
    ''', (order_id,))
    total = cursor.fetchone()
    total_amount = total['total_amount']
    
    conn.close()
    
    return render_template('purchase/view_order.html',
                          username=session['username'],
                          order=order,
                          order_items=order_items,
                          total_amount=total_amount)

@app.route('/purchase/unified/edit/<order_id>', methods=['GET', 'POST'])
def edit_purchase_order(order_id):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取采购单信息
    cursor.execute("SELECT * FROM purchase_orders WHERE order_id = ?", (order_id,))
    order = cursor.fetchone()
    
    if not order:
        conn.close()
        flash('采购单不存在！', 'danger')
        return redirect(url_for('purchase_unified'))
    
    # 检查订单状态，只有草稿状态才能编辑
    if order['status'] != '草稿':
        conn.close()
        flash('只能编辑草稿状态的采购单！', 'warning')
        return redirect(url_for('view_purchase_order', order_id=order_id))
    
    # 获取供应商列表
    cursor.execute("SELECT * FROM suppliers WHERE status = '活跃' ORDER BY name")
    suppliers = cursor.fetchall()
    
    # 获取采购单项
    cursor.execute("SELECT * FROM purchase_order_items WHERE order_id = ? ORDER BY id", (order_id,))
    order_items = cursor.fetchall()
    
    if request.method == 'POST':
        # 获取表单数据 - 采购单基本信息
        supplier_id = request.form['supplier_id']
        order_date = request.form['order_date']
        expected_delivery_date = request.form['expected_delivery_date']
        payment_terms = request.form['payment_terms']
        shipping_method = request.form['shipping_method']
        remarks = request.form['remarks']
        status = '草稿' if 'save_draft' in request.form else '已提交'
        
        try:
            # 更新采购单
            cursor.execute('''
            UPDATE purchase_orders SET 
                supplier_id = ?, order_date = ?, expected_delivery_date = ?, 
                payment_terms = ?, shipping_method = ?, remarks = ?, status = ?,
                updated_at = CURRENT_TIMESTAMP, updated_by = ?
            WHERE order_id = ?
            ''', (
                supplier_id, order_date, expected_delivery_date,
                payment_terms, shipping_method, remarks, status,
                session['username'], order_id
            ))
            
            # 删除原有的采购单项
            cursor.execute("DELETE FROM purchase_order_items WHERE order_id = ?", (order_id,))
            
            # 获取表单中的采购项
            item_codes = request.form.getlist('item_code[]')
            item_names = request.form.getlist('item_name[]')
            quantities = request.form.getlist('quantity[]')
            units = request.form.getlist('unit[]')
            unit_prices = request.form.getlist('unit_price[]')
            total_prices = request.form.getlist('total_price[]')
            item_remarks = request.form.getlist('item_remarks[]')
            
            # 插入采购单项
            for i in range(len(item_codes)):
                if item_codes[i] and item_names[i] and quantities[i]:
                    cursor.execute('''
                    INSERT INTO purchase_order_items (
                        order_id, item_code, item_name, item_type, quantity, unit, 
                        unit_price, total_price, remarks
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        order_id, item_codes[i], item_names[i], '其他', quantities[i], units[i],
                        unit_prices[i], total_prices[i], item_remarks[i]
                    ))
            
            conn.commit()
            flash('采购单已' + ('保存为草稿' if status == '草稿' else '提交') + '！', 'success')
            return redirect(url_for('purchase_unified'))
            
        except Exception as e:
            flash(f'操作失败: {str(e)}', 'danger')
        finally:
            conn.close()
    
    conn.close()
    
    return render_template('purchase/edit_order.html',
                          username=session['username'],
                          suppliers=suppliers,
                          order=order,
                          order_items=order_items)

@app.route('/purchase/unified/delete/<order_id>', methods=['POST'])
def delete_purchase_order(order_id):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查订单是否存在
        cursor.execute("SELECT status FROM purchase_orders WHERE order_id = ?", (order_id,))
        order = cursor.fetchone()
        
        if not order:
            flash('采购单不存在！', 'danger')
            return redirect(url_for('purchase_unified'))
        
        # 删除采购单项，不再检查订单状态
        cursor.execute("DELETE FROM purchase_order_items WHERE order_id = ?", (order_id,))
        
        # 删除采购单
        cursor.execute("DELETE FROM purchase_orders WHERE order_id = ?", (order_id,))
        
        conn.commit()
        flash('采购单已删除！', 'success')
    except Exception as e:
        flash(f'删除失败: {str(e)}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('purchase_unified'))

@app.route('/inventory')
def inventory():
    # 重定向到仓储管理系统
    return redirect('http://localhost:5001/inventory')

@app.route('/sales')
def sales():
    # 重定向到销售管理系统
    return redirect('http://localhost:5002/sales')
@app.route('/finance')
def finance():
    # 暂时重定向到首页，等待实现
    flash('财务管理模块正在开发中...', 'info')
    return redirect(url_for('home'))

@app.route('/member')
def member():
    # 暂时重定向到首页，等待实现
    flash('会员管理模块正在开发中...', 'info')
    return redirect(url_for('home'))

@app.route('/service')
def service():
    # 暂时重定向到首页，等待实现
    flash('特色服务模块正在开发中...', 'info')
    return redirect(url_for('home'))

# 供应商管理页面
@app.route('/purchase/suppliers')
def suppliers():
    # 获取所有供应商
    return redirect(url_for('purchase_supplier'))

@app.route('/purchase/supplier/rate/<code>', methods=['GET', 'POST'])
def rate_supplier(code):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取供应商信息
    cursor.execute("SELECT * FROM suppliers WHERE code = ?", (code,))
    supplier = cursor.fetchone()
    
    if not supplier:
        conn.close()
        flash('供应商不存在！', 'danger')
        return redirect(url_for('purchase_supplier'))
    
    if request.method == 'POST':
        # 获取表单数据 - 产品质量
        freshness_rating = request.form['freshness_rating']
        taste_rating = request.form['taste_rating']
        pesticide_rating = request.form['pesticide_rating']
        nutrition_rating = request.form['nutrition_rating']
        organic_rating = request.form['organic_rating']
        
        # 计算质量总分 (A=5, B=4, C=3, D=2, E=1)
        quality_weights = {
            'freshness': 0.3,
            'taste': 0.2,
            'pesticide': 0.2, 
            'nutrition': 0.2,
            'organic': 0.1
        }
        
        rating_scores = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
        quality_score = (
            rating_scores[freshness_rating] * quality_weights['freshness'] +
            rating_scores[taste_rating] * quality_weights['taste'] +
            rating_scores[pesticide_rating] * quality_weights['pesticide'] +
            rating_scores[nutrition_rating] * quality_weights['nutrition'] +
            rating_scores[organic_rating] * quality_weights['organic']
        )
        
        # 获取表单数据 - 供应能力
        comprehensive_rating = request.form['comprehensive_rating']
        timeliness_rating = request.form['timeliness_rating']
        flexibility_rating = request.form['flexibility_rating']
        attitude_rating = request.form['attitude_rating']
        
        # 计算供应能力总分
        capability_weights = {
            'comprehensive': 0.3,
            'timeliness': 0.3,
            'flexibility': 0.2,
            'attitude': 0.2
        }
        
        capability_score = (
            rating_scores[comprehensive_rating] * capability_weights['comprehensive'] +
            rating_scores[timeliness_rating] * capability_weights['timeliness'] +
            rating_scores[flexibility_rating] * capability_weights['flexibility'] +
            rating_scores[attitude_rating] * capability_weights['attitude']
        )
        
        # 获取表单数据 - 价格
        price_rating = request.form['price_rating']
        price_score = rating_scores[price_rating]
        
        # 计算总评分
        category_weights = {
            'quality': 0.4,
            'capability': 0.4,
            'price': 0.2
        }
        
        overall_score = (
            quality_score * category_weights['quality'] +
            capability_score * category_weights['capability'] +
            price_score * category_weights['price']
        )
        
        # 根据总分确定总等级
        overall_rating = 'C'  # 默认等级
        if overall_score >= 4.5:
            overall_rating = 'A'
        elif overall_score >= 3.5:
            overall_rating = 'B'
        elif overall_score >= 2.5:
            overall_rating = 'C'
        elif overall_score >= 1.5:
            overall_rating = 'D'
        else:
            overall_rating = 'E'
        
        # 获取评价备注
        comments = request.form['comments']
        rating_date = request.form['rating_date']
        
        try:
            # 插入评级记录
            cursor.execute('''
            INSERT INTO supplier_ratings (
                supplier_code, rating_date,
                freshness_rating, taste_rating, pesticide_rating, nutrition_rating, organic_rating, quality_score,
                comprehensive_rating, timeliness_rating, flexibility_rating, attitude_rating, capability_score,
                price_rating, price_score,
                overall_rating, overall_score,
                rater, comments
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                code, rating_date,
                freshness_rating, taste_rating, pesticide_rating, nutrition_rating, organic_rating, quality_score,
                comprehensive_rating, timeliness_rating, flexibility_rating, attitude_rating, capability_score,
                price_rating, price_score,
                overall_rating, overall_score,
                session['username'], comments
            ))
            
            # 更新供应商表中的综合评级
            cursor.execute('''
            UPDATE suppliers SET credit_rating = ? WHERE code = ?
            ''', (overall_rating, code))
            
            conn.commit()
            flash('供应商评级完成！', 'success')
        except Exception as e:
            flash(f'评级失败: {str(e)}', 'danger')
        finally:
            conn.close()
        
        return redirect(url_for('view_supplier', code=code))
    
    # 获取供应商最近的评级记录
    cursor.execute('''
    SELECT * FROM supplier_ratings 
    WHERE supplier_code = ? 
    ORDER BY rating_date DESC LIMIT 1
    ''', (code,))
    last_rating = cursor.fetchone()
    
    conn.close()
    
    # 获取当前日期
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('purchase/rate_supplier.html', 
                          username=session['username'], 
                          supplier=supplier,
                          last_rating=last_rating,
                          current_date=current_date)

@app.route('/purchase/supplier/ratings/<code>')
def supplier_ratings(code):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取供应商信息
    cursor.execute("SELECT * FROM suppliers WHERE code = ?", (code,))
    supplier = cursor.fetchone()
    
    if not supplier:
        conn.close()
        flash('供应商不存在！', 'danger')
        return redirect(url_for('purchase_supplier'))
    
    # 获取供应商的所有评级记录
    cursor.execute('''
    SELECT * FROM supplier_ratings 
    WHERE supplier_code = ? 
    ORDER BY rating_date DESC
    ''', (code,))
    ratings = cursor.fetchall()
    
    conn.close()
    
    return render_template('purchase/supplier_ratings.html', 
                          username=session['username'], 
                          supplier=supplier,
                          ratings=ratings)

# 添加批量操作路由
@app.route('/purchase/batch_operation', methods=['POST'])
def batch_operation():
    print("Received batch operation request")  # 添加日志
    try:
        # 获取JSON数据
        data = request.get_json()
        print("Request data:", data)  # 添加日志
        
        if not data or 'order_ids' not in data or 'operation' not in data:
            print("Invalid request data")  # 添加日志
            return jsonify({"status": "error", "message": "参数错误"}), 400
        
        order_ids = data['order_ids']
        operation = data['operation']
        print(f"Processing operation: {operation} for orders: {order_ids}")  # 添加日志
        
        # 连接数据库
        db_path = os.path.join('data', 'restaurant.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 定义状态转换映射
        status_map = {
            'submit': '已提交',
            'review': '已审核',
            'receive': '已收货',
            'payment': '已付款',
            'cancel': '已取消'
        }
        
        # 对每个订单执行操作
        success_count = 0
        error_messages = []
        
        for order_id in order_ids:
            print(f"Processing order: {order_id}")  # 添加日志
            # 获取当前订单状态
            cursor.execute("SELECT status FROM purchase_orders WHERE order_id = ?", (order_id,))
            result = cursor.fetchone()
            
            if not result:
                error_messages.append(f"订单 {order_id} 不存在")
                continue
            
            current_status = result['status']
            print(f"Current status for order {order_id}: {current_status}")  # 添加日志
            
            # 根据操作类型执行相应操作
            if operation == 'delete':
                try:
                    # 删除订单项
                    cursor.execute("DELETE FROM purchase_order_items WHERE order_id = ?", (order_id,))
                    # 删除订单
                    cursor.execute("DELETE FROM purchase_orders WHERE order_id = ?", (order_id,))
                    success_count += 1
                except Exception as e:
                    error_messages.append(f"删除订单 {order_id} 失败: {str(e)}")
                    print(f"Error deleting order {order_id}: {str(e)}")  # 添加日志
                
            elif operation in status_map:
                # 检查状态转换是否合法
                new_status = status_map[operation]
                
                # 定义合法的状态转换
                valid_transitions = {
                    '草稿': ['已提交'],
                    '已提交': ['已审核', '已取消'],
                    '已审核': ['已收货', '已取消'],
                    '已收货': ['已付款', '已取消'],
                    '已付款': ['已取消'],
                    '已取消': []
                }
                
                if new_status in valid_transitions.get(current_status, []):
                    try:
                        # 更新订单状态
                        cursor.execute('''
                        UPDATE purchase_orders 
                        SET status = ?, 
                            updated_at = CURRENT_TIMESTAMP,
                            updated_by = ?
                        WHERE order_id = ?
                        ''', (new_status, session.get('username', 'system'), order_id))
                        success_count += 1
                        print(f"Successfully updated order {order_id} to status {new_status}")  # 添加日志
                    except Exception as e:
                        error_messages.append(f"更新订单 {order_id} 状态失败: {str(e)}")
                        print(f"Error updating order {order_id}: {str(e)}")  # 添加日志
                else:
                    error_messages.append(f"订单 {order_id} 当前状态为 {current_status}，无法转换为 {new_status}")
                    print(f"Invalid status transition for order {order_id}: {current_status} -> {new_status}")  # 添加日志
            
            else:
                error_messages.append(f"不支持的操作类型: {operation}")
                print(f"Unsupported operation: {operation}")  # 添加日志
                break
        
        # 提交事务
        conn.commit()
        
        # 返回操作结果
        operation_names = {
            'submit': '提交',
            'review': '审核',
            'receive': '收货',
            'payment': '付款',
            'delete': '删除',
            'cancel': '取消'
        }
        operation_name = operation_names.get(operation, operation)
        
        if success_count > 0:
            message = f"成功{operation_name}了 {success_count} 个订单"
            if error_messages:
                message += f"，但有 {len(error_messages)} 个订单操作失败：{', '.join(error_messages)}"
            
            print(f"Operation completed: {message}")  # 添加日志
            return jsonify({
                "status": "success",
                "message": message,
                "success_count": success_count,
                "error_messages": error_messages
            })
        else:
            message = "操作失败: " + ", ".join(error_messages)
            print(f"Operation failed: {message}")  # 添加日志
            return jsonify({
                "status": "error",
                "message": message
            })
            
    except Exception as e:
        print(f"Unexpected error: {str(e)}")  # 添加日志
        return jsonify({"status": "error", "message": f"操作失败: {str(e)}"}), 500
    
    finally:
        if 'conn' in locals():
            conn.close()
            print("Database connection closed")  # 添加日志

def migrate_contract_files():
    """迁移现有合同文件记录，添加文件类型信息"""
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查是否需要添加新列
        cursor.execute("PRAGMA table_info(supplier_contracts)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # 添加新列
        if 'file_type' not in columns:
            cursor.execute("ALTER TABLE supplier_contracts ADD COLUMN file_type TEXT")
        if 'original_filename' not in columns:
            cursor.execute("ALTER TABLE supplier_contracts ADD COLUMN original_filename TEXT")
        
        # 更新现有记录的文件类型
        cursor.execute("SELECT contract_id, file_path FROM supplier_contracts WHERE file_type IS NULL AND file_path IS NOT NULL")
        records = cursor.fetchall()
        
        for record in records:
            contract_id, file_path = record
            if file_path:
                file_type = os.path.splitext(file_path)[1]
                original_filename = os.path.basename(file_path)
                cursor.execute("""
                    UPDATE supplier_contracts 
                    SET file_type = ?, original_filename = ?
                    WHERE contract_id = ?
                """, (file_type, original_filename, contract_id))
        
        conn.commit()
        print("合同文件记录迁移完成")
    except Exception as e:
        print(f"迁移失败: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

@app.route('/purchase/contract/delete/<contract_id>', methods=['POST'])
def delete_contract(contract_id):
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 获取合同文件路径
        cursor.execute("SELECT file_path FROM supplier_contracts WHERE contract_id = ?", (contract_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            # 删除实际文件
            file_path = os.path.join('static', result[0])
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # 删除合同记录
        cursor.execute("DELETE FROM supplier_contracts WHERE contract_id = ?", (contract_id,))
        conn.commit()
        flash('合同已成功删除！', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'删除失败: {str(e)}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('supplier_contracts'))

@app.route('/purchase/analysis')
def purchase_analysis():
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # 1. 基础统计数据
        # 供应商总数
        cursor.execute("SELECT COUNT(*) as total FROM suppliers WHERE status = '活跃'")
        active_suppliers = cursor.fetchone()['total']
        
        # 采购总金额
        cursor.execute("""
            SELECT COALESCE(SUM(poi.total_price), 0) as total
            FROM purchase_order_items poi
            JOIN purchase_orders po ON poi.order_id = po.order_id
            WHERE po.status IN ('已审核', '已收货', '已付款')
        """)
        total_purchase_amount = cursor.fetchone()['total']
        
        # 今日采购额
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT COALESCE(SUM(poi.total_price), 0) as total
            FROM purchase_order_items poi
            JOIN purchase_orders po ON poi.order_id = po.order_id
            WHERE po.order_date = ? AND po.status IN ('已审核', '已收货', '已付款')
        """, (today,))
        today_purchase_amount = cursor.fetchone()['total']

        # 今日采购次数
        cursor.execute("""
            SELECT COUNT(DISTINCT po.order_id) as count
            FROM purchase_orders po
            WHERE po.order_date = ? AND po.status IN ('已审核', '已收货', '已付款')
        """, (today,))
        today_purchase_count = cursor.fetchone()['count']
        
        # 2. 供应商采购金额占比（top 10）
        cursor.execute("""
            SELECT 
                s.name as supplier_name,
                COALESCE(SUM(poi.total_price), 0) as total_amount,
                COALESCE(SUM(poi.total_price) * 100.0 / (
                    SELECT SUM(total_price) 
                    FROM purchase_order_items 
                    JOIN purchase_orders po2 ON purchase_order_items.order_id = po2.order_id
                    WHERE po2.status IN ('已审核', '已收货', '已付款')
                ), 0) as percentage
            FROM suppliers s
            LEFT JOIN purchase_orders po ON s.code = po.supplier_id
            LEFT JOIN purchase_order_items poi ON po.order_id = poi.order_id
            WHERE po.status IN ('已审核', '已收货', '已付款') OR po.status IS NULL
            GROUP BY s.code
            ORDER BY total_amount DESC
            LIMIT 10
        """)
        supplier_percentages = cursor.fetchall()
        
        # 3. 月度采购数据（近12个月）
        cursor.execute("""
            WITH RECURSIVE months AS (
                SELECT date('now', 'start of month', '-11 months') as month
                UNION ALL
                SELECT date(month, '+1 month')
                FROM months
                WHERE month < date('now', 'start of month')
            )
            SELECT 
                strftime('%Y-%m', months.month) as month,
                COALESCE(SUM(poi.total_price), 0) as amount,
                COUNT(DISTINCT po.order_id) as order_count,
                COUNT(DISTINCT po.supplier_id) as supplier_count
            FROM months
            LEFT JOIN purchase_orders po ON strftime('%Y-%m', po.order_date) = strftime('%Y-%m', months.month)
                AND po.status IN ('已审核', '已收货', '已付款')
            LEFT JOIN purchase_order_items poi ON po.order_id = poi.order_id
            GROUP BY strftime('%Y-%m', months.month)
            ORDER BY month DESC
            LIMIT 12
        """)
        monthly_stats = cursor.fetchall()
        
        # 4. 供应商评级趋势
        cursor.execute("""
            SELECT 
                s.name as supplier_name,
                GROUP_CONCAT(sr.overall_rating || ',' || sr.rating_date) as rating_history
            FROM suppliers s
            JOIN supplier_ratings sr ON s.code = sr.supplier_code
            GROUP BY s.code
            ORDER BY s.name
        """)
        supplier_ratings = cursor.fetchall()
        
        # 5. 具体商品采购占比（当月）
        current_month = datetime.now().strftime('%Y-%m')
        cursor.execute("""
            SELECT 
                poi.item_name,
                COUNT(*) as count,
                COALESCE(SUM(poi.total_price), 0) as amount,
                COALESCE(SUM(poi.total_price) * 100.0 / (
                    SELECT SUM(total_price)
                    FROM purchase_order_items poi2
                    JOIN purchase_orders po2 ON poi2.order_id = po2.order_id
                    WHERE strftime('%Y-%m', po2.order_date) = ?
                    AND po2.status IN ('已审核', '已收货', '已付款')
                ), 0) as percentage
            FROM purchase_order_items poi
            JOIN purchase_orders po ON poi.order_id = po.order_id
            WHERE strftime('%Y-%m', po.order_date) = ?
            AND po.status IN ('已审核', '已收货', '已付款')
            GROUP BY poi.item_name
            ORDER BY amount DESC
        """, (current_month, current_month))
        item_stats = cursor.fetchall()

        # 6. 物资分类采购占比
        cursor.execute("""
            SELECT 
                poi.item_type as category,
                COUNT(*) as count,
                COALESCE(SUM(poi.total_price), 0) as amount,
                COALESCE(SUM(poi.total_price) * 100.0 / (
                    SELECT SUM(total_price) 
                    FROM purchase_order_items poi2
                    JOIN purchase_orders po2 ON poi2.order_id = po2.order_id
                    WHERE strftime('%Y-%m', po2.order_date) = ?
                    AND po2.status IN ('已审核', '已收货', '已付款')
                ), 0) as percentage
            FROM purchase_order_items poi
            JOIN purchase_orders po ON poi.order_id = po.order_id
            WHERE strftime('%Y-%m', po.order_date) = ?
            AND po.status IN ('已审核', '已收货', '已付款')
            GROUP BY poi.item_type
            ORDER BY amount DESC
        """, (current_month, current_month))
        category_stats = cursor.fetchall()

        # 处理评级历史数据
        rating_trends = []
        for supplier in supplier_ratings:
            ratings = []
            if supplier['rating_history']:
                rating_data_list = supplier['rating_history'].split(',')
                for i in range(0, len(rating_data_list), 2):
                    if i + 1 < len(rating_data_list):
                        ratings.append({
                            'rating': rating_data_list[i],
                            'date': rating_data_list[i + 1],
                            'sequence': i // 2 + 1  # 添加序号
                        })
                rating_trends.append({
                    'supplier_name': supplier['supplier_name'],
                    'ratings': sorted(ratings, key=lambda x: x['sequence'])  # 按序号排序
                })
        
        return render_template('purchase/analysis.html',
                             username=session['username'],
                             active_suppliers=active_suppliers,
                             total_purchase_amount=total_purchase_amount,
                             today_purchase_amount=today_purchase_amount,
                             today_purchase_count=today_purchase_count,
                             supplier_percentages=supplier_percentages,
                             monthly_stats=monthly_stats,
                             rating_trends=rating_trends,
                             item_stats=item_stats,
                             category_stats=category_stats)
    
    except Exception as e:
        flash(f'数据加载失败: {str(e)}', 'danger')
        return redirect(url_for('purchase'))
    finally:
        conn.close()

# 添加数据库迁移函数
def migrate_item_type():
    """添加物资类型字段并设置默认分类"""
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查是否已存在 item_type 列
        cursor.execute("PRAGMA table_info(purchase_order_items)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'item_type' not in columns:
            # 添加 item_type 列
            cursor.execute("ALTER TABLE purchase_order_items ADD COLUMN item_type TEXT")
            
            # 根据商品名称设置默认分类
            cursor.execute("""
                UPDATE purchase_order_items 
                SET item_type = CASE
                    WHEN item_name LIKE '%肉%' OR item_name LIKE '%鸡%' OR item_name LIKE '%鸭%' OR 
                         item_name LIKE '%鱼%' OR item_name LIKE '%虾%' THEN '肉类'
                    WHEN item_name LIKE '%菜%' OR item_name LIKE '%葱%' OR item_name LIKE '%姜%' OR 
                         item_name LIKE '%蒜%' OR item_name LIKE '%白菜%' OR item_name LIKE '%萝卜%' THEN '蔬菜类'
                    WHEN item_name LIKE '%盐%' OR item_name LIKE '%糖%' OR item_name LIKE '%酱%' OR 
                         item_name LIKE '%油%' OR item_name LIKE '%醋%' THEN '调料类'
                    WHEN item_name LIKE '%米%' OR item_name LIKE '%面%' OR item_name LIKE '%粉%' THEN '主食类'
                    WHEN item_name LIKE '%蛋%' OR item_name LIKE '%奶%' THEN '蛋奶类'
                    ELSE '其他'
                END
                WHERE item_type IS NULL
            """)
            
            # 设置 item_type 为非空
            cursor.execute("""
                UPDATE purchase_order_items 
                SET item_type = '其他'
                WHERE item_type IS NULL
            """)
            
            conn.commit()
            print("物资类型字段添加成功")
    except Exception as e:
        print(f"迁移失败: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

# 采购单据管理主页
@app.route('/purchase/documents')
def purchase_documents():
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # 获取发票统计数据
        cursor.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(total_amount), 0) as total
            FROM purchase_invoices
            WHERE status != '已作废'
        """)
        invoice_stats = cursor.fetchone()
        total_invoices = invoice_stats['count']
        total_invoice_amount = invoice_stats['total']
        
        # 获取收据统计数据
        cursor.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
            FROM purchase_receipts
            WHERE status != '已作废'
        """)
        receipt_stats = cursor.fetchone()
        total_receipts = receipt_stats['count']
        total_receipt_amount = receipt_stats['total']
        
        return render_template('purchase/documents.html',
                             username=session['username'],
                             total_invoices=total_invoices,
                             total_invoice_amount=total_invoice_amount,
                             total_receipts=total_receipts,
                             total_receipt_amount=total_receipt_amount)
    
    except Exception as e:
        flash(f'数据加载失败: {str(e)}', 'danger')
        return redirect(url_for('purchase'))
    finally:
        conn.close()

# 发票管理页面
@app.route('/purchase/invoices')
def purchase_invoices():
    # 获取筛选参数
    invoice_type = request.args.get('invoice_type', '')
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10  # 每页显示的记录数
    
    # 连接数据库
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # 构建查询条件
        query = """
        SELECT pi.*, s.name as supplier_name
        FROM purchase_invoices pi
        LEFT JOIN suppliers s ON pi.supplier_id = s.code
        WHERE 1=1
        """
        params = []
        
        if invoice_type:
            query += " AND pi.invoice_type = ?"
            params.append(invoice_type)
        
        if status:
            query += " AND pi.status = ?"
            params.append(status)
        
        if date_from:
            query += " AND pi.invoice_date >= ?"
            params.append(date_from)
        
        if date_to:
            query += " AND pi.invoice_date <= ?"
            params.append(date_to)
        
        if search:
            query += """ AND (
                pi.invoice_number LIKE ? OR 
                pi.invoice_code LIKE ? OR 
                s.name LIKE ?
            )"""
            search_term = f'%{search}%'
            params.extend([search_term, search_term, search_term])
        
        # 获取总记录数
        count_query = f"SELECT COUNT(*) as total FROM ({query})"
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()['total']
        
        # 添加分页
        query += " ORDER BY pi.created_at DESC LIMIT ? OFFSET ?"
        params.extend([per_page, (page - 1) * per_page])
        
        # 执行查询
        cursor.execute(query, params)
        invoices = cursor.fetchall()
        
        # 计算分页信息
        total_pages = (total_records + per_page - 1) // per_page
        has_prev = page > 1
        has_next = page < total_pages
        
        # 获取统计数据
        # 发票总数和总金额
        cursor.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(total_amount), 0) as total
            FROM purchase_invoices
            WHERE status != '已作废'
        """)
        stats = cursor.fetchone()
        total_invoices = stats['count']
        total_amount = stats['total']
        
        # 待处理发票数量
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM purchase_invoices
            WHERE status = '待审核'
        """)
        pending_invoices = cursor.fetchone()['count']
        
        # 今日新增发票数量
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM purchase_invoices
            WHERE DATE(created_at) = ?
        """, (today,))
        today_invoices = cursor.fetchone()['count']
        
        # 获取供应商列表（用于新增发票）
        cursor.execute("""
            SELECT code, name 
            FROM suppliers 
            WHERE status = '活跃'
            ORDER BY name
        """)
        suppliers = cursor.fetchall()
        
        # 获取未完成的采购订单（用于关联发票）
        cursor.execute("""
            SELECT order_id 
            FROM purchase_orders 
            WHERE status IN ('已审核', '已收货')
            ORDER BY order_date DESC
        """)
        purchase_orders = cursor.fetchall()
        
        return render_template('purchase/invoices.html',
                             username=session['username'],
                             invoices=invoices,
                             total_invoices=total_invoices,
                             total_amount=total_amount,
                             pending_invoices=pending_invoices,
                             today_invoices=today_invoices,
                             page=page,
                             has_prev=has_prev,
                             has_next=has_next,
                             suppliers=suppliers,
                             purchase_orders=purchase_orders)
    
    except Exception as e:
        flash(f'数据加载失败: {str(e)}', 'danger')
        return redirect(url_for('purchase_documents'))
    finally:
        conn.close()

# 收据管理页面
@app.route('/purchase/receipts')
def purchase_receipts():
    try:
        # 获取过滤参数
        receipt_type = request.args.get('receipt_type', '')
        status = request.args.get('status', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        search = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = 10

        # 构建SQL查询
        conn = get_db_connection()
        cursor = conn.cursor()

        # 基础查询
        base_query = """
            SELECT r.*, 
                   rp_supplier.name as receipt_party_supplier_name,
                   ip_supplier.name as issuing_party_supplier_name
            FROM purchase_receipts r
            LEFT JOIN suppliers rp_supplier ON r.receipt_party_id = rp_supplier.code 
                AND r.receipt_party_type = 'supplier'
            LEFT JOIN suppliers ip_supplier ON r.issuing_party_id = ip_supplier.code 
                AND r.issuing_party_type = 'supplier'
            WHERE 1=1
        """
        params = []

        # 添加过滤条件
        if receipt_type:
            base_query += " AND r.receipt_type = ?"
            params.append(receipt_type)
        if status:
            base_query += " AND r.status = ?"
            params.append(status)
        if date_from:
            base_query += " AND r.receipt_date >= ?"
            params.append(date_from)
        if date_to:
            base_query += " AND r.receipt_date <= ?"
            params.append(date_to)
        if search:
            base_query += """ AND (
                r.receipt_number LIKE ? OR 
                COALESCE(rp_supplier.name, r.receipt_party_name) LIKE ? OR
                COALESCE(ip_supplier.name, r.issuing_party_name) LIKE ?
            )"""
            search_term = f'%{search}%'
            params.extend([search_term, search_term, search_term])

        # 获取总记录数
        count_query = f"SELECT COUNT(*) FROM ({base_query}) as total"
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()[0]

        # 添加分页
        base_query += " ORDER BY r.created_at DESC LIMIT ? OFFSET ?"
        params.extend([per_page, (page - 1) * per_page])

        # 执行主查询
        cursor.execute(base_query, params)
        receipts = cursor.fetchall()

        # 获取统计信息
        cursor.execute("""
            SELECT 
                COUNT(*) as total_receipts,
                COALESCE(SUM(amount), 0) as total_amount,
                SUM(CASE WHEN status = '待确认' THEN 1 ELSE 0 END) as pending_receipts,
                SUM(CASE WHEN DATE(created_at) = DATE('now') THEN 1 ELSE 0 END) as today_receipts
            FROM purchase_receipts
            WHERE status != '已作废'
        """)
        stats = cursor.fetchone()

        # 获取供应商列表（用于新增/编辑表单）
        cursor.execute("SELECT code, name FROM suppliers WHERE status = '活跃' ORDER BY name")
        suppliers = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template('purchase/receipts.html',
                             receipts=receipts,
                             total_receipts=stats['total_receipts'],
                             total_amount=stats['total_amount'] or 0,
                             pending_receipts=stats['pending_receipts'],
                             today_receipts=stats['today_receipts'],
                             suppliers=suppliers,
                             page=page,
                             has_prev=page > 1,
                             has_next=total_records > page * per_page,
                             search=search,
                             receipt_type=receipt_type,
                             status=status,
                             date_from=date_from,
                             date_to=date_to)

    except Exception as e:
        print(f"Error in purchase_receipts: {str(e)}")
        flash('获取收据列表失败：' + str(e), 'error')
        return redirect(url_for('purchase_documents'))

@app.route('/purchase/receipts/add', methods=['POST'])
def add_receipt():
        
    try:
        # 获取表单数据
        receipt_type = request.form.get('receipt_type')
        receipt_number = request.form.get('receipt_number')
        receipt_date = request.form.get('receipt_date')
        amount = request.form.get('amount')
        payment_method = request.form.get('payment_method')
        purpose = request.form.get('purpose')
        remarks = request.form.get('remarks')

        # 获取收据方信息
        receipt_party_type = request.form.get('receipt_party_type')  # 'supplier' 或 'manual'
        receipt_party_id = request.form.get('receipt_party_id')  # 如果是供应商，则为供应商ID
        receipt_party_name = request.form.get('receipt_party_name')  # 如果是手动输入，则为手动输入的名称

        # 获取开据方信息
        issuing_party_type = request.form.get('issuing_party_type')  # 'supplier' 或 'manual'
        issuing_party_id = request.form.get('issuing_party_id')  # 如果是供应商，则为供应商ID
        issuing_party_name = request.form.get('issuing_party_name')  # 如果是手动输入，则为手动输入的名称

        # 验证必填字段
        if not all([receipt_type, receipt_number, receipt_date, amount, payment_method, purpose,
                   receipt_party_type, issuing_party_type]):
            return jsonify({'status': 'error', 'message': '请填写所有必填字段'})

        # 验证收据方信息
        if receipt_party_type == 'supplier' and not receipt_party_id:
            return jsonify({'status': 'error', 'message': '请选择收据方供应商'})
        elif receipt_party_type == 'manual' and not receipt_party_name:
            return jsonify({'status': 'error', 'message': '请输入收据方名称'})

        # 验证开据方信息
        if issuing_party_type == 'supplier' and not issuing_party_id:
            return jsonify({'status': 'error', 'message': '请选择开据方供应商'})
        elif issuing_party_type == 'manual' and not issuing_party_name:
            return jsonify({'status': 'error', 'message': '请输入开据方名称'})

        # 处理文件上传
        scan_file = request.files.get('receipt_scan')
        scan_file_path = None
        if scan_file and scan_file.filename:
            filename = secure_filename(scan_file.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            scan_file_path = os.path.join('static', 'uploads', 'receipts', unique_filename)
            os.makedirs(os.path.dirname(scan_file_path), exist_ok=True)
            scan_file.save(scan_file_path)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 插入收据记录
        cursor.execute("""
            INSERT INTO purchase_receipts (
                receipt_type, receipt_number, receipt_date, amount,
                payment_method, purpose, remarks, scan_file,
                receipt_party_type, receipt_party_id, receipt_party_name,
                issuing_party_type, issuing_party_id, issuing_party_name,
                status, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '待确认', ?, CURRENT_TIMESTAMP)
        """, (receipt_type, receipt_number, receipt_date, amount,
              payment_method, purpose, remarks, scan_file_path,
              receipt_party_type, receipt_party_id, receipt_party_name,
              issuing_party_type, issuing_party_id, issuing_party_name,
              session['username']))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'status': 'success', 'message': '收据添加成功'})

    except Exception as e:
        print(f"Error in add_receipt: {str(e)}")
        return jsonify({'status': 'error', 'message': f'添加收据失败: {str(e)}'})

@app.route('/purchase/receipts/<int:receipt_id>', methods=['GET'])
def get_receipt(receipt_id):
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取收据详情，包括供应商信息
        cursor.execute("""
            SELECT r.*,
                   rp.name as receipt_party_supplier_name,
                   ip.name as issuing_party_supplier_name
            FROM purchase_receipts r
            LEFT JOIN suppliers rp ON r.receipt_party_id = rp.code AND r.receipt_party_type = 'supplier'
            LEFT JOIN suppliers ip ON r.issuing_party_id = ip.code AND r.issuing_party_type = 'supplier'
            WHERE r.id = ?
        """, (receipt_id,))
        
        receipt = cursor.fetchone()

        if not receipt:
            return jsonify({'status': 'error', 'message': '收据不存在'})

        # 处理收据方显示名称
        receipt_party_display_name = (
            receipt['receipt_party_supplier_name'] 
            if receipt['receipt_party_type'] == 'supplier' 
            else receipt['receipt_party_name']
        )

        # 处理开据方显示名称
        issuing_party_display_name = (
            receipt['issuing_party_supplier_name'] 
            if receipt['issuing_party_type'] == 'supplier' 
            else receipt['issuing_party_name']
        )

        # 构建响应数据
        response_data = dict(receipt)
        response_data['receipt_party_display_name'] = receipt_party_display_name
        response_data['issuing_party_display_name'] = issuing_party_display_name

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'data': response_data
        })

    except Exception as e:
        print(f"Error in get_receipt: {str(e)}")
        return jsonify({'status': 'error', 'message': f'获取收据详情失败: {str(e)}'})

@app.route('/purchase/receipts/<int:receipt_id>', methods=['PUT'])
def update_receipt(receipt_id):
        
    try:
        # 获取表单数据
        receipt_type = request.form.get('receipt_type')
        receipt_number = request.form.get('receipt_number')
        receipt_date = request.form.get('receipt_date')
        amount = request.form.get('amount')
        payment_method = request.form.get('payment_method')
        purpose = request.form.get('purpose')
        remarks = request.form.get('remarks')

        # 获取收据方信息
        receipt_party_type = request.form.get('receipt_party_type')
        receipt_party_id = request.form.get('receipt_party_id')
        receipt_party_name = request.form.get('receipt_party_name')

        # 获取开据方信息
        issuing_party_type = request.form.get('issuing_party_type')
        issuing_party_id = request.form.get('issuing_party_id')
        issuing_party_name = request.form.get('issuing_party_name')

        # 验证必填字段
        if not all([receipt_type, receipt_number, receipt_date, amount, payment_method, purpose,
                   receipt_party_type, issuing_party_type]):
            return jsonify({'status': 'error', 'message': '请填写所有必填字段'})

        # 验证收据方信息
        if receipt_party_type == 'supplier' and not receipt_party_id:
            return jsonify({'status': 'error', 'message': '请选择收据方供应商'})
        elif receipt_party_type == 'manual' and not receipt_party_name:
            return jsonify({'status': 'error', 'message': '请输入收据方名称'})

        # 验证开据方信息
        if issuing_party_type == 'supplier' and not issuing_party_id:
            return jsonify({'status': 'error', 'message': '请选择开据方供应商'})
        elif issuing_party_type == 'manual' and not issuing_party_name:
            return jsonify({'status': 'error', 'message': '请输入开据方名称'})

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查收据是否存在且状态是否允许修改
        cursor.execute("SELECT status FROM purchase_receipts WHERE id = ?", (receipt_id,))
        current_status = cursor.fetchone()
        if not current_status:
            return jsonify({'status': 'error', 'message': '收据不存在'})
        if current_status['status'] == '已确认':
            return jsonify({'status': 'error', 'message': '已确认的收据不能修改'})

        # 处理文件上传
        scan_file = request.files.get('receipt_scan')
        scan_file_path = None
        if scan_file and scan_file.filename:
            filename = secure_filename(scan_file.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            scan_file_path = os.path.join('static', 'uploads', 'receipts', unique_filename)
            os.makedirs(os.path.dirname(scan_file_path), exist_ok=True)
            scan_file.save(scan_file_path)

            # 删除旧文件
            cursor.execute("SELECT scan_file FROM purchase_receipts WHERE id = ?", (receipt_id,))
            old_file = cursor.fetchone()
            if old_file and old_file['scan_file']:
                try:
                    os.remove(old_file['scan_file'])
                except:
                    pass  # 忽略删除失败的情况

        # 更新收据记录
        update_query = """
            UPDATE purchase_receipts SET
                receipt_type = ?,
                receipt_number = ?,
                receipt_date = ?,
                amount = ?,
                payment_method = ?,
                purpose = ?,
                remarks = ?,
                receipt_party_type = ?,
                receipt_party_id = ?,
                receipt_party_name = ?,
                issuing_party_type = ?,
                issuing_party_id = ?,
                issuing_party_name = ?,
                updated_by = ?,
                updated_at = CURRENT_TIMESTAMP
        """
        params = [
            receipt_type, receipt_number, receipt_date,
            amount, payment_method, purpose, remarks,
            receipt_party_type, receipt_party_id, receipt_party_name,
            issuing_party_type, issuing_party_id, issuing_party_name,
            session['username']
        ]

        if scan_file_path:
            update_query += ", scan_file = ?"
            params.append(scan_file_path)

        update_query += " WHERE id = ?"
        params.append(receipt_id)

        cursor.execute(update_query, params)
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'status': 'success', 'message': '收据更新成功'})

    except Exception as e:
        print(f"Error in update_receipt: {str(e)}")
        return jsonify({'status': 'error', 'message': f'更新收据失败: {str(e)}'})

@app.route('/purchase/receipts/<int:receipt_id>', methods=['DELETE'])
def delete_receipt(receipt_id):
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查收据是否存在且状态是否允许作废
        cursor.execute("SELECT status FROM purchase_receipts WHERE id = ?", (receipt_id,))
        current_status = cursor.fetchone()
        if not current_status:
            return jsonify({'status': 'error', 'message': '收据不存在'})
        if current_status['status'] == '已作废':
            return jsonify({'status': 'error', 'message': '收据已经作废'})

        # 更新收据状态为已作废
        cursor.execute("""
            UPDATE purchase_receipts SET
                status = '已作废',
                updated_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (session['username'], receipt_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'status': 'success', 'message': '收据已作废'})

    except Exception as e:
        print(f"Error in delete_receipt: {str(e)}")
        return jsonify({'status': 'error', 'message': '作废收据失败'})

@app.route('/purchase/receipts/<int:receipt_id>/confirm', methods=['POST'])
def confirm_receipt(receipt_id):
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查收据是否存在且状态是否允许确认
        cursor.execute("""
            SELECT status 
            FROM purchase_receipts 
            WHERE id = ?
        """, (receipt_id,))
        
        receipt = cursor.fetchone()
        if not receipt:
            conn.close()
            return jsonify({'status': 'error', 'message': '收据不存在'})
            
        if receipt['status'] != '待确认':
            conn.close()
            return jsonify({'status': 'error', 'message': '只有待确认的收据可以确认'})

        # 更新收据状态为已确认
        cursor.execute("""
            UPDATE purchase_receipts 
            SET status = '已确认',
                updated_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (session['username'], receipt_id))

        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': '收据已确认'
        })

    except Exception as e:
        print(f"Error in confirm_receipt: {str(e)}")
        if conn:
            conn.rollback()
            conn.close()
        return jsonify({
            'status': 'error',
            'message': f'确认收据失败：{str(e)}'
        })

@app.route('/purchase/invoices/add', methods=['POST'])
def add_invoice():
        
    try:
        data = request.form
        
        # 连接数据库
        db_path = os.path.join('data', 'restaurant.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 生成发票ID
        current_date = datetime.now().strftime('%Y%m%d')
        cursor.execute("SELECT COUNT(*) FROM purchase_invoices WHERE invoice_id LIKE ?", (f"INV{current_date}%",))
        count = cursor.fetchone()[0]
        invoice_id = f"INV{current_date}{str(count + 1).zfill(4)}"
        
        # 处理关联采购单
        order_ids = request.form.getlist('order_ids')
        related_orders = ','.join(order_ids) if order_ids else None
        
        # 插入发票记录
        cursor.execute("""
            INSERT INTO purchase_invoices (
                invoice_id, invoice_type, supplier_id, invoice_code, invoice_number,
                invoice_date, total_amount, tax_amount, related_orders,
                remarks, status, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '待审核', ?, datetime('now'))
        """, (
            invoice_id,
            data['invoice_type'],
            data['supplier_id'],
            data['invoice_code'],
            data['invoice_number'],
            data['invoice_date'],
            float(data['total_amount']),
            float(data['tax_amount']) if data['tax_amount'] else 0,
            related_orders,
            data['remarks'],
            session['username']
        ))
        
        # 处理发票扫描件上传
        if 'scan_file' in request.files:
            scan_file = request.files['scan_file']
            if scan_file and scan_file.filename:
                # 确保上传目录存在
                upload_dir = os.path.join('static', 'uploads', 'invoices')
                os.makedirs(upload_dir, exist_ok=True)
                
                # 生成安全的文件名
                filename = secure_filename(scan_file.filename)
                file_ext = os.path.splitext(filename)[1]
                new_filename = f"{invoice_id}_{int(time.time())}{file_ext}"
                
                # 保存文件
                file_path = os.path.join(upload_dir, new_filename)
                scan_file.save(file_path)
                
                # 更新数据库中的文件路径
                cursor.execute("""
                    UPDATE purchase_invoices 
                    SET scan_file = ? 
                    WHERE invoice_id = ?
                """, (f"uploads/invoices/{new_filename}", invoice_id))
        
        conn.commit()
        return jsonify({'status': 'success', 'message': '发票添加成功'})
    
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': f'发票添加失败: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/purchase/invoices/<int:invoice_id>', methods=['GET'])
def get_invoice(invoice_id):
        
    try:
        conn = sqlite3.connect(os.path.join('data', 'restaurant.db'))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT pi.*, s.name as supplier_name
            FROM purchase_invoices pi
            LEFT JOIN suppliers s ON pi.supplier_id = s.code
            WHERE pi.id = ?
        """, (invoice_id,))
        
        invoice = cursor.fetchone()
        if not invoice:
            return jsonify({'status': 'error', 'message': '发票不存在'}), 404
        
        return jsonify({
            'status': 'success',
            'data': dict(invoice)
        })
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'获取发票信息失败: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/purchase/invoices/<int:invoice_id>', methods=['PUT'])
def update_invoice(invoice_id):
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取请求数据
        data = request.form.to_dict()
        file = request.files.get('scan_file')
        
        # 验证必填字段
        required_fields = ['invoice_type', 'supplier_id', 'invoice_code', 
                         'invoice_number', 'invoice_date', 'total_amount']
        for field in required_fields:
            if field not in data:
                return jsonify({'status': 'error', 'message': f'缺少必填字段：{field}'})
        
        # 处理文件上传
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            data['scan_file'] = filename
        
        # 更新发票信息
        update_fields = []
        values = []
        for key, value in data.items():
            if key != 'purchase_orders':  # 采购订单关联单独处理
                update_fields.append(f"{key} = ?")
                values.append(value)
        
        values.append(invoice_id)
        update_query = f'''
            UPDATE purchase_invoices 
            SET {', '.join(update_fields)}
            WHERE id = ?
        '''
        
        cursor.execute(update_query, values)
        
        # 处理采购订单关联
        if 'purchase_orders' in data:
            # 先删除原有关联
            cursor.execute('DELETE FROM invoice_purchase_orders WHERE invoice_id = ?', 
                         (invoice_id,))
            
            # 添加新的关联
            purchase_orders = request.form.getlist('purchase_orders')
            for po_id in purchase_orders:
                cursor.execute('''
                    INSERT INTO invoice_purchase_orders (invoice_id, purchase_order_id)
                    VALUES (?, ?)
                ''', (invoice_id, po_id))
        
        conn.commit()
        return jsonify({'status': 'success', 'message': '发票更新成功'})
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {str(e)}")
        return jsonify({'status': 'error', 'message': '发票更新失败'})
        
    finally:
        if conn:
            conn.close()

@app.route('/purchase/invoices/<int:invoice_id>', methods=['DELETE'])
def delete_invoice(invoice_id):
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查发票是否存在
        cursor.execute('''
            SELECT scan_file 
            FROM purchase_invoices 
            WHERE id = ?
        ''', (invoice_id,))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({'status': 'error', 'message': '发票不存在'})
        
        # 删除关联的采购订单
        cursor.execute('''
            DELETE FROM invoice_purchase_orders 
            WHERE invoice_id = ?
        ''', (invoice_id,))
        
        # 删除发票记录
        cursor.execute('''
            DELETE FROM purchase_invoices 
            WHERE id = ?
        ''', (invoice_id,))
        
        # 如果有扫描文件，删除文件
        if result[0]:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], result[0])
            if os.path.exists(file_path):
                os.remove(file_path)
        
        conn.commit()
        return jsonify({'status': 'success', 'message': '发票删除成功'})
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {str(e)}")
        return jsonify({'status': 'error', 'message': '发票删除失败'})
        
    finally:
        if conn:
            conn.close()

@app.route('/purchase/invoices/<invoice_id>')
def get_invoice_details(invoice_id):
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取发票详情，包括供应商信息
        cursor.execute('''
            SELECT i.*, s.name as supplier_name 
            FROM purchase_invoices i
            LEFT JOIN suppliers s ON i.supplier_id = s.code
            WHERE i.invoice_id = ?
        ''', (invoice_id,))
        
        invoice = cursor.fetchone()
        
        if invoice is None:
            return jsonify({'status': 'error', 'message': '发票不存在'})
        
        # 构造响应数据
        invoice_data = dict(invoice)
        
        return jsonify({
            'status': 'success',
            'data': invoice_data
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'status': 'error', 'message': f'获取发票详情失败: {str(e)}'})
        
    finally:
        if conn:
            conn.close()

def migrate_invoice_table():
    """迁移发票表结构，添加新字段"""
    db_path = os.path.join('data', 'restaurant.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查是否需要添加新列
        cursor.execute("PRAGMA table_info(purchase_invoices)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # 添加新列
        if 'related_orders' not in columns:
            cursor.execute("ALTER TABLE purchase_invoices ADD COLUMN related_orders TEXT")
            print("发票表迁移完成：添加了 related_orders 字段")
        
        if 'scan_file' not in columns and 'file_path' in columns:
            # 重命名 file_path 为 scan_file
            cursor.execute("""
                CREATE TABLE purchase_invoices_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id TEXT UNIQUE NOT NULL,
                    invoice_type TEXT NOT NULL,
                    invoice_code TEXT NOT NULL,
                    invoice_number TEXT NOT NULL,
                    invoice_date DATE NOT NULL,
                    supplier_id TEXT NOT NULL,
                    total_amount DECIMAL(10,2) NOT NULL,
                    tax_amount DECIMAL(10,2),
                    related_orders TEXT,
                    scan_file TEXT,
                    remarks TEXT,
                    status TEXT DEFAULT '待审核',
                    created_by TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (supplier_id) REFERENCES suppliers (code)
                )
            """)
            
            # 复制数据，将 file_path 复制到 scan_file
            cursor.execute("""
                INSERT INTO purchase_invoices_new 
                SELECT id, invoice_id, invoice_type, invoice_code, invoice_number, 
                       invoice_date, supplier_id, total_amount, tax_amount, 
                       NULL as related_orders, file_path as scan_file, remarks, 
                       status, created_by, created_at
                FROM purchase_invoices
            """)
            
            # 删除旧表并重命名新表
            cursor.execute("DROP TABLE purchase_invoices")
            cursor.execute("ALTER TABLE purchase_invoices_new RENAME TO purchase_invoices")
            print("发票表迁移完成：file_path 重命名为 scan_file")
        
        conn.commit()
        
    except Exception as e:
        print(f"发票表迁移失败: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

@app.route('/purchase/invoices/<invoice_id>/review', methods=['POST'])
def review_invoice(invoice_id):
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查发票是否存在且状态为待审核
        cursor.execute('''
            SELECT status 
            FROM purchase_invoices 
            WHERE invoice_id = ?
        ''', (invoice_id,))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({'status': 'error', 'message': '发票不存在'})
        
        if result['status'] != '待审核':
            return jsonify({'status': 'error', 'message': '只能审核状态为待审核的发票'})
        
        # 更新发票状态为已审核
        cursor.execute('''
            UPDATE purchase_invoices 
            SET status = '已审核'
            WHERE invoice_id = ?
        ''', (invoice_id,))
        
        conn.commit()
        return jsonify({
            'status': 'success', 
            'message': '发票审核成功',
            'new_status': '已审核'
        })
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {str(e)}")
        return jsonify({'status': 'error', 'message': f'发票审核失败: {str(e)}'})
        
    finally:
        if conn:
            conn.close()

def migrate_receipts_table():
    """迁移收据表结构，添加新字段"""
    try:
        # 连接数据库
        db_path = os.path.join('data', 'restaurant.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取当前表结构
        cursor.execute("PRAGMA table_info(purchase_receipts)")
        columns = [column[1] for column in cursor.fetchall()]

        # 需要添加的字段列表
        required_columns = {
            'receipt_type': 'TEXT NOT NULL',
            'receipt_number': 'TEXT NOT NULL',
            'receipt_date': 'DATE NOT NULL',
            'amount': 'DECIMAL(10,2) NOT NULL',
            'payment_method': 'TEXT NOT NULL',
            'purpose': 'TEXT NOT NULL',
            'remarks': 'TEXT',
            'scan_file': 'TEXT',
            'status': 'TEXT DEFAULT "待确认"',
            'created_by': 'TEXT NOT NULL',
            'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            'updated_by': 'TEXT',
            'updated_at': 'TIMESTAMP',
            'receipt_party_type': 'TEXT NOT NULL',
            'receipt_party_id': 'TEXT',
            'receipt_party_name': 'TEXT',
            'issuing_party_type': 'TEXT NOT NULL',
            'issuing_party_id': 'TEXT',
            'issuing_party_name': 'TEXT'
        }

        # 添加缺失的列
        for column, type_def in required_columns.items():
            if column not in columns:
                try:
                    cursor.execute(f"ALTER TABLE purchase_receipts ADD COLUMN {column} {type_def}")
                    print(f"Added column {column} to purchase_receipts table")
                except Exception as e:
                    print(f"Error adding column {column}: {str(e)}")

        conn.commit()
        print("收据表迁移完成")

    except Exception as e:
        print(f"收据表迁移失败: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    try:
        # 初始化数据库
        db_exists = init_db()
        
        # 如果是首次创建数据库，显示提示信息
        if not db_exists:
            print("数据库初始化完成！")
            print("默认管理员账户：")
            print("用户名: admin")
            print("密码: admin123")
        
        # 执行数据库迁移
        migrate_item_type()
        migrate_contract_files()
        migrate_invoice_table()
        migrate_receipts_table()  # 添加这一行
        
        # 运行应用
        app.run(debug=True)
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

