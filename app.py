############################################################
# Kemal Yesildagli | kemalyesildagli@medatechuk.com | 2021 #
############################################################
# This is a Flask application (webserver) to handle Synel-Priority integration.
# The purpose is to run on IIS server alonsgside an installation of Priority.
# The webserver can be reached by appending /synel to the Priority base URL. 
# --------------------------------------------------------------------------
# Functionalities:
# 1 - Employee management methods: Insert/Update Employees
# 2 - Swipes Export Methods: Get clockings from Synel and update Priority LOADUSERSBWORKHOURS table

from flask import Flask, request, jsonify
import requests
import yaml
import logging, os
from datetime import date
import time
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

#region Global variables
# Load configuration from config.yml
config = yaml.safe_load(open("config.yml"))

COMPANY = config["COMPANY"]
API_URL = config["API_URL"]
PRIORITY_API_USERNAME = config["PRI_API_USERNAME"]
PRIORITY_API_PASSWORD = config["PRI_API_PASSWORD"]
SYNEL_API_USER = config["SYNEL_API_USER"]
SYNEL_API_PASSWORD = config["SYNEL_API_PASSWORD"]
CLOCK_UPDATE_TIME = config["CLOCK_UPDATE_TIME"]
#endregion

#region Setup
app = Flask(__name__)

# Set up error logger. Make sure error.log exists in this directory.
path = r"error.log"
assert os.path.isfile(path)
logging.basicConfig(filename=path, level=logging.DEBUG, format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
#endregion

#region Helper functions
# Gets all employees from Personnel File form from Priority.
def pri_get_employees():
    r = requests.get(f"{API_URL}{COMPANY}/USERSB?$filter=ZSYN_CLOCKIN eq 'Y'&$select=USERID, FIRSTNAME, FAMILYNAME, EMPINACTIVE",  auth=(PRIORITY_API_USERNAME, PRIORITY_API_PASSWORD) )
    return r.json()['value']

# Updates Synel with all Employees retrieved from Priority.
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
            'StartDate': date.today(),
            'DepartmentCode':  '0',
            'IsActive': 'false' if emp['EMPINACTIVE'] == 'Y' else 'true'
        }
        synel_employees.append(emp_data)
        
    r = requests.post(f'https://dunlopsystems.synel-saas.com/ExternalAccess/InsertUpdateEmployees?login={SYNEL_API_USER}&password={SYNEL_API_PASSWORD}&employees={synel_employees}')
    
    return r.json()

# Updates Synel with 1 employee from Priority.    
def insert_update_employee(emp):  
    emp_data = {
        'ExternalId': str(emp['USERID']),
        'EmployeeNo': str(emp['USERID']),
        'BadgeNo': str(emp['USERID']),
        'FirstName': emp['FIRSTNAME'],
        'LastName': emp['FAMILYNAME'],
        'StartDate': date.today(),
        'DepartmentCode':  '0',
        'IsActive': 'false' if emp['EMPINACTIVE'] == 'Y' else 'true'
    }
        
    r = requests.post(f'https://dunlopsystems.synel-saas.com/ExternalAccess/InsertUpdateEmployees?login={SYNEL_API_USER}&password={SYNEL_API_PASSWORD}&employees={[emp_data]}')
    
    return r.json()    

# Gets all clockings Data from Synel for today for comparison.
def get_clockings():
    r = requests.get(f"https://dunlopsystems.synel-saas.com/ExternalAccess/GetClockings?login={SYNEL_API_USER}&password={SYNEL_API_PASSWORD}&fromDate={date.today()}&toDate={date.today()}")
    return r.json()

# Gets all clockings data from Priority Interim Table-Work Hours form.
def pri_get_clockings(): 
    r = requests.get(f"{API_URL}{COMPANY}/LOADUSERSBWORKHOURS?$filter=CURDATE eq {str(date.today()) + 'T00:00:00%2B01:00'}&$select=DNAME, USERBCODE, CURDATE, FROMTIME",  auth=(PRIORITY_API_USERNAME, PRIORITY_API_PASSWORD) )
    return r.json()['value']

# Gets all clockings from synel and priority, then compares them by creating
# a composite key from the data. Only new clockings will get posted to
# Priority. If there is no new data, no request is made to Priority.
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

# Creates a key to identify records uniquely. Only for internal comparison between Pri and Synel clocking data.
def pri_create_composite_key(pri_clocking):
    key = pri_clocking['USERBCODE'] + pri_clocking['DNAME'] + pri_clocking['CURDATE'].split('T')[0] + pri_clocking['FROMTIME']
    return key

# Creates a key to identify records uniquely. Only for internal comparison between Pri and Synel clocking data.
def synel_create_composite_key(synel_clocking):
    key = synel_clocking['ExternalId'] + synel_clocking['Direction'] + synel_clocking['ScanTime'].split()[0] + synel_clocking['ScanTime'].split()[1][:5]
    return key

# Compares Pri and Synel clocking data and filters out clock data already in Priority
# so that only new data is sent to Priority.
def filter_clockings(pri_clockings, synel_clockings):
    for i, p in enumerate(pri_clockings):
        pri_clockings[i]['key'] = pri_create_composite_key(p)        
           
    for i, s in enumerate(synel_clockings):
        synel_clockings[i]['key'] = synel_create_composite_key(s)           
    
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

# Webhook is setup in business rules of Personnel File form.
# When a personnel is created, updated the webhook will fire and caught by the endpoint below.
@app.route("/synel/manageEmployee/", methods = ['POST'])
def manage_employees():
    payload = request.get_json()
    employee = payload['USERSB']
    
    response = insert_update_employee(employee)
    logging.info(response)
    return jsonify(response)
#endregion

# This starts the scheduler which runs the function 'pri_update_clockings()' with specified frequency.
# This can be configured in config.yml.
def startScheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=pri_update_clockings, trigger="interval", minutes=CLOCK_UPDATE_TIME)
    scheduler.start()

    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    insert_update_employees()
    startScheduler()
    app.run(use_reloader=False)