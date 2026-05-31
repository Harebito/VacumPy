import serial, serial.tools.list_ports ,sqlite3
import tkinter as tk
from tkinter import ttk
from datetime import datetime

import traceback

class DB_Handler:
    def __init__(self) -> None:
        self.current_date_str = datetime.now().strftime("%Y_%m_%d")
        self.db_name = f"Vacuumeter_log_{self.current_date_str}.db"
        self.connection = None

    def connect(self): # Connect to database
        try:
            self.connection = sqlite3.connect(self.db_name)
            print(f"Connected to {self.db_name}")
        except sqlite3.Error as e:
            print(f"CRITICAL: Failed to open {self.db_name}")
            print(f"Details: {e}")

    def create_table(self): # Create table, runs once per database
        if self.connection is None:
            print("ERROR: Not connected to database. Not connected!")
            return
        
        try:
            cursor = self.connection.cursor()
            _ = cursor.execute("""
                CREATE TABLE IF NOT EXISTS sensors_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    sensor_1 INTEGER,
                    sensor_2 INTEGER,
                    sensor_3 INTEGER
                )
            """)
            self.connection.commit()
            print("Table created successfully")
        except sqlite3.Error as e:
            print(f"ERROR: Failed to create table: {e}")

    def write(self, parsed_data): # Write actual data to database
        self._rotate_if_needed() # Check if rotation is needed

        if self.connection is None:
            print("ERROR: Cannot write to database. Not connected!")
            return
        
        try:
            cursor = self.connection.cursor()
            _ = cursor.execute("""
                INSERT INTO sensors_data (timestamp, sensor_1, sensor_2, sensor_3) 
                VALUES (:time, :s1, :s2, :s3)
            """, {
                "time": parsed_data["timestamp"],
                "s1": parsed_data["sensor_1"],
                "s2": parsed_data["sensor_2"],
                "s3": parsed_data["sensor_3"]
            })

            self.connection.commit()
            print(f"Saved row: {parsed_data}")

        except sqlite3.Error as e:
            print(f"ERROR: Failed to insert data: {e}")

    def _rotate_if_needed(self):
        today_str = datetime.now().strftime("%Y_%m_%d")

        if today_str != self.current_date_str: # If day changes
            print("Midnight passed! Rotating database...")

            self.close()

            self.current_date_str = today_str
            self.db_name = f"Vacuumeter_log_{self.current_date_str}.db"

            self.connect()
            self.create_table()


    def close(self): # Safely close database
        if self.connection is not None:
            try:
                self.connection.close()
                print("Database connection closed safely.")
            except sqlite3.Error as e:
                print(f"ERROR: Failed to close database safely: {e}")
            finally:
                self.connection = None

class Serial_handler:
    def __init__(self, baudrate=9600) -> None:
        self.baudrate = baudrate
        self.connection = None

    def list_ports(self): #List all valid non-empty ttyUSB
        valid_ports = []

        available_ports = serial.tools.list_ports.comports() 

        for port in available_ports:

            device_name = port.device.upper()

            if "USB" in device_name or "ACM" in device_name or "COM" in device_name:
                valid_ports.append(port.device)

        return valid_ports

    def connect(self, port_name): #Connect to device
        try:
            self.connection = serial.Serial(port_name, baudrate=self.baudrate, timeout=1)
            print(f"SUCCESS: Connect to {port_name}")
            return True

        except serial.SerialException as e:
            print(f"CRITICAL: Failer to open {port_name}")
            print(f"Details: {e}")
            return False

    def close(self):
        if self.connection is not None and self.connection.is_open:
            self.connection.close()
            print("Serial port closed safely.")
            self.connection = None

class Ui:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Vacuumapp")
        self.root.geometry("400x200")

        self.serial = Serial_handler()
        self.db = DB_Handler()

        self.label = tk.Label(self.root, text="Select a port and start", font=("Arial", 12))
        self.label.pack(pady=10)

        self.port_frame = tk.Frame(self.root)
        self.port_frame.pack(pady=5)

        self.port_selector = ttk.Combobox(self.port_frame, state="readonly", width=20)
        self.port_selector.pack(side=tk.LEFT, padx=5)
        
        self.refresh_button = tk.Button(self.root, text="Start Scan", command=self.on_button_click)
        self.refresh_button.pack(side=tk.LEFT, padx=5)

        self.refresh_ports()

        self.start_button = tk.Button(self.root, text="Start Scan", command=self.on_button_click)
        self.start_button.pack(pady=15)

    def refresh_ports(self) -> None:
        available_ports = self.serial.list_ports()

        self.port_selector['values'] = available_ports

        if available_ports:
            self.port_selector.current(0)
            self.label.config(text="Select a port and start", fg="black")
        else:
            self.port_selector.set("No USB devices found")
            self.label.config(text="Plug in a device and click Refresh", fg="orange")


    def on_button_click(self) -> None:
        selected_port = self.port_selector.get()

        if selected_port == "No USB devices found" or selected_port == "":
            self.label.config(text="Error: No valid port selected!", fg="red")
            return
        self.label.config(text=f"Connecting to {selected_port}...", fg="black")
        success = self.serial.connect(selected_port)

        if success:
            self.label.config(text=f"Scanning on {selected_port}...", fg="green")

            self.start_button.config(state="disabled")
            self.refresh_button.config(state="disabled")
            self.port_selector.config(state="disabled")
        else:
            self.label.config(text=f"Failed to open {selected_port}", fg="red")


    def run(self) -> None:
        print("Starting Application...")
        self.root.mainloop()


if __name__ == "__main__":
    try:
        print("1. Attempting to start the app...")
        app = Ui()
        print("2. UI Object created successfully. Starting mainloop...")
        app.run()
    except Exception as e:
        print("\n=== CRASH DETECTED ===")
        print(f"Error: {e}")
        traceback.print_exc() # This prints the exact line number of the crash
        input("\nPress Enter to exit...") # This forces the terminal to stay open!
