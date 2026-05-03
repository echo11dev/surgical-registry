#!/usr/bin/env python3
"""
Surgical Registry App
A Flask-based web application for managing patients, surgeries, and implants
with lookup tables for standardized data.
"""

import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, text

# Initialize Flask app
app = Flask(__name__)

# Production-ready configuration using environment variables
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-secret-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'sqlite:////tmp/surgical_registry.db'
)
# Fix for Render/Heroku Postgres URL (they use postgres:// but SQLAlchemy needs postgresql://)
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace(
        'postgres://', 'postgresql://', 1
    )

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Helps with connection issues on free tiers
}

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# ==================== DATABASE INITIALIZATION (Production Safe) ====================
# This runs on every startup, including with gunicorn on Render
with app.app_context():
    db.create_all()
    seed_initial_data()

# ==================== MODELS ====================

class Gender(db.Model):
    __tablename__ = 'genders'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    patients = db.relationship('Patient', backref='gender', lazy=True)

class ProcedureType(db.Model):
    __tablename__ = 'procedure_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    surgeries = db.relationship('Surgery', backref='procedure_type', lazy=True)

class ImplantType(db.Model):
    __tablename__ = 'implant_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    implants = db.relationship('Implant', backref='implant_type', lazy=True)

class Manufacturer(db.Model):
    __tablename__ = 'manufacturers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    implants = db.relationship('Implant', backref='manufacturer', lazy=True)

class Hospital(db.Model):
    __tablename__ = 'hospitals'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    surgeries = db.relationship('Surgery', backref='hospital', lazy=True)

class Surgeon(db.Model):
    __tablename__ = 'surgeons'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    specialty = db.Column(db.String(100))
    surgeries = db.relationship('Surgery', backref='surgeon', lazy=True)

class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    mrn = db.Column(db.String(50), unique=True, nullable=False, index=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    gender_id = db.Column(db.Integer, db.ForeignKey('genders.id'))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    surgeries = db.relationship('Surgery', backref='patient', cascade='all, delete-orphan', lazy=True)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self):
        today = date.today()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))

class Surgery(db.Model):
    __tablename__ = 'surgeries'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    surgery_date = db.Column(db.Date, nullable=False)
    procedure_type_id = db.Column(db.Integer, db.ForeignKey('procedure_types.id'))
    surgeon_id = db.Column(db.Integer, db.ForeignKey('surgeons.id'))
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id'))
    operating_room = db.Column(db.String(50))
    duration_minutes = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    implants = db.relationship('Implant', backref='surgery', cascade='all, delete-orphan', lazy=True)

class Implant(db.Model):
    __tablename__ = 'implants'
    id = db.Column(db.Integer, primary_key=True)
    surgery_id = db.Column(db.Integer, db.ForeignKey('surgeries.id'), nullable=False)
    implant_type_id = db.Column(db.Integer, db.ForeignKey('implant_types.id'))
    manufacturer_id = db.Column(db.Integer, db.ForeignKey('manufacturers.id'))
    model = db.Column(db.String(100))
    serial_number = db.Column(db.String(100), unique=True)
    size = db.Column(db.String(50))
    lot_number = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== HELPER FUNCTIONS ====================

def seed_initial_data():
    """Seed lookup tables and sample data if database is empty"""
    if Gender.query.first() is not None:
        return  # Already seeded

    # Lookups
    genders = ['Male', 'Female', 'Non-binary', 'Prefer not to say']
    for g in genders:
        db.session.add(Gender(name=g))

    procedure_types = [
        'Total Hip Arthroplasty', 'Total Knee Arthroplasty', 'Partial Knee Replacement',
        'Spinal Fusion (Lumbar)', 'Spinal Fusion (Cervical)', 'ACL Reconstruction',
        'Rotator Cuff Repair', 'Shoulder Arthroplasty', 'Carpal Tunnel Release',
        'Hip Resurfacing', 'Ankle Arthrodesis'
    ]
    for pt in procedure_types:
        db.session.add(ProcedureType(name=pt))

    implant_types = [
        'Femoral Stem', 'Acetabular Cup', 'Femoral Head', 'Tibial Tray',
        'Femoral Component (Knee)', 'Polyethylene Insert', 'Patellar Button',
        'Pedicle Screw', 'Rod', 'Interbody Cage', 'Suture Anchor',
        'Glenoid Component', 'Humeral Stem', 'Humeral Head'
    ]
    for it in implant_types:
        db.session.add(ImplantType(name=it))

    manufacturers = [
        'Stryker', 'Zimmer Biomet', 'DePuy Synthes', 'Smith & Nephew',
        'Medtronic', 'NuVasive', 'Globus Medical', 'Arthrex', 'ConMed'
    ]
    for m in manufacturers:
        db.session.add(Manufacturer(name=m))

    hospitals = [
        'Mayo Clinic - Rochester', 'Johns Hopkins Hospital', 'Cleveland Clinic',
        'Massachusetts General Hospital', 'UCLA Medical Center', 'NewYork-Presbyterian',
        'Cedars-Sinai Medical Center', 'Stanford Health Care'
    ]
    for h in hospitals:
        db.session.add(Hospital(name=h))

    surgeons = [
        ('Dr. Michael Thompson', 'Orthopedic Surgery - Joints'),
        ('Dr. Sarah Patel', 'Orthopedic Surgery - Spine'),
        ('Dr. Robert Kim', 'Orthopedic Surgery - Sports Medicine'),
        ('Dr. Emily Rodriguez', 'Orthopedic Surgery - Upper Extremity'),
        ('Dr. James Wilson', 'Neurosurgery - Spine')
    ]
    for name, specialty in surgeons:
        db.session.add(Surgeon(name=name, specialty=specialty))

    db.session.commit()

    # Sample Patients
    sample_patients = [
        {
            'mrn': 'MRN-2024-001',
            'first_name': 'John', 'last_name': 'Anderson',
            'dob': date(1965, 4, 12), 'gender_id': 1,
            'phone': '(555) 123-4567', 'email': 'john.anderson@email.com'
        },
        {
            'mrn': 'MRN-2024-002',
            'first_name': 'Maria', 'last_name': 'Garcia',
            'dob': date(1972, 9, 28), 'gender_id': 2,
            'phone': '(555) 987-6543', 'email': 'maria.garcia@email.com'
        },
        {
            'mrn': 'MRN-2024-003',
            'first_name': 'David', 'last_name': 'Lee',
            'dob': date(1958, 11, 5), 'gender_id': 1,
            'phone': '(555) 456-7890', 'email': 'david.lee@email.com'
        },
        {
            'mrn': 'MRN-2024-004',
            'first_name': 'Aisha', 'last_name': 'Khan',
            'dob': date(1980, 2, 15), 'gender_id': 2,
            'phone': '(555) 321-0987', 'email': 'aisha.khan@email.com'
        }
    ]

    for p_data in sample_patients:
        patient = Patient(**p_data)
        db.session.add(patient)
    db.session.commit()

    # Sample Surgeries
    sample_surgeries = [
        {
            'patient_id': 1, 'surgery_date': date(2024, 3, 15),
            'procedure_type_id': 1, 'surgeon_id': 1, 'hospital_id': 1,
            'operating_room': 'OR-3', 'duration_minutes': 145,
            'notes': 'Primary THA, cementless fixation. Excellent bone quality.'
        },
        {
            'patient_id': 1, 'surgery_date': date(2025, 1, 22),
            'procedure_type_id': 2, 'surgeon_id': 1, 'hospital_id': 1,
            'operating_room': 'OR-2', 'duration_minutes': 128,
            'notes': 'Bilateral TKA staged. Left knee first. Good ROM achieved.'
        },
        {
            'patient_id': 2, 'surgery_date': date(2024, 6, 10),
            'procedure_type_id': 5, 'surgeon_id': 2, 'hospital_id': 2,
            'operating_room': 'OR-5', 'duration_minutes': 195,
            'notes': 'C5-C6 ACDF with allograft and plate. No complications.'
        },
        {
            'patient_id': 3, 'surgery_date': date(2024, 9, 5),
            'procedure_type_id': 6, 'surgeon_id': 3, 'hospital_id': 3,
            'operating_room': 'OR-1', 'duration_minutes': 87,
            'notes': 'Autograft BTB. Stable Lachman post-op.'
        },
        {
            'patient_id': 4, 'surgery_date': date(2025, 2, 28),
            'procedure_type_id': 7, 'surgeon_id': 4, 'hospital_id': 4,
            'operating_room': 'OR-4', 'duration_minutes': 112,
            'notes': 'Arthroscopic double-row repair. Good tendon quality.'
        }
    ]

    for s_data in sample_surgeries:
        surgery = Surgery(**s_data)
        db.session.add(surgery)
    db.session.commit()

    # Sample Implants
    sample_implants = [
        # For surgery 1 (Hip)
        {'surgery_id': 1, 'implant_type_id': 1, 'manufacturer_id': 1, 'model': 'Accolade II', 'serial_number': 'STR-2024-78432', 'size': 'Size 5', 'lot_number': 'LOT-39281'},
        {'surgery_id': 1, 'implant_type_id': 2, 'manufacturer_id': 1, 'model': 'Trident II', 'serial_number': 'STR-2024-78433', 'size': '54mm', 'lot_number': 'LOT-39282'},
        {'surgery_id': 1, 'implant_type_id': 3, 'manufacturer_id': 1, 'model': 'LFIT Anatomic', 'serial_number': 'STR-2024-78434', 'size': '32mm', 'lot_number': 'LOT-39283'},
        # For surgery 2 (Knee)
        {'surgery_id': 2, 'implant_type_id': 4, 'manufacturer_id': 2, 'model': 'Persona', 'serial_number': 'ZIM-2025-11234', 'size': 'Size 7', 'lot_number': 'LOT-55102'},
        {'surgery_id': 2, 'implant_type_id': 5, 'manufacturer_id': 2, 'model': 'Persona CR', 'serial_number': 'ZIM-2025-11235', 'size': 'Size 7', 'lot_number': 'LOT-55103'},
        {'surgery_id': 2, 'implant_type_id': 6, 'manufacturer_id': 2, 'model': 'Persona PS', 'serial_number': 'ZIM-2025-11236', 'size': '10mm', 'lot_number': 'LOT-55104'},
        # For surgery 3 (Spine)
        {'surgery_id': 3, 'implant_type_id': 8, 'manufacturer_id': 5, 'model': 'CD Horizon', 'serial_number': 'MDT-2024-55678', 'size': '5.5mm x 45mm', 'lot_number': 'LOT-88321'},
        {'surgery_id': 3, 'implant_type_id': 9, 'manufacturer_id': 5, 'model': 'CD Horizon', 'serial_number': 'MDT-2024-55679', 'size': '5.5mm x 50mm', 'lot_number': 'LOT-88322'},
        {'surgery_id': 3, 'implant_type_id': 10, 'manufacturer_id': 6, 'model': 'CoRoent', 'serial_number': 'NUV-2024-33445', 'size': '12mm', 'lot_number': 'LOT-44719'},
        # For surgery 4 (ACL)
        {'surgery_id': 4, 'implant_type_id': 11, 'manufacturer_id': 8, 'model': 'SwiveLock', 'serial_number': 'ART-2024-99112', 'size': '4.75mm', 'lot_number': 'LOT-66234'},
        # For surgery 5 (Shoulder)
        {'surgery_id': 5, 'implant_type_id': 12, 'manufacturer_id': 3, 'model': 'Global Unite', 'serial_number': 'DPS-2025-22331', 'size': '44mm', 'lot_number': 'LOT-77890'},
        {'surgery_id': 5, 'implant_type_id': 13, 'manufacturer_id': 3, 'model': 'Global Unite', 'serial_number': 'DPS-2025-22332', 'size': '12mm x 130mm', 'lot_number': 'LOT-77891'},
    ]

    for i_data in sample_implants:
        implant = Implant(**i_data)
        db.session.add(implant)

    db.session.commit()
    print("✓ Initial data seeded successfully")

def get_all_lookups():
    """Return all lookup data for templates"""
    return {
        'genders': Gender.query.order_by(Gender.name).all(),
        'procedure_types': ProcedureType.query.order_by(ProcedureType.name).all(),
        'implant_types': ImplantType.query.order_by(ImplantType.name).all(),
        'manufacturers': Manufacturer.query.order_by(Manufacturer.name).all(),
        'hospitals': Hospital.query.order_by(Hospital.name).all(),
        'surgeons': Surgeon.query.order_by(Surgeon.name).all()
    }

# ==================== ROUTES ====================

@app.route('/')
def dashboard():
    """Main dashboard with statistics and recent activity"""
    stats = {
        'patients': Patient.query.count(),
        'surgeries': Surgery.query.count(),
        'implants': Implant.query.count(),
        'hospitals': Hospital.query.count()
    }
    
    recent_surgeries = db.session.query(Surgery, Patient).join(Patient).order_by(
        Surgery.surgery_date.desc()
    ).limit(6).all()
    
    # Top procedures
    top_procedures = db.session.query(
        ProcedureType.name, db.func.count(Surgery.id).label('count')
    ).join(Surgery).group_by(ProcedureType.name).order_by(db.func.count(Surgery.id).desc()).limit(5).all()
    
    lookups = get_all_lookups()
    
    return render_template('index.html', 
                          stats=stats, 
                          recent_surgeries=recent_surgeries,
                          top_procedures=top_procedures,
                          lookups=lookups)

# ---------- PATIENTS ----------
@app.route('/patients')
def patients_list():
    """List all patients with search"""
    search = request.args.get('search', '').strip()
    query = Patient.query
    
    if search:
        query = query.filter(
            or_(
                Patient.first_name.ilike(f'%{search}%'),
                Patient.last_name.ilike(f'%{search}%'),
                Patient.mrn.ilike(f'%{search}%'),
                Patient.phone.ilike(f'%{search}%')
            )
        )
    
    patients = query.order_by(Patient.last_name, Patient.first_name).all()
    lookups = get_all_lookups()
    
    return render_template('patients.html', 
                          patients=patients, 
                          search=search,
                          lookups=lookups)

@app.route('/patients', methods=['POST'])
def add_patient():
    """Add a new patient"""
    try:
        mrn = request.form.get('mrn', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        dob_str = request.form.get('dob')
        gender_id = request.form.get('gender_id', type=int)
        phone = request.form.get('phone', '').strip() or None
        email = request.form.get('email', '').strip() or None

        if not all([mrn, first_name, last_name, dob_str, gender_id]):
            flash('Please fill in all required fields (MRN, Name, DOB, Gender)', 'danger')
            return redirect(url_for('patients_list'))

        dob = datetime.strptime(dob_str, '%Y-%m-%d').date()

        patient = Patient(
            mrn=mrn,
            first_name=first_name,
            last_name=last_name,
            dob=dob,
            gender_id=gender_id,
            phone=phone,
            email=email
        )
        db.session.add(patient)
        db.session.commit()
        flash(f'Patient {patient.full_name} (MRN: {mrn}) added successfully!', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('A patient with that MRN already exists. Please use a unique MRN.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding patient: {str(e)}', 'danger')
    
    return redirect(url_for('patients_list'))

@app.route('/patients/<int:patient_id>')
def patient_detail(patient_id):
    """View patient details and their surgeries"""
    patient = Patient.query.get_or_404(patient_id)
    surgeries = Surgery.query.filter_by(patient_id=patient_id).order_by(Surgery.surgery_date.desc()).all()
    lookups = get_all_lookups()
    
    return render_template('patient_detail.html', 
                          patient=patient, 
                          surgeries=surgeries,
                          lookups=lookups)

@app.route('/patients/<int:patient_id>/edit', methods=['POST'])
def edit_patient(patient_id):
    """Edit an existing patient"""
    patient = Patient.query.get_or_404(patient_id)
    try:
        patient.mrn = request.form.get('mrn', patient.mrn).strip()
        patient.first_name = request.form.get('first_name', patient.first_name).strip()
        patient.last_name = request.form.get('last_name', patient.last_name).strip()
        dob_str = request.form.get('dob')
        if dob_str:
            patient.dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
        patient.gender_id = request.form.get('gender_id', type=int) or patient.gender_id
        patient.phone = request.form.get('phone', '').strip() or None
        patient.email = request.form.get('email', '').strip() or None
        
        db.session.commit()
        flash(f'Patient {patient.full_name} updated successfully!', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('MRN must be unique. Another patient already uses this MRN.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating patient: {str(e)}', 'danger')
    
    return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/patients/<int:patient_id>/delete', methods=['POST'])
def delete_patient(patient_id):
    """Delete a patient and all related data (cascade)"""
    patient = Patient.query.get_or_404(patient_id)
    name = patient.full_name
    try:
        db.session.delete(patient)
        db.session.commit()
        flash(f'Patient {name} and all associated records deleted.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting patient: {str(e)}', 'danger')
    return redirect(url_for('patients_list'))

# ---------- SURGERIES ----------
@app.route('/surgeries', methods=['POST'])
def add_surgery():
    """Add a new surgery (from patient detail or global)"""
    try:
        patient_id = request.form.get('patient_id', type=int)
        surgery_date_str = request.form.get('surgery_date')
        procedure_type_id = request.form.get('procedure_type_id', type=int)
        surgeon_id = request.form.get('surgeon_id', type=int)
        hospital_id = request.form.get('hospital_id', type=int)
        operating_room = request.form.get('operating_room', '').strip() or None
        duration = request.form.get('duration_minutes', type=int)
        notes = request.form.get('notes', '').strip() or None

        if not all([patient_id, surgery_date_str, procedure_type_id]):
            flash('Patient, Date, and Procedure Type are required.', 'danger')
            return redirect(request.referrer or url_for('patients_list'))

        surgery_date = datetime.strptime(surgery_date_str, '%Y-%m-%d').date()

        surgery = Surgery(
            patient_id=patient_id,
            surgery_date=surgery_date,
            procedure_type_id=procedure_type_id,
            surgeon_id=surgeon_id,
            hospital_id=hospital_id,
            operating_room=operating_room,
            duration_minutes=duration,
            notes=notes
        )
        db.session.add(surgery)
        db.session.commit()
        flash('Surgery added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding surgery: {str(e)}', 'danger')
    
    # Redirect back to patient detail if possible
    if patient_id:
        return redirect(url_for('patient_detail', patient_id=patient_id))
    return redirect(url_for('patients_list'))

@app.route('/surgeries/<int:surgery_id>')
def surgery_detail(surgery_id):
    """View surgery details and associated implants"""
    surgery = Surgery.query.get_or_404(surgery_id)
    patient = surgery.patient
    implants = Implant.query.filter_by(surgery_id=surgery_id).all()
    lookups = get_all_lookups()
    
    return render_template('surgery_detail.html', 
                          surgery=surgery, 
                          patient=patient,
                          implants=implants,
                          lookups=lookups)

@app.route('/surgeries/<int:surgery_id>/edit', methods=['POST'])
def edit_surgery(surgery_id):
    """Edit surgery details"""
    surgery = Surgery.query.get_or_404(surgery_id)
    try:
        surgery_date_str = request.form.get('surgery_date')
        if surgery_date_str:
            surgery.surgery_date = datetime.strptime(surgery_date_str, '%Y-%m-%d').date()
        surgery.procedure_type_id = request.form.get('procedure_type_id', type=int) or surgery.procedure_type_id
        surgery.surgeon_id = request.form.get('surgeon_id', type=int) or surgery.surgeon_id
        surgery.hospital_id = request.form.get('hospital_id', type=int) or surgery.hospital_id
        surgery.operating_room = request.form.get('operating_room', '').strip() or None
        surgery.duration_minutes = request.form.get('duration_minutes', type=int)
        surgery.notes = request.form.get('notes', '').strip() or None
        
        db.session.commit()
        flash('Surgery updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating surgery: {str(e)}', 'danger')
    
    return redirect(url_for('surgery_detail', surgery_id=surgery_id))

@app.route('/surgeries/<int:surgery_id>/delete', methods=['POST'])
def delete_surgery(surgery_id):
    """Delete a surgery and its implants"""
    surgery = Surgery.query.get_or_404(surgery_id)
    patient_id = surgery.patient_id
    try:
        db.session.delete(surgery)
        db.session.commit()
        flash('Surgery and all associated implants deleted.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting surgery: {str(e)}', 'danger')
    return redirect(url_for('patient_detail', patient_id=patient_id))

# ---------- IMPLANTS ----------
@app.route('/implants', methods=['POST'])
def add_implant():
    """Add a new implant to a surgery"""
    try:
        surgery_id = request.form.get('surgery_id', type=int)
        implant_type_id = request.form.get('implant_type_id', type=int)
        manufacturer_id = request.form.get('manufacturer_id', type=int)
        model = request.form.get('model', '').strip() or None
        serial_number = request.form.get('serial_number', '').strip() or None
        size = request.form.get('size', '').strip() or None
        lot_number = request.form.get('lot_number', '').strip() or None
        notes = request.form.get('notes', '').strip() or None

        if not surgery_id:
            flash('Surgery ID is required.', 'danger')
            return redirect(request.referrer or url_for('patients_list'))

        implant = Implant(
            surgery_id=surgery_id,
            implant_type_id=implant_type_id,
            manufacturer_id=manufacturer_id,
            model=model,
            serial_number=serial_number,
            size=size,
            lot_number=lot_number,
            notes=notes
        )
        db.session.add(implant)
        db.session.commit()
        flash('Implant added successfully!', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('A implant with that serial number already exists.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding implant: {str(e)}', 'danger')
    
    if surgery_id:
        return redirect(url_for('surgery_detail', surgery_id=surgery_id))
    return redirect(url_for('patients_list'))

@app.route('/implants/<int:implant_id>/edit', methods=['POST'])
def edit_implant(implant_id):
    """Edit an implant"""
    implant = Implant.query.get_or_404(implant_id)
    surgery_id = implant.surgery_id
    try:
        implant.implant_type_id = request.form.get('implant_type_id', type=int) or implant.implant_type_id
        implant.manufacturer_id = request.form.get('manufacturer_id', type=int) or implant.manufacturer_id
        implant.model = request.form.get('model', '').strip() or None
        implant.serial_number = request.form.get('serial_number', '').strip() or None
        implant.size = request.form.get('size', '').strip() or None
        implant.lot_number = request.form.get('lot_number', '').strip() or None
        implant.notes = request.form.get('notes', '').strip() or None
        
        db.session.commit()
        flash('Implant updated successfully!', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Serial number must be unique.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating implant: {str(e)}', 'danger')
    
    return redirect(url_for('surgery_detail', surgery_id=surgery_id))

@app.route('/implants/<int:implant_id>/delete', methods=['POST'])
def delete_implant(implant_id):
    """Delete an implant"""
    implant = Implant.query.get_or_404(implant_id)
    surgery_id = implant.surgery_id
    try:
        db.session.delete(implant)
        db.session.commit()
        flash('Implant deleted.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting implant: {str(e)}', 'danger')
    return redirect(url_for('surgery_detail', surgery_id=surgery_id))

# ---------- LOOKUPS ----------
@app.route('/lookups')
def lookups():
    """Manage all lookup tables"""
    lookups = get_all_lookups()
    return render_template('lookups.html', lookups=lookups)

@app.route('/lookups/<string:table>', methods=['POST'])
def add_lookup(table):
    """Add a new lookup entry"""
    name = request.form.get('name', '').strip()
    specialty = request.form.get('specialty', '').strip() or None  # only for surgeons
    
    if not name:
        flash('Name is required.', 'danger')
        return redirect(url_for('lookups'))
    
    model_map = {
        'genders': Gender,
        'procedure_types': ProcedureType,
        'implant_types': ImplantType,
        'manufacturers': Manufacturer,
        'hospitals': Hospital,
        'surgeons': Surgeon
    }
    
    model = model_map.get(table)
    if not model:
        flash('Invalid lookup table.', 'danger')
        return redirect(url_for('lookups'))
    
    try:
        if table == 'surgeons':
            entry = model(name=name, specialty=specialty)
        else:
            entry = model(name=name)
        db.session.add(entry)
        db.session.commit()
        flash(f'{table.replace("_", " ").title()[:-1]} added successfully!', 'success')
    except IntegrityError:
        db.session.rollback()
        flash(f'That {table.replace("_", " ")[:-1]} already exists.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('lookups'))

@app.route('/lookups/<string:table>/<int:entry_id>/delete', methods=['POST'])
def delete_lookup(table, entry_id):
    """Delete a lookup entry (if not in use)"""
    model_map = {
        'genders': Gender,
        'procedure_types': ProcedureType,
        'implant_types': ImplantType,
        'manufacturers': Manufacturer,
        'hospitals': Hospital,
        'surgeons': Surgeon
    }
    model = model_map.get(table)
    if not model:
        flash('Invalid table.', 'danger')
        return redirect(url_for('lookups'))
    
    entry = model.query.get_or_404(entry_id)
    try:
        db.session.delete(entry)
        db.session.commit()
        flash(f'Entry deleted. Note: If it was in use, related records may have been affected.', 'warning')
    except IntegrityError:
        db.session.rollback()
        flash('Cannot delete: This entry is referenced by existing records. Remove references first.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('lookups'))

# ---------- API for JS (optional) ----------
@app.route('/api/patient/<int:patient_id>/surgeries')
def api_patient_surgeries(patient_id):
    surgeries = Surgery.query.filter_by(patient_id=patient_id).order_by(Surgery.surgery_date.desc()).all()
    return jsonify([{
        'id': s.id,
        'date': s.surgery_date.isoformat(),
        'procedure': s.procedure_type.name if s.procedure_type else 'N/A',
        'surgeon': s.surgeon.name if s.surgeon else 'N/A'
    } for s in surgeries])

# ---------- Health Check (for hosting platforms) ----------
@app.route('/health')
def health_check():
    """Health check endpoint for Render, Railway, Heroku, etc."""
    try:
        # Quick DB check
        db.session.execute(text('SELECT 1'))
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_initial_data()
    
    print("\n" + "="*60)
    print("🏥 SURGICAL REGISTRY APP")
    print("="*60)
    print("Database initialized with sample data.")
    print("Open your browser to: http://localhost:5000")
    print("Press CTRL+C to stop the server.")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)