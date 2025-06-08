from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

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