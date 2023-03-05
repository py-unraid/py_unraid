import aiohttp, asyncio
from bs4 import BeautifulSoup
from datetime import datetime
import json
import re

# TODO: Handle case when server is on but array is not started.

headers = {'Content-Type': 'application/x-www-form-urlencoded','Connection': 'keep-alive'}

class Unraid_Session:
    
    def __init__(self, session, host = '', username = '', password = ''):
        ''' instantiate an unraid server session '''
        self.host = host
        self.username = username
        self.password = password
        
        self.session = session
        
        self._csrf_token = None
        self._server_name = None
        self._server_version = None
        self._guid = None
    
    async def authenticated(self, force=False):
        if not force:
            if self._csrf_token:
                return True
        else:
            await self.authenticate()

    async def authenticate(self):
        form_data = {
            "username" : self.username,
            "password" : self.password
        }
        async with self.session.post('/login', data = form_data, allow_redirects = False) as response:
            try:
                if response.status == 302:
                    server_details = await self._server_details()
                    self._server_name = server_details['NAME']
                    self._csrf_token = server_details['csrf_token']
                    self._server_version = server_details['version']
                    self._guid = server_details['regGUID']
                    return 'authenticated'
                elif response.status == 200:
                    return 'authentication failed'
                else:
                    return 'failed to connect'
            except:
                return 'failed to connect'
    
    async def _server_details(self):
        async with self.session.get('/Main') as response:
            page = await response.text()
            details_json = json.loads(re.findall('var vars        = ({"version":.+?"});', page)[0])
            return details_json
    
    async def array_state(self):
        ''' return the start/stop state of the array '''
        if not await self.authenticated():
            await self.authenticated(force=True)
        async with self.session.get('/Main') as response:
            html = BeautifulSoup(await response.text(), features="html.parser")
            state = html.find_all(attrs={"name":"startState"})[0].get('value')
            return state
        
    async def disk_status(self, disk='array'):
        ''' fetch the status details for the relevant disk(s) and parse it '''
        if not await self.authenticated():
            await self.authenticated(force=True)
        form_data = {
            "path" : "Main",
            "device" : disk,
            "csrf_token" : self._csrf_token
        }
        async with self.session.post("/webGui/include/DeviceList.php", data=form_data) as response:
            page = await response.text()
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
    
    async def mover_run(self):
        if not await self.authenticated():
            await self.authenticated(force=True)
        form_data = {
            "cmdStartMover": "Move",
            "csrf_token" : self._csrf_token
        }
        try:
            async with self.session.post('/update.htm', data=form_data) as response:
                if response.status == 200:
                    return True
                else:
                    return False
        except:
            return False

    async def mover_running(self):
        if not await self.authenticated():
            await self.authenticated(force=True)
        json = await self._server_details()
        mover_running = json['shareMoverActive']
        if mover_running == "yes":
            return True
        elif mover_running == "no":
            return False
        else:
            return False
        
    async def archive_notification(self, notification=None):
        if not notification:
            return False
        if not await self.authenticated():
            await self.authenticated(force=True)
        form_data = {
            "cmd" : "archive",
            "file" : notification['file'],
            "csrf_token" : self._csrf_token
        }
        try:
            async with self.session.post('/webGui/include/Notify.php', data=form_data) as response:
                if response.status == 200:
                    return True
                else:
                    return False
        except:
            return False
            
    async def notifications(self):
        if not await self.authenticated():
            await self.authenticated(force=True)
        form_data = {
            "cmd" : "get",
            "csrf_token" : self._csrf_token
        }
        async with self.session.post('/webGui/include/Notify.php', data=form_data) as response:
            notifications = json.loads(await response.text())
            return notifications
        
    async def parity_check_state(self):
        if not await self.authenticated():
            await self.authenticated(force=True)
        async with self.session.get('/Main') as response:
            if len(re.findall('input type="button" id="pauseButton" value="Pause" onclick="pauseParity', await response.text())) > 0:
                state = "running"
            elif len(re.findall('input type="button" id="pauseButton" value="Resume" onclick="resumeParity', await response.text())) > 0:
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
        
            current_state = await self.disk_status(disk="parity").split(';')
        
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

    async def parity_check(self, command="Start", correct=False):
        ''' command options: "Start", "Pause", "Resume", "Cancel" '''
        if not await self.authenticated():
            await self.authenticated(force=True)
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
            async with self.session.post('/update.htm', data=form_data) as response:
                if response.status == 200:
                    return True
                else:
                    return False
        except:
            return False
        
    async def parity_history(self):
        ''' date, duration, speed, status, errors '''
        if not await self.authenticated():
            await self.authenticated(force=True)
        async with self.session.get('/webGui/include/ParityHistory.php') as response:
            html = BeautifulSoup(await response.text(), features="html.parser")
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
        

async def main():
    host = input("Host of Unraid server (ie. http://tower.local or http://192.168.0.1):")
    username = input("Username for Unraid webGUI login (ie. root):")
    password = input("Password for unraid username %s:" % username)

    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(base_url=host, headers=headers, cookie_jar=jar) as session:
        server = Unraid_Session(session, host=host, username=username, password=password)
        print(await server.authenticate())
        print(server.server_name())
        print(server.server_guid())
        print(server.server_version())
        print(await server.array_state())
        print(await server.disk_status(disk='flash'))
        print(await server.disk_status(disk='cache'))
        print(await server.disk_status(disk='array'))
        print(await server.mover_running())
        print(await server.notifications())
        print(await server.parity_check_state())
        print(await server.parity_history())
    
    
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(main())
