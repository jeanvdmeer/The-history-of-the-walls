# This code is part of the Master Thesis of Jean van der Meer presented to the Eindhoven University of Technology
import ifcopenshell
import numpy as np
import pandas as pd
import os

def process_seg_columns(files2):
    # the segmented point clouds of columns are loaded and geometric information is extracted from them, assuming a manhattan world scenario with orthogonal planes
    column_dict = {}

    for file in files2:
        # Load the point cloud data
        data = pd.read_csv(file, sep=' ', header=None, names=['X', 'Y', 'Z', 'R', 'G', 'B'])

        # Extract X, Y, Z coordinates
        x = data['X'].values
        y = data['Y'].values
        z = data['Z'].values

        # Compute min and max values for X, Y, and Z
        x_min = np.min(x)
        x_max = np.max(x)
        y_min = np.min(y)
        y_max = np.max(y)
        z_min = np.min(z)
        z_max = np.max(z)

        # Define the four points, the four vertices of a square column, e.g. xlyh: x lowest point, y highest point, xhyh: x highest point, y highest point etc
        xlyh = (x_min, y_max, z_min)
        xhyh = (x_max, y_max, z_min)
        xlyl = (x_min, y_min, z_min)
        xhyl = (x_max, y_min, z_min)

        # Calculate center of gravity (cg)
        cg_x = (x_max + x_min) / 2
        cg_y = (y_max + y_min) / 2
        cg = (cg_x, cg_y, z_min) #the base point is considered as the base of the column from which it is "extruded", thus z_min

        # Calculate column height
        column_height = z_max - z_min

        # Calculate profile base and height
        # However the code is not developed here, the profile base and profile height can be easily used to compare the profiles of columns being checked,
        # and if the column in IFC has dimensions closer to a different profile found at the model, the column type can be updated, by finding which
        # column type has the closest profile to that of the point cloud column
        profile_base = x_max - x_min
        profile_height = y_max - y_min

        # Snippet to remove the file extension
        column_name = os.path.splitext(os.path.basename(file))[0]

        # Store the data in the column dictionary
        column_dict[column_name] = {
            'xlyh': xlyh,
            'xhyh': xhyh,
            'xlyl': xlyl,
            'xhyl': xhyl,
            'cg': cg,
            'column_height': column_height,
            'profile_base': profile_base,
            'profile_height': profile_height
        }

    return column_dict



import ifcopenshell
from datetime import datetime
# This function also used in several operations, with walls, finds the global start and end point of a wall in a standardized manner. 
# It is used here to help locate the space a wall occupies and areas very close to it, to identify columns that could be hidden inside walls
def extrPoints(wall):
    local_placement = wall.ObjectPlacement
    if local_placement:
        location = local_placement.RelativePlacement.Location.Coordinates
        
        # this segment is not relevant here but works regardless, sometimes the z can be extracted from location[2] when a new wall is still being generated from point cloud data
        if wall.ContainedInStructure[0].RelatingStructure.Elevation:
            z_coord = wall.ContainedInStructure[0].RelatingStructure.Elevation
        else:
            z_coord = location[2]
        
        # Get the length of the wall, to help to find its end point that is normally only implicit in IFC
        lengthW = wall.Representation.Representations[0].Items[0].Points[1].Coordinates[0]
        
        # Determine the end coordinate based on direction
        if local_placement.RelativePlacement.RefDirection is not None:
            axis2 = local_placement.RelativePlacement.RefDirection.DirectionRatios
            axis1 = local_placement.RelativePlacement.Axis.DirectionRatios

            if axis1 == (0, 0, 1) and axis2 == (-1, 0, 0):
                end_coordinate = ((location[0] - lengthW), location[1], location[2])
            elif axis1 == (0, 0, 1) and axis2 == (0, 1, 0):
                end_coordinate = (location[0], (location[1] + lengthW), location[2])
            elif axis1 == (0, 0, 1) and axis2 == (0, -1, 0):
                end_coordinate = (location[0], (location[1] - lengthW), location[2])
        else:
            end_coordinate = (location[0] + lengthW, location[1], location[2])

        return (location[0], location[1], z_coord), (end_coordinate[0], end_coordinate[1], z_coord)
    
    return None

def check_and_update_columns(model, pc_columns):
    import ifcopenshell.api
    ifc_columns_close_to_walls = []
    ifc_columns_not_close_to_walls = []
    # here "emb" means embedded, do columns that are found inside a wall in the ifc model or in the point cloud data, whose detection might be hindered
    ifc_emb_columns_no_match = []
    matched_emb_pc_columns = []
    
    walls = model.by_type('IfcWallStandardCase')
    columns = model.by_type('IfcColumn')
    
    for column in columns: 
        # Some columns depending on how they are modeled have their location at column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates
        # instead of at column.ObjectPlacement.RelativePlacement.Location.Coordinates, where it usually is, so we need to check for both cases
        # When the column's location is at column.ObjectPlacement.RelativePlacement.Location.Coordinates, the other location, column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates
        # is always set as (0.0, 0.0, 0.0), so we can use that as a test to know where the location is stored. The other scenario, where the location is stored at
        # the mapping source usually happens when every column in the file, or many of them, have their own column type and all geometric infornmation is then
        # stored at the column type instead of the column instance, even when many columns have the same profile. This can happen depending on how columns are 
        # modeled in a BIM authoring tool
        if column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates == (0.0, 0.0, 0.0):
            column_position = column.ObjectPlacement.RelativePlacement.Location.Coordinates
            column_x, column_y, column_z = column_position
        else:
            column_position = column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates
            column_x, column_y, column_z = column_position

        column_is_close_to_any_wall = False  # Flag to track if the column is close to any wall, all ifc columns are checked for all point cloud columns, and if they are once close to a wall they are labeled as so, to make sure there are no duplicates

        for wall in walls:
            start_point, end_point = extrPoints(wall)
            if not start_point or not end_point:
                continue
            
            # Determine if the wall is horizontal or vertical
            local_placement = wall.ObjectPlacement
            if local_placement.RelativePlacement.RefDirection is None or (local_placement.RelativePlacement.Axis.DirectionRatios == (0, 0, 1) and local_placement.RelativePlacement.RefDirection.DirectionRatios == (-1, 0, 0)):
                is_horizontal = True
            elif (local_placement.RelativePlacement.Axis.DirectionRatios == (0, 0, 1) and local_placement.RelativePlacement.RefDirection.DirectionRatios in [(0, 1, 0), (0, -1, 0)]):
                is_vertical = True
            else:
                is_horizontal = False
                is_vertical = False

            if is_horizontal:
                # Check if the column is within the range of a horizontal wall
                y_min, y_max = sorted([start_point[1], end_point[1]])  # y min and y max are the same y coordinate in a horizontal wall
                x_min, x_max = sorted([start_point[0], end_point[0]])
                
                # some thresholds are used for the y value (that remains the same in vertical walls) and the x values that the center of a column can be to be considered embedded in that wall
                # some tolerance is also given for the z value of the based of the wall and column
                if y_min - 0.35 <= column_y <= y_max + 0.35 and x_min - 0.35 <= column_x <= x_max + 0.35 and abs(column_z - start_point[2]) <= 0.25:
                    column_is_close_to_any_wall = True
                    break  # No need to check further walls if a match is found

            elif is_vertical:
                # Check if the column is within the range of a vertical wall
                x_min, x_max = sorted([start_point[0], end_point[0]]) # x min and x max are the same y coordinate in a horizontal wall
                y_min, y_max = sorted([start_point[1], end_point[1]])

                # some thresholds are used for the x value (that remains the same in horizontal walls) and the y values that the center of a column can be to be considered embedded in that wall
                # some tolerance is also given for the z value of the based of the wall and column                
                if x_min - 0.35 <= column_x <= x_max + 0.35 and y_min - 0.35 <= column_y <= y_max + 0.35 and abs(column_z - start_point[2]) <= 0.25:
                    column_is_close_to_any_wall = True
                    break  # No need to check further walls if a match is found

        if column_is_close_to_any_wall:
            ifc_columns_close_to_walls.append(column)
        else:
            ifc_columns_not_close_to_walls.append(column)
    
    # Matching (or try to) IFC columns close to walls with point cloud columns
    # create a copy of point cloud columns to then remove all columns that are close to a wall and matched to an embedded IFC column, to know how many point cloud columns are left
    remaining_pc_columns = pc_columns.copy()
    
    for ifc_column in ifc_columns_close_to_walls:
        if ifc_column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates == (0.0, 0.0, 0.0):
            column_position = ifc_column.ObjectPlacement.RelativePlacement.Location.Coordinates
            column_x, column_y, column_z = column_position
        else:
            column_position = ifc_column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates
            column_x, column_y, column_z = column_position
        # find the elevation of the floor an IFC column is located, to help comparing the local z value of the IFC column to the global z value of the point cloud column
        elevation = ifc_column.ContainedInStructure[0].RelatingStructure.Elevation

        matched = False
        for pc_column_name, pc_column_data in list(remaining_pc_columns.items()):
            cg_x, cg_y, cg_z = pc_column_data['cg']
            # the elevation of the floor an IFC column is in is reduced from the elevation of the point cloud column it is being compared to, to see if their position is comparable
            cg_z_transformed = cg_z - elevation
            
            distance = np.sqrt((column_x - cg_x)**2 + (column_y - cg_y)**2 + (column_z - cg_z_transformed)**2)
            # Threshold for embedded ifc-pcd column matching
            if distance <= 1.1:
                matched_emb_pc_columns.append(pc_column_name)
                remaining_pc_columns.pop(pc_column_name)
                matched = True
                print(f'Column {pc_column_name} got matched to an IFC column embedded in a wall!')
                break
        
        if not matched:
            ifc_emb_columns_no_match.append(ifc_column.GlobalId)
    
    num_ifc_emb_columns_no_match = len(ifc_emb_columns_no_match)
    if num_ifc_emb_columns_no_match > 0:
        print(f'There are {num_ifc_emb_columns_no_match} IFC columns embedded in walls that could not be checked against point cloud data.')
    
    num_pc_columns_remaining = len(remaining_pc_columns) # point cloud columns that are not close to a wall, or at least not matched to ifc columns embedded in walls
    num_ifc_columns_not_close = len(ifc_columns_not_close_to_walls)
    message2 = ''
    if num_pc_columns_remaining < num_ifc_columns_not_close:
        print(f'There were {num_pc_columns_remaining} columns found in the point cloud data away from walls, while the IFC as-designed file had more columns ({num_ifc_columns_not_close} IFC columns not embedded in walls).')
        message2 = f'There were {num_pc_columns_remaining} columns found in the point cloud data away from walls, while the IFC as-designed file had more columns ({num_ifc_columns_not_close} IFC columns not embedded in walls). This means the designed project had more columns not embedded in walls, so you are advised to check the point cloud and see if the threshold should be adapted or a manual intervention is needed'
         



    # Last step: Match remaining point cloud columns with IFC columns not close to walls
    matched_ifc_columns = []
    unmatched_ifc_columns = ifc_columns_not_close_to_walls.copy()

    for pc_column_name, pc_column_data in list(remaining_pc_columns.items()):
        cg_x, cg_y, cg_z = pc_column_data['cg']
        matched = False
        
        for ifc_column in ifc_columns_not_close_to_walls:
            # here again, both positions where the location of a column might be, depending on whether it is defined by the column type/mappingSource or 
            # column instance, have to be handled accordingly
            if ifc_column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates == (0.0, 0.0, 0.0):
                column_position = ifc_column.ObjectPlacement.RelativePlacement.Location.Coordinates
                column_x, column_y, column_z = column_position
            else:
                column_position = ifc_column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates
                column_x, column_y, column_z = column_position
            elevation = ifc_column.ContainedInStructure[0].RelatingStructure.Elevation
            
            cg_z_transformed = cg_z - elevation
            
            distance = np.sqrt((column_x - cg_x)**2 + (column_y - cg_y)**2 + (column_z - cg_z_transformed)**2)
            
            ############################
            ######## THRESHOLD: ########
            ############################
            if distance <= 1.2:
                # Update matched IFC column position with point cloud data
                # Here again, depending on where that column was keeping its location we need to add the new location to that place too, as other data pertaining
                # the geometrical representation of the column are also in that "location" (either the ObjectPlacement or the MappingSource via a column type).
                # Furthermore, because new columns that need to be created are copied based on existing column types at the model and have their new location
                # assigned afterwards, the assignment of that location also needs to respect how their reference column structured its geometry
                if ifc_column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates != (0.0, 0.0, 0.0):
                    ifc_column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates = (float(cg_x), float(cg_y), float(column_z))
                else:
                    ifc_column.ObjectPlacement.RelativePlacement.Location.Coordinates = (float(cg_x), float(cg_y), float(column_z))
                matched_ifc_columns.append(ifc_column)
                unmatched_ifc_columns.remove(ifc_column)
                remaining_pc_columns.pop(pc_column_name)
                matched = True
                print(f'Column {pc_column_name} got matched to an IFC column not embedded in a wall!')
                break

        if not matched:
            # If no match, create a new column in IFC, as mentioned above, the new column will receive its locating point following the schema of the model column it copies semantics from,
            # i.e., either ObjectPlacement or MappingSource of the representation. The elevation of the floor is reduced from the global z value of the point cloud, to give the new column a 
            # proper local position relative to the floor it is in
            possible_columns = [col for col in ifc_columns_not_close_to_walls if abs(col.ContainedInStructure[0].RelatingStructure.Elevation - cg_z) <= 0.4]
            if possible_columns:
                existing_column = possible_columns[0]
                new_column = ifcopenshell.util.element.copy_deep(model, existing_column, exclude=None)
                if new_column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates != (0.0, 0.0, 0.0):
                    new_column.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0].Position.Location.Coordinates = (float(cg_x), float(cg_y), float(cg_z - existing_column.ContainedInStructure[0].RelatingStructure.Elevation))
                else:
                    new_column.ObjectPlacement.RelativePlacement.Location.Coordinates = (float(cg_x), float(cg_y), float(cg_z - existing_column.ContainedInStructure[0].RelatingStructure.Elevation))
                print(f'New IFC column created for unmatched point cloud column {pc_column_name}.')
    num_unmatched_free_columns = len(unmatched_ifc_columns)
    # Remove unmatched IFC columns
    for column_not_matched in unmatched_ifc_columns:
        colGuid = column_not_matched.GlobalId
        ifcopenshell.api.run("root.remove_product", model, product=column_not_matched)
        print(f'IFC column {colGuid} removed as it was not matched to any point cloud column.')

    # Save the modified IFC file
    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%d%m%y_%H%M")
    new_filename = f"modified_ifc_file_{formatted_datetime}.ifc"
    model.write(new_filename)

    return {
        'new_filename': new_filename,
        'ifc_emb_columns_no_match': ifc_emb_columns_no_match,
        'num_ifc_emb_columns_no_match': num_ifc_emb_columns_no_match,
        'message' : message2,
        'num_unmatched_free_ifc_columns': num_unmatched_free_columns
    }

