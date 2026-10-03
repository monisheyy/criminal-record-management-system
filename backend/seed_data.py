"""
AI-CRMS Synthetic Demo Data Seeder

Populates an EMPTY development database with fictional demo data.

* Never runs in production (APP_ENV=production refuses SEED_DEMO_DATA=true).
* Demo accounts use published passwords, so every one is flagged
  must_change_password and production start-up deactivates any account that
  still uses one of them.
* AI predictions are left PENDING: the seeder never fabricates human review
  decisions or audit history.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
import random
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app import models
from app.security import get_password_hash
import logging

# Plain-ASCII log output: emoji in print() crashed start-up on non-UTF-8 consoles.
log = logging.getLogger("ai_crms.seed")

CRIME_TYPES = [
    'Robbery', 'Assault', 'Murder', 'Drug Trafficking', 'Burglary',
    'Cybercrime', 'Fraud', 'Kidnapping', 'Arms Trafficking', 'Extortion',
    'Human Trafficking', 'Car Theft', 'Vandalism', 'Arson', 'Money Laundering'
]
CATEGORIES = {
    'Robbery': 'Violent', 'Assault': 'Violent', 'Murder': 'Violent',
    'Kidnapping': 'Violent', 'Drug Trafficking': 'Narcotics',
    'Arms Trafficking': 'Weapons', 'Human Trafficking': 'Organized Crime',
    'Fraud': 'Financial', 'Money Laundering': 'Financial', 'Extortion': 'Financial',
    'Burglary': 'Property', 'Car Theft': 'Property', 'Vandalism': 'Property',
    'Arson': 'Property', 'Cybercrime': 'Technology'
}
LOCATIONS = [
    'Downtown District', 'North End', 'Riverside Quarter', 'Industrial Zone',
    'Harbor Front', 'University Area', 'Eastgate', 'West Hills',
    'Central Market', 'Old Town'
]
THREAT_LEVELS = ['low', 'medium', 'high', 'critical']
PRIORITIES = ['low', 'normal', 'high', 'critical']

GANG_DATA = [
    {'name': 'Shadow Syndicate', 'alias': 'SS, The Shadows', 'territory': 'Downtown District, Harbor Front',
     'threat_level': 'critical', 'known_activities': 'Drug trafficking, money laundering, armed robbery',
     'member_count': 47},
    {'name': 'Red Serpents', 'alias': 'RS, Serpents', 'territory': 'North End, Industrial Zone',
     'threat_level': 'high', 'known_activities': 'Arms trafficking, extortion, vehicle theft',
     'member_count': 32},
    {'name': 'Iron Fist', 'alias': 'IF, The Fist', 'territory': 'Riverside Quarter, Eastgate',
     'threat_level': 'high', 'known_activities': 'Human trafficking, kidnapping, fraud',
     'member_count': 28},
    {'name': 'Night Wolves', 'alias': 'NW, Wolves', 'territory': 'West Hills, Old Town',
     'threat_level': 'medium', 'known_activities': 'Burglary, car theft, vandalism',
     'member_count': 19},
    {'name': 'Black Eagles', 'alias': 'BE, Eagles', 'territory': 'University Area, Central Market',
     'threat_level': 'medium', 'known_activities': 'Cybercrime, fraud, identity theft',
     'member_count': 15},
]

CRIMINALS_DATA = [
    {'first_name': 'Marcus', 'last_name': 'Vega', 'alias': 'El Jefe, The Boss',
     'gender': 'Male', 'nationality': 'Mexican', 'occupation': 'Business Owner (Front)',
     'crime_type': 'Drug Trafficking', 'prior_convictions': 4, 'gang_idx': 0, 'gang_rank': 'Leader',
     'is_wanted': True, 'threat_level': 'critical', 'risk_score': 92.5},
    {'first_name': 'Dmitri', 'last_name': 'Volkov', 'alias': 'The Wolf',
     'gender': 'Male', 'nationality': 'Russian', 'occupation': 'Arms Dealer',
     'crime_type': 'Arms Trafficking', 'prior_convictions': 3, 'gang_idx': 1, 'gang_rank': 'Lieutenant',
     'is_wanted': True, 'threat_level': 'critical', 'risk_score': 88.0},
    {'first_name': 'Sofia', 'last_name': 'Reyes', 'alias': 'La Tigresa',
     'gender': 'Female', 'nationality': 'Colombian', 'occupation': 'Nightclub Operator',
     'crime_type': 'Human Trafficking', 'prior_convictions': 2, 'gang_idx': 2, 'gang_rank': 'Captain',
     'is_wanted': True, 'threat_level': 'high', 'risk_score': 81.3},
    {'first_name': 'James', 'last_name': 'Morrow', 'alias': 'Jimmy Two-Face',
     'gender': 'Male', 'nationality': 'American', 'occupation': 'Unemployed',
     'crime_type': 'Robbery', 'prior_convictions': 5, 'gang_idx': None, 'gang_rank': None,
     'is_wanted': True, 'threat_level': 'high', 'risk_score': 76.8},
    {'first_name': 'Chen', 'last_name': 'Liu', 'alias': 'The Ghost',
     'gender': 'Male', 'nationality': 'Chinese', 'occupation': 'IT Consultant (Cover)',
     'crime_type': 'Cybercrime', 'prior_convictions': 1, 'gang_idx': 4, 'gang_rank': 'Specialist',
     'is_wanted': False, 'threat_level': 'high', 'risk_score': 71.2},
    {'first_name': 'Rania', 'last_name': 'Hassan', 'alias': 'Queen of Spades',
     'gender': 'Female', 'nationality': 'Egyptian', 'occupation': 'Accountant',
     'crime_type': 'Money Laundering', 'prior_convictions': 2, 'gang_idx': 0, 'gang_rank': 'Treasurer',
     'is_wanted': False, 'threat_level': 'high', 'risk_score': 68.5},
    {'first_name': 'Tony', 'last_name': 'Marchetti', 'alias': 'Fat Tony',
     'gender': 'Male', 'nationality': 'Italian', 'occupation': 'Restaurant Owner',
     'crime_type': 'Extortion', 'prior_convictions': 3, 'gang_idx': 1, 'gang_rank': 'Enforcer',
     'is_wanted': False, 'threat_level': 'high', 'risk_score': 65.0},
    {'first_name': 'Arjun', 'last_name': 'Patel', 'alias': 'AJ',
     'gender': 'Male', 'nationality': 'Indian', 'occupation': 'Taxi Driver',
     'crime_type': 'Drug Trafficking', 'prior_convictions': 1, 'gang_idx': None, 'gang_rank': None,
     'is_wanted': False, 'threat_level': 'medium', 'risk_score': 48.3},
    {'first_name': 'Elena', 'last_name': 'Stavros', 'alias': None,
     'gender': 'Female', 'nationality': 'Greek', 'occupation': 'Jewelry Store Owner',
     'crime_type': 'Fraud', 'prior_convictions': 2, 'gang_idx': 4, 'gang_rank': 'Associate',
     'is_wanted': False, 'threat_level': 'medium', 'risk_score': 44.7},
    {'first_name': 'Kevin', 'last_name': 'Walsh', 'alias': 'K-Dog',
     'gender': 'Male', 'nationality': 'Irish', 'occupation': 'Mechanic',
     'crime_type': 'Car Theft', 'prior_convictions': 2, 'gang_idx': 3, 'gang_rank': 'Member',
     'is_wanted': False, 'threat_level': 'medium', 'risk_score': 42.1},
    {'first_name': 'Priya', 'last_name': 'Nair', 'alias': None,
     'gender': 'Female', 'nationality': 'Indian', 'occupation': 'Bank Employee',
     'crime_type': 'Fraud', 'prior_convictions': 0, 'gang_idx': None, 'gang_rank': None,
     'is_wanted': False, 'threat_level': 'low', 'risk_score': 28.5},
    {'first_name': 'Gabriel', 'last_name': 'Santos', 'alias': 'Gabi',
     'gender': 'Male', 'nationality': 'Brazilian', 'occupation': 'Unemployed',
     'crime_type': 'Assault', 'prior_convictions': 3, 'gang_idx': None, 'gang_rank': None,
     'is_wanted': True, 'threat_level': 'high', 'risk_score': 77.4},
    {'first_name': 'Mei', 'last_name': 'Zhang', 'alias': 'Dragon Lady',
     'gender': 'Female', 'nationality': 'Chinese', 'occupation': 'Import/Export',
     'crime_type': 'Human Trafficking', 'prior_convictions': 1, 'gang_idx': 2, 'gang_rank': 'Associate',
     'is_wanted': True, 'threat_level': 'high', 'risk_score': 79.1},
    {'first_name': 'Boris', 'last_name': 'Petrov', 'alias': 'Boris the Bear',
     'gender': 'Male', 'nationality': 'Russian', 'occupation': 'Security Consultant',
     'crime_type': 'Murder', 'prior_convictions': 1, 'gang_idx': 1, 'gang_rank': 'Soldier',
     'is_wanted': True, 'threat_level': 'critical', 'risk_score': 95.2},
    {'first_name': 'Lucia', 'last_name': 'Morales', 'alias': 'Lucky',
     'gender': 'Female', 'nationality': 'Spanish', 'occupation': 'Casino Dealer',
     'crime_type': 'Money Laundering', 'prior_convictions': 1, 'gang_idx': 0, 'gang_rank': 'Associate',
     'is_wanted': False, 'threat_level': 'medium', 'risk_score': 52.3},
]

FIRST_NAMES = ['Ahmed', 'Carlos', 'David', 'Feng', 'Hassan', 'Igor', 'John', 'Kim',
               'Lara', 'Mohammed', 'Nadia', 'Oscar', 'Pedro', 'Rashid', 'Steve',
               'Tariq', 'Uma', 'Victor', 'Wang', 'Yusuf']
LAST_NAMES = ['Ahmed', 'Brown', 'Chen', 'Davis', 'Garcia', 'Hill', 'Jones',
              'Khan', 'Lee', 'Martinez', 'Nguyen', 'Okeke', 'Park', 'Rahman',
              'Singh', 'Taylor', 'Wang', 'Wilson', 'Yilmaz', 'Zhao']

MO_LIST = [
    'Operates at night, uses getaway vehicles',
    'Targets vulnerable elderly victims',
    'Uses digital communication to evade detection',
    'Works in small coordinated teams',
    'Exploits financial system loopholes',
    'Known to use violence when confronted',
    'Uses multiple fake identities',
    'Operates through legitimate business fronts',
]


def random_dob(min_age=20, max_age=60):
    days_ago = random.randint(min_age * 365, max_age * 365)
    return datetime.utcnow() - timedelta(days=days_ago)


def random_past(max_days=365 * 3):
    return datetime.utcnow() - timedelta(days=random.randint(1, max_days))


def seed_database(db: Session):
    log.info("Seeding AI-CRMS database...")

    # ── Users ────────────────────────────────────────────────────────────────
    log.info("  Creating users...")
    users_data = [
        {'username': 'admin', 'email': 'admin@acrms.gov', 'full_name': 'System Administrator',
         'role': models.UserRole.admin, 'badge_number': 'ADM-001', 'department': 'Administration',
         'password': 'admin123'},
        {'username': 'officer1', 'email': 'officer1@acrms.gov', 'full_name': 'Inspector Rajesh Kumar',
         'role': models.UserRole.investigating_officer, 'badge_number': 'OFF-101', 'department': 'Homicide',
         'password': 'officer123'},
        {'username': 'officer2', 'email': 'officer2@acrms.gov', 'full_name': 'Inspector Sarah Johnson',
         'role': models.UserRole.investigating_officer, 'badge_number': 'OFF-102', 'department': 'Narcotics',
         'password': 'officer123'},
        {'username': 'officer3', 'email': 'officer3@acrms.gov', 'full_name': 'Inspector Ali Hassan',
         'role': models.UserRole.investigating_officer, 'badge_number': 'OFF-103', 'department': 'Cybercrime',
         'password': 'officer123'},
        {'username': 'clerk1', 'email': 'clerk1@acrms.gov', 'full_name': 'Record Clerk Priya Sharma',
         'role': models.UserRole.record_clerk, 'badge_number': 'CLK-201', 'department': 'Records',
         'password': 'clerk123'},
        {'username': 'clerk2', 'email': 'clerk2@acrms.gov', 'full_name': 'Record Clerk David Osei',
         'role': models.UserRole.record_clerk, 'badge_number': 'CLK-202', 'department': 'Records',
         'password': 'clerk123'},
    ]

    created_users = []
    for u in users_data:
        user = models.User(
            username=u['username'],
            email=u['email'],
            full_name=u['full_name'],
            role=u['role'],
            badge_number=u['badge_number'],
            department=u['department'],
            hashed_password=get_password_hash(u['password']),
            is_active=True,
            must_change_password=True,
        )
        db.add(user)
        created_users.append(user)
    db.commit()
    for u in created_users:
        db.refresh(u)
    log.info(f"  Created {len(created_users)} users")

    # ── Gangs ─────────────────────────────────────────────────────────────────
    log.info("  Creating gangs...")
    created_gangs = []
    for g in GANG_DATA:
        gang = models.Gang(
            name=g['name'],
            alias=g['alias'],
            territory=g['territory'],
            threat_level=g['threat_level'],
            known_activities=g['known_activities'],
            member_count=g['member_count'],
            active_since=random_past(365 * 10),
            is_active=True,
        )
        db.add(gang)
        created_gangs.append(gang)
    db.commit()
    for g in created_gangs:
        db.refresh(g)
    log.info(f"  Created {len(created_gangs)} gangs")

    # ── Core Criminals ────────────────────────────────────────────────────────
    log.info("  Creating criminals...")
    created_criminals = []
    import string

    def gen_crn():
        return "CRN" + "".join(random.choices(string.digits, k=8))

    for i, cd in enumerate(CRIMINALS_DATA):
        crn = gen_crn()
        gang_id = created_gangs[cd['gang_idx']].id if cd['gang_idx'] is not None else None
        criminal = models.Criminal(
            crn=crn,
            first_name=cd['first_name'],
            last_name=cd['last_name'],
            alias=cd.get('alias'),
            date_of_birth=random_dob(25, 55),
            gender=cd.get('gender', 'Male'),
            nationality=cd.get('nationality', 'Unknown'),
            address=f"{random.randint(1, 999)} {random.choice(['Main St', 'Oak Ave', 'River Rd', 'Market Ln'])}, {random.choice(LOCATIONS)}",
            phone=f"+1-{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
            occupation=cd.get('occupation', 'Unknown'),
            crime_type=cd.get('crime_type'),
            crime_category=CATEGORIES.get(cd.get('crime_type', ''), 'Other'),
            prior_convictions=cd.get('prior_convictions', 0),
            modus_operandi=random.choice(MO_LIST),
            known_associates=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}, {random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            gang_id=gang_id,
            gang_rank=cd.get('gang_rank'),
            is_wanted=cd.get('is_wanted', False),
            is_incarcerated=random.random() < 0.2,
            threat_level=cd.get('threat_level', 'low'),
            risk_score=cd.get('risk_score', 0.0),
            created_by_id=created_users[4].id,  # clerk1
        )
        db.add(criminal)
        created_criminals.append(criminal)

    # Additional random criminals
    for j in range(20):
        crime_type = random.choice(CRIME_TYPES)
        crn = gen_crn()
        gang = random.choice(created_gangs) if random.random() < 0.35 else None
        criminal = models.Criminal(
            crn=crn,
            first_name=random.choice(FIRST_NAMES),
            last_name=random.choice(LAST_NAMES),
            alias=f"{random.choice(FIRST_NAMES[::3])}" if random.random() < 0.4 else None,
            date_of_birth=random_dob(18, 60),
            gender=random.choice(['Male', 'Female', 'Male', 'Male']),
            nationality=random.choice(['American', 'British', 'Indian', 'Pakistani', 'Nigerian', 'Chinese', 'Mexican']),
            address=f"{random.randint(1,999)} {random.choice(['Main St','Oak Ave','River Rd'])}, {random.choice(LOCATIONS)}",
            phone=f"+1-{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
            occupation=random.choice(['Unemployed', 'Driver', 'Mechanic', 'Student', 'Trader', 'Laborer']),
            crime_type=crime_type,
            crime_category=CATEGORIES.get(crime_type, 'Other'),
            prior_convictions=random.randint(0, 5),
            modus_operandi=random.choice(MO_LIST),
            gang_id=gang.id if gang else None,
            gang_rank=random.choice(['Member', 'Associate', 'Soldier']) if gang else None,
            is_wanted=random.random() < 0.25,
            is_incarcerated=random.random() < 0.15,
            threat_level=random.choice(THREAT_LEVELS),
            risk_score=round(random.uniform(5, 85), 1),
            created_by_id=created_users[4].id,
        )
        db.add(criminal)
        created_criminals.append(criminal)

    db.commit()
    for c in created_criminals:
        db.refresh(c)
    log.info(f"  Created {len(created_criminals)} criminals")

    # ── Criminal History ──────────────────────────────────────────────────────
    log.info("  Creating criminal histories...")
    event_types = ['arrest', 'conviction', 'release', 'bail_granted', 'wanted_notice', 'sighting', 'associate_link']
    for criminal in created_criminals[:15]:
        n_events = random.randint(2, 6)
        for _ in range(n_events):
            evt_type = random.choice(event_types)
            db.add(models.CriminalHistory(
                criminal_id=criminal.id,
                event_type=evt_type,
                description=f"Subject {evt_type.replace('_', ' ')} at {random.choice(LOCATIONS)}",
                date=random_past(365 * 5),
                location=random.choice(LOCATIONS),
                case_reference=f"REF/{random.randint(2019, 2024)}/{random.randint(1000, 9999)}",
                recorded_by=random.choice([u.full_name for u in created_users[:3]]),
            ))
    db.commit()
    log.info("  Created criminal histories")

    # ── Cases ─────────────────────────────────────────────────────────────────
    log.info("  Creating cases...")
    import string as str_mod
    officers = [u for u in created_users if u.role == models.UserRole.investigating_officer]

    case_scenarios = [
        {'title': 'Operation Shadow Strike', 'crime_type': 'Drug Trafficking', 'location': 'Harbor Front',
         'status': models.CaseStatus.under_investigation, 'priority': 'critical',
         'criminal_idxs': [0, 5, 14], 'officer_idx': 0},
        {'title': 'Downtown Robbery Spree', 'crime_type': 'Robbery', 'location': 'Downtown District',
         'status': models.CaseStatus.under_investigation, 'priority': 'high',
         'criminal_idxs': [3], 'officer_idx': 0},
        {'title': 'Cybercrime Network Investigation', 'crime_type': 'Cybercrime', 'location': 'University Area',
         'status': models.CaseStatus.open, 'priority': 'high',
         'criminal_idxs': [4, 8], 'officer_idx': 2},
        {'title': 'Human Trafficking Ring', 'crime_type': 'Human Trafficking', 'location': 'Riverside Quarter',
         'status': models.CaseStatus.under_investigation, 'priority': 'critical',
         'criminal_idxs': [2, 12], 'officer_idx': 1},
        {'title': 'Money Laundering Operation', 'crime_type': 'Money Laundering', 'location': 'Central Market',
         'status': models.CaseStatus.open, 'priority': 'high',
         'criminal_idxs': [5, 14], 'officer_idx': 1},
        {'title': 'Arms Cache Discovery', 'crime_type': 'Arms Trafficking', 'location': 'Industrial Zone',
         'status': models.CaseStatus.closed, 'priority': 'critical',
         'criminal_idxs': [1, 13], 'officer_idx': 0},
        {'title': 'Vehicle Theft Ring', 'crime_type': 'Car Theft', 'location': 'West Hills',
         'status': models.CaseStatus.open, 'priority': 'normal',
         'criminal_idxs': [9], 'officer_idx': 2},
        {'title': 'Fraud at Central Bank', 'crime_type': 'Fraud', 'location': 'Central Market',
         'status': models.CaseStatus.closed, 'priority': 'high',
         'criminal_idxs': [8, 10], 'officer_idx': 1},
        {'title': 'Kidnapping for Ransom', 'crime_type': 'Kidnapping', 'location': 'Eastgate',
         'status': models.CaseStatus.under_investigation, 'priority': 'critical',
         'criminal_idxs': [2], 'officer_idx': 0},
        {'title': 'Assault at North End Bar', 'crime_type': 'Assault', 'location': 'North End',
         'status': models.CaseStatus.closed, 'priority': 'normal',
         'criminal_idxs': [11], 'officer_idx': 2},
    ]

    created_cases = []
    for sc in case_scenarios:
        year = random.randint(2023, 2024)
        case_number = f"CASE/{year}/" + "".join(random.choices(str_mod.digits, k=6))
        fir_number = f"FIR/{year}/" + "".join(random.choices(str_mod.digits, k=5))
        officer = officers[sc['officer_idx']]
        incident_dt = random_past(365 * 2)
        case = models.Case(
            case_number=case_number,
            fir_number=fir_number,
            title=sc['title'],
            description=f"Investigation into {sc['crime_type'].lower()} activity at {sc['location']}. Multiple suspects identified.",
            crime_type=sc['crime_type'],
            crime_category=CATEGORIES.get(sc['crime_type'], 'Other'),
            location=sc['location'],
            incident_date=incident_dt,
            status=sc['status'],
            priority=sc['priority'],
            fir_date=incident_dt + timedelta(days=random.randint(0, 2)),
            fir_filed_by=f"Constable {random.choice(LAST_NAMES)}",
            fir_station=f"{sc['location']} Police Station",
            complainant_name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            complainant_contact=f"+1-{random.randint(200,999)}-{random.randint(1000,9999)}",
            assigned_officer_id=officer.id,
            created_by_id=created_users[4].id,
            closed_at=datetime.utcnow() - timedelta(days=random.randint(10, 100)) if sc['status'] == models.CaseStatus.closed else None,
        )
        db.add(case)
        created_cases.append((case, sc['criminal_idxs']))

    db.commit()
    for case, _ in created_cases:
        db.refresh(case)

    # Link criminals to cases
    for case, criminal_idxs in created_cases:
        for cidx in criminal_idxs:
            if cidx < len(created_criminals):
                cc = models.CaseCriminal(
                    case_id=case.id,
                    criminal_id=created_criminals[cidx].id,
                    role=random.choice(['suspect', 'accused', 'accused'])
                )
                db.add(cc)
    db.commit()
    log.info(f"  Created {len(created_cases)} cases")

    # ── Evidence ──────────────────────────────────────────────────────────────
    log.info("  Creating evidence...")
    evidence_types = ['physical', 'digital', 'forensic', 'witness', 'documentary']
    for case, _ in created_cases[:8]:
        for j in range(random.randint(1, 4)):
            ev_num = f"EV/{case.case_number.split('/')[-1]}/{j+1:03d}"
            ev = models.Evidence(
                case_id=case.id,
                evidence_number=ev_num,
                type=random.choice(evidence_types),
                description=random.choice([
                    'Mobile phone recovered from suspect', 'Fingerprints lifted from scene',
                    'CCTV footage from nearby cameras', 'Cash and documents seized',
                    'Witness testimony recorded', 'DNA samples collected',
                    'Vehicle license plates recovered', 'Seized narcotics package',
                ]),
                location_found=random.choice(LOCATIONS),
                collected_by=random.choice([u.full_name for u in officers]),
                collected_at=random_past(180),
                chain_of_custody=f"Collected → Lab Analysis → Evidence Room",
                status=random.choice(['collected', 'analyzed', 'submitted_to_court']),
            )
            db.add(ev)
    db.commit()
    log.info("  Created evidence records")

    # ── Victims ───────────────────────────────────────────────────────────────
    log.info("  Creating victims...")
    for case, _ in created_cases[:6]:
        for j in range(random.randint(1, 3)):
            victim = models.Victim(
                case_id=case.id,
                first_name=random.choice(FIRST_NAMES),
                last_name=random.choice(LAST_NAMES),
                age=random.randint(18, 75),
                gender=random.choice(['Male', 'Female']),
                address=f"{random.randint(1,999)} {random.choice(['Park Ave', 'River Rd'])}, {random.choice(LOCATIONS)}",
                phone=f"+1-{random.randint(200,999)}-{random.randint(1000,9999)}",
                injury_description=random.choice([
                    'Minor injuries, received first aid',
                    'Moderate injuries, hospitalized',
                    'No physical injury, emotional trauma reported',
                    'Critical injuries, intensive care',
                    None
                ]),
                status=random.choice(['alive', 'alive', 'alive', 'hospitalized', 'deceased']),
                statement="Statement recorded and on file with investigating officer.",
            )
            db.add(victim)
    db.commit()
    log.info("  Created victims")

    # ── AI Predictions ────────────────────────────────────────────────────────
    log.info("  Creating AI predictions...")
    from app.ml.pipeline import get_pipeline
    pipeline = get_pipeline()


    for i, criminal in enumerate(created_criminals[:12]):
        criminal_data = {
            'id': criminal.id,
            'first_name': criminal.first_name,
            'last_name': criminal.last_name,
            'prior_convictions': criminal.prior_convictions or 0,
            'date_of_birth': str(criminal.date_of_birth) if criminal.date_of_birth else None,
            'crime_type': criminal.crime_type,
            'gang_id': criminal.gang_id,
            'is_wanted': criminal.is_wanted,
            'is_incarcerated': criminal.is_incarcerated,
            'known_associates': criminal.known_associates,
        }
        result = pipeline.predict(criminal_data)
        all_dicts = [{'id': c.id, 'first_name': c.first_name, 'last_name': c.last_name,
                      'prior_convictions': c.prior_convictions or 0,
                      'crime_type': c.crime_type, 'gang_id': c.gang_id,
                      'is_wanted': c.is_wanted, 'date_of_birth': str(c.date_of_birth) if c.date_of_birth else None,
                      'known_associates': c.known_associates}
                     for c in created_criminals]
        similar = pipeline.find_similar_criminals(criminal_data, all_dicts, top_k=3)

        gang_id = None
        if result.get('predicted_gang'):
            g = next((g for g in created_gangs if g.name == result['predicted_gang']), None)
            gang_id = g.id if g else None

        # Stored in the same units the API writes (0-1 fractions) and left
        # pending: review decisions must come from real human reviewers.
        prediction = models.AIPrediction(
            criminal_id=criminal.id,
            predicted_crime_type=result['predicted_crime_type'],
            crime_type_confidence=result['crime_type_confidence'] / 100.0,
            gang_affiliation_probability=result['gang_affiliation_probability'] / 100.0,
            predicted_gang_id=gang_id,
            risk_score=result['risk_score'],
            risk_level=result['risk_level'],
            confidence_overall=result['confidence_overall'] / 100.0,
            similar_criminals=similar,
            input_features=result.get('input_features'),
            review_status='pending',
            model_version=pipeline.model_version,
        )
        db.add(prediction)

    db.commit()
    log.info("  Created AI predictions")

    # ── Notifications ─────────────────────────────────────────────────────────
    log.info("  Creating notifications...")
    notifications_data = [
        {'title': '🚨 HIGH-RISK ALERT: Marcus Vega', 'message': 'Risk score 92.5/100 — CRITICAL. Immediate review required.',
         'type': 'alert', 'role': 'admin'},
        {'title': '🚨 HIGH-RISK ALERT: Boris Petrov', 'message': 'Risk score 95.2/100 — CRITICAL. Murder suspect at large.',
         'type': 'alert', 'role': 'investigating_officer'},
        {'title': '⚠ Duplicate Record Detected', 'message': 'Possible duplicate entry for Dmitri Volkov. Please review.',
         'type': 'warning', 'role': 'record_clerk'},
        {'title': 'Case Closed: Arms Cache Discovery', 'message': 'Case CASE/2023/384920 has been successfully closed.',
         'type': 'success', 'role': None},
        {'title': 'New Case Assigned', 'message': 'Operation Shadow Strike assigned to Inspector Rajesh Kumar.',
         'type': 'info', 'role': 'investigating_officer'},
        {'title': '🤖 Demo model candidate available', 'message': 'A demo model candidate is available. It was trained on synthetic data; see Model Governance for its real evaluation metrics.',
         'type': 'info', 'role': 'admin'},
        {'title': '⚠ Wanted Suspect Sighted', 'message': 'Sofia Reyes reported sighted at Harbor Front. Alert issued.',
         'type': 'alert', 'role': 'investigating_officer'},
        {'title': '📄 Report Generated', 'message': 'Criminal profile report for Marcus Vega has been generated.',
         'type': 'info', 'role': None},
    ]

    for n in notifications_data:
        notif = models.Notification(
            title=n['title'],
            message=n['message'],
            notification_type=n['type'],
            target_role=n['role'],
            is_read=random.random() < 0.4,
        )
        db.add(notif)
    db.commit()
    log.info("  Created notifications")

    # ── Audit Logs ────────────────────────────────────────────────────────────
    # A single honest audit event; the seeder never fabricates user activity.
    from app.utils.audit import create_audit_log
    create_audit_log(db, "DEMO_DATA_SEEDED", username="system", resource_type="database",
                     reason="Fictional demo data loaded into an empty development database",
                     details={"users": len(created_users)})

    # ── ML Model Record ───────────────────────────────────────────────────────
    log.info("  Creating ML model record...")
    ml_meta = pipeline.get_metadata()
    crime_meta = ml_meta.get('crime_classifier', {})
    db.add(models.MLModel(
        version=ml_meta.get('model_version', pipeline.model_version),
        model_type='crime_classifier',
        accuracy=float(crime_meta.get('accuracy', 0.0)),
        precision_score=float(crime_meta.get('precision', 0.0)),
        recall_score=float(crime_meta.get('recall', 0.0)),
        f1_score=float(crime_meta.get('f1', 0.0)),
        training_samples=int(crime_meta.get('training_samples', 0)),
        feature_importances=ml_meta.get('feature_importances'),
        evaluation_metadata={
            "crime_classifier": crime_meta,
            "gang_predictor": ml_meta.get("gang_predictor", {}),
            "evaluation_method": ml_meta.get("evaluation_method"),
            "dataset_type": ml_meta.get("dataset", {}).get("dataset_type"),
            "dataset_version": ml_meta.get("dataset", {}).get("dataset_version"),
            "dataset_sha256": ml_meta.get("dataset", {}).get("sha256"),
            "quality_gate": ml_meta.get("quality_gate"),
            "candidate_status": "active",
        },
        dataset_version=ml_meta.get("dataset", {}).get("dataset_version"),
        evaluation_method=ml_meta.get("evaluation_method"),
        is_active=True,
        notes=(f"Seeded model metadata from pipeline; dataset="
               f"{ml_meta.get('dataset', {}).get('dataset_version', 'unknown')}; "
               f"dataset_sha256={ml_meta.get('dataset', {}).get('sha256', 'unknown')}"),
    ))
    db.commit()
    log.info("  ML model record created")

    log.info("\nDatabase seeded successfully!")
    log.info("\nDemo credentials (development only; a password change is forced at first sign-in):")
    log.info("  Admin:    admin / admin123")
    log.info("  Officer1: officer1 / officer123")
    log.info("  Officer2: officer2 / officer123")
    log.info("  Clerk:    clerk1 / clerk123")


if __name__ == "__main__":
    from app.config import settings
    from app.db_bootstrap import migrate_database

    if settings.is_production:
        raise SystemExit("Refusing to seed demo data with APP_ENV=production")
    migrate_database(engine, allow_auto_upgrade=True)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
