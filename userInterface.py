# This code is part of the Master Thesis of Jean van der Meer presented to the Eindhoven University of Technology
import os
from PyQt5.QtWidgets import QFileDialog
from OCC.Display.SimpleGui import init_display
from OCC.Extend.DataExchange import read_step_file_with_names_colors
from OCC.Extend.DataExchange import read_step_file_with_names_colors
from OCC.Core.Graphic3d import Graphic3d_ArrayOfPoints
from OCC.Core.AIS import AIS_PointCloud
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
import ifcopenshell
import subprocess
# Initialize the display
display, start_display, add_menu, add_function_to_menu = init_display()

# Define global variables
stp_filename = ""
shapes_labels_colors = None


# Function to load and process the STEP file
def load_step_file(file_path):
    global stp_filename, shapes_labels_colors
    stp_filename = file_path
    shapes_labels_colors = read_step_file_with_names_colors(stp_filename)
    print("STEP file loaded successfully:", stp_filename)
    # Always when a new STEP file is loaded the display is cleared and updated
    update_display()

# Function to update the display with the loaded geometry
def update_display():
    global shapes_labels_colors
    display.EraseAll()
    for shape, (_, color) in shapes_labels_colors.items():
        display.DisplayColoredShape(shape, color)

# Function to convert IFC to STEP and load it for visualization of the project
def convert_ifc_to_step_and_load():
    global model
    model = None
    # Use PyQt5 to allow us to find a file with the .ifc extension anywhere in our computer
    ifc_file_path, _ = QFileDialog.getOpenFileName(None, "Open IFC File", "", "IFC files (*.ifc)")
    if ifc_file_path:
        # Open the IFC file selected with IfcOpenShell to use and edit information in it based on the IFC schema
        ifc_file = ifcopenshell.open(ifc_file_path)
        # Convert the IFC file to a STEP file for later visualization
        step_file_path = ifc_file_path.replace('.ifc', '.stp')
        # To avoid a crash that could be caused if there was already a STEP file with the same name in the folder 
        # (e.g. you are going several tests), replace it automatically
        if os.path.exists(step_file_path):
            os.remove(step_file_path)
        command = f'IfcConvert "{ifc_file_path}" "{step_file_path}"'
        # normally IfcConvert would be run on the command shell, but this can be automated using subprocess
        subprocess.run(command, shell=True)
        model = ifc_file
        # Load and visualize the converted STEP file
        load_step_file(step_file_path)
        # FitAll adjusts the zoom of the loaded geometry to fit the screen nicely
        display.FitAll()
    return model


def read_point_cloud(file_path):
    # These factors here are just used for the function that visualizes point clouds in the interface, and not in the semantic processing of point cloud
    # for building update. Because the conversion from IFC to STEP (the latter also just used for visualization) often changes the units from the IFC file,
    # making the distances much bigger in the step file, usually a order of 1E6 (1 million), here the point cloud is also scaled up by 1E6 to overlap with the 
    # BIM geometry data
    scale_factor = 1e6
    points = []
    with open(file_path, 'r') as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3:  # Ensure there are at least 3 components
                x, y, z = map(float, parts[:3])
                points.append((x * scale_factor, y * scale_factor, z * scale_factor))
    return points

# Function to display the point cloud
def display_point_cloud(points):
    # This is the function that allows the visualization of point clouds in the OpenCascade viewer
    n_points = len(points)
    points_3d = Graphic3d_ArrayOfPoints(n_points)
    for point in points:
        x, y, z = point
        points_3d.AddVertex(x, y, z)
    point_cloud = AIS_PointCloud()
    point_cloud.SetPoints(points_3d)
    #standard color for points is set to blue, other values can be obtained changing the 0.0, 0.0, 1.0 values below ( that stand for RGB values, respectively)
    blue_color = Quantity_Color(0.0, 0.0, 1.0, Quantity_TOC_RGB)
    point_cloud.SetColor(blue_color)
    point_cloud.SetWidth(5.0) # point size
    ais_context = display.GetContext()
    ais_context.Display(point_cloud, True)
    display.View_Iso()
    display.FitAll()
    print("Point cloud loaded with", len(points), "points.")

def load_point_cloud_file():
    # Initial function accessed from the menu that loads point clouds exclusivelly for visualization. First PyQt5 allows the user to find the
    # file in their computer, then the points are scaled up to overlap with the STEP geometry, and then the point cloud is visualized using the OCC
    # function above ( display_point_cloud(points) )

    file_path, _ = QFileDialog.getOpenFileName(None, "Open Point Cloud File", "", "Point Cloud Files (*.xyz *.txt)")
    if not file_path:
        return

    points = read_point_cloud(file_path)
    display_point_cloud(points)

# Function to load segmented walls
renamed_files = []
def load_segmented_walls():
    # Here point clouds where each one represents a segmented wall are loaded, with the possibility of multiple walls being loaded at once,
    # to be used in the comparison with as-designed IFC data. This point cloud data is therefore considered as ground truth and will dictate
    # whether IFC walls are deleted, or if a new IFC wall (or several ones) need to be added.
    filter = "Text Files (*.txt)"
    file_names, _ = QFileDialog.getOpenFileNames(None, "Select Segmented Walls", "", filter)
    if not file_names:
        return []
    counter = 1
    for file_name in file_names:
        # All the files are renamed as wall1, wall2, wall3, wall4 etc, sequentially, for organization reasons and as this naming convention is used internally 
        # in the code. It should be noted however, that it is ok to open walls that are already named wall1, wall2, wall3, etc, but if e.g. only wall3, wall5 
        # and wall5 etc elements are opened/loaded, and there are files named e.g. wall1 and wall2 at the same folder, the code will try to rename wall3 and wall4
        # into wall1 and wall2 and that will not work, as other files with the same name already exist in the folder, causing the interface to crash. Therefore 
        # either open all segmented walls, or keep in a different folder those that already have a name that follow the same convention but shoudln't be opened here
        new_name = f"wall{counter}.txt"
        new_file_path = os.path.join(os.path.dirname(file_name), new_name)
        os.rename(file_name, new_file_path)
        renamed_files.append(new_file_path)
        counter += 1
    print(f"Renamed {len(renamed_files)} files.")
    return renamed_files

# Function to check walls 
def check_walls_and_report():
    # Compares point cloud data from segmented walls with the walls of the as-designed IFC file, and outputs the matched and unmatched walls, 
    # producing an Excel report. A simpler version of Room Mode, where the entire IFC file is checked and liable to updates and deletions
    global model
    from wallChecker import process_seg_walls
    potet1 = process_seg_walls(renamed_files)
    from wallChecker import wallMatcher
    potet2, potet3 = wallMatcher(model = model, wall_dict = potet1)
    from wallChecker import resultsExcel
    resultsExcel(model = model, wall_dict = potet1, ifc_walls_matched = potet2, point_cloud_walls_matched = potet3)

# Function to update IFC walls 
def update_ifc_walls():
    # A simple update of the walls in the model is conducted based on the results from the check. IFC walls that were not matched to point cloud 
    # walls are deleted, and point cloud walls that were not matched to an IFC wall will generate a new IFC wall. For further explanations check
    # wallMatcher.py and wallCreaTor.py and wallDeleter.py. This produces a simpler update compared to Room Mode, Room Mode updates the geometry
    # with more adjustments and optimizations, this could be considered a sort of legacy version of Room Mode. Both here and in Room Mode the walls
    # handled are IfcWallStandardCase entities following a manhattan world assumption. Diagonal walls might make the script crash.
    global model
    from wallChecker import process_seg_walls
    potet1 = process_seg_walls(renamed_files)
    # match walls to know which ones are matched and therefore which ones should be deleted (IFC walls) or created (point cloud into ifc)
    from wallChecker import wallMatcher
    potet2, potet3 = wallMatcher(model=model, wall_dict=potet1)
    
    from wallRemover import wallDeleter
    # first delete all unmatched walls, so that new walls only get connected to validated pre existing walls
    wallDeleter(model=model, ifc_walls_matched=potet2)
    
    # Now we can create new walls based on the point cloud geometry, for walls that did not exist yet in the IFC model
    # or walls that need a corrected position
    from wallUpdaTor import wallCreaTor
    potet4 = wallCreaTor(model=model, wall_dict=potet1, ifc_walls_matched=potet2, point_cloud_walls_matched=potet3)
    
    # Update step file and give it a name with the date and time at the time of update
    from datetime import datetime
    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%d%m%y_%H%M")
    step_new_filename = f"updated_model_{formatted_datetime}.stp"
    
    command = f'IfcConvert "{potet4}" "{step_new_filename}"'
    subprocess.run(command, shell=True)
    load_step_file(step_new_filename)
    display.FitAll()

# Function to load point cloud file and generate alpha hull (the concave hull that envolves only the scanned area in Room Mode)
def load_point_cloud_fileRM():
    global alpha_hull
    # find the point cloud of the scanned area in any folder
    file_path, _ = QFileDialog.getOpenFileName(None, "Open Point Cloud File", "", "Point Cloud Files (*.xyz *.txt)")
    if not file_path:
        return
    # here in the read_point_cloud2 a scale of 10E6 (1 million up) is NOT used, unlike for visualization, because the point cloud is at the same
    # scale as the IFC file, unlike the STEP file that is being visualized
    from wallCheckerRM import read_point_cloud2
    from wallCheckerRM import compute_2d_concave_hull_and_extrude
    points = read_point_cloud2(file_path)
    display_point_cloud(points)
    # Generate the alpha hull
    alpha = 0.5 # Adjust alpha as needed it is a factor that can look for more or less concavities in the data, 0.5 works in the vast majority of cases
    alpha_hull = compute_2d_concave_hull_and_extrude(points, alpha)
    print("Alpha hull generated.")

# Function to check walls against alpha hull for Room Mode
# Here ifc walls are checked to see if they match point cloud data only within the volume/region scanned
def check_RM_walls_and_report():
    global model, alpha_hull
    if not alpha_hull:
        print("Alpha hull not generated.")
        return
    
    from wallCheckerRM import process_seg_wallsRM, wallMatcherRM, extrPoints, is_within_alpha_hull
    point_cloud_walls = process_seg_wallsRM(renamed_files)
    # This time, the alpha hull is also used as a an argument for the function, as the check of walls is only done in the region comprised by the alpha hull
    # furthermore, a buffer size is added, that creates a tolerance around the scanned region to accept a possible wall start or end that was just outside the scanned area
    ifc_walls_matched, point_cloud_walls_matched, ifc_walls_to_delete = wallMatcherRM(model, point_cloud_walls, alpha_hull, buffer_size=0.70)
    
    from wallCheckerRM import resultsExcel
    # Here an excel report is made of the walls that had to be deleted, had to be created, and the walls that were kept/matched
    resultsExcel(model = model, wall_dict = point_cloud_walls, ifc_walls_matched = ifc_walls_matched, point_cloud_walls_matched = point_cloud_walls_matched, alpha_hull = alpha_hull)
    print("IFC walls to delete:", ifc_walls_to_delete)

# Function to update IFC walls based on alpha hull for Room Mode
# Based on the check to see which IFC walls are inside the alpha hull, those walls are checked against point cloud data and liable to being matched or deleted
# If necessary, new IFC walls are created based on point cloud data, and they are enrichted with semantics from the model based on several heuristic principles
# This check and update of geometry at this Room Mode version is much more complex than the other one and handles many more exceptions and optimizations
def update_RM_ifc_walls():
    global model, alpha_hull
    from wallCheckerRM import process_seg_wallsRM
    point_cloud_walls = process_seg_wallsRM(renamed_files)
    from wallCheckerRM import wallMatcherRM
    ifc_walls_matched, point_cloud_walls_matched, ifc_walls_to_delete = wallMatcherRM(model, point_cloud_walls, alpha_hull, buffer_size=0.70)
    # The wallMatcherRM function is a bit different from the older wallMatcher function, and here it also produces an "ifc_walls_to_delete" list, 
    # which makes that the wallDeleter function also works a bit differently and does not parse walls from the entire project but just the preselected ones
    from wallRemoverRM import wallDeleterRM
    wallDeleterRM(model=model, ifc_walls_to_delete = ifc_walls_to_delete)
    from wallUpdaTor import wallCreaTor
    potet4 = wallCreaTor(model=model, wall_dict=point_cloud_walls, ifc_walls_matched=ifc_walls_matched, point_cloud_walls_matched=point_cloud_walls_matched)
    from datetime import datetime
    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%d%m%y_%H%M")
    step_new_filename = f"updated_model_{formatted_datetime}.stp"
    command = f'IfcConvert "{potet4}" "{step_new_filename}"'
    subprocess.run(command, shell=True)
    load_step_file(step_new_filename)
    display.FitAll()    


# Here the ceiling block starts, and similarly as with walls several segmented ceiling files, in the form of point clouds, can be loaded at once,
# and each file of a ceiling is renamed as ceiling1, ceiling2, ceiling3, etc.
renamed_ceilings = []
def load_segmented_ceilings():
    filter = "Text Files (*.txt)"
    file_names, _ = QFileDialog.getOpenFileNames(None, "Select Segmented Ceilings", "", filter)
    if not file_names:
        return []
    counter = 1
    for file_name in file_names:
        new_name = f"ceiling{counter}.txt"
        new_file_path = os.path.join(os.path.dirname(file_name), new_name)
        os.rename(file_name, new_file_path)
        renamed_ceilings.append(new_file_path)
        counter += 1
    print(f"Renamed {len(renamed_ceilings)} files.")
    return renamed_ceilings


def check_ceilings_and_update():
    global model
    from ceilingUpdaTor import check_and_update_ceilings, process_seg_ceilings
    # first the segmented ceilings are parsed to extract relevant geometrical information about them and make a dictionary with each ceiling as an item and 
    # relevant data attached to that ceiling also in the dictionary
    pc_ceilings = process_seg_ceilings(renamed_ceilings)
    # then the matching and update of ceiling heights is done based on the geometry extracted from the point clouds, for more information check ceilingUpdaTor.py
    new_model2 = check_and_update_ceilings(model=model, pc_ceilings=pc_ceilings)
    from datetime import datetime
    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%d%m%y_%H%M")
    step_new_filename2 = f'updated_model_{formatted_datetime}.stp'
    command = f'IfcConvert "{new_model2}" "{step_new_filename2}"'
    subprocess.run(command, shell=True)
    load_step_file(step_new_filename2)
    display.FitAll()


# Here the column block starts, and similarly as with walls, several segmented column files, in the form of point clouds, can be loaded at once,
# and each file of a column is renamed as column1, column2, column3, etc
renamed_columns = []
def load_segmented_columns():
    filter = "Text Files (*.txt)"
    file_names, _ = QFileDialog.getOpenFileNames(None, "Select Segmented Columns", "", filter)
    if not file_names:
        return []
    counter = 1
    for file_name in file_names:
        new_name = f"column{counter}.txt"
        new_file_path = os.path.join(os.path.dirname(file_name), new_name)
        os.rename(file_name, new_file_path)
        renamed_columns.append(new_file_path)
        counter += 1
    print(f"Renamed {len(renamed_columns)} files.")
    return renamed_columns


# This function deals with the check and update of columns. Columns are a tricky building element because columns might be embedded in a wall,
# and because current laser scanning techniques see about as much as we can see, i.e. visible building elements, elements encased in walls or other such
# spaces are not found in scanned data. To take that into account, the check is done in several stages, first seeing if there are columns in the point 
# cloud data that can be matched to encased columns in the as-designed project, but opting to not change the as-designed data of columns encased in walls
# anyways, but having an idea of how many columns are encased in the ifc project, and how many were found at the point cloud side, and also how many columns
# are found in the ifc project and how many columns are found in the point cloud that are reasonably distant from walls, and focusing on that last part,
# perform an update on the position and possibly the quantity of columns that are not embedded in walls. Because columns are important for the stability
# of a building, a series of reports and warnings are made in the form of pop-up messages, if for instance less columns are found in the real building,
# comparing it to the as-designed project. Depending on the case, the user is advised to look at the superimposion of point cloud and IFC geometry and
# possibly do a manual intervention, apart from the automated update
def check_columns_and_update():
    from PyQt5.QtWidgets import QMessageBox, QFileDialog
    global model
    from columnUpdaTor import check_and_update_columns, process_seg_columns
    
    # Process the segmented columns
    pc_columns = process_seg_columns(renamed_columns)
    
    # Perform the column check, update and get the results and warnings
    update_results = check_and_update_columns(model=model, pc_columns=pc_columns)
    
    # Extract results from the dictionary returned by check_and_update_columns
    new_filename = update_results['new_filename']
    num_ifc_emb_columns_no_match = update_results['num_ifc_emb_columns_no_match']
    message2 = update_results['message']
    num_unmatched_free_columns = update_results['num_unmatched_free_ifc_columns']
    
    # Convert the updated IFC file to STEP format
    from datetime import datetime
    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%d%m%y_%H%M")
    step_new_filename3 = f'updated_model_{formatted_datetime}.stp'
    command = f'IfcConvert "{new_filename}" "{step_new_filename3}"'
    subprocess.run(command, shell=True)
    
    # Load the new STEP file into the viewer
    load_step_file(step_new_filename3)
    display.FitAll()

    # Display a message box with the results
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("Column Update Results")
    msg.setText("The column update process has been completed.")
    msg.setInformativeText(
        f"Updated IFC File: {new_filename}\n"
        f"IFC Columns embedded in walls that were not matched to point cloud data: {num_ifc_emb_columns_no_match}\n"
        f"{message2}\n"
        f"IFC Columns (Not Embedded in Walls) that were not matched to point cloud data: {num_unmatched_free_columns}"
    )
    msg.setStandardButtons(QMessageBox.Ok)
    msg.exec_()




if __name__ == "__main__":
    # Show initial instructions pop-up message before starting the display, otherwise it only shows when you close the display window
    from PyQt5.QtWidgets import QMessageBox, QFileDialog
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("Instructions")
    msg.setText("Instructions:")
    msg.setInformativeText(
        "* As the first step, always open the IFC file at the first menu.\n"
        "* Depending on what you want to update, choose a menu and follow all the steps of the submenus in the order they are presented at the menu.\n"
        "* The menu 'Point Cloud' serves for visualization of point clouds; they are not loaded to perform operations and changes in this menu. You can open as many point clouds at the same time as you wish here."
    )
    msg.setStandardButtons(QMessageBox.Ok)
    msg.exec_()

    # Add menus and functions as submenus
    add_menu('Open IFC and make STEP')
    add_function_to_menu('Open IFC and make STEP', convert_ifc_to_step_and_load)
    add_menu('Point Cloud')
    add_function_to_menu('Point Cloud', load_point_cloud_file)
    add_menu('Walls')
    add_function_to_menu('Walls', load_segmented_walls)
    add_function_to_menu('Walls', check_walls_and_report)
    add_function_to_menu('Walls', update_ifc_walls)
    add_menu('Room Mode Walls')
    add_function_to_menu('Room Mode Walls', load_point_cloud_fileRM)
    add_function_to_menu('Room Mode Walls', load_segmented_walls)
    add_function_to_menu('Room Mode Walls', check_RM_walls_and_report)
    add_function_to_menu('Room Mode Walls', update_RM_ifc_walls)
    add_menu('Columns')
    add_function_to_menu('Columns', load_segmented_columns)
    add_function_to_menu('Columns', check_columns_and_update)
    add_menu('Ceilings')
    add_function_to_menu('Ceilings', load_segmented_ceilings)
    add_function_to_menu('Ceilings', check_ceilings_and_update)

    start_display()
