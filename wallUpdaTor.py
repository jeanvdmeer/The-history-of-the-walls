# This code is part of the Master Thesis of Jean van der Meer presented to the Eindhoven University of Technology
import uuid
from datetime import datetime
import numpy as np
import ifcopenshell.util.element




def wallCreaTor(model, wall_dict, ifc_walls_matched, point_cloud_walls_matched):
    import math
    from wallCheckerRM import extrPoints
    import ifcopenshell
    import time
    import datetime
    # create datetime data to use in the owner history of the changed items, to signal when they were edited/created
    dt = datetime.datetime.now()
    dti = int(dt.strftime('%Y%m%d'))

    # Create a new IfcOwnerHistory for new elements to be added to the model
    owner_history = model.create_entity('IfcOwnerHistory')
    owner_history.OwningUser = model.create_entity('IfcPersonAndOrganization')
    owner_history.OwningUser.ThePerson = model.create_entity('IfcPerson')
    owner_history.OwningUser.TheOrganization = model.create_entity('IfcOrganization')
    owner_history.OwningApplication = model.create_entity('IfcApplication')
    owner_history.State = 'READWRITE'
    # point out that building elements with this owner history were modified
    owner_history.ChangeAction = 'MODIFIED'
    owner_history.LastModifiedDate = int(dti)
    owner_history.LastModifyingUser = owner_history.OwningUser
    owner_history.LastModifyingApplication = owner_history.OwningApplication
    owner_history.LastModifyingApplication.ApplicationFullName = 'Python Scan to Ifc Updater'
    owner_history.CreationDate = int(dti)

    # Create list for the new walls that will be added into the model, to keep track of which walls in the
    # model were pre-existing and which ones are new
    new_walls = []

    # Iterate over point cloud walls
    for wall_name, wall_properties in wall_dict.items():
        # Skip if the wall was matched with a as-designed IFC wall
        if wall_name in point_cloud_walls_matched:
            continue
        # Define functions that will help testing the most appropriate wall in the model to use as template.
        # The idea is finding a wall of similar thickness nearby, and if that is not available, look for a wall
        # of similar thickness in the entire model
        def create_bounding_box(center, x_range, y_range, z_range):
            """Create a bounding box around a center point with given ranges. This can be used to look for IFC
            walls of similar thickness, so a similar walltype, close to the place where an IFC wall should be created
            on data of a point cloud wall"""
            return {
                'xmin': center[0] - x_range,
                'xmax': center[0] + x_range,
                'ymin': center[1] - y_range,
                'ymax': center[1] + y_range,
                'zmin': center[2] - z_range,
                'zmax': center[2] + z_range
            }
            
        def is_within_bounding_box(point, box):
            """Check if a point is within the bounding box."""
            return (box['xmin'] <= point[0] <= box['xmax'] and
                    box['ymin'] <= point[1] <= box['ymax'] and
                    box['zmin'] <= point[2] <= box['zmax'])
                            
        # here a bounding box of 4 x 4 x 0,6 m is created around start and end of the point cloud wall, to look for walls
        # around it and find the one with the closest thickness to the point cloud wall    
        base_box = create_bounding_box(wall_properties['base point'], 2, 2, 0.3)
        end_box = create_bounding_box(wall_properties['end point'], 2, 2, 0.3)
        
        candidate_walls = []

        for ifc_wall in model.by_type('IfcWallStandardCase'):
            # We want to check whether the wall that might be used as a template to create a new wall is represented by a rectangular profile,
            # as this is the type of wall that we will create
            if ifc_wall.Representation.Representations[1].Items[0].SweptArea.is_a('IfcRectangleProfileDef'):
                ifc_wall_start, ifc_wall_end = extrPoints(ifc_wall)
                # check if the start or the end of the ifc wall is in the bounding box around the start of the point cloud wall
                if is_within_bounding_box(ifc_wall_start, base_box) or is_within_bounding_box(ifc_wall_end, base_box):
                    candidate_walls.append(ifc_wall)
                # check if the start or the end of the ifc wall is in the bounding box around the end of the point cloud wall
                elif is_within_bounding_box(ifc_wall_start, end_box) or is_within_bounding_box(ifc_wall_end, end_box):
                    candidate_walls.append(ifc_wall)
            else:
                continue
            
        # Select the closest matching wall based on thickness
        closest_wall = None
        # min thickness diff is started as a very high number (infinity) and interatively uptated to the smallest difference among walls
        min_thickness_diff = float('inf')

        for candidate_wall in candidate_walls:
            candidate_thickness = candidate_wall.Representation.Representations[1].Items[0].SweptArea.YDim
            thickness_diff = abs(candidate_thickness - wall_properties['thickness'])
                # is is adopted that an IFC wall that has a difference in thickness of less than 6 cm should be found around the point cloud wall,
                # otherwise another more fitting wall is searched in the entire model
            if thickness_diff <= 0.06 and thickness_diff < min_thickness_diff:
                min_thickness_diff = thickness_diff
                closest_wall = candidate_wall
            
        # if any fitting if wall is found close to it... look at the entire model
        if not closest_wall:
            # If no wall is found within the bounding boxes, find the closest thickness wall in the entire model
            for ifc_wall in model.by_type('IfcWallStandardCase'):
                if ifc_wall.Representation.Representations[1].Items[0].SweptArea.is_a('IfcRectangleProfileDef'):
                    candidate_thickness = ifc_wall.Representation.Representations[1].Items[0].SweptArea.YDim
                    thickness_diff = abs(candidate_thickness - wall_properties['thickness'])
                    if thickness_diff < min_thickness_diff:
                        min_thickness_diff = thickness_diff
                        closest_wall = ifc_wall
                else: continue
        existing_wall = closest_wall
        
        if existing_wall:
            # Copy a previously existing wall, but most attributes will be empty. To copy all attributes, 
            # ifcopenshell.util.element.copy_deep could be used, but many attributes would have to be replaced anyways
            # copy_deep is used in the column update module if the user wants to see an example of the use
            new_wall = ifcopenshell.util.element.copy(model, existing_wall)
            
            # Assign a new GUID and the new owner history to the new wall
            new_wall.GlobalId = ifcopenshell.guid.compress(uuid.uuid1().hex)
            new_wall.OwnerHistory = owner_history
            
            # Determine whether the wall is vertical or horizontal, as different geometric operations are used for the creation of each one
            dx = max(wall_properties['end point'][0], wall_properties['base point'][0]) - min(wall_properties['end point'][0], wall_properties['base point'][0])
            dy = max(wall_properties['end point'][1], wall_properties['base point'][1]) - min(wall_properties['end point'][1], wall_properties['base point'][1])
            # also works: 
            # if wall_properties['type'] == 'horizontal':
            if abs(dx) > abs(dy):

                ###########################################
                #######  The wall is HORIZONTAL  ##########
                ###########################################

                # Create a Local Placement and fill it with data
                new_placement = model.create_entity('IfcLocalPlacement')
                new_placement.RelativePlacement = model.create_entity('IfcAxis2Placement3D')
                # Fill the local placement with data. The further entities for Reference Direction are not created for horizontal walls, as all
                # horizontal walls created by this script have the same (1.0, 0.0, 0.0) direction of the floor the wall is located in, which
                # makes reference directions superfluous, being then set to None.
                new_placement.RelativePlacement.Axis = None # for vertical walls: model.create_entity('IfcDirection'), shown later
                
                new_placement.RelativePlacement.RefDirection = None
                
                # Here the location of the new IFC wall is set as the same as the point cloud wall. At this point the z coordinate of the wall's location
                # is still the same as the point cloud wall, in global coordinates, but later it will be set to a height relative to the floor the wall is located
                # located in. That is also why the extrPoints() function has a special case to handle the position of a wall when it does not yet have a floor
                # assigned to it. Later the x and y coordinates of the location are also slightly adjusted to smoothen the connection of the wall to other walls.
                new_placement.RelativePlacement.Location = model.create_entity('IfcCartesianPoint')
                new_placement.RelativePlacement.Location.Coordinates = wall_properties['base point']
               
                # set the local placement entities created as the ObjectPlacement of the new wall
                new_wall.ObjectPlacement = new_placement
                new_wall.ObjectPlacement.PlacementRelTo = existing_wall.ObjectPlacement.PlacementRelTo # these semantics can be reused from the existing template wall
                
                # Wall Representation
                # The representation of the wall usually has two separate shape representations. One represents the profile, and the other can be used to represent
                # the outline of the wall, as a polyline. Therefore two IfcShapeRepresentation entities need to be created and populated with data
                new_representation = model.create_entity('IfcProductDefinitionShape')
                new_shape_representation1 = model.create_entity('IfcShapeRepresentation')
                new_shape_representation2 = model.create_entity('IfcShapeRepresentation')
                
                # Initialize the Representations attribute as an empty tuple
                new_representation.Representations = ()
                # Add the new shape representations into the tuple of representations, this needs to be done as a sum of a tuple into the current tuple value
                new_representation.Representations = new_representation.Representations + (new_shape_representation1,)
                new_representation.Representations = new_representation.Representations + (new_shape_representation2,)


                # First geometric representation

                #this first item ContextOfItems can be used from an existing wall
                new_representation.Representations[0].ContextOfItems = existing_wall.Representation.Representations[0].ContextOfItems
                new_representation.Representations[0].RepresentationIdentifier = 'Axis'
                new_representation.Representations[0].RepresentationType = 'Curve2D'
                
                new_polyline = model.create_entity('IfcPolyline')
                #initialize the tuple and add the ifc polyline that will represent the wall
                new_representation.Representations[0].Items = ()
                new_representation.Representations[0].Items = new_representation.Representations[0].Items + (new_polyline,)
                new_representation.Representations[0].Items[0].Points = ()
                # this new polyline is defined by ifc points, the first one is a (0,0) internal coordinate that can be used from
                # the existing wall, and the second point represents the length of the wall internally, on the x coordinate
                new_point1 = model.create_entity('IfcCartesianPoint')
                new_representation.Representations[0].Items[0].Points = new_representation.Representations[0].Items[0].Points + (existing_wall.Representation.Representations[0].Items[0].Points[0],)
                new_representation.Representations[0].Items[0].Points = new_representation.Representations[0].Items[0].Points + (new_point1,)
                # the first point, after being created and assigned to the tuple of points, can have a tuple of its coordinates assigned to its coordinates
                new_representation.Representations[0].Items[0].Points[1].Coordinates = (wall_properties['length'], 0.0)


                # Second geometric representation
                new_representation.Representations[1].ContextOfItems = existing_wall.Representation.Representations[1].ContextOfItems
                new_representation.Representations[1].RepresentationIdentifier = 'Body'
                new_representation.Representations[1].RepresentationType = 'SweptSolid'
                new_representation.Representations[1].Items = ()
                # here again the entity for an extruded area representation needs to be assigned as a tuple adition into the representation items
                new_extruded_area_solid1 = model.create_entity('IfcExtrudedAreaSolid')
                new_representation.Representations[1].Items = new_representation.Representations[1].Items + (new_extruded_area_solid1,)
                new_representation.Representations[1].Items[0].Depth = wall_properties['height'] # the height is refined later to equal that of walls around it if it should
                #use the same extruded direction from an existing wall, to not have to create a new ifc entity instance, as they are the same for all walls
                new_representation.Representations[1].Items[0].ExtrudedDirection = existing_wall.Representation.Representations[1].Items[0].ExtrudedDirection
                #definition of the profile area of the wall
                new_representation.Representations[1].Items[0].SweptArea = model.create_entity('IfcRectangleProfileDef')
                new_representation.Representations[1].Items[0].SweptArea.ProfileType = 'AREA'
                new_representation.Representations[1].Items[0].SweptArea.XDim = float(wall_properties['length'])
                new_representation.Representations[1].Items[0].SweptArea.YDim = float(wall_properties['thickness'])
                new_representation.Representations[1].Items[0].SweptArea.Position = model.create_entity('IfcAxis2Placement2D')
                new_representation.Representations[1].Items[0].SweptArea.Position.Location = model.create_entity('IfcCartesianPoint')
                #this rectangle that represents the wall has its internal location point in the centre of the rectangle, so length divided by 2
                new_representation.Representations[1].Items[0].SweptArea.Position.Location.Coordinates = (float(wall_properties['length'])/2, 0.0)
                new_representation.Representations[1].Items[0].SweptArea.Position.RefDirection = existing_wall.Representation.Representations[1].Items[0].SweptArea.Position.RefDirection
                new_representation.Representations[1].Items[0].Position = existing_wall.Representation.Representations[1].Items[0].Position #is this right? update: yea ig
                
                
                #creation of an IfcStyledItem entity, it is not part of the wall, but mentions the wall in its attributes
                new_styled_item = model.create_entity('IfcStyledItem')
                #here under, mention in the IfcStyledItem entity is made to the representation of the new wall
                new_styled_item.Item = new_representation.Representations[1].Items[0]
                new_styled_item.Styles = ()
                new_styles1 = model.create_entity('IfcPresentationStyleAssignment')
                new_styled_item.Styles = new_styled_item.Styles + (new_styles1,)
                new_styled_item.Styles[0].Styles = ()
                new_surface_style1 = model.create_entity('IfcSurfaceStyle')
                new_styled_item.Styles[0].Styles = new_styled_item.Styles[0].Styles + (new_surface_style1,)
                #from here on, the attributes of the styledItem are identical to other walls of the same type, so they can be copied from an existing wall
                new_styled_item.Styles[0].Styles = existing_wall.Representation.Representations[1].Items[0].StyledByItem[0].Styles[0].Styles

                new_wall.Representation = new_representation
                #new_wall.Tag = 'Tag'


                # A number of wall attributes are found in wall.IsDefinedBy, that are usually shared among all internal walls
                # that includes visualization properties, attributes that determine whether the wall connects to the ceiling
                # or not, whether the wall is an interior wall or not, loadbearing, etc. Those attributes can be copied from the 
                # exinsting wall being used as reference, but if a given value or parameter needs to be added to new walls,
                # the code can be changed here to include this option. There are a number of IfcRelDefinesByProperties
                # instances that connect those attributes to one of the existing walls. What the code does here is to include
                # the new wall into the tuple of walls (previously just one) that are receiving each attribute. So in a way
                # the definition of some generic properties of the template wall are expanded to apply also to the new wall.
                # To expand this code and make it more complete it could create individual instances  of those definitions to
                # say if the wall is load bearing or not, etc. But as this is not important for many purposes those properties 
                # were copied for the sake of brevity. 

                # An iteration is done in reverse order, as it was observed that if the iteration altering each item is done in normal
                # order, the index of the altered item changes to the last index of the list, messing the orders of indexes and not updating all items.
                # Therefore, if the count starts at the last index, it remains last, then it goes to index n-1, and sends n-1 into last position
                # but it keeps feeding the parsing process with indexes whose order was not yet scrambled and allows all items to be changed only once
                
                # Iterate over the IsDefinedBy attributes of the existing wall in reverse order
                for i in range(len(existing_wall.IsDefinedBy)-1, -1, -1):
                    # Create a new tuple that includes all the existing objects plus the new object
                    new_related_objects = existing_wall.IsDefinedBy[i].RelatedObjects + (new_wall,)
                    # Assign the new tuple to the RelatedObjects attribute
                    existing_wall.IsDefinedBy[i].RelatedObjects = new_related_objects

                #wall material association, add new wall to the list of other walls with the same material
                existing_wall.HasAssociations[0].RelatedObjects = existing_wall.HasAssociations[0].RelatedObjects + (new_wall,)

                
            else:
                #################################################
                # ########## The wall is VERTICAL ############# #
                #################################################

                #Local Placement
                new_placement = model.create_entity('IfcLocalPlacement')
                new_placement.RelativePlacement = model.create_entity('IfcAxis2Placement3D')
                # for vertical walls there shall be axes that give it a Reference Direction to convert the internal coordinates into the
                # coordinates of the context, of the floor the wall is located in
                new_placement.RelativePlacement.Axis = model.create_entity('IfcDirection')
                new_placement.RelativePlacement.Axis.DirectionRatios = (0., 0., 1.)
                new_placement.RelativePlacement.RefDirection = model.create_entity('IfcDirection')
                # (0.0, 1.0, 0.0) is chosen as the standard reference direction for vertical walls as walls that start at the lowest global y coordinate
                # and end at the highest global y coordinate
                new_placement.RelativePlacement.RefDirection.DirectionRatios = (0., 1., 0.)
                new_placement.RelativePlacement.Location = model.create_entity('IfcCartesianPoint')
                new_placement.RelativePlacement.Location.Coordinates = wall_properties['base point']
                #new_placement.PlacesObject[0] = (new_wall,) -> not necessary
                
                new_wall.ObjectPlacement = new_placement
                
                new_wall.ObjectPlacement.PlacementRelTo = existing_wall.ObjectPlacement.PlacementRelTo # can be used as the same of an existing wall
                
                # Wall Representation
                # The representation of the wall usually has two separate shape representations. One represents the profile, and the other can be used to represent
                # the outline of the wall, as a polyline. Therefore two IfcShapeRepresentation entities need to be created and populated with data
                new_representation = model.create_entity('IfcProductDefinitionShape')
                new_shape_representation1 = model.create_entity('IfcShapeRepresentation')
                new_shape_representation2 = model.create_entity('IfcShapeRepresentation')
                # Initialize the Representations attribute as an empty tuple
                new_representation.Representations = ()
                # Add the new shape representations into the tuple of representations, this needs to be done as a sum of a tuple into the current tuple value
                new_representation.Representations = new_representation.Representations + (new_shape_representation1,)
                new_representation.Representations = new_representation.Representations + (new_shape_representation2,)

            
                # First geometric representation

                #this first item ContextOfItems can be used from an existing wall
                new_representation.Representations[0].ContextOfItems = existing_wall.Representation.Representations[0].ContextOfItems
                new_representation.Representations[0].RepresentationIdentifier = 'Axis'
                new_representation.Representations[0].RepresentationType = 'Curve2D'
                new_polyline = model.create_entity('IfcPolyline')
                new_representation.Representations[0].Items = ()
                new_representation.Representations[0].Items = new_representation.Representations[0].Items + (new_polyline,)
                new_representation.Representations[0].Items[0].Points = ()
                # this new polyline is defined by ifc points, the first one is a (0,0) internal coordinate that can be used from
                # the existing wall, and the second point represents the length of the wall internally, on the x coordinate
                new_point1 = model.create_entity('IfcCartesianPoint')
                new_representation.Representations[0].Items[0].Points = new_representation.Representations[0].Items[0].Points + (existing_wall.Representation.Representations[0].Items[0].Points[0],)
                new_representation.Representations[0].Items[0].Points = new_representation.Representations[0].Items[0].Points + (new_point1,)
                new_representation.Representations[0].Items[0].Points[1].Coordinates = (wall_properties['length'], 0.0)
                
                # second geometric representation
                new_representation.Representations[1].ContextOfItems = existing_wall.Representation.Representations[1].ContextOfItems
                new_representation.Representations[1].RepresentationIdentifier = 'Body'
                new_representation.Representations[1].RepresentationType = 'SweptSolid'
                new_representation.Representations[1].Items = ()
                new_extruded_area_solid1 = model.create_entity('IfcExtrudedAreaSolid')
                # here again the entity for an extruded area representation needs to be assigned as a tuple adition into the representation items
                new_representation.Representations[1].Items = new_representation.Representations[1].Items + (new_extruded_area_solid1,)
                new_representation.Representations[1].Items[0].Depth = wall_properties['height']  # the height is refined later to equal that of walls around it if it should
                #use the same extruded direction from an existing wall, to not have to create a new ifc entity instance, as they are the same for all walls
                new_representation.Representations[1].Items[0].ExtrudedDirection = existing_wall.Representation.Representations[1].Items[0].ExtrudedDirection
                # definition of the profile area of a wall
                new_representation.Representations[1].Items[0].SweptArea = model.create_entity('IfcRectangleProfileDef')
                new_representation.Representations[1].Items[0].SweptArea.ProfileType = 'AREA'
                new_representation.Representations[1].Items[0].SweptArea.XDim = float(wall_properties['length'])
                new_representation.Representations[1].Items[0].SweptArea.YDim = float(wall_properties['thickness'])
                new_representation.Representations[1].Items[0].SweptArea.Position = model.create_entity('IfcAxis2Placement2D')
                new_representation.Representations[1].Items[0].SweptArea.Position.Location = model.create_entity('IfcCartesianPoint')
                #this rectangle that represents the wall has its internal location point in the centre of the rectangle, so length divided by 2
                new_representation.Representations[1].Items[0].SweptArea.Position.Location.Coordinates = (float(wall_properties['length'])/2, 0.0)
                new_representation.Representations[1].Items[0].SweptArea.Position.RefDirection = existing_wall.Representation.Representations[1].Items[0].SweptArea.Position.RefDirection
                new_representation.Representations[1].Items[0].Position = existing_wall.Representation.Representations[1].Items[0].Position
                
                #creation of an IfcStyledItem entity, it is not part of the wall, but mentions the wall in its attributes
                new_styled_item = model.create_entity('IfcStyledItem')
                #here under, mention in the IfcStyledItem entity is made to the representation of the new wall
                new_styled_item.Item = new_representation.Representations[1].Items[0]
                new_styled_item.Styles = ()
                new_styles1 = model.create_entity('IfcPresentationStyleAssignment')
                new_styled_item.Styles = new_styled_item.Styles + (new_styles1,)
                new_styled_item.Styles[0].Styles = ()
                new_surface_style1 = model.create_entity('IfcSurfaceStyle')
                new_styled_item.Styles[0].Styles = new_styled_item.Styles[0].Styles + (new_surface_style1,)
                #from here on, the attributes of the styledItem are identical to other walls of the same type, so they can be copied from an existing wall
                new_styled_item.Styles[0].Styles = existing_wall.Representation.Representations[1].Items[0].StyledByItem[0].Styles[0].Styles

                    
                new_wall.Representation = new_representation
                
                

                
                
                # A number of wall attributes are found in wall.IsDefinedBy, that are usually shared among all internal walls
                # that includes visualization properties, attributes that determine whether the wall connects to the ceiling
                # or not, whether the wall is an interior wall or not, loadbearing, etc. Those attributes can be copied from the 
                # exinsting wall being used as reference, but if a given value or parameter needs to be added to new walls,
                # the code can be changed here to include this option. There are a number of IfcRelDefinesByProperties
                # instances that connect those attributes to one of the existing walls. What the code does here is to include
                # the new wall into the tuple of walls (previously just one) that are receiving each attribute. So in a way
                # the definition of some generic properties of the template wall are expanded to apply also to the new wall.
                # To expand this code and make it more complete it could create individual instances  of those definitions to
                # say if the wall is load bearing or not, etc. But as this is not important for many purposes those properties 
                # were copied for the sake of brevity. 

                # An iteration is done in reverse order, as it was observed that if the iteration altering each item is done in normal
                # order, the index of the altered item changes to the last index of the list, messing the orders of indexes and not updating all items.
                # Therefore, if the count starts at the last index, it remains last, then it goes to index n-1, and sends n-1 into last position
                # but it keeps feeding the parsing process with indexes whose order was not yet scrambled and allows all items to be changed only once
                
                # Iterate over the IsDefinedBy attributes of the existing wall in reverse order
                for i in range(len(existing_wall.IsDefinedBy)-1, -1, -1):
                    # Create a new tuple that includes all the existing objects plus the new object
                    new_related_objects = existing_wall.IsDefinedBy[i].RelatedObjects + (new_wall,)
                    # Assign the new tuple to the RelatedObjects attribute
                    existing_wall.IsDefinedBy[i].RelatedObjects = new_related_objects


                # if the methodology of updating the indexes in the way below, commented, were to be used, some errors are obtained
                # because the indexes in IsDefinedBy are rearranged for each line performed. In the end, some of the original
                # indexes end up with too much new information (new_wall assigned to it multiple times), and some with no information
                    # wrong methodology:
                # existing_wall.IsDefinedBy[0].RelatedObjects = existing_wall.IsDefinedBy[0].RelatedObjects + (new_wall,)
                # existing_wall.IsDefinedBy[1].RelatedObjects = existing_wall.IsDefinedBy[1].RelatedObjects + (new_wall,)
                # existing_wall.IsDefinedBy[2].RelatedObjects = existing_wall.IsDefinedBy[2].RelatedObjects + (new_wall,)
                # existing_wall.IsDefinedBy[3].RelatedObjects = existing_wall.IsDefinedBy[3].RelatedObjects + (new_wall,)
                # existing_wall.IsDefinedBy[4].RelatedObjects = existing_wall.IsDefinedBy[4].RelatedObjects + (new_wall,)
                # existing_wall.IsDefinedBy[5].RelatedObjects = existing_wall.IsDefinedBy[5].RelatedObjects + (new_wall,)
                
                #wall material association, add new wall to the list of other walls with the same material
                existing_wall.HasAssociations[0].RelatedObjects = existing_wall.HasAssociations[0].RelatedObjects + (new_wall,)
            

                

            # Modify the other properties of the new wall and improve geometry
    
            #Add new wall into the elements listed in its Level
            # Get the z-coordinate of the base point of the new wall
            z_new_wall = float(wall_properties['base point'][2])
            
            # Iterate over all existing walls
            for existing_wall in model.by_type('IfcWallStandardCase'):
                if new_wall != existing_wall and existing_wall not in new_walls: #new_walls are not assigned to a floor yet so we do not want to use those as template

                    if existing_wall.Representation.Representations[1].Items[0].SweptArea.is_a('IfcRectangleProfileDef'):
                    # Check if the existing wall has a relative placement coordinate
                        if existing_wall.ObjectPlacement:
                            # Get the z-coordinate of the relative placement coordinate
                            # Worth mentioning that in extrPoints, for existing walls, the z coordinate retrieved is not the one from ObjectPlacement.RelativePlacement.Location.Coordinates but the one 
                            # in wall.ContainedInStructure[0].RelatingStructure.Elevation. This is done so that the "global height" of the existing wall can be compared
                            # to the height of the new wall, that until then was in global coordinates, and then after the comparison, here, the new wall gets the right
                            # z coordinate assigned to its ...Location.Coordinates, which will be around 0.0 instead of e.g. 3.8 or 4.0 etc. 
                            # The extrPoints function checks if a wall is new or existing, the existing wall gets checked as just mentioned for the z coordinate
                            # and a new wall that has no ContainedInStructure gets the z coordinate from its ...Location.Coordinates, as it still has its global Z there until that point
                            z_existing_wall = extrPoints(existing_wall)[0][2]
                            # Check if the existing wall starting point elevation coordinate is close to the new wall
                            if abs(z_new_wall - z_existing_wall ) <= 0.35:
                                #add new wall to the list of walls in the same level
                                existing_wall.ContainedInStructure[0].RelatedElements = existing_wall.ContainedInStructure[0].RelatedElements + (new_wall,)
                                #copy the same z coordinate to ensure the new wall starts at the same level as other walls around it, see third value of the tuple ->
                                new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates = (new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[0], new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[1], existing_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2])
                                # set the same height of the wall into walls around it if the difference in height is not too great, to have the geometry of the walls aligned on top
                                if abs(new_wall.Representation.Representations[1].Items[0].Depth - existing_wall.Representation.Representations[1].Items[0].Depth) <= 0.3:
                                    new_wall.Representation.Representations[1].Items[0].Depth = existing_wall.Representation.Representations[1].Items[0].Depth
                                    
                                break
                    else: continue
            
                        
            
            # it is important to add connections only after all new walls are created because some connections
            # might be with new walls that otherwise did not exist yet at the time of the iteration
            new_walls.append(new_wall)
    
    

    # Code to refine the geometry of wall connections
    import math

    def euclidean_distance(point1, point2):
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(point1, point2)))

    # The code here aims to improve the geometry of the newly created walls, to compensate for imprecisions of the LiDAR scanner and differences 
    # in how the start and end of a wall are defined in a point cloud and in an IFC file. The walls at the IFC file are defined as extrusions of profiles,
    # as a solid, usually and extruded rectangle, and the walls in a point cloud are segmented as planes of the visible surfaces of the wall, usually just 
    # the two faces of a wall. This difference in definition between plane representations of geometry and solid representations of geometry creates some
    # ambiguities in defining where a wall starts and ends, which are further discussed in the report. But in order to have smothened corners at connections
    # we can perform improvements at the wall geometry. Those improvements are done mainly in 8 steps for walls following a manhattan world assumption.
    # 
    # The first 4 cases deal with the connections at the starting point of the wall, when the wall that is being updated is horizontal and is being connected
    # to another horizontal wall, when the wall that is being updated is horizontal and is being connected to a vertical wall, when the wall that is being
    # updated is vertical and is connected to another vertical wall, when the wall that is being updated is vertical and is connected into a horizontal wall.
    # The last 4 cases deal with updating the end point of the wall in a similar fashion to the one described above. The main difference is that the first 4
    # cases update the actual position of the wall, with the freedom to move it in the x and y directions to generate smooth geometry, and the last 4 cases
    # only change the lenght of the wall. That happens for two reasons: one of them is that the end point of a wall is only defined implicitly, based off the
    # length of the wall, and the second reason is that because the start of the wall is already aligned to the walls around it, we don't want to move it
    # and disalign that side just to align the other end. So at the end point the algorithm looks for the best length that will generate the best alignment
    # to walls around it. In a horizontal wall that would be the optimal adition of subtraction of the length of the wall in the x direction, the direction
    # of a horizontal wall, and for a vertical wall the challenge is finding the best alignment in the y direction (that is however represented as the 
    # internal length of the wall in the internal x direction).

    for new_wall in new_walls:
        new_wall_is_horizontal = False  
        new_wall_is_vertical = False
        new_wall_has_hor_connection = False
        new_wall_has_ver_connection = False
        new_wall_start, new_wall_end = extrPoints(new_wall)
        # YDim, the thickness of the wall, is quite useful in aligning a wall being studied to another wall orthogonal to it, as the connection should either
        # be aligned to the closest face of the wall or to the opposite face of the orthogonal wall
        new_wall_dim_y = new_wall.Representation.Representations[1].Items[0].SweptArea.YDim
        new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection is None
        # if the direction ratios are not mentioned in a wall, the code would break trying to look for them in walls that don't have them
        # so we mention them as an exception for walls that do have them
        if new_wall.ObjectPlacement.RelativePlacement.RefDirection is not None:
            new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
            new_wall_is_vertical = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]
        for existing_wall in model.by_type('IfcWallStandardCase'):
            # first we match the new walls only to previously existing walls in the model, as not all new walls were corrected yet. Later on
            # a similar code section will also update (or try to) new walls relative to other possible new walls around it
            if existing_wall not in new_walls and existing_wall.Representation.Representations[1].Items[0].SweptArea.is_a('IfcRectangleProfileDef'): 

                if new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2] == existing_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2]:  # Check if on the same floor, possibly a small threshold here could be useful for walls with slightly different elevations
                    existing_wall_is_vertical = False
                    existing_wall_is_horizontal = False
                    existing_wall_start, existing_wall_end = extrPoints(existing_wall)
                    existing_wall_dim_y = existing_wall.Representation.Representations[1].Items[0].SweptArea.YDim
                    existing_wall_is_horizontal = existing_wall.ObjectPlacement.RelativePlacement.RefDirection is None
                    if existing_wall.ObjectPlacement.RelativePlacement.RefDirection is not None:
                        existing_wall_is_horizontal = existing_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
                        existing_wall_is_vertical = existing_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]
                        
                    # Here an interim check is done to see if horizontal walls have horizontal connections and vertical walls have vertical connections
                    # as, if true, those connections should take preference in determining the new wall position to keep a better geometrical alignment
                    if new_wall_is_horizontal and existing_wall_is_horizontal:
                        # Check if either the start of the new wall is close enough to determine a connection to the start of another wall, or to the end of another wall
                        # Here a dynamic threshold is used, so the highest value between 0.35 and 3 times the wall thickness. For most cases 0.35 should be fine, but if a wall
                        # is 0.7 m thick the point defined as start or end of the neaby connected wall might be much more far away
                        if euclidean_distance(new_wall_start, existing_wall_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, existing_wall_end) <= max(0.55, 2.5*new_wall_dim_y):
                            new_wall_has_hor_connection = True

                    elif new_wall_is_vertical and existing_wall_is_vertical:
                        if euclidean_distance(new_wall_start, existing_wall_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, existing_wall_end) <= max(0.55, 2.5*new_wall_dim_y):
                            new_wall_has_ver_connection = True

                   
        for existing_wall in model.by_type('IfcWallStandardCase'):
            if existing_wall not in new_walls and existing_wall.Representation.Representations[1].Items[0].SweptArea.is_a('IfcRectangleProfileDef'): 

                if new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2] == existing_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2]:  # Check if on the same floor
                    existing_wall_is_vertical = False
                    existing_wall_is_horizontal = False
                    existing_wall_start, existing_wall_end = extrPoints(existing_wall)
                    existing_wall_dim_y = existing_wall.Representation.Representations[1].Items[0].SweptArea.YDim
                    existing_wall_is_horizontal = existing_wall.ObjectPlacement.RelativePlacement.RefDirection is None
                    if existing_wall.ObjectPlacement.RelativePlacement.RefDirection is not None:
                        existing_wall_is_horizontal = existing_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
                        existing_wall_is_vertical = existing_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]
                    if new_wall_is_horizontal:
                        # A change of position in a horizontal wall gives preference in aligning it into another horizontal wall connected to it
                        if new_wall_has_hor_connection:
                            # Update start points (Cases 1-4)
                            # check if the walls are close enough to be considered as connected
                            if existing_wall_is_horizontal and (euclidean_distance(new_wall_start, existing_wall_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, existing_wall_end) <= max(0.55, 2.5*new_wall_dim_y)):
                                if euclidean_distance(new_wall_start, existing_wall_start) < euclidean_distance(new_wall_start, existing_wall_end):
                                    # if there is a gap between the two horizontal walls, or an overlap, the start of one is aligned to the end of the other
                                    # or start to start, if there is a horizontal wall with (-1.0, 0.0, 0.0) reference direction connected to the new wall
                                    new_wall_start = existing_wall_start
                                else:
                                    new_wall_start = existing_wall_end
                            else:
                                # if there is any horizontal wall connected to the horizontal wall, look for it, an alignment based on vertical wall connection (case 2) is only
                                # applied when no horizontal connection exist (that is why the else option is used, else is only parsed if the "if" condition is false)
                                continue
                        else:
                            #Case 2
                            if new_wall_is_horizontal and existing_wall_is_vertical:
                                if euclidean_distance(new_wall_start, existing_wall_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, existing_wall_end) <= max(0.55, 2.5*new_wall_dim_y):
                                    if euclidean_distance(new_wall_start, existing_wall_start) < euclidean_distance(new_wall_start, existing_wall_end):
                                        # the existing_wall start or end coordinate aligns to its longitudinal axis, so using half the thickness of the existing wall aligns the new wall
                                        # to one of the faces of the existing wall
                                        new_wall_start = (existing_wall_start[0] - 0.5 * existing_wall_dim_y, existing_wall_start[1], new_wall_start[2])
                                    else:
                                        new_wall_start = (existing_wall_end[0] - 0.5 * existing_wall_dim_y, existing_wall_end[1], new_wall_start[2])

                    elif new_wall_is_vertical:
                        if new_wall_has_ver_connection:
                            #Case 3 - here again, give preference to vertical walls connected to other vertical walls to keep the alignment
                            if existing_wall_is_vertical and (euclidean_distance(new_wall_start, existing_wall_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, existing_wall_end) <= max(0.55, 2.5*new_wall_dim_y)):
                                # whichever end (end or start) of the nearby wall is the closest to the start of the new wall, use it to correct the position and align
                                if euclidean_distance(new_wall_start, existing_wall_start) < euclidean_distance(new_wall_start, existing_wall_end):
                                    new_wall_start = existing_wall_start
                                else:
                                    new_wall_start = existing_wall_end
                            else:
                                continue
                        else:
                            #Case 4
                            if new_wall_is_vertical and existing_wall_is_horizontal:
                                if euclidean_distance(new_wall_start, existing_wall_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, existing_wall_end) <= max(0.55, 2.5*new_wall_dim_y):
                                    # if the starting points of both walls are the closest to each other and they are connected
                                    if euclidean_distance(new_wall_start, existing_wall_start) < euclidean_distance(new_wall_start, existing_wall_end):
                                        if existing_wall.ObjectPlacement.RelativePlacement.RefDirection is None:
                                            # if refDirection is none the existing wall conencting to the new wall follows the global coordinates and is at the right side
                                            # of the vertical wall, so moving the new wall to the right can ensure alignment and no indentation at the connection
                                            new_wall_start = (existing_wall_start[0] + 0.5 * new_wall_dim_y, existing_wall_start[1], new_wall_start[2])
                                        else:
                                            new_wall_start = (existing_wall_start[0] - 0.5 * new_wall_dim_y, existing_wall_start[1], new_wall_start[2])
                                    # start to end conenction. RefDirection None gives the cue of whether the horizontal connected wall is at the right or left side of the vertical wall
                                    else:
                                        if existing_wall.ObjectPlacement.RelativePlacement.RefDirection is None:
                                            new_wall_start = (existing_wall_end[0] - 0.5 * new_wall_dim_y,existing_wall_start[1], new_wall_start[2])
                                        else:
                                            new_wall_start = (existing_wall_end[0] + 0.5 * new_wall_dim_y, existing_wall_start[1], new_wall_start[2])

            # Now, update the start point of the new wall
            # new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates = new_wall_start
            new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates = (new_wall_start[0], new_wall_start[1], new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2])

    

    # Update end points (Cases 5-8)
    for new_wall in new_walls:
        new_wall_is_horizontal = False
        new_wall_is_vertical = False
        new_wall_start, new_wall_end = extrPoints(new_wall)
        new_wall_dim_y = new_wall.Representation.Representations[1].Items[0].SweptArea.YDim
        new_wall_length = new_wall.Representation.Representations[0].Items[0].Points[1].Coordinates[0]
        new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection is None
        if new_wall.ObjectPlacement.RelativePlacement.RefDirection is not None:
            new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
            new_wall_is_vertical = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]

        for existing_wall in model.by_type('IfcWallStandardCase'):
            if existing_wall not in new_walls and existing_wall.Representation.Representations[1].Items[0].SweptArea.is_a('IfcRectangleProfileDef'):
                if new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2] == existing_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2]:  # Check if on the same floor
                    existing_wall_is_horizontal = False
                    existing_wall_is_vertical = False
                    existing_wall_start, existing_wall_end = extrPoints(existing_wall)
                    existing_wall_dim_y = existing_wall.Representation.Representations[1].Items[0].SweptArea.YDim
                    existing_wall_is_horizontal = existing_wall.ObjectPlacement.RelativePlacement.RefDirection is None
                    if existing_wall.ObjectPlacement.RelativePlacement.RefDirection is not None:
                        existing_wall_is_horizontal = existing_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
                        existing_wall_is_vertical = existing_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]
                    
                    # here the alignment of horizontal-horizontal and vertical-vertical is not as important as only the lenght of the wall is being changed anyways
                    # case5
                    if new_wall_is_horizontal and existing_wall_is_horizontal:
                        # The minimum value at the dynamic threshold is higher at the wall end because the start point was just moved, possibly
                        # making distances to another wall even greater without, until here, a change in the wall length
                        if euclidean_distance(new_wall_end, existing_wall_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, existing_wall_end) <= max(0.75, 2.8*new_wall_dim_y):
                            if euclidean_distance(new_wall_end, existing_wall_start) < euclidean_distance(new_wall_end, existing_wall_end):
                                new_wall_length = existing_wall_start[0] - new_wall_start[0]
                            else:
                                new_wall_length = existing_wall_end[0] - new_wall_start[0]
                    # case 6
                    elif new_wall_is_horizontal and existing_wall_is_vertical:
                        if euclidean_distance(new_wall_end, existing_wall_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, existing_wall_end) <= max(0.75, 2.8*new_wall_dim_y):
                            if euclidean_distance(new_wall_end, existing_wall_start) < euclidean_distance(new_wall_end, existing_wall_end):
                                new_wall_length = existing_wall_start[0] - new_wall_start[0] + 0.5 * existing_wall_dim_y
                            else:
                                new_wall_length = existing_wall_end[0] - new_wall_start[0] + 0.5 * existing_wall_dim_y
                    # case 7
                    elif new_wall_is_vertical and existing_wall_is_vertical:
                        if euclidean_distance(new_wall_end, existing_wall_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, existing_wall_end) <= max(0.75, 2.8*new_wall_dim_y):
                            if euclidean_distance(new_wall_end, existing_wall_start) < euclidean_distance(new_wall_end, existing_wall_end):
                                # If the end of the new wall is conencted to the start of another vertical wall just above it, the ideal length of the wall
                                # should be the distance between this start of the existing wall bordering it, and the start of the new wall
                                new_wall_length = existing_wall_start[1] - new_wall_start[1] 
                            else:
                                # here the case is handled for when IFC decides to name the point of the existing wall above our new vertical wall as an end point, so end point
                                # is connected to end point, but the length of the wall is the distance from this end point of the exsisting wall, ideally just touching 
                                # the end point of the new wall, to the start of the new wall
                                new_wall_length = existing_wall_end[1] - new_wall_start[1] 
                    # case 8
                    elif new_wall_is_vertical and existing_wall_is_horizontal:
                        if euclidean_distance(new_wall_end, existing_wall_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, existing_wall_end) <= max(0.75, 2.8*new_wall_dim_y):
                            new_wall_length = float(existing_wall_start[1] - new_wall_start[1]) + 0.5 * existing_wall_dim_y

            # Update the new wall's length and size of the profile that defines the wall
            new_wall.Representation.Representations[0].Items[0].Points[1].Coordinates = (new_wall_length, 0.0)
            new_wall.Representation.Representations[1].Items[0].SweptArea.XDim = float(new_wall_length)
            new_wall.Representation.Representations[1].Items[0].SweptArea.Position.Location.Coordinates = (float(new_wall_length / 2), 0.0)








    # Repurposing the code to correct connections in points where multiple new walls connect to each other
    # Repeating the process helps solving the alingments that were not solved in the previous step, specially
    # because now we are matching only connections of new walls to other new walls. Previously their connection 
    # to the old walls of the model was improved, and now it is improved among other new walls, if they connect to each other
    import math

    def euclidean_distance(point1, point2):
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(point1, point2)))


    for new_wall in new_walls:
        new_wall_is_horizontal = False  
        new_wall_is_vertical = False
        new_wall_has_hor_connection = False
        new_wall_has_ver_connection = False
        new_wall_start, new_wall_end = extrPoints(new_wall)
        new_wall_dim_y = new_wall.Representation.Representations[1].Items[0].SweptArea.YDim
        new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection is None
        # if the direction ratios are not mentioned in a wall, the code would break trying to look for them in walls that don't have them
        # so we mention them as an exception for walls that do have them
        if new_wall.ObjectPlacement.RelativePlacement.RefDirection is not None:
            new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
            new_wall_is_vertical = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]
        for new_wall2 in new_walls:
            if new_wall2 != new_wall: 

                if new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2] == new_wall2.ObjectPlacement.RelativePlacement.Location.Coordinates[2]:  # Check if on the same floor
                    new_wall2_is_vertical = False
                    new_wall2_is_horizontal = False
                    new_wall2_start, new_wall2_end = extrPoints(new_wall2)
                    new_wall2_dim_y = new_wall2.Representation.Representations[1].Items[0].SweptArea.YDim
                    new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection is None
                    if new_wall2.ObjectPlacement.RelativePlacement.RefDirection is not None:
                        new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
                        new_wall2_is_vertical = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]
                        
                    # checking for horizontal-horizontal and vertical-vertical connections
                    if new_wall_is_horizontal and new_wall2_is_horizontal:
                        if euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y):
                            new_wall_has_hor_connection = True

                    elif new_wall_is_vertical and new_wall2_is_vertical:
                        if euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y):
                            new_wall_has_ver_connection = True

                   
        for new_wall2 in new_walls:
            if new_wall2 != new_wall: 

                if new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2] == new_wall2.ObjectPlacement.RelativePlacement.Location.Coordinates[2]:  # Check if on the same floor
                    new_wall2_is_vertical = False
                    new_wall2_is_horizontal = False
                    new_wall2_start, new_wall2_end = extrPoints(new_wall2)
                    new_wall2_dim_y = new_wall2.Representation.Representations[1].Items[0].SweptArea.YDim
                    new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection is None
                    if new_wall2.ObjectPlacement.RelativePlacement.RefDirection is not None:
                        new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
                        new_wall2_is_vertical = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]
                    if new_wall_is_horizontal:
                        if new_wall_has_hor_connection:
                            # Update start points (Cases 1-4)
                            if new_wall2_is_horizontal and (euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y)):
                                if euclidean_distance(new_wall_start, new_wall2_start) < euclidean_distance(new_wall_start, new_wall2_end):
                                    new_wall_start = new_wall2_start
                                else:
                                    new_wall_start = new_wall2_end
                            else:
                                continue
                        else:
                            #Case 2
                            if new_wall_is_horizontal and new_wall2_is_vertical:
                                if euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.25, 2.5*new_wall_dim_y):
                                    if euclidean_distance(new_wall_start, new_wall2_start) < euclidean_distance(new_wall_start, new_wall2_end):
                                        new_wall_start = (new_wall2_start[0] - 0.5 * new_wall2_dim_y, new_wall2_start[1], new_wall_start[2])
                                    else:
                                        new_wall_start = (new_wall2_end[0] - 0.5 * new_wall2_dim_y, new_wall2_end[1], new_wall_start[2])

                    elif new_wall_is_vertical:
                        if new_wall_has_ver_connection:
                            #Case 3
                            if new_wall2_is_vertical and (euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y)):
                                if euclidean_distance(new_wall_start, new_wall2_start) < euclidean_distance(new_wall_start, new_wall2_end):
                                    new_wall_start = new_wall2_start
                                else:
                                    new_wall_start = new_wall2_end
                            else:
                                continue
                        else:
                            #Case 4
                            if new_wall_is_vertical and new_wall2_is_horizontal:
                                if euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y):
                                    if euclidean_distance(new_wall_start, new_wall2_start) < euclidean_distance(new_wall_start, new_wall2_end):
                                        if new_wall2.ObjectPlacement.RelativePlacement.RefDirection is None:
                                            
                                            new_wall_start = (new_wall2_start[0] + 0.5 * new_wall_dim_y, new_wall2_start[1], new_wall_start[2])
                                        else:
                                            new_wall_start = (new_wall2_start[0] - 0.5 * new_wall_dim_y, new_wall2_start[1], new_wall_start[2])
                                    else:
                                        if new_wall2.ObjectPlacement.RelativePlacement.RefDirection is None:
                                            new_wall_start = (new_wall2_end[0] - 0.5 * new_wall_dim_y, new_wall2_start[1], new_wall_start[2])
                                        else:
                                            new_wall_start = (new_wall2_end[0] + 0.5 * new_wall_dim_y, new_wall2_start[1], new_wall_start[2])

            # Now, update the start point of the new wall
            # new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates = new_wall_start
            new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates = (new_wall_start[0], new_wall_start[1], new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2])

    

    # Update end points (Cases 5-8)
    for new_wall in new_walls:
        new_wall_is_horizontal = False
        new_wall_is_vertical = False
        new_wall_start, new_wall_end = extrPoints(new_wall)
        new_wall_dim_y = new_wall.Representation.Representations[1].Items[0].SweptArea.YDim
        new_wall_length = new_wall.Representation.Representations[0].Items[0].Points[1].Coordinates[0]
        new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection is None
        if new_wall.ObjectPlacement.RelativePlacement.RefDirection is not None:
            new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
            new_wall_is_vertical = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]

        for new_wall2 in model.by_type('IfcWallStandardCase'):
            if new_wall2.Representation.Representations[1].Items[0].SweptArea.is_a('IfcRectangleProfileDef'):    

                if new_wall2 != new_wall:
                    if new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2] == new_wall2.ObjectPlacement.RelativePlacement.Location.Coordinates[2]:  # Check if on the same floor
                        new_wall2_is_horizontal = False
                        new_wall2_is_vertical = False
                        new_wall2_start, new_wall2_end = extrPoints(new_wall2)
                        new_wall2_dim_y = new_wall2.Representation.Representations[1].Items[0].SweptArea.YDim
                        new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection is None
                        if new_wall2.ObjectPlacement.RelativePlacement.RefDirection is not None:
                            new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
                            new_wall2_is_vertical = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]

                        if new_wall_is_horizontal and new_wall2_is_horizontal:
                            if euclidean_distance(new_wall_end, new_wall2_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, new_wall2_end) <= max(0.75, 2.8*new_wall_dim_y):
                                if euclidean_distance(new_wall_end, new_wall2_start) < euclidean_distance(new_wall_end, new_wall2_end):
                                    new_wall_length = new_wall2_start[0] - new_wall_start[0]
                                else:
                                    new_wall_length = new_wall2_end[0] - new_wall_start[0]

                        elif new_wall_is_horizontal and new_wall2_is_vertical:
                            if euclidean_distance(new_wall_end, new_wall2_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, new_wall2_end) <= max(0.75, 2.8*new_wall_dim_y):
                                if euclidean_distance(new_wall_end, new_wall2_start) < euclidean_distance(new_wall_end, new_wall2_end):
                                    new_wall_length = new_wall2_start[0] - new_wall_start[0] + 0.5 * new_wall2_dim_y
                                else:
                                    new_wall_length = new_wall2_end[0] - new_wall_start[0] + 0.5 * new_wall2_dim_y

                        elif new_wall_is_vertical and new_wall2_is_vertical:
                            if euclidean_distance(new_wall_end, new_wall2_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, new_wall2_end) <= max(0.75, 2.8*new_wall_dim_y):
                                if euclidean_distance(new_wall_end, new_wall2_start) < euclidean_distance(new_wall_end, new_wall2_end):
                                    new_wall_length = new_wall2_start[1] - new_wall_start[1] 
                                else:
                                    new_wall_length = new_wall2_end[1] - new_wall_start[1] 

                        elif new_wall_is_vertical and new_wall2_is_horizontal:
                            if euclidean_distance(new_wall_end, new_wall2_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, new_wall2_end) <= max(0.75, 2.8*new_wall_dim_y):
                                new_wall_length = float(new_wall2_start[1] - new_wall_start[1]) + 0.5 *new_wall2_dim_y

                # Update the new wall's length and position
                new_wall.Representation.Representations[0].Items[0].Points[1].Coordinates = (new_wall_length, 0.0)
                new_wall.Representation.Representations[1].Items[0].SweptArea.XDim = float(new_wall_length)
                new_wall.Representation.Representations[1].Items[0].SweptArea.Position.Location.Coordinates = (float(new_wall_length / 2), 0.0)




    # Repurposing the code to correct connections in points where multiple new walls connect to each other
    # the process is repeated one more time just to make sure :D
    import math

    def euclidean_distance(point1, point2):
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(point1, point2)))


    for new_wall in new_walls:
        new_wall_is_horizontal = False  
        new_wall_is_vertical = False
        new_wall_has_hor_connection = False
        new_wall_has_ver_connection = False
        new_wall_start, new_wall_end = extrPoints(new_wall)
        new_wall_dim_y = new_wall.Representation.Representations[1].Items[0].SweptArea.YDim
        new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection is None
        # if the direction ratios are not mentioned in a wall, the code would break trying to look for them in walls that don't have them
        # so we mention them as an exception for walls that do have them
        if new_wall.ObjectPlacement.RelativePlacement.RefDirection is not None:
            new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
            new_wall_is_vertical = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]
        for new_wall2 in new_walls:
            if new_wall2 != new_wall: 

                if new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2] == new_wall2.ObjectPlacement.RelativePlacement.Location.Coordinates[2]:  # Check if on the same floor
                    new_wall2_is_vertical = False
                    new_wall2_is_horizontal = False
                    new_wall2_start, new_wall2_end = extrPoints(new_wall2)
                    new_wall2_dim_y = new_wall2.Representation.Representations[1].Items[0].SweptArea.YDim
                    new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection is None
                    if new_wall2.ObjectPlacement.RelativePlacement.RefDirection is not None:
                        new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
                        new_wall2_is_vertical = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]
                        
                    # Update start points (Cases 1-4)
                    if new_wall_is_horizontal and new_wall2_is_horizontal:
                        if euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y):
                            new_wall_has_hor_connection = True

                    elif new_wall_is_vertical and new_wall2_is_vertical:
                        if euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y):
                            new_wall_has_ver_connection = True

                   
        for new_wall2 in new_walls:
            if new_wall2 != new_wall: 

                if new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2] == new_wall2.ObjectPlacement.RelativePlacement.Location.Coordinates[2]:  # Check if on the same floor
                    new_wall2_is_vertical = False
                    new_wall2_is_horizontal = False
                    new_wall2_start, new_wall2_end = extrPoints(new_wall2)
                    new_wall2_dim_y = new_wall2.Representation.Representations[1].Items[0].SweptArea.YDim
                    new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection is None
                    if new_wall2.ObjectPlacement.RelativePlacement.RefDirection is not None:
                        new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
                        new_wall2_is_vertical = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]
                    if new_wall_is_horizontal:
                        if new_wall_has_hor_connection:
                            # Update start points (Cases 1-4)
                            if new_wall2_is_horizontal and (euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y)):
                                if euclidean_distance(new_wall_start, new_wall2_start) < euclidean_distance(new_wall_start, new_wall2_end):
                                    new_wall_start = new_wall2_start
                                else:
                                    new_wall_start = new_wall2_end
                            else:
                                continue
                        else:
                            #Case 2
                            if new_wall_is_horizontal and new_wall2_is_vertical:
                                if euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y):
                                    if euclidean_distance(new_wall_start, new_wall2_start) < euclidean_distance(new_wall_start, new_wall2_end):
                                        new_wall_start = (new_wall2_start[0] - 0.5 * new_wall2_dim_y, new_wall2_start[1], new_wall_start[2])
                                    else:
                                        new_wall_start = (new_wall2_end[0] - 0.5 * new_wall2_dim_y, new_wall2_end[1], new_wall_start[2])

                    elif new_wall_is_vertical:
                        if new_wall_has_ver_connection:
                            #Case 3
                            if new_wall2_is_vertical and (euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y)):
                                if euclidean_distance(new_wall_start, new_wall2_start) < euclidean_distance(new_wall_start, new_wall2_end):
                                    new_wall_start = new_wall2_start
                                else:
                                    new_wall_start = new_wall2_end
                            else:
                                continue
                        else:
                            #Case 4
                            if new_wall_is_vertical and new_wall2_is_horizontal:
                                if euclidean_distance(new_wall_start, new_wall2_start) <= max(0.55, 2.5*new_wall_dim_y) or euclidean_distance(new_wall_start, new_wall2_end) <= max(0.55, 2.5*new_wall_dim_y):
                                    if euclidean_distance(new_wall_start, new_wall2_start) < euclidean_distance(new_wall_start, new_wall2_end):
                                        if new_wall2.ObjectPlacement.RelativePlacement.RefDirection is None:
                                            
                                            new_wall_start = (new_wall2_start[0] + 0.5 * new_wall_dim_y, new_wall2_start[1], new_wall_start[2])
                                        else:
                                            new_wall_start = (new_wall2_start[0] - 0.5 * new_wall_dim_y, new_wall2_start[1], new_wall_start[2])
                                    else:
                                        if new_wall2.ObjectPlacement.RelativePlacement.RefDirection is None:
                                            new_wall_start = (new_wall2_end[0] - 0.5 * new_wall_dim_y, new_wall2_start[1], new_wall_start[2])
                                        else:
                                            new_wall_start = (new_wall2_end[0] + 0.5 * new_wall_dim_y, new_wall2_start[1], new_wall_start[2])

            # Now, update the start point of the new wall
            # new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates = new_wall_start
            new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates = (new_wall_start[0], new_wall_start[1], new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2])

    

    # Update end points (Cases 5-8)
    for new_wall in new_walls:
        new_wall_is_horizontal = False
        new_wall_is_vertical = False
        new_wall_start, new_wall_end = extrPoints(new_wall)
        new_wall_dim_y = new_wall.Representation.Representations[1].Items[0].SweptArea.YDim
        new_wall_length = new_wall.Representation.Representations[0].Items[0].Points[1].Coordinates[0]
        new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection is None
        if new_wall.ObjectPlacement.RelativePlacement.RefDirection is not None:
            new_wall_is_horizontal = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
            new_wall_is_vertical = new_wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]

        for new_wall2 in model.by_type('IfcWallStandardCase'):
            if new_wall2.Representation.Representations[1].Items[0].SweptArea.is_a('IfcRectangleProfileDef'):    

                if new_wall2 != new_wall:
                    if new_wall.ObjectPlacement.RelativePlacement.Location.Coordinates[2] == new_wall2.ObjectPlacement.RelativePlacement.Location.Coordinates[2]:  # Check if on the same floor
                        new_wall2_is_horizontal = False
                        new_wall2_is_vertical = False
                        new_wall2_start, new_wall2_end = extrPoints(new_wall2)
                        new_wall2_dim_y = new_wall2.Representation.Representations[1].Items[0].SweptArea.YDim
                        new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection is None
                        if new_wall2.ObjectPlacement.RelativePlacement.RefDirection is not None:
                            new_wall2_is_horizontal = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios == (-1., 0., 0.)
                            new_wall2_is_vertical = new_wall2.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios in [(0., 1., 0.), (0., -1., 0.)]

                        if new_wall_is_horizontal and new_wall2_is_horizontal:
                            if euclidean_distance(new_wall_end, new_wall2_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, new_wall2_end) <= max(0.75, 2.8*new_wall_dim_y):
                                if euclidean_distance(new_wall_end, new_wall2_start) < euclidean_distance(new_wall_end, new_wall2_end):
                                    new_wall_length = new_wall2_start[0] - new_wall_start[0]
                                else:
                                    new_wall_length = new_wall2_end[0] - new_wall_start[0]

                        elif new_wall_is_horizontal and new_wall2_is_vertical:
                            if euclidean_distance(new_wall_end, new_wall2_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, new_wall2_end) <= max(0.75, 2.8*new_wall_dim_y):
                                if euclidean_distance(new_wall_end, new_wall2_start) < euclidean_distance(new_wall_end, new_wall2_end):
                                    new_wall_length = new_wall2_start[0] - new_wall_start[0] + 0.5 * new_wall2_dim_y
                                else:
                                    new_wall_length = new_wall2_end[0] - new_wall_start[0] + 0.5 * new_wall2_dim_y

                        elif new_wall_is_vertical and new_wall2_is_vertical:
                            if euclidean_distance(new_wall_end, new_wall2_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, new_wall2_end) <= max(0.75, 2.8*new_wall_dim_y):
                                if euclidean_distance(new_wall_end, new_wall2_start) < euclidean_distance(new_wall_end, new_wall2_end):
                                    new_wall_length = new_wall2_start[1] - new_wall_start[1] 
                                else:
                                    new_wall_length = new_wall2_end[1] - new_wall_start[1] 

                        elif new_wall_is_vertical and new_wall2_is_horizontal:
                            if euclidean_distance(new_wall_end, new_wall2_start) <= max(0.75, 2.8*new_wall_dim_y) or euclidean_distance(new_wall_end, new_wall2_end) <= max(0.75, 2.8*new_wall_dim_y):
                                new_wall_length = float(new_wall2_start[1] - new_wall_start[1]) + 0.5 *new_wall2_dim_y

                # Update the new wall's length and position
                new_wall.Representation.Representations[0].Items[0].Points[1].Coordinates = (new_wall_length, 0.0)
                new_wall.Representation.Representations[1].Items[0].SweptArea.XDim = float(new_wall_length)
                new_wall.Representation.Representations[1].Items[0].SweptArea.Position.Location.Coordinates = (float(new_wall_length / 2), 0.0)






    #named as newWall to avoid a possible confusion with new_wall worked on above
    newWalls_matched_to_eachother = []
    for newWall in new_walls:
        
        # Last step: add connections to other walls into the new wall
                    # Iterate over matched IFC walls
        for ifc_wall in model.by_type("IfcWallStandardCase"):
            if ifc_wall.Representation.Representations[1].Items[0].SweptArea.is_a('IfcRectangleProfileDef'):

                if ifc_wall != newWall:
                                        
                    # Extract the start and end points of the new IFC wall
                    new_wall_points = extrPoints(newWall)
                    new_wall_base = new_wall_points[0]
                    new_wall_end = new_wall_points[1]

                    # Extract the start and end points of the previously existing IFC wall
                    ifc_wall_points = extrPoints(ifc_wall)
                    ifc_wall_base = ifc_wall_points[0]
                    ifc_wall_end = ifc_wall_points[1]

                    # Calculate the smallest distances between the base and end points of the new wall and the base and end points of the previously existing IFC wall
                    distance_base = min(math.dist(new_wall_base, ifc_wall_base), math.dist(new_wall_base, ifc_wall_end))
                    distance_end = min(math.dist(new_wall_end, ifc_wall_base), math.dist(new_wall_end, ifc_wall_end))

                    # An existing wall may either be connected to the beginning of the new wall, to its end, connect to it 
                    # along its path (.ATPATH. connection), or unconnected. At path connections are not dealt with in this
                    # methodology however, because the comparison of walls is based on point cloud walls and ifc walls having 
                    # continuous planes on both sides

                    # If the smallest distance is less than 0.55m, create a new IfcRelConnectsPathElements relationship
                    # max(0.55, 3.0*ifc_w_dimy)
                    ifc_w_dimy = ifc_wall.Representation.Representations[1].Items[0].SweptArea.YDim
                    walls_already_connected = False
                    if distance_base < max(0.55, 2.2*ifc_w_dimy):
                        for i in newWalls_matched_to_eachother:
                            if newWall in i and ifc_wall in i:
                                walls_already_connected = True
                        if walls_already_connected is False:
                            newWalls_matched_to_eachother.append([newWall, ifc_wall])
                            # if starting points are connected
                            if math.dist(new_wall_base, ifc_wall_base) < max(0.55, 2.2*ifc_w_dimy):
                                rel_connects_path_elements = model.create_entity('IfcRelConnectsPathElements')
                                rel_connects_path_elements.RelatingElement = ifc_wall
                                rel_connects_path_elements.RelatedElement = newWall
                                rel_connects_path_elements.RelatedConnectionType = 'ATSTART'
                                rel_connects_path_elements.GlobalId = ifcopenshell.guid.compress(uuid.uuid1().hex)
                                rel_connects_path_elements.Name = str(f'{newWall.GlobalId} + | + {ifc_wall.GlobalId}')
                                rel_connects_path_elements.OwnerHistory = owner_history 
                                rel_connects_path_elements.RelatingConnectionType = 'ATSTART'
                                rel_connects_path_elements.Description = 'Structural'
                            #if the starting point of the new wall is connected to the end of the other wall
                            elif math.dist(new_wall_base, ifc_wall_end) < max(0.55, 3.0*ifc_w_dimy):
                                rel_connects_path_elements = model.create_entity('IfcRelConnectsPathElements')
                                rel_connects_path_elements.RelatingElement = ifc_wall
                                rel_connects_path_elements.RelatedElement = newWall
                                rel_connects_path_elements.RelatedConnectionType = 'ATSTART'
                                rel_connects_path_elements.GlobalId = ifcopenshell.guid.compress(uuid.uuid1().hex)
                                rel_connects_path_elements.Name = str(f'{newWall.GlobalId} + | + {ifc_wall.GlobalId}')
                                rel_connects_path_elements.OwnerHistory = owner_history 
                                rel_connects_path_elements.RelatingConnectionType = 'ATEND'
                                rel_connects_path_elements.Description = 'Structural'
                            
                    
                    if distance_end < max(0.55, 2.2*ifc_w_dimy):
                        for i in newWalls_matched_to_eachother:
                            if newWall in i and ifc_wall in i:
                                walls_already_connected = True
                        if walls_already_connected is False:
                            newWalls_matched_to_eachother.append([newWall, ifc_wall])
                            # if the end of the new wall is connected to the start of the other wall
                            if math.dist(new_wall_end, ifc_wall_base) < max(0.55, 2.2*ifc_w_dimy):
                                rel_connects_path_elements = model.create_entity('IfcRelConnectsPathElements')
                                rel_connects_path_elements.RelatingElement = ifc_wall
                                rel_connects_path_elements.RelatedElement = newWall
                                rel_connects_path_elements.RelatedConnectionType = 'ATEND'
                                rel_connects_path_elements.GlobalId = ifcopenshell.guid.compress(uuid.uuid1().hex)
                                rel_connects_path_elements.Name = str(f'{newWall.GlobalId} + | + {ifc_wall.GlobalId}')
                                rel_connects_path_elements.OwnerHistory = owner_history 
                                rel_connects_path_elements.RelatingConnectionType = 'ATSTART'
                                rel_connects_path_elements.Description = 'Structural'
                            # if the end of the new wall is connected to the end of the other wall
                            elif math.dist(new_wall_end, ifc_wall_end) < max(0.55, 2.2*ifc_w_dimy):
                                rel_connects_path_elements = model.create_entity('IfcRelConnectsPathElements')
                                rel_connects_path_elements.RelatingElement = ifc_wall
                                rel_connects_path_elements.RelatedElement = newWall
                                rel_connects_path_elements.RelatedConnectionType = 'ATEND'
                                rel_connects_path_elements.GlobalId = ifcopenshell.guid.compress(uuid.uuid1().hex)
                                rel_connects_path_elements.Name = str(f'{newWall.GlobalId} + | + {ifc_wall.GlobalId}')
                                rel_connects_path_elements.OwnerHistory = owner_history 
                                rel_connects_path_elements.RelatingConnectionType = 'ATEND'
                                rel_connects_path_elements.Description = 'Structural'
                    
            
        else:
            print("No existing wall found.")

    from datetime import datetime
    import ifcopenshell
    current_datetime = datetime.now()
    
    # Format the date and time as a string in the specified format
    formatted_datetime = current_datetime.strftime("%d%m%y_%H%M")
    
    # Construct the new filename by appending the formatted date and time
    # If you want to use a specific name or modify it, you can do so here
    new_filename = f"modified_ifc_file_{formatted_datetime}.ifc"
    
    # Write the modified IFC file with the new filename
    model.write(new_filename)
    
    # Return the new filename
    return new_filename       
