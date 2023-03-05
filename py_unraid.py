from bs4 import BeautifulSoup
from datetime import datetime
import json
import re, requests
from urllib.parse import urlencode

# TODO: Handle case when server is on but array is not started.

class Unraid_Session:
    
    def __init__(self, host = '', username = '', password = ''):
        ''' instantiate an unraid server session '''
        self.host = host
        self.username = username
        self.password = password
        
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/x-www-form-urlencoded','Connection': 'keep-alive'})
        
        self._csrf_token = None
        self._server_name = None
        self._server_version = None
        self._guid = None
    
    def authenticated(self, force=False):
        if not force:
            if self._csrf_token:
                return True
        else:
            self.authenicate()

    def authenicate(self):
        form_data = {
            "username" : self.username,
            "password" : self.password
        }
        data = urlencode(form_data)
        data = data.replace('~', '%7E')
        response = self.session.post(self.host+'/login', data = data, allow_redirects = False)
        try:
            if response.status_code == 302:
                server_details = self._server_details()
                self._server_name = server_details['name'] #need to confirm json tag
                self._csrf_token = server_details['csrf_token'] #need to confirm json tag
                self._server_version = server_details['version']
                self._guid = server_details['regGUID']
                return 'authenticated'
            elif response.status_code == 200:
                return 'authenication failed'
            else:
                return 'failed to connect'
        except:
            return 'failed to connect'
    
    def _server_details(self):
        if not self.authenticated():
            self.authenticated(force=True)
        response = self.session.get(self.host+'/Main')
        details_json = json.loads(re.findall('var vars        = ({"version":.+?"});', response.text)[0])
        return details_json
    
    def array_state(self):
        ''' return the start/stop state of the array '''
        if not self.authenticated():
            self.authenticated(force=True)
        response = self.session.get(self.host+'/Main')
        html = BeautifulSoup(response.text, features="html.parser")
        state = html.find_all(attrs={"name":"startState"})[0].get('value')
        return state
        
    def disk_status(self, disk='array'):
        ''' fetch the status details for the relevant disk(s) and parse it '''
        if not self.authenticated():
            self.authenticated(force=True)
        form_data = {
            "path" : "Main",
            "device" : disk,
            "csrf_token" : self._csrf_token
        }
        response = self.session.post(self.host+"/webGui/include/DeviceList.php", data=urlencode(form_data))
        page = response.text
        html = BeautifulSoup(page, features="html.parser")
        if disk == "parity":
            return page
        disks = []
        for row in html.find_all('tr'):
            if  not row.contents:
                continue
            elif row.attrs == {'class': ['tr_last']}:
                ''' build a report for the whole array '''
                tds = row.find_all('td')
                disk_name = tds[1].text
                disk_temp = tds[2].text
                disk_reads = row.find_all(attrs={"class": "number"})[0].text
                disk_writes = row.find_all(attrs={"class": "number"})[1].text
                read_io = row.find_all(attrs={"class": "diskio"})[0].text
                write_io = row.find_all(attrs={"class": "diskio"})[1].text
                disk_errors = tds[5].text
                disks.append(
                    {
                        'name' : disk_name,
                        'temp' : disk_temp,
                        'reads' : disk_reads,
                        'writes' : disk_writes,
                        'read_io' : read_io,
                        'writes' : disk_writes,
                        'write_io' : write_io
                    }
                )
            else:
                disk_name = row.find_all(href=re.compile("name="))[0].text
                disk_details = row.find_all('span')
                read_io = row.find_all(attrs={"class": "diskio"})[0].text
                write_io = row.find_all(attrs={"class": "diskio"})[1].text
                tds = row.find_all('td')
                disk_temp = tds[2].text
                disk_status = disk_details[0].text.split('Click to spin')[0]
                if disk_name == "Parity":
                    disk_serial = disk_details[2].text
                    disk_reads = disk_details[-3].text
                    disk_writes = disk_details[-1].text
                    disk_errors = tds[-2].text
                    disk_dict = {
                        'name' : disk_name,
                        'temp' : disk_temp,
                        'serial' : disk_serial,
                        'status' : disk_status,
                        'reads' : disk_reads,
                        'read_io' : read_io,
                        'writes' : disk_writes,
                        'write_io' : write_io,
                        'errors' : disk_errors
                    }
                else:
                    if (disk == "cache") and (len(re.findall('Device is part of a pool', row.text)) > 0):
                        disk_serial = row.find_all('span')[2].text
                        disk_errors = row.find_all('td')[-3].text
                        disk_dict = {
                            'name' : disk_name,
                            'temp' : disk_temp,
                            'serial' : disk_serial,
                            'status' : disk_status,
                            'reads' : disk_reads,
                            'read_io' : read_io,
                            'writes' : disk_writes,
                            'write_io' : write_io,
                            'errors' : disk_errors
                        }
                    else:        
                        disk_size = tds[-4].text
                        disk_format = tds[-5].text
                        disk_status = disk_details[0].text.split('Click to spin')[0]
                        disk_reads = disk_details[-7].text
                        disk_writes = disk_details[-5].text
                        disk_errors = tds[-6].text
                        disk_serial = disk_details[-9].text
                        space_used = disk_details[-3].text
                        space_available = disk_details[-1].text
                        disk_dict = {
                            'name' : disk_name,
                            'temp' : disk_temp,
                            'size' : disk_size,
                            'format' : disk_format,
                            'status': disk_status,
                            'serial' : disk_serial,
                            'reads' : disk_reads,
                            'read_io' : read_io,
                            'writes' : disk_writes,
                            'write_io' : write_io,
                            'errors' : disk_errors,
                            'space_used' : space_used,
                            'space_available' : space_available
                        }
            
                disks.append(disk_dict)
        return disks
    
    def mover_run(self):
        if not self.authenticated():
            self.authenticated(force=True)
        form_data = {
            "cmdStartMover": "Move",
            "csrf_token" : self._csrf_token
        }
        try:
            response = self.session.post(self.host+'/update.htm', data=urlencode(form_data))
            if response.status_code == 200:
                return True
            else:
                return False
        except:
            return False

    def mover_running(self):
        if not self.authenticated():
            self.authenticated(force=True)
        json = self._server_details()
        mover_running = json['shareMoverActive']
        if mover_running == "yes":
            return True
        elif mover_running == "no":
            return False
        else:
            return False
        
    def archive_notification(self, notification=None):
        if not notification:
            return False
        if not self.authenticated():
            self.authenticated(force=True)
        form_data = {
            "cmd" : "archive",
            "file" : notification['file'],
            "csrf_token" : self._csrf_token
        }
        try:
            response = self.session.post(self.host+'/webGui/include/Notify.php', data=urlencode(form_data))
            if response.status_code == 200:
                return True
            else:
                return False
        except:
            return False
            
    def notifications(self):
        if not self.authenticated():
            self.authenticated(force=True)
        form_data = {
            "cmd" : "get",
            "csrf_token" : self._csrf_token
        }
        response = self.session.post(self.host+'/webGui/include/Notify.php', data=urlencode(form_data))
        return response.json()
        
    def parity_check_state(self):
        if not self.authenticated():
            self.authenticated(force=True)
        response = self.session.get(self.host+'/Main')
        if len(re.findall('input type="button" id="pauseButton" value="Pause" onclick="pauseParity', response.text)) > 0:
            state = "running"
        elif len(re.findall('input type="button" id="pauseButton" value="Resume" onclick="resumeParity', response.text)) > 0:
            state = "paused"
        else:
            state = "idle"
            parity_dict = {
                "state": state,
                "total_size" : "",
                "elapsed_time" : "",
                "current_position" : "",
                "estimated_speed" :  "",
                "estimated_finish" : "",
                "sync_errors" : ""
            }
            return parity_dict
        
        current_state = self.disk_status("parity").split(';')
        
        parity_dict = {
            "state": state,
            "total_size" : current_state[0],
            "elapsed_time" : current_state[1],
            "current_position" : current_state[2],
            "estimated_speed" :  current_state[3],
            "estimated_finish" : current_state[4],
            "sync_errors" : current_state[5]
        }
        return parity_dict

    def parity_check(self, command="Start", correct=False):
        ''' command options: "Start", "Pause", "Resume", "Cancel" '''
        if not self.authenticated():
            self.authenticated(force=True)
        if command == "Start":
            if correct:
                optionCorrect = "correct"
            else:
                optionCorrect = ""
        
            form_data = {
	            "startState": "STARTED",
	            "file": "",
	            "cmdCheck": "Check",
	            "optionCorrect": optionCorrect,
	            "csrf_token": "C89632265091E735"
            }
        elif command == "Resume":
            form_data = {
	            "startState": "STARTED",
	            "file": "",
	            "cmdCheck": command,
	            "csrf_token": "C89632265091E735"
            }
        else:
            form_data = {
	            "startState": "STARTED",
	            "file": "",
	            "csrf_token": "C89632265091E735",
	            "cmdNoCheck" : command
            }
            
        try:
            response = self.session.post(self.host+'/update.htm', data=urlencode(form_data))
            if response.status_code == 200:
                return True
            else:
                return False
        except:
            return False
        
    def parity_history(self):
        ''' date, duration, speed, status, errors '''
        if not self.authenticated():
            self.authenticated(force=True)
        response = self.session.get(self.host+'/webGui/include/ParityHistory.php')
        html = BeautifulSoup(response.text, features="html.parser")
        data = html.tbody
        parity_check_results = []
        if html.thead.find_all('td')[0].text == "Action":
            for row in data.find_all('tr'):
                data_points = row.find_all('td')
                try:
                    date = datetime.strptime(data_points[1].text, '%Y-%m-%d, %H:%M:%S')
                except:
                    date = None
                try:
                    errors = int(data_points[5].text.strip())
                except:
                    errors = ''
                check_result = {
                    "action": data_points[0].text.strip(),
                    "date" : date,
                    "duration" : data_points[2].text,
                    "speed" : data_points[3].text,
                    "status" : data_points[4].text,
                    "errors" : errors,
                    "elapsed_time" : data_points[6].text,
                    "increments" : data_points[7].text
                }
                parity_check_results.append(check_result)    
        else:
            for row in data.find_all('tr'):
                data_points = row.find_all('td')
                check_result = {
                    "date" : datetime.strptime(data_points[0].text, '%Y-%m-%d, %H:%M:%S'),
                    "duration" : data_points[1].text,
                    "speed" : data_points[2].text,
                    "status" : data_points[3].text,
                    "errors" : int(data_points[4].text.strip())
                }
                parity_check_results.append(check_result)
        return parity_check_results
        
    def server_guid(self):
        return self._guid
        
    def server_name(self):
        return self._server_name
        
    def server_version(self):
        return self._server_version
        

def main():
    host = input("Host of Unraid server (ie. http://tower.local or http://192.168.0.1):")
    username = input("Username for Unraid webGUI login (ie. root):")
    password = input("Password for unraid username %s:" % username)
    server = Unraid_Session(host=host, username=username, password=password)
    print(server.array_state())
    
if __name__ == "__main__":
    main()
