from flask import Flask, request, jsonify
import requests
import yaml
import logging, os
from datetime import date

#region Global variables
config = yaml.safe_load(open("config.yml"))

COMPANY = config["COMPANY"]
API_URL = config["API_URL"]
PRIORITY_API_USERNAME = config["PRI_API_USERNAME"]
PRIORITY_API_PASSWORD = config["PRI_API_PASSWORD"]
SYNEL_API_USER = config["SYNEL_API_USER"]
SYNEL_API_PASSWORD = config["SYNEL_API_PASSWORD"]
#endregion

#region Setup
app = Flask(__name__)

path = r"error.log"
assert os.path.isfile(path)
logging.basicConfig(filename=path, level=logging.DEBUG, format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
#endregion

#region Helper functions
def pri_get_employees():
    r = requests.get(f"{API_URL}{COMPANY}/USERSB?$select=USERID, FIRSTNAME, FAMILYNAME, EMPINACTIVE",  auth=(PRIORITY_API_USERNAME, PRIORITY_API_PASSWORD) )
    return r.json()['value']

def insert_update_employees():
    pri_employees = pri_get_employees()
    # synel_employees = pri_employees.copy()
    synel_employees = []
    
    for emp in pri_employees:
        emp_data = {
            'ExternalId': str(emp['USERID']),
            'EmployeeNo': str(emp['USERID']),
            'BadgeNo': str(emp['USERID']),
            'FirstName': emp['FIRSTNAME'],
            'LastName': emp['FAMILYNAME'],
            'StartDate': '2022-01-01',
            'DepartmentCode':  '0',
            'IsActive': 'false' if emp['EMPINACTIVE'] == 'Y' else 'true'
        }
        synel_employees.append(emp_data)
        
    r = requests.post(f'https://dunlopsystems.synel-saas.com/ExternalAccess/InsertUpdateEmployees?login={SYNEL_API_USER}&password={SYNEL_API_PASSWORD}&employees={synel_employees}')
    
    return r.json()
    
def insert_update_employee(emp):  
    emp_data = {
        'ExternalId': str(emp['USERID']),
        'EmployeeNo': str(emp['USERID']),
        'BadgeNo': str(emp['USERID']),
        'FirstName': emp['FIRSTNAME'],
        'LastName': emp['FAMILYNAME'],
        'StartDate': '2022-01-01',
        'DepartmentCode':  '0',
        'IsActive': 'false' if emp['EMPINACTIVE'] == 'Y' else 'true'
    }
        
    r = requests.post(f'https://dunlopsystems.synel-saas.com/ExternalAccess/InsertUpdateEmployees?login={SYNEL_API_USER}&password={SYNEL_API_PASSWORD}&employees={[emp_data]}')
    
    return r.json()    

def get_clockings():
    r = requests.get(f"https://dunlopsystems.synel-saas.com/ExternalAccess/GetClockings?login={SYNEL_API_USER}&password={SYNEL_API_PASSWORD}&fromDate={date.today()}&toDate={date.today()}")
    return r.json()

# DNAME = Direction
# CURDATE = ScanTime first half
# FROMTIME = ScanTime second half
# DETAILS = Source
# USERBCODE = ExternalId

# Needs to be run every x minutes
def pri_update_clockings():
    synel_clockings = get_clockings()
    pri_clockings = pri_get_clockings()
    
    filtered = filter_clockings(pri_clockings, synel_clockings)
    
    new_clockings = []
    
    for clock in filtered:
        data = {
            'DNAME': clock['Direction'],
            'CURDATE': clock['ScanTime'].split()[0],
            'FROMTIME': clock['ScanTime'].split()[1],
            'DETAILS': clock['Source'],
            'USERBCODE': clock['ExternalId']
        }
        new_clockings.append(data)
    
    responses = []
    for c in new_clockings:
        r = requests.post(f"{API_URL}{COMPANY}/LOADUSERSBWORKHOURS", json=c, auth=(PRIORITY_API_USERNAME, PRIORITY_API_PASSWORD))
        responses.append(r.json())
    return responses

def pri_get_clockings():
    r = requests.get(f"{API_URL}{COMPANY}/LOADUSERSBWORKHOURS?$filter=CURDATE eq {str(date.today()) + 'T00:00:00%2B01:00'}&$select=DNAME, USERBCODE, CURDATE, FROMTIME",  auth=(PRIORITY_API_USERNAME, PRIORITY_API_PASSWORD) )
    return r.json()['value']

def pri_create_composite_key(pri_clocking):
    key = pri_clocking['USERBCODE'] + pri_clocking['DNAME'] + pri_clocking['CURDATE'].split('T')[0] + pri_clocking['FROMTIME']
    return key

def synel_create_composite_key(synel_clocking):
    key = synel_clocking['ExternalId'] + synel_clocking['Direction'] + synel_clocking['ScanTime'].split()[0] + synel_clocking['ScanTime'].split()[1][:5]
    return key

def filter_clockings(pri_clockings, synel_clockings = []):
    for i, p in enumerate(pri_clockings):
        pri_clockings[i]['key'] = pri_create_composite_key(p)        
           
    for i, s in enumerate(synel_clockings):
        synel_clockings[i]['key'] = synel_create_composite_key(s)           
    
    # return pri_clockings, synel_clockings
    
    # Get the set of unique keys in pri_clockings:
    unique_keys = set( w['key'] for w in pri_clockings )
    
    # Get all records for synel_clockings that dont have the same key:
    result = [ h for h in synel_clockings if h['key'] not in unique_keys ]
    return result
#endregion

#region Endpoint definitions
@app.route("/synel/")
def home():
    return "This is the Flask App in IIS Server to handle Synel-Priority."

@app.route("/synel/manageEmployee/", methods = ['POST'])
def manage_employees():
    payload = request.get_json()
    employee = payload['USERSB']
    
    response = insert_update_employee(employee)
    logging.info(response)
    return jsonify(response)
#endregion