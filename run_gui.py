import os
import tkinter as tk
from gui import SimpleConverterGUI


# Run the GUI
if __name__ == "__main__":
    print("Importing libraries and starting the GUI...")
    root = tk.Tk()
    app = SimpleConverterGUI(root)
    root.mainloop()
