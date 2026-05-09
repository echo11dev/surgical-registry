#!/usr/bin/env python3
"""
Surgical Registry App
A Flask-based web application for managing patients, surgeries, and implants
with lookup tables for standardized data.
"""

import os
import csv
import io
import json
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
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

# Context processor to make current date available in all templates (for dynamic banner)
@app.context_processor
def inject_current_date():
    """Provide current date to all templates for the top banner."""
    from datetime import date
    return {'current_date': date.today().strftime('%B %d, %Y')}

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
    gender_id = db.Column(db.Integer, db.ForeignKey('genders.id'))  # kept as gender_id for compatibility, labeled as "Sex" in UI
    sex = db.Column(db.String(10))  # 'Male' or 'Female' (simplified)
    weight_kg = db.Column(db.Float)
    height_cm = db.Column(db.Float)
    race = db.Column(db.String(50))
    ethnicity = db.Column(db.String(50))
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

    @property
    def bmi(self):
        if self.weight_kg and self.height_cm and self.height_cm > 0:
            return round(self.weight_kg / ((self.height_cm / 100) ** 2), 1)
        return None

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
    
    # New orthopedic-specific fields
    joint = db.Column(db.String(10))           # 'Hip' or 'Knee'
    side = db.Column(db.String(10))            # 'Left' or 'Right'
    surgery_type = db.Column(db.String(20))    # 'Primary' or 'Revision'
    revision_reason = db.Column(db.String(50)) # 'Aseptic' or 'Infected' (if revision)
    
    # Elixhauser Comorbidity Index (van Walraven)
    elixhauser_score = db.Column(db.Integer, default=0)
    comorbidities = db.Column(db.JSON, default={})  # Stores Yes/No for each comorbidity
    
    # Complications
    complications = db.Column(db.JSON, default={})  # Stores Yes/No for each complication
    
    # Outpatient / Same-day discharge
    outpatient = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    implants = db.relationship('Implant', backref='surgery', cascade='all, delete-orphan', lazy=True)
    research_projects = db.relationship('ResearchProject', secondary='surgery_research_projects', backref='surgeries', lazy='dynamic')

class Implant(db.Model):
    __tablename__ = 'implants'
    id = db.Column(db.Integer, primary_key=True)
    surgery_id = db.Column(db.Integer, db.ForeignKey('surgeries.id'), nullable=False)
    implant_type_id = db.Column(db.Integer, db.ForeignKey('implant_types.id'))
    manufacturer_id = db.Column(db.Integer, db.ForeignKey('manufacturers.id'))
    model = db.Column(db.String(100))
    reference_number = db.Column(db.String(100), unique=True)  # was serial_number
    size = db.Column(db.String(50))
    lot_number = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ResearchProject(db.Model):
    """Research projects that patients can be enrolled in during a surgery"""
    __tablename__ = 'research_projects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    sponsor = db.Column(db.String(200))
    description = db.Column(db.Text)
    enrollment_goal = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Association table for many-to-many between Surgery and ResearchProject
surgery_research_projects = db.Table(
    'surgery_research_projects',
    db.Column('surgery_id', db.Integer, db.ForeignKey('surgeries.id'), primary_key=True),
    db.Column('research_project_id', db.Integer, db.ForeignKey('research_projects.id'), primary_key=True)
)


class ImplantCatalog(db.Model):
    """Master catalog of available implants searchable by catalog number.
    This is the single source of truth for all implant information.
    """
    __tablename__ = 'implant_catalog'
    id = db.Column(db.Integer, primary_key=True)
    catalog_number = db.Column(db.String(100), unique=True, nullable=False, index=True)
    implant_type_id = db.Column(db.Integer, db.ForeignKey('implant_types.id'))
    manufacturer_id = db.Column(db.Integer, db.ForeignKey('manufacturers.id'))
    model = db.Column(db.String(150))
    design = db.Column(db.String(100))       # e.g. CR, PS, Cementless, etc.
    fixation = db.Column(db.String(50))      # e.g. Cemented, Cementless, Hybrid
    side = db.Column(db.String(20))          # Left, Right, Both, N/A
    size = db.Column(db.String(50))
    description = db.Column(db.Text)
    
    implant_type = db.relationship('ImplantType', backref='catalog_entries')
    manufacturer = db.relationship('Manufacturer', backref='catalog_entries')


# ==================== HELPER FUNCTIONS ====================

def get_or_create_procedure_type(side, joint, surgery_type, primary_type=None):
    """Calculate procedure name from ortho fields (per user algorithm) and get/create ProcedureType entry.
    This allows Procedure Type to be auto-calculated without manual dropdown in forms.
    """
    if not side or not joint or not surgery_type:
        return None
    name = None
    if surgery_type == 'Primary' and primary_type:
        if joint == 'Hip':
            if primary_type == 'Total':
                name = "Total Hip Arthroplasty"
            elif primary_type == 'Partial':
                name = "Hip Hemiarthroplasty"
        elif joint == 'Knee':
            if primary_type == 'Total':
                name = "Total Knee Arthroplasty"
            elif primary_type == 'Partial':
                name = "Unicompartmental Knee Arthroplasty"
    else:
        # Revision or fallback - store base without side
        name = f"{surgery_type} {joint} Arthroplasty"
    if not name:
        return None
    pt = ProcedureType.query.filter_by(name=name).first()
    if not pt:
        pt = ProcedureType(name=name)
        db.session.add(pt)
        db.session.flush()
    return pt


def get_missing_mandatory_implants(surgery):
    """Return list of missing mandatory implant types for Primary Hip/Knee surgeries."""
    if not surgery or surgery.surgery_type != 'Primary' or surgery.joint not in ('Hip', 'Knee'):
        return []

    if surgery.joint == 'Knee':
        mandatory_names = [
            'Knee Femoral Component',
            'Knee Tibia Component',
            'Knee Tibia Liner'
        ]
    else:  # Hip
        mandatory_names = [
            'Hip Acetabular Shell',
            'Hip Acetabular Liner',
            'Hip Femoral Stem',
            'Hip Femoral Head'
        ]

    existing_names = {
        imp.implant_type.name 
        for imp in surgery.implants 
        if imp.implant_type and imp.implant_type.name
    }
    return [name for name in mandatory_names if name not in existing_names]


def seed_initial_data():
    """Seed lookup tables and sample data if database is empty"""
    if Gender.query.first() is not None:
        return  # Already seeded

    # Lookups
    genders = ['Male', 'Female']
    for g in genders:
        db.session.add(Gender(name=g))

    procedure_types = [
        'Total Hip Arthroplasty',
        'Total Knee Arthroplasty',
        'Hip Hemiarthroplasty',
        'Unicompartmental Knee Arthroplasty',
        'Revision Hip Arthroplasty',
        'Revision Knee Arthroplasty'
    ]
    for pt in procedure_types:
        db.session.add(ProcedureType(name=pt))

    implant_types = [
        'Hip Acetabular Shell',
        'Hip Acetabular Liner',
        'Hip Femoral Stem',
        'Hip Femoral Head',
        'Knee Femoral Component',
        'Knee Tibia Component',
        'Knee Tibia Liner',
        'Knee Patellar Component'
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
            'dob': date(1965, 4, 12), 'sex': 'Male',
            'phone': '(555) 123-4567', 'email': 'john.anderson@email.com'
        },
        {
            'mrn': 'MRN-2024-002',
            'first_name': 'Maria', 'last_name': 'Garcia',
            'dob': date(1972, 9, 28), 'sex': 'Female',
            'phone': '(555) 987-6543', 'email': 'maria.garcia@email.com'
        },
        {
            'mrn': 'MRN-2024-003',
            'first_name': 'David', 'last_name': 'Lee',
            'dob': date(1958, 11, 5), 'sex': 'Male',
            'phone': '(555) 456-7890', 'email': 'david.lee@email.com'
        },
        {
            'mrn': 'MRN-2024-004',
            'first_name': 'Aisha', 'last_name': 'Khan',
            'dob': date(1980, 2, 15), 'sex': 'Female',
            'phone': '(555) 321-0987', 'email': 'aisha.khan@email.com'
        },
        {
            'mrn': 'MRN-2024-005',
            'first_name': 'Robert', 'last_name': 'Chen',
            'dob': date(1968, 7, 3), 'sex': 'Male',
            'phone': '(555) 654-3210', 'email': 'robert.chen@email.com'
        },
        {
            'mrn': 'MRN-2024-006',
            'first_name': 'Linda', 'last_name': 'Martinez',
            'dob': date(1975, 11, 19), 'sex': 'Female',
            'phone': '(555) 789-0123', 'email': 'linda.martinez@email.com'
        },
        {
            'mrn': 'MRN-2024-007',
            'first_name': 'William', 'last_name': 'Brown',
            'dob': date(1955, 3, 22), 'sex': 'Male',
            'phone': '(555) 234-5678', 'email': 'william.brown@email.com'
        },
        {
            'mrn': 'MRN-2024-008',
            'first_name': 'Patricia', 'last_name': 'Wong',
            'dob': date(1962, 8, 14), 'sex': 'Female',
            'phone': '(555) 567-8901', 'email': 'patricia.wong@email.com'
        },
        {
            'mrn': 'MRN-2024-009',
            'first_name': 'Michael', 'last_name': 'Thompson',
            'dob': date(1970, 5, 9), 'sex': 'Male',
            'phone': '(555) 890-1234', 'email': 'michael.thompson@email.com'
        },
        {
            'mrn': 'MRN-2024-010',
            'first_name': 'Susan', 'last_name': 'Miller',
            'dob': date(1959, 12, 1), 'sex': 'Female',
            'phone': '(555) 345-6789', 'email': 'susan.miller@email.com'
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
            'surgeon_id': 1, 'hospital_id': 1,
            'joint': 'Hip', 'side': 'Right', 'surgery_type': 'Primary',
            'notes': 'Primary THA, cementless fixation. Excellent bone quality.'
        },
        {
            'patient_id': 1, 'surgery_date': date(2025, 1, 22),
            'surgeon_id': 1, 'hospital_id': 1,
            'joint': 'Knee', 'side': 'Left', 'surgery_type': 'Primary',
            'notes': 'Bilateral TKA staged. Left knee first. Good ROM achieved.'
        },
        {
            'patient_id': 2, 'surgery_date': date(2024, 6, 10),
            'surgeon_id': 2, 'hospital_id': 2,
            'joint': 'Hip', 'side': 'Right', 'surgery_type': 'Revision',
            'notes': 'Revision THA with acetabular bone grafting.'
        },
        {
            'patient_id': 3, 'surgery_date': date(2024, 9, 5),
            'surgeon_id': 3, 'hospital_id': 3,
            'joint': 'Knee', 'side': 'Right', 'surgery_type': 'Primary',
            'notes': 'Primary TKA, cruciate retaining.'
        },
        {
            'patient_id': 4, 'surgery_date': date(2025, 2, 28),
            'surgeon_id': 4, 'hospital_id': 4,
            'joint': 'Knee', 'side': 'Left', 'surgery_type': 'Primary',
            'notes': 'UKA medial compartment, good alignment.'
        }
    ]

    for s_data in sample_surgeries:
        # Use the new calculation to set consistent naming (avoids old redundant names)
        proc = get_or_create_procedure_type(
            s_data.get('side'), s_data.get('joint'), s_data.get('surgery_type')
        )
        if proc:
            s_data['procedure_type_id'] = proc.id
        surgery = Surgery(**s_data)
        db.session.add(surgery)
    db.session.commit()

    # Sample Implants (updated for new simplified implant types)
    sample_implants = [
        # Surgery 1 - Hip (THA)
        {'surgery_id': 1, 'implant_type_id': 3, 'manufacturer_id': 1, 'model': 'Accolade II', 'reference_number': 'STR-2024-78432', 'size': 'Size 5', 'lot_number': 'LOT-39281'},
        {'surgery_id': 1, 'implant_type_id': 1, 'manufacturer_id': 1, 'model': 'Trident II', 'reference_number': 'STR-2024-78433', 'size': '54mm', 'lot_number': 'LOT-39282'},
        {'surgery_id': 1, 'implant_type_id': 4, 'manufacturer_id': 1, 'model': 'LFIT Anatomic', 'reference_number': 'STR-2024-78434', 'size': '32mm', 'lot_number': 'LOT-39283'},
        # Surgery 2 - Knee (TKA)
        {'surgery_id': 2, 'implant_type_id': 5, 'manufacturer_id': 2, 'model': 'Persona CR', 'reference_number': 'ZIM-2025-11234', 'size': 'Size 7', 'lot_number': 'LOT-55102'},
        {'surgery_id': 2, 'implant_type_id': 6, 'manufacturer_id': 2, 'model': 'Persona Tibial', 'reference_number': 'ZIM-2025-11235', 'size': 'Size 7', 'lot_number': 'LOT-55103'},
        {'surgery_id': 2, 'implant_type_id': 7, 'manufacturer_id': 2, 'model': 'Persona PS Insert', 'reference_number': 'ZIM-2025-11236', 'size': '10mm', 'lot_number': 'LOT-55104'},
        # Surgery 3 - Hip Revision
        {'surgery_id': 3, 'implant_type_id': 1, 'manufacturer_id': 3, 'model': 'Pinnacle', 'reference_number': 'DPS-2024-99112', 'size': '54mm', 'lot_number': 'LOT-88321'},
        {'surgery_id': 3, 'implant_type_id': 2, 'manufacturer_id': 3, 'model': 'Marathon', 'reference_number': 'DPS-2024-99113', 'size': '54mm', 'lot_number': 'LOT-88322'},
        # Surgery 4 - Knee
        {'surgery_id': 4, 'implant_type_id': 5, 'manufacturer_id': 2, 'model': 'Persona CR', 'reference_number': 'ZIM-2024-33445', 'size': 'Size 6', 'lot_number': 'LOT-44719'},
        {'surgery_id': 4, 'implant_type_id': 8, 'manufacturer_id': 2, 'model': 'Persona Patella', 'reference_number': 'ZIM-2024-33446', 'size': '32mm', 'lot_number': 'LOT-44720'},
        # Surgery 5 - UKA
        {'surgery_id': 5, 'implant_type_id': 5, 'manufacturer_id': 4, 'model': 'Oxford Partial', 'reference_number': 'SN-2025-22331', 'size': 'Size 3', 'lot_number': 'LOT-77890'},
    ]

    for i_data in sample_implants:
        implant = Implant(**i_data)
        db.session.add(implant)

    db.session.commit()

    # === Enhance sample surgeries with orthopedic fields, complications, outpatient, and research projects ===
    # Update existing surgeries with proper metadata
    surgery_updates = {
        1: {'joint': 'Hip', 'side': 'Right', 'surgery_type': 'Primary', 'outpatient': False,
            'complications': {'deep_periprosthetic_joint_infection': 'yes', 'readmission': 'yes'}},
        2: {'joint': 'Knee', 'side': 'Left', 'surgery_type': 'Primary', 'outpatient': True,
            'complications': {'stiffness': 'yes'}},
        3: {'joint': 'Hip', 'side': 'Left', 'surgery_type': 'Revision', 'revision_reason': 'Aseptic',
            'outpatient': False, 'complications': {'reoperation': 'yes', 'revision': 'yes'}},
        4: {'joint': 'Knee', 'side': 'Right', 'surgery_type': 'Primary', 'outpatient': False},
        5: {'joint': 'Knee', 'side': 'Left', 'surgery_type': 'Primary', 'outpatient': True},
    }

    for sid, updates in surgery_updates.items():
        s = Surgery.query.get(sid)
        if s:
            for key, val in updates.items():
                if key == 'complications':
                    s.complications = val
                else:
                    setattr(s, key, val)

    db.session.commit()

    # Create Research Projects (if not exist)
    research_data = [
        {'name': 'OA-2025-Registry', 'sponsor': 'NIH', 'description': 'Long-term outcomes in primary joint arthroplasty'},
        {'name': 'REV-2024-Study', 'sponsor': 'Industry', 'description': 'Revision burden and outcomes in THA/TKA'},
        {'name': 'Outpatient-Joints', 'sponsor': 'AAHKS', 'description': 'Safety and outcomes of same-day discharge joint replacement'},
        {'name': 'Infection-Prevention', 'sponsor': 'CDC', 'description': 'Reducing periprosthetic joint infection rates'},
    ]
    for rp_data in research_data:
        if not ResearchProject.query.filter_by(name=rp_data['name']).first():
            db.session.add(ResearchProject(**rp_data))
    db.session.commit()

    # Link multiple research projects to some surgeries
    rp_oa = ResearchProject.query.filter_by(name='OA-2025-Registry').first()
    rp_rev = ResearchProject.query.filter_by(name='REV-2024-Study').first()
    rp_out = ResearchProject.query.filter_by(name='Outpatient-Joints').first()
    rp_inf = ResearchProject.query.filter_by(name='Infection-Prevention').first()

    s1 = Surgery.query.get(1)
    s2 = Surgery.query.get(2)
    s3 = Surgery.query.get(3)
    s4 = Surgery.query.get(4)
    s5 = Surgery.query.get(5)

    if rp_oa:
        if rp_oa not in s1.research_projects: s1.research_projects.append(rp_oa)
        if rp_oa not in s2.research_projects: s2.research_projects.append(rp_oa)
    if rp_rev:
        if rp_rev not in s3.research_projects: s3.research_projects.append(rp_rev)
        if rp_rev not in s1.research_projects: s1.research_projects.append(rp_rev)  # multiple on surgery 1
    if rp_out:
        if rp_out not in s2.research_projects: s2.research_projects.append(rp_out)
        if rp_out not in s5.research_projects: s5.research_projects.append(rp_out)
    if rp_inf:
        if rp_inf not in s3.research_projects: s3.research_projects.append(rp_inf)

    db.session.commit()

    # Seed Implant Catalog (Master list searchable by catalog number)
    if ImplantCatalog.query.first() is None:
        catalog_data = [
            # === HIP IMPLANTS ===
            # Stryker Hip
            {'catalog_number': 'STR-ACC-5', 'implant_type_id': 3, 'manufacturer_id': 1, 'model': 'Accolade II', 'design': 'Cementless', 'fixation': 'Cementless', 'side': 'N/A', 'size': 'Size 5', 'description': 'Primary cementless femoral stem'},
            {'catalog_number': 'STR-TRI-54', 'implant_type_id': 1, 'manufacturer_id': 1, 'model': 'Trident II', 'design': 'Porous', 'fixation': 'Cementless', 'side': 'N/A', 'size': '54mm', 'description': 'Acetabular shell with porous coating'},
            {'catalog_number': 'STR-LFIT-32', 'implant_type_id': 4, 'manufacturer_id': 1, 'model': 'LFIT Anatomic', 'design': 'Ceramic', 'fixation': 'N/A', 'side': 'N/A', 'size': '32mm', 'description': 'Ceramic femoral head, +0 offset'},
            
            # DePuy Synthes Hip
            {'catalog_number': 'DPS-PIN-54', 'implant_type_id': 1, 'manufacturer_id': 3, 'model': 'Pinnacle', 'design': 'Porous', 'fixation': 'Cementless', 'side': 'N/A', 'size': '54mm', 'description': 'Acetabular shell, multi-hole'},
            {'catalog_number': 'DPS-ART-32', 'implant_type_id': 4, 'manufacturer_id': 3, 'model': 'Articul/Eze', 'design': 'Metal', 'fixation': 'N/A', 'side': 'N/A', 'size': '32mm', 'description': 'Cobalt-chrome femoral head'},
            
            # === KNEE IMPLANTS ===
            # Zimmer Biomet Knee
            {'catalog_number': 'ZIM-PER-7', 'implant_type_id': 5, 'manufacturer_id': 2, 'model': 'Persona CR', 'design': 'CR', 'fixation': 'Cemented', 'side': 'N/A', 'size': 'Size 7', 'description': 'Cruciate retaining femoral component'},
            {'catalog_number': 'ZIM-TIB-7', 'implant_type_id': 6, 'manufacturer_id': 2, 'model': 'Persona Tibial', 'design': 'Modular', 'fixation': 'Cemented', 'side': 'N/A', 'size': 'Size 7', 'description': 'Tibial baseplate, modular'},
            {'catalog_number': 'ZIM-INS-10', 'implant_type_id': 7, 'manufacturer_id': 2, 'model': 'Persona PS Insert', 'design': 'PS', 'fixation': 'N/A', 'side': 'N/A', 'size': '10mm', 'description': 'Posterior stabilized tibial insert'},
            {'catalog_number': 'ZIM-PAT-32', 'implant_type_id': 8, 'manufacturer_id': 2, 'model': 'Persona Patella', 'design': 'Dome', 'fixation': 'Cemented', 'side': 'N/A', 'size': '32mm', 'description': 'Patellar button, 3-pegged'},
            
            # Smith & Nephew Knee (for variety)
            {'catalog_number': 'SN-LEG-6', 'implant_type_id': 5, 'manufacturer_id': 4, 'model': 'Legion CR', 'design': 'CR', 'fixation': 'Cementless', 'side': 'Left', 'size': 'Size 6', 'description': 'Left femoral component, cementless'},
            {'catalog_number': 'SN-LEG-6R', 'implant_type_id': 5, 'manufacturer_id': 4, 'model': 'Legion CR', 'design': 'CR', 'fixation': 'Cementless', 'side': 'Right', 'size': 'Size 6', 'description': 'Right femoral component, cementless'},
        ]
        for c in catalog_data:
            db.session.add(ImplantCatalog(**c))
        db.session.commit()

    print("✓ Initial data seeded successfully")

def get_all_lookups():
    """Return all lookup data for templates (genders removed - now hardcoded Male/Female)"""
    return {
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
    
    # Research Projects enrollment (unique patients per project)
    research_enrollment = db.session.query(
        ResearchProject.name,
        ResearchProject.enrollment_goal,
        db.func.count(db.distinct(Patient.id)).label('patient_count')
    ).join(
        surgery_research_projects, ResearchProject.id == surgery_research_projects.c.research_project_id
    ).join(
        Surgery, Surgery.id == surgery_research_projects.c.surgery_id
    ).join(
        Patient, Patient.id == Surgery.patient_id
    ).group_by(ResearchProject.name, ResearchProject.enrollment_goal).order_by(ResearchProject.name).all()
    
    # Complication & Outcome Metrics
    all_surgeries = Surgery.query.all()
    total_surgeries = len(all_surgeries)
    
    if total_surgeries > 0:
        # Overall complication rate (any 'yes' in complications JSON)
        surgeries_with_any_complication = sum(
            1 for s in all_surgeries 
            if s.complications and any(v == 'yes' for v in s.complications.values())
        )
        # Deep periprosthetic joint infection
        deep_infection_count = sum(
            1 for s in all_surgeries 
            if s.complications and s.complications.get('deep_periprosthetic_joint_infection') == 'yes'
        )
        # 30-day readmission (note: field is "readmission" per 90-day definition in Hip/Knee Society)
        readmission_30d_count = sum(
            1 for s in all_surgeries 
            if s.complications and s.complications.get('readmission') == 'yes'
        )
        # Reoperation rate
        reoperation_count = sum(
            1 for s in all_surgeries 
            if s.complications and s.complications.get('reoperation') == 'yes'
        )
        
        stats['complication_rate'] = round((surgeries_with_any_complication / total_surgeries) * 100, 1)
        stats['deep_infection_rate'] = round((deep_infection_count / total_surgeries) * 100, 1)
        stats['readmission_30d_rate'] = round((readmission_30d_count / total_surgeries) * 100, 1)
        stats['reoperation_rate'] = round((reoperation_count / total_surgeries) * 100, 1) if total_surgeries > 0 else 0

        # Stratified Reoperation Rates (for dashboard UI and research insights)
        # By Joint
        hip_surgeries = sum(1 for s in all_surgeries if s.joint == 'Hip')
        reop_hip_count = sum(
            1 for s in all_surgeries 
            if s.joint == 'Hip' and s.complications and s.complications.get('reoperation') == 'yes'
        )
        stats['reop_hip_rate'] = round((reop_hip_count / hip_surgeries * 100), 1) if hip_surgeries > 0 else 0

        knee_surgeries = sum(1 for s in all_surgeries if s.joint == 'Knee')
        reop_knee_count = sum(
            1 for s in all_surgeries 
            if s.joint == 'Knee' and s.complications and s.complications.get('reoperation') == 'yes'
        )
        stats['reop_knee_rate'] = round((reop_knee_count / knee_surgeries * 100), 1) if knee_surgeries > 0 else 0

        # By Surgery Type (Primary vs Revision)
        primary_surgeries = sum(1 for s in all_surgeries if getattr(s, 'surgery_type', None) == 'Primary')
        reop_primary_count = sum(
            1 for s in all_surgeries 
            if getattr(s, 'surgery_type', None) == 'Primary' and s.complications and s.complications.get('reoperation') == 'yes'
        )
        stats['reop_primary_rate'] = round((reop_primary_count / primary_surgeries * 100), 1) if primary_surgeries > 0 else 0

        revision_surgeries = sum(1 for s in all_surgeries if getattr(s, 'surgery_type', None) == 'Revision')
        reop_revision_count = sum(
            1 for s in all_surgeries 
            if getattr(s, 'surgery_type', None) == 'Revision' and s.complications and s.complications.get('reoperation') == 'yes'
        )
        stats['reop_revision_rate'] = round((reop_revision_count / revision_surgeries * 100), 1) if revision_surgeries > 0 else 0

        # Revision Burden (% of surgeries that are revisions)
        revision_count = sum(1 for s in all_surgeries if getattr(s, 'surgery_type', None) == 'Revision')
        stats['revision_burden'] = round((revision_count / total_surgeries) * 100, 1)

        # % Outpatient Joints (THA, TKA, UKA that were outpatient/same-day)
        joint_keywords = ['Hip', 'Knee', 'UKA']
        joint_surgeries = [
            s for s in all_surgeries 
            if s.procedure_type and any(kw in (s.procedure_type.name or '') for kw in joint_keywords)
        ]
        outpatient_joints = sum(1 for s in joint_surgeries if getattr(s, 'outpatient', False))
        stats['outpatient_joint_percent'] = round((outpatient_joints / len(joint_surgeries) * 100), 1) if joint_surgeries else 0
    else:
        stats['complication_rate'] = 0
        stats['deep_infection_rate'] = 0
        stats['readmission_30d_rate'] = 0
        stats['reoperation_rate'] = 0
        stats['reop_hip_rate'] = 0
        stats['reop_knee_rate'] = 0
        stats['reop_primary_rate'] = 0
        stats['reop_revision_rate'] = 0
        stats['revision_burden'] = 0
        stats['outpatient_joint_percent'] = 0
    
    return render_template('index.html', 
                          stats=stats, 
                          recent_surgeries=recent_surgeries,
                          top_procedures=top_procedures,
                          lookups=lookups,
                          research_enrollment=research_enrollment)

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
        sex = request.form.get('sex', '').strip()
        phone = request.form.get('phone', '').strip() or None
        email = request.form.get('email', '').strip() or None

        if not all([mrn, first_name, last_name, dob_str, sex]):
            flash('Please fill in all required fields (MRN, Name, DOB, Sex)', 'danger')
            return redirect(url_for('patients_list'))

        dob = datetime.strptime(dob_str, '%Y-%m-%d').date()

        patient = Patient(
            mrn=mrn,
            first_name=first_name,
            last_name=last_name,
            dob=dob,
            sex=sex,
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
        patient.sex = request.form.get('sex', patient.sex).strip()
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
        surgeon_id = request.form.get('surgeon_id', type=int)
        hospital_id = request.form.get('hospital_id', type=int)
        notes = request.form.get('notes', '').strip() or None

        # New ortho fields (Procedure Type is now calculated)
        joint = request.form.get('joint')
        side = request.form.get('side')
        surgery_type = request.form.get('surgery_type')
        revision_reason = request.form.get('revision_reason', '').strip() or None
        primary_type = request.form.get('primary_type')

        if not all([patient_id, surgery_date_str, side, joint, surgery_type]):
            flash('Patient, Date, Side, Joint and Surgery Type are required.', 'danger')
            return redirect(request.referrer or url_for('patients_list'))

        surgery_date = datetime.strptime(surgery_date_str, '%Y-%m-%d').date()

        # Calculate Procedure Type (and create if new name)
        proc = get_or_create_procedure_type(side, joint, surgery_type, primary_type)
        if not proc:
            flash('Could not calculate Procedure Type. Ensure all fields (including Primary Type for Primary surgeries) are selected.', 'danger')
            return redirect(request.referrer or url_for('patients_list'))

        surgery = Surgery(
            patient_id=patient_id,
            surgery_date=surgery_date,
            procedure_type_id=proc.id,
            surgeon_id=surgeon_id,
            hospital_id=hospital_id,
            notes=notes,
            # New fields
            joint=joint,
            side=side,
            surgery_type=surgery_type,
            revision_reason=revision_reason
            # operating_room and duration_minutes deprecated/removed from form
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
    
    research_projects = ResearchProject.query.order_by(ResearchProject.name).all()
    
    missing_implants = get_missing_mandatory_implants(surgery)

    return render_template('surgery_detail.html', 
                          surgery=surgery, 
                          patient=patient,
                          implants=implants,
                          lookups=lookups,
                          research_projects=research_projects,
                          missing_implants=missing_implants)

@app.route('/surgeries/<int:surgery_id>/edit', methods=['POST'])
def edit_surgery(surgery_id):
    """Edit surgery details"""
    surgery = Surgery.query.get_or_404(surgery_id)
    try:
        surgery_date_str = request.form.get('surgery_date')
        if surgery_date_str:
            surgery.surgery_date = datetime.strptime(surgery_date_str, '%Y-%m-%d').date()
        surgery.surgeon_id = request.form.get('surgeon_id', type=int) or surgery.surgeon_id
        surgery.hospital_id = request.form.get('hospital_id', type=int) or surgery.hospital_id
        surgery.notes = request.form.get('notes', '').strip() or None

        # Update ortho fields and recalculate procedure type
        joint = request.form.get('joint') or surgery.joint
        side = request.form.get('side') or surgery.side
        surgery_type = request.form.get('surgery_type') or surgery.surgery_type
        revision_reason = request.form.get('revision_reason', '').strip() or surgery.revision_reason
        primary_type = request.form.get('primary_type')

        proc = get_or_create_procedure_type(side, joint, surgery_type, primary_type)
        if proc:
            surgery.procedure_type_id = proc.id
        surgery.joint = joint
        surgery.side = side
        surgery.surgery_type = surgery_type
        surgery.revision_reason = revision_reason
        
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
        reference_number = request.form.get('reference_number', '').strip() or None
        size = request.form.get('size', '').strip() or None
        lot_number = request.form.get('lot_number', '').strip() or None
        notes = request.form.get('notes', '').strip() or None

        if not surgery_id:
            flash('Surgery ID is required.', 'danger')
            return redirect(request.referrer or url_for('patients_list'))

        surgery = Surgery.query.get(surgery_id)
        if surgery and surgery.surgery_type == 'Primary' and surgery.joint in ('Hip', 'Knee'):
            # Enforce one of each specific component for primary hip/knee
            existing = Implant.query.filter_by(
                surgery_id=surgery_id,
                implant_type_id=implant_type_id
            ).first()
            if existing:
                it_name = existing.implant_type.name if existing.implant_type else 'this component type'
                flash(f'Only one {it_name} is allowed for a Primary {surgery.joint} surgery.', 'danger')
                return redirect(url_for('surgery_detail', surgery_id=surgery_id))

        implant = Implant(
            surgery_id=surgery_id,
            implant_type_id=implant_type_id,
            manufacturer_id=manufacturer_id,
            model=model,
            reference_number=reference_number,
            size=size,
            lot_number=lot_number,
            notes=notes
        )
        db.session.add(implant)
        db.session.commit()

        # Check if this completed the mandatory set for Primary Hip/Knee
        surgery = Surgery.query.get(surgery_id)
        still_missing = get_missing_mandatory_implants(surgery)
        if surgery and surgery.surgery_type == 'Primary' and not still_missing:
            flash('All mandatory implants have been added for this Primary {} surgery!'.format(surgery.joint), 'success')
        else:
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
        implant.reference_number = request.form.get('reference_number', '').strip() or None
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
    research_projects = ResearchProject.query.order_by(ResearchProject.name).all()
    return render_template('lookups.html', lookups=lookups, research_projects=research_projects)

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


@app.route('/lookups/<string:table>/<int:entry_id>/edit', methods=['POST'])
def edit_lookup(table, entry_id):
    """Edit a lookup entry"""
    model_map = {
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

    entry = model.query.get_or_404(entry_id)
    new_name = request.form.get('name', '').strip()
    new_specialty = request.form.get('specialty', '').strip() or None

    if not new_name:
        flash('Name is required.', 'danger')
        return redirect(url_for('lookups'))

    try:
        entry.name = new_name
        if table == 'surgeons' and hasattr(entry, 'specialty'):
            entry.specialty = new_specialty
        db.session.commit()
        flash(f'{table.replace("_", " ").title()[:-1]} updated successfully!', 'success')
    except IntegrityError:
        db.session.rollback()
        flash(f'A {table.replace("_", " ")[:-1]} with that name already exists.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating: {str(e)}', 'danger')

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


# ---------- Research Projects inside Tables Management ----------
@app.route('/lookups/research-projects/add', methods=['POST'])
def add_research_project_from_lookups():
    """Add a new research project from the Tables page"""
    name = request.form.get('name', '').strip()
    sponsor = request.form.get('sponsor', '').strip() or None
    description = request.form.get('description', '').strip() or None
    enrollment_goal = request.form.get('enrollment_goal', type=int) or None

    if not name:
        flash('Project name is required.', 'danger')
        return redirect(url_for('lookups'))

    if ResearchProject.query.filter_by(name=name).first():
        flash('A research project with this name already exists.', 'danger')
        return redirect(url_for('lookups'))

    project = ResearchProject(name=name, sponsor=sponsor, description=description, enrollment_goal=enrollment_goal)
    db.session.add(project)
    db.session.commit()
    flash(f'Research project "{name}" created successfully.', 'success')
    return redirect(url_for('lookups') + '#research')


@app.route('/lookups/research-projects/<int:project_id>/edit', methods=['POST'])
def edit_research_project(project_id):
    """Edit a research project from the Tables page"""
    project = ResearchProject.query.get_or_404(project_id)
    try:
        project.name = request.form.get('name', '').strip()
        project.sponsor = request.form.get('sponsor', '').strip() or None
        project.description = request.form.get('description', '').strip() or None
        project.enrollment_goal = request.form.get('enrollment_goal', type=int) or None

        db.session.commit()
        flash(f'Research project "{project.name}" updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating research project: {str(e)}', 'danger')

    return redirect(url_for('lookups') + '#research')


@app.route('/lookups/research-projects/<int:project_id>/delete', methods=['POST'])
def delete_research_project_from_lookups(project_id):
    """Delete a research project from the Tables page"""
    project = ResearchProject.query.get_or_404(project_id)
    name = project.name
    try:
        db.session.delete(project)
        db.session.commit()
        flash(f'Research project "{name}" deleted.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Cannot delete: This project is still linked to surgeries. {str(e)}', 'danger')
    return redirect(url_for('lookups') + '#research')


# ---------- IMPLANT MASTER (Dedicated CRUD page) ----------
@app.route('/implant-master')
def implant_master():
    """Dedicated page to manage the Implant Catalog (Master List)"""
    search = request.args.get('search', '').strip()
    query = ImplantCatalog.query
    
    if search:
        query = query.filter(
            or_(
                ImplantCatalog.catalog_number.ilike(f'%{search}%'),
                ImplantCatalog.model.ilike(f'%{search}%'),
                ImplantCatalog.design.ilike(f'%{search}%')
            )
        )
    
    catalog = query.order_by(ImplantCatalog.catalog_number).all()
    lookups = get_all_lookups()
    
    return render_template('implant_master.html', 
                          catalog=catalog, 
                          search=search,
                          lookups=lookups)

@app.route('/implant-master/add', methods=['POST'])
def add_implant_catalog():
    """Add a new implant to the master catalog"""
    try:
        catalog_number = request.form.get('catalog_number', '').strip().upper()
        implant_type_id = request.form.get('implant_type_id', type=int)
        manufacturer_id = request.form.get('manufacturer_id', type=int)
        model = request.form.get('model', '').strip()
        design = request.form.get('design', '').strip() or None
        fixation = request.form.get('fixation', '').strip() or None
        side = request.form.get('side', '').strip() or None
        size = request.form.get('size', '').strip() or None
        description = request.form.get('description', '').strip() or None

        if not all([catalog_number, implant_type_id, manufacturer_id, model]):
            flash('Catalog Number, Implant Type, Manufacturer, and Model are required.', 'danger')
            return redirect(url_for('implant_master'))

        # Check for duplicate catalog number
        if ImplantCatalog.query.filter_by(catalog_number=catalog_number).first():
            flash(f'An implant with catalog number {catalog_number} already exists.', 'danger')
            return redirect(url_for('implant_master'))

        new_implant = ImplantCatalog(
            catalog_number=catalog_number,
            implant_type_id=implant_type_id,
            manufacturer_id=manufacturer_id,
            model=model,
            design=design,
            fixation=fixation,
            side=side,
            size=size,
            description=description
        )
        db.session.add(new_implant)
        db.session.commit()
        flash(f'Implant {catalog_number} added to master catalog successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding implant: {str(e)}', 'danger')
    
    return redirect(url_for('implant_master'))

@app.route('/implant-master/<int:catalog_id>/edit', methods=['POST'])
def edit_implant_catalog(catalog_id):
    """Edit an existing catalog entry"""
    catalog = ImplantCatalog.query.get_or_404(catalog_id)
    try:
        catalog.catalog_number = request.form.get('catalog_number', catalog.catalog_number).strip().upper()
        catalog.implant_type_id = request.form.get('implant_type_id', type=int) or catalog.implant_type_id
        catalog.manufacturer_id = request.form.get('manufacturer_id', type=int) or catalog.manufacturer_id
        catalog.model = request.form.get('model', catalog.model).strip()
        catalog.design = request.form.get('design', '').strip() or None
        catalog.fixation = request.form.get('fixation', '').strip() or None
        catalog.side = request.form.get('side', '').strip() or None
        catalog.size = request.form.get('size', '').strip() or None
        catalog.description = request.form.get('description', '').strip() or None
        
        db.session.commit()
        flash(f'Implant {catalog.catalog_number} updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating implant: {str(e)}', 'danger')
    
    return redirect(url_for('implant_master'))

@app.route('/implant-master/<int:catalog_id>/delete', methods=['POST'])
def delete_implant_catalog(catalog_id):
    """Delete an implant from the master catalog"""
    catalog = ImplantCatalog.query.get_or_404(catalog_id)
    cat_num = catalog.catalog_number
    try:
        db.session.delete(catalog)
        db.session.commit()
        flash(f'Implant {cat_num} deleted from master catalog.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting implant: {str(e)}', 'danger')
    return redirect(url_for('implant_master'))

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

# ---------- Implant Catalog Search API ----------
@app.route('/api/implant-catalog/search')
def search_implant_catalog():
    """Search implant catalog by catalog number or model.
    Optional: filter by joint (Hip/Knee) for procedure-based filtering.
    """
    q = request.args.get('q', '').strip()
    joint = request.args.get('joint', '').strip()  # 'Hip' or 'Knee'
    
    if not q or len(q) < 2:
        return jsonify([])
    
    # Base query
    query = ImplantCatalog.query.filter(
        or_(
            ImplantCatalog.catalog_number.ilike(f'%{q}%'),
            ImplantCatalog.model.ilike(f'%{q}%')
        )
    )
    
    # Procedure-based filtering: only show relevant implants for the surgery type
    if joint == 'Hip':
        # Hip implant types: Acetabular Shell (1), Acetabular Liner (2), Femoral Stem (3), Femoral Head (4)
        hip_type_ids = [1, 2, 3, 4]
        query = query.filter(ImplantCatalog.implant_type_id.in_(hip_type_ids))
    elif joint == 'Knee':
        # Knee implant types: Femoral Component (5), Tibial Component (6), Tibial Liner (7), Patellar Component (8)
        knee_type_ids = [5, 6, 7, 8]
        query = query.filter(ImplantCatalog.implant_type_id.in_(knee_type_ids))
    
    results = query.limit(15).all()
    
    return jsonify([{
        'id': c.id,
        'catalog_number': c.catalog_number,
        'implant_type_id': c.implant_type_id,
        'implant_type': c.implant_type.name if c.implant_type else '',
        'manufacturer_id': c.manufacturer_id,
        'manufacturer': c.manufacturer.name if c.manufacturer else '',
        'model': c.model or '',
        'design': c.design or '',
        'fixation': c.fixation or '',
        'side': c.side or '',
        'size': c.size or '',
        'description': c.description or ''
    } for c in results])


# ---------- Elixhauser Comorbidities ----------
@app.route('/surgeries/<int:surgery_id>/comorbidities', methods=['POST'])
def save_comorbidities(surgery_id):
    """Save Elixhauser comorbidities for a surgery"""
    surgery = Surgery.query.get_or_404(surgery_id)
    try:
        comorbidities = {}
        score = 0
        
        # Full van Walraven Elixhauser weights (30 comorbidities)
        weights = {
            'congestive_heart_failure': 7,
            'cardiac_arrhythmia': 5,
            'valvular_disease': 3,
            'pulmonary_circulation': 6,
            'peripheral_vascular': 2,
            'hypertension': 1,
            'paralysis': 7,
            'neurological_disorders': 6,
            'chronic_pulmonary': 3,
            'diabetes': 0,
            'diabetes_complications': 1,
            'hypothyroidism': 0,
            'renal_failure': 5,
            'liver_disease': 11,
            'peptic_ulcer': 0,
            'aids_hiv': 0,
            'lymphoma': 9,
            'metastatic_cancer': 14,
            'solid_tumor': 7,
            'rheumatoid_arthritis': 0,
            'coagulopathy': 3,
            'obesity': 0,
            'weight_loss': 6,
            'fluid_electrolyte': 5,
            'blood_loss_anemia': 3,
            'deficiency_anemia': 3,
            'alcohol_abuse': 0,
            'drug_abuse': 4,
            'psychoses': 5,
            'depression': 0
        }
        
        for key, weight in weights.items():
            value = request.form.get(key, 'no')
            comorbidities[key] = value
            if value == 'yes':
                score += weight
        
        surgery.comorbidities = comorbidities
        surgery.elixhauser_score = score
        db.session.commit()
        
        flash(f'Comorbidities saved. Elixhauser Score: {score}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving comorbidities: {str(e)}', 'danger')
    
    return redirect(url_for('surgery_detail', surgery_id=surgery_id))


# ---------- Research Projects ----------
@app.route('/surgery/<int:surgery_id>/research-projects/add', methods=['POST'])
def add_research_project_to_surgery(surgery_id):
    """Assign one or more research projects to a surgery (supports multiple dropdowns)"""
    surgery = Surgery.query.get_or_404(surgery_id)
    # Support multiple from dynamic dropdowns or single legacy
    project_ids = request.form.getlist('research_project_ids')
    if not project_ids:
        single_id = request.form.get('research_project_id', type=int)
        if single_id:
            project_ids = [str(single_id)]

    if not project_ids or all(not pid for pid in project_ids):
        flash('Please select at least one research project.', 'danger')
        return redirect(url_for('surgery_detail', surgery_id=surgery_id))

    added = []
    skipped = []
    for pid_str in project_ids:
        if not pid_str:
            continue
        try:
            pid = int(pid_str)
            project = ResearchProject.query.get(pid)
            if project and project not in surgery.research_projects:
                surgery.research_projects.append(project)
                added.append(project.name)
            else:
                skipped.append(project.name if project else f'ID {pid}')
        except (ValueError, TypeError):
            skipped.append(f'invalid ID')

    if added:
        db.session.commit()
        flash(f'Added research project(s): {", ".join(added)}', 'success')
    if skipped:
        flash(f'Skipped (already assigned or invalid): {", ".join(skipped)}', 'info')
    if not added and not skipped:
        flash('No new research projects were added.', 'warning')

    return redirect(url_for('surgery_detail', surgery_id=surgery_id))


@app.route('/surgery/<int:surgery_id>/research-projects/<int:project_id>/remove', methods=['POST'])
def remove_research_project_from_surgery(surgery_id, project_id):
    """Remove a research project from a surgery"""
    surgery = Surgery.query.get_or_404(surgery_id)
    project = ResearchProject.query.get_or_404(project_id)

    if project in surgery.research_projects:
        surgery.research_projects.remove(project)
        db.session.commit()
        flash(f'Research project "{project.name}" removed from this surgery.', 'warning')

    return redirect(url_for('surgery_detail', surgery_id=surgery_id))


# ---------- Complications ----------
@app.route('/surgeries/<int:surgery_id>/complications', methods=['POST'])
def save_complications(surgery_id):
    """Save complications for a surgery"""
    surgery = Surgery.query.get_or_404(surgery_id)
    try:
        complications = {}
        
        # Full standardized complications from Knee Society (TKA) and Hip Society (THA)
        complication_keys = [
            'bleeding',
            'wound_complication',
            'thromboembolic_disease',
            'neural_deficit',
            'vascular_injury',
            'medial_collateral_ligament_injury',
            'instability',
            'malalignment',
            'stiffness',
            'deep_periprosthetic_joint_infection',
            'periprosthetic_fracture',
            'extensor_mechanism_disruption',
            'patellofemoral_dislocation',
            'tibiofemoral_dislocation',
            'bearing_surface_wear',
            'osteolysis',
            'implant_loosening',
            'implant_fracture_tibial_insert_dissociation',
            'cup_liner_dissociation',
            'abductor_muscle_disruption',
            'heterotopic_ossification',
            'reoperation',
            'revision',
            'readmission',
            'death'
        ]
        
        for key in complication_keys:
            value = request.form.get(key, 'no')
            date_val = request.form.get(f"{key}_date") or None
            if value == 'yes':
                complications[key] = {'value': 'yes', 'date': date_val}
            else:
                complications[key] = {'value': 'no', 'date': None}
        
        surgery.complications = complications
        db.session.commit()
        
        flash('Complications saved successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving complications: {str(e)}', 'danger')
    
    return redirect(url_for('surgery_detail', surgery_id=surgery_id))


# ---------- REPORTS & CSV EXPORTS ----------
@app.route('/reports')
def reports():
    """Reports dashboard with CSV export options"""
    stats = {
        'patients': Patient.query.count(),
        'surgeries': Surgery.query.count(),
        'implants': Implant.query.count(),
    }
    return render_template('reports.html', stats=stats)


@app.route('/reports/export/patients')
def export_patients_csv():
    """Export all patients as CSV"""
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['MRN', 'First Name', 'Last Name', 'Date of Birth', 'Sex', 'Age', 'Weight (kg)', 'Height (cm)', 'BMI', 'Race', 'Ethnicity', 'Phone', 'Email', 'Created'])

    for p in Patient.query.order_by(Patient.last_name, Patient.first_name).all():
        cw.writerow([
            p.mrn,
            p.first_name,
            p.last_name,
            p.dob.isoformat() if p.dob else '',
            p.sex or '',
            p.age,
            p.weight_kg or '',
            p.height_cm or '',
            p.bmi or '',
            p.race or '',
            p.ethnicity or '',
            p.phone or '',
            p.email or '',
            p.created_at.isoformat() if p.created_at else ''
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=um_registry_patients.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@app.route('/reports/export/surgeries')
def export_surgeries_csv():
    """Export all surgeries with patient and procedure details (using algorithm names)"""
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Surgery ID', 'Patient MRN', 'Patient Name', 'Surgery Date', 'Procedure Type (Standardized)', 'Joint', 'Side', 'Surgery Type', 'Revision Reason', 'Surgeon', 'Hospital', 'Notes', 'Created'])

    for s in Surgery.query.order_by(Surgery.surgery_date.desc()).all():
        cw.writerow([
            s.id,
            s.patient.mrn if s.patient else '',
            s.patient.full_name if s.patient else '',
            s.surgery_date.isoformat() if s.surgery_date else '',
            s.procedure_type.name if s.procedure_type else '',
            s.joint or '',
            s.side or '',
            s.surgery_type or '',
            s.revision_reason or '',
            s.surgeon.name if s.surgeon else '',
            s.hospital.name if s.hospital else '',
            (s.notes or '').replace('\n', ' ').strip(),
            s.created_at.isoformat() if s.created_at else ''
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=um_registry_surgeries.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@app.route('/reports/export/implants')
def export_implants_csv():
    """Export all implants linked to surgeries"""
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Implant ID', 'Surgery ID', 'Patient MRN', 'Patient Name', 'Surgery Date', 'Procedure', 'Implant Type', 'Manufacturer', 'Reference #', 'Size', 'Lot Number', 'Notes'])

    for imp in Implant.query.order_by(Implant.created_at.desc()).all():
        s = imp.surgery
        cw.writerow([
            imp.id,
            s.id if s else '',
            s.patient.mrn if s and s.patient else '',
            s.patient.full_name if s and s.patient else '',
            s.surgery_date.isoformat() if s and s.surgery_date else '',
            s.procedure_type.name if s and s.procedure_type else '',
            imp.implant_type.name if imp.implant_type else '',
            imp.manufacturer.name if imp.manufacturer else '',
            imp.reference_number or '',
            imp.size or '',
            imp.lot_number or '',
            (imp.notes or '').replace('\n', ' ').strip()
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=um_registry_implants.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@app.route('/reports/export/complications_dataset')
def export_complications_dataset_csv():
    """Export rich Complications Dataset for research & QI (one row per surgery).
    
    Includes:
    - Full surgery metadata + Elixhauser score + Research Project enrollment
    - Key complications expanded as separate Yes/No + Date columns (from Hip/Knee Society lists)
    - Full complications JSON as string column for advanced parsing / time-to-event analysis
    Ready for Excel, R, Python/Pandas, or statistical software.
    """
    si = io.StringIO()
    cw = csv.writer(si)
    
    # Key complications we expand into dedicated columns (high research/QI priority)
    # These come from the standardized Hip Society (2015) and Knee Society (2013) lists
    key_complication_keys = [
        'deep_periprosthetic_joint_infection',
        'reoperation',
        'readmission',
        'revision',
        'death',
        'instability',
        'periprosthetic_fracture',
        'wound_complication',
        'thromboembolic_disease',
        'bleeding',
        'implant_loosening',
        'stiffness',                    # Knee-specific
        'abductor_muscle_disruption',   # Hip-specific
        'heterotopic_ossification',     # Hip-specific
        'implant_fracture_tibial_insert_dissociation',
    ]
    
    # Build header
    header = [
        'Surgery_ID', 'Surgery_Date', 'Patient_MRN', 'Patient_Name', 'Patient_Age', 'Patient_Sex',
        'Joint', 'Side', 'Surgery_Type', 'Revision_Reason',
        'Surgeon', 'Hospital', 'Operating_Room', 'Duration_Minutes', 'Outpatient',
        'Procedure_Type_Standardized', 'Elixhauser_Score_van_Walraven',
        'Research_Projects_Enrolled', 'Number_of_Implants'
    ]
    
    for key in key_complication_keys:
        header.append(f'Comp_{key}')
        header.append(f'Comp_{key}_Date')
    
    header.append('Complications_Full_JSON')
    cw.writerow(header)
    
    # Fetch all surgeries with eager loading for performance
    surgeries = Surgery.query.options(
        db.joinedload(Surgery.patient),
        db.joinedload(Surgery.surgeon),
        db.joinedload(Surgery.hospital),
        db.joinedload(Surgery.procedure_type),
        db.joinedload(Surgery.implants),
        db.joinedload(Surgery.research_projects)
    ).order_by(Surgery.surgery_date.desc()).all()
    
    for s in surgeries:
        # Base metadata
        row = [
            s.id,
            s.surgery_date.isoformat() if s.surgery_date else '',
            s.patient.mrn if s.patient else '',
            s.patient.full_name if s.patient else '',
            s.patient.age if s.patient else '',
            s.patient.sex if s.patient else '',
            s.joint or '',
            s.side or '',
            s.surgery_type or '',
            s.revision_reason or '',
            s.surgeon.name if s.surgeon else '',
            s.hospital.name if s.hospital else '',
            s.operating_room or '',
            s.duration_minutes or '',
            'Yes' if getattr(s, 'outpatient', False) else 'No',
            s.procedure_type.name if s.procedure_type else '',
            s.elixhauser_score or 0,
        ]
        
        # Research projects (comma-separated for easy filtering in Excel)
        rp_names = [rp.name for rp in getattr(s, 'research_projects', [])]
        row.append(', '.join(rp_names) if rp_names else '')
        
        # Number of implants
        row.append(len(s.implants) if s.implants else 0)
        
        # Expand key complications + dates
        comps = s.complications or {}
        for key in key_complication_keys:
            raw_val = comps.get(key, '')
            
            if isinstance(raw_val, dict):
                # Future-proof for {"value": "yes", "date": "2025-..."} structure
                value = raw_val.get('value', '')
                date_val = raw_val.get('date', '') if value == 'yes' else ''
            else:
                # Current flat structure: 'yes' / 'no' / ''
                value = raw_val if raw_val in ('yes', 'no') else ''
                date_val = ''  # Dates not yet stored in flat model; ready for enhancement
            
            row.append(value)
            row.append(date_val)
        
        # Full JSON for researchers who want everything (parse with json.loads)
        full_json_str = json.dumps(comps, default=str, ensure_ascii=False) if comps else '{}'
        row.append(full_json_str)
        
        cw.writerow(row)
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=um_arthroplasty_complications_dataset.csv"
    output.headers["Content-type"] = "text/csv"
    return output


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

# ==================== DATABASE INITIALIZATION (runs on every startup - works with gunicorn) ====================
with app.app_context():
    db.create_all()
    seed_initial_data()

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