# SERIAL-TO-CSV
Simple Serial (RS232) Monitoring for CSV Logging

This project is a lightweight RS-232 data acquisition tool with GUI that continuously monitors a selected serial port (e.g., COM1) at a configurable baud rate such as 19200 bps. When ASCII data arrives, it automatically starts recording and writes the stream directly to a comma-delimited CSV file. After two seconds of inactivity, the current file is closed and saved, and a new file is created when fresh data appears. The program includes a simple GUI for selecting the COM port, baud rate, and output directory, shows live connection status, logs activity in real time, and organizes each capture with timestamped filenames for easy record keeping. Provided as a python executable EXE for standalone deployment.

This project was originally designed for use with a TestResources 200Q Universal Test Machine that exports data via RS232 serial at 19200 baud. This script allows a computer connected via a RS232 DB9 to USB cable adapter to log the data output directly to a CSV file for further analysis.


<img width="1777" height="900" alt="image" src="https://github.com/user-attachments/assets/f5b5e633-0a28-4d62-9a27-dba6c75f8a71" />
