import serial, serial.tools.list_ports, sqlite3
import tkinter as tk
from tkinter import ttk
from datetime import datetime # For midnight DB rotation
from pathlib import Path
from typing import final
import threading, time

import traceback #DEBUG

@final
class DB_Handler:
    def __init__(self) -> None:
        self.data_dir = Path("logs")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Get current Year, Month, Day for database name
        self.current_date_str = datetime.now().strftime("%Y_%m_%d")
        self.db_name = self.data_dir / f"Vacuumeter_log_{self.current_date_str}.db"

        self.connection = None

    def connect(self): # Connect to database
        try: # check_same_thread=False to allow the background thread to write data safely
            self.connection = sqlite3.connect(self.db_name, check_same_thread=False)
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
        """ We check if database rotation is needed before write to no initialize empty database
        if app is running but no device connected/we are connected but packets are not sent"""

        if self.connection is None:
            print("ERROR: Cannot write to database. Not connected!")
            return

        try:
            cursor = self.connection.cursor()
            _ = cursor.execute("""
                INSERT INTO sensors_data (timestamp, sensor_1, sensor_2, sensor_3) 
                VALUES (:time, :s1, :s2, :s3)
            """, {
                "time": parsed_data["time"],
                "s1": parsed_data["s1"],
                "s2": parsed_data["s2"],
                "s3": parsed_data["s3"]
                })

            self.connection.commit()
            print(f"Saved row: {parsed_data}")

        except sqlite3.Error as e:
            print(f"ERROR: Failed to insert data: {e}")
            self.close()

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
@final
class Serial_handler:
    def __init__(self, baudrate=115200) -> None:
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
            self.connection = serial.Serial(port_name, baudrate=self.baudrate, timeout=0)
            print(f"SUCCESS: Connect to {port_name}")
            return True

        except serial.SerialException as e:
            print(f"CRITICAL: Failed to open {port_name}")
            print(f"Details: {e}")
            return False

    def close(self):
        if self.connection is not None and self.connection.is_open:
            self.connection.close()
            print("Serial port closed safely.")
            self.connection = None
@final
class Ui:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Vacuumapp")
        self.root.geometry("400x200")

        # Serial connection and Database objects
        self.serial = Serial_handler()
        self.db = DB_Handler()
        self.db.connect()
        self.db.create_table()

        self.data_buffer = ""
        self.is_scanning = False
        self.read_thread = None

        # Window customisation
        self.label = tk.Label(self.root, text="Select a port and start", font=("Arial", 12))
        self.label.pack(pady=10)

        self.port_frame = tk.Frame(self.root)
        self.port_frame.pack(pady=5)

        self.port_selector = ttk.Combobox(self.port_frame, state="readonly", width=20)
        self.port_selector.pack(side=tk.LEFT, padx=5)

        self.refresh_button = tk.Button(self.root, text="Refresh", command=self.refresh_ports)
        self.refresh_button.pack(side=tk.LEFT, padx=5)

        self.start_button = tk.Button(self.root, text="Connect", command=self.on_button_click)
        self.start_button.pack(pady=15)
        
        self.stop_button = tk.Button(self.root, text="Disconnect", command=self.on_stop_click, state="disabled")
        self.stop_button.pack(pady=5) 

        # First refresh to list if device was connected before launching the app
        self.refresh_ports()

    def refresh_ports(self) -> None:
        available_ports = self.serial.list_ports()

        self.port_selector['values'] = available_ports

        if available_ports:
            _ = self.port_selector.current(0)
            _ = self.label.config(text="Select a port and start", fg="black")
        else:
            self.port_selector.set("No USB devices found")
            _ = self.label.config(text="Plug in a device and click Refresh", fg="orange")


    def on_button_click(self) -> None:
        if self.db.connection is None:
            _ = self.label.config(text="ERROR: Failed connecting to database.", fg="red")
            return

        selected_port = self.port_selector.get()

        if selected_port == "No USB devices found" or selected_port == "":
            _ = self.label.config(text="Error: No valid port selected!", fg="red")
            return

        success = self.serial.connect(selected_port)

        if success:
            _ = self.label.config(text=f"Scanning on {selected_port}...", fg="green")
            _ = self.start_button.config(state="disabled") 
            _ = self.refresh_button.config(state="disabled")
            _ = self.port_selector.config(state="disabled")
            _ = self.stop_button.config(state="normal")
            
            self.is_scanning = True
            self.read_thread = threading.Thread(target=self._usb_thread_worker, daemon=True)
            self.read_thread.start()

        else:
            _ = self.label.config(text=f"Failed to open {selected_port}", fg="red")

    def on_stop_click(self) -> None:
        self.is_scanning = False

        self.serial.close()

        _ = self.label.config(text="Disconnected. Ready.", fg="black")
        _ = self.start_button.config(state="normal")
        _ = self.refresh_button.config(state="normal")
        _ = self.port_selector.config(state="readonly") # Comboboxes use 'readonly', not 'normal'
        _ = self.stop_button.config(state="disabled")

    def _usb_thread_worker(self) -> None:
        #        print("Background worker thread started!")

        while self.is_scanning and self.serial.connection and self.serial.connection.is_open:
            try:
                bytes_waiting = self.serial.connection.in_waiting
                if bytes_waiting > 0:
                    raw_bytes = self.serial.connection.read(bytes_waiting)
                    
                    # Notice: NO .strip() here, so we don't mangle chunks mid-stream!
                    self.data_buffer += raw_bytes.decode('utf-8', errors='ignore')

                    while "$" in self.data_buffer and ";;" in self.data_buffer:
                        start_idx = self.data_buffer.find("$")
                        end_idx = self.data_buffer.find(";;")

                        if end_idx < start_idx:
                            self.data_buffer = self.data_buffer[start_idx:]
                            continue

                        packet = self.data_buffer[start_idx : end_idx + 2]
                        self.data_buffer = self.data_buffer[end_idx + 2 :]

                        parsed_data = self.parse_payload(packet)
                        if parsed_data:
                            print(f"THREAD CAPTURED: {packet}")
                            self.db.write(parsed_data)

                            if self.db.connection is None:
                                print("CRITICAL: Database connection lost!")
                                self.is_scanning = False

                                _ = self.root.after(0, self.on_stop_click)
                                _ = self.root.after(100, lambda: self.label.config(text="ERROR: Write halted!", fg="red"))
                                break

            except Exception as e:
                print(f"CRITICAL: Thread USB Read Error: {e}")

                self.is_scanning = False

                _ = self.root.after(0, self.on_stop_click)
                _ = self.root.after(100, lambda: self.label.config(text="ERROR: Lost connection to device!", fg="red"))
                break

            # CRITICAL: Sleep for 10ms so this background thread doesn't max out your CPU
            time.sleep(0.01)

        print("Background thread worker stopped cleanly.")

    # Parses raw string into dict for database
    def parse_payload(self, packet: str):
        try:
            clean_str = packet.strip("$;")

            parts = clean_str.split(";")

            if len(parts) == 4:
                parsed_data = {
                        "time": parts[0],
                        "s1": float(parts[1]),
                        "s2": float(parts[2]),
                        "s3": float(parts[3])
                        }
                return parsed_data
            else:
                print(f"Warning: Incomplete packet dropped: {packet}")
                return None
        except Exception as e:
            print(f"Error parsing packet {packet}: {e}")
            return None


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
        _ = input("\nPress Enter to exit...") # This forces the terminal to stay open!
