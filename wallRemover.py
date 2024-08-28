# This code is part of the Master Thesis of Jean van der Meer presented to the Eindhoven University of Technology
import ifcopenshell
import pandas as pd
import numpy as np
import os as os
import ifcopenshell.api

# Here the deletion of non matched IFC walls is handled for the case where the entire building is scanned. If the entire building was scanned
# then all walls in the model that are not in the list ifc_walls_matched can be deleted, which is done here. In Room Mode, where only a specific
# section of the building is scanned, a unique list of walls to be deleted is produced at the wall matching step, and this list is used at that
# version of the wall deleter function.

def wallDeleter(model, ifc_walls_matched):
    for wall in model.by_type("IfcWallStandardCase"):
        # we want to delete all IfcWalls that did not find a match with a point cloud wall
        if wall.GlobalId not in ifc_walls_matched:
            # before deleting the wall we need to delete all decompositions of the wall such as doors, windows and openings it had
            # otherwise if the wall were deleted first we wouldn't be able to connect their existence to a wall and they
            # would just be unconnnected entities hard to find and making the model less consistent
            extras2 = ifcopenshell.util.element.get_decomposition(wall)
            print(extras2)
            for extra in extras2:
                # delete the decompositions of the not-matched wall being parsed
                ifcopenshell.api.run("root.remove_product", model, product=extra)

    for wall in model.by_type("IfcWallStandardCase"):
        # after deleting the decompositions the walls without a match can be deleted
        if wall.GlobalId not in ifc_walls_matched:
            ifcopenshell.api.run("root.remove_product", model, product=wall)
            