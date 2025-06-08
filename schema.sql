-- 收据表
CREATE TABLE IF NOT EXISTS purchase_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_type TEXT NOT NULL,  -- 收据类型：发票/收据
    supplier_id TEXT NOT NULL,   -- 供应商编码
    receipt_number TEXT NOT NULL, -- 收据编号
    receipt_date DATE NOT NULL,  -- 收据日期
    amount DECIMAL(10,2) NOT NULL, -- 金额
    payment_method TEXT NOT NULL, -- 支付方式
    purpose TEXT NOT NULL,       -- 用途
    remarks TEXT,               -- 备注
    scan_file TEXT,            -- 扫描件文件路径
    status TEXT NOT NULL DEFAULT '待确认', -- 状态：待确认/已确认/已作废
    created_by TEXT NOT NULL,   -- 创建人
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,           -- 更新人
    updated_at TIMESTAMP,      -- 更新时间
    confirmed_by TEXT,         -- 确认人
    confirmed_at TIMESTAMP,    -- 确认时间
    FOREIGN KEY (supplier_id) REFERENCES suppliers(code),
    FOREIGN KEY (created_by) REFERENCES users(username),
    FOREIGN KEY (updated_by) REFERENCES users(username),
    FOREIGN KEY (confirmed_by) REFERENCES users(username)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_receipts_supplier ON purchase_receipts(supplier_id);
CREATE INDEX IF NOT EXISTS idx_receipts_status ON purchase_receipts(status);
CREATE INDEX IF NOT EXISTS idx_receipts_date ON purchase_receipts(receipt_date);
CREATE INDEX IF NOT EXISTS idx_receipts_number ON purchase_receipts(receipt_number); 