import os
import os.path as op
import tkinter as tk
from tkinter import filedialog, ttk
import threading  # Add this import

import humanize
from ncs_to_mat import convert_recording


class SimpleConverterGUI:
    def __init__(self, master):
        self.master = master
        master.title("NCS to MAT Converter")
        master.geometry("600x400")

        # Paths
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()

        # Input path selector
        self._add_path_selector("NCS input directory", self.input_dir, 0)
        self._add_path_selector("MAT output directory", self.output_dir, 1)

        # Progress bars
        self.recording_progress = self._add_progress_bar("Recordings progress", 2)
        self.file_progress = self._add_progress_bar("Files progress", 3)

        # Estimated time remaining
        tk.Label(master, text="Estimated time remaining:").grid(
            row=4, column=0, sticky="w", padx=10, pady=2)
        self.estimated_time_label = tk.Label(
            master, text="", font=("Arial", 10, "italic"))
        self.estimated_time_label.grid(
            row=4, column=1, columnspan=2, sticky="w")

        # Log box
        tk.Label(master, text="Log:").grid(row=5, column=0, sticky="nw", padx=10)
        self.log_box = tk.Text(master, height=8, width=70)
        self.log_box.grid(row=6, column=0, columnspan=3, padx=10, pady=5)

        # Dummy "Start" button for testing
        self.start_button = tk.Button(master, text="Start Processing", command=self.start_processing)
        self.start_button.grid(row=7, column=0, columnspan=3, pady=10)

        # center the window
        self.master.update_idletasks()  # Ensure window dimensions are calculated

        # Get window size
        width = self.master.winfo_width()
        height = self.master.winfo_height()

        # Get screen size
        x = (self.master.winfo_screenwidth() // 2) - (width // 2)
        y = (self.master.winfo_screenheight() // 2) - (height // 2)

        # Center the window
        self.master.geometry(f'{width}x{height}+{x}+{y}')

    def _add_path_selector(self, label_text, var, row):
        tk.Label(self.master, text=label_text).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        entry = tk.Entry(self.master, textvariable=var, width=50)
        entry.grid(row=row, column=1, pady=5)
        tk.Button(self.master, text="Browse", command=lambda: self._browse_directory(var)).grid(row=row, column=2, padx=5)

    def _browse_directory(self, var):
        current_path = var.get()
        if os.path.isdir(current_path):
            initial_dir = current_path
        else:
            initial_dir = os.getcwd()  # fallback to current dir

        selected_dir = filedialog.askdirectory(initialdir=initial_dir)
        if selected_dir:
            var.set(selected_dir)

    def _add_progress_bar(self, label, row):
        canvas = tk.Canvas(self.master, height=25, bg='white')
        canvas.grid(row=row, column=0, columnspan=3, padx=10, pady=5, sticky='we')

        # Create the rectangle and text once, keep references
        canvas.rect = canvas.create_rectangle(0, 0, 0, 25, fill='green')
        canvas.text_shadow = canvas.create_text(300 + 1, 12 + 1, text="", fill='black', font=('Arial', 10, 'bold'))
        canvas.text = canvas.create_text(300, 12, text="", fill='white', font=('Arial', 10, 'bold'))

        return canvas

    def update_file_progress(self, current, total):
        self.master.after(0, lambda: self._update_progress(self.file_progress, current, total, "files"))

    def update_recording_progress(self, current, total):
        self.master.after(0, lambda: self._update_progress(self.recording_progress, current, total, "recordings"))

    def _update_progress(self, canvas, current, total, unit_name):
        if total == 0:
            # Hide bar if nothing to do
            canvas.coords(canvas.rect, 0, 0, 0, 25)
            canvas.itemconfig(canvas.text, text="")
            return

        percent = current / total
        fill_width = int(percent * canvas.winfo_width())

        # Update bar width and text
        canvas.coords(canvas.rect, 0, 0, fill_width, 25)
        text = f"{current} / {total} ({int(percent * 100)}%) {unit_name} completed"

        canvas.itemconfig(canvas.text, text=text)
        canvas.itemconfig(canvas.text_shadow, text=text)

    def update_estimated(self, seconds):
        if seconds is None or seconds <= 0:
            self.estimated_time_label.config(text="—")
            return
        human_readable = humanize.precisedelta(seconds, minimum_unit="seconds")
        self.estimated_time_label.config(text=human_readable)
        self.master.update()  # Allow GUI update during loop

    def log(self, message):
        self.master.after(0, lambda: self._log_message(message))

    def _log_message(self, message):
        self.log_box.insert(tk.END, message + "\n")
        self.log_box.see(tk.END)

    def start_processing(self):
        input_path = self.input_dir.get()
        output_path = self.output_dir.get()

        if not input_path or not os.path.isdir(input_path):
            self.log("Please select a valid input directory.")
            return

        # Run the processing in a separate thread
        processing_thread = threading.Thread(
            target=self._process_recordings, args=(input_path, output_path), daemon=True
        )
        processing_thread.start()

    def _process_recordings(self, input_path, output_path):
        # Determine if input has subfolders (recordings)
        subdirs = [os.path.join(input_path, d) for d in os.listdir(input_path)
                   if os.path.isdir(os.path.join(input_path, d))]

        self.log("Importing libraries...")
        if subdirs:
            # Multiple recordings
            total_recordings = len(subdirs)
            self.update_recording_progress(0, total_recordings)

            for i, rec_dir in enumerate(subdirs, 1):
                convert_recording(rec_dir, op.join(output_path, rec_dir), gui=self)
                self.update_recording_progress(i, total_recordings)
        else:
            # Single recording
            self.update_recording_progress(0, 0)  # inactive
            convert_recording(input_path, output_path, gui=self)

        self.log("Processing complete!")
