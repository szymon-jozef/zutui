import requests
from bs4 import BeautifulSoup
import json
import os

from .config import get_config_path

APP_DIR = get_config_path()

CACHE_FILE = os.path.join(APP_DIR, "grades_cache.json")
TIMEOUT = 10

class ZUT:
    URLS = {
        "LOGIN": "https://edziekanat.zut.edu.pl/WU/Logowanie2.aspx",
        "FINAL": "https://edziekanat.zut.edu.pl/WU/OcenyP.aspx",
        "PARTIAL": "https://edziekanat.zut.edu.pl/WU/OcenyCzast.aspx",
        "NEWS": "https://edziekanat.zut.edu.pl/WU/News.aspx"
    }

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": "https://edziekanat.zut.edu.pl",
        })
        self.is_logged_in = False

    def load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_cache(self, data):
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Failed to save cache: {e}")

    def _get_hidden_inputs(self, soup):
        return {inp.get('name'): inp.get('value') for inp in soup.find_all('input', type='hidden') if inp.get('name')}

    def login(self):
        try:
            self.session.headers.update({"Referer": self.URLS["LOGIN"]})
            r = self.session.get(self.URLS["LOGIN"], timeout=TIMEOUT)
            soup = BeautifulSoup(r.text, 'html.parser')
            payload = self._get_hidden_inputs(soup)

            payload.update({
                'ctl00$ctl00$ContentPlaceHolder$MiddleContentPlaceHolder$txtIdent': self.username,
                'ctl00$ctl00$ContentPlaceHolder$MiddleContentPlaceHolder$txtHaslo': self.password,
                'ctl00$ctl00$ContentPlaceHolder$MiddleContentPlaceHolder$butLoguj': 'Zaloguj',
                'ctl00$ctl00$ContentPlaceHolder$MiddleContentPlaceHolder$rbKto': 'student'
            })

            post_response = self.session.post(self.URLS["LOGIN"], data=payload, timeout=TIMEOUT)
            
            if ".ASPX" in str(self.session.cookies.get_dict()) or "Wyloguj" in post_response.text:
                self.is_logged_in = True
                return True
            return False
        except Exception as e:
            print(f"Login Error: {e}")
            return False

    def get_final_grades(self):
        if not self.is_logged_in: return {}
        self.session.headers.update({"Referer": self.URLS["NEWS"]})
        try:
            resp = self.session.get(self.URLS["FINAL"], timeout=TIMEOUT)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            data = {}
            table = soup.find('table', id='ctl00_ctl00_ContentPlaceHolder_RightContentPlaceHolder_dgDane')
            if not table: return data

            for row in table.find_all('tr', class_='gridDane'):
                cells = row.find_all('td')
                if not cells: continue

                def parse_cell(c):
                    txt = [t.strip() for t in c.stripped_strings]
                    if not txt: return None
                    return {"grade": txt[0], "date": txt[1] if len(txt)>1 else ""}

                subject = cells[0].get_text(strip=True)
                ctype = cells[1].get_text(strip=True)
                key = f"{subject}_{ctype}"

                data[key] = {
                    "subject": subject,
                    "type": ctype,
                    "final_grades": {
                        "term_1": parse_cell(cells[5]),
                        "retake_1": parse_cell(cells[6]),
                        "retake_2": parse_cell(cells[7]),
                        "commission": parse_cell(cells[8]),
                    },
                    "partial_grades": []
                }
            return data
        except Exception:
            return {}

    def get_partial_grades(self):
        if not self.is_logged_in: return {}
        try:
            resp = self.session.get(self.URLS["PARTIAL"], timeout=TIMEOUT)
            soup = BeautifulSoup(resp.text, 'html.parser')
            payload = self._get_hidden_inputs(soup)
            
            payload.update({
                '__EVENTTARGET': 'ctl00$ctl00$ContentPlaceHolder$RightContentPlaceHolder$chb_ExpColAll',
                '__EVENTARGUMENT': '',
                'ctl00$ctl00$ContentPlaceHolder$RightContentPlaceHolder$chb_ExpColAll': 'on'
            })
            
            resp_expanded = self.session.post(self.URLS["PARTIAL"], data=payload, timeout=TIMEOUT)
            soup_exp = BeautifulSoup(resp_expanded.text, 'html.parser')
            
            partials_map = {}
            main_grid = soup_exp.find('table', id='ctl00_ctl00_ContentPlaceHolder_RightContentPlaceHolder_rg_Przedmioty_ctl00')
            if not main_grid: return {}

            rows = main_grid.find_all('tr')
            current_key = None

            for row in rows:
                classes = row.get('class', [])
                if ('rgRow' in classes or 'rgAltRow' in classes) and not row.find('table'):
                    cells = row.find_all('td')
                    if len(cells) > 2:
                        subj = cells[1].get_text(strip=True)
                        ctype = cells[2].get_text(strip=True)
                        current_key = f"{subj}_{ctype}"
                
                nested_table = row.find('table')
                if nested_table and current_key:
                    grades_list = []
                    for inner_row in nested_table.find_all('tr'):
                        icells = inner_row.find_all('td')
                        if len(icells) >= 4:
                            g_val = icells[2].get_text(strip=True)
                            if g_val:
                                grades_list.append({
                                    "grade": g_val,
                                    "desc": icells[1].get_text(strip=True) if len(icells) > 1 else "",
                                    "date": icells[3].get_text(strip=True) if len(icells) > 3 else "",
                                    "teacher": icells[4].get_text(strip=True) if len(icells) > 4 else ""
                                })
                    partials_map[current_key] = grades_list
            return partials_map
        except Exception:
            return {}

    def refresh_data(self):
        if not self.is_logged_in:
            if not self.login():
                return None
        try:
            finals = self.get_final_grades()
            partials = self.get_partial_grades()
            for key, p_grades in partials.items():
                if key in finals:
                    finals[key]['partial_grades'] = p_grades
            self.save_cache(finals)
            return finals
        except Exception as e:
            print(f"Refresh error: {e}")
            return None
