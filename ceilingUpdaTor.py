# This code is part of the Master Thesis of Jean van der Meer presented to the Eindhoven University of Technology


import numpy as np
import pandas as pd
import os
import ifcopenshell

# Function to process segmented ceilings from point cloud data and extract the necessary geometry data
def process_seg_ceilings(files2):
    # the input of the function are the several point cloud files, each one with one segmented ceiling
    data_dict = {}
    ceiling_dict = {}

    for file in files2:
        data_dict[file] = pd.read_csv(file, sep=' ', header=None, names=['X', 'Y', 'Z', 'R', 'G', 'B'])
    
    for file, data in data_dict.items():
        # each line is divided into x, y and z values, so each one is stored in this initial data_dict for each ceiling
        x = data['X'].values
        y = data['Y'].values
        z = data['Z'].values

        z_avg = np.mean(z)  # Compute the average Z value (height), used to find the cg and other geometry information

        # Compute center of gravity of X and Y coordinates
        x_cg = np.mean(x)
        y_cg = np.mean(y)
        cg = (x_cg, y_cg, z_avg)

        # Compute 8 additional points around the center of gravity, they plus the cg are used to check if the central area of a
        # point cloud ceiling can be matched to the area of one of the ifc ceilings, if a majority of those points are within the area of an ifc ceiling
        # The aditional points are basically a square around the cg, or an 8-pointed star inscribed in a square
        offset = 0.6
        additional_points = [
            (x_cg + offset, y_cg, z_avg),
            (x_cg - offset, y_cg, z_avg),
            (x_cg, y_cg + offset, z_avg),
            (x_cg, y_cg - offset, z_avg),
            (x_cg + offset, y_cg + offset, z_avg),
            (x_cg - offset, y_cg + offset, z_avg),
            (x_cg - offset, y_cg - offset, z_avg),
            (x_cg + offset, y_cg - offset, z_avg)
        ]

        nine_points = [cg] + additional_points

        # Store the data in ceiling_dict and change the name of each ceiling in the dictionary from e.g. ceiling1.txt, ceiling2.txt into just celing1, ceiling2
        ceiling_name = os.path.splitext(os.path.basename(file))[0]
        ceiling_dict[ceiling_name] = {
            'z_avg': z_avg,
            'nine_points': nine_points
        }

    return ceiling_dict

# Function to check and update ceilings in the IFC model
def check_and_update_ceilings(model, pc_ceilings):
    for pc_name, pc_data in pc_ceilings.items():
        z_avg = pc_data['z_avg']
        nine_points = pc_data['nine_points']
        
        # Ceilings usually have their geometry represented either as a rectangle, for perfectly rectangular rooms, or as an IfcArbitraryClosedProfileDef, for 
        # rooms with a more complex layout. A rectangular room is represented by a rectangle oriented around a center point, that might also have local coordinates
        # that need to be translated into the coordinates of the rest of the model by a reference direction. Usually IFC (or IFC authoring tools) considers the 
        # larger side of an element as its internal main axis, the x axis, but if in the global coordinates the element has its shortest dimension on the x axis,
        # it will probably have a reference direction of either (0.0, 1.0, 0.0) or (0.0, -1.0, 0.0) to bring its "wide local x axis" into the global y axis.
        # Ceilings represented by an IfcArbitraryClosedProfileDef can also have reference axis and follow a similar idea. Ceilings represented by a 
        # IfcArbitraryClosedProfileDef have a location given in global coordinates (except for the z coordinate that is relative to the floor), and then they
        # have a polyline that represents the outline of the ceiling in local coordinates, that is, each point has x,y coordinates that represent its distance
        # in the internal x and y axis to the location point of the ceiling. Those coordinates might have to be transformed, with internal 
        # x and y values being added or removed from the location coordinate of the ceiling, to then find the global coordinates of the polyline points, as
        # will be shown later in the code
        for ceiling in model.by_type('IfcCovering'):
            if ceiling.Representation.Representations[0].Items[0].SweptArea.is_a('IfcRectangleProfileDef'):
                # Handle IfcRectangleProfileDef, here x_dim and y_dim are the internal coordinate dimensions of the rectangle profile
                x_dim = ceiling.Representation.Representations[0].Items[0].SweptArea.XDim
                y_dim = ceiling.Representation.Representations[0].Items[0].SweptArea.YDim
                # here are the coordinates of the point that locates semi-globally (except for z) the ceiling
                base_x = ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates[0]
                base_y = ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates[1]
                # here is the height of the floor the ceiling is located, the global height of the ceiling is that of the floor (floor_z) plus ceiling_z
                floor_z = ceiling.ObjectPlacement.PlacementRelTo.RelativePlacement.Location.Coordinates[2]
                ceiling_z = ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates[2]
                ref_direction = ceiling.Representation.Representations[0].Items[0].Position.RefDirection

                if ref_direction: #ceilings aligned the global coordinates, usually ceilings whose larger dimension is in the x axis, have no specific RefDirection
                    direction_ratios = ref_direction.DirectionRatios
                    if direction_ratios == (0.0, 1.0, 0.0) or direction_ratios == (0.0, -1.0, 0.0):
                        # as explained previously, if the internal coordinates are orthogonal to the global coordinates we invert x and y dimensions
                        x_dim, y_dim = y_dim, x_dim

                # Compute the bounds of the ifc ceiling volume
                x_min = base_x - x_dim / 2
                x_max = base_x + x_dim / 2
                y_min = base_y - y_dim / 2
                y_max = base_y + y_dim / 2
                z_min = floor_z + ceiling_z - 0.5 # a threshold is used (here 0.5m) to look for a match with ceilings globally 0.5 meters above or 0.5 meters below the ifc ceiling
                z_max = floor_z + ceiling_z + 0.5

                # Check if at least 6 of the 9 points are within the volume
                match_count = sum(1 for point in nine_points if x_min <= point[0] <= x_max and y_min <= point[1] <= y_max and z_min <= point[2] <= z_max)

                if match_count >= 6:
                    new_ceiling_z = z_avg - floor_z # setting the height of the IFC ceiling to that of the matched point cloud ceiling, and converting the global height to local height
                    ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates = (float(ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates[0]), float(ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates[1]), float(new_ceiling_z))
                    # ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates[2] = new_ceiling_z' -> this does not work, an entire tuple of coordinates needs to be assigned
                    print('rectangular celiling updated')


            # now is the script for when a ceiling is defined by a polyline
            elif ceiling.Representation.Representations[0].Items[0].SweptArea.is_a('IfcArbitraryClosedProfileDef'):
                
                floor_z = ceiling.ObjectPlacement.PlacementRelTo.RelativePlacement.Location.Coordinates[2]
                ceiling_z = ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates[2]
                z_min = floor_z + ceiling_z - 0.5
                z_max = floor_z + ceiling_z + 0.5

                base_point = ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates
                ref_direction = ceiling.Representation.Representations[0].Items[0].Position.RefDirection

                # here is where the points that outline the polyline are given
                points = ceiling.Representation.Representations[0].Items[0].SweptArea.OuterCurve.Points
                polygon_points = []

                # here the points given in internal coordinates are translated to global coordinates if the reference direction is orthogonal to the global axes
                if ref_direction is None or ref_direction.DirectionRatios != (0.0, 1.0, 0.0):
                    # No RefDirection or different direction ratios; use base point directly, x is added to x, y to y
                    polygon_points = [(base_point[0] + p.Coordinates[0], base_point[1] + p.Coordinates[1]) for p in points]
                else:
                    # RefDirection with DirectionRatios (0.0, 1.0, 0.0); transform coordinates, because of the rotarion direction from (1.0, 0.0, 0.0) to (0.0, 1.0, 0.0)
                    # the y local distances are reduced from the x global distances, and the x local distances are added to the y global distances
                    polygon_points = [(base_point[0] - p.Coordinates[1], base_point[1] + p.Coordinates[0]) for p in points]

                from shapely.geometry import Polygon, Point
                # a 3d polygon is made to see if the 9 points extracted from a point cloud ceiling fit within the projection of the IFC ceiling
                polygon = Polygon(polygon_points)

                # Check if at least 6 of the 9 points are within the volume
                match_count = sum(1 for point in nine_points if polygon.contains(Point(point[:2])) and z_min <= point[2] <= z_max)

                if match_count >= 6:
                    new_ceiling_z = z_avg - floor_z
                                                    
                    ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates = (float(ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates[0]), float(ceiling.Representation.Representations[0].Items[0].Position.Location.Coordinates[1]), float(new_ceiling_z))
                    
                    print('polygonal ceiling updated')
    # Save the modified IFC file with the date and time of the changes
    from datetime import datetime

    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%d%m%y_%H%M")
    new_filename = f"modified_ifc_file_{formatted_datetime}.ifc"
    model.write(new_filename)

    return new_filename
