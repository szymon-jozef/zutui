import json
import os
import keyring
from keyring.errors import KeyringError
from datetime import datetime
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, DataTable, Label, Button, Input
from textual.screen import Screen
from textual.binding import Binding

from .zut_client import ZUT
from .config import get_config_path

APP_DIR = get_config_path()

CONFIG_FILE = os.path.join(APP_DIR, "config.json")
REFRESH_INTERVAL = 1800

class LoginScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Container(
            Label("ZUT e-Dziekanat Login", id="login_title"),
            Input(placeholder="Login (ID)", id="user"),
            Input(placeholder="Hasło", password=True, id="pass"),
            Button("Zaloguj się", variant="primary", id="login_btn"),
            Label("", id="status_msg"),
            id="login_dialog"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.submit_login()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.submit_login()

    def submit_login(self):
        user = self.query_one("#user", Input).value
        password = self.query_one("#pass", Input).value
        
        if not user or not password:
            self.query_one("#status_msg", Label).update("[!] Proszę wypełnić wszystkie pola.")
            return

        self.app.zut_client = ZUT(user, password)
        self.query_one("#status_msg", Label).update("Trwa logowanie...")
        self.query_one("#login_btn", Button).disabled = True
        self.query_one("#user", Input).disabled = True
        self.query_one("#pass", Input).disabled = True
        
        self.run_worker(self.perform_login_action(user, password), thread=True)

    def perform_login_action(self, user, password):
        def job():
            success = self.app.zut_client.login()
            if success:
                try:
                    with open(CONFIG_FILE, "w") as f:
                        json.dump({"username": user}, f)
                        keyring.set_password("zutui", user, password)
                except KeyringError as e:
                    error = e
                    self.app.call_from_thread(
                            lambda:
                                self.app.notify(
                                    f"Błąd: {str(error)}",
                                    title="Błąd zapisu hasła do systemowego menedżera haseł",
                                    severity="warning",
                                    timeout=5
                                    )
                            )
                except: pass
                def do_switch():
                    self.app.switch_screen(DashboardScreen())
                self.app.call_from_thread(do_switch)
            else:
                def show_error():
                    self.query_one("#status_msg", Label).update("[!] Błąd logowania.")
                    self.query_one("#login_btn", Button).disabled = False
                    self.query_one("#user", Input).disabled = False
                    self.query_one("#pass", Input).disabled = False
                    self.query_one("#pass", Input).focus()
                self.app.call_from_thread(show_error)
        return job

class DetailsScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Zamknij")]

    def __init__(self, subject_data):
        super().__init__()
        self.subject_data = subject_data

    def compose(self) -> ComposeResult:
        yield Container(
            Label(f"{self.subject_data['subject']} - Szczegóły", classes="details_title"),
            DataTable(id="details_table"),
            Button("Zamknij (Esc)", variant="error", id="close_btn"),
            classes="modal_container"
        )

    def on_mount(self):
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Opis", "Ocena", "Data", "Nauczyciel")
        
        partials = self.subject_data.get("partial_grades", [])
        
        if not partials:
            table.add_row("Brak ocen cząstkowych", "-", "-", "-")
        else:
            for p in partials:
                val = p.get("grade", "-")
                color = "red" if "2" in val else "green"
                fmt_val = f"[{color}]{val}[/]"
                
                table.add_row(
                    p.get("desc", "-"),
                    fmt_val,
                    p.get("date", "-"),
                    p.get("teacher", "-")
                )
        table.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.app.pop_screen()

class GradesTable(DataTable):
    BINDINGS = [
        Binding("enter", "select_cursor", "Pokaż szczegóły", priority=True),
        Binding("j", "cursor_down", "W dół"),
        Binding("k", "cursor_up", "W górę"),
    ]

class DashboardScreen(Screen):
    BINDINGS = [
        ("f5", "refresh_grades", "Odśwież dane")
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Twoje Oceny", classes="table_title"),
            Label("Ostatnia aktualizacja: Teraz", id="status_bar", classes="status_ok"),
            GradesTable(id="grades_table"),
            id="main_container"
        )
        yield Container(
            Label("F5 - Odśwież dane"),
            Label("Enter - szczegóły ocen cząstkowych"),
            id="info_container"
        )

    def on_mount(self) -> None:
        self.current_data = {}
        table = self.query_one(GradesTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Przedmiot", "Typ", "Oceny Częściowe", "Semestr 1", "Poprawka 1", "Poprawka 2", "Komis")
        
        cached_data = self.app.zut_client.load_cache()
        if cached_data:
            self.update_table(cached_data)
            self.query_one("#status_bar", Label).update("[+] Załadowano z pamięci. Odświeżanie...")
        else:
            self.query_one("#status_bar", Label).update("[?] Pobieranie danych...")
            table.loading = True

        self.run_worker(self.refresh_data_worker, exclusive=True, thread=True)
        self.set_interval(REFRESH_INTERVAL, self.scheduled_refresh)

    def action_refresh_grades(self):
        self.query_one("#status_bar", Label).update("[!] Wymuszanie odświeżania...")
        self.query_one(GradesTable).loading = True
        self.run_worker(self.refresh_data_worker, exclusive=True, thread=True)

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        row_key = event.row_key.value
        if row_key and row_key in self.current_data:
            self.app.push_screen(DetailsScreen(self.current_data[row_key]))

    def scheduled_refresh(self):
        self.query_one("#status_bar", Label).update("[?] Sprawdzanie aktualizacji...")
        self.run_worker(self.refresh_data_worker, exclusive=True, thread=True)

    def refresh_data_worker(self): 
        try:
            if not self.app.zut_client.is_logged_in:
                if not self.app.zut_client.login():
                    self.app.call_from_thread(self.query_one("#status_bar", Label).update, "[!] Błąd ponownego logowania")
                    return

            new_data = self.app.zut_client.refresh_data()
            now = datetime.now().strftime("%H:%M:%S")
            
            if new_data:
                self.app.call_from_thread(self.update_table, new_data)
                self.app.call_from_thread(self.query_one("#status_bar", Label).update, f"[+] Zaktualizowano: {now}")
            else:
                self.app.call_from_thread(self.query_one("#status_bar", Label).update, f"[!] Błąd sieci: {now}")
        
        except Exception as e:
            self.app.call_from_thread(self.query_one("#status_bar", Label).update, f"[!] Błąd: {str(e)}")
        
        finally:
            def stop_loading():
                try: self.query_one(GradesTable).loading = False
                except: pass
            self.app.call_from_thread(stop_loading)

    def update_table(self, data):
        self.current_data = data
        table = self.query_one(GradesTable)
        table.clear()
        
        for key, item in data.items():
            finals = item['final_grades']
            
            def fmt_grade(g_obj):
                if not g_obj: return "-"
                val = g_obj['grade'].replace(',', '.')
                color = "red" if "2" in val else "green"
                return f"[{color}]{val}[/]"

            partials_list = item.get('partial_grades', [])
            if partials_list:
                p_str_list = []
                for p in partials_list:
                    raw_val = p['grade'].strip().replace(',', '.')
                    p_str_list.append(f"[cyan]{raw_val}[/]")
                p_str = ", ".join(p_str_list)
            else:
                p_str = "[dim]-[/dim]"

            table.add_row(
                f"[bold]{item['subject']}[/]", item['type'], p_str,
                fmt_grade(finals.get('term_1')), fmt_grade(finals.get('retake_1')),
                fmt_grade(finals.get('retake_2')), fmt_grade(finals.get('commission')),
                key=key
            )

class ZutApp(App):
    TITLE = "ZUT e-Dziekanat"
    CSS = """
    Screen { 
        align: center middle; 
        background: #0e0e0e;
    }
    
    #login_dialog { 
        width: 60; 
        height: auto; 
        border: solid rgb(40,40,40); 
        padding: 1;
        background: #0e0e0e; 

        Input { 
            background: rgb(20, 20, 20); 
            border: wide rgb(40, 40, 40); 
            color: rgb(225, 225, 225);
            height: auto;
            padding: 1;
            margin: 0 0; 
        }

        Button { 
            background: rgb(30, 30, 30); 
            border: wide rgb(40, 40, 40);
            width: 100%;
            padding: 1;
            margin: 0 0;
            &:hover { background: rgb(50, 50, 50); }
            &:disabled { background: rgb(20, 20, 20); color: rgb(80, 80, 80); }
        }
    }

    #login_title { 
        text-align: center; 
        width: 100%; 
        margin-bottom: 1; 
    }

    #status_msg { 
        text-align: center; 
        width: 100%; 
        color: red; 
        margin-top: 0; 
    }
     
    #main_container { 
        width: 100%; 
        height: 1fr; 
        padding: 1;
        background: #0e0e0e; 
        border: wide #282828;
    }

    .table_title { 
        background: rgb(27,27,27); 
        color: rgb(225,225,225); 
        width: 100%; 
        padding: 1 1;
        text-align: center; 
        text-style: bold;
        border-left: wide #282828;
        border-right: wide #282828;
        border-top: wide #282828;
    }

    #status_bar { 
        width: 100%;
        height: auto;
        background: rgb(19,19,19); 
        color: #a0a0a0; 
        padding: 1 1; 
        border-left: wide #282828;
        border-right: wide #282828;
        border-bottom: wide #282828;
    }

    #info_container { 
        width: 100%;
        height: auto;
        background: #0e0e0e;
        background-tint: black 0%;
        color: rgb(150, 150, 150);
        border: wide rgb(40, 40, 40);
        padding: 1 1;
    }
    
    DataTable { 
        height: 1fr; 
        width: 100%; 
        background: rgb(10, 10, 10);
        border: wide #282828;   
        padding: 1;
        scrollbar-color: rgb(50, 50, 50);
        scrollbar-background: rgb(20, 20, 20);

        &:focus {
            background-tint: black 0%;
            & > .datatable--cursor {
                background: rgb(60, 60, 60);
            }

            & > .datatable--header {
                background-tint: black 0%;
                background: rgb(22, 22, 22);
            }

            & > .datatable--fixed-cursor {
                color: $block-cursor-foreground;
                background: $block-cursor-background;
            }
        }

        & > .datatable--even-row {
            background: rgb(15, 15, 15);
        }
    }

    .modal_container { 
        width: 80%; 
        height: 80%; 
        border: thick #282828; 
        background: rgb(17, 17, 17); 
        align: center middle; 
        padding: 1;
        layout: vertical;
    }

    .details_title {
        text-align: center;
        width: 100%;
        text-style: bold;
        background: rgb(19,19,19);
        color: rgb(225,225,225);
        margin-bottom: 1;
        padding: 1;
    }

    #details_table {
        height: 1fr;
        width: 100%;
        margin-bottom: 1;
        background: rgb(17, 17, 17);
        border: wide #282828;

        &:focus {
            background-tint: black 0%;
            & > .datatable--cursor {
                background: rgb(60, 60, 60);
            }

            & > .datatable--header {
                background-tint: black 0%;
                background: rgb(22, 22, 22);
            }

            & > .datatable--fixed-cursor {
                color: $block-cursor-foreground;
                background: $block-cursor-background;
            }
        }

        & > .datatable--even-row {
            background: rgb(15, 15, 15);
        }
    }

    #close_btn {
        width: 100%;
    }
    """

    def on_mount(self) -> None:
        self.zut_client = None
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    creds = json.load(f)
                    password = keyring.get_password("zutui", creds["username"])
                    if password is None:
                        raise ValueError("Hasło nie zostało znalezione")
                    self.zut_client = ZUT(creds["username"], password)
                    self.push_screen(DashboardScreen())
            except:
                self.push_screen(LoginScreen())
        else:
            self.push_screen(LoginScreen())

def main():
    app = ZutApp()
    app.run()

if __name__ == "__main__":
    main()
