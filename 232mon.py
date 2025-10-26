# pip install pyserial
# Python 3.8+
import os
import time
import threading
import queue
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import serial
import serial.tools.list_ports

DEFAULT_BAUD = 19200
SILENCE_SEC = 2.0
READ_TIMEOUT = 0.1

class SerialMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RS-232 CSV Monitor")

        # State
        self.ser = None
        self.rx_thread = None
        self.stop_evt = threading.Event()
        self.rx_q = queue.Queue()
        self.out_dir = os.path.abspath("captures")
        os.makedirs(self.out_dir, exist_ok=True)
        self.buf = bytearray()
        self.last_rx = None
        self.csv_file = None

        # UI
        frm = ttk.Frame(root, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        ttk.Label(frm, text="Port").grid(row=0, column=0, sticky="w")
        self.port_cb = ttk.Combobox(frm, width=18, state="readonly")
        self.port_cb.grid(row=0, column=1, sticky="w")
        ttk.Button(frm, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=(6, 0))

        ttk.Label(frm, text="Baud").grid(row=1, column=0, sticky="w")
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        ttk.Entry(frm, textvariable=self.baud_var, width=10).grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Output").grid(row=2, column=0, sticky="w")
        self.out_lbl = ttk.Label(frm, text=self.out_dir, width=40)
        self.out_lbl.grid(row=2, column=1, sticky="w")
        ttk.Button(frm, text="Browse…", command=self.choose_dir).grid(row=2, column=2, padx=(6, 0))

        self.connect_btn = ttk.Button(frm, text="Connect", command=self.toggle_connect)
        self.connect_btn.grid(row=3, column=0, pady=(8, 0), sticky="w")

        self.status_dot = tk.Canvas(frm, width=14, height=14, highlightthickness=0)
        self.status_dot.grid(row=3, column=1, sticky="w", padx=(8, 0))
        self.status_txt = ttk.Label(frm, text="Disconnected")
        self.status_txt.grid(row=3, column=1, sticky="e", padx=(28, 0))
        self._set_status(False)

        ttk.Label(frm, text="Log").grid(row=4, column=0, sticky="nw", pady=(8, 0))
        self.log = tk.Text(frm, height=12, width=70, state="disabled")
        self.log.grid(row=4, column=1, columnspan=2, sticky="nsew", pady=(8, 0))
        frm.rowconfigure(4, weight=1)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Last file").grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.last_file_lbl = ttk.Label(frm, text="-")
        self.last_file_lbl.grid(row=5, column=1, columnspan=2, sticky="w", pady=(6, 0))

        self.refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(50, self.gui_pump)

    # ---------- UI helpers ----------
    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        if ports and not self.port_cb.get():
            self.port_cb.set(ports[0])

    def choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_dir, mustexist=True)
        if d:
            self.out_dir = d
            self.out_lbl.config(text=self.out_dir)

    def _set_status(self, connected: bool):
        self.status_dot.delete("all")
        color = "#2e7d32" if connected else "#b71c1c"
        self.status_dot.create_oval(2, 2, 12, 12, fill=color, outline=color)
        self.status_txt.config(text="Connected" if connected else "Disconnected")

    def log_line(self, s: str):
        self.log.configure(state="normal")
        self.log.insert("end", f"{datetime.now():%H:%M:%S}  {s}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---------- Connection ----------
    def toggle_connect(self):
        if self.ser and self.ser.is_open:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_cb.get().strip()
        if not port:
            messagebox.showwarning("Select Port", "Choose a serial port.")
            return
        try:
            baud = int(self.baud_var.get())
        except ValueError:
            messagebox.showerror("Baud Error", "Baud must be an integer.")
            return
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=READ_TIMEOUT,
            )
        except serial.SerialException as e:
            self.log_line(f"Connect failed: {e}")
            self._set_status(False)
            return

        self.log_line(f"Connected {port} @ {baud}")
        self._set_status(True)
        self.stop_evt.clear()
        self.rx_thread = threading.Thread(target=self.read_loop, daemon=True)
        self.rx_thread.start()
        self.connect_btn.config(text="Disconnect")

    def disconnect(self):
        self.stop_evt.set()
        if self.rx_thread:
            self.rx_thread.join(timeout=2)
        self._end_capture("disconnected")
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self._set_status(False)
        self.connect_btn.config(text="Connect")
        self.log_line("Disconnected")

    # ---------- Serial I/O ----------
    def read_loop(self):
        try:
            while not self.stop_evt.is_set():
                n = self.ser.in_waiting if self.ser else 0
                chunk = self.ser.read(n if n else 1) if self.ser else b""
                if chunk:
                    self.rx_q.put(chunk)
                else:
                    time.sleep(READ_TIMEOUT)
        except Exception as e:
            self.rx_q.put(("__EXC__", str(e)))

    def gui_pump(self):
        try:
            while True:
                item = self.rx_q.get_nowait()
                if isinstance(item, tuple) and item[0] == "__EXC__":
                    self.log_line(f"Serial error: {item[1]}")
                    self.disconnect()
                    break
                self._on_bytes(item)
        except queue.Empty:
            pass

        if self.csv_file and self.last_rx and (time.monotonic() - self.last_rx >= SILENCE_SEC):
            self._end_capture("silence")

        self.root.after(50, self.gui_pump)

    def _on_bytes(self, chunk: bytes):
        self.last_rx = time.monotonic()
        if self.csv_file is None:
            os.makedirs(self.out_dir, exist_ok=True)
            path = os.path.join(self.out_dir, f"capture_{datetime.now():%Y%m%d_%H%M%S}.csv")
            try:
                self.csv_file = open(path, "w", encoding="utf-8", newline="")
                self.log_line(f"Started file {os.path.basename(path)}")
            except Exception as e:
                self.log_line(f"File open failed: {e}")
                return

        self.buf.extend(chunk)
        data = self.buf.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        lines = data.split(b"\n")
        self.buf = bytearray(lines[-1])
        for line in lines[:-1]:
            if not line:
                continue
            try:
                self.csv_file.write(line.decode("utf-8", errors="replace"))
                self.csv_file.write("\n")
            except Exception as e:
                self.log_line(f"Write error: {e}")
                self._end_capture("error")
                return
        if self.csv_file:
            self.csv_file.flush()

    def _end_capture(self, reason: str):
        if self.csv_file:
            try:
                path = self.csv_file.name
                self.csv_file.close()
                self.last_file_lbl.config(text=path)
                self.log_line(f"Closed file ({reason}): {os.path.basename(path)}")
            except Exception as e:
                self.log_line(f"Close error: {e}")
            finally:
                self.csv_file = None
        self.buf.clear()
        self.last_rx = None

    # ---------- Lifecycle ----------
    def on_close(self):
        try:
            if self.ser and self.ser.is_open:
                self.disconnect()
        finally:
            self.root.destroy()

def main():
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    SerialMonitorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
