# This code is part of the Master Thesis of Jean van der Meer presented to the Eindhoven University of Technology
import ifcopenshell
import pandas as pd
import numpy as np
import os as os
import ifcopenshell.util.element
import ifcopenshell.api

def wallDeleterRM(model, ifc_walls_to_delete):
    #First, remove all decompositions of the walls
    for wall_id in ifc_walls_to_delete:
        wall = model.by_id(wall_id)
        if wall:
            extras2 = ifcopenshell.util.element.get_decomposition(wall)
            print(f"Decompositions for wall {wall_id}: {extras2}")
            # before deleting the wall we need to delete all decompositions of the wall such as doors, windows and openings it had
            # otherwise if the wall were deleted first we wouldn't be able to connect their existence to a wall and they
            # would just be unconnnected entities hard to find and making the model less consistent
            for extra in extras2:
                try:
                    ifcopenshell.api.run("root.remove_product", model, product=extra)
                    print(f"Removed decomposition product: {extra}")
                except Exception as e:
                    print(f"Error removing decomposition product {extra}: {e}")

    #Then, remove the walls themselves
    for wall_id in ifc_walls_to_delete:
        wall = model.by_id(wall_id)
        if wall:
            try:
                ifcopenshell.api.run("root.remove_product", model, product=wall)
                print(f"Removed wall: {wall}")
            except Exception as e:
                print(f"Error removing wall {wall_id}: {e}")

