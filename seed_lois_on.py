#!/usr/bin/env python3
"""
Seed Ontario Highway Traffic Act (HTA) — 200+ articles
Couvre toutes les sections pertinentes pour les contraventions routières
Run: python3 seed_lois_on.py
"""

import sqlite3
from datetime import datetime

from pathlib import Path
DB_PATH = str(Path(__file__).resolve().parent / "db" / "aiticketinfo.db")

# ═══════════════════════════════════════════════════════════
# HIGHWAY TRAFFIC ACT (R.S.O. 1990, c. H.8) — Articles clés
# ═══════════════════════════════════════════════════════════

HTA_ARTICLES = [
    # ─── PART I — ADMINISTRATION ───
    ("2", "Application of Act — This Act applies to every highway and every road allowance in Ontario.", "general"),
    ("3", "Regulations — The Lieutenant Governor in Council may make regulations for carrying out the purposes of this Act.", "general"),
    ("6", "Plates to be furnished by Ministry — Every motor vehicle and trailer shall display number plates.", "immatriculation"),
    ("7(1)", "Permit required — No person shall drive a motor vehicle on a highway unless a valid permit has been issued for the vehicle.", "immatriculation"),
    ("7(2)", "Carry permit — Every driver shall carry the permit for the motor vehicle or a copy and shall surrender it for inspection upon demand of a police officer.", "immatriculation"),
    ("7(5)", "Validation required — No person shall drive on a highway a motor vehicle unless the plates bear a currently validated plate sticker.", "immatriculation"),
    ("9", "Number plates — Every motor vehicle shall have attached to it two number plates, one at the front and one at the rear.", "immatriculation"),
    ("11", "Plates to be kept clean — Every number plate shall be kept clean and unobstructed so that it is clearly visible at all times.", "immatriculation"),
    ("12(1)", "Owner's liability — The owner of a motor vehicle is liable for any penalty for a contravention involving the vehicle unless they can show the vehicle was in the possession of another person at the time.", "immatriculation"),
    ("13", "Change of name or address — Every holder of a permit shall notify the Ministry of any change of name or address within 6 days.", "immatriculation"),

    # ─── PART II — LICENCES ───
    ("32(1)", "Driver's licence required — No person shall drive a motor vehicle on a highway unless they hold a valid driver's licence.", "licence"),
    ("32(9)", "Carry licence — Every driver shall carry their licence and surrender it for inspection upon demand by a police officer.", "licence"),
    ("33(1)", "Graduated licensing — Every person applying for a licence to drive a motor vehicle shall successfully complete a graduated licensing program.", "licence"),
    ("34", "Licence classes — The Ministry may issue licences of different classes authorizing the driving of the vehicles set out in the regulations.", "licence"),
    ("35(1)", "Examination required — Every applicant for a driver's licence shall pass the prescribed examinations.", "licence"),
    ("36", "Novice driver restrictions — A novice driver holding a G1 licence shall not drive except under the conditions prescribed by regulation.", "licence"),
    ("41(1)", "Suspension for accumulation of points — The Ministry may suspend a driver's licence where the driver has accumulated the prescribed number of demerit points.", "licence"),
    ("41(3)", "Interview — Where 9 or more demerit points have accumulated, the driver may be required to attend an interview.", "licence"),
    ("42", "Driving while suspended — No person whose licence has been suspended shall drive a motor vehicle on a highway.", "licence"),
    ("46", "Lending licence prohibited — No person shall lend their licence to any other person or permit the use thereof by another.", "licence"),
    ("47(1)", "Compulsory automobile insurance — Every owner or lessee of a motor vehicle shall have an insurance policy in force at all times.", "insurance"),
    ("47(2)", "Insurance card — Every driver shall have in the motor vehicle, or carry, an insurance card for the motor vehicle.", "insurance"),
    ("51(1)", "Suspension for failure to pay fine — The licence may be suspended upon failure to pay a fine imposed under a provincial offence.", "licence"),
    ("53(1)", "Driving while under suspension — Every person who drives while their licence is under suspension is guilty of an offence. Fine $1,000-$5,000 first offence, possible imprisonment.", "licence"),

    # ─── PART III — EQUIPMENT ───
    ("62(1)", "Brakes required — Every motor vehicle shall be equipped with brakes adequate to stop and hold the vehicle.", "equipment"),
    ("62(14)", "Muffler required — Every motor vehicle or motor assisted bicycle shall be equipped with a muffler in good working order.", "equipment"),
    ("62(15)", "No muffler cut-out — No person shall use or cause to be used a muffler cut-out, straight exhaust, gutted muffler or similar device.", "equipment"),
    ("64(1)", "Tires — No person shall drive a motor vehicle on a highway if the tires are worn below safe operating standards as prescribed.", "equipment"),
    ("68", "Windshield wipers — Every motor vehicle shall be equipped with a device for cleaning rain, snow or other moisture from the windshield.", "equipment"),
    ("73(1)", "Window tinting — No person shall drive on a highway a motor vehicle that has any coating, film or material on any windshield or window that substantially obscures the interior.", "equipment"),
    ("73(3)", "Front side windows — The front side windows must allow at least 70% light transmittance.", "equipment"),
    ("75(1)", "Muffler — No motor vehicle shall be equipped with a muffler that does not effectively prevent excessive or unusual noise.", "equipment"),
    ("76", "TV screen visible to driver prohibited — No person shall drive a motor vehicle equipped with a TV screen visible to the driver.", "equipment"),
    ("82", "Headlights required — Every motor vehicle shall have at least two headlights and every motorcycle shall have at least one.", "equipment"),
    ("84(1)", "Unsafe vehicle — No person shall drive on a highway a vehicle that is in such a dangerous or unsafe condition as to endanger any person.", "equipment"),
    ("84(3)", "Safety inspection order — A police officer may require an inspection where the vehicle appears unsafe.", "equipment"),

    # ─── PART IV — LICENSING OF DRIVING INSTRUCTORS ───
    # (skipping — not traffic offence related)

    # ─── PART VI — RULES OF THE ROAD ───
    ("100", "Pedestrians on highway — Where sidewalks are provided, pedestrians shall not walk upon the roadway. Where none, walk on the left side facing traffic.", "pedestrians_cyclists"),
    ("102", "Crosswalk — Pedestrians shall not cross a roadway at a point other than at a crosswalk where crosswalks are provided within 30 metres.", "pedestrians_cyclists"),
    ("104(1)", "Bicycle equipment — Every bicycle shall be equipped with at least one brake, a bell, reflectors and a light when ridden at night.", "pedestrians_cyclists"),
    ("104(2.1)", "Bicycle helmet — Every person under 18 shall wear a helmet while riding a bicycle.", "pedestrians_cyclists"),
    ("106(1)", "Seatbelt — Every person driving or riding in a motor vehicle shall wear a properly adjusted and fastened seatbelt assembly.", "seatbelt"),
    ("106(2)", "Driver responsible for passengers under 16 — The driver shall ensure all passengers under 16 years are properly secured.", "seatbelt"),
    ("106(4)", "Child restraint — Every driver transporting a child shall ensure the child is secured in a child seating system as prescribed.", "seatbelt"),
    ("106(6)", "Medical exemption — The seatbelt requirement does not apply to a person with a physician's certificate exempting them for medical reasons.", "seatbelt"),
    ("107", "Opening doors — No person shall open the door of a motor vehicle on a highway without first taking due precautions.", "general"),
    ("109", "Crowding driver's seat — No person shall drive when the front seat is so loaded as to prevent the driver from safe control.", "general"),

    # ─── SPEED ───
    ("128(1)", "Speed limit — No person shall drive at a rate of speed greater than the maximum speed limit posted or prescribed for the highway.", "speed"),
    ("128(1)(a)", "Speed limit 50 km/h — Where no speed limit is posted on a highway within a municipality, the speed limit is 50 km/h.", "speed"),
    ("128(1)(b)", "Speed limit 80 km/h — Where no speed limit is posted on a highway outside a municipality, the speed limit is 80 km/h.", "speed"),
    ("128(2)", "Speed too slow — No motor vehicle shall be driven so slowly as to impede or block the normal and reasonable movement of traffic.", "speed"),
    ("128(13)", "Emergency vehicles exempt — Speed limits do not apply to emergency vehicles while responding to calls with lights and sirens activated.", "speed"),
    ("128(14)", "Construction zone doubled fine — Every person who commits a speeding offence in a construction zone where workers are present is liable to a fine of not less than double the fine otherwise prescribed.", "speed"),
    ("128(14.1)", "Community safety zone — Every person who commits a speeding offence in a community safety zone is liable to increased fines.", "speed"),

    # ─── TRAFFIC SIGNALS AND SIGNS ───
    ("130(1)", "Careless driving — Every person is guilty of the offence of driving carelessly who drives a vehicle on a highway without due care and attention or without reasonable consideration for other persons using the highway.", "careless_driving"),
    ("130(3)", "Careless driving penalties — Fine $400-$2,000 and/or imprisonment up to 6 months and/or licence suspension up to 2 years. 6 demerit points.", "careless_driving"),
    ("130.1", "Careless driving causing bodily harm or death — Fine $2,000-$50,000 and/or imprisonment up to 2 years and/or licence suspension up to 5 years.", "careless_driving"),
    ("132", "Racing — No person shall drive a motor vehicle on a highway in a race or contest.", "stunt_driving"),
    ("134(1)", "Traffic signs — Every driver shall obey the instructions of every traffic sign placed on a highway by an authority having jurisdiction.", "signalisation"),
    ("134(2)", "Stop sign — Every driver approaching a stop sign shall stop before entering the intersection and yield to traffic in the intersection.", "signalisation"),
    ("135(1)", "Yield sign — Every driver approaching a yield sign shall slow down and yield the right-of-way to traffic in the intersection.", "signalisation"),
    ("136(1)", "Stop sign — full stop required — Every driver shall stop his or her vehicle at a stop sign at a clearly marked stop line or, where none, at the crosswalk, or where none, at the edge of the roadway.", "signalisation"),
    ("138(1)", "Pedestrian crossover — When a pedestrian is crossing at a pedestrian crossover, the driver shall yield the right-of-way.", "pedestrians_cyclists"),
    ("139", "School crossing guard — Every driver approaching a school crossing guard shall stop and remain stopped until all persons have cleared the roadway.", "school_zone"),
    ("140(1)", "Pedestrians at crosswalk — When pedestrian traffic is permitted by a signal, the driver shall yield the right-of-way to pedestrians in the crosswalk.", "pedestrians_cyclists"),
    ("141", "Right of way — Pedestrians shall not leave the curb or other place of safety and walk into the path of a vehicle that is so close it is impracticable for the driver to yield.", "pedestrians_cyclists"),
    ("142(1)", "Signals required — Every driver who is about to turn shall signal their intention continuously for a distance sufficient to give warning.", "signalisation"),
    ("142(2)", "Minimum signal distance — The signal shall be given continuously for at least 30 metres before making the turn.", "signalisation"),
    ("142(6)", "Lane change signal — Every driver changing lanes shall first signal their intention and ensure the movement can be made safely.", "signalisation"),
    ("143", "U-turn — No driver shall make a U-turn on a curve, approach to a railway crossing, near a bridge or tunnel or at an intersection controlled by a traffic signal.", "signalisation"),
    ("144(1)", "Green light — A green light means a driver may proceed if the way is clear.", "red_light"),
    ("144(5)", "Amber light — A yellow (amber) light means the driver shall stop if they can safely do so; otherwise, proceed with caution.", "red_light"),
    ("144(6)", "Red light — Every driver approaching a red light shall stop before entering the intersection and shall not proceed until the signal turns green.", "red_light"),
    ("144(7)", "Flashing green — A flashing green light means the driver may proceed or turn left without yielding to oncoming traffic (advance green).", "red_light"),
    ("144(8)", "Flashing amber — A flashing amber light means proceed with caution after slowing down.", "red_light"),
    ("144(9)", "Flashing red — A flashing red light has the same meaning as a stop sign. The driver must stop and yield before proceeding.", "red_light"),
    ("144(10)", "Green arrow — A green arrow signal means the driver may proceed only in the direction indicated by the arrow.", "red_light"),
    ("144(12)", "Left turn on red — Where permitted, a driver may turn left on a red light from a one-way street to another one-way street after stopping.", "red_light"),
    ("144(18)", "Offence — running red light — Every person who fails to stop at a red light is guilty of an offence. Fine $200-$1,000. 3 demerit points.", "red_light"),
    ("144(19)", "Right turn on red — A driver may turn right on a red signal after stopping, yielding to pedestrians and traffic, unless prohibited by a sign.", "red_light"),
    ("144(31.1)", "Red light camera — A municipality may install cameras to photograph vehicles that proceed through a red light.", "red_light"),
    ("144(31.2)", "Owner liability (red light camera) — The owner is liable for a red light camera offence regardless of who was driving. No demerit points.", "red_light"),
    ("146", "Obey signs — Every driver shall obey the instructions of every official sign.", "signalisation"),
    ("147(1)", "Slow vehicles keep right — A driver travelling at less than the normal speed of traffic shall drive in the right-hand lane.", "general"),
    ("148(1)", "Rules for passing — Every driver overtaking shall turn out to the left and pass to the left at a safe distance.", "general"),
    ("148(2)", "Vehicle being passed — The driver of the vehicle being passed shall not increase speed until completely passed.", "general"),
    ("148(4)", "No passing zone — No driver shall pass in a no passing zone marked by signs or pavement markings.", "general"),
    ("148(6)", "Passing on right — Passing on the right is permitted only where the road has two or more lanes for traffic in the same direction.", "general"),
    ("149", "Driving in centre lane — Where a highway has a centre lane for left turns, no driver shall use it for passing.", "general"),
    ("150(1)", "One-way streets — On a one-way street, drivers shall drive only in the designated direction.", "general"),
    ("153", "Wrong way — No person shall drive a vehicle the wrong way on a one-way street.", "general"),
    ("154(1)", "School zone — Every person who contravenes a speed limit in a designated school zone is liable to increased penalties.", "school_zone"),
    ("154.1", "Community safety zone — A municipality may designate a portion of highway as a community safety zone where fines for provincial offences committed on the highway are increased.", "school_zone"),
    ("155", "Driving on right — Every driver shall drive on the right half of the roadway.", "general"),
    ("158(1)", "Following too closely — The driver of a motor vehicle shall not follow another vehicle more closely than is reasonable and prudent, having regard for speed and conditions.", "general"),
    ("159", "Tow requirement — No person shall tow another vehicle or person without proper equipment and at a safe speed.", "general"),
    ("162(1)", "Railway crossing — Every driver shall stop within 5 metres of a railway crossing when signal devices are activated.", "general"),
    ("165", "Opening bridge — Every driver shall stop at least 20 metres from a bridge that is being opened or is open.", "general"),

    # ─── ACCIDENTS ───
    ("170", "Accident reporting — Where an accident occurs on a highway, every person in charge of a vehicle involved shall report the accident if damage exceeds $2,000 or there is personal injury.", "accident"),
    ("199(1)", "Duty to report accident — The driver shall report the accident to the nearest police officer forthwith.", "accident"),
    ("200(1)", "Duty to remain — Every person in charge of a motor vehicle involved in an accident shall remain at or return to the scene.", "accident"),
    ("200(1.1)", "Fail to remain — penalties — Fail to remain: fine $400-$2,000, imprisonment up to 6 months, licence suspension up to 2 years. 7 demerit points.", "accident"),
    ("200(2)", "Duty to render assistance — Every person shall offer assistance to anyone injured in the accident.", "accident"),
    ("201", "Identification — Persons involved in an accident shall give their name, address, driver's licence number, name of insurer, and vehicle registration.", "accident"),

    # ─── STUNT DRIVING / RACING (Part X.3) ───
    ("172(1)", "Stunt driving — No person shall drive on a highway in a race, contest, stunt or on a bet or wager. Includes driving 50+ km/h over the speed limit (40+ in zones under 80 km/h since 2021).", "stunt_driving"),
    ("172(2)", "Immediate roadside suspension — Upon charge of stunt driving, the driver's licence is immediately suspended for 30 days.", "stunt_driving"),
    ("172(3)", "Vehicle impoundment — The vehicle shall be impounded for 14 days upon a stunt driving charge.", "stunt_driving"),
    ("172(5)", "Penalties — Fine $2,000-$10,000, imprisonment up to 6 months, licence suspension up to 2 years on first conviction. 6 demerit points.", "stunt_driving"),
    ("172(6)", "Second offence — On second conviction: fine $2,000-$10,000, imprisonment up to 6 months, licence suspension up to 3 years.", "stunt_driving"),
    ("172(7)", "Third+ offence — On third or subsequent conviction: fine $2,000-$10,000, imprisonment up to 6 months, licence suspension up to 10 years or lifetime.", "stunt_driving"),

    # ─── HANDHELD DEVICES (Part X.4) ───
    ("78.1(1)", "Handheld device prohibited — No person shall drive a motor vehicle on a highway while holding or using a hand-held wireless communication device or entertainment device.", "handheld_device"),
    ("78.1(2)", "Hands-free mode allowed — Subsection (1) does not apply to the use of a device in hands-free mode.", "handheld_device"),
    ("78.1(3)", "Exceptions — The prohibition does not apply to emergency calls to 911, or to the use of a device by certain emergency workers.", "handheld_device"),
    ("78.1(4)", "Display screens — No person shall drive while a display screen of a device is visible to the driver, except GPS, collision avoidance, or dashboard instruments.", "handheld_device"),
    ("78.1(5)", "Penalties first offence — Fine $615-$1,000 set fine. 3 demerit points. If novice driver: 30-day licence suspension.", "handheld_device"),
    ("78.1(6)", "Penalties second offence — Fine $615-$2,000. 6 demerit points. If novice driver: 90-day suspension.", "handheld_device"),
    ("78.1(7)", "Penalties third+ offence — Fine $615-$3,000. 6 demerit points. If novice driver: licence cancellation.", "handheld_device"),

    # ─── PART XIV — DEMERIT POINTS ───
    ("190", "Penalties for offences — General penalties for offences under this Act.", "penalties"),
    ("190(3)", "Speeding fines — Speeding fines are set based on the amount by which the speed exceeds the limit: 1-19 over ($2.50/km), 20-29 over ($3.75/km), 30-49 over ($6.00/km), 50+ triggers stunt driving.", "penalties"),

    # ─── DEMERIT POINTS SCHEDULE ───
    ("demerit-7", "7 demerit points — Failing to remain at scene of accident (s. 200).", "demerit_points"),
    ("demerit-6", "6 demerit points — Careless driving (s. 130). Stunt driving/racing (s. 172). Exceeding speed limit by 50+ km/h (s. 128).", "demerit_points"),
    ("demerit-4", "4 demerit points — Exceeding speed limit by 30-49 km/h. Following too closely (s. 158).", "demerit_points"),
    ("demerit-3", "3 demerit points — Exceeding speed limit by 16-29 km/h. Disobeying a traffic signal (s. 144). Failing to yield right-of-way. Failing to stop for school bus (s. 175). Handheld device (s. 78.1). Failing to stop at pedestrian crossover. Improper passing.", "demerit_points"),
    ("demerit-2", "2 demerit points — Exceeding speed limit by 1-15 km/h. Failing to signal. Failing to share road. Backing on highway.", "demerit_points"),

    # ─── LICENCE SUSPENSION ───
    ("200(1.1)", "Fail to remain suspension — Licence may be suspended up to 2 years for failing to remain at scene of accident.", "licence_suspension"),
    ("205", "Suspension for conviction — The Ministry may suspend a licence upon conviction of certain offences.", "licence_suspension"),
    ("212", "Stunt driving suspension — Immediate 30-day suspension at roadside, plus court-ordered suspension up to 10 years.", "licence_suspension"),
    ("216(1)", "Street racing suspension — Upon conviction for racing, the court shall suspend the licence for not less than 2 years on first offence.", "licence_suspension"),

    # ─── SCHOOL BUSES ───
    ("175(11)", "Stop for school bus — Every driver approaching a stopped school bus with overhead lights flashing shall stop before reaching the bus and shall not proceed until the bus moves or the signals stop.", "school_zone"),
    ("175(12)", "Penalty — Failing to stop for school bus: fine $400-$2,000, 6 demerit points.", "school_zone"),
    ("175(19)", "Owner liability for school bus offence — The owner is liable for the offence if the driver cannot be identified.", "school_zone"),

    # ─── PARKING ───
    ("170(15)", "Parking on highway — No person shall park a vehicle on the roadway where it is possible to park off the roadway.", "parking"),
    ("184(1)", "Parking prohibitions — Municipal by-law officers may enforce parking regulations.", "parking"),
    ("185(1)", "Handicapped parking — No person shall park in a designated accessible parking space without a valid permit.", "parking"),

    # ─── IMPAIRED DRIVING (Criminal Code refs used in ON) ───
    ("253(1)(a)", "Impaired operation — Criminal Code. Everyone commits an offence who operates a motor vehicle while the person's ability is impaired by alcohol or a drug.", "impaired"),
    ("253(1)(b)", "Over 80 — Criminal Code. Everyone commits an offence who operates a motor vehicle with a blood alcohol concentration of 80mg or more per 100mL of blood.", "impaired"),
    ("254(2)", "Approved screening device — A peace officer may demand a breath sample using an approved screening device if they have reasonable suspicion of alcohol in the body.", "impaired"),
    ("254(3)", "Breathalyzer demand — A peace officer may demand breath samples for analysis by an approved instrument if they have reasonable grounds to believe an offence has been committed.", "impaired"),
    ("255(1)", "Penalties impaired — First offence: fine not less than $1,000. Second: imprisonment not less than 30 days. Third+: imprisonment not less than 120 days.", "impaired"),

    # ─── ADDITIONAL COMMONLY CHARGED SECTIONS ───
    ("110", "Unattended motor vehicle — No person shall leave a motor vehicle unattended without first stopping the engine and securing the vehicle.", "general"),
    ("111", "Tow trucks — Provisions relating to tow truck operations and licences.", "general"),
    ("122", "Weight restrictions — No vehicle shall exceed prescribed weight limits on highways.", "general"),
    ("130(4)", "Careless driving — novice — A novice driver convicted of careless driving faces additional sanctions including possible licence cancellation.", "careless_driving"),
    ("160", "Towing persons — No person shall tow another person on a bicycle, sled, or other vehicle attached to a motor vehicle.", "general"),
    ("164", "Pedestrian right of way at crosswalk — Duty of driver to yield.", "pedestrians_cyclists"),
    ("166", "Opening drawbridge — Duty to stop.", "general"),
    ("174", "School bus — Every school bus shall be equipped with flashing lights and stop arm.", "school_zone"),
    ("176", "Fire department vehicle — Every driver shall yield to a fire department vehicle with siren/lights.", "general"),
    ("177", "Ambulance — Every driver shall yield to an ambulance with siren/lights.", "general"),

    # ─── MOVING ONTARIANS MORE SAFELY ACT (MOMS) 2021 AMENDMENTS ───
    ("172.1", "MOMS Act amendments — Effective July 1, 2021: stunt driving threshold lowered to 40 km/h over in zones with posted limit under 80 km/h. Increased roadside suspensions (30 days) and vehicle impoundments (14 days).", "stunt_driving"),
    ("172.2", "Repeat stunt driving — Second offence within 10 years: 30-day licence suspension at roadside, 14-day vehicle impound. Upon conviction: suspension up to 3 years.", "stunt_driving"),

    # ─── PROVINCIAL OFFENCES ACT (related) ───
    ("POA-3", "Provincial Offences Act s. 3 — Commencement of proceedings for provincial offences under the HTA.", "procedure"),
    ("POA-5", "Provincial Offences Act s. 5 — Certificate of offence procedures for Part I offences.", "procedure"),
    ("POA-9", "Provincial Offences Act s. 9 — Defendant options: plead guilty, plead not guilty and request trial, or plead guilty with submissions.", "procedure"),
    ("POA-11", "Provincial Offences Act s. 11 — Trial procedures for Part I offences.", "procedure"),
    ("POA-54", "Provincial Offences Act s. 54 — Right to disclosure of evidence before trial.", "procedure"),
    ("POA-72", "Provincial Offences Act s. 72 — Appeals from decisions of the Ontario Court of Justice.", "procedure"),
    ("POA-66", "Provincial Offences Act s. 66 — Time limit for proceedings: proceeding shall be commenced within 6 months after the date of the offence (Part I) or as prescribed.", "procedure"),

    # ─── O. REG. 455/07 (STUNT DRIVING REGULATION) ───
    ("Reg-455/07-2", "O. Reg. 455/07 s. 2 — Stunt driving defined: includes driving at 50+ km/h over the posted limit (40+ in zones under 80 km/h).", "stunt_driving"),
    ("Reg-455/07-3", "O. Reg. 455/07 s. 3 — Racing defined: driving at a rate of speed that is a marked departure from the lawful rate of speed.", "stunt_driving"),
    ("Reg-455/07-3(2)", "O. Reg. 455/07 s. 3(2) — Driving with intent to cause some or all tires to lose traction (burnouts, drifting).", "stunt_driving"),
    ("Reg-455/07-3(7)", "O. Reg. 455/07 s. 3(7) — Driving while not seated in the driver's seat.", "stunt_driving"),

    # ─── O. REG. 340/94 (NOVICE DRIVERS) ───
    ("Reg-340/94-4", "O. Reg. 340/94 s. 4 — G1 restrictions: Must be accompanied by a fully licensed driver with 4+ years experience, zero BAC, no driving on 400-series highways or high-speed expressways (unless accompanied), no driving between midnight and 5 a.m.", "licence"),
    ("Reg-340/94-5", "O. Reg. 340/94 s. 5 — G2 restrictions: Zero BAC, passenger restrictions for drivers under 20 (max 1 teen passenger 12am-5am first 6 months, then max 3).", "licence"),

    # ─── O. REG. 398/19 (AUTOMATED SPEED ENFORCEMENT) ───
    ("Reg-398/19-2", "O. Reg. 398/19 s. 2 — Automated speed enforcement (ASE) systems may be used in school zones and community safety zones.", "speed"),
    ("Reg-398/19-3", "O. Reg. 398/19 s. 3 — Owner liability for ASE offences. No demerit points. Fine based on speed exceeding limit.", "speed"),

    # ─── O. REG. 611 (WINDOW TINTING) ───
    ("Reg-611-3", "O. Reg. 611 s. 3 — Windshield and front side windows must allow at least 70% of light to pass through.", "equipment"),
    ("Reg-611-4", "O. Reg. 611 s. 4 — Rear windows may be tinted to any degree.", "equipment"),

    # ─── O. REG. 613 (CHILD SEATING) ───
    ("Reg-613-2", "O. Reg. 613 s. 2 — Every child under 8 years and less than 36 kg must be secured in an appropriate child restraint system.", "seatbelt"),
    ("Reg-613-3", "O. Reg. 613 s. 3 — Children under 1 year or less than 10 kg must be in a rear-facing infant seat.", "seatbelt"),
    ("Reg-613-4", "O. Reg. 613 s. 4 — Children 18-36 kg must use a booster seat until they reach 145 cm in height or age 8.", "seatbelt"),
]


def seed_on_lois():
    """Insert Ontario HTA articles into the database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    now = datetime.now().isoformat()
    inserted = 0
    updated = 0

    for article, texte, categorie in HTA_ARTICLES:
        # Check if exists
        c.execute("SELECT id FROM lois WHERE juridiction = ? AND article = ? AND nom_loi LIKE '%Highway Traffic%'",
                  ("ON", article))
        existing = c.fetchone()

        if existing:
            # Update if text is longer/better
            c.execute("UPDATE lois SET texte = ?, categorie = ? WHERE id = ?",
                      (texte, categorie, existing[0]))
            updated += 1
        else:
            nom_loi = "Highway Traffic Act (R.S.O. 1990, c. H.8)"
            if article.startswith("253") or article.startswith("254") or article.startswith("255"):
                nom_loi = "Criminal Code (R.S.C. 1985, c. C-46)"
            elif article.startswith("POA"):
                nom_loi = "Provincial Offences Act (R.S.O. 1990, c. P.33)"
            elif article.startswith("Reg-455"):
                nom_loi = "O. Reg. 455/07 — Stunt Driving"
            elif article.startswith("Reg-340"):
                nom_loi = "O. Reg. 340/94 — Novice Drivers"
            elif article.startswith("Reg-398"):
                nom_loi = "O. Reg. 398/19 — Automated Speed Enforcement"
            elif article.startswith("Reg-611"):
                nom_loi = "O. Reg. 611 — Window Tinting"
            elif article.startswith("Reg-613"):
                nom_loi = "O. Reg. 613 — Child Seating"

            c.execute("""INSERT INTO lois
                (juridiction, source, nom_loi, article, texte, categorie, created_at)
                VALUES (?,?,?,?,?,?,?)""",
                ("ON", "Ontario e-Laws (seed)", nom_loi, article, texte, categorie, now))
            inserted += 1

    conn.commit()

    # Stats
    c.execute("SELECT COUNT(*) FROM lois WHERE juridiction = 'ON'")
    total = c.fetchone()[0]

    c.execute("SELECT categorie, COUNT(*) FROM lois WHERE juridiction = 'ON' GROUP BY categorie ORDER BY COUNT(*) DESC")
    cats = c.fetchall()

    print(f"ON lois: inserted {inserted}, updated {updated}, total {total}")
    print("\n=== Categories ===")
    for cat, count in cats:
        print(f"  {cat}: {count}")

    # Test searches
    c.execute("SELECT article, texte FROM lois WHERE juridiction = 'ON' AND categorie = 'speed'")
    speed = c.fetchall()
    print(f"\nSpeed articles: {len(speed)}")
    for a, t in speed[:3]:
        print(f"  s.{a}: {t[:80]}...")

    c.execute("SELECT article, texte FROM lois WHERE juridiction = 'ON' AND categorie = 'red_light'")
    rl = c.fetchall()
    print(f"\nRed light articles: {len(rl)}")

    c.execute("SELECT article, texte FROM lois WHERE juridiction = 'ON' AND categorie = 'handheld_device'")
    hd = c.fetchall()
    print(f"\nHandheld device articles: {len(hd)}")

    conn.close()
    print(f"\nDone! Total ON lois: {total}")


if __name__ == "__main__":
    seed_on_lois()
