# 智慧餐厅管理系统

这是一个基于Web的智慧餐厅管理系统，采用B/S架构。（注：上述文件目录非完整版，完整版需访问其他仓库）
<img width="2788" height="1472" alt="image" src="https://github.com/user-attachments/assets/53dfc71e-6f33-42a9-b390-58aa4132644a" />
<img width="1104" height="583" alt="image" src="https://github.com/user-attachments/assets/65645296-debd-4803-bcb5-94229651a1d1" />
![设计图2](https://github.com/user-attachments/assets/9a24aba8-c19f-4632-9e5b-06449ed28880)
![设计图3](https://github.com/user-attachments/assets/f575f335-0e2a-487f-87ef-53d7700beee9)
![设计图4](https://github.com/user-attachments/assets/d9496977-e656-4d3f-a744-4fc7eb957607)
![设计图5](https://github.com/user-attachments/assets/b775d12a-2635-4527-adf9-605e2ae6ebeb)

## 后期优化
调用AI助手组件和AI助手悬浮，实现AI回复用户问题。

## 技术栈

- 前端: HTML, CSS, JavaScript
- 后端: Python (Flask)
- 数据库: SQLite

## 功能特点

本系统整合了四个子系统，统一在一个端口提供服务：

1. **采购系统**：管理供应商、采购订单、采购分析等功能
2. **库存系统**：管理入库、出库、库存盘点等功能
3. **销售系统**：管理菜单、订单、会员、销售分析等功能
4. **特色系统**：管理传承菜、DIY饮品等特色功能

## 安装与运行

1. 克隆代码库
2. 安装依赖:
   ```
   pip install -r requirements.txt
   ```
3. 运行应用:
   ```
   python app.py
   ```
4. 在浏览器中访问 `http://127.0.0.1:5000`

## 初始账户

- 用户名: admin
- 密码: admin123

## 目录结构

```
restaurant-management-system/
├── app.py                # 主应用程序文件（整合了四个子系统）
├── routes/               # 路由模块目录
│   ├── __init__.py       # 包初始化文件
│   ├── purchase_routes.py  # 采购系统路由
│   ├── inventory_routes.py # 库存系统路由
│   ├── sales_routes.py     # 销售系统路由
│   └── special_routes.py   # 特色系统路由
├── requirements.txt      # 依赖项
├── static/               # 静态资源
│   ├── css/              # CSS样式文件
│   ├── js/               # JavaScript文件
│   └── images/           # 图像资源
├── templates/            # HTML模板
│   ├── purchase/         # 采购系统模板
│   ├── inventory/        # 库存系统模板
│   ├── sales/            # 销售系统模板
│   ├── special/          # 特色系统模板
│   ├── login.html        # 登录页面
│   └── index.html        # 主页
└── data/                 # 数据存储
    └── restaurant.db     # SQLite数据库
```

## 系统结构

系统采用模块化设计，将四个子系统整合到一个统一的应用中，使用同一个数据库和端口：

1. **采购管理**：`/purchase` - 负责供应商管理、采购订单等
2. **库存管理**：`/inventory` - 负责入库、出库、库存查询等
3. **销售管理**：`/sales` - 负责菜单管理、订单处理、会员管理等
4. **特色管理**：`/special` - 负责传承菜试做、DIY饮品等特色功能

各子系统共享同一个数据库，但表结构独立，避免耦合。

## 开发与扩展

系统设计为模块化结构，可以方便地添加新功能。要添加新功能，请按照以下步骤:

1. 在相应的路由模块中添加新的路由和处理逻辑
2. 在templates目录中创建新的HTML模板
3. 根据需要，在static目录中添加CSS和JavaScript文件
4. 如需新的数据表，在数据库初始化函数中添加相应的表结构 



