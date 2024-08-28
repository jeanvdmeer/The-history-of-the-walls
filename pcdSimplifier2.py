# This code is part of the Master Thesis of Jean van der Meer presented to the Eindhoven University of Technology
# simple file to update one or several point cloud files at once, some of them might have to many fields of data that either 
# make the files too heavy or might cause the code to malfunction, so this code only keeps the first three values of the point data,
# that is, the x, y and z values, that are the ones used by the tool

# the code is made for point cloud files in ASCII characters with values separated by spaces where each line represents a point

import tkinter as tk
from tkinter import filedialog

def process_file(file_path):
    with open(file_path, 'r') as file:
        lines = file.readlines()
    
    processed_lines = []
    for line in lines:
        values = line.strip().split()
        if len(values) >= 3:
            processed_lines.append(' '.join(values[:3]))
    
    with open(file_path, 'w') as file:
        file.write('\n'.join(processed_lines))

def open_files_dialog():
    root = tk.Tk()
    root.withdraw()  # Hide the root window
    file_paths = filedialog.askopenfilenames(
        title="Select Text Files",
        filetypes=(("Text Files", "*.txt"), ("All Files", "*.*"))
    )
    if file_paths:
        for file_path in file_paths:
            process_file(file_path)
            print(f"Processed the file: {file_path}")

if __name__ == "__main__":
    open_files_dialog()
